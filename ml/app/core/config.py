import socket

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM / Embeddings (через RouterAI, OpenAI-совместимый API).
    # Имя поля `openrouter_api_key` и env `OPENROUTER_API_KEY` оставлены как
    # есть: на них завязаны docker-compose и код, переименование — вне задачи.
    openrouter_api_key: str
    llm_model: str = "minimax/minimax-m3:free"
    embed_model: str = "openai/text-embedding-3-small"
    base_url: str = "https://routerai.ru/api/v1"

    # Модель LLM-судьи (open_answer и choice). Пусто → судья работает на
    # общей LLM_MODEL, как раньше.
    # Имя переменной задано с дефисом (LLM-AS-A-JUDGE), но дефис невозможен
    # для docker compose interpolation ${...} — поэтому принимаем обе формы
    # плюс короткое JUDGE_MODEL. Порядок в AliasChoices = приоритет.
    judge_model: str = Field(
        default="",
        validation_alias=AliasChoices(
            "LLM_AS_A_JUDGE",
            "LLM-AS-A-JUDGE",
            "JUDGE_MODEL",
        ),
    )

    # Redis Streams
    redis_url: str = "redis://localhost:6379/0"
    # Имена каналов — часть контракта и заданы в app/contracts.py.
    consumer_group: str = "ml-workers"
    # Имя consumer'а по умолчанию — имя машины: несколько воркеров на одной
    # машине различаются по префиксу хоста. Env CONSUMER_NAME переопределяет.
    consumer_name: str = socket.gethostname()

    # Reclaim зависших сообщений (pending-список канала).
    # XREADGROUP с ">" отдаёт только новые сообщения: прочитанное, но не
    # подтверждённое (XACK), лежит в pending-списке и больше не перечитывается.
    # XAUTOCLAIM возвращает такие сообщения в обработку — доставка получается
    # "как минимум один раз", поэтому запись результата в БД должна быть
    # идемпотентной.
    worker_claim_idle_ms: int = 30_000       # сколько сообщение должно провисеть без XACK
    worker_claim_max_attempts: int = 5       # после скольких попыток бросить сообщение
    worker_claim_interval_ms: int = 60_000   # как часто может выполняться reclaim-проход

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

    # Подробные логи LLM: полные промпты, схемы и сырые ответы модели.
    # Включено по умолчанию — владелец хочет видеть в docker logs всё, что
    # уходит в LLM и что возвращается. Выключается env-переменной
    # LOG_LLM_PAYLOADS=false: тогда остаются только обычные INFO-строки.
    log_llm_payloads: bool = True

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