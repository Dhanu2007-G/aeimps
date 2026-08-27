"""Sparse vector retrieval via Qdrant BGE-M3 sparse vectors."""
from __future__ import annotations
import logging
from app.core.config import settings
from app.services.retrieval.orchestrator import ChunkResult

logger = logging.getLogger(__name__)


class SparseRetriever:
    async def search(self, query: str, top_k: int, filters: dict) -> list[ChunkResult]:
        from app.db.qdrant import get_qdrant_client
        from workers.embedding_worker.encoder import get_encoder
        from qdrant_client import models

        encoder = get_encoder()
        sparse_vecs = encoder.encode_sparse([query])
        if not sparse_vecs:
            return []
        sparse_vec = sparse_vecs[0]

        client = get_qdrant_client()
        from app.services.retrieval.dense import _build_qdrant_filter
        filter_conds = _build_qdrant_filter(filters)

        try:
            indices = list(sparse_vec.keys())
            values = list(sparse_vec.values())
            results = await client.search(
                collection_name=settings.QDRANT_COLLECTION_CHUNKS,
                query_vector=models.NamedSparseVector(
                    name="sparse",
                    vector=models.SparseVector(indices=indices, values=values),
                ),
                limit=top_k,
                query_filter=filter_conds,
                with_payload=True,
            )
            return [
                ChunkResult(
                    chunk_id=str(r.id),
                    document_id=r.payload.get("document_id", ""),
                    content=r.payload.get("content", ""),
                    chunk_type=r.payload.get("chunk_type", "text"),
                    score=float(r.score),
                    source_doc={
                        "filename": r.payload.get("filename", ""),
                        "original_name": r.payload.get("original_name", ""),
                        "doc_type": r.payload.get("doc_type", ""),
                        "page_number": r.payload.get("page_number"),
                    },
                    metadata=r.payload.get("metadata", {}),
                )
                for r in results
            ]
        except Exception as e:
            logger.error(f"Sparse search failed: {e}")
            return []
