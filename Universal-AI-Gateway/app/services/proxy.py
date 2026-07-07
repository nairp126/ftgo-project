"""
Async reverse proxy service forwarding requests downstream.
Supports Requirements for proxying, headers filtering, and error handling.
"""

import time
import uuid
import logging
from typing import Optional, AsyncGenerator
from decimal import Decimal

import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.proxy_config import RouteConfig
from app.services.request_logger import RequestLogger

logger = logging.getLogger(__name__)

# Module-level httpx.AsyncClient for connection pooling (Step 2.httpx)
_client = httpx.AsyncClient()


async def close_proxy_client():
    """Close the proxy HTTP client."""
    await _client.aclose()


async def forward_request(
    request: Request,
    route: RouteConfig,
    db: Optional[AsyncSession] = None,
) -> Response:
    """
    Forward an incoming HTTP request downstream to the upstream service.

    Features:
      - Path prefix stripping
      - Headers stripping and injection
      - Streaming response body
      - Exception mapping to status codes 502/503/504
      - Audit/request logging to PostgreSQL
    """
    start_time = time.time()
    correlation_id = request.headers.get("X-Correlation-ID") or getattr(request.state, "request_id", None) or str(uuid.uuid4())
    request_id = request.headers.get("X-Request-ID") or getattr(request.state, "request_id", None) or correlation_id

    # 1. Path construction (Step 2.URL)
    path = request.url.path
    if route.strip_prefix:
        service_name = route.prefix.split("/")[-1]
        new_path = "/" + service_name + path[len(route.prefix):]
    else:
        new_path = path

    # Target URL construction
    upstream_url = route.upstream_url.rstrip("/") + new_path

    # 2. Header handling (Step 2.Headers)
    headers = {}
    for k, v in request.headers.items():
        k_lower = k.lower()
        # Strip credentials/hop-by-hop and to-be-injected headers
        if k_lower in (
            "authorization", "x-api-key", "cookie", "x-forwarded-proto",
            "x-correlation-id", "x-request-id", "x-forwarded-for", "x-forwarded-host",
            "x-tenant-id", "x-authenticated"
        ):
            continue
        headers[k] = v

    # Inject required trace headers
    headers["X-Correlation-ID"] = correlation_id
    headers["X-Request-ID"] = request_id

    # X-Forwarded-For
    client_host = request.client.host if request.client else "127.0.0.1"
    incoming_xff = request.headers.get("x-forwarded-for")
    if incoming_xff:
        headers["X-Forwarded-For"] = f"{incoming_xff}, {client_host}"
    else:
        headers["X-Forwarded-For"] = client_host

    # X-Forwarded-Host
    headers["X-Forwarded-Host"] = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc

    # Inject identity headers
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id:
        headers["X-Tenant-ID"] = str(tenant_id)
    headers["X-Authenticated"] = "true"

    # 3. Request body
    body = await request.body()

    # 4. Forwarding execution
    status_code = 502
    error_status = None
    error_message = None

    try:
        # Build request to forward
        req = _client.build_request(
            method=request.method,
            url=upstream_url,
            headers=headers,
            content=body,
            params=request.query_params,
            timeout=route.timeout_seconds,
        )

        # Stream response
        r = await _client.send(req, stream=True)
        status_code = r.status_code

        # Exclude hop-by-hop response headers
        response_headers = {}
        for k, v in r.headers.items():
            if k.lower() not in (
                "connection",
                "keep-alive",
                "proxy-authenticate",
                "proxy-authorization",
                "te",
                "trailer",
                "transfer-encoding",
                "upgrade",
                "content-length",
            ):
                response_headers[k] = v

        # Add trace headers to response
        response_headers["X-Correlation-ID"] = correlation_id
        response_headers["X-Request-ID"] = request_id

        async def generate_response_body(res: httpx.Response) -> AsyncGenerator[bytes, None]:
            try:
                async for chunk in res.aiter_bytes():
                    yield chunk
            finally:
                await res.aclose()

        latency_ms = (time.time() - start_time) * 1000
        
        # Async audit logging (Step 2.Logging)
        await _log_request(
            db=db,
            correlation_id=correlation_id,
            request=request,
            status_code=status_code,
            latency_ms=latency_ms,
        )

        return StreamingResponse(
            generate_response_body(r),
            status_code=status_code,
            headers=response_headers,
        )

    except httpx.TimeoutException as exc:
        status_code = 504
        error_status = "UPSTREAM_TIMEOUT"
        error_message = f"Upstream service did not respond within {route.timeout_seconds}s"
    except httpx.ConnectError as exc:
        status_code = 503
        error_status = "UPSTREAM_UNAVAILABLE"
        error_message = "Upstream service is unreachable"
    except httpx.HTTPError as exc:
        status_code = 502
        error_status = "UPSTREAM_ERROR"
        error_message = f"HTTP error occurred while calling upstream: {exc}"
    except Exception as exc:
        status_code = 502
        error_status = "UPSTREAM_ERROR"
        error_message = f"An unhandled proxy error occurred: {exc}"

    # Log exception path
    latency_ms = (time.time() - start_time) * 1000
    await _log_request(
        db=db,
        correlation_id=correlation_id,
        request=request,
        status_code=status_code,
        latency_ms=latency_ms,
        error_status=error_status,
        error_message=error_message,
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": error_status,
                "message": error_message,
                "path": request.url.path,
                "correlation_id": correlation_id,
            }
        },
        headers={
            "X-Correlation-ID": correlation_id,
            "X-Request-ID": request_id,
        }
    )


async def _log_request(
    db: Optional[AsyncSession],
    correlation_id: str,
    request: Request,
    status_code: int,
    latency_ms: float,
    error_status: Optional[str] = None,
    error_message: Optional[str] = None,
):
    """Helper to log the request asynchronously to request_logger (memory + PostgreSQL)."""
    try:
        request_logger = RequestLogger()
        await request_logger.log_request_async(
            db=db,
            request_id=correlation_id,
            model="proxy",
            provider="proxy",
            endpoint=f"{request.method} {request.url.path}",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=latency_ms,
            cost_usd=Decimal("0.00000000"),
            cache_status="BYPASS",
            status_code=status_code,
            api_key_id=getattr(request.state, "api_key_id", None),
            tenant_id=getattr(request.state, "tenant_id", None),
            error_status=error_status,
            error_message=error_message,
        )
    except Exception as log_exc:
        logger.error("Failed to log proxy request: %s", log_exc)
