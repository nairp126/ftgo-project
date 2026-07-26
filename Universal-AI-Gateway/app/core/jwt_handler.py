"""
JWT decoding, validation, and identity extraction handler.
Supports Phase 3 JWT validation requirements.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import jwt
from fastapi import HTTPException, status
from app.core.config import get_settings

@dataclass
class UserIdentity:
    """User identity details extracted from a decoded JWT."""
    user_id: str
    tenant_id: str
    roles: List[str]
    email: Optional[str] = None


def is_jwt(token: str) -> bool:
    """
    Check if the token has exactly two dots (format: header.payload.signature).
    """
    return token.count(".") == 2


def decode_jwt(token: str) -> Dict[str, Any]:
    """
    Decode and verify a JWT using the configured JWT_SECRET_KEY.
    
    Algorithm: HS256
    
    Raises:
        HTTPException(401) with message "Token expired" if expired.
        HTTPException(401) with message "Invalid token" for other validation errors.
    """
    settings = get_settings()
    secret_key = settings.jwt_secret_key

    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


def extract_identity(payload: Dict[str, Any]) -> UserIdentity:
    """
    Extract UserIdentity from a decoded JWT payload.

    Expected claims:
      - sub or user_id -> user_id
      - tenant_id -> tenant_id
      - roles (default: [])
      - email (optional)
      
    Raises:
        HTTPException(401) with message "Token missing required claims" if user_id
        or tenant_id is missing.
    """
    user_id = payload.get("sub") or payload.get("user_id")
    tenant_id = payload.get("tenant_id")
    roles = payload.get("roles", [])
    email = payload.get("email")

    if not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required claims"
        )

    return UserIdentity(
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        roles=list(roles),
        email=str(email) if email is not None else None
    )
