from loguru import logger

_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]
_MAX_RECURSIVE_LEN = 800


def _split_once(text: str, sep: str) -> list[str]:
    if sep == "":
        return list(text)
    return [p for p in text.split(sep) if p]


def _split_recursive(text: str, seps: list[str]) -> list[str]:
    if not seps or len(text) <= _MAX_RECURSIVE_LEN:
        return [text]
    sep = seps[0]
    parts = _split_once(text, sep) if sep else list(text)
    result: list[str] = []
    for p in parts:
        if len(p) <= _MAX_RECURSIVE_LEN:
            result.append(p)
        else:
            result.extend(_split_recursive(p, seps[1:]))
    return result


def _merge_with_overlap(pieces: list[str], chunk_size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if len(current) + len(piece) + 1 > chunk_size and current:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap > 0 and len(current) > overlap else ""
            current = (tail + " " + piece).strip()
        else:
            current = (current + " " + piece).strip() if current else piece
    if current:
        chunks.append(current.strip())
    logger.info(f"Chunked text into {len(chunks)} chunks (size={chunk_size}, overlap={overlap})")
    return chunks


def split_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """
    Recursive text splitter.
    Tries \n\n -> \n -> '. ' -> ' ' -> '' until each piece fits in chunk_size.
    Adjacent small pieces are merged; overlap is added between merged chunks.
    """
    if not text or not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]
    pieces = _split_recursive(text, _SEPARATORS)
    return _merge_with_overlap(pieces, chunk_size, overlap)