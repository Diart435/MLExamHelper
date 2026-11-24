"""Parser Protocol + common async helper for download + extract.

Each format-specific parser implements `Parser.extract(data: bytes, source: str) -> str`
operating on already-downloaded bytes. The async helper `download_and_extract`
downloads bytes via `app.services.storage.fetch_bytes` (MinIO / local fallback)
and dispatches to the correct parser through `app.parsers.registry`.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol

from app.services.storage import fetch_bytes


class UnsupportedFormatError(Exception):
    """Raised when `storage_key` has an unknown / missing extension."""


@dataclass
class ParsedDocument:
    """Future-proof container for parser output.

    For now only `text` is consumed by chunker; `meta` is reserved for
    page/slide/timestamp metadata that may improve retrieval later.
    """
    text: str
    meta: dict = field(default_factory=dict)


class Parser(Protocol):
    """Protocol every format parser implements.

    `extract` is intentionally sync and pure — it operates on bytes already
    loaded by `fetch_bytes`. The async wrapper `download_and_extract` (below)
    offloads it to a thread so event-loop friendly.
    """
    extensions: tuple[str, ...]

    def extract(self, data: bytes, *, source: str) -> str: ...


async def download_and_extract(
    storage_key: str, settings=None
) -> str:
    """Async helper: download bytes, then dispatch to the right parser.

    Three branches:
      - URL (http:// or https://) → fetch + extract via `app.services.url_source`
        (no registry/extension involvement — URLs don't have extensions).
      - local file or MinIO key with known extension → registry lookup.
      - unknown extension → `UnsupportedFormatError` before any I/O.

    Raises `UnsupportedFormatError` if the extension is unknown.
    Raises `FileNotFoundError` if the object is missing in MinIO / on disk.
    Raises `httpx.HTTPError` on URL transport failures.
    """
    if storage_key.startswith(("http://", "https://")):
        from app.services.url_source import fetch_and_extract_url
        return await fetch_and_extract_url(storage_key, settings)

    from app.parsers import registry  # late import: registry registers on its own import
    parser = registry.get_parser(storage_key)
    data = await fetch_bytes(storage_key, settings)
    return await asyncio.to_thread(parser.extract, data, source=storage_key)