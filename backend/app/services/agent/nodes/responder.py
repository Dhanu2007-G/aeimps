"""Agent Responder Node — formats final response with source citations."""
from __future__ import annotations
import logging
import time
from app.services.agent.state import AgentState
from app.services.llm.abstraction import get_llm_client

logger = logging.getLogger(__name__)


async def responder_node(state: AgentState) -> dict:
    """Format draft into final polished response with citations."""
    start = time.monotonic()
    llm = get_llm_client()

    # Build source citations from retrieved chunks
    citations = []
    for chunk in state["retrieved_chunks"][:8]:
        citations.append({
            "chunk_id": chunk["chunk_id"],
            "document_id": chunk["document_id"],
            "filename": chunk["source_doc"].get("filename", ""),
            "content_preview": chunk["content"][:150] + "..." if len(chunk["content"]) > 150 else chunk["content"],
            "relevance_score": round(chunk["score"], 4),
        })

    system = f"""You are an enterprise intelligence assistant.
Format the analysis into a clear, well-structured response.
Workflow: {state['workflow_type']}

Rules:
- Be concise but comprehensive
- Use markdown formatting (headers, bullets) for readability
- Reference sources as [SOURCE N] where N matches the source number
- Explicitly state confidence level
- For incidents/RCA: include Summary, Root Cause, Evidence, Recommended Actions
- For Q&A: include direct answer then supporting details
- For summaries: include Overview, Key Points, Details"""

    # Build context list for citation numbering
    context_list = "\n".join(
        f"[SOURCE {i+1}] {c['source_doc'].get('original_name', 'Unknown')}"
        for i, c in enumerate(state["retrieved_chunks"][:8])
    )

    prompt = f"""Analysis to format:
{state.get('draft_response', 'No analysis available.')}

Validation notes: {state.get('validation_notes', [])}
Confidence: {state.get('confidence_score', 0.5):.0%}

Available Sources:
{context_list}

Format this into a final, professional response."""

    try:
        final_text, tokens = await llm.complete(
            prompt, system=system, max_tokens=3000, temperature=0.1
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        # Persist final session result to PostgreSQL
        await _persist_session_result(
            session_id=state["session_id"],
            final_response=final_text,
            confidence=state.get("confidence_score", 0.5),
            total_tokens=state["total_tokens_used"] + tokens,
            model=llm._client.__class__.__name__ if llm._client else "mock",
        )

        return {
            "final_response": final_text,
            "source_citations": citations,
            "current_node": "responder",
            "total_tokens_used": state["total_tokens_used"] + tokens,
            "llm_calls": state["llm_calls"] + 1,
        }
    except Exception as e:
        logger.error(f"Responder failed: {e}")
        return {
            "final_response": state.get("draft_response", "Unable to generate response."),
            "source_citations": citations,
            "current_node": "responder",
            "errors": state["errors"] + [f"Responder failed: {str(e)}"],
        }


async def _persist_session_result(
    session_id: str,
    final_response: str,
    confidence: float,
    total_tokens: int,
    model: str,
) -> None:
    try:
        from datetime import datetime, timezone
        from sqlalchemy import update
        from app.db.postgres import get_db
        from app.db.models import AgentSession

        async with get_db() as db:
            await db.execute(
                update(AgentSession)
                .where(AgentSession.session_id == session_id)
                .values(
                    status="COMPLETED",
                    final_response=final_response,
                    confidence_score=confidence,
                    total_tokens_used=total_tokens,
                    llm_model=model,
                    completed_at=datetime.now(timezone.utc),
                )
            )
    except Exception as e:
        logger.error(f"Session persist failed: {e}")
