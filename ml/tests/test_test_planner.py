"""Тесты планировщика размера теста (services/test_planner.py).

Планировщик отвечает ДО генерации: сколько вопросов покрывает материал и на
какие темы. От его ответа зависят и размер теста, и жёсткая JSON Schema
генератора (minItems = maxItems = N), поэтому план должен быть валидным, а не
«примерно правильным».

Здесь мок не подменяет `chat_json` целиком — подменяется только сырой вызов
`_chat_once_raw`, чтобы проверить и retry из LLMClient, и схему, которая
уходит провайдеру.
"""

from __future__ import annotations

import json

import pytest

from app.contracts import MAX_QUESTIONS, MIN_QUESTIONS
from app.services.llm import LLMClient
from app.services.test_planner import PLAN_SCHEMA, TestPlan, plan_test


def _make_llm(responses) -> LLMClient:
    """LLMClient без сети: `_chat_once_raw` отдаёт заранее заданные ответы."""
    llm = LLMClient.__new__(LLMClient)
    llm._model = "fake"
    llm._client = None
    llm.requests = []  # type: ignore[attr-defined]
    it = iter(responses)

    async def fake_raw(system_prompt, user_message, *, fmt="plain", schema=None):
        llm.requests.append({
            "fmt": fmt, "schema": schema,
            "system": system_prompt, "user": user_message,
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
        plan = await plan_test(llm, digest="текст материала", difficulty="medium")
        assert plan.num_questions == 5
        assert plan.topics[0] == "тема 1"

    @pytest.mark.asyncio
    async def test_uses_json_schema(self):
        llm = _make_llm([json.dumps({"num_questions": 1, "topics": ["тема"]})])
        await plan_test(llm, digest="текст материала", difficulty="easy")
        assert llm.requests[0]["fmt"] == "json_schema"
        assert llm.requests[0]["schema"] == PLAN_SCHEMA

    @pytest.mark.asyncio
    async def test_schema_bounds_match_contract(self):
        assert PLAN_SCHEMA["properties"]["num_questions"]["minimum"] == MIN_QUESTIONS
        assert PLAN_SCHEMA["properties"]["num_questions"]["maximum"] == MAX_QUESTIONS

    @pytest.mark.asyncio
    async def test_digest_and_difficulty_go_to_llm(self):
        llm = _make_llm([json.dumps({"num_questions": 1, "topics": ["тема"]})])
        await plan_test(llm, digest="текст материала", difficulty="hard")
        request = llm.requests[0]
        assert "текст материала" in request["user"]
        assert "hard" in request["user"]
        assert "hard" in request["system"]

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
        plan = await plan_test(llm, digest="текст материала", difficulty="medium")
        assert plan.num_questions == 5
        assert len(llm.requests) == 2
        assert "предыдущий ответ был невалидным" in llm.requests[1]["system"]

    @pytest.mark.asyncio
    async def test_raises_after_retries(self):
        """Все ответы невалидны → RuntimeError, а не тест на 5 вопросов «на глаз»."""
        bad = json.dumps({"num_questions": 5, "topics": ["одна"]})
        llm = _make_llm([bad, bad, bad])
        with pytest.raises(RuntimeError, match="chat_json failed"):
            await plan_test(llm, digest="текст материала", difficulty="medium")

    @pytest.mark.asyncio
    async def test_planner_does_not_write_questions(self):
        """Планировщик не генерирует вопросы — только считает и называет темы."""
        llm = _make_llm([json.dumps({"num_questions": 2, "topics": ["тема 1", "тема 2"]})])
        await plan_test(llm, digest="текст материала", difficulty="medium")
        assert "НЕ писать вопросы" in llm.requests[0]["system"]
