"""Smoke-тесты для PgVectorStore. Skippable, если БД не поднята — чтобы
pytest не падал в окружениях без БД (например, CI без инфры).

Подключение — по DATABASE_URL из env, либо дефолтный localhost:5432.
Если asyncpg не сконнектился — skip'аем весь модуль.

Тесты работают с настоящей схемой backend'а: `material_chunks` с FK на
`materials`, а `materials` — на `courses`, а та — на `users`. Поэтому фикстура
заводит цепочку родителей и убирает её за собой.
"""
from __future__ import annotations

import os
import uuid

import numpy as np
import pytest
import pytest_asyncio

from app.core.config import Settings
from app.services.vector_store import PgVectorStore, _uuid5

VEC_DIM = 1536  # production dim для text-embedding-3-small

TEST_USER = uuid.UUID("00000000-0000-4000-8000-000000000001")
TEST_COURSE = uuid.UUID("00000000-0000-4000-8000-000000000002")
TEST_MATERIAL = uuid.UUID("00000000-0000-4000-8000-000000000003")
OTHER_MATERIAL = uuid.UUID("00000000-0000-4000-8000-000000000004")

MID = str(TEST_MATERIAL)
OTHER_MID = str(OTHER_MATERIAL)


def _make_dsn() -> str | None:
    return os.environ.get("DATABASE_URL") or Settings().database_url


async def _exec(store: PgVectorStore, sql: str, *args) -> None:
    async with store._pool.acquire() as conn:  # type: ignore[union-attr]
        await conn.execute(sql, *args)


async def _ensure_parents(store: PgVectorStore) -> None:
    await _exec(
        store,
        """INSERT INTO users (user_id, email, password_hash, first_name, last_name)
           VALUES ($1, 'pgvector-test@example.com', 'x', 'Pg', 'Test')
           ON CONFLICT (user_id) DO NOTHING""",
        TEST_USER,
    )
    await _exec(
        store,
        """INSERT INTO courses (course_id, owner_id, title)
           VALUES ($1, $2, 'pgvector-test') ON CONFLICT (course_id) DO NOTHING""",
        TEST_COURSE, TEST_USER,
    )
    for mid, title in ((TEST_MATERIAL, "pg-test"), (OTHER_MATERIAL, "pg-test-other")):
        await _exec(
            store,
            """INSERT INTO materials
               (material_id, course_id, type_material, title, source_uri,
                status_material, material_size)
               VALUES ($1, $2, 'file', $3, 's3://test/x', 'processing', 1)
               ON CONFLICT (material_id) DO NOTHING""",
            mid, TEST_COURSE, title,
        )


async def _delete_chunks(store: PgVectorStore) -> None:
    await _exec(store, "DELETE FROM material_chunks WHERE material_id::text = ANY($1::text[])",
                [MID, OTHER_MID])


async def _cleanup(store: PgVectorStore) -> None:
    await _delete_chunks(store)
    await _exec(store, "DELETE FROM materials WHERE material_id = ANY($1::uuid[])",
                [TEST_MATERIAL, OTHER_MATERIAL])
    await _exec(store, "DELETE FROM courses WHERE course_id = $1", TEST_COURSE)
    await _exec(store, "DELETE FROM users WHERE user_id = $1", TEST_USER)


@pytest_asyncio.fixture
async def pg_store():
    """Коннектимся; если БД недоступна — skip. Чистим за собой."""
    dsn = _make_dsn()
    store = PgVectorStore(dsn)
    try:
        await store.connect()
    except Exception as e:
        pytest.skip(f"pgvector not available at {dsn}: {type(e).__name__}: {e}")

    await _ensure_parents(store)
    await _delete_chunks(store)

    yield store

    try:
        await _cleanup(store)
    finally:
        await store.close()


def _unit_vec(dim=VEC_DIM, axis: int = 0) -> np.ndarray:
    """Генерирует unit-вектор с одной активной осью (для cosine-сравнения)."""
    v = np.zeros(dim, dtype=np.float32)
    v[axis] = 1.0
    return v


@pytest.mark.asyncio
async def test_pgvector_add_and_search(pg_store):
    await pg_store.add("test-pgstore:c1", "кот", _unit_vec(axis=0), MID)
    await pg_store.add("test-pgstore:c2", "пёс", _unit_vec(axis=1), MID)
    await pg_store.add("test-pgstore:c3", "котёнок", _unit_vec(axis=0) * 0.95 + _unit_vec(axis=1) * 0.05, MID)

    hits = await pg_store.search(_unit_vec(axis=0), top_k=2, material_id=MID)
    assert len(hits) == 2
    assert hits[0].chunk_id == str(_uuid5("test-pgstore:c1"))
    assert hits[0].text == "кот"
    assert hits[0].score > 0.99
    assert hits[1].chunk_id == str(_uuid5("test-pgstore:c3"))


@pytest.mark.asyncio
async def test_pgvector_search_filters_by_material(pg_store):
    await pg_store.add("test-pgstore:c1", "alpha", _unit_vec(axis=0), MID)
    await pg_store.add("other:c1", "бета", _unit_vec(axis=0), OTHER_MID)

    hits = await pg_store.search(_unit_vec(axis=0), top_k=10, material_id=MID)
    assert hits
    assert all(h.chunk_id != str(_uuid5("other:c1")) for h in hits)


@pytest.mark.asyncio
async def test_pgvector_has_material_and_materials_indexed(pg_store):
    await pg_store.add("test-pgstore:c1", "x", _unit_vec(axis=0), MID)
    assert await pg_store.has_material(MID) is True
    assert await pg_store.has_material("none-such") is False
    assert MID in await pg_store.materials_indexed()


@pytest.mark.asyncio
async def test_pgvector_get_chunks_returns_text(pg_store):
    await pg_store.add("test-pgstore:c1", "первый", _unit_vec(axis=0), MID)
    await pg_store.add("test-pgstore:c2", "второй", _unit_vec(axis=1), MID)

    chunks = await pg_store.get_chunks(MID)
    assert len(chunks) == 2
    assert {c.text for c in chunks} == {"первый", "второй"}


@pytest.mark.asyncio
async def test_pgvector_rejects_non_uuid_material_id(pg_store):
    with pytest.raises(ValueError, match="material_id must be a UUID"):
        await pg_store.add("test-pgstore:c1", "x", _unit_vec(axis=0), "15716")
