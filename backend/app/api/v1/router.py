"""API v1 router — aggregates all sub-routers."""
from fastapi import APIRouter

from app.api.v1 import admin, admin_config, agent, auth, evaluate, ingest, retrieve, users

router = APIRouter()

router.include_router(auth.router, tags=["Authentication"])
router.include_router(users.router, prefix="/admin")
router.include_router(admin_config.router)
router.include_router(ingest.router, prefix="/ingest", tags=["Ingestion"])
router.include_router(retrieve.router, prefix="/retrieve", tags=["Retrieval"])
router.include_router(agent.router, prefix="/agent", tags=["Agent Workflows"])
router.include_router(evaluate.router, prefix="/evaluate", tags=["Evaluation"])
router.include_router(admin.router, prefix="/admin", tags=["Administration"])
