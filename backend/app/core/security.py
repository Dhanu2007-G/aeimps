"""Security utilities for authentication and authorization."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns: (full_key, key_hash, key_prefix)
    """
    raw_key = f"aeimps_{secrets.token_urlsafe(40)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]
    return raw_key, key_hash, key_prefix


def hash_api_key(key: str) -> str:
    """Hash an API key for storage/comparison."""
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(provided_key: str, stored_hash: str) -> bool:
    """Constant-time comparison of API key hashes."""
    provided_hash = hash_api_key(provided_key)
    return secrets.compare_digest(provided_hash, stored_hash)


# ─── Password Functions ──────────────────────────────────────


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ─── JWT Functions ───────────────────────────────────────────


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT token."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.JWT_ALGORITHM])


def create_password_reset_token(email: str) -> str:
    """Create a password reset token."""
    expire = datetime.now(timezone.utc) + timedelta(
        hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS
    )
    to_encode = {"sub": email, "exp": expire, "type": "password_reset"}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.JWT_ALGORITHM)
