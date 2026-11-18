"""Тесты хранилища эталонов ответов (Redis) и LLM-судьи для вопросов с
вариантами ответа.

Зачем они нужны
===============
По контракту заказчика в ответе `create-test:ml-to-be` у вопроса НЕТ поля
`answer_key`, и в таблице `test_questions` backend'а такой колонки тоже нет.
Значит эталон правильного ответа ML обязан сохранить сам — в Redis — и потом
найти его при проверке попытки.

Ключ сопоставления — нормализованный текст вопроса: `question_id` в БД
генерирует backend, и на момент генерации теста ML его не знал.

Тесты детерминированные: Redis — заглушка, LLM — заглушка. Ни сети, ни БД.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.contracts import TestQuestion
from app.services.answer_store import (
    DEFAULT_TTL_SECONDS,
    KEY_PREFIX,
    AnswerStore,
    answer_key_for,
    normalize_question_text,
)
from app.services.choice_judge import (
    ChoiceJudge,
    ChoiceVerdict,
    parse_choice_verdict,
)


# ============================================================================
# Заглушки
# ============================================================================

class FakeRedis:
    """Redis-заглушка: словарь значений + записанные TTL."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int | None] = {}

    async def set(self, name: str, value: str, ex: int | None = None) -> bool:
        self.values[name] = value
        self.expirations[name] = ex
        return True

    async def get(self, name: str) -> str | None:
        return self.values.get(name)


class FakeLLM:
    """LLMClient-заглушка: отдаёт заранее заданный вердикт."""

    def __init__(self, verdict: dict | None = None, error: Exception | None = None):
        self.verdict = verdict
        self.error = error
        self.calls: list[dict] = []

    async def chat_json(self, user_message, *, validator, system_prompt=None,
                        max_retries=3, schema=None):
        self.calls.append({"user": user_message, "system": system_prompt, "schema": schema})
        if self.error:
            raise self.error
        return validator(self.verdict or {})


def single_question(qid: int = 1, text: str = "Что такое RAG?") -> TestQuestion:
    return TestQuestion(
        id=qid, text=text, type_question="single_choice",
        options=["A", "B"],
        answer_key={"correct_index": 1, "explanation": "потому что B"},
    )


# ============================================================================
# Нормализация текста
# ============================================================================

class TestNormalizeQuestionText:
    def test_trims_and_lowercases(self):
        assert normalize_question_text("  Что Такое RAG?  ") == "что такое rag?"

    def test_collapses_whitespace(self):
        assert normalize_question_text("Что\n\tтакое   RAG?") == "что такое rag?"

    def test_empty_text(self):
        assert normalize_question_text("") == ""
        assert normalize_question_text("   ") == ""

    def test_none_is_tolerated(self):
        assert normalize_question_text(None) == ""


# ============================================================================
# Ключ Redis
# ============================================================================

class TestAnswerKey:
    def test_key_prefix(self):
        assert answer_key_for("T1") == f"{KEY_PREFIX}T1"

    def test_key_is_namespaced(self):
        """Ключи эталонов не должны пересекаться с каналами задач."""
        assert answer_key_for("T1").startswith("ml:answers:")

    def test_dashed_and_hex_uuid_use_same_key(self):
        """Java присылает UUID с дефисами, другие клиенты — hex."""
        test_id = uuid.uuid4()
        assert answer_key_for(str(test_id)) == answer_key_for(test_id.hex)

    def test_non_uuid_id_is_unchanged(self):
        assert answer_key_for("T1") == f"{KEY_PREFIX}T1"


# ============================================================================
# Сохранение и чтение
# ============================================================================

