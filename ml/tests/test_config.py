import socket

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


def test_consumer_name_defaults_to_hostname(monkeypatch, tmp_path):
    """Имя consumer'а по умолчанию — имя машины (env CONSUMER_NAME может
    переопределить)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONSUMER_NAME", raising=False)
    s = Settings()
    assert s.consumer_name == socket.gethostname()

    monkeypatch.setenv("CONSUMER_NAME", "worker-from-env")
    assert Settings().consumer_name == "worker-from-env"


def test_claim_settings_defaults(monkeypatch, tmp_path):
    """Настройки reclaim'а: env WORKER_CLAIM_* без env_prefix."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("WORKER_CLAIM_IDLE_MS", raising=False)
    monkeypatch.delenv("WORKER_CLAIM_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("WORKER_CLAIM_INTERVAL_MS", raising=False)
    s = Settings()
    assert s.worker_claim_idle_ms == 30_000
    assert s.worker_claim_max_attempts == 5
    assert s.worker_claim_interval_ms == 60_000


def test_claim_settings_read_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("WORKER_CLAIM_IDLE_MS", "1000")
    monkeypatch.setenv("WORKER_CLAIM_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("WORKER_CLAIM_INTERVAL_MS", "3000")
    s = Settings()
    assert s.worker_claim_idle_ms == 1000
    assert s.worker_claim_max_attempts == 2
    assert s.worker_claim_interval_ms == 3000


def test_settings_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # уходим в директорию без .env
    with pytest.raises(Exception):
        Settings()
