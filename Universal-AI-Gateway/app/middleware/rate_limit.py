"""
Rate limiting middleware.
Enforces per-key rate limits and returns standardised 429 responses.
Supports Requirements 7.2, 7.3.
"""

import json
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.logging import get_logger
from app.core.logging import get_logger
from app.services.rate_limiter import TokenBucketRateLimiter, RateLimitResult
from app.services.budget_manager import BudgetManager, BudgetExceededError

logger = get_logger(__name__)

# Paths that are exempt from rate limiting
EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/actuator/health"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces rate limits on incoming requests.

    Expects that authentication has already occurred upstream, so
    ``request.state.api_key_id`` and ``request.state.tenant_id``
    are available when needed.  If they are absent the middleware
    passes the request through (e.g. for public endpoints).
    """

    def __init__(self, app, limiter: TokenBucketRateLimiter = None, budget_manager: BudgetManager = None):
        super().__init__(app)
        self._limiter = limiter or TokenBucketRateLimiter()
        self._budget = budget_manager or BudgetManager()

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for exempt paths
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # Extract identifiers set by auth dependency
        api_key_id = getattr(request.state, "api_key_id", None)
        tenant_id = getattr(request.state, "tenant_id", None)
        rate_per_minute = getattr(request.state, "rate_limit_per_minute", None)

        # If no API key ID, skip rate limiting (unauthenticated endpoint)
        if not api_key_id:
            return await call_next(request)

        # 1. Per-key check
        result = await self._limiter.check_rate_limit(
            api_key_id=api_key_id,
            rate_per_minute=rate_per_minute or 60,
        )

        if not result.allowed:
            return self._rate_limited_response(result, "per-key")

        # 2. Per-tenant aggregate check (if tenant known)
        if tenant_id:
            tenant_result = await self._limiter.check_tenant_limit(tenant_id)
            if not tenant_result.allowed:
                return self._rate_limited_response(tenant_result, "per-tenant")

        # 3. Global check
        global_result = await self._limiter.check_global_limit()
        if not global_result.allowed:
            return self._rate_limited_response(global_result, "global")

        # 4. Budget check (Requirement R7-1) — scoped to LLM /v1/ paths only
        if tenant_id and request.url.path.startswith("/v1/"):
            try:
                await self._budget.check_budget(tenant_id)
            except BudgetExceededError as exc:
                return JSONResponse(
                    status_code=402,
                    content={
                        "error": {
                            "type": "budget_exceeded",
                            "message": str(exc),
                            "suggestion": "Please upgrade your payment plan or contact finance."
                        }
                    }
                )

        # Proceed with the request
        response = await call_next(request)

        # Add rate limit headers (Requirement 7.3)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(int(result.reset_at))

        return response

    @staticmethod
    def _rate_limited_response(result: RateLimitResult, scope: str) -> JSONResponse:
        """Build a 429 Too Many Requests response."""
        retry_after = result.retry_after or 1
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "type": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded ({scope}). "
                               f"Try again in {retry_after}s.",
                    "retry_after": retry_after,
                }
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(result.reset_at)),
            },
        )
