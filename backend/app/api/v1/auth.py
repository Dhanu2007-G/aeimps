"""Authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, DBSession
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services.auth_service import AuthService
from app.services.saml_service import SAMLService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: DBSession):
    """Register a new user."""
    auth_service = AuthService(db)
    user = await auth_service.create_user(user_data)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, db: DBSession):
    """Authenticate user and return JWT tokens."""
    auth_service = AuthService(db)
    user = await auth_service.authenticate_user(credentials.email, credentials.password)
    tokens = await auth_service.create_tokens(user)
    
    return TokenResponse(
        **tokens,
        user=UserResponse.model_validate(user)
    )


@router.post("/refresh", response_model=dict)
async def refresh_token(request: RefreshTokenRequest, db: DBSession):
    """Refresh access token using refresh token."""
    auth_service = AuthService(db)
    return await auth_service.refresh_access_token(request.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user: CurrentUser):
    """
    Logout user (client should delete tokens).
    Future: Implement token blacklist in Redis.
    """
    return None


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(request: PasswordResetRequest, db: DBSession):
    """Request password reset email."""
    auth_service = AuthService(db)
    await auth_service.initiate_password_reset(request.email)
    return {"message": "If email exists, password reset instructions have been sent"}


@router.post("/password-reset/confirm", status_code=status.HTTP_200_OK)
async def confirm_password_reset(request: PasswordResetConfirm, db: DBSession):
    """Confirm password reset with token."""
    auth_service = AuthService(db)
    await auth_service.reset_password(request.token, request.new_password)
    return {"message": "Password has been reset successfully"}


@router.post("/password/change", status_code=status.HTTP_200_OK)
async def change_password(
    request: PasswordChange,
    current_user: CurrentUser,
    db: DBSession,
):
    """Change password for authenticated user."""
    auth_service = AuthService(db)
    await auth_service.change_password(
        current_user, request.current_password, request.new_password
    )
    return {"message": "Password changed successfully"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser):
    """Get current user information."""
    return current_user


# ─── SAML SSO Endpoints ──────────────────────────────────────


@router.get("/saml/metadata")
async def saml_metadata(request: Request, db: DBSession):
    """Get SAML Service Provider metadata."""
    saml_service = SAMLService(db)
    saml_config = await saml_service.get_active_saml_config()
    
    if not saml_config:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SAML SSO is not configured"
        )
    
    settings_data = await saml_service.get_saml_settings(saml_config)
    from onelogin.saml2.settings import OneLogin_Saml2_Settings
    saml_settings = OneLogin_Saml2_Settings(settings=settings_data)
    metadata = saml_settings.get_sp_metadata()
    
    return {"metadata": metadata}


@router.get("/saml/login")
async def saml_login(request: Request, db: DBSession):
    """Initiate SAML SSO login."""
    saml_service = SAMLService(db)
    sso_url = await saml_service.initiate_sso(request)
    return RedirectResponse(url=sso_url)


@router.post("/saml/acs", response_model=TokenResponse)
async def saml_acs(request: Request, db: DBSession):
    """SAML Assertion Consumer Service - process SAML response."""
    saml_service = SAMLService(db)
    user = await saml_service.process_saml_response(request)
    tokens = await saml_service.create_tokens_for_user(user)
    
    return TokenResponse(
        **tokens,
        user=UserResponse.model_validate(user)
    )
