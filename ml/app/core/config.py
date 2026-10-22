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

    # Postgres. ML пишет только material_chunks, читает test_questions.
    database_url: str = "postgresql://ml:ml@localhost:5432/ml"
    db_pool_min_size: int = 1
    db_pool_max_size: int = 4

    # Redis Streams. Тип задачи задаёт имя стрима, поле type не передаётся.
    redis_url: str = "redis://localhost:6379/0"
    stream_tasks_ingest: str = "ml:tasks:ingest"
    stream_tasks_create_test: str = "ml:tasks:create-test"
    stream_tasks_grade_attempt: str = "ml:tasks:grade-attempt"
    stream_results_ingest: str = "ml:results:ingest"
    stream_results_create_test: str = "ml:results:create-test"
    stream_results_grade_attempt: str = "ml:results:grade-attempt"
    consumer_group: str = "ml-workers"
    consumer_name: str = "worker-1"
    worker_claim_idle_ms: int = 30000

    # S3 (seaweedfs)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minio_user"
    minio_secret_key: str = "minio_password"
    minio_bucket: str = "materials"
    minio_secure: bool = False

    # RAG
    chunk_size: int = 800
    chunk_overlap: int = 100
    context_chunks: int = 12

    # Misc
    log_level: str = "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings