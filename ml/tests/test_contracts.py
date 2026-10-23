"""Контракт — граница между двумя сервисами, поэтому проверяем именно его:
одинаковый JSON на входе и выходе, никакого поля type нигде."""

import json

import pytest

from app.contracts import (
    ContractError,
    CreateTestResult,
    CreateTestTask,
    GradeAttemptResult,
    GradeAttemptTask,
    GradedItem,
    IngestResult,
    IngestTask,
    Test,
    TestQuestion,
    grade_from_pct,
    parse_task,
)

FORBIDDEN = ("type", "input_msg_id")


def _no_leaked_fields(payload: dict) -> None:
    for field in FORBIDDEN:
        assert field not in payload, f"поле {field!r} должно быть убрано из контракта"


# --------------------------------------------------------------------------
#  ВХОД: backend → ML
# --------------------------------------------------------------------------


def test_parse_ingest_task():
    task = parse_task(
        "ingest",
        '{"task_id": "t1", "material_id": "11111111-1111-1111-1111-111111111111", '
        '"storage_key": "lectures/1.pdf"}',
    )
    assert isinstance(task, IngestTask)
    assert task.task_id == "t1"
    assert task.storage_key == "lectures/1.pdf"


def test_parse_create_test_task():
    task = parse_task(
        "create_test",
        '{"task_id": "t2", "test_id": "t", "material_ids": ["m1", "m2"], '
        '"title": "Основы СУБД", "num_questions": 5, "difficulty": "hard", "course_id": "c1"}',
    )
    assert isinstance(task, CreateTestTask)
    assert task.material_ids == ["m1", "m2"]
    assert task.difficulty == "hard"


def test_parse_grade_attempt_task():
    task = parse_task(
        "grade_attempt",
        '{"task_id": "t3", "attempt_id": "a1", "test_id": "te1", '
        '"answers": [{"question_id": "q1", "student_answer_index": 2}]}',
    )
    assert isinstance(task, GradeAttemptTask)
    assert task.answers[0].student_answer_index == 2


def test_parse_task_accepts_dict_as_well_as_json_string():
    payload = {"task_id": "t1", "material_id": "m", "storage_key": "a.txt"}
    assert parse_task("ingest", payload) == parse_task("ingest", json.dumps(payload))


@pytest.mark.parametrize(
    ("channel", "payload"),
    [
        ("rag_question", '{"task_id": "t"}'),
        ("unknown", '{"task_id": "t"}'),
    ],
)
def test_parse_task_rejects_unknown_channel(channel, payload):
    with pytest.raises(ContractError):
        parse_task(channel, payload)


def test_parse_task_rejects_broken_json():
    with pytest.raises(ContractError):
        parse_task("ingest", "{not json")


@pytest.mark.parametrize(
    "payload",
    [
        '{"material_id": "m", "storage_key": "a.txt"}',
        '{"task_id": "", "material_id": "m", "storage_key": "a.txt"}',
    ],
)
def test_parse_ingest_requires_its_fields(payload):
    with pytest.raises(ContractError):
        parse_task("ingest", payload)


def test_create_test_requires_non_empty_material_ids():
    with pytest.raises(ContractError):
        parse_task("create_test", '{"task_id": "t", "test_id": "te", "title": "x", "material_ids": []}')


def test_create_test_rejects_unknown_difficulty():
    with pytest.raises(ContractError):
        parse_task(
            "create_test",
            '{"task_id": "t", "test_id": "te", "title": "x", "material_ids": ["m"], '
            '"difficulty": "extreme"}',
        )


def test_create_test_rejects_zero_questions():
    with pytest.raises(ContractError):
        parse_task(
            "create_test",
            '{"task_id": "t", "test_id": "te", "title": "x", "material_ids": ["m"], "num_questions": 0}',
        )


# --------------------------------------------------------------------------
#  ВЫХОД: ML → backend
# --------------------------------------------------------------------------


def test_ingest_ok_result_is_task_id_and_status_only():
    out = json.loads(IngestResult.ok("t1").to_json())
    assert out == {"task_id": "t1", "status": "ok"}
    _no_leaked_fields(out)


def test_ingest_error_result_carries_reason():
    out = json.loads(IngestResult.err("t1", "boom").to_json())
    assert out == {"task_id": "t1", "status": "error", "error": "boom"}


def test_create_test_ok_result_shape():
    test = Test(
        title="Основы СУБД",
        questions=[
            TestQuestion(id=1, text="Что такое индекс?", options=["a", "b", "c", "d"],
                         correct_index=2, source_chunk_id="chunk-1"),
            TestQuestion(id=2, text="Что такое транзакция?", options=["a", "b"], correct_index=0),
        ],
    )
    out = json.loads(CreateTestResult.ok("t2", "te1", test).to_json())

    _no_leaked_fields(out)
    assert out["status"] == "ok"
    assert out["test_id"] == "te1"
    assert out["test"]["title"] == "Основы СУБД"

    first = out["test"]["questions"][0]
    assert first["source_chunk_id"] == "chunk-1"
    assert first["correct_index"] == 2
    # explanation наружу не отдаём: в test_questions такой колонки нет
    assert "explanation" not in first


def test_create_test_ok_without_test_is_a_contract_error():
    with pytest.raises(ContractError):
        CreateTestResult(task_id="t2", test_id="te1", status="ok").to_json()


def test_create_test_error_result_still_names_the_test():
    out = json.loads(CreateTestResult.err("t2", "нет чанков", "te1").to_json())
    assert out == {"task_id": "t2", "status": "error", "test_id": "te1", "error": "нет чанков"}


def test_grade_result_has_no_per_question_verdict():
    """is_correct, correct_index, student_answer_index у backend'а уже есть
    в его же таблицах — дублировать их в payload незачем."""
    out = json.loads(
        GradeAttemptResult.ok(
            task_id="t3",
            attempt_id="a1",
            test_id="te1",
            score_pct=66.67,
            grade=3,
            overall_feedback="Разбери нормализацию форм.",
            items=[GradedItem(question_id="q1", score=1.0), GradedItem(question_id="q2", score=0.0)],
        ).to_json()
    )

    _no_leaked_fields(out)
    assert out["score_pct"] == 66.67
    assert out["grade"] == 3
    assert out["overall_feedback"] == "Разбери нормализацию форм."
    assert out["items"] == [
        {"question_id": "q1", "score": 1.0},
        {"question_id": "q2", "score": 0.0},
    ]
    for item in out["items"]:
        assert "is_correct" not in item
        assert "feedback" not in item


def test_grade_error_result_keeps_ids_so_backend_can_find_its_row():
    out = json.loads(GradeAttemptResult.err("t3", "boom", "a1", "te1").to_json())
    assert out["status"] == "error"
    assert out["attempt_id"] == "a1"
    assert out["test_id"] == "te1"
    assert "items" not in out


@pytest.mark.parametrize(
    ("pct", "grade"),
    [(100, 5), (90, 5), (89.99, 4), (70, 4), (69.99, 3), (50, 3), (49.99, 2), (0, 2)],
)
def test_grade_scale(pct, grade):
    assert grade_from_pct(pct) == grade