"""
LangGraph Agent State Schema
Defines the complete state that flows through all agent workflow nodes.
All fields are explicitly typed for LangGraph's state management.
"""
from __future__ import annotations

from typing import Any, TypedDict


class ToolCall(TypedDict):
    tool_name: str
    input: dict[str, Any]
    output: Any
    latency_ms: int


class CitationSource(TypedDict):
    chunk_id: str
    document_id: str
    filename: str
    content_preview: str
    relevance_score: float


class AgentState(TypedDict):
    # ─── Session ─────────────────────────────────────────────
    session_id: str
    workflow_type: str
    original_query: str
    input_context: dict[str, Any]

    # ─── Planning ────────────────────────────────────────────
    sub_tasks: list[str]
    execution_plan: list[str]
    current_step: int

    # ─── Retrieval ───────────────────────────────────────────
    retrieval_queries: list[str]
    retrieved_chunks: list[dict[str, Any]]   # Serialized ChunkResult
    entity_context: list[dict[str, Any]]
    retrieval_attempts: int

    # ─── Reasoning ───────────────────────────────────────────
    intermediate_thoughts: list[str]
    current_hypothesis: str
    confidence_score: float
    reasoning_chain: list[str]
    hypotheses: list[dict[str, Any]]         # [{hypothesis, confidence, evidence}]

    # ─── Response ────────────────────────────────────────────
    draft_response: str
    validation_passed: bool
    validation_notes: list[str]
    final_response: str
    source_citations: list[CitationSource]

    # ─── Metadata ────────────────────────────────────────────
    total_tokens_used: int
    llm_calls: int
    tool_calls: list[ToolCall]
    errors: list[str]
    current_node: str


def initial_state(
    session_id: str,
    workflow_type: str,
    query: str,
    input_context: dict | None = None,
) -> AgentState:
    """Create fresh initial state for a new agent session."""
    return AgentState(
        session_id=session_id,
        workflow_type=workflow_type,
        original_query=query,
        input_context=input_context or {},
        sub_tasks=[],
        execution_plan=[],
        current_step=0,
        retrieval_queries=[],
        retrieved_chunks=[],
        entity_context=[],
        retrieval_attempts=0,
        intermediate_thoughts=[],
        current_hypothesis="",
        confidence_score=0.0,
        reasoning_chain=[],
        hypotheses=[],
        draft_response="",
        validation_passed=False,
        validation_notes=[],
        final_response="",
        source_citations=[],
        total_tokens_used=0,
        llm_calls=0,
        tool_calls=[],
        errors=[],
        current_node="start",
    )
