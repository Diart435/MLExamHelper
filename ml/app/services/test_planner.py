"""Планировщик размера теста: сколько вопросов материал реально покрывает.

Зачем отдельный вызов LLM, а не «пусть генератор сам решит»:

  Число вопросов зашито в JSON Schema генератора (`minItems = maxItems = N`).
  Это жёсткая гарантия, что модель не вернёт 25 вопросов вместо 10 — на
  free-моделях OpenRouter мусорный JSON иначе не редкость. Если поручить модели
  выбрать N в том же вызове, схема ослабеет до `minItems=1, maxItems=30` и
  брак вернётся.

  Планировщик отвечает ДО генерации → N известен → схема остаётся жёсткой.
  Бонус: мы видим, почему получилось столько вопросов (темы из `topics`), и эти
  же темы уходят в промпт генератора — вопросы почти не дублируются.

Планировщик видит ровно тот же контекст, что и генератор: обещать 30 вопросов
по чанкам, которых у нас нет, нельзя — генерировать придётся по этому же тексту.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.contracts import MAX_QUESTIONS, MIN_QUESTIONS
from app.services.llm import LLMClient


# Насколько «глубокий» вопрос требует материала: чем сложнее, тем меньше
# вопросов из того же текста получается. Подставляется в промпт планировщика.
_DIFFICULTY_HINT = {
    "easy": "easy (вспомнить факт — вопрос получается из одного абзаца)",
    "medium": "medium (применить факт в новой ситуации — нужен контекст вокруг него)",
    "hard": "hard (проанализировать и сделать вывод — нужен целый раздел)",
}


def _planner_prompt(difficulty: str) -> str:
    hint = _DIFFICULTY_HINT.get(difficulty, difficulty)
    return f"""\
Ты — преподаватель, который готовит тест по учебным материалам.
Твоя задача — НЕ писать вопросы, а оценить, сколько вопросов материал покрывает.

Правила:
1. Перебери материал и выдели отдельные ПРОВЕРЯЕМЫЕ факты: определения, свойства,
   формулы, правила, примеры, даты, классификации. Один факт = один вопрос.
   Разные формулировки одного факта = один вопрос.
2. Не выдумывай: если в материале нет информации о чём-то — этого не будет в вопросе.
3. num_questions = число найденных фактов, с ограничением:
   - меньше {MIN_QUESTIONS} не бывает (материал совсем пустой — верни
     {MIN_QUESTIONS} и возьми самый базовый факт);
   - больше {MAX_QUESTIONS} не бывает (потолок).
   Если фактов 3 — верни 3. Не добирай до 5 и не раздувай до {MAX_QUESTIONS}.
4. Учитывай сложность теста — {hint}. На высокой сложности один вопрос требует
   больше материала, поэтому при прочих равных num_questions меньше.
5. topics — по одному короткому названию на каждый вопрос, в том же порядке.
   Это план тем: по нему потом пишутся сами вопросы.

Формат ответа — СТРОГО один JSON-объект:
{{"num_questions": <{MIN_QUESTIONS}..{MAX_QUESTIONS}>, "topics": ["<тема 1>", "<тема 2>"]}}
Никакого текста до или после JSON.
"""


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["num_questions", "topics"],
    "properties": {
        "num_questions": {"type": "integer", "minimum": MIN_QUESTIONS, "maximum": MAX_QUESTIONS},
        "topics": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_QUESTIONS,
            "items": {"type": "string"},
        },
    },
}


@dataclass
class TestPlan:
    """План теста: сколько вопросов и на какие темы."""

    __test__ = False  # не pytest-класс

    num_questions: int
    topics: list[str]

    @classmethod
    def from_dict(cls, d: dict) -> "TestPlan":
        """Собрать план из ответа LLM.

        num_questions вне 1..30 — обрезаем по границам и логируем: JSON Schema
        этого не пропустит, но если провайдер деградировал до json_object, модель
        может ответить «50 вопросов». Отказываться из-за одного числа смысла
        нет — план всё равно пойдёт в генератор, который всё проверит.

        Raises:
            ValueError: план не согласован — тем меньше, чем вопросов (достроить
                        их нечем), или тема пустая. `chat_json` на такой ответ ретраит.
        """
        n = int(d["num_questions"])
        if not (MIN_QUESTIONS <= n <= MAX_QUESTIONS):
            clamped = max(MIN_QUESTIONS, min(MAX_QUESTIONS, n))
            logger.warning(
                f"TestPlanner: num_questions={n} вне [{MIN_QUESTIONS}, {MAX_QUESTIONS}] "
                f"— берём {clamped}"
            )
            n = clamped
        raw_topics = d.get("topics") or []
        if not isinstance(raw_topics, list):
            raise ValueError("topics must be a list")
        topics = [str(t).strip() for t in raw_topics]
        if len(topics) > n:
            logger.warning(
                f"TestPlanner: тем {len(topics)} больше, чем вопросов {n} — обрезаем"
            )
            topics = topics[:n]
        if len(topics) != n:
            raise ValueError(f"topics count {len(topics)} != num_questions {n}")
        if any(not t for t in topics):
            raise ValueError("topics must not be empty")
        return cls(num_questions=n, topics=topics)


async def plan_test(
    llm: LLMClient,
    digest: str,
    difficulty: str,
) -> TestPlan:
    """Сколько вопросов покрывает материал и на какие темы.

    Raises:
        RuntimeError: LLM не ответила валидным JSON (после ретраев).
    """
    user_message = (
        f"Материалы:\n{digest}\n\n"
        f"Определи num_questions и topics. Сложность теста: {difficulty}."
    )
    plan = await llm.chat_json(
        user_message,
        validator=TestPlan.from_dict,
        system_prompt=_planner_prompt(difficulty),
        schema=PLAN_SCHEMA,
    )
    logger.info(
        f"TestPlanner: difficulty={difficulty}, num_questions={plan.num_questions}, "
        f"topics={plan.topics}"
    )
    return plan