class TestAnswerStore:
    @pytest.mark.asyncio
    async def test_save_returns_question_count(self):
        store = AnswerStore(FakeRedis())
        assert await store.save("T1", [single_question(1), single_question(2)]) == 2

    @pytest.mark.asyncio
    async def test_save_writes_expected_shape(self):
        redis = FakeRedis()
        store = AnswerStore(redis)
        await store.save("T1", [single_question(1)])
        payload = json.loads(redis.values["ml:answers:T1"])
        assert set(payload) == {"1"}
        ref = payload["1"]
        assert ref["type"] == "single_choice"
        assert ref["text"] == "Что такое RAG?"
        assert ref["options"] == ["A", "B"]
        assert ref["answer_key"]["correct_index"] == 1

    @pytest.mark.asyncio
    async def test_save_sets_ttl(self):
        redis = FakeRedis()
        store = AnswerStore(redis)
        await store.save("T1", [single_question(1)])
        assert redis.expirations["ml:answers:T1"] == DEFAULT_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_save_of_empty_list_writes_nothing(self):
        redis = FakeRedis()
        store = AnswerStore(redis)
        assert await store.save("T1", []) == 0
        assert redis.values == {}

    @pytest.mark.asyncio
    async def test_load_returns_saved_references(self):
        store = AnswerStore(FakeRedis())
        await store.save("T1", [single_question(1), single_question(2)])
        loaded = await store.load("T1")
        assert set(loaded) == {"1", "2"}
        assert loaded["2"]["answer_key"]["correct_index"] == 1

    @pytest.mark.asyncio
    async def test_load_of_missing_test_is_empty(self):
        store = AnswerStore(FakeRedis())
        assert await store.load("T1") == {}

    @pytest.mark.asyncio
    async def test_load_of_broken_json_is_empty(self):
        """Мусор в Redis не должен ронять проверку — просто эталона нет."""
        redis = FakeRedis()
        redis.values["ml:answers:T1"] = "{не json"
        store = AnswerStore(redis)
        assert await store.load("T1") == {}

    @pytest.mark.asyncio
    async def test_load_of_non_object_json_is_empty(self):
        redis = FakeRedis()
        redis.values["ml:answers:T1"] = "[1, 2, 3]"
        store = AnswerStore(redis)
        assert await store.load("T1") == {}

    @pytest.mark.asyncio
    async def test_save_overwrites_previous_references(self):
        """Тот же test_id перезаписывает эталоны: тест пересоздали."""
        store = AnswerStore(FakeRedis())
        await store.save("T1", [single_question(1), single_question(2)])
        await store.save("T1", [single_question(1, text="Другой вопрос?")])
        loaded = await store.load("T1")
        assert set(loaded) == {"1"}
        assert loaded["1"]["text"] == "Другой вопрос?"


# ============================================================================
# Поиск эталона по тексту вопроса
# ============================================================================

class TestFindByText:
    @pytest.mark.asyncio
    async def test_exact_match(self):
        store = AnswerStore(FakeRedis())
        await store.save("T1", [single_question(1)])
        found = await store.find_by_text("T1", "Что такое RAG?")
        assert found is not None
        assert found["answer_key"]["correct_index"] == 1

    @pytest.mark.asyncio
    async def test_match_ignores_case_and_whitespace(self):
        store = AnswerStore(FakeRedis())
        await store.save("T1", [single_question(1)])
        found = await store.find_by_text("T1", "  что   ТАКОЕ rag?  ")
        assert found is not None

    @pytest.mark.asyncio
    async def test_second_question_is_found_by_its_own_text(self):
        store = AnswerStore(FakeRedis())
        await store.save("T1", [
            single_question(1, text="Первый вопрос?"),
            single_question(2, text="Второй вопрос?"),
        ])
        found = await store.find_by_text("T1", "Второй вопрос?")
        assert found is not None
        assert found["text"] == "Второй вопрос?"

    @pytest.mark.asyncio
    async def test_uuid_representations_address_same_reference(self):
        """Эталон, сохранённый с дефисами, находится по hex-форме test_id."""
        test_id = uuid.uuid4()
        store = AnswerStore(FakeRedis())
        await store.save(str(test_id), [single_question(1)])
        found = await store.find_by_text(test_id.hex, "Что такое RAG?")
        assert found is not None
        assert found["answer_key"]["correct_index"] == 1

    @pytest.mark.asyncio
    async def test_unknown_text_returns_none(self):
        store = AnswerStore(FakeRedis())
        await store.save("T1", [single_question(1)])
        assert await store.find_by_text("T1", "Совсем другой вопрос?") is None

    @pytest.mark.asyncio
    async def test_empty_text_returns_none(self):
        store = AnswerStore(FakeRedis())
        await store.save("T1", [single_question(1)])
        assert await store.find_by_text("T1", "") is None

    @pytest.mark.asyncio
    async def test_other_test_is_not_searched(self):
        """Эталоны одного теста не подходят другому: ключ включает test_id."""
        store = AnswerStore(FakeRedis())
        await store.save("T1", [single_question(1)])
        assert await store.find_by_text("T2", "Что такое RAG?") is None


