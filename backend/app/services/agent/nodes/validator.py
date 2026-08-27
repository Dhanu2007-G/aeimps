"""Agent Validator Node — checks response quality and groundedness."""
from __future__ import annotations
import logging
import time
from app.services.agent.state import AgentState
from app.services.llm.abstraction import get_llm_client

logger = logging.getLogger(__name__)


async def validator_node(state: AgentState) -> dict:
    """Validate draft response against retrieved context for hallucination risk."""
    start = time.monotonic()
    llm = get_llm_client()

    if not state.get("draft_response"):
        return {"validation_passed": False, "current_node": "validator",
                "validation_notes": ["No draft response to validate"]}

    # Quick context coverage check
    context_texts = " ".join(c["content"] for c in state["retrieved_chunks"][:10])
    draft = state["draft_response"]

    system = """You are a quality validator for AI-generated responses.
Check if the response is grounded in the provided context.
Output JSON: {
    passed (bool), 
    confidence_adjustment (float, -0.3 to 0.1),
    issues (list of strings),
    unsupported_claims (list of strings)
}"""

    prompt = f"""Response to validate:
{draft[:2000]}

Available Context (first 3000 chars):
{context_texts[:3000]}

Check: Is every claim in the response supported by the context?
Are there hallucinated facts, names, or numbers?"""

    try:
        result, tokens = await llm.complete_structured(prompt, system=system, max_tokens=512)
        duration_ms = int((time.monotonic() - start) * 1000)

        validation_passed = result.get("passed", True)
        confidence_adj = float(result.get("confidence_adjustment", 0.0))
        issues = result.get("issues", [])

        adjusted_confidence = max(0.0, min(1.0,
            state["confidence_score"] + confidence_adj
        ))

        return {
            "validation_passed": validation_passed,
            "validation_notes": issues,
            "confidence_score": adjusted_confidence,
            "current_node": "validator",
            "total_tokens_used": state["total_tokens_used"] + tokens,
            "llm_calls": state["llm_calls"] + 1,
            "tool_calls": state["tool_calls"] + [{
                "tool_name": "validator",
                "input": {"draft_length": len(draft)},
                "output": {"passed": validation_passed, "issues": len(issues)},
                "latency_ms": duration_ms,
            }],
        }
    except Exception as e:
        logger.warning(f"Validator failed (passing through): {e}")
        return {
            "validation_passed": True,
            "validation_notes": [f"Validation skipped: {str(e)}"],
            "current_node": "validator",
        }
