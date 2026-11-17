"""Vector stores for RAG.

Two backends with the same interface:

  - InMemoryVectorStore: numpy, теряется при рестарте. Для тестов и dev
    без Docker.
  - PgVectorStore: asyncpg + Postgres+pgvector, persistent, переживает
    рестарт worker'а. Пишет в таблицу `material_chunks`, которую создаёт
    backend (миграция `001-initial-schema.sql`).

Factory `create_vector_store(settings)` выбирает backend по env
`VECTOR_STORE_BACKEND` (mem | pg). RAGService получает store через DI,
поэтому оба варианта прозрачны для handler'ов и demo.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from loguru import logger

from app.core.config import Settings, get_settings


def _normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else v


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Both vectors must be 1-D. Returns float in [-1, 1]."""
    na, nb = _normalize(a), _normalize(b)
    return float(np.dot(na, nb))


@dataclass
class Hit:
    chunk_id: str
    text: str
    score: float


class VectorStore(Protocol):
    """Контракт, который использует RAGService. Реализуют оба backend'а."""

    async def add(self, chunk_id: str, text: str, vector: np.ndarray, material_id: str) -> None: ...
    async def search(
        self, query_vector: np.ndarray, top_k: int = 4,
        material_id: str | None = None,
    ) -> list[Hit]: ...
    async def get_chunks(
        self, material_id: str, limit: int | None = None,
    ) -> list[Hit]: ...
    async def has_material(self, material_id: str) -> bool: ...
    async def materials_indexed(self) -> set[str]: ...
    def __len__(self) -> int: ...


# ============================================================================
#  In-memory
# ============================================================================

class InMemoryVectorStore:
    """Simple in-memory vector store. Not persistent — one process lifetime.

    Chunks are grouped by material_id, and search() filters by material_id
    so chunks from other materials never leak into the answer.

    NOTE: методы async, чтобы сигнатура совпадала с PgVectorStore. Для
    in-memory оверхед миллисекундный (микротаски), зато RAGService
    использует один await-путь для обоих backend'ов.
    """

    def __init__(self) -> None:
        # chunk_id -> (text, vector, material_id)
        self._chunks: dict[str, tuple[str, np.ndarray, str]] = {}

    async def add(self, chunk_id: str, text: str, vector: np.ndarray, material_id: str) -> None:
        self._chunks[chunk_id] = (text, vector, material_id)

    def __len__(self) -> int:
        return len(self._chunks)

    async def materials_indexed(self) -> set[str]:
        return {m for (_t, _v, m) in self._chunks.values()}

    async def has_material(self, material_id: str) -> bool:
        return any(m == material_id for (_t, _v, m) in self._chunks.values())

    async def search(self, query_vector: np.ndarray, top_k: int = 4, material_id: str | None = None) -> list[Hit]:
        items = [
            (cid, txt, vec)
            for cid, (txt, vec, mid) in self._chunks.items()
            if material_id is None or mid == material_id
        ]
        if not items:
            return []
        scores = [_cosine_similarity(query_vector, vec) for (_c, _t, vec) in items]
        order = np.argsort(scores)[::-1][:top_k]
        return [
            Hit(chunk_id=items[i][0], text=items[i][1], score=float(scores[i]))
            for i in order
        ]

    async def get_chunks(self, material_id: str, limit: int | None = None) -> list[Hit]:
        """Вернуть чанки материала в порядке chunk_id (≈ в порядке появления в тексте).

        Для test generation не нужен similarity-based retrieval — нужно скормить
        модели как можно больше исходного материала. Score ставим 0.0
        (не similarity).
        """
        items = [
            (cid, txt, mid)
            for cid, (txt, _vec, mid) in self._chunks.items()
            if mid == material_id
        ]
        items.sort(key=lambda x: x[0])
        if limit is not None:
            items = items[:limit]
        return [Hit(chunk_id=cid, text=txt, score=0.0) for cid, txt, _mid in items]


# ============================================================================
#  Postgres + pgvector
# ============================================================================

