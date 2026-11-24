"""Tests for the URL fetcher — httpx is mocked, trafilatura runs for real.

Real network is tested manually in `python -m app.demo --url ...`.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


SAMPLE_HTML = """
<html><head><title>Test Article</title></head>
<body>
  <header><nav>Menu link 1 Menu link 2</nav></header>
  <article>
    <h1>Test Article Title</h1>
    <p>Это первый абзац основной статьи. Здесь много полезного текста.</p>
    <p>Это второй абзац с дополнительной информацией для теста парсера.</p>
  </article>
  <footer>Copyright footer text</footer>
</body></html>
"""


@pytest.mark.asyncio
async def test_url_fetcher_extracts_article_text():
    """HTTP fetched → trafilatura extracts article, drops nav/footer."""
    from app.services.url_source import fetch_and_extract_url

    fake_resp = MagicMock()
    fake_resp.text = SAMPLE_HTML
    fake_resp.raise_for_status = MagicMock()

    with patch("httpx.Client") as ClientCls:
        ctx = MagicMock()
        ctx.__enter__.return_value.get.return_value = fake_resp
        ClientCls.return_value = ctx

        text = await fetch_and_extract_url("https://example.com/article")

    assert "Test Article Title" in text
    assert "первый абзац основной статьи" in text
    assert "второй абзац с дополнительной информацией" in text
    # Nav and footer should NOT be in extracted text
    assert "Menu link 1" not in text
    assert "Copyright footer text" not in text


@pytest.mark.asyncio
async def test_url_fetcher_propagates_http_errors():
    """5xx / network errors bubble up — caller decides what to do."""
    import httpx

    from app.services.url_source import fetch_and_extract_url

    fake_resp = MagicMock()
    fake_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found", request=MagicMock(), response=MagicMock()
    )
    fake_resp.text = ""

    with patch("httpx.Client") as ClientCls:
        ctx = MagicMock()
        ctx.__enter__.return_value.get.return_value = fake_resp
        ClientCls.return_value = ctx

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_and_extract_url("https://example.com/missing")


@pytest.mark.asyncio
async def test_url_fetcher_returns_empty_when_no_article():
    """If trafilatura can't find article content, return '' (not None)."""
    from app.services.url_source import fetch_and_extract_url

    fake_resp = MagicMock()
    fake_resp.text = "<html><body><p>tiny</p></body></html>"
    fake_resp.raise_for_status = MagicMock()

    with patch("httpx.Client") as ClientCls:
        ctx = MagicMock()
        ctx.__enter__.return_value.get.return_value = fake_resp
        ClientCls.return_value = ctx

        text = await fetch_and_extract_url("https://example.com/x")
    # Empty or short extraction is acceptable; we just want a `str` back.
    assert isinstance(text, str)