# ============================================================================
# parse_choice_verdict
# ============================================================================

class TestParseChoiceVerdict:
    def test_ok(self):
        v = parse_choice_verdict({"correct_indexes": [1], "explanation": "потому что B"}, 4)
        assert v.correct_indexes == [1]
        assert v.explanation == "потому что B"
        assert v.found is True

    def test_indexes_are_sorted_and_deduplicated(self):
        v = parse_choice_verdict({"correct_indexes": [2, 0, 2]}, 4)
        assert v.correct_indexes == [0, 2]

    def test_out_of_range_indexes_are_dropped(self):
        """Мусорный индекс не должен ломать проверку — он отбрасывается."""
        v = parse_choice_verdict({"correct_indexes": [0, 99]}, 4)
        assert v.correct_indexes == [0]

    def test_non_integer_indexes_are_dropped(self):
        v = parse_choice_verdict({"correct_indexes": [0, "abc", None]}, 4)
        assert v.correct_indexes == [0]

    def test_missing_indexes_raises(self):
        with pytest.raises(ValueError, match="correct_indexes"):
            parse_choice_verdict({"explanation": "x"}, 4)

    def test_indexes_not_a_list_raises(self):
        with pytest.raises(ValueError, match="correct_indexes"):
            parse_choice_verdict({"correct_indexes": 1}, 4)

    def test_empty_indexes_is_not_found(self):
        v = parse_choice_verdict({"correct_indexes": []}, 4)
        assert v.found is False


# ============================================================================
# ChoiceJudge
# ============================================================================

class TestChoiceJudge:
    @pytest.mark.asyncio
    async def test_verdict_passthrough(self):
        llm = FakeLLM(verdict={"correct_indexes": [1], "explanation": "потому что B"})
        judge = ChoiceJudge(llm=llm)
        verdict = await judge.judge(
            question="Что верно?", options=["A", "B"], question_type="single_choice",
        )
        assert verdict.correct_indexes == [1]
        assert verdict.explanation == "потому что B"

    @pytest.mark.asyncio
    async def test_empty_options_not_asked_from_llm(self):
        """Определять нечего — LLM не тратим."""
        llm = FakeLLM(verdict={"correct_indexes": [0]})
        judge = ChoiceJudge(llm=llm)
        verdict = await judge.judge(question="q", options=[])
        assert verdict.found is False
        assert llm.calls == []

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty_verdict(self):
        llm = FakeLLM(error=RuntimeError("LLM down"))
        judge = ChoiceJudge(llm=llm)
        verdict = await judge.judge(question="q", options=["A", "B"])
        assert verdict.found is False
        assert verdict.correct_indexes == []

    @pytest.mark.asyncio
    async def test_options_are_numbered_in_the_prompt(self):
        llm = FakeLLM(verdict={"correct_indexes": [0]})
        judge = ChoiceJudge(llm=llm)
        await judge.judge(question="q", options=["A", "B"])
        assert "0. A" in llm.calls[0]["user"]
        assert "1. B" in llm.calls[0]["user"]
