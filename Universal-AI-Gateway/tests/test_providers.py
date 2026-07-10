"""
Tests for provider adapter system.
Tests schemas, circuit breaker, retry, and provider request/response transformations.
All tests run in-memory — no external API calls are made.
"""

import asyncio
import time
import uuid
from decimal import Decimal

import pytest

from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Choice,
    Message,
    Usage,
    GatewayMetadata,
)
from app.providers.base import (
    ProviderAdapter,
    ProviderError,
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderAuthError,
    MODEL_PROVIDER_MAP,
    get_provider_for_model,
)
from app.providers.circuit_breaker import CircuitBreaker, CircuitState
from app.providers.retry import retry_with_backoff
from app.providers.openai_provider import OpenAIProvider
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.bedrock_provider import BedrockProvider, BEDROCK_MODEL_MAP


# ============================================================================
# Schema Tests
# ============================================================================


class TestChatRequest:
    """Test ChatRequest schema validation."""

    def test_minimal_request(self):
        req = ChatRequest(
            model="gpt-4o",
            messages=[Message(role="user", content="Hello")],
        )
        assert req.model == "gpt-4o"
        assert len(req.messages) == 1

    def test_full_request(self):
        req = ChatRequest(
            model="gpt-4o",
            messages=[
                Message(role="system", content="You are helpful"),
                Message(role="user", content="Hello"),
            ],
            temperature=0.5,
            max_tokens=100,
            top_p=0.9,
            stream=True,
            stop=["END"],
        )
        assert req.temperature == 0.5
        assert req.max_tokens == 100
        assert req.stream is True

    def test_default_temperature(self):
        req = ChatRequest(
            model="gpt-4o",
            messages=[Message(role="user", content="Hi")],
        )
        assert req.temperature == 0.7

    def test_default_stream_false(self):
        req = ChatRequest(
            model="gpt-4o",
            messages=[Message(role="user", content="Hi")],
        )
        assert req.stream is False


