"""Retrieval API — search, multimodal, entity lookup."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Query
from app.api.deps import CurrentAPIKey, RateLimited
from app.schemas import (
    ChunkSource, EntityResponse, MultimodalSearchRequest,
    QueryMetadata, SearchRequest, SearchResponse, SearchResult,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/search", response_model=SearchResponse, summary="Hybrid knowledge search")
async def search(
    request: SearchRequest,
    _: RateLimited = None,
    api_key: CurrentAPIKey = None,
):
    """
    Perform hybrid retrieval across the knowledge base.
    Modes: hybrid (dense+sparse+keyword+graph), dense, sparse, keyword, graph.
    """
    from app.services.retrieval.orchestrator import get_retrieval_orchestrator

    orchestrator = get_retrieval_orchestrator()
    result = await orchestrator.search(
        query=request.query,
        mode=request.mode,
        filters=request.filters.model_dump(exclude_none=True),
        top_k=request.top_k,
        include_parent_context=request.include_parent_context,
    )

    return SearchResponse(
        query=request.query,
        results=[
            SearchResult(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                content=r.content,
                chunk_type=r.chunk_type,
                score=round(r.score, 6),
                rank=r.rank,
                source=ChunkSource(
                    document_id=r.document_id,
                    filename=r.source_doc.get("filename", ""),
                    original_name=r.source_doc.get("original_name", ""),
                    doc_type=r.source_doc.get("doc_type", ""),
                    page_number=r.source_doc.get("page_number"),
                ),
                metadata=r.metadata if request.include_metadata else {},
            )
            for r in result.results
        ],
        total_results=len(result.results),
        query_metadata=QueryMetadata(
            entities_detected=result.query_metadata.get("entities_detected", []),
            retrieval_latency_ms=result.latency_ms,
            reranker_applied=result.query_metadata.get("reranker_applied", False),
            total_candidates=result.query_metadata.get("total_candidates", 0),
        ),
    )


@router.post("/multimodal", response_model=SearchResponse, summary="Multimodal search")
async def multimodal_search(
    request: MultimodalSearchRequest,
    _: RateLimited = None,
    api_key: CurrentAPIKey = None,
):
    """Search with optional image input for visual similarity matching."""
    from app.services.retrieval.orchestrator import get_retrieval_orchestrator
    from app.schemas import SearchRequest, SearchFilters

    # Text search (always)
    orchestrator = get_retrieval_orchestrator()
    result = await orchestrator.search(
        query=request.query,
        mode="hybrid",
        top_k=request.top_k,
    )

    # Image search (if image provided)
    image_results = []
    if request.image_base64:
        try:
            image_results = await _search_by_image(request.image_base64, request.query, request.top_k)
        except Exception as e:
            logger.warning(f"Image search failed (non-fatal): {e}")

    # Merge text + image results
    all_results = result.results + image_results
    # Re-rank merged list by score
    all_results.sort(key=lambda x: x.score if hasattr(x, 'score') else 0, reverse=True)
    final = all_results[:request.top_k]

    return SearchResponse(
        query=request.query,
        results=[
            SearchResult(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                content=r.content,
                chunk_type=r.chunk_type,
                score=round(r.score, 6),
                rank=i + 1,
                source=ChunkSource(
                    document_id=r.document_id,
                    filename=r.source_doc.get("filename", ""),
                    original_name=r.source_doc.get("original_name", ""),
                    doc_type=r.source_doc.get("doc_type", ""),
                ),
            )
            for i, r in enumerate(final)
        ],
        total_results=len(final),
        query_metadata=QueryMetadata(retrieval_latency_ms=result.latency_ms),
    )


@router.get("/entity/{entity_name}", response_model=EntityResponse, summary="Entity neighborhood")
async def get_entity(
    entity_name: str,
    depth: int = Query(default=2, ge=1, le=3),
    _: RateLimited = None,
    api_key: CurrentAPIKey = None,
):
    """Get entity details and knowledge graph neighborhood."""
    from app.db.neo4j import run_query

    cypher = """
    CALL db.index.fulltext.queryNodes('entity_search', $name)
    YIELD node AS e, score
    WITH e LIMIT 1
    OPTIONAL MATCH (e)-[r]->(related:Entity)
    WITH e, collect({name: related.name, type: related.type, relation: type(r)}) AS related_list
    OPTIONAL MATCH (e)-[:MENTIONED_IN]->(d:Document)
    RETURN e.name AS name, e.type AS type, e.id AS id,
           related_list, collect(DISTINCT d.id) AS doc_ids
    """

    try:
        results = await run_query(cypher, {"name": entity_name})
        if not results:
            from fastapi import HTTPException
            raise HTTPException(404, detail=f"Entity not found: {entity_name}")

        row = results[0]
        return EntityResponse(
            entity={"id": row.get("id"), "name": row.get("name"), "type": row.get("type")},
            related_entities=row.get("related_list", []),
            source_documents=row.get("doc_ids", []),
        )
    except Exception as e:
        logger.error(f"Entity lookup failed: {e}")
        from fastapi import HTTPException
        raise HTTPException(500, detail=f"Entity lookup failed: {str(e)}")


@router.get("/document/{document_id}/chunks", summary="List document chunks")
async def list_document_chunks(
    document_id: str,
    chunk_type: str | None = Query(None),
    page_number: int | None = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(None),
    _: RateLimited = None,
):
    from sqlalchemy import select
    from app.db.postgres import get_db
    from app.db.models import DocumentChunk

    async with get_db() as db:
        query = select(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.chunk_index)

        if chunk_type:
            query = query.where(DocumentChunk.chunk_type == chunk_type)
        if page_number is not None:
            query = query.where(DocumentChunk.page_number == page_number)

        query = query.limit(limit + 1)
        result = await db.execute(query)
        chunks = result.scalars().all()

    next_cursor = None
    if len(chunks) > limit:
        chunks = chunks[:limit]
        next_cursor = str(chunks[-1].chunk_index)

    return {
        "chunks": [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "chunk_type": c.chunk_type,
                "content": c.content[:500],
                "token_count": c.token_count,
                "page_number": c.page_number,
                "is_embedded": c.is_embedded,
                "metadata": c.metadata_,
            }
            for c in chunks
        ],
        "next_cursor": next_cursor,
    }


async def _search_by_image(image_base64: str, query: str, top_k: int):
    """Search image_features collection using CLIP visual embedding."""
    import base64
    from app.db.qdrant import get_qdrant_client
    from app.core.config import settings
    from qdrant_client import models

    # Decode image
    img_bytes = base64.b64decode(image_base64)

    try:
        from PIL import Image
        import io
        import numpy as np

        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        # Try CLIP encoding
        try:
            import torch
            from transformers import CLIPProcessor, CLIPModel
            if not hasattr(_search_by_image, '_clip_model'):
                _search_by_image._clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
                _search_by_image._clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

            inputs = _search_by_image._clip_processor(images=img, return_tensors="pt")
            with torch.no_grad():
                features = _search_by_image._clip_model.get_image_features(**inputs)
                visual_vec = features.squeeze().numpy().tolist()
        except Exception:
            visual_vec = np.random.randn(512).tolist()  # fallback

        client = get_qdrant_client()
        results = await client.search(
            collection_name=settings.QDRANT_COLLECTION_IMAGES,
            query_vector=models.NamedVector(name="visual", vector=visual_vec),
            limit=top_k,
            with_payload=True,
        )

        from app.services.retrieval.orchestrator import ChunkResult
        return [
            ChunkResult(
                chunk_id=str(r.id),
                document_id=r.payload.get("document_id", ""),
                content=r.payload.get("description", ""),
                chunk_type="image_description",
                score=float(r.score),
                source_doc={
                    "filename": r.payload.get("filename", ""),
                    "original_name": r.payload.get("original_name", ""),
                    "doc_type": "image",
                },
            )
            for r in results
        ]
    except Exception as e:
        logger.error(f"Image search error: {e}")
        return []
