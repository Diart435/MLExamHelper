import sys
from typing import IO

from loguru import logger

from app.core.config import get_settings


class _SafeStderr:
    """stderr, который не теряет строки из-за кодировки.

    Подробные логи содержат русский текст и стрелки «→»/«←». Если у stderr
    не-UTF-8 кодировка (например, cp1251 в Windows-консоли), запись такой
    строки упала бы с UnicodeEncodeError — и loguru молча потерял бы строку
    целиком. Здесь непечатаемые символы заменяются на «?», и строка доходит
    до лога целиком.

    В Docker (python:3.12-slim, LANG=C.UTF-8) кодировка UTF-8, поэтому это
    обёртка ничего не меняет — она страхует других окружений.
    """

    def __init__(self, stream: IO[str]) -> None:
        self._stream = stream

    def write(self, message: str) -> int:
        try:
            return self._stream.write(message)
        except UnicodeEncodeError:
            encoding = getattr(self._stream, "encoding", None) or "ascii"
            safe = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
            return self._stream.write(safe)

    def flush(self) -> None:
        try:
            self._stream.flush()
        except Exception:
            pass

    def __getattr__(self, name):  # noqa: D105 — проксируем остальное (isatty и т.п.)
        return getattr(self._stream, name)


def setup_logging() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(
        _SafeStderr(sys.stderr),
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
