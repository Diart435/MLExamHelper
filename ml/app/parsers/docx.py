"""DOCX parser via `python-docx`."""
from __future__ import annotations

import io


class DocxParser:
    extensions = (".docx",)

    def extract(self, data: bytes, *, source: str) -> str:
        from docx import Document
        doc = Document(io.BytesIO(data))
        parts: list[str] = [
            p.text for p in doc.paragraphs if p.text and p.text.strip()
        ]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text and cell.text.strip():
                        parts.append(cell.text)
        return "\n\n".join(parts)