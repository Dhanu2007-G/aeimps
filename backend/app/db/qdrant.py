"""
Qdrant vector database client wrapper.
Manages named vector collections for multimodal retrieval.
"""
from __future__ import annotations

import logging
from typing import Any

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=30,
        )
    return _client


async def init_collections() -> None:
    """Initialize Qdrant collections with named vectors for hybrid search."""
    client = get_qdrant_client()

    # ─── document_chunks: text embeddings ────────────────────
    await _ensure_collection(
        client,
        settings.QDRANT_COLLECTION_CHUNKS,
        vectors_config={
            "dense": models.VectorParams(
                size=settings.EMBEDDING_DIM,
                distance=models.Distance.COSINE,
                on_disk=False,
            ),
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams(
                index=models.SparseIndexParams(on_disk=False),
            ),
        },
        payload_schema={
            "document_id": models.PayloadSchemaType.KEYWORD,
            "chunk_type": models.PayloadSchemaType.KEYWORD,
            "doc_type": models.PayloadSchemaType.KEYWORD,
            "source_system": models.PayloadSchemaType.KEYWORD,
            "is_embedded": models.PayloadSchemaType.BOOL,
        },
    )

    # ─── image_features: visual + text embeddings ────────────
    await _ensure_collection(
        client,
        settings.QDRANT_COLLECTION_IMAGES,
        vectors_config={
            "visual": models.VectorParams(
                size=512,
                distance=models.Distance.COSINE,
            ),
            "text": models.VectorParams(
                size=settings.EMBEDDING_DIM,
                distance=models.Distance.COSINE,
            ),
        },
        payload_schema={
            "document_id": models.PayloadSchemaType.KEYWORD,
            "diagram_type": models.PayloadSchemaType.KEYWORD,
        },
    )

    # ─── entity_embeddings: KG entity vectors ────────────────
    await _ensure_collection(
        client,
        settings.QDRANT_COLLECTION_ENTITIES,
        vectors_config={
            "entity": models.VectorParams(
                size=settings.EMBEDDING_DIM,
                distance=models.Distance.COSINE,
            ),
        },
        payload_schema={
            "entity_type": models.PayloadSchemaType.KEYWORD,
            "neo4j_id": models.PayloadSchemaType.KEYWORD,
        },
    )

    logger.info("Qdrant collections initialized")


async def _ensure_collection(
    client: AsyncQdrantClient,
    name: str,
    vectors_config: dict,
    sparse_vectors_config: dict | None = None,
    payload_schema: dict | None = None,
) -> None:
    """Create collection if it doesn't exist, otherwise verify config."""
    try:
        existing = await client.get_collection(name)
        logger.info(f"Qdrant collection exists: {name} ({existing.points_count} points)")
    except Exception:
        logger.info(f"Creating Qdrant collection: {name}")
        await client.create_collection(
            collection_name=name,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_vectors_config or {},
            optimizers_config=models.OptimizersConfigDiff(
                indexing_threshold=20000,
                memmap_threshold=50000,
            ),
            hnsw_config=models.HnswConfigDiff(
                m=16,
                ef_construct=100,
                full_scan_threshold=10000,
            ),
        )

        # Create payload indexes
        if payload_schema:
            for field, field_type in payload_schema.items():
                await client.create_payload_index(
                    collection_name=name,
                    field_name=field,
                    field_schema=field_type,
                )


async def check_connection() -> bool:
    try:
        client = get_qdrant_client()
        await client.get_collections()
        return True
    except Exception as e:
        logger.error(f"Qdrant connection failed: {e}")
        return False


async def close_client() -> None:
    global _client
    if _client:
        await _client.close()
        _client = None
