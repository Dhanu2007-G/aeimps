"""Resource quota service."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ResourceQuota, User, UserRole


class QuotaService:
    """Service for managing and enforcing resource quotas."""

    # Default quotas by role
    DEFAULT_QUOTAS = {
        UserRole.ADMIN: {
            "max_documents": 10000,
            "max_storage_bytes": 100 * 1024 * 1024 * 1024,  # 100GB
            "max_agent_sessions_per_day": 500,
        },
        UserRole.MANAGER: {
            "max_documents": 5000,
            "max_storage_bytes": 50 * 1024 * 1024 * 1024,  # 50GB
            "max_agent_sessions_per_day": 200,
        },
        UserRole.ANALYST: {
            "max_documents": 1000,
            "max_storage_bytes": 10 * 1024 * 1024 * 1024,  # 10GB
            "max_agent_sessions_per_day": 100,
        },
        UserRole.VIEWER: {
            "max_documents": 100,
            "max_storage_bytes": 1 * 1024 * 1024 * 1024,  # 1GB
            "max_agent_sessions_per_day": 20,
        },
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_quota(self, user: User) -> ResourceQuota:
        """Get user quota or create with defaults."""
        stmt = select(ResourceQuota).where(ResourceQuota.user_id == user.id)
        result = await self.db.execute(stmt)
        quota = result.scalar_one_or_none()

        if not quota:
            defaults = self.DEFAULT_QUOTAS[user.role]
            quota = ResourceQuota(
                user_id=user.id,
                **defaults,
            )
            self.db.add(quota)
            await self.db.commit()
            await self.db.refresh(quota)

        return quota

    async def check_document_quota(self, user: User) -> None:
        """Check if user can upload more documents."""
        quota = await self.get_or_create_quota(user)

        if quota.current_documents >= quota.max_documents:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Document quota exceeded ({quota.max_documents} max)",
            )

    async def check_storage_quota(self, user: User, file_size: int) -> None:
        """Check if user has enough storage quota."""
        quota = await self.get_or_create_quota(user)

        if quota.current_storage_bytes + file_size > quota.max_storage_bytes:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Storage quota exceeded ({quota.max_storage_bytes / (1024**3):.1f}GB max)",
            )

    async def check_agent_session_quota(self, user: User) -> None:
        """Check if user can start more agent sessions today."""
        quota = await self.get_or_create_quota(user)

        # Reset daily counter if it's a new day
        now = datetime.now(timezone.utc)
        if quota.last_reset_at.date() < now.date():
            quota.current_agent_sessions_today = 0
            quota.last_reset_at = now
            await self.db.commit()

        if quota.current_agent_sessions_today >= quota.max_agent_sessions_per_day:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Agent session quota exceeded ({quota.max_agent_sessions_per_day} per day)",
            )

    async def increment_document_count(self, user: User, file_size: int) -> None:
        """Increment document count and storage usage."""
        quota = await self.get_or_create_quota(user)
        quota.current_documents += 1
        quota.current_storage_bytes += file_size
        await self.db.commit()

    async def decrement_document_count(self, user: User, file_size: int) -> None:
        """Decrement document count and storage usage."""
        quota = await self.get_or_create_quota(user)
        quota.current_documents = max(0, quota.current_documents - 1)
        quota.current_storage_bytes = max(0, quota.current_storage_bytes - file_size)
        await self.db.commit()

    async def increment_agent_session_count(self, user: User) -> None:
        """Increment agent session count for today."""
        quota = await self.get_or_create_quota(user)
        quota.current_agent_sessions_today += 1
        await self.db.commit()

    async def get_quota_usage(self, user: User) -> dict:
        """Get current quota usage for user."""
        quota = await self.get_or_create_quota(user)

        return {
            "documents": {
                "current": quota.current_documents,
                "max": quota.max_documents,
                "percentage": (quota.current_documents / quota.max_documents * 100)
                if quota.max_documents > 0
                else 0,
            },
            "storage": {
                "current_bytes": quota.current_storage_bytes,
                "max_bytes": quota.max_storage_bytes,
                "percentage": (quota.current_storage_bytes / quota.max_storage_bytes * 100)
                if quota.max_storage_bytes > 0
                else 0,
            },
            "agent_sessions_today": {
                "current": quota.current_agent_sessions_today,
                "max": quota.max_agent_sessions_per_day,
                "percentage": (
                    quota.current_agent_sessions_today / quota.max_agent_sessions_per_day * 100
                )
                if quota.max_agent_sessions_per_day > 0
                else 0,
            },
        }
