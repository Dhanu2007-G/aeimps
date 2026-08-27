"""User management endpoints for admins."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DBSession
from app.core.rbac import Permission, check_permission
from app.db.models import AuditLog, User
from app.schemas.auth import AuditLogResponse, UserCreate, UserResponse, UserUpdate
from app.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: CurrentUser,
    db: DBSession,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List all users (admin only)."""
    check_permission(current_user, Permission.USERS_READ)
    result = await db.execute(select(User).offset(offset).limit(limit))
    return result.scalars().all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_data: UserCreate, current_user: CurrentUser, db: DBSession):
    """Create a new user (admin only)."""
    check_permission(current_user, Permission.USERS_WRITE)
    auth_service = AuthService(db)
    return await auth_service.create_user(user_data)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, current_user: CurrentUser, db: DBSession):
    """Get user by ID."""
    check_permission(current_user, Permission.USERS_READ)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user_update: UserUpdate, current_user: CurrentUser, db: DBSession):
    """Update user."""
    check_permission(current_user, Permission.USERS_WRITE)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if user_update.full_name is not None:
        user.full_name = user_update.full_name
    if user_update.role is not None:
        user.role = user_update.role
    if user_update.status is not None:
        user.status = user_update.status
    
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, current_user: CurrentUser, db: DBSession):
    """Delete user."""
    check_permission(current_user, Permission.USERS_DELETE)
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    await db.delete(user)
    await db.commit()


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    current_user: CurrentUser,
    db: DBSession,
    user_id: str | None = None,
    action: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List audit logs (admin only)."""
    check_permission(current_user, Permission.AUDIT_LOGS_READ)
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc())
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()