class TestChatResponse:
    """Test ChatResponse schema."""

    def test_response_creation(self):
        resp = ChatResponse(
            id="test-123",
            created=int(time.time()),
            model="gpt-4o",
            choices=[
                Choice(
                    message=Message(role="assistant", content="Hello!"),
                    finish_reason="stop",
                )
            ],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        assert resp.id == "test-123"
        assert resp.object == "chat.completion"
        assert resp.choices[0].message.content == "Hello!"
        assert resp.usage.total_tokens == 15


class TestGatewayMetadata:
    """Test GatewayMetadata schema."""

    def test_metadata_creation(self):
        meta = GatewayMetadata(
            provider="openai",
            cache_status="HIT",
            latency_ms=42,
            cost_usd=Decimal("0.001"),
            request_id="req-123",
        )
        assert meta.provider == "openai"
        assert meta.cache_status == "HIT"


# ============================================================================
# Model Provider Mapping Tests
# ============================================================================


class TestModelProviderMapping:
    """Test model-to-provider mapping."""

    def test_openai_models(self):
        assert get_provider_for_model("gpt-4o") == "openai"
        assert get_provider_for_model("gpt-4o-mini") == "openai"
        assert get_provider_for_model("gpt-3.5-turbo") == "openai"

    def test_anthropic_models(self):
        assert get_provider_for_model("claude-3-5-sonnet-20241022") == "anthropic"
        assert get_provider_for_model("claude-3-5-haiku-20241022") == "anthropic"

    def test_bedrock_models(self):
        assert get_provider_for_model("bedrock/claude-3-5-sonnet") == "bedrock"
        assert get_provider_for_model("bedrock/llama-3-70b") == "bedrock"

    def test_unknown_model(self):
        assert get_provider_for_model("unknown-model") is None


# ============================================================================
# Circuit Breaker Tests
# ============================================================================


class TestCircuitBreaker:
    """Test circuit breaker state machine."""

    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        cb = CircuitBreaker(name="test")
        assert await cb.get_state() == CircuitState.CLOSED
        assert await cb.is_available() is True

    @pytest.mark.asyncio
    async def test_stays_closed_under_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=5)
        for _ in range(4):
            await cb.record_failure()
        assert await cb.get_state() == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_at_threshold(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        for _ in range(3):
            await cb.record_failure()
        assert await cb.get_state() == CircuitState.OPEN
        assert await cb.is_available() is False

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        cb = CircuitBreaker(name="test", failure_threshold=5)
        await cb.record_failure()
        await cb.record_failure()
        await cb.record_success()
        await cb.record_failure()
        # Only 1 failure after reset, still closed
        assert await cb.get_state() == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_recovery_timeout_transitions_to_half_open(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.01)
        await cb.record_failure()
        assert await cb.get_state() == CircuitState.OPEN  # Check while still within timeout
        time.sleep(0.02)
        assert await cb.get_state() == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_closes(self):
        cb = CircuitBreaker(
            name="test",
            failure_threshold=1,
            recovery_timeout=0.01,
            success_threshold=2,
        )
        await cb.record_failure()
        time.sleep(0.02)
        assert await cb.get_state() == CircuitState.HALF_OPEN
        await cb.record_success()
        await cb.record_success()
        assert await cb.get_state() == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(name="test", failure_threshold=1, recovery_timeout=0.01)
        await cb.record_failure()
        time.sleep(0.02)
        assert await cb.get_state() == CircuitState.HALF_OPEN
        await cb.record_failure()
        assert await cb.get_state() == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_manual_reset(self):
        cb = CircuitBreaker(name="test", failure_threshold=1)
        await cb.record_failure()
        assert await cb.get_state() == CircuitState.OPEN
        await cb.reset()
        assert await cb.get_state() == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_get_status(self):
        cb = CircuitBreaker(name="test-provider", failure_threshold=3)
        status = await cb.get_status()
        assert status["name"] == "test-provider"
        assert status["state"] == "closed"
        assert status["failure_threshold"] == 3


# ============================================================================
# Retry Tests
# ============================================================================


class TestRetryWithBackoff:
    """Test retry mechanism."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        call_count = 0

        async def good_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await retry_with_backoff(good_func, max_retries=3, base_delay=0.01)
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ProviderError("fail", "test")
            return "recovered"

        result = await retry_with_backoff(
            fail_then_succeed, max_retries=3, base_delay=0.01
        )
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        async def always_fail():
            raise ProviderError("always fails", "test")

        with pytest.raises(ProviderError, match="always fails"):
            await retry_with_backoff(always_fail, max_retries=2, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_non_retryable_exception_not_retried(self):
        call_count = 0

        async def auth_fail():
            nonlocal call_count
            call_count += 1
            raise ProviderAuthError("test")

        with pytest.raises(ProviderAuthError):
            await retry_with_backoff(
                auth_fail,
                max_retries=3,
                base_delay=0.01,
                non_retryable_exceptions=(ProviderAuthError,),
            )
        assert call_count == 1  # Should not retry


# ============================================================================
# Provider Transformation Tests
# ============================================================================


class TestOpenAITransformRequest:
    """Test OpenAI request transformation."""

    def setup_method(self):
        self.provider = OpenAIProvider()

    def test_basic_transform(self):
        request = ChatRequest(
            model="gpt-4o",
            messages=[Message(role="user", content="Hello")],
        )
        payload = self.provider.transform_request(request)
        assert payload["model"] == "gpt-4o"
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"

    def test_with_all_params(self):
        request = ChatRequest(
            model="gpt-4o",
            messages=[Message(role="user", content="Hello")],
            temperature=0.5,
            max_tokens=100,
            top_p=0.9,
            stream=True,
        )
        payload = self.provider.transform_request(request)
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 100
        assert payload["top_p"] == 0.9
        assert payload["stream"] is True

    def test_supported_models(self):
        assert "gpt-4o" in self.provider.supported_models
        assert "gpt-4o-mini" in self.provider.supported_models
        assert "gpt-3.5-turbo" in self.provider.supported_models


class TestOpenAITransformResponse:
    """Test OpenAI response transformation."""

    def setup_method(self):
        self.provider = OpenAIProvider()

    def test_basic_response(self):
        raw = {
            "id": "chatcmpl-123",
            "created": 1700000000,
            "model": "gpt-4o",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hi!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
        resp = self.provider.transform_response(raw, "gpt-4o")
        assert resp.id == "chatcmpl-123"
        assert resp.choices[0].message.content == "Hi!"
        assert resp.usage.total_tokens == 15


class TestAnthropicTransformRequest:
    """Test Anthropic request transformation."""

    def setup_method(self):
        self.provider = AnthropicProvider()

    def test_system_message_extraction(self):
        """Anthropic requires system as top-level param, not in messages."""
        request = ChatRequest(
            model="claude-3-5-sonnet-20241022",
            messages=[
                Message(role="system", content="You are helpful"),
                Message(role="user", content="Hello"),
            ],
        )
        payload = self.provider.transform_request(request)
        assert payload["system"] == "You are helpful"
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"

    def test_default_max_tokens(self):
        """Anthropic requires max_tokens; defaults to 4096."""
        request = ChatRequest(
            model="claude-3-5-sonnet-20241022",
            messages=[Message(role="user", content="Hello")],
        )
        payload = self.provider.transform_request(request)
        assert payload["max_tokens"] == 4096

    def test_stop_sequences_mapping(self):
        """Gateway 'stop' → Anthropic 'stop_sequences'."""
        request = ChatRequest(
            model="claude-3-5-sonnet-20241022",
            messages=[Message(role="user", content="Hello")],
            stop=["END", "STOP"],
        )
        payload = self.provider.transform_request(request)
        assert payload["stop_sequences"] == ["END", "STOP"]


class TestAnthropicTransformResponse:
    """Test Anthropic response transformation."""

    def setup_method(self):
        self.provider = AnthropicProvider()

    def test_content_blocks_to_text(self):
        raw = {
            "id": "msg-123",
            "model": "claude-3-5-sonnet-20241022",
            "content": [
                {"type": "text", "text": "Hello "},
                {"type": "text", "text": "world!"},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        resp = self.provider.transform_response(raw, "claude-3-5-sonnet-20241022")
        assert resp.choices[0].message.content == "Hello world!"
        assert resp.usage.prompt_tokens == 10
        assert resp.usage.completion_tokens == 5
        assert resp.usage.total_tokens == 15

    def test_stop_reason_mapping(self):
        raw = {
            "content": [{"type": "text", "text": "..."}],
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        resp = self.provider.transform_response(raw, "claude-3-5-sonnet-20241022")
        assert resp.choices[0].finish_reason == "length"


class TestBedrockTransformRequest:
    """Test Bedrock Converse API request transformation."""

    def setup_method(self):
        self.provider = BedrockProvider()

    def test_content_blocks_format(self):
        """Bedrock uses content as list of {text: ...} blocks."""
        request = ChatRequest(
            model="bedrock/claude-3-5-sonnet",
            messages=[Message(role="user", content="Hello")],
        )
        payload = self.provider.transform_request(request)
        assert payload["messages"][0]["content"] == [{"text": "Hello"}]

    def test_system_message_extraction(self):
        request = ChatRequest(
            model="bedrock/claude-3-5-sonnet",
            messages=[
                Message(role="system", content="Be concise"),
                Message(role="user", content="Hello"),
            ],
        )
        payload = self.provider.transform_request(request)
        assert payload["system"] == [{"text": "Be concise"}]
        assert len(payload["messages"]) == 1

    def test_inference_config(self):
        request = ChatRequest(
            model="bedrock/claude-3-5-sonnet",
            messages=[Message(role="user", content="Hello")],
            temperature=0.5,
            max_tokens=200,
        )
        payload = self.provider.transform_request(request)
        assert payload["inferenceConfig"]["temperature"] == 0.5
        assert payload["inferenceConfig"]["maxTokens"] == 200

    def test_model_resolution(self):
        model_id = self.provider._resolve_model_id("bedrock/claude-3-5-sonnet")
        assert "anthropic.claude" in model_id

    def test_unknown_model_raises(self):
        with pytest.raises(ProviderError, match="Unknown Bedrock model"):
            self.provider._resolve_model_id("bedrock/nonexistent")


class TestBedrockTransformResponse:
    """Test Bedrock Converse API response transformation."""

    def setup_method(self):
        self.provider = BedrockProvider()

    def test_output_blocks(self):
        raw = {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [{"text": "Hello from Bedrock!"}],
                }
            },
            "stopReason": "end_turn",
            "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        }
        resp = self.provider.transform_response(raw, "bedrock/claude-3-5-sonnet")
        assert resp.choices[0].message.content == "Hello from Bedrock!"
        assert resp.usage.prompt_tokens == 10
        assert resp.usage.total_tokens == 15


# ============================================================================
# Provider Error Tests
# ============================================================================


class TestProviderErrors:
    """Test provider error hierarchy."""

    def test_base_error(self):
        err = ProviderError("test error", "openai", 502)
        assert str(err) == "test error"
        assert err.provider == "openai"
        assert err.status_code == 502

    def test_timeout_error(self):
        err = ProviderTimeoutError("openai", 30.0)
        assert err.status_code == 504
        assert "timed out" in str(err)

    def test_rate_limit_error(self):
        err = ProviderRateLimitError("anthropic", retry_after=60)
        assert err.status_code == 429
        assert err.retry_after == 60

    def test_auth_error(self):
        err = ProviderAuthError("bedrock")
        assert err.status_code == 401
        assert "authentication" in str(err).lower()


# ============================================================================
# Provider Properties Tests
# ============================================================================


class TestProviderProperties:
    """Test provider name and model support."""

    def test_openai_provider_name(self):
        assert OpenAIProvider().provider_name == "openai"

    def test_anthropic_provider_name(self):
        assert AnthropicProvider().provider_name == "anthropic"

    def test_bedrock_provider_name(self):
        assert BedrockProvider().provider_name == "bedrock"

    def test_openai_supports_gpt4o(self):
        assert OpenAIProvider().supports_model("gpt-4o")

    def test_anthropic_supports_claude(self):
        assert AnthropicProvider().supports_model("claude-3-5-sonnet-20241022")

    def test_bedrock_supports_mapped_models(self):
        provider = BedrockProvider()
        for model in BEDROCK_MODEL_MAP:
            assert provider.supports_model(model)

    def test_cross_provider_model_rejection(self):
        assert not OpenAIProvider().supports_model("claude-3-5-sonnet-20241022")
        assert not AnthropicProvider().supports_model("gpt-4o")
        assert not BedrockProvider().supports_model("gpt-4o")
