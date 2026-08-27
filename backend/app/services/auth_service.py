"""Authentication service for user management."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import User, UserRole, UserStatus

if TYPE_CHECKING:
    from app.schemas.auth import UserCreate


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user."""
        # Check if user already exists
        stmt = select(User).where(User.email == user_data.email)
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        # Create user
        user = User(
            email=user_data.email,
            full_name=user_data.full_name,
            password_hash=hash_password(user_data.password),
            role=user_data.role,
            status=UserStatus.ACTIVE,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def authenticate_user(self, email: str, password: str) -> User:
        """Authenticate user by email and password."""
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        # Check account status
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account is {user.status.value}",
            )

        # Check if account is locked
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is temporarily locked",
            )

        # SSO-only users cannot login with password
        if user.is_sso_user and not user.password_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please login via SSO",
            )

        # Verify password
        if not user.password_hash or not verify_password(password, user.password_hash):
            # Increment failed login attempts
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
            await self.db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        # Reset failed attempts on successful login
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(user)
        
        return user

    async def create_tokens(self, user: User) -> dict:
        """Create access and refresh tokens for user."""
        token_data = {"sub": user.id, "email": user.email, "role": user.role.value}
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token({"sub": user.id})
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    async def refresh_access_token(self, refresh_token: str) -> dict:
        """Create new access token from refresh token."""
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                )
            
            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                )
            
            # Get user
            stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user or user.status != UserStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found or inactive",
                )
            
            # Create new access token
            token_data = {"sub": user.id, "email": user.email, "role": user.role.value}
            access_token = create_access_token(token_data)
            
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            }
            
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

    async def get_user_by_id(self, user_id: str) -> User | None:
        """Get user by ID."""
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email."""
        stmt = select(User).where(User.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def initiate_password_reset(self, email: str) -> str:
        """Initiate password reset process."""
        user = await self.get_user_by_email(email)
        if not user:
            # Don't reveal if email exists
            return "reset_token_placeholder"
        
        # Generate reset token
        reset_token = create_password_reset_token(email)
        user.password_reset_token = reset_token
        user.password_reset_expires = datetime.now(timezone.utc) + timedelta(
            hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
        )
        await self.db.commit()
        
        return reset_token

    async def reset_password(self, token: str, new_password: str) -> None:
        """Reset password using token."""
        try:
            payload = decode_token(token)
            if payload.get("type") != "password_reset":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid token type",
                )
            
            email = payload.get("sub")
            user = await self.get_user_by_email(email)
            
            if not user or user.password_reset_token != token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or expired reset token",
                )
            
            if user.password_reset_expires < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Reset token has expired",
                )
            
            # Update password
            user.password_hash = hash_password(new_password)
            user.password_reset_token = None
            user.password_reset_expires = None
            user.failed_login_attempts = 0
            user.locked_until = None
            await self.db.commit()
            
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token",
            )

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        """Change user password."""
        if not user.password_hash or not verify_password(current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
        
        user.password_hash = hash_password(new_password)
        await self.db.commit()
