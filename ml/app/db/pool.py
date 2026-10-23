"""Ленивый общий asyncpg-пул на процесс.

Пул создаётся при первом обращении, потому что настройки читаются лениво, а в
юнит-тестах БД может не быть вовсе — тогда пул просто не создастся.
"""

from __future__ import annotations

import json

import asyncpg

from app.core.config import get_settings

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """По умолчанию asyncpg отдаёт jsonb строкой — переучиваем на dict,
    иначе options и answer_key пришлось бы парсить вручную в каждом месте."""
    for typename in ("json", "jsonb"):
        await conn.set_type_codec(
            typename, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=s.database_url,
            min_size=s.db_pool_min_size,
            max_size=s.db_pool_max_size,
            init=_init_connection,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def to_vector(embedding: list[float]) -> str:
    """asyncpg не знает тип vector — отдаём литерал '[0.1,0.2,...]' и кастуем в SQL."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"