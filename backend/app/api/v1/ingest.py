"""Ingestion API — document upload, job tracking, deletion."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from fastapi.responses import ORJSONResponse

from app.api.deps import CurrentAPIKey, DBSession, RateLimited
from app.schemas import (
    BatchIngestResponse,
    DocumentResponse,
    IngestResponse,
    JobListResponse,
    JobStatusResponse,
)
from app.services.ingestion.service import IngestionService

logger = logging.getLogger(__name__)
router = APIRouter()


def get_ingestion_service(db: DBSession) -> IngestionService:
    return IngestionService(db)


@router.post(
    "/document",
    response_model=IngestResponse,
    status_code=202,
    summary="Upload and ingest a document",
)
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: str = Form(default="{}"),
    tags: str = Form(default=""),
    priority: int = Form(default=5, ge=1, le=10),
    source_system: str = Form(default="upload"),
    _: RateLimited = None,
    api_key: CurrentAPIKey = None,
    db: DBSession = None,
):
    """
    Upload a document for async processing.

    Supported formats: PDF, PNG, JPG, JPEG, TXT, MD, CSV, LOG,
    PY, JS, TS, GO, JAVA, RS, YAML, JSON, TOML

    Returns a job_id to poll for processing status.
    Deduplicates by SHA-256 hash — uploading the same file twice returns
    the existing document_id.
    """
    import json
    parsed_metadata = {}
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            pass

    parsed_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    service = IngestionService(db)
    result = await service.ingest_document(
        file=file,
        metadata=parsed_metadata,
        tags=parsed_tags,
        priority=priority,
        source_system=source_system,
        api_key_id=api_key["id"],
    )
    return result


@router.post(
    "/batch",
    response_model=BatchIngestResponse,
    status_code=202,
    summary="Upload multiple documents",
)
async def ingest_batch(
    files: list[UploadFile] = File(...),
    metadata: str = Form(default="{}"),
    tags: str = Form(default=""),
    priority: int = Form(default=5),
    _: RateLimited = None,
    api_key: CurrentAPIKey = None,
    db: DBSession = None,
):
    """Ingest up to 20 documents in a single batch request."""
    if len(files) > 20:
        from fastapi import HTTPException
        raise HTTPException(400, detail="Maximum 20 files per batch")

    import json
    import uuid
    parsed_metadata = json.loads(metadata) if metadata else {}
    parsed_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    service = IngestionService(db)
    jobs = []
    for file in files:
        try:
            result = await service.ingest_document(
                file=file,
                metadata=parsed_metadata,
                tags=parsed_tags,
                priority=priority,
                source_system="batch_upload",
                api_key_id=api_key["id"],
            )
            jobs.append(result)
        except Exception as e:
            logger.error(f"Batch ingest failed for {file.filename}: {e}")

    return BatchIngestResponse(
        batch_id=str(uuid.uuid4()),
        jobs=jobs,
        total=len(jobs),
    )


@router.get(
    "/job/{job_id}",
    response_model=JobStatusResponse,
    summary="Get processing job status",
)
async def get_job_status(
    job_id: str,
    _: RateLimited = None,
    db: DBSession = None,
):
    from sqlalchemy import select
    from app.db.models import ProcessingJob

    result = await db.execute(select(ProcessingJob).where(ProcessingJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        from fastapi import HTTPException
        raise HTTPException(404, detail=f"Job not found: {job_id}")

    # Estimate progress based on status
    progress_map = {
        "PENDING": 0, "RUNNING": 25, "COMPLETED": 100, "FAILED": 0
    }

    duration_ms = None
    if job.started_at and job.completed_at:
        duration_ms = int(
            (job.completed_at - job.started_at).total_seconds() * 1000
        )

    return JobStatusResponse(
        job_id=job.id,
        document_id=job.document_id,
        job_type=job.job_type,
        status=job.status,
        progress_pct=progress_map.get(job.status, 50),
        worker_id=job.worker_id,
        attempts=job.attempts,
        error=job.error_message,
        queued_at=job.queued_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_ms=duration_ms,
    )


@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="List processing jobs",
)
async def list_jobs(
    status: str | None = Query(None),
    doc_type: str | None = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(None),
    _: RateLimited = None,
    db: DBSession = None,
):
    from sqlalchemy import select, desc
    from app.db.models import ProcessingJob

    query = select(ProcessingJob).order_by(desc(ProcessingJob.queued_at))
    if status:
        query = query.where(ProcessingJob.status == status)
    query = query.limit(limit + 1)
    if cursor:
        query = query.where(ProcessingJob.id < cursor)

    result = await db.execute(query)
    jobs = result.scalars().all()

    next_cursor = None
    if len(jobs) > limit:
        jobs = jobs[:limit]
        next_cursor = jobs[-1].id

    return JobListResponse(
        jobs=[
            JobStatusResponse(
                job_id=j.id,
                document_id=j.document_id,
                job_type=j.job_type,
                status=j.status,
                progress_pct=100 if j.status == "COMPLETED" else 0,
                worker_id=j.worker_id,
                attempts=j.attempts,
                error=j.error_message,
                queued_at=j.queued_at,
                started_at=j.started_at,
                completed_at=j.completed_at,
            )
            for j in jobs
        ],
        next_cursor=next_cursor,
        total=None,
    )


@router.get(
    "/document/{document_id}",
    response_model=DocumentResponse,
    summary="Get document details",
)
async def get_document(
    document_id: str,
    _: RateLimited = None,
    db: DBSession = None,
):
    from sqlalchemy import select, func
    from app.db.models import Document, DocumentChunk

    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        from fastapi import HTTPException
        raise HTTPException(404, detail=f"Document not found: {document_id}")

    # Count chunks and embeddings
    chunk_count_result = await db.execute(
        select(func.count(DocumentChunk.id)).where(
            DocumentChunk.document_id == document_id
        )
    )
    total_chunks = chunk_count_result.scalar() or 0

    embedded_count_result = await db.execute(
        select(func.count(DocumentChunk.id)).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.is_embedded == True,
        )
    )
    embedded_chunks = embedded_count_result.scalar() or 0
    coverage = (embedded_chunks / total_chunks * 100) if total_chunks > 0 else 0.0

    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        original_name=doc.original_name,
        doc_type=doc.doc_type,
        status=doc.status,
        file_size_bytes=doc.file_size_bytes,
        page_count=doc.page_count,
        tags=doc.tags,
        source_system=doc.source_system,
        metadata=doc.metadata_,
        chunks_count=total_chunks,
        embedding_coverage_pct=round(coverage, 1),
        kg_entities_count=0,
        created_at=doc.created_at,
        processed_at=doc.processed_at,
    )


@router.delete(
    "/document/{document_id}",
    summary="Delete a document and all associated data",
)
async def delete_document(
    document_id: str,
    _: RateLimited = None,
    db: DBSession = None,
):
    from sqlalchemy import select, delete
    from app.db.models import Document, DocumentChunk
    from app.db.qdrant import get_qdrant_client
    from app.core.config import settings

    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        from fastapi import HTTPException
        raise HTTPException(404, detail=f"Document not found: {document_id}")

    # Get embedding IDs for Qdrant cleanup
    chunk_result = await db.execute(
        select(DocumentChunk.embedding_id).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.embedding_id.isnot(None),
        )
    )
    embedding_ids = [row[0] for row in chunk_result.fetchall()]

    # Delete from Qdrant
    vectors_removed = 0
    if embedding_ids:
        try:
            client = get_qdrant_client()
            await client.delete(
                collection_name=settings.QDRANT_COLLECTION_CHUNKS,
                points_selector=embedding_ids,
            )
            vectors_removed = len(embedding_ids)
        except Exception as e:
            logger.warning(f"Qdrant cleanup error: {e}")

    chunks_count = len(embedding_ids)
    await db.execute(delete(Document).where(Document.id == document_id))
    await db.commit()

    return ORJSONResponse({
        "document_id": document_id,
        "status": "DELETED",
        "chunks_removed": chunks_count,
        "vectors_removed": vectors_removed,
    })
