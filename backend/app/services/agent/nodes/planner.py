"""
Agent Planner Node
Decomposes user query into sub-tasks and execution plan.
"""
from __future__ import annotations
import logging
import time
from app.services.agent.state import AgentState
from app.services.llm.abstraction import get_llm_client

logger = logging.getLogger(__name__)


async def planner_node(state: AgentState) -> dict:
    """Analyze query, decompose into sub-tasks, create execution plan."""
    start = time.monotonic()
    llm = get_llm_client()

    system = """You are an enterprise AI planner. Analyze the query and create a structured plan.
Output ONLY valid JSON with keys: sub_tasks (list of strings), execution_plan (list of steps), 
retrieval_queries (list of 2-4 search queries to gather context)."""

    prompt = f"""Query: {state['original_query']}
Workflow: {state['workflow_type']}
Context: {state.get('input_context', {})}

Create a JSON execution plan with sub_tasks, execution_plan, and retrieval_queries."""

    try:
        result, tokens = await llm.complete_structured(prompt, system=system)
        duration_ms = int((time.monotonic() - start) * 1000)

        return {
            "sub_tasks": result.get("sub_tasks", [state["original_query"]]),
            "execution_plan": result.get("execution_plan", ["retrieve", "reason", "respond"]),
            "retrieval_queries": result.get("retrieval_queries", [state["original_query"]]),
            "total_tokens_used": state["total_tokens_used"] + tokens,
            "llm_calls": state["llm_calls"] + 1,
            "current_node": "planner",
            "tool_calls": state["tool_calls"] + [{
                "tool_name": "llm_planner",
                "input": {"query": state["original_query"]},
                "output": result,
                "latency_ms": duration_ms,
            }],
        }
    except Exception as e:
        logger.error(f"Planner node failed: {e}")
        return {
            "sub_tasks": [state["original_query"]],
            "execution_plan": ["retrieve", "reason", "respond"],
            "retrieval_queries": [state["original_query"]],
            "errors": state["errors"] + [f"Planner failed: {str(e)}"],
            "current_node": "planner",
        }
