"""Тесты планировщика размера теста (services/test_planner.py).

Планировщик отвечает ДО генерации: сколько вопросов покрывает материал и на
какие темы. От его ответа зависят и размер теста, и жёсткая JSON Schema
генератора (minItems = maxItems = N), поэтому план должен быть валидным, а не
«примерно правильным».

Семантика размера: `num_questions` = число проверяемых фактов в материале,
границы жёсткие 1..30. Если фактов 30 или больше — ровно 30; если 3 — 3.
Backend в выборе размера не участвует, сложность на размер не влияет.

Здесь мок не подменяет `chat_json` целиком — подменяется только сырой вызов
`_chat_once_raw`, чтобы проверить и retry из LLMClient, и схему, которая
уходит провайдеру.
"""

from __future__ import annotations

import json

import pytest

from app.contracts import MAX_QUESTIONS, MIN_QUESTIONS
from app.services.llm import LLMClient
from app.services.test_planner import (
    PLAN_SCHEMA,
    TestPlan,
    _plan_schema,
    plan_test,
)


def _make_llm(responses) -> LLMClient:
    """LLMClient без сети: `_chat_once_raw` отдаёт заранее заданные ответы."""
    llm = LLMClient.__new__(LLMClient)
    llm._model = "fake"
    llm._client = None
    llm.requests = []  # type: ignore[attr-defined]
    it = iter(responses)

    async def fake_raw(system_prompt, user_message, *, fmt="plain", schema=None, max_tokens=None, attempt=""):
        llm.requests.append({
            "fmt": fmt, "schema": schema,
            "system": system_prompt, "user": user_message,
            "max_tokens": max_tokens,
        })
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    llm._chat_once_raw = fake_raw  # type: ignore[method-assign]
    return llm


# ============================================================================
# TestPlan — валидация ответа планировщика
# ============================================================================

class TestPlanValidation:
    def test_valid_plan(self):
        plan = TestPlan.from_dict({
            "num_questions": 5,
            "topics": ["тема 1", "тема 2", "тема 3", "тема 4", "тема 5"],
        })
        assert plan.num_questions == 5
        assert len(plan.topics) == 5

    def test_topics_count_must_match_num_questions(self):
        with pytest.raises(ValueError, match="topics count"):
            TestPlan.from_dict({"num_questions": 5, "topics": ["одна тема"]})

    def test_num_questions_below_minimum_is_clamped(self):
        """JSON Schema этого не пропустит, но на json_object модель может ответить 0."""
        plan = TestPlan.from_dict({"num_questions": 0, "topics": ["тема"]})
        assert plan.num_questions == MIN_QUESTIONS

    def test_num_questions_above_maximum_is_clamped(self):
        plan = TestPlan.from_dict({
            "num_questions": MAX_QUESTIONS + 1,
            "topics": ["т"] * (MAX_QUESTIONS + 1),
        })
        assert plan.num_questions == MAX_QUESTIONS
        assert len(plan.topics) == MAX_QUESTIONS

    def test_extra_topics_are_truncated(self):
        plan = TestPlan.from_dict({"num_questions": 2, "topics": ["а", "б", "в"]})
        assert plan.topics == ["а", "б"]

    def test_minimum_is_one_question(self):
        plan = TestPlan.from_dict({"num_questions": MIN_QUESTIONS, "topics": ["тема"]})
        assert plan.num_questions == 1

    def test_empty_topic_raises(self):
        with pytest.raises(ValueError, match="topics must not be empty"):
            TestPlan.from_dict({"num_questions": 2, "topics": ["тема", "   "]})

    def test_topics_must_be_list(self):
        with pytest.raises(ValueError, match="topics must be a list"):
            TestPlan.from_dict({"num_questions": 1, "topics": "тема"})


# ============================================================================
# plan_test — вызов LLM
# ============================================================================

class TestPlanTest:
    @pytest.mark.asyncio
    async def test_returns_plan(self):
        llm = _make_llm([json.dumps({
            "num_questions": 5,
            "topics": ["тема 1", "тема 2", "тема 3", "тема 4", "тема 5"],
        })])
        plan = await plan_test(llm, digest="текст материала")
        assert plan.num_questions == 5
        assert plan.topics[0] == "тема 1"

    @pytest.mark.asyncio
    async def test_uses_json_schema(self):
        llm = _make_llm([json.dumps({"num_questions": 1, "topics": ["тема"]})])
        await plan_test(llm, digest="текст материала")
        assert llm.requests[0]["fmt"] == "json_schema"
        assert llm.requests[0]["schema"] == PLAN_SCHEMA

    @pytest.mark.asyncio
    async def test_schema_bounds_match_contract(self):
        assert PLAN_SCHEMA["properties"]["num_questions"]["minimum"] == MIN_QUESTIONS
        assert PLAN_SCHEMA["properties"]["num_questions"]["maximum"] == MAX_QUESTIONS

    @pytest.mark.asyncio
    async def test_digest_goes_to_llm(self):
        llm = _make_llm([json.dumps({"num_questions": 1, "topics": ["тема"]})])
        await plan_test(llm, digest="текст материала")
        request = llm.requests[0]
        assert "текст материала" in request["user"]

    @pytest.mark.asyncio
    async def test_difficulty_does_not_affect_prompt(self):
        """Сложность на размер не влияет: планировщик о ней не знает."""
        llm = _make_llm([json.dumps({"num_questions": 1, "topics": ["тема"]})])
        await plan_test(llm, digest="текст материала")
        system = llm.requests[0]["system"]
        assert "сложност" not in system.lower()
        assert "hard" not in system.lower()

    @pytest.mark.asyncio
    async def test_retries_on_invalid_plan(self):
        """Темы не совпали с числом вопросов → LLMClient повторяет с уточнением."""
        llm = _make_llm([
            json.dumps({"num_questions": 5, "topics": ["только одна"]}),
            json.dumps({
                "num_questions": 5,
                "topics": ["тема 1", "тема 2", "тема 3", "тема 4", "тема 5"],
            }),
        ])
        plan = await plan_test(llm, digest="текст материала")
        assert plan.num_questions == 5
        assert len(llm.requests) == 2
        assert "предыдущий ответ был невалидным" in llm.requests[1]["system"]

    @pytest.mark.asyncio
    async def test_raises_after_retries(self):
        """Все ответы невалидны → RuntimeError, а не тест на 5 вопросов «на глаз»."""
        bad = json.dumps({"num_questions": 5, "topics": ["одна"]})
        llm = _make_llm([bad, bad, bad])
        with pytest.raises(RuntimeError, match="chat_json failed"):
            await plan_test(llm, digest="текст материала")

    @pytest.mark.asyncio
    async def test_planner_does_not_write_questions(self):
        """Планировщик не генерирует вопросы — только считает и называет темы."""
        llm = _make_llm([json.dumps({"num_questions": 2, "topics": ["тема 1", "тема 2"]})])
        await plan_test(llm, digest="текст материала")
        assert "НЕ писать вопросы" in llm.requests[0]["system"]


