"""
Security middleware — CORS and security headers.
Supports Requirement 13.1.
"""

import logging
from typing import List

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Security headers (Requirement 13.1)
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",  # HSTS
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Content-Security-Policy": "default-src 'none'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

# Default CORS settings
DEFAULT_ALLOWED_ORIGINS: List[str] = ["*"]
DEFAULT_ALLOWED_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
DEFAULT_ALLOWED_HEADERS: List[str] = [
    "Authorization", "Content-Type", "X-Request-ID", "X-API-Key",
]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers (HSTS, CSP, etc.) to all responses.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        for header, value in SECURITY_HEADERS.items():
            # Skip CSP for documentation endpoints so Swagger UI can load external assets
            if header == "Content-Security-Policy" and request.url.path in ["/docs", "/redoc", "/openapi.json"]:
                continue
            response.headers[header] = value

        return response
