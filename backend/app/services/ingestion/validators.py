"""File validation utilities for the ingestion service."""
from __future__ import annotations
import magic
from pathlib import Path
from app.core.config import settings
from app.core.exceptions import FileTooLargeError, UnsupportedFileTypeError

MAGIC_TO_EXT = {
    "application/pdf": "pdf",
    "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif",
    "image/webp": "webp", "image/bmp": "bmp", "image/tiff": "tiff",
    "text/plain": "txt", "text/csv": "csv", "text/markdown": "md",
    "application/json": "json",
}


def validate_file_size(size_bytes: int) -> None:
    max_bytes = settings.max_file_size_bytes
    if size_bytes > max_bytes:
        raise FileTooLargeError(size_bytes / (1024 * 1024), settings.MAX_FILE_SIZE_MB)


def validate_file_type(filename: str, content: bytes | None = None) -> str:
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        # Try magic byte detection
        if content:
            try:
                mime = magic.from_buffer(content[:2048], mime=True)
                ext = MAGIC_TO_EXT.get(mime, ext)
            except Exception:
                pass
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(ext)
    return ext
