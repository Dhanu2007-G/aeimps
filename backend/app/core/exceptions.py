"""Custom exception hierarchy for AEIMPS."""
from __future__ import annotations

from fastapi import HTTPException, status


class AEIMPSError(Exception):
    """Base exception for all AEIMPS errors."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", details: dict | None = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


# ─── Ingestion Errors ────────────────────────────────────────
class DocumentNotFoundError(AEIMPSError):
    def __init__(self, document_id: str):
        super().__init__(f"Document not found: {document_id}", "DOCUMENT_NOT_FOUND")


class DuplicateDocumentError(AEIMPSError):
    def __init__(self, file_hash: str, existing_id: str):
        super().__init__(
            f"Document already exists: {existing_id}",
            "DUPLICATE_DOCUMENT",
            {"existing_document_id": existing_id, "file_hash": file_hash},
        )


class FileTooLargeError(AEIMPSError):
    def __init__(self, size_mb: float, max_mb: int):
        super().__init__(
            f"File size {size_mb:.1f}MB exceeds maximum {max_mb}MB",
            "FILE_TOO_LARGE",
        )


class UnsupportedFileTypeError(AEIMPSError):
    def __init__(self, extension: str):
        super().__init__(f"Unsupported file type: .{extension}", "UNSUPPORTED_FILE_TYPE")


class ProcessingError(AEIMPSError):
    def __init__(self, message: str, job_id: str | None = None):
        super().__init__(message, "PROCESSING_ERROR", {"job_id": job_id})


# ─── Retrieval Errors ────────────────────────────────────────
class RetrievalError(AEIMPSError):
    def __init__(self, message: str):
        super().__init__(message, "RETRIEVAL_ERROR")


class ChunkNotFoundError(AEIMPSError):
    def __init__(self, chunk_id: str):
        super().__init__(f"Chunk not found: {chunk_id}", "CHUNK_NOT_FOUND")


# ─── Agent Errors ────────────────────────────────────────────
class AgentSessionNotFoundError(AEIMPSError):
    def __init__(self, session_id: str):
        super().__init__(f"Agent session not found: {session_id}", "SESSION_NOT_FOUND")


class AgentTimeoutError(AEIMPSError):
    def __init__(self, session_id: str):
        super().__init__(f"Agent session timed out: {session_id}", "SESSION_TIMEOUT")


class LLMError(AEIMPSError):
    def __init__(self, message: str):
        super().__init__(message, "LLM_ERROR")


# ─── Auth Errors ─────────────────────────────────────────────
class InvalidAPIKeyError(AEIMPSError):
    def __init__(self):
        super().__init__("Invalid or missing API key", "INVALID_API_KEY")


class RateLimitExceededError(AEIMPSError):
    def __init__(self, limit: int, window: int):
        super().__init__(
            f"Rate limit exceeded: {limit} requests per {window}s",
            "RATE_LIMIT_EXCEEDED",
            {"limit": limit, "window_seconds": window},
        )


# ─── HTTP Exception Mapping ──────────────────────────────────
def to_http_exception(error: AEIMPSError) -> HTTPException:
    mapping = {
        "DOCUMENT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "CHUNK_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "SESSION_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "DUPLICATE_DOCUMENT": status.HTTP_409_CONFLICT,
        "FILE_TOO_LARGE": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        "UNSUPPORTED_FILE_TYPE": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        "INVALID_API_KEY": status.HTTP_401_UNAUTHORIZED,
        "RATE_LIMIT_EXCEEDED": status.HTTP_429_TOO_MANY_REQUESTS,
        "LLM_ERROR": status.HTTP_503_SERVICE_UNAVAILABLE,
    }
    status_code = mapping.get(error.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": error.code, "message": error.message, "details": error.details}},
    )
