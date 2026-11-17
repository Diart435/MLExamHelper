"""Parser registry: dispatches by file extension (case-insensitive).

Parsers self-register at import time (see bottom of this file). Anywhere in
the codebase that needs to ingest a file calls `registry.get_parser(key)` and
gets back a `Parser` instance bound to that format.
"""
from __future__ import annotations

from pathlib import Path

from app.parsers.base import Parser, UnsupportedFormatError

_PARSERS: dict[str, Parser] = {}


def register(parser: Parser) -> None:
    for ext in parser.extensions:
        _PARSERS[ext.lower()] = parser


def get_parser(storage_key: str) -> Parser:
    ext = Path(storage_key).suffix.lower()
    if ext not in _PARSERS:
        raise UnsupportedFormatError(
            f"{ext or '<no extension>'} (from {storage_key!r}); "
            f"supported: {sorted(_PARSERS)}"
        )
    return _PARSERS[ext]


def supported_extensions() -> list[str]:
    return sorted(_PARSERS)


# === self-registration on import ===
# Importing the modules is the registration trigger. Keep these at the bottom
# so all functions above are defined before any parser code runs.
from app.parsers.pdf import PdfParser          # noqa: E402
from app.parsers.text import TextParser        # noqa: E402
from app.parsers.markdown import MarkdownParser # noqa: E402
from app.parsers.docx import DocxParser        # noqa: E402
from app.parsers.pptx import PptxParser        # noqa: E402
from app.parsers.audio import AudioParser      # noqa: E402
from app.parsers.video import VideoParser      # noqa: E402

for _p in (
    PdfParser(),
    TextParser(),
    MarkdownParser(),
    DocxParser(),
    PptxParser(),
    AudioParser(),
    VideoParser(),
):
    register(_p)