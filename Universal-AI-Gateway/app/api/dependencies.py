"""
FastAPI dependencies for authentication and authorization.
Supports Requirements 2.2 (API key validation), 2.3 (401 errors).
"""

from typing import Optional
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import APIKey
from app.services.api_key_service import get_api_key_service
from app.core.logging import get_logger

logger = get_logger(__name__)


async def authenticate_api_key(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> APIKey:
    """
    FastAPI dependency that validates the API key from the request.

    Accepts the key via:
      - Authorization: Bearer <key>
      - X-API-Key: <key>

    Flow:
      1. Extract raw key from header
      2. Extract prefix (first 8 chars) for DB lookup
      3. Query DB for active keys matching that prefix
      4. Verify the raw key against each candidate's Argon2 hash
      5. Return the matching APIKey model on success

    Raises:
        HTTPException 401 if no key provided, key is invalid, or key is inactive.
    """
    # Short-circuit if request has already been authenticated via middleware
    if getattr(request.state, "auth_method", None) in ("api_key", "jwt"):
        return None

    raw_key = _extract_raw_key(authorization, x_api_key)

    if raw_key is None:
        logger.warning("Request missing API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "type": "authentication_error",
                "message": "API key is required. Provide via 'Authorization: Bearer <key>' or 'X-API-Key: <key>' header.",
            },
        )

    # Look up candidate keys by prefix for efficient matching
    prefix = raw_key[:8]
    api_key_service = get_api_key_service()

    stmt = select(APIKey).where(
        APIKey.key_prefix == prefix,
        APIKey.is_active == True,  # noqa: E712 — SQLAlchemy requires == for column comparisons
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()
    
    logger.debug(f"Auth lookup: prefix='{prefix}', found {len(candidates)} candidates")

    if not candidates:
        logger.warning("No active API key found with prefix '%s...'", prefix)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "type": "authentication_error",
                "message": "Invalid API key.",
            },
        )

    # Verify the raw key against each candidate's hash
    for api_key in candidates:
        if api_key_service.verify_api_key(raw_key, api_key.key_hash):
            # Check if key has expired
            if api_key.expires_at is not None:
                from datetime import datetime, timezone

                if api_key.expires_at < datetime.now(timezone.utc):
                    logger.warning(
                        "Expired API key used: prefix='%s...', id=%s", prefix, api_key.id
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail={
                            "type": "authentication_error",
                            "message": "API key has expired.",
                        },
                    )

            logger.info(
                "API key authenticated: prefix='%s...', id=%s", prefix, api_key.id
            )
            
            # Populate state for middleware (e.g. RateLimiting, BudgetManager)
            request.state.api_key_id = api_key.id
            request.state.tenant_id = api_key.tenant_id
            request.state.rate_limit_per_minute = api_key.rate_limit_per_minute
            request.state.daily_cost_limit = api_key.daily_cost_limit
            
            return api_key
        else:
            logger.debug(f"Hash mismatch for candidate id={api_key.id}")

    # No hash matched
    logger.warning("API key verification failed for prefix '%s...'", prefix)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "type": "authentication_error",
            "message": "Invalid API key.",
        },
    )


def _extract_raw_key(
    authorization: Optional[str],
    x_api_key: Optional[str],
) -> Optional[str]:
    """
    Extract the raw API key from request headers.

    Priority:
      1. Authorization: Bearer <key>
      2. X-API-Key: <key>

    Returns None if neither header provides a usable key.
    """
    # Try Authorization bearer header first
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
        # If Authorization header exists but is malformed, don't fall through
        # to X-API-Key — this avoids confusing behavior.
        return None

    # Fall back to X-API-Key header
    if x_api_key:
        return x_api_key

    return None

def verify_admin_token(
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token")
) -> bool:
    """
    Verify the admin API key provided in the X-Admin-Token header.
    """
    from app.core.config import get_settings
    settings = get_settings()
    
    if not settings.security.admin_api_key:
        logger.warning("Attempted admin access without configured ADMIN_API_KEY")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin access is disabled because ADMIN_API_KEY is not configured.",
        )
        
    if not x_admin_token or not secrets.compare_digest(x_admin_token, settings.security.admin_api_key):
        logger.warning("Invalid admin token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token.",
        )
        
    return True
