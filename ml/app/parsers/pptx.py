"""PPTX parser via `python-pptx`.

Each slide's text is prefixed with `[Слайд N]`. Speaker notes (if any) are
appended to the slide's text — they often carry the actual lecture content.
"""
from __future__ import annotations

import io


class PptxParser:
    extensions = (".pptx",)

    def extract(self, data: bytes, *, source: str) -> str:
        from pptx import Presentation
        prs = Presentation(io.BytesIO(data))
        parts: list[str] = []
        for i, slide in enumerate(prs.slides, 1):
            slide_texts = [
                sh.text_frame.text
                for sh in slide.shapes
                if sh.has_text_frame and sh.text_frame.text.strip()
            ]
            block = "\n".join(slide_texts)
            notes = (
                slide.notes_slide.notes_text_frame.text.strip()
                if slide.has_notes_slide
                else ""
            )
            if notes:
                block = (block + "\n" + notes).strip()
            parts.append(f"[Слайд {i}]\n{block}")
        return "\n\n".join(parts)