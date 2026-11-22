"""LLM-судья для вопросов с открытым ответом (open_answer).

Задача: студент пишет ответ свободной формой, ML сверяет его с эталоном и
оценивает, насколько ответ верный. Оценка дробная — «примерно правильно» это
0.5, а не 0 или 1.

Почему не сравнение строк: правильных формулировок бывает много, и совпадение
по подстроке не отличает «верно по сути» от «упомянул ключевое слово».

Контракт:
  - на входе: текст вопроса, эталонный ответ, опорные критерии, ответ студента;
  - на выходе: Verdict(score 0..1, feedback).

Детерминированный fallback (спека §5.3): если LLM не ответил или вернул кривой
JSON — score=0.0 и feedback-заглушка. Один сбойный вопрос не роняет всю
попытку: single_choice-вопросы всё равно засчитываются.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from app.services.llm import MAX_TOKENS_SMALL_JSON, LLMClient


SYSTEM_PROMPT = """\
Ты — строгий, но справедливый преподаватель. Оценишь ответ студента по эталону.

Правила:
1. Оценивай по СУЩЕСТВУ: совпадает ли смысл ответа с эталоном. Разная формулировка
   при том же смысле — это верно.
2. Частично верный ответ — частичный балл: score между 0 и 1.
   - 1.0 — ответ по сути совпадает с эталоном;
   - 0.5..0.9 — верно по главному, но пропущено или перепутано второстепенное;
   - 0.0..0.4 — неверно или бессмысленно.
3. Опорные пункты из <criteria> — чек-лист: каждый покрытый пункт тянет балл вверх.
4. Если ответ противоречит эталону — score = 0, даже если звучит гладко.
5. Если <reference_answer> пуст («—») — эталона нет, оценивай ТОЛЬКО по <criteria>
   и смыслу вопроса: покрыты критерии — высокий балл, не покрыты — низкий.
6. feedback — 1-3 предложения на русском: что верно, что неверно, чего не хватает.
   Не хвали заранее и не пиши вступлений вроде «Вот ваш разбор».
"""

USER_TEMPLATE = """\
<question>
{question}
</question>

<reference_answer>
{reference}
</reference_answer>

<criteria>
{criteria}
</criteria>

<student_answer>
{student}
</student_answer>
"""

# Схема ответа: без неё LLM на json_object иногда возвращает пустой объект,
# parse_verdict его отвергает, и вопрос тихо получает score=0.0 — то есть
# открытые вопросы всегда «неверные». Схема делает такой ответ невозможным.
VERDICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["score", "feedback"],
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "feedback": {"type": "string"},
    },
}

FALLBACK_FEEDBACK = "Не удалось автоматически оценить открытый ответ."


@dataclass
class Verdict:
    """Вердикт судьи по одному вопросу."""

    score: float
    feedback: str


def parse_verdict(data: dict) -> Verdict:
    """Проверить JSON-ответ судьи и превратить в Verdict.

    Raises:
        ValueError: нет score, score вне 0..1, пустой feedback.
    """
    if not isinstance(data, dict):
        raise ValueError("verdict must be a JSON object")
    raw_score = data.get("score")
    if raw_score is None:
        raise ValueError("verdict.score is required")
    score = float(raw_score)
    if not (0.0 <= score <= 1.0):
        raise ValueError(f"verdict.score must be in [0.0, 1.0], got {score}")

    feedback = str(data.get("feedback") or "").strip()
    if not feedback:
        raise ValueError("verdict.feedback is required")

    return Verdict(score=score, feedback=feedback)


class OpenAnswerJudge:
    __test__ = False  # не pytest-класс

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def judge(
        self,
        *,
        question: str,
        reference_answer: str,
        criteria: list[str],
        student_answer: str,
    ) -> Verdict:
        """Оценить ответ студента по эталону.

        Пустой ответ студента — без LLM: результат детерминирован.
        Эталона нет, но критерии (`key_points`) есть — LLM всё равно зовём:
        он оценивает по критериям и смыслу вопроса (см. правило 5 в промпте).
        Не оценивать нечем только когда нет ни эталона, ни критериев.
        """
        if not student_answer.strip():
            return Verdict(score=0.0, feedback="Ответ пустой.")

        if not reference_answer.strip() and not criteria:
            return Verdict(
                score=0.0,
                feedback="У вопроса нет ни эталона, ни критериев — оценить нечем.",
            )

        user_message = USER_TEMPLATE.format(
            question=question.strip(),
            reference=reference_answer.strip() or "—",
            criteria="\n".join(f"- {c.strip()}" for c in criteria) if criteria else "-",
            student=student_answer.strip(),
        )

        try:
            return await self.llm.chat_json(
                user_message,
                validator=parse_verdict,
                system_prompt=SYSTEM_PROMPT,
                max_retries=2,
                schema=VERDICT_SCHEMA,
                # Ответ судьи — 100–200 токенов: большой max_tokens упирается
                # в кредитный лимит OpenRouter (HTTP 402) на free-моделях.
                max_tokens=MAX_TOKENS_SMALL_JSON,
            )
        except Exception as e:
            logger.warning(f"OpenAnswerJudge: LLM failed ({type(e).__name__}: {e}) → score=0.0")
            return Verdict(score=0.0, feedback=FALLBACK_FEEDBACK)
