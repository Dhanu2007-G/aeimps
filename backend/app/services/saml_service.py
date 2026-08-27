"""SAML SSO service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.db.models import SAMLConfig, User, UserRole, UserStatus

if TYPE_CHECKING:
    from fastapi import Request


class SAMLService:
    """Service for SAML 2.0 SSO operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_saml_config(self) -> SAMLConfig | None:
        """Get active SAML configuration."""
        stmt = select(SAMLConfig).where(SAMLConfig.is_active == True)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_saml_settings(self, saml_config: SAMLConfig) -> dict:
        """Build SAML settings dictionary for python3-saml."""
        base_url = settings.APP_URL if hasattr(settings, "APP_URL") else "http://localhost:8000"
        
        return {
            "strict": True,
            "debug": settings.is_development,
            "sp": {
                "entityId": f"{base_url}/api/v1/auth/saml/metadata",
                "assertionConsumerService": {
                    "url": f"{base_url}/api/v1/auth/saml/acs",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
                },
                "singleLogoutService": {
                    "url": f"{base_url}/api/v1/auth/saml/sls",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                },
                "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
                "x509cert": "",
                "privateKey": ""
            },
            "idp": {
                "entityId": saml_config.entity_id,
                "singleSignOnService": {
                    "url": saml_config.sso_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                },
                "singleLogoutService": {
                    "url": saml_config.slo_url or "",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
                },
                "x509cert": saml_config.x509_cert
            }
        }

    def prepare_request(self, request: Request) -> dict:
        """Prepare request data for python3-saml."""
        return {
            "https": "on" if request.url.scheme == "https" else "off",
            "http_host": request.url.hostname,
            "server_port": request.url.port or (443 if request.url.scheme == "https" else 80),
            "script_name": request.url.path,
            "get_data": dict(request.query_params),
            "post_data": {},
        }

    async def initiate_sso(self, request: Request) -> str:
        """Initiate SAML SSO login flow."""
        saml_config = await self.get_active_saml_config()
        if not saml_config:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SAML SSO is not configured"
            )
        
        settings_data = await self.get_saml_settings(saml_config)
        req = self.prepare_request(request)
        auth = OneLogin_Saml2_Auth(req, settings_data)
        
        return auth.login()

    async def process_saml_response(self, request: Request) -> User:
        """Process SAML assertion and create/update user."""
        saml_config = await self.get_active_saml_config()
        if not saml_config:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SAML SSO is not configured"
            )
        
        settings_data = await self.get_saml_settings(saml_config)
        req = self.prepare_request(request)
        
        # Add POST data
        form_data = await request.form()
        req["post_data"] = dict(form_data)
        
        auth = OneLogin_Saml2_Auth(req, settings_data)
        auth.process_response()
        
        errors = auth.get_errors()
        if errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SAML authentication failed: {', '.join(errors)}"
            )
        
        if not auth.is_authenticated():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="SAML authentication failed"
            )
        
        # Extract user attributes
        attributes = auth.get_attributes()
        name_id = auth.get_nameid()
        
        # Map SAML attributes to user fields
        email = attributes.get(saml_config.attribute_mapping.get("email", "email"), [name_id])[0]
        full_name = attributes.get(saml_config.attribute_mapping.get("name", "name"), [email])[0]
        groups = attributes.get(saml_config.attribute_mapping.get("groups", "groups"), [])
        
        # Determine role from SAML groups
        role = self._map_groups_to_role(groups, saml_config.role_mapping)
        
        # JIT provisioning: create or update user
        if saml_config.jit_provisioning:
            user = await self._provision_user(name_id, email, full_name, role, saml_config.provider)
        else:
            # User must already exist
            stmt = select(User).where(User.sso_subject == name_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User not provisioned. Contact administrator."
                )
        
        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(user)
        
        return user

    def _map_groups_to_role(self, groups: list[str], role_mapping: dict) -> UserRole:
        """Map SAML groups to application role."""
        # Check role_mapping for explicit group -> role mappings
        for group in groups:
            if group in role_mapping:
                return UserRole(role_mapping[group])
        
        # Default to viewer
        return UserRole.VIEWER

    async def _provision_user(
        self,
        sso_subject: str,
        email: str,
        full_name: str,
        role: UserRole,
        sso_provider: str
    ) -> User:
        """Create or update SSO user."""
        # Check if user exists by SSO subject
        stmt = select(User).where(User.sso_subject == sso_subject)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            # Update existing user
            user.email = email
            user.full_name = full_name
            user.role = role
            user.status = UserStatus.ACTIVE
        else:
            # Create new user
            user = User(
                email=email,
                full_name=full_name,
                role=role,
                status=UserStatus.ACTIVE,
                is_sso_user=True,
                sso_provider=sso_provider,
                sso_subject=sso_subject,
                password_hash=None,  # SSO users don't have passwords
            )
            self.db.add(user)
        
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def create_tokens_for_user(self, user: User) -> dict:
        """Create JWT tokens for SSO user."""
        token_data = {"sub": user.id, "email": user.email, "role": user.role.value}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token({"sub": user.id})
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
