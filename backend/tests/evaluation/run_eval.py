#!/usr/bin/env python3
"""
Offline evaluation runner.
Loads test dataset, runs retrieval + agent, scores results.
Reports pass/fail against threshold targets.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

DATASET_PATH = Path(__file__).parent / "datasets" / "question_answering.jsonl"
FAITHFULNESS_THRESHOLD = float(os.getenv("EVAL_MIN_FAITHFULNESS", "0.70"))
OVERALL_THRESHOLD = float(os.getenv("EVAL_MIN_OVERALL", "0.60"))


async def run_evaluation():
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}")
        print("Skipping evaluation (no ground truth data yet).")
        return True

    from app.services.retrieval.orchestrator import RetrievalOrchestrator
    from app.services.evaluation.evaluator import EvaluationService
    from app.services.llm.abstraction import get_llm_client

    orch = RetrievalOrchestrator()
    evaluator = EvaluationService()
    llm = get_llm_client()

    results = []
    items = [json.loads(l) for l in DATASET_PATH.read_text().splitlines() if l.strip()]

    print(f"\nRunning evaluation on {len(items)} items...\n")

    for i, item in enumerate(items):
        query = item["query"]
        reference = item.get("answer", "")

        t = time.monotonic()
        try:
            # Retrieve context
            ret = await orch.search(query=query, mode="hybrid", top_k=6)
            context = [{"content": r.content} for r in ret.results]

            # Generate response
            ctx_text = "\n---\n".join(c["content"] for c in context[:5])
            response, _ = await llm.complete(
                f"Answer based on context:\n{ctx_text}\n\nQ: {query}",
                max_tokens=512,
            )

            # Score
            scores = await evaluator.evaluate_session(
                session_id=f"eval-{i}",
                final_state={
                    "original_query": query,
                    "final_response": response,
                    "retrieved_chunks": [{"content": c["content"]} for c in context],
                },
                reference_answer=reference,
            )

            results.append({
                "query": query[:60],
                "overall": scores.get("overall_score", 0),
                "faithfulness": scores.get("faithfulness", 0),
                "latency_ms": int((time.monotonic() - t) * 1000),
            })
            status = "✓" if (scores.get("overall_score", 0) or 0) >= OVERALL_THRESHOLD else "✗"
            print(f"  [{i+1:2d}/{len(items)}] {status} {query[:50]:<50} "
                  f"overall={scores.get('overall_score', 0):.2f}")

        except Exception as e:
            print(f"  [{i+1:2d}/{len(items)}] ERROR: {e}")
            results.append({"query": query[:60], "overall": 0, "faithfulness": 0, "latency_ms": 0})

    # Summary
    if results:
        avg_overall = sum(r["overall"] for r in results) / len(results)
        avg_faith = sum(r["faithfulness"] for r in results) / len(results)
        avg_lat = sum(r["latency_ms"] for r in results) / len(results)
        pass_rate = sum(1 for r in results if r["overall"] >= OVERALL_THRESHOLD) / len(results)

        print(f"\n{'='*60}")
        print(f"EVALUATION SUMMARY ({len(results)} items)")
        print(f"  Avg Overall Score:    {avg_overall:.3f}  (threshold: {OVERALL_THRESHOLD})")
        print(f"  Avg Faithfulness:     {avg_faith:.3f}  (threshold: {FAITHFULNESS_THRESHOLD})")
        print(f"  Pass Rate:            {pass_rate:.1%}")
        print(f"  Avg Latency:          {avg_lat:.0f}ms")

        passed = avg_overall >= OVERALL_THRESHOLD and avg_faith >= FAITHFULNESS_THRESHOLD
        print(f"\n  {'✓ EVALUATION PASSED' if passed else '✗ EVALUATION FAILED'}")
        print(f"{'='*60}\n")
        return passed
    return True


if __name__ == "__main__":
    passed = asyncio.run(run_evaluation())
    sys.exit(0 if passed else 1)
