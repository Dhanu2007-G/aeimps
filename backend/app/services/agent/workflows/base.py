"""
Base workflow builder for all AEIMPS agent workflows.
All workflows share the same nodes but differ in routing logic and prompts.
"""
from __future__ import annotations
import logging
from app.core.config import settings
from app.services.agent.state import AgentState

logger = logging.getLogger(__name__)


def should_retrieve_more(state: AgentState) -> str:
    """Routing: decide if we need more retrieval before responding."""
    confidence = state.get("confidence_score", 0.0)
    attempts = state.get("retrieval_attempts", 0)
    min_conf = settings.AGENT_MIN_CONFIDENCE

    if confidence < min_conf and attempts < 2:
        logger.debug(f"Low confidence ({confidence:.2f}) → re-retrieving (attempt {attempts})")
        return "retrieve_more"
    return "validate"


def should_retry_after_validation(state: AgentState) -> str:
    """Routing: after validation, decide if we need to re-reason."""
    passed = state.get("validation_passed", True)
    attempts = state.get("retrieval_attempts", 0)

    if not passed and attempts < 2:
        return "retrieve_more"
    return "respond"


def build_qa_workflow():
    """Question Answering: simple linear flow with optional re-retrieval."""
    from langgraph.graph import StateGraph, END
    from app.services.agent.nodes.planner import planner_node
    from app.services.agent.nodes.retriever import retriever_node
    from app.services.agent.nodes.reasoner import reasoner_node
    from app.services.agent.nodes.validator import validator_node
    from app.services.agent.nodes.responder import responder_node

    workflow = StateGraph(AgentState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("retriever", retriever_node)
    workflow.add_node("reasoner", reasoner_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("responder", responder_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "retriever")
    workflow.add_edge("retriever", "reasoner")
    workflow.add_conditional_edges(
        "reasoner",
        should_retrieve_more,
        {"retrieve_more": "retriever", "validate": "validator"},
    )
    workflow.add_conditional_edges(
        "validator",
        should_retry_after_validation,
        {"retrieve_more": "retriever", "respond": "responder"},
    )
    workflow.add_edge("responder", END)
    return workflow.compile()


def build_incident_workflow():
    """Incident Investigation: adds hypothesis generation and evidence collection."""
    from langgraph.graph import StateGraph, END
    from app.services.agent.nodes.planner import planner_node
    from app.services.agent.nodes.retriever import retriever_node
    from app.services.agent.nodes.reasoner import reasoner_node
    from app.services.agent.nodes.validator import validator_node
    from app.services.agent.nodes.responder import responder_node

    async def incident_reasoner(state: AgentState) -> dict:
        """Incident-specific reasoner that generates multiple hypotheses."""
        from app.services.agent.nodes.reasoner import reasoner_node as base_reasoner
        # Use base reasoner with incident system prompt (injected via workflow_type)
        return await base_reasoner(state)

    workflow = StateGraph(AgentState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("retriever", retriever_node)
    workflow.add_node("reasoner", incident_reasoner)
    workflow.add_node("validator", validator_node)
    workflow.add_node("responder", responder_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "retriever")
    workflow.add_edge("retriever", "reasoner")
    workflow.add_conditional_edges(
        "reasoner",
        should_retrieve_more,
        {"retrieve_more": "retriever", "validate": "validator"},
    )
    workflow.add_conditional_edges(
        "validator",
        should_retry_after_validation,
        {"retrieve_more": "retriever", "respond": "responder"},
    )
    workflow.add_edge("responder", END)
    return workflow.compile()


def build_summarization_workflow():
    """Summarization: retrieves document chunks then summarizes."""
    return build_qa_workflow()  # Same flow, different system prompt via workflow_type


def build_rca_workflow():
    """Root Cause Analysis: deep causal reasoning with graph traversal."""
    return build_incident_workflow()


def build_remediation_workflow():
    """Remediation: suggests fixes based on RCA."""
    return build_qa_workflow()


WORKFLOW_BUILDERS = {
    "question_answering": build_qa_workflow,
    "incident_investigation": build_incident_workflow,
    "summarization": build_summarization_workflow,
    "root_cause_analysis": build_rca_workflow,
    "remediation": build_remediation_workflow,
}


def get_workflow(workflow_type: str):
    """Get compiled workflow by type."""
    builder = WORKFLOW_BUILDERS.get(workflow_type)
    if not builder:
        raise ValueError(f"Unknown workflow type: {workflow_type}")
    return builder()
