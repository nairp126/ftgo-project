"""
Anthropic provider adapter.
Supports Requirement 3.2 (Claude Sonnet 4.5, Claude Haiku 4.5).
"""

import time
import uuid
from typing import AsyncIterator, List

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.base import (
    ProviderAdapter,
    ProviderError,
    ProviderTimeoutError,
    ProviderRateLimitError,
    ProviderAuthError,
)
from app.providers.circuit_breaker import CircuitBreaker
from app.providers.retry import retry_with_backoff
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    Choice,
    Message,
    Usage,
)

logger = get_logger(__name__)

ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_API_VERSION = "2024-10-22"


class AnthropicProvider(ProviderAdapter):
    """
    Adapter for Anthropic's Messages API.
    Transforms between OpenAI-compatible gateway format and Anthropic's format.
    """

    def __init__(self):
        settings = get_settings()
        self._api_key = settings.providers.anthropic_api_key or ""
        self._timeout = settings.providers.timeout
        self._circuit = CircuitBreaker(name="anthropic")
        self._client = httpx.AsyncClient(
            base_url=ANTHROPIC_BASE_URL,
            timeout=httpx.Timeout(self._timeout),
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "Content-Type": "application/json",
            },
        )

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def supported_models(self) -> List[str]:
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-sonnet-4-5-20250514",
            "claude-haiku-4-5-20250514",
        ]

    def transform_request(self, request: ChatRequest) -> dict:
        """
        Transform OpenAI-format request to Anthropic Messages API format.

        Key differences:
        - Anthropic uses 'system' as a top-level parameter, not a message
        - Messages must alternate user/assistant (no system role in messages)
        - 'max_tokens' is required in Anthropic (default to 4096)
        """
        system_messages = []
        user_messages = []
        for msg in request.messages:
            if msg.role == "system":
                system_messages.append(msg.content)
            else:
                user_messages.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": request.model,
            "messages": user_messages,
            "max_tokens": request.max_tokens or 4096,
        }

        if system_messages:
            payload["system"] = "\n\n".join(system_messages)

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop:
            payload["stop_sequences"] = request.stop
        if request.stream:
            payload["stream"] = True

        return payload

    def transform_response(self, response: dict, model: str) -> ChatResponse:
        """Transform Anthropic Messages response to OpenAI-compatible format."""
        # Extract text from content blocks
        content_blocks = response.get("content", [])
        text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                text += block.get("text", "")

        # Map Anthropic stop_reason to OpenAI finish_reason
        stop_reason = response.get("stop_reason", "end_turn")
        finish_reason_map = {
            "end_turn": "stop",
            "max_tokens": "length",
            "stop_sequence": "stop",
        }
        finish_reason = finish_reason_map.get(stop_reason, "stop")

        # Token usage
        usage_data = response.get("usage", {})

        return ChatResponse(
            id=response.get("id", f"msg-{uuid.uuid4().hex[:12]}"),
            object="chat.completion",
            created=int(time.time()),
            model=response.get("model", model),
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content=text),
                    finish_reason=finish_reason,
                )
            ],
            usage=Usage(
                prompt_tokens=usage_data.get("input_tokens", 0),
                completion_tokens=usage_data.get("output_tokens", 0),
                total_tokens=(
                    usage_data.get("input_tokens", 0)
                    + usage_data.get("output_tokens", 0)
                ),
            ),
        )

    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        """Execute chat completion via Anthropic Messages API."""
        if not await self._circuit.is_available():
            raise ProviderError(
                message="Anthropic circuit breaker is open",
                provider=self.provider_name,
                status_code=503,
            )

        if get_settings().mock_llm:
            return ChatResponse(
                id=f"mock-msg-{uuid.uuid4().hex[:12]}",
                object="chat.completion",
                created=int(time.time()),
                model=request.model,
                choices=[
                    Choice(
                        index=0,
                        message=Message(role="assistant", content=f"Mock response from {self.provider_name} (Claude) for model {request.model}"),
                        finish_reason="stop"
                    )
                ],
                usage=Usage(prompt_tokens=15, completion_tokens=25, total_tokens=40)
            )

        async def _do_request():
            payload = self.transform_request(request)
            try:
                resp = await self._client.post("/messages", json=payload)
                self._handle_error_response(resp)
                await self._circuit.record_success()
                return self.transform_response(resp.json(), request.model)
            except httpx.TimeoutException:
                await self._circuit.record_failure()
                raise ProviderTimeoutError(self.provider_name, self._timeout)
            except ProviderError:
                await self._circuit.record_failure()
                raise
            except Exception as e:
                await self._circuit.record_failure()
                raise ProviderError(
                    message=f"Anthropic request failed: {e}",
                    provider=self.provider_name,
                    original_error=e,
                )

        return await retry_with_backoff(
            _do_request,
            max_retries=3,
            non_retryable_exceptions=(ProviderAuthError,),
        )

    async def stream_completion(self, request: ChatRequest) -> AsyncIterator[str]:
        """Stream chat completion via Anthropic Messages API (SSE)."""
        if not await self._circuit.is_available():
            raise ProviderError(
                message="Anthropic circuit breaker is open",
                provider=self.provider_name,
                status_code=503,
            )

        request_copy = request.model_copy(update={"stream": True})
        payload = self.transform_request(request_copy)

        try:
            async with self._client.stream(
                "POST", "/messages", json=payload
            ) as resp:
                self._handle_error_response(resp)
                await self._circuit.record_success()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line + "\n\n"
        except httpx.TimeoutException:
            await self._circuit.record_failure()
            raise ProviderTimeoutError(self.provider_name, self._timeout)
        except ProviderError:
            await self._circuit.record_failure()
            raise

    async def health_check(self) -> bool:
        """Check Anthropic API reachability."""
        try:
            # Anthropic doesn't have a models endpoint; use a minimal request
            resp = await self._client.post(
                "/messages",
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
            )
            return resp.status_code in (200, 400)  # 400 = API works, just bad request
        except Exception:
            return False

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """Map Anthropic HTTP errors to gateway ProviderErrors."""
        if resp.status_code == 200:
            return
        if resp.status_code == 401:
            raise ProviderAuthError(self.provider_name)
        if resp.status_code == 429:
            retry_after = resp.headers.get("retry-after")
            raise ProviderRateLimitError(
                self.provider_name,
                retry_after=int(retry_after) if retry_after else None,
            )
        raise ProviderError(
            message=f"Anthropic returned {resp.status_code}: {resp.text[:200]}",
            provider=self.provider_name,
            status_code=resp.status_code,
        )
