#!/usr/bin/env python3
"""Seed AEIMPS with sample enterprise documents for demo/testing."""
import asyncio, sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

SAMPLE_DOCS = [
    {
        "filename": "incident_runbook.md",
        "content": """# Incident Response Runbook

## Payment Service Outage (SEV-1)

### Symptoms
- HTTP 500 errors on /api/v1/payments endpoint
- Error rate exceeds 5% for more than 2 minutes
- Increased latency on payment-service (p99 > 10s)

### Root Cause History
Previous incidents have been caused by:
1. Database connection pool exhaustion (2024-01-15)
2. Redis cache invalidation storm (2024-02-03)
3. Upstream auth-service timeout cascade (2024-02-28)

### Immediate Actions
1. Check payment-service logs: `kubectl logs -n prod deployment/payment-service --tail=100`
2. Verify database connections: `SELECT count(*) FROM pg_stat_activity WHERE state='active'`
3. Check Redis health: `redis-cli -h redis-prod ping`
4. Scale up payment-service if CPU > 80%: `kubectl scale deployment/payment-service --replicas=5`

### Escalation
- L1: On-call engineer (PagerDuty)
- L2: Payment team lead (Slack: #payment-incidents)
- L3: VP Engineering (if revenue impact > $10k/hr)
""",
        "tags": ["runbook", "incident", "payment"],
    },
    {
        "filename": "architecture_overview.md",
        "content": """# System Architecture Overview

## Core Services

### API Gateway (FastAPI)
Entry point for all client requests. Handles authentication, rate limiting, and routing.
Depends on: Redis (rate limiting), PostgreSQL (auth), all downstream services.

### Payment Service
Processes payment transactions. Integrates with Stripe API.
Dependencies: PostgreSQL (transactions), Redis (idempotency keys), auth-service
SLO: 99.9% uptime, p99 < 500ms

### Auth Service  
JWT token generation and validation.
Dependencies: PostgreSQL (users), Redis (session cache)
Critical path: All other services call auth-service on every request.

### Notification Service
Sends email and SMS notifications.
Dependencies: SendGrid API, Twilio API, RabbitMQ (async queue)

## Infrastructure
- Kubernetes (EKS) on AWS us-east-1
- PostgreSQL 15 (RDS Multi-AZ)
- Redis 7 (ElastiCache cluster)
- Qdrant vector store (self-hosted, 3-node cluster)
""",
        "tags": ["architecture", "services", "infrastructure"],
    },
    {
        "filename": "postmortem_2024_02.md",
        "content": """# Postmortem: Payment Outage 2024-02-28

## Summary
Payment service experienced 47 minutes of degraded availability (15% error rate).
Impact: ~$85,000 in delayed transactions. No data loss.

## Timeline
- 14:32 UTC: Alert fired — payment-service error rate > 5%
- 14:35 UTC: On-call engineer acknowledged
- 14:38 UTC: Identified auth-service latency spike (p99: 8.2s)
- 14:45 UTC: Root cause identified — auth-service Redis connection pool exhausted
- 14:51 UTC: Temporary fix: increased Redis pool size from 10 to 50
- 15:19 UTC: Permanent fix deployed — auth-service v2.1.4

## Root Cause
Auth-service connection pool was undersized (maxconn=10) for peak traffic.
During the 14:30 UTC traffic spike (3x normal), connections queued and timed out.
Payment-service retried failed auth requests, amplifying the load.

## Action Items
- [x] Increase auth-service Redis pool to 100 connections
- [ ] Add circuit breaker on payment-service → auth-service calls (due: 2024-03-15)
- [ ] Set up connection pool utilization alerts (due: 2024-03-10)
- [ ] Load test auth-service at 5x peak traffic (due: 2024-03-22)

## Lessons Learned
1. Service dependencies need explicit SLOs and timeouts
2. Connection pool sizing must be re-evaluated at each traffic milestone
3. Retry logic without circuit breakers causes cascade failures
""",
        "tags": ["postmortem", "incident", "auth", "payment"],
    },
    {
        "filename": "api_performance_report.csv",
        "content": """endpoint,method,p50_ms,p95_ms,p99_ms,error_rate,requests_per_day
/api/v1/payments,POST,145,520,1240,0.002,125000
/api/v1/auth/login,POST,38,95,210,0.008,450000
/api/v1/users/profile,GET,22,55,98,0.001,890000
/api/v1/orders,GET,67,180,420,0.003,320000
/api/v1/notifications/send,POST,890,2100,5400,0.015,45000
""",
        "tags": ["performance", "api", "metrics"],
    },
    {
        "filename": "deployment_checklist.md",
        "content": """# Production Deployment Checklist

## Pre-Deployment
- [ ] All unit tests passing (>95% coverage)
- [ ] Integration tests green on staging
- [ ] Load test completed (target: 2x peak traffic)
- [ ] Database migrations reviewed and tested
- [ ] Rollback procedure documented
- [ ] Feature flags configured

## Deployment Steps
1. Notify #deployments Slack channel
2. Enable maintenance mode if DB migrations required
3. Deploy to 10% canary (monitor for 15 minutes)
4. Check error rate, latency, and business metrics
5. Roll out to 50% (monitor 10 minutes)
6. Full rollout
7. Monitor for 30 minutes post-deployment

## Post-Deployment Verification
- [ ] Health endpoints responding (all services)
- [ ] Error rate within normal bounds (<0.5%)
- [ ] P99 latency within SLO
- [ ] Database connection count stable
- [ ] Redis hit rate > 80%
- [ ] No unexpected alerts firing

## Rollback Trigger Conditions
- Error rate > 2% sustained for 5 minutes
- P99 latency > 2x pre-deployment baseline
- Any SEV-1 or SEV-2 alert fires
""",
        "tags": ["deployment", "operations", "checklist"],
    },
]


async def seed():
    from app.core.security import generate_api_key
    from app.db.postgres import get_db
    from app.db.models import APIKey
    from app.services.ingestion.service import IngestionService
    from fastapi import UploadFile
    import io

    print("Seeding AEIMPS with sample documents...\n")

    # Create a default API key if none exists
    from sqlalchemy import select
    async with get_db() as db:
        result = await db.execute(select(APIKey).limit(1))
        existing_key = result.scalar_one_or_none()

        if not existing_key:
            raw_key, key_hash, key_prefix = generate_api_key()
            api_key = APIKey(name="seed-default", key_hash=key_hash,
                             key_prefix=key_prefix, permissions=["read", "write"])
            db.add(api_key)
            print(f"Created default API key: {raw_key}\n")

        api_key_id = existing_key.id if existing_key else api_key.id

    # Ingest sample documents
    async with get_db() as db:
        service = IngestionService(db)
        for doc in SAMPLE_DOCS:
            try:
                content = doc["content"].encode("utf-8")
                upload = UploadFile(
                    filename=doc["filename"],
                    file=io.BytesIO(content),
                )
                upload.size = len(content)
                result = await service.ingest_document(
                    file=upload,
                    metadata={},
                    tags=doc.get("tags", []),
                    source_system="seed",
                    api_key_id=api_key_id,
                )
                print(f"✓ Queued: {doc['filename']} (job: {result.job_id[:8]}...)")
            except Exception as e:
                print(f"✗ Failed: {doc['filename']}: {e}")

    print(f"\n{len(SAMPLE_DOCS)} documents seeded. Workers will process them shortly.")
    print("Run: docker compose logs -f worker-doc-processor  to monitor progress.")


if __name__ == "__main__":
    asyncio.run(seed())
