"""Embedding Worker — batched BGE inference and Qdrant upsert."""
from __future__ import annotations
import asyncio
import logging
from app.core.config import settings
from workers.base_worker import BaseWorker

logger = logging.getLogger(__name__)


class EmbeddingWorker(BaseWorker):
    stream_name = settings.STREAM_EMBED
    group_name = "embedding-group"
    consumer_prefix = "embed-worker"
    batch_size = 3

    async def setup(self) -> None:
        # Pre-load encoder to avoid cold-start on first message
        from workers.embedding_worker.encoder import get_encoder
        self._encoder = get_encoder()
        self._encoder._load_dense_model()
        logger.info("Embedding worker ready")

    async def process_message(self, msg_id: str, fields: dict) -> None:
        document_id = fields.get("document_id")
        chunk_ids_raw = fields.get("chunk_ids", "")

        if fields.get("reindex") == "true":
            # Reindex all chunks for document
            chunk_ids = await self._get_all_chunk_ids(document_id)
        else:
            chunk_ids = [c for c in chunk_ids_raw.split(",") if c.strip()]

        if not chunk_ids:
            logger.warning(f"No chunk IDs for document {document_id}")
            return

        # Load chunks from DB
        chunks = await self._load_chunks(chunk_ids)
        if not chunks:
            return

        texts = [c["content"] for c in chunks]
        logger.info(f"Embedding {len(texts)} chunks for document {document_id}")

        # Generate dense vectors
        dense_vecs = self._encoder.encode_dense(texts)

        # Generate sparse vectors
        sparse_vecs = self._encoder.encode_sparse(texts)

        # Write to Qdrant
        from workers.embedding_worker.qdrant_writer import QdrantWriter
        writer = QdrantWriter()
        await writer.upsert(chunks, dense_vecs, sparse_vecs)

        # Mark as embedded in PostgreSQL
        await self._mark_embedded([c["id"] for c in chunks])

    async def _load_chunks(self, chunk_ids: list[str]) -> list[dict]:
        from sqlalchemy import select
        from app.db.postgres import get_db
        from app.db.models import DocumentChunk, Document

        async with get_db() as db:
            result = await db.execute(
                select(DocumentChunk, Document)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(DocumentChunk.id.in_(chunk_ids))
            )
            rows = result.all()

        return [
            {
                "id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "content": chunk.content,
                "chunk_type": chunk.chunk_type,
                "page_number": chunk.page_number,
                "filename": doc.filename,
                "original_name": doc.original_name,
                "doc_type": doc.doc_type,
                "metadata": chunk.metadata_ or {},
            }
            for chunk, doc in rows
        ]

    async def _get_all_chunk_ids(self, document_id: str) -> list[str]:
        from sqlalchemy import select
        from app.db.postgres import get_db
        from app.db.models import DocumentChunk

        async with get_db() as db:
            result = await db.execute(
                select(DocumentChunk.id).where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.is_embedded == False,
                )
            )
            return [str(row[0]) for row in result.fetchall()]

    async def _mark_embedded(self, chunk_ids: list[str]) -> None:
        from sqlalchemy import update
        from app.db.postgres import get_db
        from app.db.models import DocumentChunk

        async with get_db() as db:
            await db.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id.in_(chunk_ids))
                .values(
                    is_embedded=True,
                    embedding_model=settings.EMBEDDING_MODEL,
                )
            )


if __name__ == "__main__":
    import asyncio
    worker = EmbeddingWorker()
    asyncio.run(worker.run())
