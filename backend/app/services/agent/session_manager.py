"""
Agent Session Manager
Handles workflow instantiation, async execution, state persistence,
and session lifecycle management.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.services.agent.state import AgentState, initial_state

logger = logging.getLogger(__name__)


class AgentSessionManager:
    """Manages the full lifecycle of agent workflow sessions."""

    async def create_session(
        self,
        workflow_type: str,
        query: str,
        input_context: dict,
        config: dict,
        api_key_id: str | None = None,
    ) -> str:
        """Create a new agent session and persist to PostgreSQL."""
        session_id = f"sess_{uuid.uuid4().hex[:16]}"

        from app.db.postgres import get_db
        from app.db.models import AgentSession

        async with get_db() as db:
            session = AgentSession(
                session_id=session_id,
                workflow_type=workflow_type,
                status="INITIALIZING",
                input_query=query,
                input_context=input_context,
                api_key_id=api_key_id,
            )
            db.add(session)

        logger.info(f"Agent session created: {session_id} [{workflow_type}]")
        return session_id

    async def run_workflow(
        self,
        session_id: str,
        workflow_type: str,
        query: str,
        input_context: dict,
        config: dict,
    ) -> None:
        """
        Execute the full agent workflow asynchronously.
        Updates session status in PostgreSQL throughout execution.
        """
        start_time = time.monotonic()

        try:
            await self._update_session_status(session_id, "RUNNING")

            # Build initial state
            state = initial_state(
                session_id=session_id,
                workflow_type=workflow_type,
                query=query,
                input_context=input_context,
            )

            # Get compiled workflow
            from app.services.agent.workflows.base import get_workflow
            workflow = get_workflow(workflow_type)

            # Execute with timeout
            timeout = config.get("timeout_seconds", 300)
            try:
                final_state = await asyncio.wait_for(
                    workflow.ainvoke(
                        state,
                        config={
                            "configurable": {"thread_id": session_id},
                            "recursion_limit": config.get("max_iterations", 8) * 3,
                        },
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Session {session_id} timed out after {timeout}s")
                await self._update_session_status(session_id, "TIMED_OUT",
                                                   error=f"Workflow timed out after {timeout}s")
                return

            duration_ms = int((time.monotonic() - start_time) * 1000)

            # Persist agent steps
            await self._persist_steps(session_id, final_state)

            # If responder didn't persist (edge case), do it now
            if not final_state.get("final_response"):
                final_response = final_state.get("draft_response", "No response generated.")
            else:
                final_response = final_state["final_response"]

            # Update final session state
            async with _get_db_context() as db:
                from sqlalchemy import update
                from app.db.models import AgentSession
                await db.execute(
                    update(AgentSession)
                    .where(AgentSession.session_id == session_id)
                    .values(
                        status="COMPLETED",
                        final_response=final_response,
                        confidence_score=final_state.get("confidence_score", 0.0),
                        total_duration_ms=duration_ms,
                        total_tokens_used=final_state.get("total_tokens_used", 0),
                        completed_at=datetime.now(timezone.utc),
                        response_metadata={
                            "citations": final_state.get("source_citations", []),
                            "tool_calls": len(final_state.get("tool_calls", [])),
                            "retrieval_attempts": final_state.get("retrieval_attempts", 0),
                        },
                    )
                )

            logger.info(
                f"Session {session_id} completed in {duration_ms}ms "
                f"(confidence={final_state.get('confidence_score', 0):.2f})"
            )

            # Trigger evaluation if enabled
            if config.get("include_evaluation", True) and settings.EVAL_ENABLED:
                asyncio.create_task(self._trigger_evaluation(session_id, final_state))

        except Exception as e:
            logger.error(f"Session {session_id} failed: {e}", exc_info=True)
            await self._update_session_status(session_id, "FAILED", error=str(e))

    async def _persist_steps(self, session_id: str, final_state: AgentState) -> None:
        """Write tool calls as agent steps to PostgreSQL."""
        tool_calls = final_state.get("tool_calls", [])
        if not tool_calls:
            return

        try:
            from app.db.postgres import get_db
            from app.db.models import AgentSession, AgentStep
            from sqlalchemy import select

            async with get_db() as db:
                result = await db.execute(
                    select(AgentSession.id).where(AgentSession.session_id == session_id)
                )
                session_pk = result.scalar_one_or_none()
                if not session_pk:
                    return

                for i, tc in enumerate(tool_calls):
                    step = AgentStep(
                        session_id=session_pk,
                        step_index=i,
                        node_name=tc.get("tool_name", f"step_{i}"),
                        tool_calls=[tc],
                        tokens_used=0,
                        duration_ms=tc.get("latency_ms"),
                    )
                    db.add(step)
        except Exception as e:
            logger.error(f"Step persistence failed: {e}")

    async def _update_session_status(
        self,
        session_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        try:
            from sqlalchemy import update
            from app.db.models import AgentSession
            async with _get_db_context() as db:
                values = {"status": status, "updated_at": datetime.now(timezone.utc)}
                if error:
                    values["error_message"] = error
                await db.execute(
                    update(AgentSession)
                    .where(AgentSession.session_id == session_id)
                    .values(**values)
                )
        except Exception as e:
            logger.error(f"Status update failed: {e}")

    async def _trigger_evaluation(
        self, session_id: str, final_state: AgentState
    ) -> None:
        try:
            from app.services.evaluation.evaluator import EvaluationService
            evaluator = EvaluationService()
            await evaluator.evaluate_session(session_id, final_state)
        except Exception as e:
            logger.warning(f"Evaluation trigger failed (non-critical): {e}")


from contextlib import asynccontextmanager
from app.db.postgres import get_db as _pg_get_db


@asynccontextmanager
async def _get_db_context():
    async with _pg_get_db() as db:
        yield db


_session_manager: AgentSessionManager | None = None


def get_session_manager() -> AgentSessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = AgentSessionManager()
    return _session_manager
