"""
Unit tests for the caching system.
All tests use a mock Redis — no live Redis required.
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Choice,
    Message,
    Usage,
)
from app.cache.cache_manager import (
    CacheManager,
    generate_cache_key,
    CACHE_KEY_PREFIX,
    DEFAULT_TTL_SECONDS,
    MAX_CACHE_ENTRY_BYTES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(**overrides) -> ChatRequest:
    defaults = dict(
        model="gpt-4o",
        messages=[Message(role="user", content="Hello")],
    )
    defaults.update(overrides)
    return ChatRequest(**defaults)


def _make_response(**overrides) -> ChatResponse:
    defaults = dict(
        id="test-123",
        created=int(time.time()),
        model="gpt-4o",
        choices=[
            Choice(
                message=Message(role="assistant", content="Hi!"),
                finish_reason="stop",
            )
        ],
        usage=Usage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
    )
    defaults.update(overrides)
    return ChatResponse(**defaults)


def _mock_redis() -> MagicMock:
    """Create a mock RedisManager with async methods."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.get_client = MagicMock()
    return mock


# ===========================================================================
# Cache Key Generation Tests
# ===========================================================================


class TestGenerateCacheKey:

    def test_returns_prefixed_hex(self):
        key = generate_cache_key(_make_request())
        assert key.startswith(CACHE_KEY_PREFIX)
        # SHA-256 hex = 64 chars
        hex_part = key[len(CACHE_KEY_PREFIX):]
        assert len(hex_part) == 64

    def test_deterministic(self):
        req = _make_request()
        assert generate_cache_key(req) == generate_cache_key(req)

    def test_same_params_same_key(self):
        a = _make_request(model="gpt-4o", temperature=0.7)
        b = _make_request(model="gpt-4o", temperature=0.7)
        assert generate_cache_key(a) == generate_cache_key(b)

    def test_different_model_different_key(self):
        a = _make_request(model="gpt-4o")
        b = _make_request(model="gpt-4o-mini")
        assert generate_cache_key(a) != generate_cache_key(b)

    def test_different_messages_different_key(self):
        a = _make_request(messages=[Message(role="user", content="Hello")])
        b = _make_request(messages=[Message(role="user", content="Goodbye")])
        assert generate_cache_key(a) != generate_cache_key(b)

    def test_different_temperature_different_key(self):
        a = _make_request(temperature=0.5)
        b = _make_request(temperature=0.9)
        assert generate_cache_key(a) != generate_cache_key(b)

    def test_different_max_tokens_different_key(self):
        a = _make_request(max_tokens=100)
        b = _make_request(max_tokens=200)
        assert generate_cache_key(a) != generate_cache_key(b)

    def test_different_top_p_different_key(self):
        a = _make_request(top_p=0.9)
        b = _make_request(top_p=0.5)
        assert generate_cache_key(a) != generate_cache_key(b)

    def test_none_top_p_handled(self):
        """top_p=None should produce a valid key."""
        key = generate_cache_key(_make_request(top_p=None))
        assert key.startswith(CACHE_KEY_PREFIX)


# ===========================================================================
# CacheManager.get Tests
# ===========================================================================


class TestCacheGet:

    @pytest.mark.asyncio
    async def test_cache_miss(self):
        redis = _mock_redis()
        redis.get = AsyncMock(return_value=None)
        cm = CacheManager(redis=redis)

        result = await cm.get("cache:exact:abc123")
        assert result is None
        assert cm.get_stats()["misses"] == 1

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        resp = _make_response()
        redis = _mock_redis()
        redis.get = AsyncMock(return_value=resp.model_dump_json())
        cm = CacheManager(redis=redis)

        result = await cm.get("cache:exact:abc123")
        assert result is not None
        assert result.id == "test-123"
        assert cm.get_stats()["hits"] == 1

    @pytest.mark.asyncio
    async def test_corrupted_json_counts_as_miss(self):
        redis = _mock_redis()
        redis.get = AsyncMock(return_value="not-valid-json{{{")
        cm = CacheManager(redis=redis)

        result = await cm.get("cache:exact:abc123")
        assert result is None
        assert cm.get_stats()["misses"] == 1


# ===========================================================================
# CacheManager.set Tests
# ===========================================================================


class TestCacheSet:

    @pytest.mark.asyncio
    async def test_stores_response(self):
        redis = _mock_redis()
        cm = CacheManager(redis=redis)
        resp = _make_response()

        ok = await cm.set("cache:exact:abc123", resp)
        assert ok is True
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_default_ttl(self):
        redis = _mock_redis()
        cm = CacheManager(redis=redis)
        resp = _make_response()

        await cm.set("k", resp)
        _, kwargs = redis.set.call_args
        assert kwargs["ttl"] == DEFAULT_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_custom_ttl(self):
        redis = _mock_redis()
        cm = CacheManager(redis=redis)
        resp = _make_response()

        await cm.set("k", resp, ttl=3600)
        _, kwargs = redis.set.call_args
        assert kwargs["ttl"] == 3600

    @pytest.mark.asyncio
    async def test_rejects_oversized_entry(self):
        redis = _mock_redis()
        cm = CacheManager(redis=redis)

        # Create a response with content > 1 MB
        big_content = "x" * (MAX_CACHE_ENTRY_BYTES + 1000)
        resp = _make_response()
        resp.choices[0].message.content = big_content

        ok = await cm.set("k", resp)
        assert ok is False
        redis.set.assert_not_awaited()


# ===========================================================================
# CacheManager.should_bypass Tests
# ===========================================================================


