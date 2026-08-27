"""Agent Reasoner Node — LLM reasoning over retrieved context."""
from __future__ import annotations
import logging
import time
from app.services.agent.state import AgentState
from app.services.llm.abstraction import get_llm_client

logger = logging.getLogger(__name__)


WORKFLOW_SYSTEM_PROMPTS = {
    "incident_investigation": """You are an expert SRE analyzing a production incident.
Use the provided context to investigate the issue thoroughly.
Always cite specific sources. Be precise about what you know vs. what you're inferring.
Output JSON: {hypothesis, confidence (0-1), reasoning, evidence_chunks, needs_more_context (bool)}""",

    "question_answering": """You are an enterprise knowledge assistant.
Answer the question using only the provided context.
If context is insufficient, say so clearly.
Output JSON: {answer, confidence (0-1), reasoning, sources_used, needs_more_context (bool)}""",

    "summarization": """You are an expert document summarizer.
Create a comprehensive, structured summary of the provided content.
Output JSON: {summary, key_points (list), confidence (0-1), needs_more_context (bool)}""",

    "root_cause_analysis": """You are an expert RCA analyst.
Identify root causes with supporting evidence from the context.
Output JSON: {root_causes (list with confidence), causal_chain, evidence, confidence (0-1), needs_more_context (bool)}""",

    "remediation": """You are a senior engineer providing remediation guidance.
Suggest actionable fixes based on the context and best practices.
Output JSON: {immediate_actions (list), short_term_fixes (list), long_term_prevention (list), confidence (0-1), needs_more_context (bool)}""",
}


async def reasoner_node(state: AgentState) -> dict:
    """Core reasoning: analyze retrieved context and form response."""
    start = time.monotonic()
    llm = get_llm_client()

    workflow = state["workflow_type"]
    system = WORKFLOW_SYSTEM_PROMPTS.get(workflow, WORKFLOW_SYSTEM_PROMPTS["question_answering"])

    # Build context block from retrieved chunks
    context_parts = []
    for i, chunk in enumerate(state["retrieved_chunks"][:15], 1):
        source = chunk.get("source_doc", {})
        context_parts.append(
            f"[CONTEXT {i}] {source.get('original_name', 'Unknown')} "
            f"(score: {chunk['score']:.3f})\n{chunk['content']}\n"
        )
    context_text = "\n---\n".join(context_parts) if context_parts else "No context available."

    # Include prior reasoning if this is a re-attempt
    prior_context = ""
    if state.get("intermediate_thoughts"):
        prior_context = f"\nPrevious reasoning:\n{chr(10).join(state['intermediate_thoughts'][-3:])}\n"

    prompt = f"""Query: {state['original_query']}
{prior_context}
Retrieved Context:
{context_text}

Workflow: {workflow}
Attempt: {state.get('retrieval_attempts', 1)}

Analyze the context and provide a structured JSON response."""

    try:
        result, tokens = await llm.complete_structured(prompt, system=system, max_tokens=2048)
        duration_ms = int((time.monotonic() - start) * 1000)

        confidence = float(result.get("confidence", 0.5))
        needs_more = result.get("needs_more_context", False) and state["retrieval_attempts"] < 2

        # Extract main content based on workflow
        draft = (
            result.get("answer") or
            result.get("hypothesis") or
            result.get("summary") or
            result.get("root_causes") or
            str(result)
        )
        if isinstance(draft, (list, dict)):
            import json
            draft = json.dumps(draft, indent=2)

        updates = {
            "current_hypothesis": str(result),
            "confidence_score": confidence,
            "draft_response": draft,
            "total_tokens_used": state["total_tokens_used"] + tokens,
            "llm_calls": state["llm_calls"] + 1,
            "current_node": "reasoner",
            "intermediate_thoughts": state["intermediate_thoughts"] + [str(result)[:200]],
            "tool_calls": state["tool_calls"] + [{
                "tool_name": "llm_reasoner",
                "input": {"query": state["original_query"], "chunks_used": len(state["retrieved_chunks"])},
                "output": {"confidence": confidence},
                "latency_ms": duration_ms,
            }],
        }

        # If needs more context and haven't exceeded attempts, add more queries
        if needs_more:
            follow_up = result.get("follow_up_queries", [state["original_query"] + " details"])
            updates["retrieval_queries"] = (
                state.get("retrieval_queries", []) + follow_up[:2]
            )

        return updates

    except Exception as e:
        logger.error(f"Reasoner node failed: {e}")
        return {
            "draft_response": f"Analysis incomplete due to error: {str(e)}",
            "confidence_score": 0.1,
            "current_node": "reasoner",
            "errors": state["errors"] + [f"Reasoner failed: {str(e)}"],
        }
