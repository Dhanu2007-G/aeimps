"""Dense retrieval via Qdrant named vectors."""
from __future__ import annotations
import logging
from app.core.config import settings
from app.services.retrieval.orchestrator import ChunkResult

logger = logging.getLogger(__name__)


class DenseRetriever:
    async def search(self, query: str, top_k: int, filters: dict) -> list[ChunkResult]:
        from app.db.qdrant import get_qdrant_client
        from workers.embedding_worker.encoder import get_encoder
        from qdrant_client import models

        encoder = get_encoder()
        query_vec = encoder.encode_query(query)

        client = get_qdrant_client()
        filter_conds = _build_qdrant_filter(filters)

        results = await client.search(
            collection_name=settings.QDRANT_COLLECTION_CHUNKS,
            query_vector=models.NamedVector(name="dense", vector=query_vec),
            limit=top_k,
            query_filter=filter_conds,
            with_payload=True,
            score_threshold=0.3,
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


def _build_qdrant_filter(filters: dict):
    from qdrant_client import models
    conditions = []
    if filters.get("doc_types"):
        conditions.append(
            models.FieldCondition(
                key="doc_type",
                match=models.MatchAny(any=filters["doc_types"]),
            )
        )
    if filters.get("chunk_types"):
        conditions.append(
            models.FieldCondition(
                key="chunk_type",
                match=models.MatchAny(any=filters["chunk_types"]),
            )
        )
    return models.Filter(must=conditions) if conditions else None
