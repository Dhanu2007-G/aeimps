"""
Reciprocal Rank Fusion (RRF) for combining multiple retrieval result lists.
Parameter-free, robust to different score scales across retrieval modes.
"""
from __future__ import annotations
import logging
from collections import defaultdict
from app.services.retrieval.orchestrator import ChunkResult

logger = logging.getLogger(__name__)


class RRFFusion:
    """
    RRF: score(d) = sum over r in result_lists: 1 / (k + rank_r(d))
    k=60 is empirically stable (Cormack et al. 2009).
    """

    def __init__(self, k: int = 60):
        self.k = k

    def fuse(self, result_lists: list[list[ChunkResult]]) -> list[ChunkResult]:
        """Fuse multiple ranked lists into a single re-ranked list."""
        if not result_lists:
            return []

        # Filter out empty lists
        result_lists = [r for r in result_lists if r]
        if not result_lists:
            return []

        # Accumulate RRF scores
        rrf_scores: dict[str, float] = defaultdict(float)
        chunk_map: dict[str, ChunkResult] = {}

        for result_list in result_lists:
            for rank, chunk in enumerate(result_list):
                rrf_score = 1.0 / (self.k + rank + 1)
                rrf_scores[chunk.chunk_id] += rrf_score

                # Keep the chunk with highest original score if seen multiple times
                if (chunk.chunk_id not in chunk_map or
                        chunk.score > chunk_map[chunk.chunk_id].score):
                    chunk_map[chunk.chunk_id] = chunk

        # Sort by RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)

        results = []
        for cid in sorted_ids:
            chunk = chunk_map[cid]
            chunk.score = rrf_scores[cid]  # Replace with RRF score for transparency
            results.append(chunk)

        logger.debug(f"RRF fused {sum(len(r) for r in result_lists)} → {len(results)} candidates")
        return results
