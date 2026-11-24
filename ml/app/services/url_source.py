"""URL → article-text fetcher.

Один путь, без регистрации в `parsers/registry` (URL не имеет расширения),
но с тем же контрактом `async def fetch_and_extract_url(url) -> str` —
вызывается из `app/parsers/base.py::download_and_extract`, если ключ
начинается с http:// или https://.

Используется `trafilatura` — он умеет отделять основной текст статьи от
навигации/комментариев/футера и принимает HTML в bytes.
"""
from __future__ import annotations

import asyncio

import httpx

from app.core.config import Settings, get_settings


async def fetch_and_extract_url(url: str, settings: Settings | None = None) -> str:
    """Fetch URL HTML in a thread (httpx sync client) + extract article text."""
    s = settings or get_settings()

    def _do() -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept-Language": "ru,en;q=0.8",
        }
        with httpx.Client(
            follow_redirects=True,
            timeout=20.0,
            headers=headers,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text

        import trafilatura
        from loguru import logger

        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        ) or ""
        logger.info(f"Fetched & extracted {len(text)} chars from {url}")
        return text

    return await asyncio.to_thread(_do)
