"""
Tests for the routing engine.
Covers model resolution, fallback chains, decision logging, and property tests.
All tests run in-memory — no external API calls.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings, HealthCheck, strategies as st

from app.providers.base import ProviderError, MODEL_PROVIDER_MAP
from app.schemas.chat import ChatRequest, ChatResponse, Choice, Message, Usage
from app.services.router import (
    RoutingEngine,
    RoutingDecision,
    DEFAULT_MODEL,
    FALLBACK_CHAINS,
    PROVIDER_DEFAULT_MODELS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(model="gpt-4o") -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=[Message(role="user", content="Hello")],
    )


def _make_response(model="gpt-4o") -> ChatResponse:
    return ChatResponse(
        id="test-123",
        created=int(time.time()),
        model=model,
        choices=[Choice(message=Message(role="assistant", content="Hi!"), finish_reason="stop")],
        usage=Usage(prompt_tokens=5, completion_tokens=3, total_tokens=8),
    )


def _mock_provider(name: str, succeed: bool = True):
    """Create a mock provider that either succeeds or fails."""
    provider = MagicMock()
    provider.provider_name = name
    provider.supported_models = list(MODEL_PROVIDER_MAP.keys())
    provider.supports_model = MagicMock(return_value=True)

    if succeed:
        provider.chat_completion = AsyncMock(return_value=_make_response())
    else:
        provider.chat_completion = AsyncMock(
            side_effect=ProviderError(f"{name} failed", name, 500)
        )
    return provider


# ===========================================================================
# Model Resolution Tests
# ===========================================================================


class TestModelResolution:

    def setup_method(self):
        self.engine = RoutingEngine()

    def test_explicit_openai_model(self):
        model, provider, reason = self.engine.resolve_provider("gpt-4o")
        assert model == "gpt-4o"
        assert provider == "openai"
        assert reason == "explicit_model"

    def test_explicit_anthropic_model(self):
        model, provider, reason = self.engine.resolve_provider("claude-3-5-sonnet-20241022")
        assert provider == "anthropic"
        assert reason == "explicit_model"

    def test_explicit_bedrock_model(self):
        model, provider, reason = self.engine.resolve_provider("bedrock/claude-3-5-sonnet")
        assert provider == "bedrock"
        assert reason == "explicit_model"

    def test_default_model_when_none(self):
        model, provider, reason = self.engine.resolve_provider(None)
        assert model == DEFAULT_MODEL
        assert reason == "default_model"

    def test_unknown_model_falls_back_to_default(self):
        model, provider, reason = self.engine.resolve_provider("nonexistent-model-v99")
        assert model == DEFAULT_MODEL
        assert reason == "unknown_model_fallback"


# ===========================================================================
# Fallback Chain Tests
# ===========================================================================


class TestFallbackChain:

    def setup_method(self):
        self.engine = RoutingEngine()

    def test_openai_fallback_chain(self):
        chain = self.engine.get_fallback_chain("openai")
        assert "anthropic" in chain
        assert "bedrock" in chain

    def test_anthropic_fallback_chain(self):
        chain = self.engine.get_fallback_chain("anthropic")
        assert "openai" in chain

    def test_unknown_provider_empty_chain(self):
        chain = self.engine.get_fallback_chain("nonexistent")
        assert chain == []


# ===========================================================================
# Route Request Tests (with mocked providers)
# ===========================================================================


class TestRouteRequest:

    @pytest.mark.asyncio
    async def test_successful_primary_routing(self):
        engine = RoutingEngine()
        engine._providers = {"openai": _mock_provider("openai", succeed=True)}

        request = _make_request("gpt-4o")
        response, decision = await engine.route_request(request, request_id="test-1")

        assert response.id == "test-123"
        assert decision.provider == "openai"
        assert decision.success is True
        assert decision.fallback_attempted is False

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self):
        engine = RoutingEngine()
        engine._providers = {
            "openai": _mock_provider("openai", succeed=False),
            "anthropic": _mock_provider("anthropic", succeed=True),
        }

        request = _make_request("gpt-4o")
        response, decision = await engine.route_request(request)

        assert decision.fallback_attempted is True
        assert decision.provider == "anthropic"
        assert decision.success is True

    @pytest.mark.asyncio
    async def test_all_providers_fail_raises(self):
        engine = RoutingEngine()
        engine._providers = {
            "openai": _mock_provider("openai", succeed=False),
            "anthropic": _mock_provider("anthropic", succeed=False),
            "bedrock": _mock_provider("bedrock", succeed=False),
        }

        request = _make_request("gpt-4o")
        with pytest.raises(ProviderError, match="All providers failed"):
            await engine.route_request(request)


# ===========================================================================
# Routing Decision Tests
# ===========================================================================


class TestRoutingDecision:

    def test_decision_to_dict(self):
        d = RoutingDecision(
            request_id="req-1",
            original_model="gpt-4o",
            resolved_model="gpt-4o",
            provider="openai",
            reason="explicit_model",
            latency_ms=42.5,
        )
        data = d.to_dict()
        assert data["request_id"] == "req-1"
        assert data["provider"] == "openai"
        assert data["latency_ms"] == 42.5

    @pytest.mark.asyncio
    async def test_decisions_are_recorded(self):
        engine = RoutingEngine()
        engine._providers = {"openai": _mock_provider("openai", succeed=True)}

        await engine.route_request(_make_request("gpt-4o"), request_id="r1")
        await engine.route_request(_make_request("gpt-4o"), request_id="r2")

        decisions = engine.get_recent_decisions()
        assert len(decisions) == 2
        assert decisions[0]["request_id"] == "r1"
        assert decisions[1]["request_id"] == "r2"


class TestRoutingStats:

    @pytest.mark.asyncio
    async def test_stats_empty(self):
        engine = RoutingEngine()
        stats = engine.get_routing_stats()
        assert stats["total"] == 0

    @pytest.mark.asyncio
    async def test_stats_after_requests(self):
        engine = RoutingEngine()
        engine._providers = {"openai": _mock_provider("openai", succeed=True)}

        await engine.route_request(_make_request("gpt-4o"))
        await engine.route_request(_make_request("gpt-4o"))

        stats = engine.get_routing_stats()
        assert stats["total"] == 2
        assert stats["success_rate"] == 1.0
        assert stats["fallback_rate"] == 0.0


# ===========================================================================
# Property Tests
# ===========================================================================


class TestRoutingConsistencyProperty:
    """Property 1: Request Routing Consistency."""

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(model=st.sampled_from(list(MODEL_PROVIDER_MAP.keys())))
    def test_same_model_always_routes_to_same_provider(self, model):
        """
        Property 1: The same model name MUST always resolve to the
        same provider, regardless of call order.
        """
        engine = RoutingEngine()
        _, provider1, _ = engine.resolve_provider(model)
        _, provider2, _ = engine.resolve_provider(model)
        assert provider1 == provider2


class TestRoutingDecisionLoggingProperty:
    """Property 20: All routing actions produce a logged decision."""

    @pytest.mark.asyncio
    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None, max_examples=10)
    @given(model=st.sampled_from(["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]))
    async def test_every_route_produces_decision(self, model):
        """
        Property 20: Every call to route_request MUST produce exactly
        one routing decision record.
        """
        engine = RoutingEngine()
        engine._providers = {"openai": _mock_provider("openai", succeed=True)}
        before = len(engine._decisions)

        await engine.route_request(_make_request(model))

        assert len(engine._decisions) == before + 1


class TestFallbackChainProperty:
    """Property 17: Fallback chains are attempted in order."""

    @pytest.mark.asyncio
    async def test_fallback_tries_all_providers_in_order(self):
        """
        Property 17: When the primary fails, the engine MUST attempt
        each fallback provider in configured order before giving up.
        """
        engine = RoutingEngine()
        calls = []

        def make_failing_provider(name):
            p = _mock_provider(name, succeed=False)
            original_fn = p.chat_completion

            async def tracked(*a, **kw):
                calls.append(name)
                return await original_fn(*a, **kw)

            p.chat_completion = tracked
            return p

        engine._providers = {
            "openai": make_failing_provider("openai"),
            "anthropic": make_failing_provider("anthropic"),
            "google": make_failing_provider("google"),
            "bedrock": make_failing_provider("bedrock"),
        }

        with pytest.raises(ProviderError):
            await engine.route_request(_make_request("gpt-4o"))

        # Verify: primary called first, then fallbacks in order
        assert calls[0] == "openai"
        expected_fallbacks = FALLBACK_CHAINS["openai"]
        for i, fb in enumerate(expected_fallbacks):
            assert calls[i + 1] == fb
