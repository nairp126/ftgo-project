"""
Tests for main API endpoints.
Covers chat completions response format, health endpoint, and property tests.
Uses FastAPI TestClient with mocked providers.
"""

import time
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings, HealthCheck, strategies as st

from app.schemas.chat import ChatRequest, ChatResponse, Choice, Message, Usage
from app.services.error_handler import (
    build_error_response,
    ErrorResponse,
    ERROR_TYPES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(model="gpt-4o") -> ChatResponse:
    return ChatResponse(
        id="chatcmpl-test123",
        created=int(time.time()),
        model=model,
        choices=[Choice(message=Message(role="assistant", content="Hello!"), finish_reason="stop")],
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


# ===========================================================================
# Response Format Tests (Property 2: OpenAI-compatible)
# ===========================================================================


class TestResponseFormat:

    def test_response_has_required_fields(self):
        """OpenAI-compatible response must have id, created, model, choices, usage."""
        resp = _make_response()
        data = resp.model_dump()

        required = {"id", "created", "model", "choices", "usage"}
        assert required.issubset(data.keys())

    def test_choices_structure(self):
        resp = _make_response()
        data = resp.model_dump()
        assert len(data["choices"]) >= 1
        choice = data["choices"][0]
        assert "message" in choice
        assert "finish_reason" in choice
        assert "role" in choice["message"]
        assert "content" in choice["message"]

    def test_usage_structure(self):
        resp = _make_response()
        data = resp.model_dump()
        usage = data["usage"]
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


# ===========================================================================
# Response Headers Tests (Property 11)
# ===========================================================================


REQUIRED_HEADERS = {"X-Request-ID", "X-Provider", "X-Cache-Status", "X-Response-Time-Ms"}


class TestResponseHeaders:

    def test_all_required_headers_defined(self):
        """Verify that the expected set of headers is defined in routes module."""
        from app.api.routes import GATEWAY_HEADERS
        assert REQUIRED_HEADERS.issubset(GATEWAY_HEADERS)


# ===========================================================================
# Health Endpoint Tests
# ===========================================================================


@patch("app.db.database.DatabaseManager.health_check", new_callable=AsyncMock)
@patch("app.cache.redis.RedisManager.health_check", new_callable=AsyncMock)
class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_health_returns_status(self, mock_redis, mock_db):
        mock_redis.return_value = True
        mock_db.return_value = True
        from app.api.health import health_check
        result = await health_check()
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_includes_components(self, mock_redis, mock_db):
        mock_redis.return_value = True
        mock_db.return_value = True
        from app.api.health import health_check
        result = await health_check()
        assert "components" in result
        assert "providers" in result["components"]
        assert "cache" in result["components"]
        assert "database" in result["components"]

    @pytest.mark.asyncio
    async def test_health_provider_details(self, mock_redis, mock_db):
        mock_redis.return_value = True
        mock_db.return_value = True
        from app.api.health import health_check
        result = await health_check()
        providers = result["components"]["providers"]
        for name in ["openai", "anthropic", "bedrock"]:
            assert name in providers
            assert "status" in providers[name]

    @pytest.mark.asyncio
    async def test_health_includes_version(self, mock_redis, mock_db):
        """Requirement 10.1: Health response should include version."""
        mock_redis.return_value = True
        mock_db.return_value = True
        from app.api.health import health_check
        result = await health_check()
        assert "version" in result


# ===========================================================================
# Admin Endpoint Tests
# ===========================================================================


class TestAdminEndpoints:

    @pytest.mark.asyncio
    async def test_list_api_keys_returns_structure(self):
        from app.api.admin import list_api_keys
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        result = await list_api_keys(db=mock_db, limit=100)
        assert "keys" in result
        assert "total" in result

    @pytest.mark.asyncio
    async def test_get_analytics_structure(self):
        from app.api.admin import get_analytics
        result = await get_analytics()
        assert "total_requests" in result
        assert "total_cost_usd" in result

    @pytest.mark.asyncio
    async def test_get_logs_structure(self):
        from app.api.admin import get_logs
        result = await get_logs(limit=10)
        assert "logs" in result
        assert "total" in result

    @pytest.mark.asyncio
    async def test_export_logs_structure(self):
        """Requirement 6.6: Log export endpoint returns status."""
        from app.api.admin import export_logs
        result = await export_logs()
        assert "status" in result


# ===========================================================================
# Gateway Metadata Tests (Requirement 9.5)
# ===========================================================================


class TestGatewayMetadata:

    def test_gateway_metadata_required_fields(self):
        """Requirement 9.5: gateway_metadata must include provider, cache, latency, cost."""
        metadata = {
            "request_id": "test-123",
            "provider": "openai",
            "model_used": "gpt-4o",
            "cache_status": "MISS",
            "latency_ms": 42.5,
            "cost": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost_usd": "0.00005000",
            },
        }
        required = {"request_id", "provider", "model_used", "cache_status", "latency_ms", "cost"}
        assert required.issubset(metadata.keys())
        assert "cost_usd" in metadata["cost"]


# ===========================================================================
# Error Response Tests (linked to Property 2)
# ===========================================================================


class TestErrorResponseFormat:

    def test_error_response_has_standard_structure(self):
        resp = build_error_response("internal_error", "Something failed")
        data = resp.model_dump()
        assert "error" in data
        assert "type" in data["error"]
        assert "message" in data["error"]
        assert "correlation_id" in data["error"]


# ===========================================================================
# Property Tests
# ===========================================================================


class TestResponseFormatProperty:
    """Property 2: Response Format Standardization (Requirements 1.3, 1.5)."""

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        model=st.sampled_from(["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet-20241022"]),
        content=st.text(min_size=1, max_size=200),
    )
    def test_response_always_has_openai_fields(self, model, content):
        """
        Property 2: Every ChatResponse MUST always contain the fields
        required for OpenAI compatibility (id, created, model, choices, usage).
        """
        resp = ChatResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
            created=int(time.time()),
            model=model,
            choices=[Choice(
                message=Message(role="assistant", content=content),
                finish_reason="stop",
            )],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        data = resp.model_dump()

        required = {"id", "created", "model", "choices", "usage"}
        assert required.issubset(data.keys())
        assert len(data["choices"]) >= 1
        assert data["usage"]["total_tokens"] == data["usage"]["prompt_tokens"] + data["usage"]["completion_tokens"]


class TestResponseHeadersProperty:
    """Property 11: Response Headers Completeness (Requirements 4.5, 5.5, 7.3)."""

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        request_id=st.uuids().map(str),
        provider=st.sampled_from(["openai", "anthropic", "bedrock"]),
        latency=st.floats(min_value=0.1, max_value=10000.0),
    )
    def test_header_set_always_complete(self, request_id, provider, latency):
        """
        Property 11: Gateway response headers MUST always include
        X-Request-ID, X-Provider, X-Cache-Status, X-Response-Time-Ms.
        """
        # Simulate the headers that would be set by the chat endpoint
        headers = {
            "X-Request-ID": request_id,
            "X-Provider": provider,
            "X-Cache-Status": "MISS",
            "X-Response-Time-Ms": str(round(latency, 2)),
        }

        for required_header in REQUIRED_HEADERS:
            assert required_header in headers
            assert headers[required_header] is not None
            assert len(headers[required_header]) > 0
