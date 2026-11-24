"""Tests for DOCX and PPTX parsers.

Fixtures create sample files in tmp_path programmatically — keeps the repo
clean and avoids committing binary fixtures. Verifies that paragraphs,
table cells, and slide notes are extracted.
"""
from pathlib import Path

import pytest

from app.parsers.docx import DocxParser
from app.parsers.pptx import PptxParser


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    from docx import Document
    p = tmp_path / "sample.docx"
    doc = Document()
    doc.add_paragraph("Первый параграф документа.")
    doc.add_paragraph("Второй параграф с таблицей ниже.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Ячейка A1"
    table.cell(0, 1).text = "Ячейка A2"
    table.cell(1, 0).text = "Ячейка B1"
    table.cell(1, 1).text = "Ячейка B2"
    doc.save(str(p))
    return p


@pytest.fixture
def sample_pptx(tmp_path: Path) -> Path:
    from pptx import Presentation
    from pptx.util import Inches
    p = tmp_path / "sample.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])  # title slide layout
    slide.shapes.title.text = "Заголовок презентации"
    slide.placeholders[1].text = "Подзаголовок"

    slide2 = prs.slides.add_slide(prs.slide_layouts[1])
    slide2.shapes.title.text = "Второй слайд"
    notes_tf = slide2.notes_slide.notes_text_frame
    notes_tf.text = "Это заметки спикера ко второму слайду"

    prs.save(str(p))
    return p


def test_docx_extracts_paragraphs_and_table_cells(sample_docx: Path):
    data = sample_docx.read_bytes()
    out = DocxParser().extract(data, source="sample.docx")

    assert "Первый параграф документа." in out
    assert "Второй параграф с таблицей ниже." in out
    assert "Ячейка A1" in out
    assert "Ячейка B2" in out


def test_docx_skips_blank_paragraphs(sample_docx: Path):
    from docx import Document
    p2 = sample_docx.parent / "with_blanks.docx"
    doc = Document()
    doc.add_paragraph("Видимый текст")
    doc.add_paragraph("")
    doc.add_paragraph("   ")
    doc.add_paragraph("Ещё видимый")
    doc.save(str(p2))
    out = DocxParser().extract(p2.read_bytes(), source="with_blanks.docx")
    assert "Видимый текст" in out
    assert "Ещё видимый" in out


def test_pptx_extracts_slide_titles_and_notes(sample_pptx: Path):
    data = sample_pptx.read_bytes()
    out = PptxParser().extract(data, source="sample.pptx")

    assert "[Слайд 1]" in out
    assert "[Слайд 2]" in out
    assert "Заголовок презентации" in out
    assert "Второй слайд" in out
    assert "заметки спикера" in out


def test_pptx_empty_presentation(tmp_path: Path):
    from pptx import Presentation
    p = tmp_path / "empty.pptx"
    Presentation().save(str(p))
    out = PptxParser().extract(p.read_bytes(), source="empty.pptx")
    assert out == ""