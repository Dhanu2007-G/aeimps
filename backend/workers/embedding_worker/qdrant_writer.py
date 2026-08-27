"""Qdrant Writer — batched named-vector upsert for hybrid search."""
from __future__ import annotations
import logging
import uuid
from app.core.config import settings

logger = logging.getLogger(__name__)


class QdrantWriter:
    async def upsert(
        self,
        chunks: list[dict],
        dense_vecs: list[list[float]],
        sparse_vecs: list[dict],
    ) -> None:
        from qdrant_client import models
        from app.db.qdrant import get_qdrant_client

        client = get_qdrant_client()
        points = []

        for chunk, dense, sparse in zip(chunks, dense_vecs, sparse_vecs):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["id"]))

            # Convert sparse dict {token_id: weight} → SparseVector
            sparse_indices = list(sparse.keys())
            sparse_values = list(sparse.values())

            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        "dense": dense,
                        "sparse": models.SparseVector(
                            indices=sparse_indices,
                            values=sparse_values,
                        ),
                    },
                    payload={
                        "chunk_db_id": chunk["id"],
                        "document_id": chunk["document_id"],
                        "content": chunk["content"][:2000],  # Truncate for payload
                        "chunk_type": chunk["chunk_type"],
                        "doc_type": chunk.get("doc_type", ""),
                        "filename": chunk.get("filename", ""),
                        "original_name": chunk.get("original_name", ""),
                        "page_number": chunk.get("page_number"),
                        "metadata": chunk.get("metadata", {}),
                    },
                )
            )

        # Upsert in batches of 100
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            await client.upsert(
                collection_name=settings.QDRANT_COLLECTION_CHUNKS,
                points=batch,
                wait=True,
            )
            logger.debug(f"Upserted batch {i//batch_size + 1}: {len(batch)} vectors")

        logger.info(f"Upserted {len(points)} vectors to Qdrant")

        # Update embedding_id in PostgreSQL
        await self._update_embedding_ids(chunks, points)

    async def _update_embedding_ids(self, chunks: list[dict], points) -> None:
        from sqlalchemy import update
        from app.db.postgres import get_db
        from app.db.models import DocumentChunk

        id_map = {c["id"]: str(p.id) for c, p in zip(chunks, points)}
        async with get_db() as db:
            for chunk_id, point_id in id_map.items():
                await db.execute(
                    update(DocumentChunk)
                    .where(DocumentChunk.id == chunk_id)
                    .values(embedding_id=point_id)
                )
