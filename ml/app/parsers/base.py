from typing import Protocol


class ParseError(ValueError):
    """Файл не удалось разобрать, либо формат не поддерживается."""


class Parser(Protocol):
    def __call__(self, data: bytes) -> str: ...