import pytest
from app.core.config import Settings


def test_settings_loads_all_defaults(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    s = Settings()
    assert s.openrouter_api_key == "test-key"
    assert s.llm_model == "minimax/minimax-m3:free"
    assert s.embed_model == "openai/text-embedding-3-small"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.minio_endpoint == "localhost:9000"
    assert s.minio_bucket == "materials"
    assert s.minio_secure is False


def test_settings_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # уходим в директорию без .env
    with pytest.raises(Exception):
        Settings()


def test_each_task_has_its_own_stream_pair(monkeypatch):
    """Три задачи — три независимые очереди. Общие стримы означали бы, что
    зависшая генерация теста блокирует ingest."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    s = Settings()

    tasks = [s.stream_tasks_ingest, s.stream_tasks_create_test, s.stream_tasks_grade_attempt]
    results = [
        s.stream_results_ingest,
        s.stream_results_create_test,
        s.stream_results_grade_attempt,
    ]
    assert len(set(tasks)) == 3
    assert len(set(results)) == 3
    assert not set(tasks) & set(results)


def test_settings_reads_stream_names_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("STREAM_TASKS_INGEST", "custom:ingest")
    s = Settings()
    assert s.stream_tasks_ingest == "custom:ingest"