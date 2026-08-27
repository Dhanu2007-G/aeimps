"""Admin endpoints for retention policies and SSO configuration."""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession
from app.core.rbac import Permission, check_permission
from app.db.models import RetentionPolicy, SAMLConfig

router = APIRouter(prefix="/admin", tags=["Administration"])


# ─── Retention Policy Schemas ────────────────────────────────


class RetentionPolicyCreate(BaseModel):
    name: str
    description: str | None = None
    resource_type: str
    retention_days: int
    archive_before_delete: bool = True
    match_criteria: dict = {}


class RetentionPolicyResponse(BaseModel):
    id: str
    name: str
    resource_type: str
    retention_days: int
    is_active: bool

    class Config:
        from_attributes = True


# ─── SAML Config Schemas ─────────────────────────────────────


class SAMLConfigCreate(BaseModel):
    name: str
    provider: str
    entity_id: str
    sso_url: str
    slo_url: str | None = None
    x509_cert: str
    attribute_mapping: dict = {}
    role_mapping: dict = {}
    jit_provisioning: bool = True


class SAMLConfigResponse(BaseModel):
    id: str
    name: str
    provider: str
    entity_id: str
    is_active: bool

    class Config:
        from_attributes = True


# ─── Retention Policy Endpoints ──────────────────────────────


@router.get("/retention-policies", response_model=list[RetentionPolicyResponse])
async def list_retention_policies(current_user: CurrentUser, db: DBSession):
    """List all retention policies."""
    check_permission(current_user, Permission.SYSTEM_CONFIG)
    result = await db.execute(select(RetentionPolicy))
    return result.scalars().all()


@router.post("/retention-policies", response_model=RetentionPolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_retention_policy(policy: RetentionPolicyCreate, current_user: CurrentUser, db: DBSession):
    """Create retention policy."""
    check_permission(current_user, Permission.SYSTEM_CONFIG)
    
    new_policy = RetentionPolicy(**policy.model_dump())
    db.add(new_policy)
    await db.commit()
    await db.refresh(new_policy)
    return new_policy


@router.delete("/retention-policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_retention_policy(policy_id: str, current_user: CurrentUser, db: DBSession):
    """Delete retention policy."""
    check_permission(current_user, Permission.SYSTEM_CONFIG)
    
    result = await db.execute(select(RetentionPolicy).where(RetentionPolicy.id == policy_id))
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    await db.delete(policy)
    await db.commit()


# ─── SAML Configuration Endpoints ────────────────────────────


@router.get("/saml-configs", response_model=list[SAMLConfigResponse])
async def list_saml_configs(current_user: CurrentUser, db: DBSession):
    """List SAML configurations."""
    check_permission(current_user, Permission.SYSTEM_CONFIG)
    result = await db.execute(select(SAMLConfig))
    return result.scalars().all()


@router.post("/saml-configs", response_model=SAMLConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_saml_config(config: SAMLConfigCreate, current_user: CurrentUser, db: DBSession):
    """Create SAML configuration."""
    check_permission(current_user, Permission.SYSTEM_CONFIG)
    
    new_config = SAMLConfig(**config.model_dump())
    db.add(new_config)
    await db.commit()
    await db.refresh(new_config)
    return new_config


@router.patch("/saml-configs/{config_id}/activate", status_code=status.HTTP_200_OK)
async def activate_saml_config(config_id: str, current_user: CurrentUser, db: DBSession):
    """Activate SAML configuration (deactivates others)."""
    check_permission(current_user, Permission.SYSTEM_CONFIG)
    
    # Deactivate all
    result = await db.execute(select(SAMLConfig))
    for config in result.scalars():
        config.is_active = False
    
    # Activate selected
    result = await db.execute(select(SAMLConfig).where(SAMLConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    
    config.is_active = True
    await db.commit()
    return {"message": "SAML configuration activated"}


@router.get("/quota/usage")
async def get_my_quota_usage(current_user: CurrentUser, db: DBSession):
    """Get current user's quota usage."""
    from app.services.quota_service import QuotaService
    
    quota_service = QuotaService(db)
    return await quota_service.get_quota_usage(current_user)
