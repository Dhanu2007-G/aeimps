"""Authentication and user schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.db.models import UserRole, UserStatus


# ─── User Schemas ────────────────────────────────────────────

class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)
    role: UserRole = UserRole.VIEWER


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    role: UserRole | None = None
    status: UserStatus | None = None


class UserResponse(UserBase):
    id: str
    role: UserRole
    status: UserStatus
    is_sso_user: bool
    sso_provider: str | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Auth Schemas ────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


# ─── RBAC Schemas ────────────────────────────────────────────

class RoleInfo(BaseModel):
    role: UserRole
    permissions: list[str]
    description: str


# ─── Audit Log Schemas ───────────────────────────────────────

class AuditLogResponse(BaseModel):
    id: str
    user_id: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    method: str
    path: str
    ip_address: str
    response_status: int
    response_time_ms: int | None
    timestamp: datetime

    class Config:
        from_attributes = True


class AuditLogFilter(BaseModel):
    user_id: str | None = None
    action: str | None = None
    resource_type: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)
