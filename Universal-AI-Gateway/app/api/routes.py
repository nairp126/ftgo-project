"""
Main API routes — /v1/chat/completions endpoint.
Supports Requirements 1.1, 1.3, 1.4, 1.5, 4.5, 5.1–5.5, 7.3, 9.5.
"""

import json
import logging
import os
import time
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.error_handler import (
    build_error_response,
    generate_correlation_id,
    validation_error,
    provider_error,
    internal_error,
)
from app.services.token_counter import count_request_tokens, extract_response_tokens
from app.services.cost_calculator import calculate_request_cost
from app.services.metrics import metrics
from app.services.request_logger import RequestLogger
from app.services.router import RoutingEngine
from app.services.ensembler import ModelEnsembler
from app.cache.cache_manager import CacheManager, generate_cache_key
from app.services.budget_manager import BudgetManager, BudgetExceededError
from app.services.prompt_safety import PromptSafetyScrubber, SecurityPolicyViolation
from app.core.tracing import get_tracer
from app.core.config import get_settings
from app.services.pii_redactor import redact_pii

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["Chat"])
request_logger = RequestLogger()
tracer = get_tracer(__name__)

# Singleton routing engine — created once, reused across requests (R2-2)
_routing_engine = RoutingEngine()

# Singleton model ensembler
_ensembler = ModelEnsembler(_routing_engine)

# Singleton cache manager (R2-3)
_cache = CacheManager()

# Singleton budget manager
_budget_manager = BudgetManager()


async def close_router_clients():
    """Close HTTP clients initialized in the router."""
    if _routing_engine:
        await _routing_engine.close_clients()
    try:
        from app.services.embeddings import close_embeddings_client
        await close_embeddings_client()
    except Exception as e:
        logger.warning("Failed to close embeddings client: %s", e)


# Required response headers (Requirements 4.5, 5.5, 7.3)
GATEWAY_HEADERS = {
    "X-Request-ID",
    "X-Provider",
    "X-Cache-Status",
    "X-Response-Time-Ms",
}


