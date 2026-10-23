from app.parsers.base import ParseError


def parse(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError("text: cannot decode as utf-8 or cp1251")