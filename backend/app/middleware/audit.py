"""Audit logging middleware."""
from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.db.models import AuditLog
from app.db.postgres import async_session_factory


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware to log all API requests for audit purposes."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip audit logging for health checks and static files
        if request.url.path in ["/health", "/metrics", "/docs", "/openapi.json"]:
            return await call_next(request)
        
        start_time = time.time()
        
        # Extract user/api_key info if available
        user_id = None
        api_key_id = None
        
        if hasattr(request.state, "user") and request.state.user:
            user_id = request.state.user.id
        elif hasattr(request.state, "api_key") and request.state.api_key:
            api_key_id = request.state.api_key.get("id")
        
        # Get client IP
        ip_address = request.client.host if request.client else "unknown"
        if forwarded_for := request.headers.get("X-Forwarded-For"):
            ip_address = forwarded_for.split(",")[0].strip()
        
        # Process request
        response = await call_next(request)
        
        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Determine action from method and path
        action = f"{request.method} {request.url.path}"
        
        # Extract resource info from path
        resource_type = None
        resource_id = None
        path_parts = request.url.path.split("/")
        if len(path_parts) >= 4:
            resource_type = path_parts[3]  # e.g., /api/v1/documents -> documents
            if len(path_parts) >= 5 and path_parts[4]:
                resource_id = path_parts[4]
        
        # Create audit log entry asynchronously
        try:
            async with async_session_factory() as session:
                audit_log = AuditLog(
                    user_id=user_id,
                    api_key_id=api_key_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    method=request.method,
                    path=str(request.url.path),
                    ip_address=ip_address,
                    user_agent=request.headers.get("User-Agent"),
                    response_status=response.status_code,
                    response_time_ms=response_time_ms,
                )
                session.add(audit_log)
                await session.commit()
        except Exception as e:
            # Don't fail the request if audit logging fails
            import logging
            logging.error(f"Failed to create audit log: {e}")
        
        return response
