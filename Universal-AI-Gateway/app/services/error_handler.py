"""
Standardized error response system.
Provides consistent JSON error structures with correlation IDs.
Supports Requirements 8.1–8.8.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error response schema (matches design.md ErrorResponse / ErrorDetail)
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    """Standard error detail included in every error response."""
    type: str
    message: str
    correlation_id: str
    retry_after: Optional[int] = None


class ErrorResponse(BaseModel):
    """Top-level wrapper returned by all error endpoints."""
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Error type constants
# ---------------------------------------------------------------------------

# Error type → default HTTP status code
ERROR_TYPES = {
    "authentication_error": 401,       # Req 8.1
    "authorization_error": 403,        # Req 8.2
    "rate_limit_exceeded": 429,        # Req 8.3
    "provider_error": 502,             # Req 8.4
    "provider_unavailable": 503,       # Req 8.4
    "validation_error": 400,           # Req 8.5
    "internal_error": 500,             # Req 8.6
    "not_found": 404,
}


# ---------------------------------------------------------------------------
# Error builder functions
# ---------------------------------------------------------------------------


def generate_correlation_id() -> str:
    """Generate a unique correlation ID for error tracing (Req 8.7)."""
    return str(uuid.uuid4())


def build_error_response(
    error_type: str,
    message: str,
    correlation_id: Optional[str] = None,
    retry_after: Optional[int] = None,
) -> ErrorResponse:
    """
    Build a standardized error response.

    Args:
        error_type: One of the ERROR_TYPES keys.
        message: Human-readable error description.
        correlation_id: Optional; auto-generated if not provided.
        retry_after: Seconds to wait before retrying (for 429s).

    Returns:
        :class:`ErrorResponse` with consistent structure.
    """
    cid = correlation_id or generate_correlation_id()

    return ErrorResponse(
        error=ErrorDetail(
            type=error_type,
            message=message,
            correlation_id=cid,
            retry_after=retry_after,
        )
    )


def get_status_code(error_type: str) -> int:
    """Look up the HTTP status code for an error type."""
    return ERROR_TYPES.get(error_type, 500)


# ---------------------------------------------------------------------------
# Convenience builders for each category
# ---------------------------------------------------------------------------


def authentication_error(
    message: str = "Invalid or missing API key",
    correlation_id: Optional[str] = None,
) -> tuple:
    """401 — Req 8.1."""
    resp = build_error_response("authentication_error", message, correlation_id)
    return resp, 401


def authorization_error(
    message: str = "Insufficient permissions",
    correlation_id: Optional[str] = None,
) -> tuple:
    """403 — Req 8.2."""
    resp = build_error_response("authorization_error", message, correlation_id)
    return resp, 403


def rate_limit_error(
    message: str = "Rate limit exceeded",
    retry_after: int = 60,
    correlation_id: Optional[str] = None,
) -> tuple:
    """429 — Req 8.3."""
    resp = build_error_response("rate_limit_exceeded", message, correlation_id, retry_after)
    return resp, 429


def provider_error(
    message: str = "Provider returned an error",
    status_code: int = 502,
    correlation_id: Optional[str] = None,
) -> tuple:
    """502/503 — Req 8.4."""
    error_type = "provider_unavailable" if status_code == 503 else "provider_error"
    resp = build_error_response(error_type, message, correlation_id)
    return resp, status_code


def validation_error(
    message: str = "Invalid request parameters",
    correlation_id: Optional[str] = None,
) -> tuple:
    """400 — Req 8.5."""
    resp = build_error_response("validation_error", message, correlation_id)
    return resp, 400


def internal_error(
    message: str = "An internal error occurred",
    correlation_id: Optional[str] = None,
) -> tuple:
    """500 — Req 8.6."""
    resp = build_error_response("internal_error", message, correlation_id)
    return resp, 500
