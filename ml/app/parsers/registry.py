"""Выбор парсера по расширению файла. Единственная точка, где известно,
какие форматы вообще поддерживаются."""

from pathlib import PurePosixPath

from app.parsers import docx, pdf, pptx, text
from app.parsers.base import ParseError

PARSERS = {
    ".pdf": pdf.parse,
    ".docx": docx.parse,
    ".pptx": pptx.parse,
    ".txt": text.parse,
    ".md": text.parse,
}


def extension_of(storage_key: str) -> str:
    return PurePosixPath(storage_key).suffix.lower()


def parse(storage_key: str, data: bytes) -> str:
    """Разобрать файл по расширению его storage_key."""
    ext = extension_of(storage_key)
    parser = PARSERS.get(ext)
    if parser is None:
        supported = ", ".join(sorted(PARSERS))
        raise ParseError(f"unsupported format {ext or '(none)'!r}: expected one of {supported}")
    return parser(data)