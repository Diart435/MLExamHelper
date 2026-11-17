from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM / Embeddings (через OpenRouter)
    openrouter_api_key: str
    llm_model: str = "minimax/minimax-m3:free"
    embed_model: str = "openai/text-embedding-3-small"
    base_url: str = "https://openrouter.ai/api/v1"

    # Redis Streams
    redis_url: str = "redis://localhost:6379/0"
    # Имена каналов — часть контракта и заданы в app/contracts.py.
    consumer_group: str = "ml-workers"
    consumer_name: str = "worker-1"

    # Reclaim зависших сообщений (pending-список канала).
    # XREADGROUP с ">" отдаёт только новые сообщения: прочитанное, но не
    # подтверждённое (XACK), лежит в pending-списке и больше не перечитывается.
    # XAUTOCLAIM возвращает такие сообщения в обработку — доставка получается
    # "как минимум один раз", поэтому запись результата в БД должна быть
    # идемпотентной.
    reclaim_idle_ms: int = 120_000      # сколько сообщение должно провисеть без XACK
    reclaim_max_attempts: int = 5       # после скольких попыток бросить сообщение

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minio_user"
    minio_secret_key: str = "minio_password"
    minio_bucket: str = "materials"
    minio_secure: bool = False

    # Vector store backend
    #   "mem" — InMemoryVectorStore (по умолчанию, для тестов / dev без Docker)
    #   "pg"  — PgVectorStore через asyncpg, требует поднятый docker compose
    vector_store_backend: str = "mem"
    database_url: str = "postgresql://ml:ml@localhost:5432/ml"

    # Misc
    log_level: str = "INFO"

    # Whisper (local faster-whisper)
    whisper_model_size: str = "base"   # tiny / base / small / medium / large-v3
    whisper_device: str = "cpu"        # cpu / cuda
    whisper_compute_type: str = "int8"  # int8 / float16 / float32
    whisper_enabled: bool = True        # false → audio/video tasks fail explicitly


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings