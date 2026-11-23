"""Обвязка для тестов против живых сервисов — вместо моков.

Зачем: тесты, которые бьют по настоящему Redis/Postgres/LLM, ловят реальные
ошибки (кодеки asyncpg, семантику consumer-групп, формат ответа провайдера),
которые фейки не воспроизводят.

Правила обвязки:

* **Пропуск вместо падения.** Если сервис недоступен — `pytest.skip`, а не
  ошибка. Иначе прогон в окружении без Docker падал бы на импорте.
* **Изоляция.** Redis — на **БД 15** (`redis://localhost:6379/15`): consumer-группы
  привязаны к БД, поэтому тестовые группы не задевают прод-каналы в БД 0.
* **Явный DSN.** Тесты бьют по `TEST_REDIS_URL` / `TEST_DATABASE_URL`, а не по
  рабочим `REDIS_URL` / `DATABASE_URL`: иначе тест по ошибке снесёт прод-данные.

Фикстуры:

| фикстура | что даёт |
|---|---|
| `live_redis` | клиент Redis на БД 15 (json в тексте) |
| `live_pg` | пул asyncpg + тестовая схема `test_questions` |
| `live_llm` | настоящий `LLMClient` (провайдер LLM) |

Маркеры: `integration` (живые Redis/Postgres), `llm` (живой провайдер),
`network` (внешний HTTP).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# БД 15 — изолированная от рабочей БД 0, где живут прод-каналы.
DEFAULT_TEST_REDIS_URL = "redis://localhost:6379/15"
DEFAULT_TEST_DATABASE_URL = "postgresql://ml:ml@localhost:5432/ml_test"

SCHEMA_FILE = Path(__file__).parent / "_fixtures" / "test_schema.sql"


def test_redis_url() -> str:
    """Redis для тестов: `TEST_REDIS_URL` или изолированная БД 15."""
    return os.environ.get("TEST_REDIS_URL", DEFAULT_TEST_REDIS_URL)


def test_database_url() -> str:
    """Postgres для тестов: `TEST_DATABASE_URL` или отдельная база `ml_test`."""
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


@pytest.fixture
async def live_redis():
    """Живой Redis. Недоступен — skip.

    Клиент отдаёт строки, а не bytes: в коде ML все команды работают со
    строками (`payload`, `xreadgroup`), и `decode_responses=True` это отражает.
    """
    from redis.asyncio import Redis

    url = test_redis_url()
    client = Redis.from_url(url, decode_responses=True)
    try:
        await client.ping()
    except Exception as e:
        await client.aclose()
        pytest.skip(f"redis not available at {url}: {type(e).__name__}: {e}")

    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def live_pg():
    """Живой Postgres с тестовой схемой `test_questions`.

    Таблица создаётся, если её нет (см. `tests/_fixtures/test_schema.sql`).
    Строки чистятся только в базе, в имени которой есть "test" — указав
    `TEST_DATABASE_URL` на рабочую базу, тест ничего в ней не удалит.
    """
    import asyncpg

    from app.core.db import install_json_codecs

    url = test_database_url()
    try:
        pool = await asyncpg.create_pool(
            url, min_size=1, max_size=4, init=install_json_codecs,
        )
    except Exception as e:
        pytest.skip(f"postgres not available at {url}: {type(e).__name__}: {e}")

    try:
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
            db_name = await conn.fetchval("SELECT current_database()")
            if "test" in db_name.lower():
                await conn.execute("DELETE FROM test_questions")
            else:
                pytest.fail(
                    f"TEST_DATABASE_URL указывает на не-тестовую базу {db_name!r} — "
                    f"чистка test_questions отключена, укажите базу с 'test' в имени"
                )
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def live_llm():
    """Настоящий LLM-клиент (провайдер LLM). Без ключа/кредита — skip.

    `LLMClient` читает настройки через `Settings`, который берёт ключ из env
    или из `.env`; если ключа нет — конструктор падает, и это повод пропустить
    тест, а не уронить прогон.
    """
    from app.services.llm import LLMClient

    try:
        client = LLMClient()
    except Exception as e:
        pytest.skip(f"LLM client unavailable: {type(e).__name__}: {e}")

    yield client
