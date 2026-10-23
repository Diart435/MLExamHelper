import io
from pathlib import Path

from loguru import logger
from pypdf import PdfReader

from app.parsers.base import ParseError


def parse(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as e:
        raise ParseError(f"pdf: cannot read document: {e}") from e

    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
        else:
            logger.warning(f"PDF page {i} extracted as empty text")
    return "\n\n".join(parts)


def extract_text(pdf_path: str | Path) -> str:
    """Разобрать локальный PDF-файл. Нужен для тестов и ноутбуков."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    full = parse(path.read_bytes())
    logger.info(f"Extracted {len(full)} chars from {path.name}")
    return full