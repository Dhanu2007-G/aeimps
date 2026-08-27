"""Integration tests for authentication flow."""
import pytest
from httpx import AsyncClient

from app.db.models import UserRole


@pytest.mark.asyncio
async def test_user_registration_and_login(async_client: AsyncClient):
    """Test user registration and login flow."""
    # Register new user
    response = await async_client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "SecurePass123!",
        "role": "viewer"
    })
    assert response.status_code == 201
    user_data = response.json()
    assert user_data["email"] == "test@example.com"
    
    # Login with credentials
    response = await async_client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "SecurePass123!"
    })
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    
    return token_data["access_token"]


@pytest.mark.asyncio
async def test_token_refresh(async_client: AsyncClient):
    """Test token refresh flow."""
    # Login first
    login_response = await async_client.post("/api/v1/auth/login", json={
        "email": "admin@aeimps.local",
        "password": "admin123"
    })
    refresh_token = login_response.json()["refresh_token"]
    
    # Refresh token
    response = await async_client.post("/api/v1/auth/refresh", json={
        "refresh_token": refresh_token
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_protected_endpoint_requires_auth(async_client: AsyncClient):
    """Test that protected endpoints require authentication."""
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_rbac_permissions(async_client: AsyncClient):
    """Test RBAC permission enforcement."""
    # Create viewer user
    await async_client.post("/api/v1/auth/register", json={
        "email": "viewer@test.com",
        "full_name": "Viewer",
        "password": "SecurePass123!",
        "role": "viewer"
    })
    
    # Login as viewer
    login_response = await async_client.post("/api/v1/auth/login", json={
        "email": "viewer@test.com",
        "password": "SecurePass123!"
    })
    viewer_token = login_response.json()["access_token"]
    
    # Try to create user (should fail - admin only)
    response = await async_client.post(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={
            "email": "newuser@test.com",
            "full_name": "New User",
            "password": "SecurePass123!",
            "role": "viewer"
        }
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_audit_logging(async_client: AsyncClient, admin_token: str):
    """Test that actions are audit logged."""
    # Perform an action
    await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    # Check audit logs
    response = await async_client.get(
        "/api/v1/admin/users/audit-logs",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    logs = response.json()
    assert len(logs) > 0
    assert any(log["action"] == "GET /api/v1/auth/me" for log in logs)


@pytest.mark.asyncio
async def test_password_change(async_client: AsyncClient):
    """Test password change flow."""
    # Login
    login_response = await async_client.post("/api/v1/auth/login", json={
        "email": "admin@aeimps.local",
        "password": "admin123"
    })
    token = login_response.json()["access_token"]
    
    # Change password
    response = await async_client.post(
        "/api/v1/auth/password/change",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "admin123",
            "new_password": "NewSecurePass456!"
        }
    )
    assert response.status_code == 200
    
    # Login with new password
    response = await async_client.post("/api/v1/auth/login", json={
        "email": "admin@aeimps.local",
        "password": "NewSecurePass456!"
    })
    assert response.status_code == 200
