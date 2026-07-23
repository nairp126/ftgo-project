"""
Health check endpoint.
Supports Requirements 10.1, 10.3, 10.4, 10.5.

Queries real circuit breaker state for provider health,
and real ping/queries for DB and Redis.
"""

import logging
from typing import Dict, Any

import httpx
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app.core.config import get_settings

from app.providers.circuit_breaker import CircuitBreaker
from app.db.database import db_manager
from app.cache.redis import redis_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

# Circuit breakers for each provider (Requirement 10.3)
_provider_circuits: Dict[str, CircuitBreaker] = {
    "openai": CircuitBreaker("openai"),
    "anthropic": CircuitBreaker("anthropic"),
    "bedrock": CircuitBreaker("bedrock"),
    "google": CircuitBreaker("google"),
}


def get_provider_circuits() -> Dict[str, CircuitBreaker]:
    """Return provider circuit breakers (allows test injection)."""
    return _provider_circuits


@router.get("/health", summary="Detailed Health Check")
async def health_check() -> Dict[str, Any]:
    """
    System health endpoint (Requirement 10.1).

    Returns status of all subsystems:
    - Provider health from circuit breaker state (Req 10.3)
    - Cache connectivity (Req 10.4)
    - Database connectivity (Req 10.5)
    """
    circuits = get_provider_circuits()

    # Build provider health from circuit breaker state
    provider_health = {}
    all_providers_healthy = True
    for name, cb in circuits.items():
        try:
            status = await cb.get_status()
            is_avail = await cb.is_available()
            provider_health[name] = {
                "status": "healthy" if is_avail else "unhealthy",
                "circuit_state": status["state"],
                "failure_count": status["failure_count"],
            }
            if not is_avail:
                all_providers_healthy = False
        except Exception as e:
            logger.error(f"Health check failed for circuit '{name}': {e}")
            provider_health[name] = {
                "status": "degraded",
                "error": str(e)
            }
            all_providers_healthy = False

    # Check database and cache health
    try:
        db_healthy = await db_manager.health_check()
    except Exception as e:
        logger.error(f"Health check failed for database: {e}")
        db_healthy = False

    try:
        cache_healthy = await redis_manager.health_check()
    except Exception as e:
        logger.error(f"Health check failed for cache: {e}")
        cache_healthy = False

    # Determine overall status
    overall = "healthy" if (all_providers_healthy and db_healthy and cache_healthy) else "degraded"

    return {
        "status": overall,
        "version": "1.0.0",
        "components": {
            "providers": provider_health,
            "cache": {
                "status": "healthy" if cache_healthy else "unhealthy",
                "type": "redis",
            },
            "database": {
                "status": "healthy" if db_healthy else "unhealthy",
                "type": "postgresql",
            },
        },
    }


@router.get("/actuator/health", summary="Actuator Health Proxy")
async def actuator_health() -> Response:
    """
    Proxy endpoint for Spring Boot Actuator health checks (Requirement R3-3).
    
    Forwards requests to the downstream API gateway's actuator health endpoint.
    """
    settings = get_settings()
    url = settings.downstream_health_url
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            # Return body and status code as-is
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers={"Content-Type": resp.headers.get("Content-Type", "application/json")}
            )
    except Exception as exc:
        logger.error("Failed to proxy health check to %s: %s", url, exc)
        return JSONResponse(
            status_code=503,
            content={"status": "DOWNSTREAM_UNAVAILABLE"}
        )