def _make_starlette_request(method: str, path: str, headers: dict = None) -> Request:
    from starlette.datastructures import Headers
    return Request(scope={
        "type": "http",
        "method": method,
        "path": path,
        "headers": Headers(headers or {}).raw,
    })


class TestCacheBypass:

    def test_no_headers_no_bypass(self):
        req1 = _make_starlette_request("POST", "/v1/chat/completions", None)
        assert CacheManager.should_bypass(req1) is False
        req2 = _make_starlette_request("POST", "/v1/chat/completions", {})
        assert CacheManager.should_bypass(req2) is False

    def test_cache_control_no_cache(self):
        req = _make_starlette_request("POST", "/v1/chat/completions", {"Cache-Control": "no-cache"})
        assert CacheManager.should_bypass(req) is True

    def test_cache_control_case_insensitive(self):
        req = _make_starlette_request("POST", "/v1/chat/completions", {"cache-control": "no-cache"})
        assert CacheManager.should_bypass(req) is True

    def test_x_cache_bypass_header(self):
        req = _make_starlette_request("POST", "/v1/chat/completions", {"X-Cache-Bypass": "true"})
        assert CacheManager.should_bypass(req) is True

    def test_x_cache_bypass_case_insensitive(self):
        req = _make_starlette_request("POST", "/v1/chat/completions", {"x-cache-bypass": "True"})
        assert CacheManager.should_bypass(req) is True

    def test_unrelated_headers_no_bypass(self):
        req = _make_starlette_request("POST", "/v1/chat/completions", {"Authorization": "Bearer xxx"})
        assert CacheManager.should_bypass(req) is False

    def test_http_method_bypass(self):
        # GET /v1/chat/completions (not standard, but checks headers)
        req_get_llm = _make_starlette_request("GET", "/v1/chat/completions")
        assert CacheManager.should_bypass(req_get_llm) is False

        # POST /api/orders (non-LLM POST) -> must bypass
        req_post_orders = _make_starlette_request("POST", "/api/orders")
        assert CacheManager.should_bypass(req_post_orders) is True

        # PUT /api/orders/123/cancel -> must bypass
        req_put_orders = _make_starlette_request("PUT", "/api/orders/123/cancel")
        assert CacheManager.should_bypass(req_put_orders) is True

        # DELETE /api/orders/123 -> must bypass
        req_delete_orders = _make_starlette_request("DELETE", "/api/orders/123")
        assert CacheManager.should_bypass(req_delete_orders) is True

        # GET /api/orders/123 -> should not bypass by method (eligible for cache)
        req_get_orders = _make_starlette_request("GET", "/api/orders/123")
        assert CacheManager.should_bypass(req_get_orders) is False


# ===========================================================================
# CacheManager Stats Tests
# ===========================================================================


class TestCacheStats:

    @pytest.mark.asyncio
    async def test_stats_accumulate(self):
        redis = _mock_redis()
        redis.get = AsyncMock(return_value=None)
        cm = CacheManager(redis=redis)

        await cm.get("a")
        await cm.get("b")
        cm.record_bypass()

        stats = cm.get_stats()
        assert stats["misses"] == 2
        assert stats["bypasses"] == 1
        assert stats["total"] == 3

    def test_reset_stats(self):
        cm = CacheManager(redis=_mock_redis())
        cm._hits = 5
        cm._misses = 3
        cm.reset_stats()
        assert cm.get_stats()["total"] == 0

    def test_hit_rate_calculation(self):
        cm = CacheManager(redis=_mock_redis())
        cm._hits = 3
        cm._misses = 7
        stats = cm.get_stats()
        assert stats["hit_rate"] == 0.3

    def test_hit_rate_zero_when_empty(self):
        cm = CacheManager(redis=_mock_redis())
        assert cm.get_stats()["hit_rate"] == 0.0


# ===========================================================================
# Round-trip Serialization Test
# ===========================================================================


class TestCacheRoundTrip:

    @pytest.mark.asyncio
    async def test_set_then_get_roundtrip(self):
        """Simulate a full cache set → get cycle."""
        stored = {}

        async def mock_set(key, value, ttl=None):
            stored[key] = value
            return True

        async def mock_get(key):
            return stored.get(key)

        redis = _mock_redis()
        redis.set = mock_set
        redis.get = mock_get
        cm = CacheManager(redis=redis)

        original = _make_response()
        key = "cache:exact:roundtrip"

        await cm.set(key, original)
        recovered = await cm.get(key)

        assert recovered is not None
        assert recovered.id == original.id
        assert recovered.choices[0].message.content == original.choices[0].message.content
        assert recovered.usage.total_tokens == original.usage.total_tokens


class TestCacheSettingsAndDimension:

    @pytest.mark.asyncio
    async def test_semantic_cache_custom_dimension(self):
        """Verify semantic cache index creation command utilizes configured settings dimension."""
        redis = _mock_redis()
        mock_client = AsyncMock()
        redis.get_client = MagicMock(return_value=mock_client)
        
        # First call fails (FT.INFO index doesn't exist), second call succeeds (FT.CREATE)
        mock_client.execute_command = AsyncMock(side_effect=[Exception("index not found"), True])
        
        from app.core.config import get_settings
        settings = get_settings()
        
        original_dim = settings.cache.semantic_cache_dimension
        settings.cache.semantic_cache_dimension = 768
        
        try:
            cm = CacheManager(redis=redis)
            await cm._init_semantic_index()
            
            args = mock_client.execute_command.call_args_list
            assert len(args) == 2
            create_args = args[1][0]
            assert "FT.CREATE" in create_args
            assert "768" in create_args
        finally:
            settings.cache.semantic_cache_dimension = original_dim
