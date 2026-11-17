"""Markdown parser. Strips markup (`#`, `**`, backticks, links) → plain text.

Why strip? Embeddings are trained on natural language; markdown syntax
characters hurt retrieval. Headings still surface as standalone paragraphs
because the bs4 stripper keeps block-level newlines.
"""
from __future__ import annotations

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt


class MarkdownParser:
    extensions = (".md", ".markdown")

    def extract(self, data: bytes, *, source: str) -> str:
        raw = data.decode("utf-8", errors="replace")
        # markdown-it-py is already a transitive dep; MD → HTML → plain text.
        html = MarkdownIt().render(raw)
        return BeautifulSoup(html, "html.parser").get_text("\n")