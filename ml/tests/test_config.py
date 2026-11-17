import pytest
from app.core.config import Settings


def test_settings_loads_all_defaults(monkeypatch, tmp_path):
    # chdir в tmp без .env — иначе подхватится пользовательский .env и
    # дефолты не сработают.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.openrouter_api_key == "test-key"
    assert s.llm_model == "minimax/minimax-m3:free"
    assert s.embed_model == "openai/text-embedding-3-small"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.consumer_group == "ml-workers"
    assert s.minio_endpoint == "localhost:9000"
    assert s.minio_bucket == "materials"
    assert s.minio_secure is False
    # pgvector defaults
    assert s.vector_store_backend == "mem"
    assert s.database_url.startswith("postgresql://")


def test_settings_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # уходим в директорию без .env
    with pytest.raises(Exception):
        Settings()
