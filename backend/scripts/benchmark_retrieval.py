#!/usr/bin/env python3
"""Benchmark retrieval latency across all modes."""
import asyncio, sys, os, time, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

QUERIES = [
    "payment service outage root cause",
    "authentication timeout cascade failure",
    "Redis connection pool exhaustion fix",
    "deployment rollback procedure",
    "API latency SLO thresholds",
]


async def benchmark():
    from app.services.retrieval.orchestrator import RetrievalOrchestrator
    orch = RetrievalOrchestrator()

    print(f"\n{'Mode':<12} {'P50 ms':>8} {'P95 ms':>8} {'P99 ms':>8} {'Avg ms':>8}")
    print("-" * 52)

    for mode in ["dense", "sparse", "keyword", "hybrid"]:
        latencies = []
        for q in QUERIES:
            for _ in range(2):  # 2 runs per query
                t = time.monotonic()
                try:
                    await orch.search(query=q, mode=mode, top_k=8)
                    latencies.append((time.monotonic() - t) * 1000)
                except Exception as e:
                    print(f"  {mode}/{q[:20]}: {e}")

        if latencies:
            latencies.sort()
            n = len(latencies)
            print(f"{mode:<12} {statistics.median(latencies):>8.1f} "
                  f"{latencies[int(n*0.95)]:>8.1f} "
                  f"{latencies[int(n*0.99)] if n > 1 else latencies[-1]:>8.1f} "
                  f"{statistics.mean(latencies):>8.1f}")

    print(f"\nBenchmark complete ({len(QUERIES)} queries × 2 runs × 4 modes)")


if __name__ == "__main__":
    asyncio.run(benchmark())
