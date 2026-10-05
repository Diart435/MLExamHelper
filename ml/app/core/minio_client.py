from minio import Minio

from app.core.config import Settings, get_settings


def get_minio(settings: Settings | None = None) -> Minio:
    """Returns a sync Minio client. Caller responsible for not sharing across threads."""
    s = settings or get_settings()
    return Minio(
        s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
        secure=s.minio_secure,
    )