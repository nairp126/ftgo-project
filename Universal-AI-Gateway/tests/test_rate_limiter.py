"""
Tests for rate limiting system.
Tests token bucket logic, middleware, and property-based tests.
All tests use mock Redis — no live Redis required.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings, HealthCheck, strategies as st

from app.services.rate_limiter import (
    TokenBucketRateLimiter,
    RateLimitResult,
    DEFAULT_RPM,
    DEFAULT_BURST,
    DEFAULT_TENANT_RPM,
    DEFAULT_GLOBAL_RPM,
)


# ---------------------------------------------------------------------------
# Mock Redis helpers
# ---------------------------------------------------------------------------

class FakeRedisClient:
    """In-memory fake Redis for testing token bucket without real Redis."""

    def __init__(self):
        self._store = {}
        self._expiry = {}

    async def get(self, key):
        return self._store.get(key)

    async def set(self, key, value, **kwargs):
        self._store[key] = value
        return True

    async def expire(self, key, ttl):
        self._expiry[key] = ttl
        return True

    async def delete(self, *keys):
        for k in keys:
            self._store.pop(k, None)
        return len(keys)

    async def eval(self, script, numkeys, bucket_key, capacity, refill_rate, now):
        tokens_raw = self._store.get(bucket_key)
        last_raw = self._store.get(f"{bucket_key}:last")

        tokens = float(capacity)
        last_refill = float(now)

        if tokens_raw is not None:
            tokens = float(tokens_raw)
        if last_raw is not None:
            last_refill = float(last_raw)

        elapsed = float(now) - last_refill
        if elapsed > 0:
            tokens = min(float(capacity), tokens + elapsed * float(refill_rate))

        allowed = 0
        if tokens >= 1.0:
            tokens -= 1.0
            allowed = 1

        self._store[bucket_key] = str(tokens)
        self._store[f"{bucket_key}:last"] = str(now)
        self._expiry[bucket_key] = 120
        self._expiry[f"{bucket_key}:last"] = 120

        return [allowed, str(tokens)]

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    """Fake pipeline that batches commands."""

    def __init__(self, client: FakeRedisClient):
        self._client = client
        self._commands = []

    def get(self, key):
        self._commands.append(("get", key))
        return self

    def set(self, key, value):
        self._commands.append(("set", key, value))
        return self

    def expire(self, key, ttl):
        self._commands.append(("expire", key, ttl))
        return self

    async def execute(self):
        results = []
        for cmd in self._commands:
            if cmd[0] == "get":
                results.append(self._client._store.get(cmd[1]))
            elif cmd[0] == "set":
                self._client._store[cmd[1]] = cmd[2]
                results.append(True)
            elif cmd[0] == "expire":
                self._client._expiry[cmd[1]] = cmd[2]
                results.append(True)
        self._commands = []
        return results


def _mock_redis_manager(client: FakeRedisClient = None):
    """Create a mock RedisManager backed by FakeRedisClient."""
    client = client or FakeRedisClient()
    mock = MagicMock()
    mock.get_client = MagicMock(return_value=client)
    return mock


# ===========================================================================
# Token Bucket Unit Tests
# ===========================================================================


class TestTokenBucketBasics:

    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        limiter = TokenBucketRateLimiter(redis=_mock_redis_manager())
        result = await limiter.check_rate_limit("key-1", rate_per_minute=60, burst=10)
        assert result.allowed is True
        assert result.remaining >= 0

    @pytest.mark.asyncio
    async def test_capacity_equals_rate_plus_burst(self):
        limiter = TokenBucketRateLimiter(redis=_mock_redis_manager())
        result = await limiter.check_rate_limit("key-1", rate_per_minute=60, burst=10)
        assert result.limit == 70  # 60 + 10

    @pytest.mark.asyncio
    async def test_exhaustion_after_capacity(self):
        """After consuming all tokens, next request should be denied."""
        client = FakeRedisClient()
        limiter = TokenBucketRateLimiter(redis=_mock_redis_manager(client))

        capacity = 5
        for i in range(capacity):
            r = await limiter.check_rate_limit("key-1", rate_per_minute=capacity, burst=0)
            assert r.allowed is True, f"Request {i+1} should be allowed"

        denied = await limiter.check_rate_limit("key-1", rate_per_minute=capacity, burst=0)
        assert denied.allowed is False
        assert denied.retry_after is not None
        assert denied.retry_after >= 1

    @pytest.mark.asyncio
    async def test_result_has_required_fields(self):
        limiter = TokenBucketRateLimiter(redis=_mock_redis_manager())
        result = await limiter.check_rate_limit("key-1")
        assert isinstance(result, RateLimitResult)
        assert isinstance(result.allowed, bool)
        assert isinstance(result.limit, int)
        assert isinstance(result.remaining, int)
        assert isinstance(result.reset_at, float)


class TestTenantRateLimit:

    @pytest.mark.asyncio
    async def test_tenant_limit_check(self):
        limiter = TokenBucketRateLimiter(redis=_mock_redis_manager())
        result = await limiter.check_tenant_limit("tenant-1", rate_per_minute=100)
        assert result.allowed is True
        assert result.limit == 100


class TestGlobalRateLimit:

    @pytest.mark.asyncio
    async def test_global_limit_check(self):
        limiter = TokenBucketRateLimiter(redis=_mock_redis_manager())
        result = await limiter.check_global_limit(rate_per_minute=1000)
        assert result.allowed is True
        assert result.limit == 1000


class TestRateLimiterFailOpen:

    @pytest.mark.asyncio
    async def test_fails_open_on_redis_error(self):
        """If Redis is down, requests should be allowed (fail open)."""
        mock = MagicMock()
        broken_client = MagicMock()
        broken_client.pipeline = MagicMock(side_effect=Exception("Redis down"))
        mock.get_client = MagicMock(return_value=broken_client)

        limiter = TokenBucketRateLimiter(redis=mock)
        result = await limiter.check_rate_limit("key-1")
        assert result.allowed is True


class TestResetBucket:

    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        client = FakeRedisClient()
        client._store["rate_limit:key-1:tokens"] = "0"
        client._store["rate_limit:key-1:tokens:last"] = str(time.time())

        limiter = TokenBucketRateLimiter(redis=_mock_redis_manager(client))
        ok = await limiter.reset_bucket("key-1")
        assert ok is True
        assert "rate_limit:key-1:tokens" not in client._store


# ===========================================================================
# Property Tests — Token Bucket Behavior (Property 10)
# ===========================================================================


class TestTokenBucketProperty:

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        rate=st.integers(min_value=1, max_value=100),
        burst=st.integers(min_value=0, max_value=50),
    )
    @pytest.mark.asyncio
    async def test_first_request_always_allowed(self, rate, burst):
        """
        Property 10: On a fresh bucket, the first request is ALWAYS allowed,
        regardless of rate/burst configuration.
        """
        limiter = TokenBucketRateLimiter(redis=_mock_redis_manager())
        result = await limiter.check_rate_limit(
            f"prop-key-{rate}-{burst}",
            rate_per_minute=rate,
            burst=burst,
        )
        assert result.allowed is True
        assert result.limit == rate + burst

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(capacity=st.integers(min_value=1, max_value=20))
    @pytest.mark.asyncio
    async def test_capacity_exhaustion(self, capacity):
        """
        Property 10: After consuming exactly `capacity` tokens,
        the next request MUST be denied.
        """
        client = FakeRedisClient()
        limiter = TokenBucketRateLimiter(redis=_mock_redis_manager(client))
        key = f"exhaust-{capacity}"

        for _ in range(capacity):
            r = await limiter.check_rate_limit(key, rate_per_minute=capacity, burst=0)
            assert r.allowed is True

        denied = await limiter.check_rate_limit(key, rate_per_minute=capacity, burst=0)
        assert denied.allowed is False


# ===========================================================================
# Property Tests — Aggregate Rate Limiting (Property 18)
# ===========================================================================


class TestAggregateRateLimitProperty:

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(rate=st.integers(min_value=1, max_value=50))
    @pytest.mark.asyncio
    async def test_tenant_exhaustion(self, rate):
        """
        Property 18: After consuming all tenant tokens, the next request
        on ANY key under that tenant MUST be denied.
        """
        client = FakeRedisClient()
        limiter = TokenBucketRateLimiter(redis=_mock_redis_manager(client))
        tenant = f"tenant-{rate}"

        for _ in range(rate):
            r = await limiter.check_tenant_limit(tenant, rate_per_minute=rate)
            assert r.allowed is True

        denied = await limiter.check_tenant_limit(tenant, rate_per_minute=rate)
        assert denied.allowed is False


# ===========================================================================
# Property Tests — Global Rate Limiting (Property 19)
# ===========================================================================


class TestGlobalRateLimitProperty:

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(rate=st.integers(min_value=1, max_value=50))
    @pytest.mark.asyncio
    async def test_global_exhaustion(self, rate):
        """
        Property 19: After consuming all global tokens, any request
        MUST be denied.
        """
        client = FakeRedisClient()
        limiter = TokenBucketRateLimiter(redis=_mock_redis_manager(client))

        for _ in range(rate):
            r = await limiter.check_global_limit(rate_per_minute=rate)
            assert r.allowed is True

        denied = await limiter.check_global_limit(rate_per_minute=rate)
        assert denied.allowed is False


class TestRateLimiterFallback:

    @pytest.mark.asyncio
    async def test_fallback_when_redis_fails(self):
        """Verify rate limiter falls back to in-memory rate limiting when Redis raises an exception."""
        mock_client = MagicMock()
        mock_client.eval = AsyncMock(side_effect=Exception("Redis connection error"))
        
        mock_redis = MagicMock()
        mock_redis.get_client = MagicMock(return_value=mock_client)
        
        limiter = TokenBucketRateLimiter(redis=mock_redis)
        
        # Initial requests allowed (capacity = rate + burst = 2 + 0 = 2)
        res1 = await limiter.check_rate_limit("key-fail", rate_per_minute=2, burst=0)
        assert res1.allowed is True
        
        res2 = await limiter.check_rate_limit("key-fail", rate_per_minute=2, burst=0)
        assert res2.allowed is True
        
        # Third request denied (empty)
        res3 = await limiter.check_rate_limit("key-fail", rate_per_minute=2, burst=0)
        assert res3.allowed is False
