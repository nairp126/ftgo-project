"""
Tests for token counting and cost calculation.
Covers tiktoken counting, cost math, and property tests.
"""

import time
from decimal import Decimal

import pytest
from hypothesis import given, settings as h_settings, HealthCheck, strategies as st

from app.schemas.chat import (
    ChatRequest, ChatResponse, Choice, Message, Usage,
)
from app.services.token_counter import (
    count_message_tokens,
    count_text_tokens,
    count_request_tokens,
    extract_response_tokens,
    TOKENS_PER_MESSAGE,
    TOKENS_REPLY_OVERHEAD,
)
from app.services.cost_calculator import (
    calculate_cost,
    calculate_request_cost,
    get_model_pricing,
    get_all_pricing,
    PROVIDER_PRICING,
    ONE_MILLION,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(model="gpt-4o", content="Hello world") -> ChatRequest:
    return ChatRequest(
        model=model,
        messages=[Message(role="user", content=content)],
    )


def _make_response(prompt_tokens=10, completion_tokens=5) -> ChatResponse:
    return ChatResponse(
        id="test",
        created=int(time.time()),
        model="gpt-4o",
        choices=[Choice(message=Message(role="assistant", content="Hi!"), finish_reason="stop")],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


# ===========================================================================
# Token Counting Unit Tests
# ===========================================================================


class TestCountMessageTokens:

    def test_single_message_nonzero(self):
        msgs = [Message(role="user", content="Hello")]
        tokens = count_message_tokens(msgs, "gpt-4o")
        assert tokens > 0

    def test_longer_message_more_tokens(self):
        short = count_message_tokens([Message(role="user", content="Hi")], "gpt-4o")
        long_ = count_message_tokens([Message(role="user", content="Hello world, this is a longer message")], "gpt-4o")
        assert long_ > short

    def test_multiple_messages_more_than_single(self):
        one = count_message_tokens([Message(role="user", content="Hello")], "gpt-4o")
        two = count_message_tokens([
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi"),
        ], "gpt-4o")
        assert two > one

    def test_includes_per_message_overhead(self):
        """Each message adds TOKENS_PER_MESSAGE overhead."""
        msgs = [Message(role="user", content="a")]
        tokens = count_message_tokens(msgs, "gpt-4o")
        # At minimum: overhead per msg + role + content + reply overhead
        assert tokens >= TOKENS_PER_MESSAGE + TOKENS_REPLY_OVERHEAD

    def test_unknown_model_uses_fallback_encoding(self):
        """Unknown models should still produce a valid count."""
        msgs = [Message(role="user", content="Hello")]
        tokens = count_message_tokens(msgs, "unknown-model-v99")
        assert tokens > 0


class TestCountTextTokens:

    def test_empty_string_zero(self):
        assert count_text_tokens("", "gpt-4o") == 0

    def test_hello_nonzero(self):
        assert count_text_tokens("Hello", "gpt-4o") > 0

    def test_longer_text_more_tokens(self):
        short = count_text_tokens("Hi", "gpt-4o")
        long_ = count_text_tokens("Hello world, this is a much longer text string", "gpt-4o")
        assert long_ > short


class TestCountRequestTokens:

    def test_counts_from_request(self):
        req = _make_request(content="Hello world")
        tokens = count_request_tokens(req)
        assert tokens > 0


class TestExtractResponseTokens:

    def test_uses_provider_values(self):
        resp = _make_response(prompt_tokens=100, completion_tokens=50)
        result = extract_response_tokens(resp)
        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50
        assert result["total_tokens"] == 150

    def test_fallback_local_count_when_zero_completion(self):
        resp = _make_response(prompt_tokens=10, completion_tokens=0)
        result = extract_response_tokens(resp)
        # Should count "Hi!" locally
        assert result["completion_tokens"] > 0


# ===========================================================================
# Cost Calculation Unit Tests
# ===========================================================================


class TestCalculateCost:

    def test_zero_tokens_zero_cost(self):
        cost = calculate_cost("gpt-4o", 0, 0)
        assert cost == Decimal("0")

    def test_known_model_nonzero_cost(self):
        cost = calculate_cost("gpt-4o", 1000, 500)
        assert cost > Decimal("0")

    def test_unknown_model_zero_cost(self):
        cost = calculate_cost("nonexistent-model", 1000, 500)
        assert cost == Decimal("0")

    def test_gpt4o_cost_math(self):
        """Verify: 1000 input tokens at $2.50/1M = $0.0025, 500 output at $10/1M = $0.005"""
        cost = calculate_cost("gpt-4o", 1000, 500)
        expected = Decimal("0.0025") + Decimal("0.005")
        assert cost == expected.quantize(Decimal("0.00000001"))

    def test_cost_scales_linearly(self):
        cost_1k = calculate_cost("gpt-4o", 1000, 0)
        cost_2k = calculate_cost("gpt-4o", 2000, 0)
        assert cost_2k == cost_1k * 2


class TestCalculateRequestCost:

    def test_returns_full_breakdown(self):
        result = calculate_request_cost("gpt-4o", {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        })
        assert result["model"] == "gpt-4o"
        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50
        assert result["total_tokens"] == 150
        assert result["cost_usd"] > Decimal("0")


class TestPricingLookup:

    def test_get_known_model_pricing(self):
        pricing = get_model_pricing("gpt-4o")
        assert pricing is not None
        assert "input" in pricing
        assert "output" in pricing

    def test_get_unknown_model_pricing(self):
        assert get_model_pricing("nonexistent") is None

    def test_get_all_pricing(self):
        all_prices = get_all_pricing()
        assert len(all_prices) > 0
        assert "gpt-4o" in all_prices


# ===========================================================================
# Property Tests
# ===========================================================================


class TestTokenCountingProperty:
    """Property 12: Token Counting Accuracy."""

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        content=st.text(min_size=1, max_size=500),
        model=st.sampled_from(["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]),
    )
    def test_token_count_always_positive(self, content, model):
        """Property 12: Non-empty content MUST always produce at least 1 token."""
        tokens = count_text_tokens(content, model)
        assert tokens >= 1

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        content=st.text(min_size=1, max_size=200),
        model=st.sampled_from(["gpt-4o", "gpt-4o-mini"]),
    )
    def test_message_tokens_greater_than_text_tokens(self, content, model):
        """
        Property 12: Message tokens include per-message overhead,
        so MUST always be greater than raw text tokens.
        """
        text_tokens = count_text_tokens(content, model)
        msg_tokens = count_message_tokens(
            [Message(role="user", content=content)], model
        )
        assert msg_tokens > text_tokens


class TestCostCalculationProperty:
    """Property 13: Cost Calculation Consistency."""

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        prompt=st.integers(min_value=0, max_value=100000),
        completion=st.integers(min_value=0, max_value=100000),
        model=st.sampled_from(list(PROVIDER_PRICING.keys())),
    )
    def test_cost_is_non_negative(self, prompt, completion, model):
        """Property 13: Cost MUST always be >= 0."""
        cost = calculate_cost(model, prompt, completion)
        assert cost >= Decimal("0")

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        tokens=st.integers(min_value=1, max_value=50000),
        model=st.sampled_from(list(PROVIDER_PRICING.keys())),
    )
    def test_more_tokens_higher_cost(self, tokens, model):
        """Property 13: More tokens MUST always result in equal or higher cost."""
        cost_small = calculate_cost(model, tokens, 0)
        cost_large = calculate_cost(model, tokens * 2, 0)
        assert cost_large >= cost_small

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        prompt=st.integers(min_value=0, max_value=10000),
        completion=st.integers(min_value=0, max_value=10000),
        model=st.sampled_from(list(PROVIDER_PRICING.keys())),
    )
    def test_cost_deterministic(self, prompt, completion, model):
        """Property 13: Same inputs MUST always produce the same cost."""
        c1 = calculate_cost(model, prompt, completion)
        c2 = calculate_cost(model, prompt, completion)
        assert c1 == c2