@router.post(
    "/chat/completions",
    response_model=ChatResponse,
    responses={
        200: {
            "headers": {
                "X-Request-ID": {"description": "Unique request ID", "schema": {"type": "string"}},
                "X-Provider": {"description": "Provider that handled the request", "schema": {"type": "string"}},
                "X-Cache-Status": {"description": "HIT, MISS, or BYPASS", "schema": {"type": "string"}},
                "X-Response-Time-Ms": {"description": "Gateway latency", "schema": {"type": "string"}},
                "X-Correlation-ID": {"description": "Tracing ID", "schema": {"type": "string"}},
                "X-Tenant-Budget-Remaining": {"description": "Remaining budget (optional)", "schema": {"type": "string"}},
            }
        },
        402: {"description": "Budget Exceeded"},
        403: {"description": "Security Policy Violation"},
    }
)
async def chat_completions(
    chat_request: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    OpenAI-compatible chat completions endpoint (Requirement 1.1).

    Integrates routing, token counting, cost calculation,
    caching, and returns standardized response with required headers.
    """
    request_id = str(uuid.uuid4())
    correlation_id = generate_correlation_id()
    start_time = time.time()
    
    logger.info("Request state contains: %s", request.state._state)
    tenant_id = getattr(request.state, "tenant_id", None)
    
    # Financial Budget pre-flight check
    if tenant_id:
        try:
            limit = getattr(request.state, "daily_cost_limit", None)
            await _budget_manager.check_budget(tenant_id, max_budget=limit)
        except BudgetExceededError as e:
            err = build_error_response("budget_exceeded", str(e), correlation_id)
            return JSONResponse(
                status_code=402,
                headers={"X-Correlation-ID": correlation_id},
                content=err.model_dump(),
            )

    # 2. Prompt Injection Safety Scrubbing
    try:
        PromptSafetyScrubber.verify_safety(chat_request)
    except SecurityPolicyViolation as e:
        logger.warning(
            "Prompt Injection blocked [%s]: %s (pattern matched: '%s')",
            correlation_id, e, e.matched_pattern
        )
        err = build_error_response("policy_violation", str(e), correlation_id).model_dump()
        err["error"]["matched_pattern"] = e.matched_pattern
        return JSONResponse(
            status_code=403,
            headers={"X-Correlation-ID": correlation_id},
            content=err,
        )

    # 3. PII Redaction
    settings = get_settings()
    if settings.logging.log_pii_redaction:
        for message in chat_request.messages:
            message.content = redact_pii(message.content)

    try:
        # Check if streaming is requested (Requirement 1.4)
        if chat_request.stream:
            return await _handle_streaming(
                chat_request, request_id, correlation_id, start_time, db, tenant_id
            )

        # --- Cache lookup (Requirement 5.1–5.5) ---
        bypass_cache = CacheManager.should_bypass(request)
        cache_status = "BYPASS" if bypass_cache else "MISS"

        if not bypass_cache:
            cache_key = generate_cache_key(chat_request)
            with tracer.start_as_current_span("cache_lookup", attributes={"cache.key": cache_key}):
                try:
                    cached_response = await _cache.get(cache_key, request=chat_request)
                except Exception:
                    cached_response = None

            if cached_response:
                cache_status = "HIT"
                latency_ms = (time.time() - start_time) * 1000
                metrics.record_request("cache", latency_ms)
                metrics.record_cache(hit=True)
                response_data = cached_response.model_dump()
                response_data["gateway_metadata"] = {
                    "request_id": request_id,
                    "cache_status": "HIT",
                    "latency_ms": round(latency_ms, 2),
                }
                return JSONResponse(
                    content=response_data,
                    headers={
                        "X-Request-ID": request_id,
                        "X-Cache-Status": "HIT",
                        "X-Response-Time-Ms": str(round(latency_ms, 2)),
                        "X-Correlation-ID": correlation_id,
                    },
                )
        else:
            _cache.record_bypass()
            cache_key = None

        # Count input tokens (Requirement 9.1)
        with tracer.start_as_current_span("count_request_tokens"):
            prompt_tokens = count_request_tokens(chat_request)

        # Route to provider using singleton engine (R2-2) or run Ensembler
        with tracer.start_as_current_span("provider_invoke") as provider_span:
            if chat_request.ensemble_strategy and chat_request.ensemble_models:
                response, decision = await _ensembler.execute_ensemble(
                    chat_request, 
                    request_id, 
                    chat_request.ensemble_strategy, 
                    chat_request.ensemble_models
                )
            else:
                response, decision = await _routing_engine.route_request(
                    chat_request, request_id=request_id
                )
                
            provider_span.set_attribute("provider", decision.provider)
            provider_span.set_attribute("model", decision.resolved_model)

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Extract token counts (Requirement 9.2, 9.4)
        token_usage = extract_response_tokens(response)

        # Calculate cost (Requirement 9.3, 9.5)
        cost_data = calculate_request_cost(
            response.model, token_usage
        )

        # Increment tenant budget
        if tenant_id:
            try:
                await _budget_manager.add_cost(tenant_id, float(cost_data["cost_usd"]))
            except Exception as e:
                logger.error("Failed to update budget for tenant %s: %s", tenant_id, e)

        # --- Cache store (Requirement 5.2) ---
        if cache_key:
            with tracer.start_as_current_span("cache_store", attributes={"cache.key": cache_key}):
                try:
                    await _cache.set(cache_key, response, request=chat_request)
                except Exception as exc:
                    logger.warning("Cache store failed: %s", exc)

        # Build gateway metadata (Requirement 9.5)
        gateway_metadata = {
            "request_id": request_id,
            "provider": decision.provider,
            "model_used": decision.resolved_model,
            "cache_status": cache_status,
            "latency_ms": round(latency_ms, 2),
            "cost": {
                "prompt_tokens": cost_data["prompt_tokens"],
                "completion_tokens": cost_data["completion_tokens"],
                "total_tokens": cost_data["total_tokens"],
                "cost_usd": str(cost_data["cost_usd"]),
            },
        }

        # Build response body (Requirement 1.3, 1.5)
        response_data = response.model_dump()
        response_data["gateway_metadata"] = gateway_metadata

        # Build response headers (Requirements 4.5, 5.5, 7.3)
        headers = {
            "X-Request-ID": request_id,
            "X-Provider": decision.provider,
            "X-Cache-Status": cache_status,
            "X-Response-Time-Ms": str(round(latency_ms, 2)),
            "X-Correlation-ID": correlation_id,
        }
        
        if tenant_id:
            spend = await _budget_manager.get_tenant_spend(tenant_id)
            budget = _budget_manager.default_budget
            remaining = max(Decimal("0.00"), budget - spend)
            headers["X-Tenant-Budget-Remaining"] = str(remaining)

        # Record metrics (Requirement 15.2–15.6)
        metrics.record_request(decision.provider, latency_ms)
        metrics.record_cache(hit=False)
        metrics.record_cost(float(cost_data["cost_usd"]))
        metrics.record_tokens(
            cost_data["prompt_tokens"], cost_data["completion_tokens"]
        )

        # Log request (Requirement 6.1–6.4)
        await request_logger.log_request_async(
            db=db,
            request_id=request_id,
            model=response.model,
            provider=decision.provider,
            prompt_tokens=cost_data["prompt_tokens"],
            completion_tokens=cost_data["completion_tokens"],
            total_tokens=cost_data["total_tokens"],
            latency_ms=latency_ms,
            cost_usd=cost_data["cost_usd"],
            cache_status=cache_status,
            api_key_id=getattr(request.state, "api_key_id", None),
            tenant_id=tenant_id,
            routing_decision=decision.to_dict()
        )

        return JSONResponse(content=response_data, headers=headers)

    except Exception as exc:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(
            "Chat completion failed [%s]: %s (type: %s)", correlation_id, exc, type(exc)
        )

        # Record error metrics
        metrics.record_request(
            getattr(exc, "provider", "unknown"), latency_ms, error=True
        )

        resp, status = provider_error(
            message=str(exc), correlation_id=correlation_id
        )
        return JSONResponse(
            status_code=status,
            content=resp.model_dump(),
            headers={
                "X-Request-ID": request_id,
                "X-Correlation-ID": correlation_id,
                "X-Response-Time-Ms": str(round(latency_ms, 2)),
            },
        )


async def _handle_streaming(
    chat_request: ChatRequest,
    request_id: str,
    correlation_id: str,
    start_time: float,
    db: AsyncSession,
    tenant_id: Optional[str] = None,
) -> StreamingResponse:
    """
    Handle streaming chat completion (Requirement 1.4).

    Returns SSE-formatted response using the provider's stream_completion().
    """
    async def event_generator():
        content_parts = []
        provider_used = "unknown"
        model_used = chat_request.model
        
        try:
            with tracer.start_as_current_span("provider_stream_invoke") as stream_span:
                stream_obj, decision = await _routing_engine.stream_request(
                    chat_request, request_id=request_id
                )
                provider_used = decision.provider
                model_used = decision.resolved_model
                
                async for chunk in stream_obj:
                    if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                        try:
                            data = json.loads(chunk[6:].strip())
                            if "gateway_metadata" in data and "provider" in data["gateway_metadata"]:
                                provider_used = data["gateway_metadata"]["provider"]
                            if "model" in data:
                                model_used = data["model"]
                            if data.get("choices") and data["choices"][0].get("delta", {}).get("content"):
                                content_parts.append(data["choices"][0]["delta"]["content"])
                        except Exception:
                            pass
                    yield chunk
                yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.error("Streaming failed [%s]: %s", correlation_id, exc)
            err = build_error_response("provider_error", str(exc), correlation_id)
            yield f"data: {json.dumps(err.model_dump())}\n\n"
        finally:
            # 1. Reconstruct full response & Count tokens
            final_content = "".join(content_parts)
            prompt_tokens = count_request_tokens(chat_request)
            from app.services.token_counter import count_text_tokens
            completion_tokens = count_text_tokens(final_content, model_used) if final_content else 0
            
            # 2. Calculate cost
            cost_data = calculate_request_cost(model_used, {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens})
            
            # 3. Budget Tracking
            if tenant_id:
                try:
                    await _budget_manager.add_cost(tenant_id, float(cost_data["cost_usd"]))
                except Exception as e:
                    logger.error("Failed to update budget for tenant %s: %s", tenant_id, e)
                    
            # 4. Record final metrics
            latency_ms = (time.time() - start_time) * 1000
            metrics.record_request(provider_used, latency_ms)
            metrics.record_cost(float(cost_data["cost_usd"]))
            metrics.record_tokens(prompt_tokens, completion_tokens)
            
            # 5. Log Request
            await request_logger.log_request_async(
                db=db,
                request_id=request_id,
                model=model_used,
                provider=provider_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                latency_ms=latency_ms,
                cost_usd=Decimal(str(cost_data["cost_usd"])),
                cache_status="MISS",
                tenant_id=tenant_id
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "X-Request-ID": request_id,
            "X-Correlation-ID": correlation_id,
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Reverse Proxy Routes (Step 3)
# ---------------------------------------------------------------------------

from fastapi import Response
from app.core.proxy_config import get_route
from app.services.proxy import forward_request

proxy_router = APIRouter(tags=["Proxy"])


@proxy_router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
)
async def proxy_request(
    request: Request,
    full_path: str,
    db: AsyncSession = Depends(get_db)
) -> Response:
    """
    Catch-all proxy endpoint forwarding matched routes to the downstream API gateway.
    """
    route = get_route(request.url.path)
    if route is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "ROUTE_NOT_FOUND",
                    "path": request.url.path,
                    "message": f"No proxy route matched path: {request.url.path}"
                }
            }
        )

    try:
        return await forward_request(request, route, db)
    except Exception as exc:
        logger.error("Unhandled proxy exception: %s", exc, exc_info=True)
        correlation_id = request.headers.get("X-Correlation-ID") or getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unhandled error occurred while routing your request.",
                    "path": request.url.path,
                    "correlation_id": correlation_id
                }
            }
        )
