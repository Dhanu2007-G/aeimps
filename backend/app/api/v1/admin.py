"""Admin API — health checks, metrics summary, worker status."""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from fastapi import APIRouter
from fastapi.responses import ORJSONResponse
from app.api.deps import CurrentAPIKey, DBSession, RateLimited
from app.schemas import HealthResponse, ServiceHealthStatus, SystemMetricsSummary, WorkerStatus

logger = logging.getLogger(__name__)
router = APIRouter()
_start_time = time.monotonic()


@router.get("/health", response_model=HealthResponse)
async def health_check(db: DBSession = None):
    """Full health check — all services."""
    from app.core.config import settings
    services: dict[str, ServiceHealthStatus] = {}

    # PostgreSQL
    try:
        t = time.monotonic()
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        services["postgres"] = ServiceHealthStatus(
            status="healthy", latency_ms=int((time.monotonic()-t)*1000)
        )
    except Exception as e:
        services["postgres"] = ServiceHealthStatus(status="unhealthy", details=str(e))

    # Redis
    try:
        t = time.monotonic()
        from app.db.redis import get_redis
        await get_redis().ping()
        services["redis"] = ServiceHealthStatus(
            status="healthy", latency_ms=int((time.monotonic()-t)*1000)
        )
    except Exception as e:
        services["redis"] = ServiceHealthStatus(status="unhealthy", details=str(e))

    # Qdrant
    try:
        t = time.monotonic()
        from app.db.qdrant import get_qdrant_client
        await get_qdrant_client().get_collections()
        services["qdrant"] = ServiceHealthStatus(
            status="healthy", latency_ms=int((time.monotonic()-t)*1000)
        )
    except Exception as e:
        services["qdrant"] = ServiceHealthStatus(status="degraded", details=str(e))

    # Neo4j
    try:
        t = time.monotonic()
        from app.db.neo4j import run_query
        await run_query("RETURN 1")
        services["neo4j"] = ServiceHealthStatus(
            status="healthy", latency_ms=int((time.monotonic()-t)*1000)
        )
    except Exception as e:
        services["neo4j"] = ServiceHealthStatus(status="degraded", details=str(e))

    # Workers (via heartbeat)
    try:
        from app.db.redis import get_worker_heartbeats
        heartbeats = await get_worker_heartbeats()
        now = time.time()
        for wname, ts in heartbeats.items():
            age = now - ts
            services[f"worker:{wname}"] = ServiceHealthStatus(
                status="healthy" if age < 120 else "stale",
                latency_ms=int(age * 1000),
            )
    except Exception:
        pass

    degraded = any(s.status != "healthy" for s in services.values())
    overall = "degraded" if degraded else "healthy"
    if services.get("postgres", ServiceHealthStatus(status="healthy")).status == "unhealthy":
        overall = "unhealthy"

    return HealthResponse(
        status=overall,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        uptime_seconds=time.monotonic() - _start_time,
        services=services,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/health/live")
async def liveness():
    """Kubernetes/Docker liveness probe — fast."""
    return ORJSONResponse({"status": "ok"})


@router.get("/health/ready")
async def readiness(db: DBSession = None):
    """Readiness probe — checks DB connectivity."""
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        return ORJSONResponse({"status": "ready"})
    except Exception as e:
        return ORJSONResponse({"status": "not_ready", "error": str(e)}, status_code=503)


@router.get("/metrics/summary", response_model=SystemMetricsSummary)
async def metrics_summary(_: RateLimited = None, db: DBSession = None):
    from sqlalchemy import func, select, text
    from app.db.models import Document, DocumentChunk, AgentSession
    from datetime import date

    docs_total = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    chunks_total = (await db.execute(select(func.count(DocumentChunk.id)))).scalar() or 0

    today = date.today()
    agents_today = (await db.execute(
        select(func.count(AgentSession.id)).where(
            func.date(AgentSession.created_at) == today
        )
    )).scalar() or 0

    avg_lat = None
    try:
        result = await db.execute(
            text("SELECT AVG(latency_ms) FROM retrieval_logs WHERE created_at > NOW() - INTERVAL '1 day'")
        )
        avg_lat = result.scalar()
        avg_lat = float(avg_lat) if avg_lat else None
    except Exception:
        pass

    avg_eval = None
    try:
        from app.db.models import Evaluation
        result = await db.execute(
            select(func.avg(Evaluation.overall_score)).where(
                Evaluation.created_at > text("NOW() - INTERVAL '24 hours'")
            )
        )
        avg_eval = result.scalar()
        avg_eval = float(avg_eval) if avg_eval else None
    except Exception:
        pass

    # Qdrant vector count
    vectors_total = 0
    try:
        from app.db.qdrant import get_qdrant_client
        from app.core.config import settings
        info = await get_qdrant_client().get_collection(settings.QDRANT_COLLECTION_CHUNKS)
        vectors_total = info.points_count or 0
    except Exception:
        pass

    return SystemMetricsSummary(
        documents_total=docs_total,
        chunks_total=chunks_total,
        vectors_total=vectors_total,
        agents_run_today=agents_today,
        avg_retrieval_ms=avg_lat,
        eval_avg_score=avg_eval,
    )


@router.get("/workers")
async def worker_status(_: RateLimited = None):
    from app.db.redis import get_worker_heartbeats
    now = time.time()
    heartbeats = await get_worker_heartbeats()

    workers = []
    for name, ts in heartbeats.items():
        age = now - ts
        workers.append(WorkerStatus(
            name=name,
            status="alive" if age < 60 else ("stale" if age < 300 else "dead"),
            last_heartbeat=ts,
            seconds_since_heartbeat=round(age, 1),
        ))

    return {"workers": workers, "total": len(workers)}


@router.post("/reindex/{document_id}")
async def reindex_document(
    document_id: str,
    _: RateLimited = None,
    db: DBSession = None,
):
    from sqlalchemy import select, update
    from app.db.models import Document, DocumentChunk, ProcessingJob
    import uuid

    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        from fastapi import HTTPException
        raise HTTPException(404, detail="Document not found")

    # Reset embedding flags
    await db.execute(
        update(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .values(is_embedded=False)
    )

    job = ProcessingJob(
        id=str(uuid.uuid4()),
        document_id=document_id,
        job_type="embedding",
        status="PENDING",
        input_payload={"document_id": document_id, "reindex": True},
    )
    db.add(job)

    from app.db.redis import publish_to_stream
    from app.core.config import settings
    await publish_to_stream(settings.STREAM_EMBED, {"document_id": document_id, "reindex": "true"})

    return {"document_id": document_id, "job_id": job.id, "status": "QUEUED"}
