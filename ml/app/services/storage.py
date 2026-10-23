"""Скачивание исходника материала из S3 (seaweedfs). Отдаёт байты —
разбором занимается app.parsers.registry."""

from __future__ import annotations

import asyncio

from minio.error import S3Error

from app.core.config import get_settings
from app.core.minio_client import get_minio


async def download_bytes(storage_key: str) -> bytes:
    """Скачать объект из бакета. minio-py синхронный — уводим в поток,
    чтобы не блокировать остальные два цикла воркера."""

    def _download() -> bytes:
        s = get_settings()
        client = get_minio(s)
        try:
            response = client.get_object(s.minio_bucket, storage_key)
        except S3Error as e:
            raise FileNotFoundError(
                f"object '{storage_key}' not found in bucket '{s.minio_bucket}': {e}"
            ) from e
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await asyncio.to_thread(_download)