class PgVectorStore:
    """Persistent vector store on Postgres + pgvector.

    Connection — пул asyncpg. Embedding-колонка vector(1536). Cosine-distance
    считается в БД через оператор `<=>` (`vector_cosine_ops`).

    Схема — та, что заливает backend (миграция `001-initial-schema.sql`):
    таблица `material_chunks` (chunk_id UUID PK, material_id UUID FK→materials,
    text_chunk, embedding vector(1536)). Идентификатор чанка приходит от
    RAGService строкой вида "<material_id>:<hex>" — в БД он лежит UUID,
    поэтому детерминированно отображаем строку в UUID5: re-ingest того же
    материала перезапишет те же чанки, а не заведёт дубли.

    `material_id` в базе — UUID, его создаёт backend (строка `materials`).
    Поэтому читаем через `material_id::text = $1`: не-UUID идентификатор
    даёт «не найдено», а не ошибку приведения типа.
    """

    def __init__(self, dsn: str, pool_min_size: int = 1, pool_max_size: int = 4) -> None:
        self._dsn = dsn
        self._pool_min_size = pool_min_size
        self._pool_max_size = pool_max_size
        self._pool = None  # создаётся в connect()

    async def connect(self) -> None:
        if self._pool is not None:
            return
        import asyncpg  # локальный импорт — pytest с backend=mem не тянет драйвер
        self._pool = await asyncpg.create_pool(
            self._dsn, min_size=self._pool_min_size, max_size=self._pool_max_size,
        )
        logger.info(f"PgVectorStore connected (min={self._pool_min_size}, "
                    f"max={self._pool_max_size})")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self) -> "PgVectorStore":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    # ---- запись ---------------------------------------------------------

    async def add(self, chunk_id: str, text: str, vector: np.ndarray, material_id: str) -> None:
        await self.connect()
        emb = _to_pg_vector(vector)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO material_chunks (chunk_id, material_id, text_chunk, embedding)
                VALUES ($1, $2, $3, $4::vector)
                ON CONFLICT (chunk_id) DO UPDATE
                  SET text_chunk = EXCLUDED.text_chunk, embedding = EXCLUDED.embedding
                """,
                _uuid5(chunk_id), _as_uuid(material_id), text, emb,
            )

    # ---- чтение ---------------------------------------------------------

    async def has_material(self, material_id: str) -> bool:
        await self.connect()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM material_chunks WHERE material_id::text = $1 LIMIT 1",
                material_id,
            )
            return row is not None

    async def materials_indexed(self) -> set[str]:
        await self.connect()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT material_id::text AS mid FROM material_chunks"
            )
            return {r["mid"] for r in rows}

    async def search(
        self, query_vector: np.ndarray, top_k: int = 4,
        material_id: str | None = None,
    ) -> list[Hit]:
        await self.connect()
        emb = _to_pg_vector(query_vector)
        # pgvector возвращает distance (cosine distance ∈ [0, 2]); нашему
        # контракту нужна similarity ∈ [-1, 1], конвертируем как 1 - distance.
        sql = """
            SELECT chunk_id, text_chunk,
                   (1 - (embedding <=> $1::vector)) AS score
            FROM material_chunks
            WHERE material_id::text = $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, emb, material_id, top_k)
        return [
            Hit(chunk_id=str(r["chunk_id"]), text=r["text_chunk"], score=float(r["score"]))
            for r in rows
        ]

    async def get_chunks(
        self, material_id: str, limit: int | None = None,
    ) -> list[Hit]:
        """Чанки материала в порядке добавления. Для test generation.

        Порядок — по created_at (колонка есть в `material_chunks`), внутри
        одного батча created_at совпадает, поэтому добавляем chunk_id как
        вторичный ключ: детерминированный порядок вместо произвольного.
        """
        await self.connect()
        sql = (
            "SELECT chunk_id, text_chunk FROM material_chunks "
            "WHERE material_id::text = $1 ORDER BY created_at, chunk_id"
        )
        args: list = [material_id]
        if limit is not None:
            sql += " LIMIT $2"
            args.append(int(limit))
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return [
            Hit(chunk_id=str(r["chunk_id"]), text=r["text_chunk"], score=0.0)
            for r in rows
        ]

    async def __len__(self) -> int:
        await self.connect()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) AS n FROM material_chunks")
        return int(row["n"])


def _to_pg_vector(v: np.ndarray) -> str:
    """numpy → строковое представление 'v1,v2,...,vn' для cast $X::vector."""
    arr = np.asarray(v, dtype=np.float32).ravel()
    return "[" + ",".join(f"{x:.7f}" for x in arr) + "]"


def _uuid5(chunk_id: str) -> uuid.UUID:
    """Строка "<material_id>:<hex>" → детерминированный UUID.

    Колонка chunk_id в БД — UUID. UUID5 даёт стабильный маппинг: повторный
    ingest того же материала перезапишет те же строки, а не заведёт дубли.
    """
    return uuid.uuid5(uuid.NAMESPACE_URL, chunk_id)


def normalize_chunk_id(raw: str) -> str:
    """chunk_id из vector store → UUID-строка для `test_questions.source_chunk_id`.

    PgVectorStore отдаёт настоящий UUID из `material_chunks` — возвращаем его
    как есть. InMemoryVectorStore отдаёт сырой ключ "<material_id>:<hex>" —
    приводим тем же UUID5, что используется при записи в Postgres, чтобы
    идентификатор был корректным UUID в обоих режимах.
    """
    try:
        return str(uuid.UUID(str(raw)))
    except (ValueError, AttributeError, TypeError):
        return str(_uuid5(str(raw)))


def _as_uuid(material_id: str) -> uuid.UUID:
    """material_id → UUID. В БД material_id — UUID, его создаёт backend."""
    try:
        return uuid.UUID(str(material_id))
    except (ValueError, AttributeError, TypeError) as e:
        raise ValueError(
            f"material_id must be a UUID (backend creates the 'materials' row): {material_id!r}"
        ) from e


# ============================================================================
#  Factory
# ============================================================================

def create_vector_store(settings: Settings | None = None) -> VectorStore:
    """Выбирает backend по `VECTOR_STORE_BACKEND`. Sync — оба конструктора
    лёгкие; PgVectorStore.connect() отложен до первого await."""
    s = settings or get_settings()
    backend = (s.vector_store_backend or "mem").lower()
    if backend == "pg":
        logger.info("Vector store backend: pgvector (Postgres)")
        return PgVectorStore(s.database_url)
    if backend == "mem":
        logger.info("Vector store backend: in-memory (lost on restart)")
        return InMemoryVectorStore()
    raise ValueError(
        f"Unknown VECTOR_STORE_BACKEND={backend!r} (expected 'mem' or 'pg')"
    )
