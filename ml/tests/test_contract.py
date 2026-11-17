"""Контрактные тесты: формат сообщений BE ↔ ML.

Контракт — это соглашение двух сторон, поэтому его нужно защищать тестом с
обеих сторон. Здесь фиксируется **канонический вид** payload'ов: набор ключей
и их типы. Если кто-то добавит или переименует поле в `app/contracts.py`, тест
упадёт — и правку придётся прогнать через backend тоже, а не молча разъехаться.

Что проверяется:
  - задачи, которые шлёт backend, разбираются ML без потерь (round-trip);
  - результаты, которые шлёт ML, разбираются backend'ом без потерь — здесь
    проверяется форма, которую backend ждёт в своих record'ах;
  - `answer_key` соответствует типу вопроса;
  - служебная метка блока (`source_chunk_ref`) наружу не публикуется.

Полная спека: `ml/docs/superpowers/specs/2026-11-17-ml-backend-contract-v4.md`.
"""

from __future__ import annotations

import json

import pytest

from app.contracts import (
    BE_TO_ML,
    ML_TO_BE,
    CreateTestResult,
    CreateTestTask,
    GradeAttemptResult,
    GradeAttemptTask,
    GradedItem,
    IngestResult,
    IngestTask,
    TASK_CHANNEL_SLUGS,
    Test,
    TestQuestion,
    channel_task_type,
    mirror_channel,
    parse_task,
    result_channel,
    stream_channel,
    task_channel,
)


def payload_of(obj) -> dict:
    """Канонический вид сообщения: ровно то, что уходит в Redis."""
    return json.loads(obj.to_json())


# ============================================================================
#  Схема имён Redis-каналов
# ============================================================================

class TestChannelNames:
    def test_slug_matches_internal_task_type(self):
        assert TASK_CHANNEL_SLUGS == {
            "ingest": "ingest",
            "rag_question": "rag-question",
            "create_test": "create-test",
            "grade_attempt": "grade-test",
        }

    @pytest.mark.parametrize(
        ("task_type", "channel"),
        [
            ("ingest", "ingest:be-to-ml"),
            ("create_test", "create-test:be-to-ml"),
            ("grade_attempt", "grade-test:be-to-ml"),
        ],
    )
    def test_backend_contract_task_channels(self, task_type, channel):
        assert task_channel(task_type) == channel
        assert result_channel(task_type) == channel.replace(BE_TO_ML, ML_TO_BE)

    def test_legacy_rag_question_channel_is_preserved(self):
        assert task_channel("rag_question") == "rag-question:be-to-ml"
        assert result_channel("rag_question") == "rag-question:ml-to-be"

    @pytest.mark.parametrize(
        ("task_type", "direction"),
        [
            ("ingest", BE_TO_ML),
            ("ingest", ML_TO_BE),
            ("rag_question", BE_TO_ML),
            ("create_test", BE_TO_ML),
            ("grade_attempt", ML_TO_BE),
        ],
    )
    def test_channel_task_type_round_trip(self, task_type, direction):
        channel = stream_channel(task_type, direction)
        assert channel_task_type(channel) == task_type

    def test_unknown_task_type_raises_key_error(self):
        with pytest.raises(KeyError):
            stream_channel("unknown", BE_TO_ML)

    @pytest.mark.parametrize("channel", ["", "unknown", "unknown:be-to-ml", "create_test:be-to-ml"])
    def test_unknown_channel_has_no_task_type(self, channel):
        assert channel_task_type(channel) == ""

    @pytest.mark.parametrize(
        ("channel", "expected"),
        [
            ("foo:be-to-ml", "foo:ml-to-be"),
            ("foo", "foo:ml-to-be"),
            ("ingest:be-to-ml", "ingest:ml-to-be"),
        ],
    )
    def test_mirror_channel(self, channel, expected):
        assert mirror_channel(channel) == expected


# ============================================================================
#  BE → ML: задачи, которые шлёт backend
# ============================================================================

