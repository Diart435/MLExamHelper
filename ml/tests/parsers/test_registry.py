"""Tests for the parser registry (dispatch by extension, case-insensitive, errors)."""
import pytest

from app.parsers import registry
from app.parsers.audio import AudioParser
from app.parsers.base import UnsupportedFormatError
from app.parsers.docx import DocxParser
from app.parsers.markdown import MarkdownParser
from app.parsers.pdf import PdfParser
from app.parsers.pptx import PptxParser
from app.parsers.text import TextParser
from app.parsers.video import VideoParser


@pytest.mark.parametrize(
    "storage_key, expected_cls",
    [
        ("a.pdf", PdfParser),
        ("a.PDF", PdfParser),
        ("some/path/to/lecture.pdf", PdfParser),
        ("notes.txt", TextParser),
        ("notes.md", MarkdownParser),
        ("notes.markdown", MarkdownParser),
        ("NOTES.MD", MarkdownParser),
        ("report.docx", DocxParser),
        ("slides.pptx", PptxParser),
        ("song.mp3", AudioParser),
        ("song.WAV", AudioParser),
        ("video.mp4", VideoParser),
        ("video.MOV", VideoParser),
    ],
)
def test_dispatch_by_extension(storage_key, expected_cls):
    parser = registry.get_parser(storage_key)
    assert isinstance(parser, expected_cls)


def test_unknown_extension_raises():
    with pytest.raises(UnsupportedFormatError) as exc_info:
        registry.get_parser("archive.zip")
    assert ".zip" in str(exc_info.value)
    assert "supported:" in str(exc_info.value)


def test_no_extension_raises():
    with pytest.raises(UnsupportedFormatError) as exc_info:
        registry.get_parser("README")
    assert "<no extension>" in str(exc_info.value)


def test_supported_extensions_lists_all():
    exts = registry.supported_extensions()
    # All seven core formats registered
    assert ".pdf" in exts
    assert ".txt" in exts
    assert ".md" in exts
    assert ".docx" in exts
    assert ".pptx" in exts
    assert ".mp3" in exts
    assert ".mp4" in exts