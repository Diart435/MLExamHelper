"""Async byte-fetcher used by all parsers.

Two modes:
  - Local file (path exists on disk): read bytes directly. Used by `app.demo`
    so demos work without a running MinIO.
  - Remote object (MinIO): stream bytes through the sync `minio-py` client,
    offloaded to a thread so the event loop isn't blocked.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.minio_client import get_minio


async def fetch_bytes(storage_key: str, settings: Settings | None = None) -> bytes:
    """Returns raw bytes for `storage_key` from MinIO, or from local disk if present."""
    path = Path(storage_key)
    if path.is_file():
        return await asyncio.to_thread(path.read_bytes)

    s = settings or get_settings()

    def _read_from_minio() -> bytes:
        client = get_minio(s)
        bucket = s.minio_bucket
        try:
            response = client.get_object(bucket, storage_key)
        except Exception as e:
            raise FileNotFoundError(
                f"Object '{storage_key}' not found in bucket '{bucket}': {e}"
            ) from e
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await asyncio.to_thread(_read_from_minio)