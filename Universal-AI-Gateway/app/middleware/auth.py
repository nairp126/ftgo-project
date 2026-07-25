"""
Authentication middleware for request-level API key validation and JWT verification.
Supports Requirements 2.2, 2.3, 8.1, and Phase 3 JWT validation.
"""

import time
import uuid
import inspect
from typing import Set

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from fastapi import HTTPException

from app.core.logging import get_logger, generate_correlation_id
from app.core.jwt_handler import is_jwt, decode_jwt, extract_identity
from app.api.dependencies import authenticate_api_key
from app.db.database import db_manager

logger = get_logger(__name__)

# Paths that do not require authentication
PUBLIC_PATHS: Set[str] = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
    "/actuator/health",
}


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Middleware that attaches a correlation ID to every request
    and enforces authentication (API key or JWT) on non-public paths.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Assign a unique request ID for tracing
        request_id = generate_correlation_id()
        request.state.request_id = request_id

        # Record start time for latency tracking
        request.state.start_time = time.time()

        # Log the incoming request
        logger.info(
            f"{request.method} {request.url.path}",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        # Check public paths exemption or admin paths (admin auth is handled separately on endpoint level)
        if request.url.path in PUBLIC_PATHS or request.url.path.startswith("/admin"):
            try:
                response = await call_next(request)
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Correlation-ID"] = request_id
                return response
            except Exception as exc:
                return self._handle_unhandled_exception(exc, request_id)

        # Check if auth dependency is overridden (e.g. in integration tests)
        auth_dep = request.app.dependency_overrides.get(authenticate_api_key, authenticate_api_key)
        if auth_dep is not authenticate_api_key:
            try:
                # Inspect signature to support 0-argument lambdas used in existing tests
                sig = inspect.signature(auth_dep)
                if len(sig.parameters) == 0:
                    if inspect.iscoroutinefunction(auth_dep):
                        await auth_dep()
                    else:
                        auth_dep()
                else:
                    if inspect.iscoroutinefunction(auth_dep):
                        await auth_dep(request)
                    else:
                        auth_dep(request)
                
                request.state.auth_method = "api_key"
                
                response = await call_next(request)
                response.headers["X-Request-ID"] = request_id
                response.headers["X-Correlation-ID"] = request_id
                return response
            except HTTPException as exc:
                err_detail = exc.detail
                err_msg = err_detail.get("message", "Authentication failed.") if isinstance(err_detail, dict) else str(err_detail)
                res = JSONResponse(
                    status_code=exc.status_code,
                    content={
                        "error": {
                            "type": "authentication_error",
                            "message": err_msg,
                            "correlation_id": request_id,
                        }
                    },
                )
                res.headers["X-Request-ID"] = request_id
                res.headers["X-Correlation-ID"] = request_id
                return res
            except Exception as exc:
                return self._handle_unhandled_exception(exc, request_id)

        # Enforce authentication
        authorization = request.headers.get("Authorization")
        x_api_key = request.headers.get("X-API-Key")

        token = None
        if authorization:
            parts = authorization.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
        elif x_api_key:
            token = x_api_key

        if not token:
            res = JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "type": "authentication_error",
                        "message": "Authentication credentials are required. Provide via 'Authorization: Bearer <token>' or 'X-API-Key' header.",
                        "correlation_id": request_id,
                    }
                },
            )
            res.headers["X-Request-ID"] = request_id
            res.headers["X-Correlation-ID"] = request_id
            return res

        # Determine token type and perform validation
        if is_jwt(token):
            try:
                payload = decode_jwt(token)
                identity = extract_identity(payload)

                # Attach identity to request state
                request.state.user_id = identity.user_id
                request.state.tenant_id = identity.tenant_id
                request.state.roles = identity.roles
                request.state.auth_method = "jwt"
            except HTTPException as exc:
                err_msg = exc.detail if isinstance(exc.detail, str) else exc.detail.get("message", "Invalid token")
                res = JSONResponse(
                    status_code=exc.status_code,
                    content={
                        "error": {
                            "type": "authentication_error",
                            "message": err_msg,
                            "correlation_id": request_id,
                        }
                    },
                )
                res.headers["X-Request-ID"] = request_id
                res.headers["X-Correlation-ID"] = request_id
                return res
        else:
            # API key path: delegate database lookup and hash validation
            session_factory = db_manager.create_session_factory()
            async with session_factory() as db:
                try:
                    await authenticate_api_key(
                        request,
                        authorization=authorization,
                        x_api_key=x_api_key,
                        db=db,
                    )
                    request.state.auth_method = "api_key"
                except HTTPException as exc:
                    err_detail = exc.detail
                    err_msg = err_detail.get("message", "Invalid API key.") if isinstance(err_detail, dict) else str(err_detail)
                    res = JSONResponse(
                        status_code=exc.status_code,
                        content={
                            "error": {
                                "type": "authentication_error",
                                "message": err_msg,
                                "correlation_id": request_id,
                            }
                        },
                    )
                    res.headers["X-Request-ID"] = request_id
                    res.headers["X-Correlation-ID"] = request_id
                    return res

        # Process authenticated request
        try:
            response = await call_next(request)
        except Exception as exc:
            return self._handle_unhandled_exception(exc, request_id)

        # Attach correlation ID to all responses
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = request_id

        # Log response
        latency_ms = int((time.time() - request.state.start_time) * 1000)
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({latency_ms}ms)",
            request_id=request_id,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )

        return response

    def _handle_unhandled_exception(self, exc: Exception, request_id: str) -> Response:
        """Log unhandled exception and return 500 error response."""
        logger.error(
            f"Unhandled exception during request: {exc}",
            request_id=request_id,
            exc_info=True,
        )
        res = JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "internal_server_error",
                    "message": "An internal error occurred.",
                    "correlation_id": request_id,
                }
            },
        )
        res.headers["X-Request-ID"] = request_id
        res.headers["X-Correlation-ID"] = request_id
        return res
