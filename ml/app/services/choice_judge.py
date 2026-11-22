"""LLM-судья для вопросов с вариантами ответа (single_choice / multi_choice).

Зачем он нужен
==============
Эталон (`answer_key`) по контракту v4.1 лежит в БД (`test_questions.answer_key`),
а Redis (`services/answer_store.py`) держит его резервную копию. Но эталон
может отсутствовать в обоих местах: Redis очистился (TTL 30 суток), тест
сгенерирован до появления колонки в БД. Тогда правильный вариант не известен —
и без страховки попытка была бы засчитана как «всё неверно».

Судья решает это: по тексту вопроса и вариантам ответа определяет, какие
варианты правильные.

Контракт:
  - на входе: текст вопроса, список вариантов, тип вопроса;
  - на выходе: `ChoiceVerdict` — правильные индексы + текст правильного
    варианта + объяснение.

Детерминированный fallback: если LLM не ответил или вернул кривой JSON —
вердикт «правильных вариантов нет», и грейдер ставит score=0.0 с явным
feedback. Один сбойный вопрос не роняет всю попытку.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from app.services.llm import MAX_TOKENS_SMALL_JSON, LLMClient


SYSTEM_PROMPT = """\
Ты — строгий преподаватель. Определи, какие варианты ответа правильные.

Правила:
1. Один вопрос — один правильный набор вариантов. Для single_choice правильный
   ровно ОДИН вариант. Для multi_choice правильных ДВА или ТРИ.
2. Смотри только на текст вопроса и варианты ответа. Если из них нельзя
   однозначно определить правильный вариант — не выдумывай: верни пустой
   список correct_indexes.
3. Варианты, не содержащие правильного ответа, не выбирай.
4. explanation — 1 предложение на русском: почему правильны именно эти варианты.
"""


USER_TEMPLATE = """\
<question>
{question}
</question>

<options>
{options}
</options>

<question_type>
{qtype}
</question_type>
"""


# Схема ответа: без неё модель на json_object иногда возвращает пустой объект,
# который parse_verdict отвергает, — и вопрос тихо получает score=0.0.
VERDICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["correct_indexes", "explanation"],
    "properties": {
        "correct_indexes": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "integer", "minimum": 0},
        },
        "explanation": {"type": "string"},
    },
}

FALLBACK_FEEDBACK = "Не удалось автоматически оценить ответ."


@dataclass
class ChoiceVerdict:
    """Вердикт судьи по вопросу с вариантами ответа."""

    correct_indexes: list[int]
    explanation: str = ""

    @property
    def found(self) -> bool:
        """Нашёл ли судья хотя бы один правильный вариант."""
        return bool(self.correct_indexes)


def parse_choice_verdict(data: dict, num_options: int) -> ChoiceVerdict:
    """Проверить JSON-ответ судьи и превратить в ChoiceVerdict.

    Индексы вне диапазона вариантов отбрасываются: мусорный индекс не должен
    ломать проверку.

    Raises:
        ValueError: нет correct_indexes или они не массив.
    """
    if not isinstance(data, dict):
        raise ValueError("verdict must be a JSON object")
    raw = data.get("correct_indexes")
    if raw is None:
        raise ValueError("verdict.correct_indexes is required")
    if not isinstance(raw, list):
        raise ValueError("verdict.correct_indexes must be a list")

    indexes: list[int] = []
    for item in raw:
        try:
            idx = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < num_options and idx not in indexes:
            indexes.append(idx)

    return ChoiceVerdict(
        correct_indexes=sorted(indexes),
        explanation=str(data.get("explanation") or "").strip(),
    )


class ChoiceJudge:
    """LLM-судья для single_choice / multi_choice."""

    __test__ = False  # не pytest-класс

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def judge(
        self,
        *,
        question: str,
        options: list[str],
        question_type: str = "single_choice",
    ) -> ChoiceVerdict:
        """Определить правильные варианты ответа.

        Пустые варианты проверяются без LLM: определять нечего.
        """
        if not options:
            return ChoiceVerdict(correct_indexes=[], explanation="")

        user_message = USER_TEMPLATE.format(
            question=question.strip(),
            options="\n".join(
                f"{i}. {str(o).strip()}" for i, o in enumerate(options)
            ),
            qtype=question_type,
        )

        try:
            return await self.llm.chat_json(
                user_message,
                validator=lambda data: parse_choice_verdict(data, len(options)),
                system_prompt=SYSTEM_PROMPT,
                max_retries=2,
                schema=VERDICT_SCHEMA,
                # Ответ судьи — 100–200 токенов: большой max_tokens упирается
                # в кредитный лимит OpenRouter (HTTP 402) на free-моделях.
                max_tokens=MAX_TOKENS_SMALL_JSON,
            )
        except Exception as e:
            logger.warning(f"ChoiceJudge: LLM failed ({type(e).__name__}: {e}) → нет эталона")
            return ChoiceVerdict(correct_indexes=[], explanation="")
