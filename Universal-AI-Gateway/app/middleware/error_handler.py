"""
Global exception handler middleware.
Catches unhandled exceptions and returns standardized 500 responses.
Supports Requirement 8.8.
"""

import logging
import traceback

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.services.error_handler import (
    build_error_response,
    generate_correlation_id,
)

logger = logging.getLogger(__name__)


class GlobalExceptionMiddleware(BaseHTTPMiddleware):
    """
    Catches any unhandled exception and returns a standardized
    500 JSON response with a correlation ID.

    All errors are logged with full context (Requirement 8.8).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            correlation_id = generate_correlation_id()

            # Log with full context (Req 8.8)
            logger.error(
                "Unhandled exception [correlation_id=%s] %s: %s\n%s",
                correlation_id,
                type(exc).__name__,
                str(exc),
                traceback.format_exc(),
            )

            error_resp = build_error_response(
                error_type="internal_error",
                message="An internal error occurred. Please try again later.",
                correlation_id=correlation_id,
            )

            return JSONResponse(
                status_code=500,
                content=error_resp.model_dump(),
                headers={"X-Correlation-ID": correlation_id},
            )
