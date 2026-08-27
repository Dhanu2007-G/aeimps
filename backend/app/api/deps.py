"""FastAPI shared dependencies for injection across all routes."""
from __future__ import annotations

import time
import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import InvalidAPIKeyError, RateLimitExceededError
from app.core.security import decode_token, hash_api_key
from app.db.models import APIKey, User, UserStatus
from app.db.postgres import get_db_session
from app.db.redis import get_redis

logger = logging.getLogger(__name__)

# Security scheme for JWT Bearer tokens
security = HTTPBearer(auto_error=False)


async def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db_session),
) -> User | None:
    """Extract user from JWT token (optional)."""
    if not credentials:
        return None
    
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        result = await db.execute(
            select(User).where(User.id == user_id, User.status == UserStatus.ACTIVE)
        )
        return result.scalar_one_or_none()
    except JWTError:
        return None


async def get_current_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    db: AsyncSession = Depends(get_db_session),
) -> dict | None:
    """Validate API key and return key metadata (optional)."""
    if not x_api_key:
        return None

    key_hash = hash_api_key(x_api_key)
    result = await db.execute(
        select(APIKey).where(
            APIKey.key_hash == key_hash,
            APIKey.is_active == True,
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        return None

    # Check expiry
    if api_key.expires_at and api_key.expires_at.timestamp() < time.time():
        return None

    # Update last_used_at (non-blocking)
    from datetime import datetime, timezone
    api_key.last_used_at = datetime.now(timezone.utc)

    return {
        "id": api_key.id,
        "name": api_key.name,
        "permissions": api_key.permissions,
        "rate_limit_rpm": api_key.rate_limit_rpm,
    }


async def get_current_user_or_api_key(
    user: User | None = Depends(get_current_user_from_token),
    api_key: dict | None = Depends(get_current_api_key),
) -> tuple[User | None, dict | None]:
    """
    Get current user from JWT or API key (backward compatible).
    Either user or api_key must be present.
    """
    if not user and not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: provide Bearer token or X-API-Key header",
        )
    
    return user, api_key


async def require_user(
    auth_data: tuple[User | None, dict | None] = Depends(get_current_user_or_api_key),
) -> User:
    """
    Require authenticated user (JWT only, not API key).
    Use this for user-specific operations.
    """
    user, api_key = auth_data
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User authentication required (JWT token)",
        )
    return user


async def check_rate_limit(
    request: Request,
    auth_data: tuple[User | None, dict | None] = Depends(get_current_user_or_api_key),
) -> None:
    """Sliding window rate limiter using Redis."""
    user, api_key = auth_data
    redis = get_redis()
    
    # Determine rate limit key and limit
    if user:
        rate_key = f"rate_limit:user:{user.id}"
        limit = settings.DEFAULT_RATE_LIMIT_RPM
    elif api_key:
        rate_key = f"rate_limit:api_key:{api_key['id']}"
        limit = api_key.get("rate_limit_rpm", settings.DEFAULT_RATE_LIMIT_RPM)
    else:
        return
    
    window = settings.RATE_LIMIT_WINDOW
    now = time.time()
    window_start = now - window

    pipe = redis.pipeline()
    pipe.zremrangebyscore(rate_key, 0, window_start)
    pipe.zadd(rate_key, {str(now): now})
    pipe.zcard(rate_key)
    pipe.expire(rate_key, window * 2)
    results = await pipe.execute()

    current_count = results[2]
    if current_count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(window)},
            detail=f"Rate limit exceeded: {limit} requests per {window}s",
        )


# Type aliases for cleaner route signatures
DBSession = Annotated[AsyncSession, Depends(get_db_session)]
AuthData = Annotated[tuple[User | None, dict | None], Depends(get_current_user_or_api_key)]
CurrentUser = Annotated[User, Depends(require_user)]
RateLimited = Annotated[None, Depends(check_rate_limit)]
