"""Tests for plain-text and markdown parsers."""
from pathlib import Path

import pytest

from app.parsers.markdown import MarkdownParser
from app.parsers.text import TextParser

FIXTURES = Path(__file__).resolve().parent.parent / "_fixtures"


def test_text_parser_strips_to_plain_text():
    data = (FIXTURES / "notes.txt").read_bytes()
    out = TextParser().extract(data, source="notes.txt")
    assert "Просто текстовая заметка." in out
    assert "Вторая строка заметки." in out
    assert "Третья строка." in out


def test_text_parser_handles_bad_utf8_with_replace():
    # Latin-1 "привет" encoded in bytes — invalid UTF-8 sequence.
    data = b"\xff\xfe bad bytes \xc3\x28"
    out = TextParser().extract(data, source="bad.txt")
    # We don't care about the exact replacement char, only that no exception.
    assert isinstance(out, str)
    assert "bad bytes" in out


def test_markdown_parser_strips_markup():
    data = (FIXTURES / "notes.md").read_bytes()
    out = MarkdownParser().extract(data, source="notes.md")

    # Expected content present
    assert "Заголовок заметки" in out
    assert "жирный текст" in out
    assert "курсив" in out
    assert "Пункт 1" in out
    assert "Пункт 2" in out
    assert "Ссылка куда-то" in out
    # Code block content preserved
    assert 'print("hello")' in out

    # Markdown syntax stripped
    assert "#" not in out
    assert "**" not in out
    assert "_" not in out  # italic markers
    assert "```" not in out
    assert "[Ссылка куда-то](https://example.com)" not in out


@pytest.mark.parametrize("bad_bytes", [b"", b"\x00\x01\x02"])
def test_text_parser_returns_empty_or_replaced(bad_bytes):
    out = TextParser().extract(bad_bytes, source="x.txt")
    assert isinstance(out, str)