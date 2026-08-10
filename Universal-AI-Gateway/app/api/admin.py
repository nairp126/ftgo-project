"""
Admin API endpoints.
Supports Requirements 2.5, 6.5, 6.6, 7.5.

Connected to real services: metrics, request logger, API key service.
"""

import logging
import uuid
from typing import Dict, Any, List

from fastapi import APIRouter, Query, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.services.metrics import metrics
from app.services.request_logger import RequestLogger
from app.services.api_key_service import get_api_key_service
from app.api.dependencies import verify_admin_token
from app.db.database import get_db
from app.db.models import APIKey, Tenant

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin", 
    tags=["Admin"],
    dependencies=[Depends(verify_admin_token)]
)

# Shared request logger instance (same one used by routes.py)
# In production, this would be injected via dependency injection
_request_logger = RequestLogger()


def get_request_logger() -> RequestLogger:
    """Return the request logger instance (allows test injection)."""
    return _request_logger


@router.get("/api-keys")
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=1000),
) -> Dict[str, Any]:
    """List all API keys."""
    stmt = select(APIKey).limit(limit)
    result = await db.execute(stmt)
    keys = result.scalars().all()
    
    return {
        "keys": [
            {
                "id": str(k.id),
                "name": k.name,
                "prefix": k.key_prefix,
                "tenant_id": str(k.tenant_id),
                "is_active": k.is_active,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            }
            for k in keys
        ],
        "total": len(keys)
    }

@router.post("/api-keys")
async def create_api_key(
    tenant_id: str = Body(...),
    name: str = Body(...),
    rate_limit: int = Body(default=60),
    db: AsyncSession = Depends(get_db),
    service = Depends(get_api_key_service),
) -> Dict[str, Any]:
    """Create a new API key."""
    try:
        raw_key, key_obj = await service.create_key(
            db=db,
            tenant_id=uuid.UUID(tenant_id),
            name=name,
            rate_limit_per_minute=rate_limit,
        )
        return {
            "id": str(key_obj.id),
            "name": key_obj.name,
            "raw_key": raw_key,
            "prefix": key_obj.key_prefix,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api-keys/{key_id}/rotate")
async def rotate_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    service = Depends(get_api_key_service),
) -> Dict[str, Any]:
    """Rotate an API key."""
    try:
        raw_key, new_key = await service.rotate_key(
            db=db,
            key_id=uuid.UUID(key_id),
        )
        return {
            "new_id": str(new_key.id),
            "new_raw_key": raw_key,
            "old_id": key_id,
            "status": "rotated"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    service = Depends(get_api_key_service),
) -> Dict[str, Any]:
    """Revoke (deactivate) an API key."""
    success = await service.deactivate_key(db, uuid.UUID(key_id))
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "success", "message": f"API key {key_id} deactivated"}


@router.get("/analytics")
async def get_analytics() -> Dict[str, Any]:
    """
    Usage analytics (Requirement 7.5).
    Aggregates from metrics collector and request logger.
    """
    m = metrics.get_metrics()
    rl = get_request_logger()
    stats = rl.get_stats()

    return {
        "total_requests": m["gateway_requests_total"],
        "total_tokens": m["tokens_total"],
        "total_cost_usd": str(m["cost_total_usd"]),
        "error_rate": m["gateway_error_rate"],
        "cache_hit_rate": m["cache_hit_rate"],
        "avg_latency_ms": m["gateway_latency_avg_ms"],
        "provider_breakdown": m["provider_requests"],
        "top_models": [],  # Would aggregate from request logs
        "log_stats": stats,
    }


@router.get("/logs")
async def get_logs(
    limit: int = Query(default=100, ge=1, le=1000),
) -> Dict[str, Any]:
    """
    Queryable request logs (Requirement 6.5).
    Returns recent log entries from the request logger.
    """
    rl = get_request_logger()
    logs = rl.get_logs(limit=limit)
    return {"logs": logs, "total": len(logs)}


@router.post("/logs/export")
async def export_logs() -> Dict[str, Any]:
    """
    Log export to S3 (Requirement 6.6).
    """
    rl = get_request_logger()
    return rl.export_logs_to_s3()

@router.post("/config/reload")
async def reload_configuration() -> Dict[str, str]:
    """
    Reload configuration without service restart (Requirement 11.6).
    Clears the lru_cache on get_settings.
    """
    from app.core.config import get_settings
    get_settings.cache_clear()
    logger.info("Configuration hot-reloaded via admin endpoint.")
    return {"status": "success", "message": "Configuration reloaded"}