class TestTaskPayloads:
    def test_ingest_task_matches_backend_payload(self):
        """Backend шлёт task_id, material_id, storage_key — ML читает их все."""
        task = IngestTask(
            material_id="5a2c0000-0000-0000-0000-000000000001",
            storage_key="uploads/lec.pdf",
            task_id="8f1b0000-0000-0000-0000-000000000002",
        )
        assert payload_of(task) == {
            "task_id": "8f1b0000-0000-0000-0000-000000000002",
            "material_id": "5a2c0000-0000-0000-0000-000000000001",
            "storage_key": "uploads/lec.pdf",
        }

    def test_create_test_task_matches_backend_payload(self):
        """Ключи create_test: amountQuestions (число), difficulty, material_ids."""
        task = CreateTestTask(
            task_id="t1",
            test_id="test-1",
            material_ids=["m1", "m2"],
            title="Quiz",
            num_questions=10,
            difficulty="medium",
            course_id="c1",
        )
        assert payload_of(task) == {
            "task_id": "t1",
            "test_id": "test-1",
            "material_ids": ["m1", "m2"],
            "title": "Quiz",
            "amountQuestions": 10,
            "difficulty": "medium",
            "course_id": "c1",
        }

    def test_grade_attempt_task_matches_backend_payload(self):
        """student_answer — ровно один вид: index | indexes | text."""
        task = GradeAttemptTask(
            task_id="t1",
            attempt_id="a1",
            test_id="test-1",
            user_id="u1",
            answers=[],
        )
        from app.contracts import StudentAnswer
        task.answers = [
            StudentAnswer(question_id="q1", student_answer_index=2),
            StudentAnswer(question_id="q2", student_answer_indexes=[0, 2]),
            StudentAnswer(question_id="q3", student_answer_text="мой ответ"),
        ]
        assert payload_of(task)["answers"] == [
            {"question_id": "q1", "student_answer": {"index": 2}},
            {"question_id": "q2", "student_answer": {"indexes": [0, 2]}},
            {"question_id": "q3", "student_answer": {"text": "мой ответ"}},
        ]


class TestTaskParsing:
    """Задачи backend'а ML обязан разобрать без потерь."""

    def test_parses_backend_ingest_payload(self):
        raw = {
            "task_id": "t1",
            "material_id": "m1",
            "storage_key": "uploads/lec.pdf",
        }
        task = parse_task(raw, "ingest")
        assert isinstance(task, IngestTask)
        assert task.material_id == "m1"
        assert task.storage_key == "uploads/lec.pdf"

    def test_parses_backend_create_test_payload(self):
        raw = {
            "task_id": "t1",
            "test_id": "test-1",
            "material_ids": ["m1"],
            "title": "Quiz",
            "amountQuestions": 20,
            "difficulty": "hard",
            "course_id": "c1",
        }
        task = parse_task(raw, "create_test")
        assert isinstance(task, CreateTestTask)
        assert task.num_questions == 20
        assert task.difficulty == "hard"

    def test_parses_backend_grade_attempt_payload(self):
        raw = {
            "task_id": "t1",
            "attempt_id": "a1",
            "test_id": "test-1",
            "user_id": "u1",
            "answers": [
                {"question_id": "q1", "student_answer": {"index": 1}},
                {"question_id": "q2", "student_answer": {"indexes": [0, 3]}},
                {"question_id": "q3", "student_answer": {"text": "ответ"}},
            ],
        }
        task = parse_task(raw, "grade_attempt")
        assert isinstance(task, GradeAttemptTask)
        assert task.answers[0].student_answer_index == 1
        assert task.answers[1].student_answer_indexes == [0, 3]
        assert task.answers[2].student_answer_text == "ответ"


# ============================================================================
#  ML → BE: результаты, которые ждёт backend
# ============================================================================

