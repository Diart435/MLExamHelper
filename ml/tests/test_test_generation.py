"""Тесты для генерации тестов: TestGenerator, process_create_test, LLMClient.chat_json.

Без реального OpenRouter — мокаем LLMClient. Цель — убедиться, что:
  - TestGenerator правильно собирает контекст и парсит ответ LLM
  - микс типов вопросов соответствует сложности (70/30/0, 40/30/30, 10/30/60)
  - количество вопросов укладывается в лимиты заказчика (1..30), а если не
    задано — его выбирает планировщик
  - process_create_test правильно валидирует вход и формирует result
  - chat_json retry'ит на битом JSON и валидирует через переданный callable
  - _extract_json_block корректно достаёт JSON из типичных LLM-обёрток
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import numpy as np
import pytest

from app.contracts import (
    MAX_QUESTIONS,
    MIN_QUESTIONS,
    CreateTestResult,
    CreateTestTask,
    Test,
    TestQuestion,
    parse_task,
)
from app.handlers.rag import process_create_test
from app.services.llm import LLMClient, _extract_json_block
from app.services.rag import RAGService
from app.services.test_generator import (
    MIX_SHARES,
    QUESTION_TYPE_ORDER,
    TestGenerator,
    _question_schema,
    _system_prompt,
    question_mix,
    spread_types,
)
from app.services.vector_store import InMemoryVectorStore


# ============================================================================
# _extract_json_block
# ============================================================================

class TestExtractJsonBlock:
    def test_plain_json(self):
        assert _extract_json_block('{"a": 1}') == '{"a": 1}'

    def test_json_with_preamble(self):
        s = "Вот ваш тест:\n\n{\"a\": 1}"
        assert _extract_json_block(s) == '{"a": 1}'

    def test_json_with_epilogue(self):
        s = "{\"a\": 1}\n\nГотово!"
        assert _extract_json_block(s) == '{"a": 1}'

    def test_json_in_code_fence(self):
        s = '```json\n{"a": 1, "b": [1,2]}\n```'
        assert _extract_json_block(s) == '{"a": 1, "b": [1,2]}'

    def test_json_in_code_fence_no_lang(self):
        s = '```\n{"a": 1}\n```'
        assert _extract_json_block(s) == '{"a": 1}'

    def test_no_json_passes_through(self):
        # Если JSON нет вообще — возвращаем as is, json.loads упадёт потом
        assert _extract_json_block("plain text") == "plain text"


# ============================================================================
# Микс типов вопросов и лимиты
# ============================================================================

# Таблица из спеки §5.2: (single_choice / multi_choice / open_answer).
MIX_TABLE: dict[str, dict[int, tuple[int, int, int]]] = {
    "easy": {
        1: (1, 0, 0), 2: (1, 1, 0), 3: (2, 1, 0),
        5: (3, 2, 0), 10: (7, 3, 0), 30: (21, 9, 0),
    },
    "medium": {
        1: (1, 0, 0), 2: (1, 0, 1), 3: (1, 1, 1),
        5: (2, 1, 2), 10: (4, 3, 3), 30: (12, 9, 9),
    },
    "hard": {
        1: (0, 0, 1), 2: (0, 1, 1), 3: (0, 1, 2),
        5: (0, 2, 3), 10: (1, 3, 6), 30: (3, 9, 18),
    },
}


class TestQuestionMix:
    @pytest.mark.parametrize("difficulty", sorted(MIX_TABLE))
    @pytest.mark.parametrize("n", [1, 2, 3, 5, 10, 30])
    def test_mix_matches_spec_table(self, n, difficulty):
        single, multi, open_ = MIX_TABLE[difficulty][n]
        assert question_mix(n, difficulty) == {
            "single_choice": single,
            "multi_choice": multi,
            "open_answer": open_,
        }

    @pytest.mark.parametrize("difficulty", sorted(MIX_SHARES))
    @pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 11, 17, 23, 30])
    def test_mix_always_sums_to_n(self, n, difficulty):
        counts = question_mix(n, difficulty)
        assert sum(counts.values()) == n
        assert all(v >= 0 for v in counts.values())

    @pytest.mark.parametrize("difficulty", sorted(MIX_SHARES))
    @pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 11, 17, 23, 30])
    def test_dominant_type_always_present(self, n, difficulty):
        """Тип с наибольшей долей есть в тесте всегда — даже при N=1."""
        counts = question_mix(n, difficulty)
        dominant = max(QUESTION_TYPE_ORDER, key=lambda t: MIX_SHARES[difficulty][t])
        assert counts[dominant] >= 1

    def test_easy_has_no_open_questions(self):
        assert question_mix(20, "easy") == {
            "single_choice": 14, "multi_choice": 6, "open_answer": 0,
        }

    def test_medium_mix(self):
        assert question_mix(10, "medium") == {
            "single_choice": 4, "multi_choice": 3, "open_answer": 3,
        }

    def test_hard_mix(self):
        assert question_mix(10, "hard") == {
            "single_choice": 1, "multi_choice": 3, "open_answer": 6,
        }

    def test_unknown_difficulty_raises(self):
        with pytest.raises(ValueError, match="unknown difficulty"):
            question_mix(10, "impossible")

    def test_zero_questions_raises(self):
        with pytest.raises(ValueError, match="num_questions"):
            question_mix(0, "easy")


class TestSpreadTypes:
    def test_matches_spec_example_for_hard(self):
        """Эталон из спеки §5.3 — 1 single, 3 multi, 6 open."""
        counts = question_mix(10, "hard")
        assert spread_types(counts) == [
            "open_answer", "multi_choice", "open_answer", "open_answer",
            "multi_choice", "open_answer", "open_answer", "single_choice",
            "multi_choice", "open_answer",
        ]

    @pytest.mark.parametrize("difficulty", sorted(MIX_SHARES))
    @pytest.mark.parametrize("n", [1, 2, 3, 5, 10, 30])
    def test_length_and_counts_match_mix(self, n, difficulty):
        counts = question_mix(n, difficulty)
        order = spread_types(counts)
        assert len(order) == n
        for t in QUESTION_TYPE_ORDER:
            assert order.count(t) == counts[t]

    @pytest.mark.parametrize("difficulty", sorted(MIX_SHARES))
    @pytest.mark.parametrize("n", [2, 3, 5, 10, 30])
    def test_types_are_not_one_block(self, n, difficulty):
        """Типы не идут блоком: ни одна серия подряд не длиннее потолка Д'Хондта."""
        counts = question_mix(n, difficulty)
        order = spread_types(counts)
        for t in QUESTION_TYPE_ORDER:
            share = MIX_SHARES[difficulty][t]
            if share == 0:
                continue
            limit = max(1, -(-n * share // 1))  # ceil(n * share)
            longest = 0
            run = 0
            for item in order:
                run = run + 1 if item == t else 0
                longest = max(longest, run)
            assert longest <= limit, f"{t}: серия {longest} длиннее потолка {limit}"

    def test_spread_is_deterministic(self):
        counts = question_mix(10, "medium")
        assert spread_types(counts) == spread_types(counts)


# ============================================================================
# JSON Schema ответа LLM
# ============================================================================

# Метки блоков, которые попали в контекст генерации.
CHUNK_REFS = ["C1", "C2", "C3"]


class TestQuestionSchema:
    def test_question_count_is_fixed(self):
        schema = _question_schema(10, {"single_choice": 4, "multi_choice": 3, "open_answer": 3}, CHUNK_REFS)
        questions = schema["properties"]["questions"]
        assert questions["minItems"] == 10
        assert questions["maxItems"] == 10

    def test_single_type_has_no_anyof(self):
        """Один тип в тесте — одна ветка схемы, other-типы невозможны структурно."""
        schema = _question_schema(1, {"single_choice": 1, "multi_choice": 0, "open_answer": 0}, CHUNK_REFS)
        item = schema["properties"]["questions"]["items"]
        assert "anyOf" not in item
        assert item["properties"]["type_question"]["enum"] == ["single_choice"]

    def test_all_three_branches_present(self):
        schema = _question_schema(10, {"single_choice": 1, "multi_choice": 3, "open_answer": 6}, CHUNK_REFS)
        branches = schema["properties"]["questions"]["items"]["anyOf"]
        assert len(branches) == 3
        by_type = {b["properties"]["type_question"]["enum"][0]: b for b in branches}
        assert set(by_type) == {"single_choice", "multi_choice", "open_answer"}

    def test_single_choice_requires_correct_index(self):
        schema = _question_schema(10, {"single_choice": 1, "multi_choice": 3, "open_answer": 6}, CHUNK_REFS)
        branches = schema["properties"]["questions"]["items"]["anyOf"]
        by_type = {b["properties"]["type_question"]["enum"][0]: b for b in branches}
        assert "correct_index" in by_type["single_choice"]["properties"]["answer_key"]["required"]

    def test_multi_choice_requires_correct_indexes(self):
        schema = _question_schema(10, {"single_choice": 1, "multi_choice": 3, "open_answer": 6}, CHUNK_REFS)
        branches = schema["properties"]["questions"]["items"]["anyOf"]
        by_type = {b["properties"]["type_question"]["enum"][0]: b for b in branches}
        multi = by_type["multi_choice"]
        assert "correct_indexes" in multi["properties"]["answer_key"]["required"]
        indexes = multi["properties"]["answer_key"]["properties"]["correct_indexes"]
        assert indexes["minItems"] == 2
        assert indexes["maxItems"] == 3

    def test_multi_choice_has_more_options_than_single(self):
        schema = _question_schema(10, {"single_choice": 1, "multi_choice": 3, "open_answer": 6}, CHUNK_REFS)
        branches = schema["properties"]["questions"]["items"]["anyOf"]
        by_type = {b["properties"]["type_question"]["enum"][0]: b for b in branches}
        assert by_type["multi_choice"]["properties"]["options"]["minItems"] == 4
        assert by_type["single_choice"]["properties"]["options"]["maxItems"] == 4

    def test_open_answer_requires_reference_and_criteria(self):
        schema = _question_schema(10, {"single_choice": 1, "multi_choice": 3, "open_answer": 6}, CHUNK_REFS)
        branches = schema["properties"]["questions"]["items"]["anyOf"]
        by_type = {b["properties"]["type_question"]["enum"][0]: b for b in branches}
        open_ = by_type["open_answer"]
        assert "reference_answer" in open_["properties"]["answer_key"]["required"]
        # key_points — массив критериев: 2-4 штуки.
        assert open_["properties"]["key_points"]["minItems"] == 2
        assert open_["properties"]["key_points"]["maxItems"] == 4

    def test_closed_types_have_empty_key_points(self):
        """У single_choice/multi_choice опорных пунктов нет — key_points пустой."""
        schema = _question_schema(10, {"single_choice": 1, "multi_choice": 3, "open_answer": 6}, CHUNK_REFS)
        branches = schema["properties"]["questions"]["items"]["anyOf"]
        by_type = {b["properties"]["type_question"]["enum"][0]: b for b in branches}
        for t in ("single_choice", "multi_choice"):
            assert by_type[t]["properties"]["key_points"]["maxItems"] == 0

    def test_explanation_required_for_every_type(self):
        schema = _question_schema(10, {"single_choice": 1, "multi_choice": 3, "open_answer": 6}, CHUNK_REFS)
        branches = schema["properties"]["questions"]["items"]["anyOf"]
        for b in branches:
            assert "explanation" in b["properties"]["answer_key"]["required"]

    def test_source_chunk_ref_limited_to_real_labels(self):
        """Модель может сослаться только на реально попавший в контекст блок."""
        schema = _question_schema(10, {"single_choice": 1, "multi_choice": 3, "open_answer": 6}, CHUNK_REFS)
        branches = schema["properties"]["questions"]["items"]["anyOf"]
        for b in branches:
            ref = b["properties"]["source_chunk_ref"]
            assert ref["enum"] == list(CHUNK_REFS)
            assert "source_chunk_ref" in b["required"]

    def test_source_chunk_ref_cannot_be_null(self):
        """null в enum'е — лазейка: модель писала null во все вопросы подряд,
        и привязка к источнику терялась целиком."""
        schema = _question_schema(10, {"single_choice": 1, "multi_choice": 3, "open_answer": 6}, CHUNK_REFS)
        branches = schema["properties"]["questions"]["items"]["anyOf"]
        for b in branches:
            ref = b["properties"]["source_chunk_ref"]
            assert None not in ref["enum"]
            assert ref["type"] == "string"

    def test_open_answer_options_must_be_empty(self):
        schema = _question_schema(10, {"single_choice": 1, "multi_choice": 3, "open_answer": 6}, CHUNK_REFS)
        branches = schema["properties"]["questions"]["items"]["anyOf"]
        by_type = {b["properties"]["type_question"]["enum"][0]: b for b in branches}
        assert by_type["open_answer"]["properties"]["options"]["maxItems"] == 0


class TestSystemPrompt:
    def test_prompt_lists_plan_for_every_question(self):
        counts = question_mix(10, "hard")
        types = spread_types(counts)
        prompt = _system_prompt(10, "hard", types, None)
        for i, qtype in enumerate(types, start=1):
            assert f"{i}. [{qtype}]" in prompt

    def test_prompt_contains_topics_when_plan_given(self):
        counts = question_mix(3, "medium")
        types = spread_types(counts)
        topics = ["тема раз", "тема два", "тема три"]
        prompt = _system_prompt(3, "medium", types, topics)
        for topic in topics:
            assert topic in prompt

    def test_prompt_explains_each_type(self):
        prompt = _system_prompt(10, "medium", spread_types(question_mix(10, "medium")), None)
        assert "correct_index" in prompt
        assert "correct_indexes" in prompt
        assert "reference_answer" in prompt

    def test_prompt_has_no_contradiction_about_key_points(self):
        # Раньше правило 2 требовало key_points.criteria, а правило 3 описывало
        # key_points как {points, explanation} — модель разрешала противоречие
        # двумя объектами key_points в одном вопросе. Сейчас key_points — один
        # массив строк, а объяснение живёт в answer_key.
        prompt = _system_prompt(10, "hard", spread_types(question_mix(10, "hard")), None)
        assert "key_points.criteria" not in prompt
        assert "answer_key.explanation" in prompt
        assert prompt.count("key_points —") == 1

    def test_prompt_explains_source_chunk_ref(self):
        prompt = _system_prompt(10, "hard", spread_types(question_mix(10, "hard")), None)
        assert "source_chunk_ref" in prompt


class TestCreateTestTaskLimits:
    def test_min_questions_ok(self):
        task = CreateTestTask(
            task_id="t", test_id="T", material_ids=["1"], title="X",
            num_questions=MIN_QUESTIONS,
        )
        assert task.num_questions == MIN_QUESTIONS

    def test_max_questions_ok(self):
        task = CreateTestTask(
            task_id="t", test_id="T", material_ids=["1"], title="X",
            num_questions=MAX_QUESTIONS,
        )
        assert task.num_questions == MAX_QUESTIONS

    def test_none_means_ml_decides(self):
        task = CreateTestTask(
            task_id="t", test_id="T", material_ids=["1"], title="X",
            num_questions=None,
        )
        assert task.num_questions is None

    @pytest.mark.parametrize("n", [0, -1, 31, 100])
    def test_out_of_range_raises(self, n):
        with pytest.raises(ValueError, match="num_questions"):
            CreateTestTask(
                task_id="t", test_id="T", material_ids=["1"], title="X",
                num_questions=n,
            )

    def test_invalid_difficulty_raises(self):
        with pytest.raises(ValueError, match="difficulty"):
            CreateTestTask(
                task_id="t", test_id="T", material_ids=["1"], title="X",
                num_questions=10, difficulty="impossible",
            )


# ============================================================================
# TestGenerator — с мок-LLM
# ============================================================================

def llm_response(single: int, multi: int = 0, open_: int = 0, chunk_ref: str = "C1") -> str:
    """Валидный ответ LLM с нужным количеством вопросов каждого типа."""
    questions: list[dict] = []
    qid = 1
    for _ in range(single):
        questions.append({
            "id": qid, "type_question": "single_choice",
            "options": ["A", "B", "C", "D"], "text": f"Вопрос {qid}?",
            "answer_key": {"correct_index": 0, "explanation": "потому что A"},
            "key_points": [],
            "source_chunk_ref": chunk_ref,
        })
        qid += 1
    for _ in range(multi):
        questions.append({
            "id": qid, "type_question": "multi_choice",
            "options": ["A", "B", "C", "D", "E", "F"], "text": f"Вопрос {qid}?",
            "answer_key": {"correct_indexes": [0, 2], "explanation": "потому что A и C"},
            "key_points": [],
            "source_chunk_ref": chunk_ref,
        })
        qid += 1
    for _ in range(open_):
        questions.append({
            "id": qid, "type_question": "open_answer", "options": [],
            "text": f"Открытый вопрос {qid}?",
            "answer_key": {
                "reference_answer": "Эталонный ответ",
                "explanation": "пояснение",
            },
            "key_points": ["пункт 1", "пункт 2"],
            "source_chunk_ref": chunk_ref,
        })
        qid += 1
    return json.dumps({"title": "Тест по лекции", "questions": questions}, ensure_ascii=False)


def planner_response(num_questions: int) -> str:
    """Валидный ответ планировщика: N вопросов и N тем."""
    return json.dumps(
        {
            "num_questions": num_questions,
            "topics": [f"тема {i + 1}" for i in range(num_questions)],
        },
        ensure_ascii=False,
    )


class _StubEmbeddings:
    """Заглушка эмбеддингов: тесты не векторизуют, но RAGService требует клиент.

    Без неё RAGService поднимает настоящий AsyncOpenAI — а он на машине с
    socks4-прокси в переменных окружения падает ещё на конструкторе.
    """

    async def embed(self, text: str) -> list[float]:
        return [0.0] * 8

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


class _StubLLM:
    """Заглушка LLM: тесты генерируют ответы через подставной chat_json."""


def _make_rag_with_chunks(material_ids: list[int], chunks_per_material: int = 3) -> RAGService:
    """RAGService с InMemoryVectorStore, где для каждого material_id лежат чанки.

    Подсовываем явный InMemoryVectorStore через DI — RAGService() по умолчанию
    читает VECTOR_STORE_BACKEND из env и может подсунуть PgVectorStore.
    """
    store = InMemoryVectorStore()
    rag = RAGService(store=store, embeddings=_StubEmbeddings(), llm=_StubLLM())
    for mid in material_ids:
        for i in range(chunks_per_material):
            cid = f"{mid}:{uuid.uuid4().hex[:8]}"
            vec = np.random.rand(8).astype(np.float32)
            store._chunks[cid] = (f"текст чанка {i} для материала {mid}", vec, str(mid))
    return rag


def _make_fake_llm(responses: list[str]) -> LLMClient:
    """LLMClient.chat_json, который по очереди отдаёт responses.

    Каждый вызов — следующий элемент. Если кончились — кидает.
    """
    llm = LLMClient.__new__(LLMClient)
    llm._model = "fake"
    llm._client = MagicMock()
    iter_resp = iter(responses)
    llm.calls = []  # type: ignore[attr-defined]

    async def fake_chat_json(user_message, *, validator, system_prompt=None, max_retries=3, schema=None):
        llm.calls.append({"user": user_message, "system": system_prompt, "schema": schema})
        try:
            content = next(iter_resp)
        except StopIteration:
            raise RuntimeError("fake llm: out of responses")
        data = json.loads(content)
        return validator(data)

    llm.chat_json = fake_chat_json  # type: ignore[method-assign]
    return llm


def _chunk_ids(rag: RAGService, mid: int) -> list[str]:
    """Chunk'ы материала в том же порядке, в каком их отдаёт store."""
    store = rag._store
    return sorted(cid for cid, (_t, _v, m) in store._chunks.items() if m == str(mid))


class TestTestGenerator:
    @pytest.mark.asyncio
    async def test_generate_with_mocked_llm(self):
        rag = _make_rag_with_chunks([101, 202], chunks_per_material=4)
        llm = _make_fake_llm([llm_response(3, 2)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1",
            material_ids=[101, 202], title="Quiz", num_questions=5,
            difficulty="easy",
        )
        test = await gen.generate(task)
        assert isinstance(test, Test)
        assert test.title == "Тест по лекции"
        assert len(test.questions) == 5
        assert test.questions[0].answer_key["correct_index"] == 0
        assert test.questions[0].answer_key["explanation"] == "потому что A"
        assert test.questions[0].key_points == []
        assert sum(1 for q in test.questions if q.type_question == "single_choice") == 3
        assert sum(1 for q in test.questions if q.type_question == "multi_choice") == 2

    @pytest.mark.asyncio
    async def test_generate_medium_mix(self):
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([llm_response(4, 3, 3)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=10, difficulty="medium",
        )
        test = await gen.generate(task)
        assert len(test.questions) == 10
        assert sum(1 for q in test.questions if q.type_question == "open_answer") == 3
        assert sum(1 for q in test.questions if q.type_question == "multi_choice") == 3

    @pytest.mark.asyncio
    async def test_generate_hard_mix(self):
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([llm_response(1, 3, 6)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=10, difficulty="hard",
        )
        test = await gen.generate(task)
        assert sum(1 for q in test.questions if q.type_question == "open_answer") == 6
        assert sum(1 for q in test.questions if q.type_question == "multi_choice") == 3
        assert sum(1 for q in test.questions if q.type_question == "single_choice") == 1

    @pytest.mark.asyncio
    async def test_multi_choice_keeps_correct_indexes(self):
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([llm_response(1, 3, 6)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=10, difficulty="hard",
        )
        test = await gen.generate(task)
        multi = next(q for q in test.questions if q.type_question == "multi_choice")
        assert multi.correct_indexes() == [0, 2]
        assert multi.options == ["A", "B", "C", "D", "E", "F"]

    @pytest.mark.asyncio
    async def test_open_question_keeps_reference_answer(self):
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([llm_response(1, 3, 6)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=10, difficulty="hard",
        )
        test = await gen.generate(task)
        open_q = next(q for q in test.questions if q.type_question == "open_answer")
        assert open_q.reference_answer() == "Эталонный ответ"
        assert open_q.criteria() == ["пункт 1", "пункт 2"]
        assert open_q.options == []

    @pytest.mark.asyncio
    async def test_prompt_lists_question_types(self):
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([llm_response(4, 3, 3)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=10, difficulty="medium",
        )
        await gen.generate(task)
        system = llm.calls[0]["system"]
        for i, qtype in enumerate(spread_types(question_mix(10, "medium")), start=1):
            assert f"{i}. [{qtype}]" in system

    @pytest.mark.asyncio
    async def test_generator_passes_json_schema_to_llm(self):
        """Схема уходит в LLM: без неё модель отдаёт мусорный JSON."""
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([llm_response(4, 3, 3)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=10, difficulty="medium",
        )
        await gen.generate(task)
        schema = llm.calls[0]["schema"]
        assert schema is not None
        assert schema["properties"]["questions"]["minItems"] == 10
        assert len(schema["properties"]["questions"]["items"]["anyOf"]) == 3

    @pytest.mark.asyncio
    async def test_wrong_mix_triggers_regeneration(self):
        """Первый ответ с неверным миксом → вторая попытка с уточнением."""
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([llm_response(10, 0, 0), llm_response(4, 3, 3)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=10, difficulty="medium",
        )
        test = await gen.generate(task)
        assert len(test.questions) == 10
        assert len(llm.calls) == 2
        assert "ВНИМАНИЕ" in llm.calls[1]["user"]

    @pytest.mark.asyncio
    async def test_persistent_wrong_mix_raises(self):
        """Две попытки с неверным миксом → ValueError, а не тихий all-single_choice."""
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([llm_response(10, 0, 0), llm_response(10, 0, 0)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=10, difficulty="medium",
        )
        with pytest.raises(ValueError, match="question-type mix"):
            await gen.generate(task)

    @pytest.mark.asyncio
    async def test_generate_raises_if_material_not_indexed(self):
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([llm_response(3, 2)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1",
            material_ids=[101, 999], title="Quiz", num_questions=5,
        )
        with pytest.raises(ValueError, match="not indexed"):
            await gen.generate(task)

    @pytest.mark.asyncio
    async def test_auto_mode_calls_planner_first(self):
        """num_questions не задан → первым идёт планировщик, вторым генератор."""
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([planner_response(6), llm_response(2, 2, 2)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=None, difficulty="medium",
        )
        test = await gen.generate(task)
        assert len(test.questions) == 6
        assert len(llm.calls) == 2
        # Первый вызов — планировщик: его схема про num_questions/topics.
        planner_schema = llm.calls[0]["schema"]
        assert planner_schema is not None
        assert "num_questions" in planner_schema["properties"]
        # Второй вызов — генератор: у него questions.
        generator_schema = llm.calls[1]["schema"]
        assert generator_schema is not None
        assert "questions" in generator_schema["properties"]

    @pytest.mark.asyncio
    async def test_auto_mode_passes_topics_into_prompt(self):
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([planner_response(3), llm_response(1, 1, 1)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=None, difficulty="medium",
        )
        await gen.generate(task)
        system = llm.calls[1]["system"]
        assert "тема 1" in system
        assert "тема 3" in system

    @pytest.mark.asyncio
    async def test_auto_mode_size_comes_from_planner(self):
        """Число вопросов в тесте = то, что решил планировщик."""
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([planner_response(9), llm_response(3, 3, 3)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=None, difficulty="medium",
        )
        test = await gen.generate(task)
        assert len(test.questions) == 9


# ============================================================================
# Привязка вопроса к источнику (source_chunk_id)
# ============================================================================

class TestSourceChunkBinding:
    @pytest.mark.asyncio
    async def test_chunk_ref_is_mapped_to_chunk_id(self):
        """Метка блока от LLM разворачивается в UUID чанка."""
        rag = _make_rag_with_chunks([101], chunks_per_material=3)
        llm = _make_fake_llm([llm_response(2, 1, 0, chunk_ref="C2")])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=3, difficulty="easy",
        )
        test = await gen.generate(task)
        expected = str(uuid.uuid5(uuid.NAMESPACE_URL, _chunk_ids(rag, 101)[1]))
        assert all(q.source_chunk_id == expected for q in test.questions)

    @pytest.mark.asyncio
    async def test_unknown_chunk_ref_leaves_source_empty(self):
        """Метка не из нашего списка → вопрос без привязки, а не привязка к чужому."""
        rag = _make_rag_with_chunks([101], chunks_per_material=3)
        llm = _make_fake_llm([llm_response(2, 1, 0, chunk_ref="C999")])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=3, difficulty="easy",
        )
        test = await gen.generate(task)
        assert all(q.source_chunk_id is None for q in test.questions)

    @pytest.mark.asyncio
    async def test_digest_marks_every_chunk(self):
        """Каждый чанк в контексте помечен меткой — по ней LLM выбирает источник."""
        rag = _make_rag_with_chunks([101, 202], chunks_per_material=2)
        llm = _make_fake_llm([llm_response(3, 2)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101, 202], title="Quiz",
            num_questions=5, difficulty="easy",
        )
        await gen.generate(task)
        digest = llm.calls[0]["user"]
        for ref in ("C1", "C2", "C3", "C4"):
            assert f"[{ref}]" in digest

    @pytest.mark.asyncio
    async def test_schema_offers_only_real_refs(self):
        """В enum схемы попадают только метки блоков из контекста."""
        rag = _make_rag_with_chunks([101], chunks_per_material=2)
        llm = _make_fake_llm([llm_response(3, 2)])
        gen = TestGenerator(rag=rag, llm=llm)

        task = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=[101], title="Quiz",
            num_questions=5, difficulty="easy",
        )
        await gen.generate(task)
        schema = llm.calls[0]["schema"]
        branch = schema["properties"]["questions"]["items"]["anyOf"][0]
        assert branch["properties"]["source_chunk_ref"]["enum"] == ["C1", "C2"]


# ============================================================================
# process_create_test — handler
# ============================================================================

class TestProcessCreateTest:
    @pytest.mark.asyncio
    async def test_ok(self):
        rag = _make_rag_with_chunks([101])
        # Контракт v4.1: числа вопросов в задаче нет — размер выбирает
        # планировщик, поэтому первым идёт ответ планировщика (10 вопросов),
        # вторым — генератор (микс medium = 4/3/3).
        llm = _make_fake_llm([planner_response(10), llm_response(4, 3, 3)])
        gen = TestGenerator(rag=rag, llm=llm)
        task_dict = {
            "task_id": "t1", "test_id": "T1",
            "material_ids": [101], "title": "Quiz",
            "difficulty": "medium",
        }
        result = await process_create_test(task_dict, rag, generator=gen)
        assert result["status"] == "ok"
        assert result["task_id"] == "t1"
        assert "type" not in result
        assert "test" in result
        assert len(result["test"]["questions"]) == 10

    @pytest.mark.asyncio
    async def test_auto_mode_reports_actual_count(self):
        """ML сам выбрал размер — backend узнаёт фактическое число по массиву вопросов.

        Контракт v4.1: числа вопросов в задаче нет вовсе, размер всегда
        выбирает планировщик."""
        rag = _make_rag_with_chunks([101])
        llm = _make_fake_llm([planner_response(6), llm_response(2, 2, 2)])
        gen = TestGenerator(rag=rag, llm=llm)
        task_dict = {
            "task_id": "t1", "test_id": "T1",
            "material_ids": [101], "title": "Quiz",
            "difficulty": "medium",
        }
        result = await process_create_test(task_dict, rag, generator=gen)
        assert result["status"] == "ok"
        assert len(result["test"]["questions"]) == 6

    @pytest.mark.asyncio
    async def test_invalid_payload_returns_error(self):
        rag = _make_rag_with_chunks([101])
        bad = {"task_id": "t1"}  # без material_ids, title
        result = await process_create_test(bad, rag)
        assert result["status"] == "error"
        assert "invalid" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_legacy_amount_questions_is_ignored(self):
        """Старый payload с `amountQuestions: 31` не должен ронять задачу:
        числа вопросов в контракте больше нет (v4.1), размер выбирает ML."""
        rag = _make_rag_with_chunks([101])
        task_dict = {
            "task_id": "t1", "test_id": "T1",
            "material_ids": [101], "title": "Quiz", "amountQuestions": 31,
        }
        llm = _make_fake_llm([planner_response(4), llm_response(2, 1, 1)])
        gen = TestGenerator(rag=rag, llm=llm)
        result = await process_create_test(task_dict, rag, generator=gen)
        assert result["status"] == "ok"
        assert len(result["test"]["questions"]) == 4

    @pytest.mark.asyncio
    async def test_llm_failure_returns_error(self):
        rag = _make_rag_with_chunks([101])
        # LLM, который всегда падает
        llm = LLMClient.__new__(LLMClient)
        llm._model = "fake"
        llm._client = MagicMock()

        async def boom(*args, **kwargs):
            raise RuntimeError("LLM down")
        llm.chat_json = boom  # type: ignore[method-assign]
        gen = TestGenerator(rag=rag, llm=llm)

        task_dict = {
            "task_id": "t1", "test_id": "T1",
            "material_ids": [101], "title": "Quiz", "num_questions": 5,
        }
        result = await process_create_test(task_dict, rag, generator=gen)
        assert result["status"] == "error"
        assert "LLM down" in result["error"]
        assert result["test_id"] == "T1"


# ============================================================================
# parse_task для create_test
# ============================================================================

class TestParseCreateTest:
    def test_roundtrip(self):
        original = CreateTestTask(
            task_id="t1", test_id="T1", material_ids=["1", "2", "3"],
            title="Quiz", difficulty="hard",
        )
        parsed = parse_task(original.to_json(), "create_test")
        assert isinstance(parsed, CreateTestTask)
        assert parsed.material_ids == ["1", "2", "3"]
        assert parsed.difficulty == "hard"
        assert parsed.num_questions is None

    def test_missing_num_questions_means_auto(self):
        parsed = CreateTestTask.from_dict({
            "task_id": "t1", "test_id": "T1", "title": "X", "material_ids": ["1"],
        })
        assert parsed.num_questions is None

    def test_amount_questions_is_ignored(self):
        """Контракт v4.1: `amountQuestions` из payload'а НЕ читается — числа
        вопросов в контракте больше нет, размер выбирает ML."""
        parsed = CreateTestTask.from_dict({
            "task_id": "t1", "test_id": "T1", "title": "X", "material_ids": ["1"],
            "amountQuestions": 12,
        })
        assert parsed.num_questions is None

    def test_min_sentinel_means_auto(self):
        parsed = CreateTestTask.from_dict({
            "task_id": "t1", "test_id": "T1", "title": "X", "material_ids": ["1"],
            "amountQuestions": "min",
        })
        assert parsed.num_questions is None

    def test_legacy_num_questions_is_ignored(self):
        """В Redis Streams остались payload'ы прежнего формата — читаем их
        без падения, но число вопросов не применяем (v4.1)."""
        parsed = CreateTestTask.from_dict({
            "task_id": "t1", "test_id": "T1", "title": "X", "material_ids": ["1"],
            "num_questions": 7,
        })
        assert parsed.num_questions is None

    def test_explicit_null_means_auto(self):
        parsed = CreateTestTask.from_dict({
            "task_id": "t1", "test_id": "T1", "title": "X", "material_ids": ["1"],
            "num_questions": None,
        })
        assert parsed.num_questions is None

    def test_missing_material_ids_raises(self):
        with pytest.raises(ValueError):
            CreateTestTask.from_dict({
                "task_id": "t1", "test_id": "T1", "title": "X",
                "num_questions": 5,
            })

    def test_empty_material_ids_raises(self):
        with pytest.raises(ValueError):
            CreateTestTask.from_dict({
                "task_id": "t1", "test_id": "T1", "title": "X",
                "material_ids": [], "num_questions": 5,
            })


# ============================================================================
# TestQuestion — нормализация ответа LLM
# ============================================================================

class TestTestQuestionNormalisation:
    def test_key_points_is_flat_list(self):
        """Каноническая форма: key_points — список опорных пунктов."""
        q = TestQuestion.from_dict({
            "id": 1, "type_question": "open_answer", "options": [],
            "text": "Опишите RAG",
            "answer_key": {"reference_answer": "Эталон", "explanation": "пояснение"},
            "key_points": ["пункт 1", "пункт 2"],
        })
        assert q.criteria() == ["пункт 1", "пункт 2"]
        assert q.explanation() == "пояснение"
        assert q.to_dict()["key_points"] == ["пункт 1", "пункт 2"]

    def test_criteria_from_answer_key_moved_to_key_points(self):
        """LLM часто кладёт criteria в answer_key — судья читает key_points."""
        q = TestQuestion.from_dict({
            "id": 1, "type_question": "open_answer", "options": [],
            "text": "Опишите RAG",
            "answer_key": {
                "reference_answer": "Эталон",
                "criteria": ["пункт 1", "пункт 2"],
            },
            "key_points": [],
        })
        assert q.criteria() == ["пункт 1", "пункт 2"]
        assert "criteria" not in q.answer_key
        assert q.reference_answer() == "Эталон"

    def test_legacy_key_points_object_is_accepted(self):
        """Старая форма {points, explanation, criteria} ещё может прийти из Redis."""
        q = TestQuestion.from_dict({
            "id": 1, "type_question": "open_answer", "options": [],
            "text": "Опишите RAG",
            "answer_key": {"reference_answer": "Эталон"},
            "key_points": {"points": 2, "explanation": "пояснение", "criteria": ["пункт 1"]},
        })
        assert q.criteria() == ["пункт 1"]
        assert q.explanation() == "пояснение"

    def test_normalised_question_serialises_with_criteria_in_key_points(self):
        q = TestQuestion.from_dict({
            "id": 1, "type_question": "open_answer", "options": [],
            "text": "Опишите RAG",
            "answer_key": {"reference_answer": "Эталон", "criteria": ["пункт 1"]},
            "key_points": [],
        })
        dumped = q.to_dict()
        assert dumped["key_points"] == ["пункт 1"]
        # Контракт v4.1: эталон наружу ВЫХОДИТ — но без `criteria`: criteria
        # живёт только в key_points.
        assert dumped["answer_key"] == {"reference_answer": "Эталон"}

    def test_source_chunk_id_is_kept_and_ref_is_not_published(self):
        """Метка блока — внутренняя, наружу уходит UUID чанка."""
        q = TestQuestion.from_dict({
            "id": 1, "type_question": "single_choice",
            "options": ["A", "B"], "text": "Что верно?",
            "answer_key": {"correct_index": 0},
            "key_points": [],
            "source_chunk_ref": "C7",
            "source_chunk_id": "11111111-2222-3333-4444-555555555555",
        })
        dumped = q.to_dict()
        assert dumped["source_chunk_id"] == "11111111-2222-3333-4444-555555555555"
        assert "source_chunk_ref" not in dumped

    def test_multi_choice_indexes_sorted(self):
        q = TestQuestion.from_dict({
            "id": 1, "type_question": "multi_choice",
            "options": ["A", "B", "C", "D"],
            "text": "Что верно?",
            "answer_key": {"correct_indexes": [2, 0], "explanation": "пояснение"},
            "key_points": [],
        })
        assert q.correct_indexes() == [0, 2]
        assert q.answer_key["correct_indexes"] == [0, 2]

    def test_multi_choice_needs_at_least_two_indexes(self):
        with pytest.raises(ValueError, match="correct indexes"):
            TestQuestion.from_dict({
                "id": 1, "type_question": "multi_choice",
                "options": ["A", "B", "C", "D"],
                "text": "Что верно?",
                "answer_key": {"correct_indexes": [1]},
                "key_points": [],
            })

    def test_multi_choice_rejects_duplicates(self):
        with pytest.raises(ValueError, match="duplicates"):
            TestQuestion.from_dict({
                "id": 1, "type_question": "multi_choice",
                "options": ["A", "B", "C", "D"],
                "text": "Что верно?",
                "answer_key": {"correct_indexes": [1, 1]},
                "key_points": [],
            })

    def test_multi_choice_rejects_index_out_of_range(self):
        with pytest.raises(ValueError, match="out of range"):
            TestQuestion.from_dict({
                "id": 1, "type_question": "multi_choice",
                "options": ["A", "B"],
                "text": "Что верно?",
                "answer_key": {"correct_indexes": [0, 5]},
                "key_points": [],
            })

    def test_multi_choice_without_answer_key_raises(self):
        with pytest.raises(ValueError, match="correct_indexes"):
            TestQuestion.from_dict({
                "id": 1, "type_question": "multi_choice",
                "options": ["A", "B", "C", "D"],
                "text": "Что верно?",
                "answer_key": {},
                "key_points": [],
            })

    def test_multi_choice_serialises_indexes(self):
        """Контракт v4.1: эталон multi_choice выходит наружу — backend пишет
        его в `test_questions.answer_key`."""
        q = TestQuestion.from_dict({
            "id": 1, "type_question": "multi_choice",
            "options": ["A", "B", "C", "D"],
            "text": "Что верно?",
            "answer_key": {"correct_indexes": [0, 3], "explanation": "пояснение"},
            "key_points": [],
        })
        assert q.correct_indexes() == [0, 3]
        assert q.answer_key["explanation"] == "пояснение"
        dumped = q.to_dict()
        assert dumped["answer_key"] == {
            "correct_indexes": [0, 3], "explanation": "пояснение",
        }
        assert dumped["options"] == ["A", "B", "C", "D"]

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="unknown type_question"):
            TestQuestion.from_dict({
                "id": 1, "type_question": "true_false", "options": ["A", "B"],
                "text": "Вопрос?",
                "answer_key": {"correct_index": 0},
                "key_points": [],
            })
