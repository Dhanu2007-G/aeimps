"""Unit tests for RBAC system."""
import pytest
from fastapi import HTTPException

from app.core.rbac import (
    Permission,
    check_permission,
    check_role,
    get_role_permissions,
    has_permission,
    is_role_superior,
)
from app.db.models import User, UserRole, UserStatus


def test_role_permissions():
    """Test role permission mappings."""
    admin_perms = get_role_permissions("admin")
    manager_perms = get_role_permissions("manager")
    analyst_perms = get_role_permissions("analyst")
    viewer_perms = get_role_permissions("viewer")
    
    # Admin has all permissions
    assert Permission.USERS_WRITE in admin_perms
    assert Permission.DOCUMENTS_DELETE in admin_perms
    
    # Manager can manage documents
    assert Permission.DOCUMENTS_WRITE in manager_perms
    assert Permission.USERS_WRITE not in manager_perms
    
    # Analyst can search and use agents
    assert Permission.SEARCH in analyst_perms
    assert Permission.AGENTS_WRITE in analyst_perms
    assert Permission.DOCUMENTS_WRITE not in analyst_perms
    
    # Viewer is read-only
    assert Permission.DOCUMENTS_READ in viewer_perms
    assert Permission.DOCUMENTS_WRITE not in viewer_perms


def test_role_hierarchy():
    """Test role hierarchy comparisons."""
    assert is_role_superior("admin", "viewer")
    assert is_role_superior("manager", "analyst")
    assert is_role_superior("analyst", "analyst")
    assert not is_role_superior("viewer", "admin")
    assert not is_role_superior("analyst", "manager")


def test_has_permission():
    """Test permission checking."""
    assert has_permission("admin", Permission.USERS_WRITE)
    assert has_permission("manager", Permission.DOCUMENTS_WRITE)
    assert not has_permission("viewer", Permission.DOCUMENTS_WRITE)
    assert has_permission("viewer", Permission.DOCUMENTS_READ)


def test_check_permission_success():
    """Test successful permission check."""
    user = User(
        id="1",
        email="admin@test.com",
        full_name="Admin",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    
    # Should not raise
    check_permission(user, Permission.USERS_WRITE)


def test_check_permission_failure():
    """Test failed permission check raises exception."""
    user = User(
        id="1",
        email="viewer@test.com",
        full_name="Viewer",
        role=UserRole.VIEWER,
        status=UserStatus.ACTIVE,
    )
    
    with pytest.raises(HTTPException) as exc_info:
        check_permission(user, Permission.USERS_WRITE)
    
    assert exc_info.value.status_code == 403


def test_check_role_success():
    """Test successful role check."""
    user = User(
        id="1",
        email="manager@test.com",
        full_name="Manager",
        role=UserRole.MANAGER,
        status=UserStatus.ACTIVE,
    )
    
    # Should not raise
    check_role(user, UserRole.ANALYST)
    check_role(user, UserRole.MANAGER)


def test_check_role_failure():
    """Test failed role check raises exception."""
    user = User(
        id="1",
        email="analyst@test.com",
        full_name="Analyst",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
    )
    
    with pytest.raises(HTTPException) as exc_info:
        check_role(user, UserRole.ADMIN)
    
    assert exc_info.value.status_code == 403
