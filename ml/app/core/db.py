"""Подключение к Postgres с типизированным JSON.

Root cause
==========
Без codec'а asyncpg отдаёт колонки `json`/`jsonb` **Python-строкой** с
JSON-текстом, а не разобранным объектом. Прикладной код получал `str` вместо
`dict`/`list` и трактовал JSON-документ как строку: например, `key_points`
приходил как `'["пункт 1"]'`, и `kp[0]` брал первый символ — студенту уходил
ответ «[» вместо первого критерия.

`install_json_codecs` ставит codec'и на соединение: после этого json/jsonb
приходят как `dict`/`list`, а на запись передаются нативные объекты
(готовый `json.dumps` при codec'е дал бы двойное кодирование).

⚠️ Модульной функции `asyncpg.set_type_codec` не существует — codec ставится
на **каждое** соединение отдельно. Поэтому пулы создаются с
`init=install_json_codecs`: asyncpg вызывает init-хук для каждого нового
соединения и await'ит его.
"""
from __future__ import annotations

import json
from typing import Any


async def install_json_codecs(conn: Any) -> None:
    """Поставить codec'и json/jsonb: значения приходят dict/list, а не строкой."""
    for typename in ("json", "jsonb"):
        await conn.set_type_codec(
            typename,
            schema="pg_catalog",
            encoder=lambda v: json.dumps(v, ensure_ascii=False),
            decoder=json.loads,
            format="text",
        )


async def connect(dsn: str) -> Any:
    """Подключение с codec'ами — вместо голого `asyncpg.connect()`."""
    import asyncpg
    conn = await asyncpg.connect(dsn)
    await install_json_codecs(conn)
    return conn
