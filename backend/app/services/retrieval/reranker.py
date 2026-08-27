"""BGE cross-encoder reranker for precision re-scoring of candidates."""
from __future__ import annotations
import asyncio
import logging
from app.services.retrieval.orchestrator import ChunkResult

logger = logging.getLogger(__name__)


class BGEReranker:
    """
    Uses BGE cross-encoder to score (query, passage) pairs.
    Much higher precision than bi-encoder at the cost of latency.
    Applied only to the top-N candidates after initial retrieval.
    """

    async def rerank(
        self,
        query: str,
        chunks: list[ChunkResult],
        top_n: int | None = None,
    ) -> list[ChunkResult]:
        """
        Rerank chunks by cross-encoder score.
        Runs in a thread pool to avoid blocking the event loop.
        """
        if not chunks:
            return []

        passages = [c.content[:512] for c in chunks]

        # Run CPU-bound reranker in thread pool
        scores = await asyncio.get_event_loop().run_in_executor(
            None,
            self._score_pairs,
            query,
            passages,
        )

        # Attach reranker scores and sort
        for chunk, score in zip(chunks, scores):
            chunk.score = score

        reranked = sorted(chunks, key=lambda c: c.score, reverse=True)
        if top_n:
            reranked = reranked[:top_n]

        logger.debug(f"Reranked {len(chunks)} → top {len(reranked)} results")
        return reranked

    def _score_pairs(self, query: str, passages: list[str]) -> list[float]:
        from workers.embedding_worker.encoder import get_encoder
        encoder = get_encoder()
        return encoder.rerank(query, passages)
