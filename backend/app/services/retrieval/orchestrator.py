"""
Retrieval Orchestrator
Coordinates parallel retrieval across dense, sparse, keyword, and graph modes.
Applies RRF fusion and cross-encoder reranking.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    chunk_id: str
    document_id: str
    content: str
    chunk_type: str
    score: float
    rank: int = 0
    source_doc: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    retrieval_mode: str = "unknown"


@dataclass
class RetrievalResult:
    query: str
    results: list[ChunkResult]
    query_metadata: dict = field(default_factory=dict)
    latency_ms: int = 0


class RetrievalOrchestrator:
    """
    Orchestrates all retrieval modes in parallel and fuses results.
    This is the core intelligence layer for AEIMPS search quality.
    """

    def __init__(self):
        from app.services.retrieval.dense import DenseRetriever
        from app.services.retrieval.sparse import SparseRetriever
        from app.services.retrieval.keyword import KeywordRetriever
        from app.services.retrieval.graph import GraphRetriever
        from app.services.retrieval.fusion import RRFFusion
        from app.services.retrieval.reranker import BGEReranker
        from app.services.retrieval.context_assembler import ContextAssembler

        self.dense = DenseRetriever()
        self.sparse = SparseRetriever()
        self.keyword = KeywordRetriever()
        self.graph = GraphRetriever()
        self.fusion = RRFFusion(k=settings.RRF_K)
        self.reranker = BGEReranker()
        self.assembler = ContextAssembler()

    async def search(
        self,
        query: str,
        mode: str = "hybrid",
        filters: dict | None = None,
        top_k: int = 8,
        include_parent_context: bool = True,
        session_id: str | None = None,
    ) -> RetrievalResult:
        """
        Main search entry point.
        Returns top_k results after fusion and reranking.
        """
        start = time.monotonic()
        filters = filters or {}
        candidates_k = settings.RETRIEVAL_CANDIDATES

        # ─── Extract query entities for graph search ──────────
        entities = await self._extract_query_entities(query)

        # ─── Parallel retrieval ───────────────────────────────
        retrieval_tasks = []

        if mode in ("hybrid", "dense"):
            retrieval_tasks.append(self._safe_retrieve(
                self.dense.search, query, candidates_k, filters, "dense"
            ))

        if mode in ("hybrid", "sparse"):
            retrieval_tasks.append(self._safe_retrieve(
                self.sparse.search, query, candidates_k, filters, "sparse"
            ))

        if mode in ("hybrid", "keyword"):
            retrieval_tasks.append(self._safe_retrieve(
                self.keyword.search, query, candidates_k, filters, "keyword"
            ))

        if mode in ("hybrid", "graph") and entities:
            retrieval_tasks.append(self._safe_graph_retrieve(
                entities, candidates_k, filters
            ))

        # Single mode shortcuts
        if mode == "dense":
            all_results = await asyncio.gather(*retrieval_tasks)
            fused = all_results[0] if all_results else []
        elif mode in ("sparse", "keyword"):
            all_results = await asyncio.gather(*retrieval_tasks)
            fused = all_results[0] if all_results else []
        else:
            all_results = await asyncio.gather(*retrieval_tasks)
            fused = self.fusion.fuse([r for r in all_results if r])

        # ─── Reranking ────────────────────────────────────────
        reranked = fused
        reranker_applied = False
        if settings.RERANKER_ENABLED and len(fused) > top_k:
            try:
                reranked = await self.reranker.rerank(query, fused)
                reranker_applied = True
            except Exception as e:
                logger.warning(f"Reranker failed, using fused results: {e}")

        # Trim to top_k
        final = reranked[:top_k]
        for i, r in enumerate(final):
            r.rank = i + 1

        # ─── Context assembly ─────────────────────────────────
        if include_parent_context:
            final = await self.assembler.enrich(final)

        latency_ms = int((time.monotonic() - start) * 1000)

        # ─── Log retrieval ────────────────────────────────────
        asyncio.create_task(self._log_retrieval(
            query=query,
            mode=mode,
            results=final,
            latency_ms=latency_ms,
            session_id=session_id,
        ))

        return RetrievalResult(
            query=query,
            results=final,
            query_metadata={
                "entities_detected": entities,
                "retrieval_latency_ms": latency_ms,
                "reranker_applied": reranker_applied,
                "total_candidates": sum(len(r) for r in all_results if r),
                "mode": mode,
            },
            latency_ms=latency_ms,
        )

    async def _safe_retrieve(self, fn, query, k, filters, mode) -> list[ChunkResult]:
        """Wrap retrieval with error handling."""
        try:
            results = await fn(query, k, filters)
            for r in results:
                r.retrieval_mode = mode
            return results
        except Exception as e:
            logger.error(f"Retrieval mode {mode} failed: {e}")
            return []

    async def _safe_graph_retrieve(
        self, entities, k, filters
    ) -> list[ChunkResult]:
        try:
            results = await self.graph.search(entities, k, filters)
            for r in results:
                r.retrieval_mode = "graph"
            return results
        except Exception as e:
            logger.error(f"Graph retrieval failed: {e}")
            return []

    async def _extract_query_entities(self, query: str) -> list[str]:
        """Simple entity extraction from query for graph search seeding."""
        try:
            import spacy
            if not hasattr(self, '_nlp'):
                try:
                    self._nlp = spacy.load("en_core_web_sm")
                except Exception:
                    return []
            doc = self._nlp(query)
            return [ent.text for ent in doc.ents if ent.label_ in (
                "ORG", "PRODUCT", "PERSON", "GPE", "TECHNOLOGY", "SYSTEM"
            )]
        except Exception:
            return []

    async def _log_retrieval(
        self,
        query: str,
        mode: str,
        results: list[ChunkResult],
        latency_ms: int,
        session_id: str | None,
    ) -> None:
        try:
            from app.db.postgres import get_db
            from app.db.models import RetrievalLog
            async with get_db() as db:
                log = RetrievalLog(
                    session_id=session_id,
                    query=query[:500],
                    retrieval_mode=mode,
                    num_candidates=len(results),
                    num_returned=len(results),
                    top_chunk_ids=[r.chunk_id for r in results[:10]],
                    scores=[r.score for r in results[:10]],
                    latency_ms=latency_ms,
                )
                db.add(log)
        except Exception as e:
            logger.debug(f"Retrieval logging failed (non-critical): {e}")


# Module-level singleton
_orchestrator: RetrievalOrchestrator | None = None


def get_retrieval_orchestrator() -> RetrievalOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = RetrievalOrchestrator()
    return _orchestrator
