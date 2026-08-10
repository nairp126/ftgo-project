"""
Google Gemini provider adapter.
Supports Requirement 21 (Google Gemini support).
"""

import time
import uuid
import json
from typing import AsyncIterator, List, Dict, Any

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

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GoogleProvider(ProviderAdapter):
    """
    Adapter for Google's Gemini API.
    Transforms between OpenAI-compatible gateway format and Gemini's format.
    """

    def __init__(self):
        settings = get_settings()
        self._api_key = settings.providers.google_api_key or ""
        self._timeout = settings.providers.timeout
        self._circuit = CircuitBreaker(name="google")
        self._client = httpx.AsyncClient(
            base_url=GEMINI_BASE_URL,
            timeout=httpx.Timeout(self._timeout),
        )

    @property
    def provider_name(self) -> str:
        return "google"

    @property
    def supported_models(self) -> List[str]:
        return [
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.0-pro",
        ]

    def transform_request(self, request: ChatRequest) -> dict:
        """
        Transform OpenAI-format request to Gemini GenerateContent format.
        
        Gemini Roles: 'user', 'model'. Optional 'system_instruction' for system prompt.
        """
        contents = []
        system_instruction = None

        for msg in request.messages:
            if msg.role == "system":
                system_instruction = {"parts": [{"text": msg.content}]}
            else:
                role = "user" if msg.role == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg.content}]
                })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature if request.temperature is not None else 0.7,
                "topP": request.top_p if request.top_p is not None else 0.95,
                "maxOutputTokens": request.max_tokens or 2048,
            }
        }

        if system_instruction:
            payload["system_instruction"] = system_instruction

        if request.stop:
            payload["generationConfig"]["stopSequences"] = request.stop

        return payload

    def transform_response(self, response: dict, model: str) -> ChatResponse:
        """Transform Gemini response to OpenAI-compatible format."""
        candidates = response.get("candidates", [])
        if not candidates:
            raise ProviderError(
                message="Gemini returned no candidates (blocked search or safety check failure)",
                provider=self.provider_name
            )

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        text = "".join([p.get("text", "") for p in parts])

        finish_reason_map = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "RECITATION": "content_filter",
            "OTHER": "stop",
        }
        finish_reason = finish_reason_map.get(candidate.get("finishReason", "STOP"), "stop")

        usage_data = response.get("usageMetadata", {})

        return ChatResponse(
            id=f"gemini-{uuid.uuid4().hex[:12]}",
            object="chat.completion",
            created=int(time.time()),
            model=model,
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content=text),
                    finish_reason=finish_reason,
                )
            ],
            usage=Usage(
                prompt_tokens=usage_data.get("promptTokenCount", 0),
                completion_tokens=usage_data.get("candidatesTokenCount", 0),
                total_tokens=usage_data.get("totalTokenCount", 0),
            ),
        )

    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        """Execute chat completion via Gemini API."""
        if not await self._circuit.is_available():
            raise ProviderError(
                message="Google Gemini circuit breaker is open",
                provider=self.provider_name,
                status_code=503,
            )

        if get_settings().mock_llm:
            return ChatResponse(
                id=f"mock-gemini-{uuid.uuid4().hex[:12]}",
                object="chat.completion",
                created=int(time.time()),
                model=request.model,
                choices=[
                    Choice(
                        index=0,
                        message=Message(role="assistant", content=f"Mock response from Gemini for model {request.model}"),
                        finish_reason="stop"
                    )
                ],
                usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
            )

        async def _do_request():
            payload = self.transform_request(request)
            url = f"/models/{request.model}:generateContent?key={self._api_key}"
            try:
                resp = await self._client.post(url, json=payload)
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
                    message=f"Gemini request failed: {e}",
                    provider=self.provider_name,
                    original_error=e,
                )

        return await retry_with_backoff(
            _do_request,
            max_retries=3,
            non_retryable_exceptions=(ProviderAuthError,),
        )

    async def stream_completion(self, request: ChatRequest) -> AsyncIterator[str]:
        """Stream chat completion via Gemini API (SSE)."""
        if not await self._circuit.is_available():
            raise ProviderError(
                message="Google Gemini circuit breaker is open",
                provider=self.provider_name,
                status_code=503,
            )

        payload = self.transform_request(request)
        url = f"/models/{request.model}:streamGenerateContent?alt=sse&key={self._api_key}"

        try:
            async with self._client.stream("POST", url, json=payload) as resp:
                self._handle_error_response(resp)
                await self._circuit.record_success()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        # Convert Gemini's SSE format to OpenAI's if needed, 
                        # but gateway handles raw SSE if consistent.
                        # Gemini's 'alt=sse' already provides data: {json}
                        yield line + "\n\n"
        except httpx.TimeoutException:
            await self._circuit.record_failure()
            raise ProviderTimeoutError(self.provider_name, self._timeout)
        except ProviderError:
            await self._circuit.record_failure()
            raise

    async def health_check(self) -> bool:
        """Check Gemini API reachability."""
        try:
            # Minimal request to check connectivity
            url = f"/models?key={self._api_key}"
            resp = await self._client.get(url)
            return resp.status_code == 200
        except Exception:
            return False

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """Map Gemini HTTP errors to gateway ProviderErrors."""
        if resp.status_code == 200:
            return
        
        error_data = {}
        try:
            error_data = resp.json().get("error", {})
        except:
            pass

        message = error_data.get("message", f"Gemini returned {resp.status_code}")
        
        if resp.status_code == 401 or resp.status_code == 403:
            raise ProviderAuthError(self.provider_name)
        if resp.status_code == 429:
            raise ProviderRateLimitError(self.provider_name)
        
        raise ProviderError(
            message=message,
            provider=self.provider_name,
            status_code=resp.status_code,
        )
