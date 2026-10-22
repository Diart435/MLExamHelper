import io

from docx import Document

from app.parsers.base import ParseError


def parse(data: bytes) -> str:
    try:
        doc = Document(io.BytesIO(data))
    except Exception as e:
        raise ParseError(f"docx: cannot read document: {e}") from e
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())