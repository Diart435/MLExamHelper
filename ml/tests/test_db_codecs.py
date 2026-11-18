"""Тесты codec'ов json/jsonb для asyncpg (`app/core/db.py`).

Что защищаем
============
Без codec'а asyncpg отдаёт json/jsonb **строкой** с JSON-текстом. Прикладной
код получал `str` вместо `dict`/`list` и трактовал JSON-документ как строку —
например, `key_points` `'["пункт 1"]'` давал `kp[0] == "["` (студенту уходил
ответ «[» вместо первого критерия).

Поэтому:
  - codec ставится на **каждое** соединение (модульной функции
    `asyncpg.set_type_codec` не существует) — значит, пулы создаются с
    `init=install_json_codecs`;
  - `schema='pg_catalog'` обязателен: json/jsonb живут в pg_catalog, дефолт
    `public` не сработает;
  - encoder не двоит кодирование: нативный объект → JSON-текст ровно один раз.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.core.db import install_json_codecs
from app.services.test_store import TestStore
from app.services.vector_store import PgVectorStore


class FakeConn:
    """Соединение asyncpg: записывает вызовы `set_type_codec`."""

    def __init__(self) -> None:
        self.codecs: list[dict[str, Any]] = []

    async def set_type_codec(self, typename: str, **kwargs: Any) -> None:
        self.codecs.append({"typename": typename, **kwargs})


class FakeAsyncpg:
    """Подмена модуля asyncpg: `create_pool` возвращает заглушку пула."""

    def __init__(self) -> None:
        self.pool_kwargs: list[dict[str, Any]] = []

    async def create_pool(self, dsn: str, **kwargs: Any) -> Any:
        self.pool_kwargs.append({"dsn": dsn, **kwargs})
        return object()


# ---------------------------------------------------------------------------
# install_json_codecs
# ---------------------------------------------------------------------------

class TestInstallJsonCodecs:
    @pytest.mark.asyncio
    async def test_registers_json_and_jsonb(self):
        conn = FakeConn()
        await install_json_codecs(conn)
        assert [c["typename"] for c in conn.codecs] == ["json", "jsonb"]

    @pytest.mark.asyncio
    async def test_uses_pg_catalog_schema(self):
        """json/jsonb живут в pg_catalog — дефолт `public` не сработает."""
        conn = FakeConn()
        await install_json_codecs(conn)
        for codec in conn.codecs:
            assert codec["schema"] == "pg_catalog"

    @pytest.mark.asyncio
    async def test_decoder_is_json_loads(self):
        conn = FakeConn()
        await install_json_codecs(conn)
        for codec in conn.codecs:
            assert codec["decoder"] is json.loads
            assert codec["format"] == "text"

    @pytest.mark.asyncio
    async def test_encoder_does_not_double_encode(self):
        """Encoder должен отдать ровно один JSON-уровень.

        Готовый `json.dumps` на входе дал бы в БД JSON-строку вместо объекта —
        ровно тот дефект, который эта правка устраняет."""
        conn = FakeConn()
        await install_json_codecs(conn)
        encoder = conn.codecs[0]["encoder"]
        assert json.loads(encoder({"a": 1})) == {"a": 1}
        assert json.loads(encoder(["пункт 1"])) == ["пункт 1"]

    @pytest.mark.asyncio
    async def test_encoder_keeps_cyrillic_readable(self):
        """ensure_ascii=False — русский текст в БД остаётся читаемым."""
        conn = FakeConn()
        await install_json_codecs(conn)
        encoder = conn.codecs[0]["encoder"]
        assert "пункт" in encoder({"points": ["пункт 1"]})
        assert json.loads(encoder("текст")) == "текст"


# ---------------------------------------------------------------------------
# Пулы создаются с init=install_json_codecs
# ---------------------------------------------------------------------------

class TestPoolsUseCodecs:
    @pytest.mark.asyncio
    async def test_test_store_pool_has_init_hook(self, monkeypatch):
        fake = FakeAsyncpg()
        monkeypatch.setattr("asyncpg.create_pool", fake.create_pool)

        store = TestStore(dsn="postgresql://ml:ml@localhost:5432/ml")
        await store.connect()

        assert len(fake.pool_kwargs) == 1
        assert fake.pool_kwargs[0]["init"] is install_json_codecs

    @pytest.mark.asyncio
    async def test_pg_vector_store_pool_has_init_hook(self, monkeypatch):
        fake = FakeAsyncpg()
        monkeypatch.setattr("asyncpg.create_pool", fake.create_pool)

        store = PgVectorStore(dsn="postgresql://ml:ml@localhost:5432/ml")
        await store.connect()

        assert len(fake.pool_kwargs) == 1
        assert fake.pool_kwargs[0]["init"] is install_json_codecs
