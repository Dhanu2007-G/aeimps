"""Unit tests for authentication."""
import pytest
from datetime import datetime, timedelta, timezone

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hashing():
    """Test password hashing and verification."""
    password = "test_password123"
    hashed = hash_password(password)
    
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)


def test_access_token_creation():
    """Test JWT access token creation and decoding."""
    data = {"sub": "user123", "email": "test@example.com", "role": "admin"}
    token = create_access_token(data)
    
    assert isinstance(token, str)
    assert len(token) > 0
    
    decoded = decode_token(token)
    assert decoded["sub"] == "user123"
    assert decoded["email"] == "test@example.com"
    assert decoded["role"] == "admin"
    assert decoded["type"] == "access"
    assert "exp" in decoded


def test_refresh_token_creation():
    """Test JWT refresh token creation."""
    data = {"sub": "user123"}
    token = create_refresh_token(data)
    
    assert isinstance(token, str)
    
    decoded = decode_token(token)
    assert decoded["sub"] == "user123"
    assert decoded["type"] == "refresh"


def test_token_expiration():
    """Test that expired tokens are rejected."""
    data = {"sub": "user123"}
    # Create token that expires immediately
    token = create_access_token(data, expires_delta=timedelta(seconds=-1))
    
    with pytest.raises(Exception):  # JWTError
        decode_token(token)
