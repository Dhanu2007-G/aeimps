"""Evaluation API — trigger, retrieve, and summarize evaluation results."""
from __future__ import annotations
import logging
import uuid
from fastapi import APIRouter, Query
from app.api.deps import CurrentAPIKey, DBSession, RateLimited
from app.schemas import (
    BatchEvaluationRequest, BatchEvaluationResponse,
    EvaluationResultResponse, EvaluationScores, EvaluationSummaryResponse,
    EvaluationTriggerResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/session/{session_id}", response_model=EvaluationTriggerResponse, status_code=202)
async def trigger_evaluation(
    session_id: str,
    background_tasks=None,
    _: RateLimited = None,
    db: DBSession = None,
):
    """Trigger evaluation for a completed session."""
    from sqlalchemy import select
    from app.db.models import AgentSession
    from fastapi import BackgroundTasks

    result = await db.execute(
        select(AgentSession).where(AgentSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        from fastapi import HTTPException
        raise HTTPException(404, detail=f"Session not found: {session_id}")

    if session.status != "COMPLETED":
        from fastapi import HTTPException
        raise HTTPException(400, detail="Can only evaluate COMPLETED sessions")

    eval_id = str(uuid.uuid4())

    async def run_eval():
        from app.services.evaluation.evaluator import EvaluationService
        ev = EvaluationService()
        state = {
            "original_query": session.input_query,
            "final_response": session.final_response or "",
            "retrieved_chunks": (session.response_metadata or {}).get("citations", []),
        }
        await ev.evaluate_session(session_id, state)

    import asyncio
    asyncio.create_task(run_eval())

    return EvaluationTriggerResponse(
        evaluation_id=eval_id,
        session_id=session_id,
        status="RUNNING",
    )


@router.post("/batch", response_model=BatchEvaluationResponse, status_code=202)
async def batch_evaluate(
    request: BatchEvaluationRequest,
    _: RateLimited = None,
    db: DBSession = None,
):
    import asyncio
    from sqlalchemy import select
    from app.db.models import AgentSession
    from app.services.evaluation.evaluator import EvaluationService

    async def eval_all():
        ev = EvaluationService()
        for sid in request.session_ids:
            try:
                result = await db.execute(
                    select(AgentSession).where(AgentSession.session_id == sid)
                )
                session = result.scalar_one_or_none()
                if session and session.status == "COMPLETED":
                    state = {
                        "original_query": session.input_query,
                        "final_response": session.final_response or "",
                        "retrieved_chunks": [],
                    }
                    await ev.evaluate_session(sid, state)
            except Exception as e:
                logger.error(f"Batch eval failed for {sid}: {e}")

    asyncio.create_task(eval_all())
    return BatchEvaluationResponse(
        batch_id=str(uuid.uuid4()),
        evaluations_queued=len(request.session_ids),
    )


@router.get("/summary", response_model=EvaluationSummaryResponse)
async def evaluation_summary(
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    workflow: str | None = Query(None),
    _: RateLimited = None,
    db: DBSession = None,
):
    from sqlalchemy import select, func
    from app.db.models import Evaluation, AgentSession

    q = select(Evaluation)
    if workflow:
        q = q.join(AgentSession, AgentSession.id == Evaluation.session_id).where(
            AgentSession.workflow_type == workflow
        )

    result = await db.execute(q.order_by(Evaluation.created_at.desc()).limit(500))
    evals = result.scalars().all()

    if not evals:
        return EvaluationSummaryResponse(
            period={"from": from_date or "all", "to": to_date or "now"},
            total_evaluations=0,
            average_scores=EvaluationScores(),
            score_distribution={},
        )

    def avg(vals):
        v = [x for x in vals if x is not None]
        return round(sum(v) / len(v), 4) if v else None

    # Score distribution buckets
    dist = {"0.0-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
    for e in evals:
        s = e.overall_score or 0
        if s < 0.4: dist["0.0-0.4"] += 1
        elif s < 0.6: dist["0.4-0.6"] += 1
        elif s < 0.8: dist["0.6-0.8"] += 1
        else: dist["0.8-1.0"] += 1

    worst = sorted(
        [e for e in evals if e.overall_score is not None],
        key=lambda x: x.overall_score
    )[:5]

    return EvaluationSummaryResponse(
        period={"from": from_date or "all", "to": to_date or "now"},
        total_evaluations=len(evals),
        average_scores=EvaluationScores(
            faithfulness=avg([e.faithfulness for e in evals]),
            context_precision=avg([e.context_precision for e in evals]),
            answer_relevance=avg([e.answer_relevance for e in evals]),
            hallucination_score=avg([e.hallucination_score for e in evals]),
            overall_score=avg([e.overall_score for e in evals]),
        ),
        score_distribution=dist,
        worst_performing=[
            {"session_id": str(e.session_id), "score": e.overall_score,
             "query": e.query[:100]}
            for e in worst
        ],
    )
