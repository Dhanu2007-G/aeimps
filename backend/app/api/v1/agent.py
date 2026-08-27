"""Agent Workflow API — run, poll, list, continue sessions."""
from __future__ import annotations
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, Query
from app.api.deps import CurrentAPIKey, DBSession, RateLimited
from app.schemas import (
    AgentContinueRequest, AgentListResponse, AgentResult,
    AgentRunRequest, AgentRunResponse, AgentSessionResponse,
    AgentStepSummary, CitationSource, EvaluationScores,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/run", response_model=AgentRunResponse, status_code=202)
async def run_agent(
    request: AgentRunRequest,
    background_tasks: BackgroundTasks,
    _: RateLimited = None,
    api_key: CurrentAPIKey = None,
    db: DBSession = None,
):
    """Start an agent workflow session. Returns session_id for polling."""
    from app.services.agent.session_manager import get_session_manager

    mgr = get_session_manager()
    session_id = await mgr.create_session(
        workflow_type=request.workflow,
        query=request.input,
        input_context=request.context.model_dump(),
        config=request.config.model_dump(),
        api_key_id=api_key["id"],
    )

    # Run workflow in background
    background_tasks.add_task(
        mgr.run_workflow,
        session_id=session_id,
        workflow_type=request.workflow,
        query=request.input,
        input_context=request.context.model_dump(),
        config=request.config.model_dump(),
    )

    return AgentRunResponse(
        session_id=session_id,
        workflow=request.workflow,
        estimated_duration_seconds=_estimate_duration(request.workflow),
    )


@router.get("/session/{session_id}", response_model=AgentSessionResponse)
async def get_session(
    session_id: str,
    _: RateLimited = None,
    db: DBSession = None,
):
    """Poll session status, current node, steps, and result."""
    from sqlalchemy import select
    from app.db.models import AgentSession, AgentStep, Evaluation

    result = await db.execute(
        select(AgentSession).where(AgentSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        from fastapi import HTTPException
        raise HTTPException(404, detail=f"Session not found: {session_id}")

    # Load steps
    steps_result = await db.execute(
        select(AgentStep)
        .where(AgentStep.session_id == session.id)
        .order_by(AgentStep.step_index)
    )
    steps = steps_result.scalars().all()

    # Load evaluation if exists
    eval_result = await db.execute(
        select(Evaluation)
        .where(Evaluation.session_id == session.id)
        .order_by(Evaluation.created_at.desc())
    )
    evaluation = eval_result.scalars().first()

    agent_result = None
    if session.status == "COMPLETED" and session.final_response:
        meta = session.response_metadata or {}
        citations = [
            CitationSource(**c)
            for c in meta.get("citations", [])
            if isinstance(c, dict)
        ]
        agent_result = AgentResult(
            response=session.final_response,
            confidence=session.confidence_score or 0.0,
            sources=citations,
            total_tokens=session.total_tokens_used or 0,
        )

    eval_scores = None
    if evaluation:
        eval_scores = EvaluationScores(
            faithfulness=evaluation.faithfulness,
            context_recall=evaluation.context_recall,
            context_precision=evaluation.context_precision,
            answer_relevance=evaluation.answer_relevance,
            hallucination_score=evaluation.hallucination_score,
            overall_score=evaluation.overall_score,
        )

    return AgentSessionResponse(
        session_id=session.session_id,
        workflow=session.workflow_type,
        status=session.status,
        input_query=session.input_query,
        steps=[
            AgentStepSummary(
                node=s.node_name,
                step_index=s.step_index,
                summary=f"{s.node_name} completed",
                tool_calls_count=len(s.tool_calls or []),
                duration_ms=s.duration_ms,
                created_at=s.created_at,
            )
            for s in steps
        ],
        result=agent_result,
        evaluation=eval_scores,
        total_duration_ms=session.total_duration_ms,
        created_at=session.created_at,
        completed_at=session.completed_at,
        error=session.error_message,
    )


@router.get("/sessions", response_model=AgentListResponse)
async def list_sessions(
    workflow: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(None),
    _: RateLimited = None,
    db: DBSession = None,
):
    from sqlalchemy import select, desc
    from app.db.models import AgentSession

    q = select(AgentSession).order_by(desc(AgentSession.created_at)).limit(limit + 1)
    if workflow:
        q = q.where(AgentSession.workflow_type == workflow)
    if status:
        q = q.where(AgentSession.status == status)
    if cursor:
        q = q.where(AgentSession.session_id < cursor)

    result = await db.execute(q)
    sessions = result.scalars().all()

    next_cursor = None
    if len(sessions) > limit:
        sessions = sessions[:limit]
        next_cursor = sessions[-1].session_id

    return AgentListResponse(
        sessions=[
            AgentSessionResponse(
                session_id=s.session_id,
                workflow=s.workflow_type,
                status=s.status,
                input_query=s.input_query,
                confidence_score=s.confidence_score,
                total_duration_ms=s.total_duration_ms,
                created_at=s.created_at,
                completed_at=s.completed_at,
                error=s.error_message,
            )
            for s in sessions
        ],
        next_cursor=next_cursor,
    )


@router.post("/session/{session_id}/continue", response_model=AgentRunResponse)
async def continue_session(
    session_id: str,
    request: AgentContinueRequest,
    background_tasks: BackgroundTasks,
    _: RateLimited = None,
    db: DBSession = None,
):
    """Resume an AWAITING_INPUT session with human input."""
    from sqlalchemy import select, update
    from app.db.models import AgentSession

    result = await db.execute(
        select(AgentSession).where(AgentSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        from fastapi import HTTPException
        raise HTTPException(404, detail=f"Session not found: {session_id}")

    if session.status not in ("AWAITING_INPUT", "FAILED"):
        from fastapi import HTTPException
        raise HTTPException(400, detail=f"Session cannot be continued in status: {session.status}")

    await db.execute(
        update(AgentSession)
        .where(AgentSession.session_id == session_id)
        .values(status="RUNNING")
    )

    from app.services.agent.session_manager import get_session_manager
    mgr = get_session_manager()
    combined_query = f"{session.input_query}\n\nUser follow-up: {request.input}"

    background_tasks.add_task(
        mgr.run_workflow,
        session_id=session_id,
        workflow_type=session.workflow_type,
        query=combined_query,
        input_context=session.input_context or {},
        config={"max_iterations": 5},
    )

    return AgentRunResponse(session_id=session_id, workflow=session.workflow_type)


@router.delete("/session/{session_id}")
async def cancel_session(
    session_id: str,
    _: RateLimited = None,
    db: DBSession = None,
):
    from sqlalchemy import select, update
    from app.db.models import AgentSession

    result = await db.execute(
        select(AgentSession).where(AgentSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        from fastapi import HTTPException
        raise HTTPException(404, detail=f"Session not found: {session_id}")

    await db.execute(
        update(AgentSession)
        .where(AgentSession.session_id == session_id)
        .values(status="CANCELLED")
    )

    # Clear Redis checkpoint
    try:
        from app.db.redis import get_redis
        redis = get_redis()
        keys = await redis.keys(f"checkpoint:{session_id}:*")
        if keys:
            await redis.delete(*keys)
    except Exception:
        pass

    return {"session_id": session_id, "status": "CANCELLED"}


def _estimate_duration(workflow: str) -> int:
    return {"incident_investigation": 60, "question_answering": 20,
            "summarization": 30, "root_cause_analysis": 60, "remediation": 45}.get(workflow, 30)
