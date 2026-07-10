"""
OpenAI provider adapter.
Supports Requirements 3.1 (GPT-4o, GPT-4o-mini, GPT-3.5-turbo).
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

OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIProvider(ProviderAdapter):
    """
    Adapter for OpenAI's Chat Completions API.
    Minimal transformation needed since the gateway follows OpenAI's schema.
    """

    def __init__(self):
        settings = get_settings()
        self._api_key = settings.providers.openai_api_key or ""
        self._timeout = settings.providers.timeout
        self._circuit = CircuitBreaker(name="openai")
        self._client = httpx.AsyncClient(
            base_url=OPENAI_BASE_URL,
            timeout=httpx.Timeout(self._timeout),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def supported_models(self) -> List[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]

    def transform_request(self, request: ChatRequest) -> dict:
        """OpenAI request format is the same as gateway format."""
        payload = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stream:
            payload["stream"] = True
        if request.stop:
            payload["stop"] = request.stop
        if request.presence_penalty:
            payload["presence_penalty"] = request.presence_penalty
        if request.frequency_penalty:
            payload["frequency_penalty"] = request.frequency_penalty
        return payload

    def transform_response(self, response: dict, model: str) -> ChatResponse:
        """Transform OpenAI response to gateway format (minimal mapping)."""
        choices = []
        for c in response.get("choices", []):
            msg = c.get("message", {})
            choices.append(
                Choice(
                    index=c.get("index", 0),
                    message=Message(
                        role=msg.get("role", "assistant"),
                        content=msg.get("content", ""),
                    ),
                    finish_reason=c.get("finish_reason", "stop"),
                )
            )

        usage_data = response.get("usage", {})
        return ChatResponse(
            id=response.get("id", f"chatcmpl-{uuid.uuid4().hex[:12]}"),
            object="chat.completion",
            created=response.get("created", int(time.time())),
            model=response.get("model", model),
            choices=choices,
            usage=Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
        )

    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        """Execute chat completion via OpenAI API with retry and circuit breaker."""
        if not await self._circuit.is_available():
            raise ProviderError(
                message="OpenAI circuit breaker is open",
                provider=self.provider_name,
                status_code=503,
            )

        if get_settings().mock_llm:
            return ChatResponse(
                id=f"mock-completion-{uuid.uuid4().hex[:12]}",
                object="chat.completion",
                created=int(time.time()),
                model=request.model,
                choices=[
                    Choice(
                        index=0,
                        message=Message(role="assistant", content=f"Mock response from {self.provider_name} for model {request.model}"),
                        finish_reason="stop"
                    )
                ],
                usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
            )

        async def _do_request():
            payload = self.transform_request(request)
            try:
                resp = await self._client.post("/chat/completions", json=payload)
                self._handle_error_response(resp)
                await self._circuit.record_success()
                return self.transform_response(resp.json(), request.model)
            except (httpx.TimeoutException,):
                await self._circuit.record_failure()
                raise ProviderTimeoutError(self.provider_name, self._timeout)
            except ProviderError:
                await self._circuit.record_failure()
                raise
            except Exception as e:
                await self._circuit.record_failure()
                raise ProviderError(
                    message=f"OpenAI request failed: {e}",
                    provider=self.provider_name,
                    original_error=e,
                )

        return await retry_with_backoff(
            _do_request,
            max_retries=3,
            non_retryable_exceptions=(ProviderAuthError,),
        )

    async def stream_completion(self, request: ChatRequest) -> AsyncIterator[str]:
        """Stream chat completion via OpenAI API."""
        if not await self._circuit.is_available():
            raise ProviderError(
                message="OpenAI circuit breaker is open",
                provider=self.provider_name,
                status_code=503,
            )

        request_copy = request.model_copy(update={"stream": True})
        payload = self.transform_request(request_copy)

        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=payload
            ) as resp:
                self._handle_error_response(resp)
                await self._circuit.record_success()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line + "\n\n"
                    elif line.strip() == "data: [DONE]":
                        yield "data: [DONE]\n\n"
                        break
        except httpx.TimeoutException:
            await self._circuit.record_failure()
            raise ProviderTimeoutError(self.provider_name, self._timeout)
        except ProviderError:
            await self._circuit.record_failure()
            raise

    async def health_check(self) -> bool:
        """Check OpenAI API reachability."""
        try:
            resp = await self._client.get("/models")
            return resp.status_code == 200
        except Exception:
            return False

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """Map OpenAI HTTP errors to gateway ProviderErrors."""
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
            message=f"OpenAI returned {resp.status_code}: {resp.text[:200]}",
            provider=self.provider_name,
            status_code=resp.status_code,
        )
