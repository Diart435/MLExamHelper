"""Plain-text parser. UTF-8 with replacement for stray bytes."""
from __future__ import annotations


class TextParser:
    extensions = (".txt",)

    def extract(self, data: bytes, *, source: str) -> str:
        return data.decode("utf-8", errors="replace")