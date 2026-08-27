"""
Ingestion Service — orchestrates document upload, deduplication,
storage, and Redis Streams dispatch.
"""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    DuplicateDocumentError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.db.models import Document, ProcessingJob
from app.db.redis import publish_to_stream
from app.schemas import IngestResponse

logger = logging.getLogger(__name__)

# Maps file extensions to document type categories
EXTENSION_TO_DOC_TYPE: dict[str, str] = {
    "pdf": "pdf",
    "png": "image", "jpg": "image", "jpeg": "image",
    "gif": "image", "bmp": "image", "tiff": "image", "webp": "image",
    "txt": "text", "md": "markdown",
    "csv": "csv",
    "log": "log",
    "py": "code", "js": "code", "ts": "code", "go": "code",
    "java": "code", "rs": "code", "cpp": "code", "c": "code",
    "h": "code", "yaml": "code", "yml": "code",
    "json": "text", "toml": "code",
}


class IngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest_document(
        self,
        file: UploadFile,
        metadata: dict,
        tags: list[str],
        priority: int = 5,
        source_system: str = "upload",
        api_key_id: str | None = None,
    ) -> IngestResponse:
        """Full ingestion flow: validate → deduplicate → store → dispatch."""

        # ─── 1. Validate ──────────────────────────────────────
        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lstrip(".").lower()

        if ext not in settings.ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(ext)

        # ─── 2. Read & hash file ──────────────────────────────
        content = await file.read()
        file_size = len(content)

        if file_size > settings.max_file_size_bytes:
            raise FileTooLargeError(file_size / (1024 * 1024), settings.MAX_FILE_SIZE_MB)

        file_hash = hashlib.sha256(content).hexdigest()

        # ─── 3. Deduplication check ───────────────────────────
        existing = await self.db.execute(
            select(Document).where(Document.file_hash == file_hash)
        )
        existing_doc = existing.scalar_one_or_none()
        if existing_doc:
            # Return existing document info instead of re-processing
            job_result = await self.db.execute(
                select(ProcessingJob).where(
                    ProcessingJob.document_id == existing_doc.id
                ).order_by(ProcessingJob.queued_at.desc())
            )
            existing_job = job_result.scalars().first()
            return IngestResponse(
                job_id=existing_job.id if existing_job else str(uuid.uuid4()),
                document_id=existing_doc.id,
                status=existing_doc.status,
                filename=filename,
                file_size_bytes=file_size,
                message="Document already exists — returning existing record",
            )

        # ─── 4. Store raw file ────────────────────────────────
        document_id = str(uuid.uuid4())
        safe_filename = f"{document_id}.{ext}"
        raw_path = Path(settings.RAW_FILES_PATH) / safe_filename
        raw_path.parent.mkdir(parents=True, exist_ok=True)

        with open(raw_path, "wb") as f:
            f.write(content)

        doc_type = EXTENSION_TO_DOC_TYPE.get(ext, "text")
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # ─── 5. Create document record ────────────────────────
        document = Document(
            id=document_id,
            filename=safe_filename,
            original_name=filename,
            doc_type=doc_type,
            status="QUEUED",
            file_path=str(raw_path),
            file_size_bytes=file_size,
            file_hash=file_hash,
            mime_type=mime_type,
            metadata_=metadata,
            tags=tags if tags else None,
            source_system=source_system,
        )
        self.db.add(document)

        # ─── 6. Create processing job ─────────────────────────
        job_id = str(uuid.uuid4())
        job = ProcessingJob(
            id=job_id,
            document_id=document_id,
            job_type="document_processing",
            status="PENDING",
            priority=priority,
            input_payload={
                "document_id": document_id,
                "file_path": str(raw_path),
                "file_type": doc_type,
                "filename": filename,
                "ext": ext,
            },
        )
        self.db.add(job)
        await self.db.commit()

        # ─── 7. Publish to Redis Stream ───────────────────────
        try:
            await publish_to_stream(
                settings.STREAM_INGEST,
                {
                    "job_id": job_id,
                    "document_id": document_id,
                    "file_path": str(raw_path),
                    "file_type": doc_type,
                    "filename": filename,
                    "ext": ext,
                    "priority": str(priority),
                    "source_system": source_system,
                },
            )
            logger.info(
                "Document queued for ingestion",
                extra={"document_id": document_id, "job_id": job_id, "filename": filename},
            )
        except Exception as e:
            logger.error(f"Failed to publish to stream: {e}")
            # Job is still in DB — worker will pick it up on retry

        # Estimate processing time based on file size and type
        estimated_seconds = self._estimate_duration(doc_type, file_size)

        return IngestResponse(
            job_id=job_id,
            document_id=document_id,
            status="QUEUED",
            filename=filename,
            file_size_bytes=file_size,
            estimated_duration_seconds=estimated_seconds,
        )

    @staticmethod
    def _estimate_duration(doc_type: str, file_size: int) -> int:
        """Rough duration estimate in seconds."""
        base = {
            "pdf": 30, "image": 20, "csv": 10,
            "text": 5, "markdown": 5, "code": 10, "log": 15,
        }
        size_factor = max(1, file_size // (1024 * 1024))  # per MB
        return base.get(doc_type, 15) * size_factor
