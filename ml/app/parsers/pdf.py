from pathlib import Path
import asyncio
import io

from loguru import logger
from pypdf import PdfReader

from app.core.config import Settings, get_settings
from app.core.minio_client import get_minio


def _read_pages(data: bytes, source: str) -> str:
    """Internal: parse PDF bytes into text. Logs a warning per empty page."""
    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
        else:
            logger.warning(f"Page {i} extracted empty text from {source}")
    return "\n\n".join(parts)


def extract_text(pdf_path: str | Path) -> str:
    """Extract plain text from a local PDF file. Raises FileNotFoundError if missing."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    data = path.read_bytes()
    full = _read_pages(data, str(path))
    logger.info(f"Extracted {len(full)} chars from {path.name}")
    return full


async def download_and_extract(
    storage_key: str, settings: Settings | None = None
) -> str:
    """Download PDF from MinIO by storage_key, parse to text. Wraps sync I/O in to_thread."""
    s = settings or get_settings()
    bucket = s.minio_bucket

    def _download_and_parse() -> str:
        client = get_minio(s)
        try:
            response = client.get_object(bucket, storage_key)
        except Exception as e:
            raise FileNotFoundError(
                f"Object '{storage_key}' not found in bucket '{bucket}': {e}"
            ) from e
        try:
            data = response.read()
        finally:
            response.close()
            response.release_conn()
        full = _read_pages(data, f"{bucket}/{storage_key}")
        logger.info(f"Downloaded & extracted {len(full)} chars from {bucket}/{storage_key}")
        return full

    # minio-py is sync; offload to a thread to avoid blocking the event loop
    return await asyncio.to_thread(_download_and_parse)
