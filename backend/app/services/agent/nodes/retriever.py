"""Agent Retriever Node — fetches context from knowledge base."""
from __future__ import annotations
import asyncio
import logging
import time
from app.services.agent.state import AgentState

logger = logging.getLogger(__name__)


async def retriever_node(state: AgentState) -> dict:
    """Execute retrieval for all planned sub-queries in parallel."""
    from app.services.retrieval.orchestrator import get_retrieval_orchestrator

    orchestrator = get_retrieval_orchestrator()
    queries = state.get("retrieval_queries") or [state["original_query"]]

    ctx = state.get("input_context", {})
    filters = {}
    if ctx.get("document_ids"):
        # NOTE: Qdrant doesn't filter by document_id list natively without payload index
        pass  # Would need to add document_id to Qdrant payload index
    if ctx.get("time_window"):
        filters["date_from"] = ctx["time_window"].get("from")
        filters["date_to"] = ctx["time_window"].get("to")

    start = time.monotonic()
    tasks = [
        orchestrator.search(
            query=q,
            mode="hybrid",
            filters={k: v for k, v in filters.items() if v},
            top_k=10,
            session_id=state["session_id"],
        )
        for q in queries[:4]  # Max 4 concurrent queries
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    duration_ms = int((time.monotonic() - start) * 1000)

    all_chunks = []
    seen_ids = set()
    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"Retrieval sub-query failed: {result}")
            continue
        for chunk in result.results:
            if chunk.chunk_id not in seen_ids:
                seen_ids.add(chunk.chunk_id)
                all_chunks.append({
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "content": chunk.content,
                    "chunk_type": chunk.chunk_type,
                    "score": chunk.score,
                    "source_doc": chunk.source_doc,
                    "metadata": chunk.metadata,
                })

    # Sort by score, keep top 20
    all_chunks.sort(key=lambda x: x["score"], reverse=True)
    all_chunks = all_chunks[:20]

    logger.info(
        f"Retriever: {len(queries)} queries → {len(all_chunks)} unique chunks in {duration_ms}ms"
    )

    return {
        "retrieved_chunks": all_chunks,
        "retrieval_attempts": state["retrieval_attempts"] + 1,
        "current_node": "retriever",
        "tool_calls": state["tool_calls"] + [{
            "tool_name": "retriever",
            "input": {"queries": queries},
            "output": {"chunks_found": len(all_chunks)},
            "latency_ms": duration_ms,
        }],
    }
