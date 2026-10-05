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
    ml_tasks_stream: str = "ml-tasks"
    ml_results_stream: str = "ml-results"
    consumer_group: str = "ml-workers"
    consumer_name: str = "worker-1"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minio_user"
    minio_secret_key: str = "minio_password"
    minio_bucket: str = "materials"
    minio_secure: bool = False

    # Misc
    log_level: str = "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings