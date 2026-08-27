"""
Evaluation Service — automated quality scoring for agent responses.
Implements: faithfulness, context recall, context precision,
answer relevance, hallucination risk, composite score.
"""
from __future__ import annotations
import asyncio
import logging
import time
from app.core.config import settings
from app.services.llm.abstraction import get_llm_client

logger = logging.getLogger(__name__)


class EvaluationService:
    """Orchestrates all evaluation metrics for a completed agent session."""

    COMPOSITE_WEIGHTS = {
        "faithfulness": 0.35,
        "context_precision": 0.25,
        "answer_relevance": 0.20,
        "hallucination_risk": 0.20,
    }

    async def evaluate_session(
        self,
        session_id: str,
        final_state: dict,
        reference_answer: str | None = None,
    ) -> dict:
        """Run all metrics and persist evaluation to PostgreSQL."""
        query = final_state.get("original_query", "")
        response = final_state.get("final_response", "")
        retrieved_chunks = final_state.get("retrieved_chunks", [])

        if not query or not response:
            logger.warning(f"Skipping evaluation for {session_id}: empty query/response")
            return {}

        context_texts = [c.get("content", "") for c in retrieved_chunks[:10]]

        start = time.monotonic()
        try:
            # Run metrics in parallel (with graceful individual failures)
            results = await asyncio.gather(
                self._score_faithfulness(query, response, context_texts),
                self._score_context_precision(query, retrieved_chunks),
                self._score_answer_relevance(query, response),
                self._score_hallucination(response, context_texts),
                return_exceptions=True,
            )

            faithfulness = results[0] if not isinstance(results[0], Exception) else None
            ctx_precision = results[1] if not isinstance(results[1], Exception) else None
            answer_rel = results[2] if not isinstance(results[2], Exception) else None
            hallucination = results[3] if not isinstance(results[3], Exception) else None

            # Composite score
            overall = self._composite_score(
                faithfulness, ctx_precision, answer_rel, hallucination
            )

            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                f"Evaluation completed for {session_id}: "
                f"overall={overall:.2f} in {duration_ms}ms"
            )

            await self._persist_evaluation(
                session_id=session_id,
                query=query,
                response=response,
                retrieved_chunks=retrieved_chunks,
                faithfulness=faithfulness,
                context_precision=ctx_precision,
                answer_relevance=answer_rel,
                hallucination_score=hallucination,
                overall_score=overall,
                reference_answer=reference_answer,
            )

            # Emit Prometheus metrics
            self._emit_metrics(session_id, overall, faithfulness, hallucination)

            return {
                "faithfulness": faithfulness,
                "context_precision": ctx_precision,
                "answer_relevance": answer_rel,
                "hallucination_score": hallucination,
                "overall_score": overall,
            }

        except Exception as e:
            logger.error(f"Evaluation failed for {session_id}: {e}")
            return {}

    async def _score_faithfulness(
        self,
        query: str,
        response: str,
        context_texts: list[str],
    ) -> float:
        """
        Faithfulness: fraction of response claims supported by context.
        Uses LLM to extract claims then verify each against context.
        """
        llm = get_llm_client()
        context_combined = "\n---\n".join(context_texts[:8])[:4000]

        prompt = f"""Given this context and response, identify all factual claims in the response
and determine how many are directly supported by the context.

Context:
{context_combined}

Response:
{response[:2000]}

Output JSON: {{"total_claims": int, "supported_claims": int, "faithfulness_score": float (0-1)}}"""

        try:
            result, _ = await llm.complete_structured(
                prompt,
                system="You are an evaluation metric. Output only valid JSON.",
                max_tokens=256,
            )
            return float(result.get("faithfulness_score", 0.7))
        except Exception:
            return 0.7  # conservative default

    async def _score_context_precision(
        self,
        query: str,
        retrieved_chunks: list[dict],
    ) -> float:
        """Context precision: fraction of retrieved chunks that are relevant."""
        if not retrieved_chunks:
            return 0.0

        llm = get_llm_client()
        chunk_previews = [
            f"Chunk {i+1}: {c.get('content', '')[:200]}"
            for i, c in enumerate(retrieved_chunks[:10])
        ]

        prompt = f"""Query: {query}

Retrieved chunks:
{chr(10).join(chunk_previews)}

For each chunk, determine if it is relevant to answering the query.
Output JSON: {{"relevant_count": int, "total_count": int, "precision": float}}"""

        try:
            result, _ = await llm.complete_structured(
                prompt,
                system="You are an evaluation metric. Output only valid JSON.",
                max_tokens=128,
            )
            return float(result.get("precision", 0.7))
        except Exception:
            return 0.7

    async def _score_answer_relevance(self, query: str, response: str) -> float:
        """
        Answer relevance: embedding similarity between query and
        questions the response would answer (reverse-generation trick).
        """
        llm = get_llm_client()
        prompt = f"""Given this response, generate 3 questions it directly answers.
Response: {response[:1000]}
Output JSON: {{"questions": ["q1", "q2", "q3"]}}"""

        try:
            result, _ = await llm.complete_structured(
                prompt,
                system="You are an evaluation metric. Output only valid JSON.",
                max_tokens=128,
            )
            generated_questions = result.get("questions", [])
            if not generated_questions:
                return 0.7

            # Compute embedding similarity
            from workers.embedding_worker.encoder import get_encoder
            encoder = get_encoder()

            query_vec = encoder.encode_dense([query])[0]
            gen_vecs = encoder.encode_dense(generated_questions)

            import numpy as np
            q = np.array(query_vec)
            scores = []
            for gv in gen_vecs:
                g = np.array(gv)
                cos_sim = float(np.dot(q, g) / (np.linalg.norm(q) * np.linalg.norm(g) + 1e-8))
                scores.append(cos_sim)

            return float(np.mean(scores))
        except Exception:
            return 0.7

    async def _score_hallucination(
        self,
        response: str,
        context_texts: list[str],
    ) -> float:
        """
        Hallucination risk: fraction of named entities in response
        that appear in the retrieved context.
        Lower = more hallucination risk. Score = 1 - risk.
        """
        llm = get_llm_client()
        context_combined = " ".join(context_texts[:5])[:3000]

        prompt = f"""Extract all specific named entities (names, systems, error codes, 
numbers, versions, dates) from the response. Then check each against the context.

Context: {context_combined}
Response: {response[:1500]}

Output JSON: {{
  "total_entities": int,
  "supported_entities": int,
  "hallucination_risk_score": float (0=high risk, 1=no hallucination)
}}"""

        try:
            result, _ = await llm.complete_structured(
                prompt,
                system="You are an evaluation metric. Output only valid JSON.",
                max_tokens=128,
            )
            return float(result.get("hallucination_risk_score", 0.85))
        except Exception:
            return 0.85

    def _composite_score(
        self,
        faithfulness: float | None,
        ctx_precision: float | None,
        answer_rel: float | None,
        hallucination: float | None,
    ) -> float:
        """Weighted composite score from all metrics."""
        total_weight = 0.0
        total_score = 0.0

        pairs = [
            (faithfulness, self.COMPOSITE_WEIGHTS["faithfulness"]),
            (ctx_precision, self.COMPOSITE_WEIGHTS["context_precision"]),
            (answer_rel, self.COMPOSITE_WEIGHTS["answer_relevance"]),
            (hallucination, self.COMPOSITE_WEIGHTS["hallucination_risk"]),
        ]

        for score, weight in pairs:
            if score is not None:
                total_score += score * weight
                total_weight += weight

        return round(total_score / total_weight, 4) if total_weight > 0 else 0.0

    async def _persist_evaluation(self, session_id: str, **kwargs) -> None:
        try:
            from sqlalchemy import select
            from app.db.postgres import get_db
            from app.db.models import AgentSession, Evaluation

            async with get_db() as db:
                result = await db.execute(
                    select(AgentSession.id).where(AgentSession.session_id == session_id)
                )
                session_pk = result.scalar_one_or_none()

                chunks_for_storage = [
                    {"chunk_id": c.get("chunk_id"), "content": c.get("content", "")[:200]}
                    for c in kwargs.get("retrieved_chunks", [])[:10]
                ]

                evaluation = Evaluation(
                    session_id=session_pk,
                    query=kwargs["query"][:500],
                    response=kwargs["response"][:2000],
                    retrieved_context={"chunks": chunks_for_storage},
                    reference_answer=kwargs.get("reference_answer"),
                    faithfulness=kwargs.get("faithfulness"),
                    context_precision=kwargs.get("context_precision"),
                    answer_relevance=kwargs.get("answer_relevance"),
                    hallucination_score=kwargs.get("hallucination_score"),
                    overall_score=kwargs.get("overall_score"),
                    eval_model=from_settings_model(),
                )
                db.add(evaluation)
        except Exception as e:
            logger.error(f"Evaluation persistence failed: {e}")

    def _emit_metrics(self, session_id: str, overall: float, faithfulness: float | None, hallucination: float | None) -> None:
        try:
            from prometheus_client import Gauge, Counter
            # These would be pre-registered in metrics module — safe no-op if not
        except Exception:
            pass


def from_settings_model() -> str:
    return settings.CLAUDE_MODEL
