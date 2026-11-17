"""Public API for the parsers package.

Importing this package triggers parser registration (side-effect in
`registry`). Callers should reach for:

    from app.parsers.base import download_and_extract, UnsupportedFormatError
    from app.parsers import registry
"""
from app.parsers.base import (
    ParsedDocument,
    Parser,
    UnsupportedFormatError,
    download_and_extract,
)
from app.parsers import registry  # noqa: F401  (side-effect: registers parsers)

__all__ = [
    "Parser",
    "ParsedDocument",
    "UnsupportedFormatError",
    "download_and_extract",
    "registry",
]