class TestResultPayloads:
    def test_ingest_ready_payload(self):
        result = IngestResult.ok(task_id="t1", material_id="m1", chunks_indexed=29)
        assert payload_of(result) == {
            "task_id": "t1",
            "material_id": "m1",
            "status": "ready",
            "chunks_indexed": 29,
        }

    def test_ingest_error_payload_keeps_material_id(self):
        """material_id в error-ветке обязателен: без него backend не знает,
        какую строку materials перевести в error."""
        result = IngestResult.err(task_id="t1", error="unsupported format", material_id="m1")
        payload = payload_of(result)
        assert payload["status"] == "error"
        assert payload["error"] == "unsupported format"
        assert payload["material_id"] == "m1"

    def test_create_test_ok_payload(self):
        question = TestQuestion(
            id=1,
            text="Вопрос?",
            type_question="single_choice",
            options=["A", "B"],
            answer_key={"correct_index": 0, "explanation": "Потому что"},
            key_points=[],
            source_chunk_id="chunk-1",
        )
        result = CreateTestResult.ok(
            task_id="t1", test=Test(title="Quiz", questions=[question]), test_id="test-1",
        )
        payload = payload_of(result)
        assert payload["status"] == "ok"
        assert payload["test_id"] == "test-1"
        assert payload["test"]["title"] == "Quiz"
        assert payload["test"]["questions"] == [{
            "id": 1,
            "type": "single_choice",
            "text": "Вопрос?",
            "options": ["A", "B"],
            "answer_key": {"correct_index": 0, "explanation": "Потому что"},
            "key_points": [],
            "source_chunk_id": "chunk-1",
        }]

    def test_create_test_error_payload_keeps_test_id(self):
        result = CreateTestResult.err(task_id="t1", error="boom", test_id="test-1")
        payload = payload_of(result)
        assert payload["status"] == "error"
        assert payload["error"] == "boom"
        assert payload["test_id"] == "test-1"

    def test_grade_attempt_ok_payload(self):
        result = GradeAttemptResult.ok(
            task_id="t1", attempt_id="a1", test_id="test-1",
            score_pct=60.0, grade=3,
            items=[GradedItem(
                question_id="q1", is_correct=True, score=1.0,
                feedback="Верно", correct_answer="A", student_answer="A",
            )],
        )
        payload = payload_of(result)
        assert payload["status"] == "ok"
        assert payload["score_pct"] == 60.0
        assert payload["grade"] == 3
        assert payload["items"] == [{
            "question_id": "q1",
            "is_correct": True,
            "score": 1.0,
            "feedback": "Верно",
            "correct_answer": "A",
            "student_answer": "A",
        }]

    def test_grade_attempt_error_payload_keeps_ids(self):
        result = GradeAttemptResult.err(
            task_id="t1", error="boom", attempt_id="a1", test_id="test-1",
        )
        payload = payload_of(result)
        assert payload["status"] == "error"
        assert payload["attempt_id"] == "a1"
        assert payload["test_id"] == "test-1"

    def test_results_carry_no_type_field(self):
        """Тип задачи задаёт имя канала — поля type в payload нет."""
        results = [
            IngestResult.ok(task_id="t1", material_id="m1", chunks_indexed=1),
            CreateTestResult.err(task_id="t1", error="boom", test_id="test-1"),
            GradeAttemptResult.err(task_id="t1", error="boom"),
        ]
        for result in results:
            assert "type" not in payload_of(result)


# ============================================================================
#  Формат вопроса
# ============================================================================

class TestQuestionFormat:
    def test_answer_key_per_type(self):
        single = TestQuestion.from_dict({
            "id": 1, "type": "single_choice", "text": "Q",
            "options": ["A", "B"], "answer_key": {"correct_index": 1, "explanation": "E"},
        })
        assert single.answer_key["correct_index"] == 1
        assert single.correct_indexes() == []

        multi = TestQuestion.from_dict({
            "id": 2, "type": "multi_choice", "text": "Q",
            "options": ["A", "B", "C", "D"],
            "answer_key": {"correct_indexes": [2, 0], "explanation": "E"},
        })
        assert multi.correct_indexes() == [0, 2]

        open_ = TestQuestion.from_dict({
            "id": 3, "type": "open_answer", "text": "Q",
            "options": [],
            "answer_key": {"reference_answer": "эталон", "explanation": "E"},
            "key_points": ["пункт 1", "пункт 2"],
        })
        assert open_.reference_answer() == "эталон"
        assert open_.criteria() == ["пункт 1", "пункт 2"]

    def test_key_points_is_flat_list_of_strings(self):
        """Старая форма (объект с criteria) нормализуется в плоский список."""
        question = TestQuestion.from_dict({
            "id": 1, "type": "open_answer", "text": "Q",
            "options": [],
            "answer_key": {"reference_answer": "эталон", "explanation": "E"},
            "key_points": {"criteria": ["пункт 1", "пункт 2"]},
        })
        assert question.key_points == ["пункт 1", "пункт 2"]

    def test_chunk_ref_is_not_published(self):
        """Метка блока — внутренняя: наружу уходит только source_chunk_id."""
        question = TestQuestion.from_dict({
            "id": 1, "type": "single_choice", "text": "Q",
            "options": ["A", "B"], "answer_key": {"correct_index": 0, "explanation": "E"},
            "source_chunk_ref": "C7",
            "source_chunk_id": "chunk-uuid",
        })
        dumped = question.to_dict()
        assert "source_chunk_ref" not in dumped
        assert dumped["source_chunk_id"] == "chunk-uuid"

    @pytest.mark.parametrize(
        "payload",
        [
            {"id": 1, "type": "single_choice", "text": "Q", "options": ["A"],
             "answer_key": {"correct_index": 0}},
            {"id": 1, "type": "multi_choice", "text": "Q", "options": ["A", "B"],
             "answer_key": {"correct_indexes": [0]}},
            {"id": 1, "type": "open_answer", "text": "Q", "options": [],
             "answer_key": {}},
            {"id": 1, "type": "true_false", "text": "Q", "options": [],
             "answer_key": {"correct_index": 0}},
        ],
    )
    def test_invalid_questions_are_rejected(self, payload):
        """ML не отдаёт backend'у вопрос, который нечем оценить."""
        with pytest.raises(ValueError):
            TestQuestion.from_dict(payload)
