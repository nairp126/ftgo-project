"""
Authentication middleware for request-level API key validation.
Supports Requirements 2.2 (request validation), 2.3 (error responses),
and 8.1 (standardized error format).
"""

import time
import uuid
from typing import Set

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_logger, generate_correlation_id

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
    and enforces authentication on non-public paths.

    Authentication itself is handled by the FastAPI dependency
    (authenticate_api_key) on individual endpoints. This middleware
    provides the outer layer: correlation IDs, timing, and a
    catch-all for unauthenticated access to protected paths.
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

        # Process the request
        try:
            response = await call_next(request)
        except Exception as exc:
            # Unhandled exceptions get a 500 with correlation ID
            logger.error(
                f"Unhandled exception during request: {exc}",
                request_id=request_id,
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "type": "internal_server_error",
                        "message": "An internal error occurred.",
                        "correlation_id": request_id,
                    }
                },
            )

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
