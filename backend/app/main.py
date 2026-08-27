"""
AEIMPS FastAPI Application Factory
Initializes all services, databases, and middleware on startup.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.exceptions import AEIMPSError, to_http_exception
from app.core.logging import setup_logging
from app.core.telemetry import instrument_fastapi, setup_telemetry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup → yield → shutdown."""
    # ─── Startup ──────────────────────────────────────────────
    logger.info(f"Starting AEIMPS v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")

    # Initialize databases
    from app.db.postgres import get_engine
    from app.db.qdrant import init_collections
    from app.db.neo4j import init_constraints
    from app.db.redis import get_redis

    # Verify PostgreSQL
    engine = get_engine()
    logger.info("PostgreSQL engine initialized")

    # Initialize Qdrant collections
    try:
        await init_collections()
        logger.info("Qdrant collections ready")
    except Exception as e:
        logger.warning(f"Qdrant initialization: {e}")

    # Initialize Neo4j constraints
    try:
        await init_constraints()
        logger.info("Neo4j constraints ready")
    except Exception as e:
        logger.warning(f"Neo4j initialization: {e}")

    # Verify Redis
    try:
        redis = get_redis()
        await redis.ping()
        logger.info("Redis connection ready")
    except Exception as e:
        logger.warning(f"Redis initialization: {e}")

    logger.info("AEIMPS startup complete ✓")

    yield

    # ─── Shutdown ─────────────────────────────────────────────
    logger.info("Shutting down AEIMPS...")

    from app.db.postgres import close_engine
    from app.db.qdrant import close_client
    from app.db.neo4j import close_driver
    from app.db.redis import close_redis

    await close_engine()
    await close_client()
    await close_driver()
    await close_redis()

    logger.info("AEIMPS shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    setup_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title="AEIMPS",
        description="Autonomous Enterprise Intelligence & Multimodal Processing System",
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ─── CORS ─────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ] if settings.is_development else [settings.APP_URL],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
        max_age=3600,
    )
    
    # ─── Security Headers Middleware ──────────────────────────
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        if not settings.is_development:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Content-Security-Policy"] = "default-src 'self'"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # ─── Request ID & Logging Middleware ──────────────────────
    from app.middleware.request_id import RequestIDMiddleware
    from app.middleware.audit import AuditMiddleware
    
    # Request size limit middleware
    @app.middleware("http")
    async def limit_request_size(request: Request, call_next):
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > 100 * 1024 * 1024:  # 100MB
                return ORJSONResponse(
                    status_code=413,
                    content={"error": "Request body too large (max 100MB)"}
                )
        return await call_next(request)
    
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(AuditMiddleware)

    # ─── Prometheus Metrics ───────────────────────────────────
    if settings.METRICS_ENABLED:
        Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            should_group_untemplated=True,
            excluded_handlers=["/metrics", "/api/v1/admin/health/live"],
        ).instrument(app).expose(app, endpoint="/metrics")

    # ─── OpenTelemetry ────────────────────────────────────────
    try:
        setup_telemetry(
            service_name=settings.OTEL_SERVICE_NAME,
            otlp_endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            environment=settings.ENVIRONMENT,
        )
        instrument_fastapi(app)
    except Exception as e:
        logger.warning(f"Telemetry setup warning: {e}")

    # ─── Exception Handlers ───────────────────────────────────
    @app.exception_handler(AEIMPSError)
    async def aeimps_error_handler(request: Request, exc: AEIMPSError):
        http_exc = to_http_exception(exc)
        return ORJSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled error on {request.url}: {exc}", exc_info=True)
        return ORJSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}},
        )

    # ─── Routers ──────────────────────────────────────────────
    from app.api.v1.router import router as v1_router
    app.include_router(v1_router, prefix="/api/v1")

    # ─── Root endpoint ────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name": "AEIMPS",
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "health": "/api/v1/admin/health",
        }

    return app


app = create_app()
