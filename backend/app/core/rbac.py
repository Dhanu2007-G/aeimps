"""Role-Based Access Control (RBAC) system."""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from app.db.models import User, UserRole


class Permission(str, Enum):
    """System permissions."""
    # Document permissions
    DOCUMENTS_READ = "documents:read"
    DOCUMENTS_WRITE = "documents:write"
    DOCUMENTS_DELETE = "documents:delete"
    
    # Search permissions
    SEARCH = "search:execute"
    
    # Agent permissions
    AGENTS_READ = "agents:read"
    AGENTS_WRITE = "agents:write"
    
    # Admin permissions
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    USERS_DELETE = "users:delete"
    AUDIT_LOGS_READ = "audit_logs:read"
    SYSTEM_CONFIG = "system:config"
    QUOTAS_MANAGE = "quotas:manage"
    
    # API Key permissions
    API_KEYS_READ = "api_keys:read"
    API_KEYS_WRITE = "api_keys:write"


# Role hierarchy and permissions
ROLE_PERMISSIONS: dict[str, list[Permission]] = {
    "admin": [
        # All permissions
        Permission.DOCUMENTS_READ,
        Permission.DOCUMENTS_WRITE,
        Permission.DOCUMENTS_DELETE,
        Permission.SEARCH,
        Permission.AGENTS_READ,
        Permission.AGENTS_WRITE,
        Permission.USERS_READ,
        Permission.USERS_WRITE,
        Permission.USERS_DELETE,
        Permission.AUDIT_LOGS_READ,
        Permission.SYSTEM_CONFIG,
        Permission.QUOTAS_MANAGE,
        Permission.API_KEYS_READ,
        Permission.API_KEYS_WRITE,
    ],
    "manager": [
        # Can manage documents and use agents
        Permission.DOCUMENTS_READ,
        Permission.DOCUMENTS_WRITE,
        Permission.DOCUMENTS_DELETE,
        Permission.SEARCH,
        Permission.AGENTS_READ,
        Permission.AGENTS_WRITE,
        Permission.USERS_READ,
        Permission.API_KEYS_READ,
    ],
    "analyst": [
        # Can search and use agents, but not manage documents
        Permission.DOCUMENTS_READ,
        Permission.SEARCH,
        Permission.AGENTS_READ,
        Permission.AGENTS_WRITE,
    ],
    "viewer": [
        # Read-only access
        Permission.DOCUMENTS_READ,
        Permission.SEARCH,
        Permission.AGENTS_READ,
    ],
}

# Role hierarchy (higher roles inherit lower role permissions)
ROLE_HIERARCHY: dict[str, int] = {
    "admin": 4,
    "manager": 3,
    "analyst": 2,
    "viewer": 1,
}


def get_role_permissions(role: str) -> list[Permission]:
    """Get all permissions for a role."""
    return ROLE_PERMISSIONS.get(role, [])


def has_permission(user_role: str, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    permissions = get_role_permissions(user_role)
    return permission in permissions


def is_role_superior(user_role: str, required_role: str) -> bool:
    """Check if user role is superior or equal to required role."""
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= required_level


def check_permission(user: User, permission: Permission) -> None:
    """
    Check if user has permission, raise HTTPException if not.
    
    Args:
        user: User object
        permission: Required permission
        
    Raises:
        HTTPException: 403 Forbidden if user lacks permission
    """
    if not has_permission(user.role.value, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission.value} required",
        )


def check_role(user: User, required_role: UserRole) -> None:
    """
    Check if user has required role or higher.
    
    Args:
        user: User object
        required_role: Minimum required role
        
    Raises:
        HTTPException: 403 Forbidden if user role is insufficient
    """
    if not is_role_superior(user.role.value, required_role.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role {required_role.value} or higher required",
        )
