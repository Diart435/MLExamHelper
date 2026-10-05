import pytest
from app.core.config import Settings


def test_settings_loads_all_defaults(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    s = Settings()
    assert s.openrouter_api_key == "test-key"
    assert s.llm_model == "minimax/minimax-m3:free"
    assert s.embed_model == "openai/text-embedding-3-small"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.ml_tasks_stream == "ml-tasks"
    assert s.ml_results_stream == "ml-results"
    assert s.consumer_group == "ml-workers"
    assert s.minio_endpoint == "localhost:9000"
    assert s.minio_bucket == "materials"
    assert s.minio_secure is False


def test_settings_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # уходим в директорию без .env
    with pytest.raises(Exception):
        Settings()