class TestCostDataPersistenceProperty:
    """Property 21: Cost Data Persistence (Requirement 9.6)."""

    REQUIRED_FIELDS = {"model", "prompt_tokens", "completion_tokens", "total_tokens", "cost_usd"}

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        prompt=st.integers(min_value=0, max_value=50000),
        completion=st.integers(min_value=0, max_value=50000),
        model=st.sampled_from(list(PROVIDER_PRICING.keys())),
    )
    def test_cost_data_contains_all_persistence_fields(self, prompt, completion, model):
        """
        Property 21: The cost data dict returned by calculate_request_cost
        MUST always contain every field required for analytics storage.
        """
        usage = {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}
        result = calculate_request_cost(model, usage)

        # Every required field MUST be present
        assert self.REQUIRED_FIELDS.issubset(result.keys()), (
            f"Missing fields: {self.REQUIRED_FIELDS - result.keys()}"
        )

    @h_settings(suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @given(
        prompt=st.integers(min_value=0, max_value=50000),
        completion=st.integers(min_value=0, max_value=50000),
        model=st.sampled_from(list(PROVIDER_PRICING.keys())),
    )
    def test_cost_data_types_valid_for_storage(self, prompt, completion, model):
        """
        Property 21: All fields must have correct types for database storage.
        """
        usage = {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}
        result = calculate_request_cost(model, usage)

        assert isinstance(result["model"], str)
        assert isinstance(result["prompt_tokens"], int)
        assert isinstance(result["completion_tokens"], int)
        assert isinstance(result["total_tokens"], int)
        assert isinstance(result["cost_usd"], Decimal)
        assert result["cost_usd"] >= Decimal("0")
        assert result["total_tokens"] == prompt + completion
