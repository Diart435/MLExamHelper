"""Планировщик размера теста: сколько вопросов материал реально покрывает.

Зачем отдельный вызов LLM, а не «пусть генератор сам решит»:

  Число вопросов зашито в JSON Schema генератора (`minItems = maxItems = N`).
  Это жёсткая гарантия, что модель не вернёт 25 вопросов вместо 10 — на
  free-моделях провайдера (RouterAI) мусорный JSON иначе не редкость. Если
  поручить модели выбрать N в том же вызове, схема ослабеет до `minItems=1,
  maxItems=30` и брак вернётся.

  Планировщик отвечает ДО генерации → N известен → схема остаётся жёсткой.
  Бонус: мы видим, почему получилось столько вопросов (темы из `topics`), и эти
  же темы уходят в промпт генератора — вопросы почти не дублируются.

Планировщик видит ровно тот же контекст, что и генератор: обещать 30 вопросов
по чанкам, которых у нас нет, нельзя — генерировать придётся по этому же тексту.

Семантика размера: `num_questions` = ЧИСЛО ПРОВЕРЯЕМЫХ ФАКТОВ, найденных в
материале. Жёсткие границы — 1..30 (`MIN_QUESTIONS`/`MAX_QUESTIONS` в
`app/contracts.py`): меньше 1 только для вырожденного случая «материал совсем
пустой», больше 30 — не бывает.

  - фактов 3  → вернуть 3 (выдумывать, чтобы добить число, нельзя);
  - фактов 40 → вернуть 30 (30 самых важных);
  - фактов 30 → вернуть ровно 30: «если материалы позволяют — делаем 30».

Размер определяет ТОЛЬКО планировщик. Backend в этом не участвует: поля
`amount_questions` в контракте нет (v4.2). Сложность теста на размер не
влияет — она влияет только на микс типов вопросов (`question_mix` в
`test_generator.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.contracts import MAX_QUESTIONS, MIN_QUESTIONS
from app.services.llm import LLMClient


def _planner_prompt() -> str:
    """Промпт планировщика: посчитать факты, не выдумывая ни одного.

    Границы 1..30 — рамка, а не цель: если фактов больше 30 — берём 30 самых
    важных, если фактов 3 — возвращаем 3. Добивать число выдуманными фактами
    нельзя.
    """
    return """\
Ты — преподаватель, который готовит тест по учебным материалам.
Твоя задача — НЕ писать вопросы, а оценить, сколько вопросов материал покрывает.

Правила:
1. Перебери материал и выдели отдельные ПРОВЕРЯЕМЫЕ факты: определения, свойства,
   формулы, правила, примеры, даты, классификации. Один факт = один вопрос.
   Разные формулировки одного факта = один вопрос.
2. Не выдумывай: если в материале нет информации о чём-то — этого не будет в вопросе.
3. num_questions = число найденных фактов, с ограничением:
   - меньше 1 не бывает (материал совсем пустой — верни 1 и возьми самый базовый факт);
   - больше 30 не бывает.
   Если фактов 3 — верни 3. Если фактов 40 — верни 30.
4. Границы 1..30 — это рамка, а не цель: возвращай ровно столько вопросов,
   сколько фактов нашлось, но не больше 30. Если фактов больше 30 — возьми 30
   самых важных. Добивать число выдуманными фактами нельзя.
5. topics — по одному короткому названию на каждый вопрос, в том же порядке.
   Это план тем: по нему потом пишутся сами вопросы.

Формат ответа — СТРОГО один JSON-объект:
{"num_questions": <1..30>, "topics": ["<тема 1>", "<тема 2>"]}
Никакого текста до или после JSON.
"""


def _plan_schema() -> dict[str, Any]:
    """JSON Schema ответа планировщика.

    Границы жёсткие: `MIN_QUESTIONS..MAX_QUESTIONS` (= 1..30). Схема —
    единственное, что структурно запрещает модели превысить их.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["num_questions", "topics"],
        "properties": {
            "num_questions": {
                "type": "integer",
                "minimum": MIN_QUESTIONS,
                "maximum": MAX_QUESTIONS,
            },
            "topics": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_QUESTIONS,
                "items": {"type": "string"},
            },
        },
    }


# Схема планировщика — с жёсткими границами 1..30.
PLAN_SCHEMA: dict[str, Any] = _plan_schema()


@dataclass
class TestPlan:
    """План теста: сколько вопросов и на какие темы."""

    __test__ = False  # не pytest-класс

    num_questions: int
    topics: list[str]

    @classmethod
    def from_dict(cls, d: dict) -> "TestPlan":
        """Собрать план из ответа LLM.

        num_questions вне [1..30] — обрезаем по границам и логируем: JSON Schema
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
                f"TestPlanner: num_questions={n} вне "
                f"[{MIN_QUESTIONS}, {MAX_QUESTIONS}] — берём {clamped}"
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


async def plan_test(llm: LLMClient, digest: str) -> TestPlan:
    """Сколько вопросов покрывает материал и на какие темы.

    Размер = число проверяемых фактов в материале, границы 1..30. Если фактов
    30 или больше — вернём ровно 30 (самые важные); если 3 — вернём 3. Выдумывать
    факты, чтобы добить число, нельзя.

    Raises:
        RuntimeError: LLM не ответила валидным JSON (после ретраев).
    """
    user_message = (
        f"Материалы:\n{digest}\n\n"
        f"Определи num_questions и topics."
    )
    plan = await llm.chat_json(
        user_message,
        validator=lambda d: TestPlan.from_dict(d),
        system_prompt=_planner_prompt(),
        schema=_plan_schema(),
    )
    logger.info(
        f"TestPlanner: num_questions={plan.num_questions}, "
        f"topics={plan.topics}"
    )
    return plan
