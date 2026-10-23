"""Чанки материала в Postgres: единственная таблица, в которую ML пишет.

Схема (docs + миграции backend):
    material_chunks(chunk_id UUID PK, material_id UUID FK, text_chunk TEXT,
                    page_number INT NULL, heading VARCHAR NULL,
                    embedding vector(1536) NULL, created_at TIMESTAMPTZ)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from loguru import logger

from app.db.pool import get_pool, to_vector


@dataclass
class ChunkHit:
    """Найденный чанк. distance — косинусное расстояние, меньше значит ближе."""

    chunk_id: str
    material_id: str
    text: str
    distance: float


class PgChunkStore:
    """Запись и векторный поиск по material_chunks. Единственный владелец
    pgvector-доступа в приложении."""

    async def add_chunks(
        self, material_id: str, texts: list[str], embeddings: list[list[float]]
    ) -> list[str]:
        """Положить чанки материала в БД и вернуть их chunk_id в том же порядке.

        Перед вставкой удаляет прежние чанки материала — повторный ingest того же
        материала не должен плодить дубли.
        """
        if not texts:
            return []
        if len(texts) != len(embeddings):
            raise ValueError(f"texts/embeddings length mismatch: {len(texts)} vs {len(embeddings)}")

        chunk_ids = [str(uuid.uuid4()) for _ in texts]
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM material_chunks WHERE material_id = $1::uuid", material_id
                )
                await conn.executemany(
                    "INSERT INTO material_chunks (chunk_id, material_id, text_chunk, embedding) "
                    "VALUES ($1::uuid, $2::uuid, $3, $4::vector)",
                    [
                        (cid, material_id, text, to_vector(vec))
                        for cid, text, vec in zip(chunk_ids, texts, embeddings)
                    ],
                )
        logger.info(f"Stored {len(chunk_ids)} chunks for material {material_id}")
        return chunk_ids

    async def search(
        self, material_ids: list[str], query_embedding: list[float], top_k: int
    ) -> list[ChunkHit]:
        """Ближайшие чанки по косинусному расстоянию среди указанных материалов."""
        if not material_ids:
            return []
        pool = await get_pool()
        rows = await pool.fetch(
            "SELECT chunk_id, material_id, text_chunk, embedding <=> $1::vector AS distance "
            "FROM material_chunks "
            "WHERE material_id = ANY($2::uuid[]) AND embedding IS NOT NULL "
            "ORDER BY distance "
            "LIMIT $3",
            to_vector(query_embedding),
            material_ids,
            top_k,
        )
        return [
            ChunkHit(
                chunk_id=str(r["chunk_id"]),
                material_id=str(r["material_id"]),
                text=r["text_chunk"],
                distance=float(r["distance"]),
            )
            for r in rows
        ]

    async def has_material(self, material_id: str) -> bool:
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT 1 FROM material_chunks WHERE material_id = $1::uuid LIMIT 1", material_id
        )
        return row is not None