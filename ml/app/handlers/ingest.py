"""Задача ingest: файл из S3 → текст → чанки → material_chunks.

Чистая функция: ни Redis, ни сети наружу наружу не торчит — всё, что нужно,
приходит аргументами. Поэтому её можно вызывать из воркера и из тестов.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from app.contracts import IngestResult, IngestTask
from app.db.chunks import PgChunkStore
from app.parsers import registry
from app.services.chunker import split_text
from app.services.embeddings import EmbeddingsClient
from app.services.storage import download_bytes


async def process_ingest(
    task: IngestTask,
    *,
    chunks: PgChunkStore | None = None,
    embeddings: EmbeddingsClient | None = None,
) -> IngestResult:
    """Нарезать материал и положить чанки в БД. Любая ошибка — status=error."""
    try:
        store = chunks or PgChunkStore()
        embedder = embeddings or EmbeddingsClient()

        data = await download_bytes(task.storage_key)
        text = await asyncio.to_thread(registry.parse, task.storage_key, data)
        if not text.strip():
            raise ValueError(f"material {task.material_id} parsed into empty text")

        pieces = split_text(text)
        if not pieces:
            raise ValueError(f"material {task.material_id} produced no chunks")

        vectors = await embedder.embed_batch(pieces)
        chunk_ids = await store.add_chunks(task.material_id, pieces, vectors)
        logger.info(f"Ingested material {task.material_id}: {len(chunk_ids)} chunks")
        return IngestResult.ok(task.task_id)

    except Exception as e:  # noqa: BLE001 — наружу уходит результат, а не исключение
        logger.exception(f"Ingest failed for material {task.material_id}: {e}")
        return IngestResult.err(task.task_id, f"{type(e).__name__}: {e}")