# ============================================================================
#  Границы размера: 1..30, размер = число фактов
# ============================================================================

class TestQuestionCountBounds:
    """Размер = число проверяемых фактов, жёсткие границы 1..30.

    Backend в выборе размера не участвует, добивать число выдуманными
    фактами нельзя.
    """

    def test_plan_schema_has_no_cap_parameter(self):
        """Схема строится без потолка — границы жёстко 1..30."""
        schema = _plan_schema()
        assert schema["properties"]["num_questions"]["minimum"] == MIN_QUESTIONS
        assert schema["properties"]["num_questions"]["maximum"] == MAX_QUESTIONS
        assert schema["properties"]["topics"]["maxItems"] == MAX_QUESTIONS
        assert schema["properties"]["topics"]["minItems"] == 1
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["num_questions", "topics"]

    def test_plan_schema_equals_module_constant(self):
        assert PLAN_SCHEMA == _plan_schema()

    def test_from_dict_clamps_above_maximum(self):
        """Модель ответила больше 30 — обрезаем по границам, не падаем."""
        plan = TestPlan.from_dict(
            {"num_questions": 40, "topics": ["т"] * 40},
        )
        assert plan.num_questions == MAX_QUESTIONS
        assert len(plan.topics) == MAX_QUESTIONS

    def test_from_dict_keeps_small_count(self):
        """Фактов 3 — возвращаем 3, добивать нельзя."""
        plan = TestPlan.from_dict(
            {"num_questions": 3, "topics": ["а", "б", "в"]},
        )
        assert plan.num_questions == 3
        assert len(plan.topics) == 3

    @pytest.mark.asyncio
    async def test_thirty_facts_give_thirty_questions(self):
        """«Если материалы позволяют — делаем 30»: фактов 30 → ровно 30."""
        llm = _make_llm([json.dumps({
            "num_questions": MAX_QUESTIONS,
            "topics": ["т"] * MAX_QUESTIONS,
        })])
        plan = await plan_test(llm, digest="текст материала")
        assert plan.num_questions == MAX_QUESTIONS
        assert len(plan.topics) == MAX_QUESTIONS

    @pytest.mark.asyncio
    async def test_few_facts_give_few_questions(self):
        """Фактов 3 — план на 3 вопроса, а не на 30."""
        llm = _make_llm([json.dumps({
            "num_questions": 3,
            "topics": ["а", "б", "в"],
        })])
        plan = await plan_test(llm, digest="текст материала")
        assert plan.num_questions == 3
        assert len(plan.topics) == 3

    @pytest.mark.asyncio
    async def test_schema_sent_to_provider_has_hard_bounds(self):
        """Провайдер получает схему с границами 1..30 — потолка от backend нет."""
        llm = _make_llm([json.dumps({"num_questions": 1, "topics": ["тема"]})])
        await plan_test(llm, digest="текст материала")
        schema = llm.requests[0]["schema"]
        assert schema["properties"]["num_questions"]["maximum"] == MAX_QUESTIONS
        assert schema["properties"]["topics"]["maxItems"] == MAX_QUESTIONS

    @pytest.mark.asyncio
    async def test_prompt_says_thirty_is_allowed(self):
        """Промпт обязан разрешать 30: иначе модель уходит в «безопасные» 10."""
        llm = _make_llm([json.dumps({"num_questions": 1, "topics": ["тема"]})])
        await plan_test(llm, digest="текст материала")
        system = llm.requests[0]["system"]
        assert "Если фактов 40 — верни 30" in system
        assert "Добивать число выдуманными фактами нельзя" in system

    @pytest.mark.asyncio
    async def test_plan_larger_than_max_is_clamped(self):
        """Границы режут и сам ответ модели, а не только схему."""
        llm = _make_llm([json.dumps({
            "num_questions": 45,
            "topics": ["т"] * 45,
        })])
        plan = await plan_test(llm, digest="текст материала")
        assert plan.num_questions == MAX_QUESTIONS
        assert len(plan.topics) == MAX_QUESTIONS
