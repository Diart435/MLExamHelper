"""Проводка воркера: какой канал на какой стрим и какой обработчик.

Redis тут не поднимаем — проверяем чистую таблицу каналов и то, что воркер
умеет отдалить нечитаемое сообщение, не залипнув на нём навсегда."""

from app.contracts import CreateTestTask, GradeAttemptTask, IngestTask
from app.core.config import Settings
from app.handlers.create_test import process_create_test
from app.handlers.grade_attempt import process_grade_attempt
from app.handlers.ingest import process_ingest
from app.workers.worker import _error_result, _peek_task_id, channels_of


def settings() -> Settings:
    return Settings(openrouter_api_key="test-key")


def test_three_channels_with_distinct_stream_pairs():
    channels = channels_of(settings())
    assert [c.name for c in channels] == ["ingest", "create_test", "grade_attempt"]

    tasks = [c.tasks_stream for c in channels]
    results = [c.results_stream for c in channels]
    assert len(set(tasks)) == 3
    assert len(set(results)) == 3
    assert not set(tasks) & set(results)


def test_each_channel_is_wired_to_its_handler():
    by_name = {c.name: c for c in channels_of(settings())}
    assert by_name["ingest"].handler is process_ingest
    assert by_name["create_test"].handler is process_create_test
    assert by_name["grade_attempt"].handler is process_grade_attempt


def test_channel_stream_names_come_from_settings():
    channels = {c.name: c for c in channels_of(settings())}
    assert channels["ingest"].tasks_stream == "ml:tasks:ingest"
    assert channels["ingest"].results_stream == "ml:results:ingest"
    assert channels["create_test"].tasks_stream == "ml:tasks:create-test"
    assert channels["grade_attempt"].tasks_stream == "ml:tasks:grade-attempt"


def test_peek_task_id_survives_broken_payloads():
    assert _peek_task_id('{"task_id": "t1"}') == "t1"
    assert _peek_task_id("{not json") is None
    assert _peek_task_id('["t1"]') is None
    assert _peek_task_id('{"task_id": ""}') is None


def test_error_result_carries_ids_the_backend_needs():
    """Без test_id/attempt_id backend не найдёт строку и оставит её в queued."""

    create = _error_result(
        "create_test", "t", "boom", CreateTestTask("t", "te1", ["m"], "Название")
    )
    assert '"test_id": "te1"' in create.to_json()

    attempt = _error_result(
        "grade_attempt", "t", "boom", GradeAttemptTask("t", "a1", "te1")
    )
    payload = attempt.to_json()
    assert '"attempt_id": "a1"' in payload
    assert '"test_id": "te1"' in payload

    ingest = _error_result("ingest", "t", "boom", IngestTask("t", "m1", "a.pdf"))
    assert '"material_id"' not in ingest.to_json()