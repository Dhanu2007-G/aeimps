"""Document Processor Worker — consumes stream:doc.ingest and runs parse→chunk pipeline."""
from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timezone

from app.core.config import settings
from workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class DocumentProcessorWorker(BaseWorker):
    stream_name = settings.STREAM_INGEST
    group_name = "doc-processor-group"
    consumer_prefix = "doc-processor"
    batch_size = 2  # CPU-heavy, low concurrency

    async def setup(self) -> None:
        from app.db.postgres import get_engine
        get_engine()  # warm up pool
        logger.info("Document processor worker ready")

    async def process_message(self, msg_id: str, fields: dict) -> None:
        job_id = fields.get("job_id")
        document_id = fields.get("document_id")
        file_path = fields.get("file_path")
        file_type = fields.get("file_type")
        filename = fields.get("filename", "unknown")

        if not all([job_id, document_id, file_path]):
            raise ValueError(f"Missing required fields: {fields}")

        logger.info(f"Processing document: {filename} [{file_type}]")

        # Update job status → RUNNING
        await _update_job(job_id, "RUNNING", worker_id=self.worker_id)
        await _update_document(document_id, "PROCESSING")

        try:
            from workers.document_processor.pipeline import DocumentPipeline
            pipeline = DocumentPipeline()
            chunks = await pipeline.process(
                document_id=document_id,
                file_path=file_path,
                file_type=file_type,
                filename=filename,
            )

            logger.info(f"Document {document_id}: {len(chunks)} chunks extracted")

            # Persist chunks to PostgreSQL
            chunk_ids = await _persist_chunks(document_id, chunks)

            # Publish chunk batches to embedding queue
            await _publish_embed_batch(document_id, chunk_ids)

            # Publish to KG queue
            await _publish_kg_batch(document_id, chunk_ids)

            # Mark document PROCESSED
            await _update_document(document_id, "PROCESSED")
            await _update_job(job_id, "COMPLETED", output={"chunks_count": len(chunks)})

        except Exception as e:
            logger.error(f"Document processing failed: {document_id}: {e}")
            await _update_document(document_id, "FAILED", error=str(e))
            await _update_job(job_id, "FAILED", error=str(e),
                              trace=traceback.format_exc()[-1000:])
            raise


async def _update_job(job_id: str, status: str, worker_id: str | None = None,
                      output: dict | None = None, error: str | None = None,
                      trace: str | None = None) -> None:
    from sqlalchemy import update
    from app.db.postgres import get_db
    from app.db.models import ProcessingJob

    values = {"status": status, "updated_at": datetime.now(timezone.utc)}
    if worker_id:
        values["worker_id"] = worker_id
    if status == "RUNNING":
        values["started_at"] = datetime.now(timezone.utc)
        values["attempts"] = ProcessingJob.attempts + 1
    if status in ("COMPLETED", "FAILED"):
        values["completed_at"] = datetime.now(timezone.utc)
    if output:
        values["output_payload"] = output
    if error:
        values["error_message"] = error[:500]
    if trace:
        values["error_trace"] = trace

    async with get_db() as db:
        await db.execute(update(ProcessingJob).where(ProcessingJob.id == job_id).values(**values))


async def _update_document(document_id: str, status: str, error: str | None = None) -> None:
    from sqlalchemy import update
    from app.db.postgres import get_db
    from app.db.models import Document

    values: dict = {"status": status, "updated_at": datetime.now(timezone.utc)}
    if status == "PROCESSED":
        values["processed_at"] = datetime.now(timezone.utc)
    if error:
        values["error_message"] = error[:500]

    async with get_db() as db:
        await db.execute(update(Document).where(Document.id == document_id).values(**values))


async def _persist_chunks(document_id: str, chunks: list[dict]) -> list[str]:
    from app.db.postgres import get_db
    from app.db.models import DocumentChunk

    chunk_ids = []
    async with get_db() as db:
        for chunk in chunks:
            obj = DocumentChunk(
                document_id=document_id,
                chunk_index=chunk["chunk_index"],
                chunk_type=chunk.get("chunk_type", "text"),
                content=chunk["content"],
                token_count=chunk.get("token_count"),
                page_number=chunk.get("page_number"),
                table_data=chunk.get("table_data"),
                code_language=chunk.get("code_language"),
                metadata_=chunk.get("metadata", {}),
            )
            db.add(obj)
            chunk_ids.append(obj.id)

    return chunk_ids


async def _publish_embed_batch(document_id: str, chunk_ids: list[str]) -> None:
    from app.db.redis import publish_to_stream
    # Publish in batches of 50
    for i in range(0, len(chunk_ids), 50):
        batch = chunk_ids[i:i+50]
        await publish_to_stream(settings.STREAM_EMBED, {
            "document_id": document_id,
            "chunk_ids": ",".join(batch),
            "batch_index": str(i // 50),
        })


async def _publish_kg_batch(document_id: str, chunk_ids: list[str]) -> None:
    from app.db.redis import publish_to_stream
    await publish_to_stream(settings.STREAM_KG, {
        "document_id": document_id,
        "chunk_count": str(len(chunk_ids)),
    })


if __name__ == "__main__":
    worker = DocumentProcessorWorker()
    asyncio.run(worker.run())
