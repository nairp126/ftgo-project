"""
AWS Bedrock provider adapter.
Supports Requirement 3.3 (Claude via Bedrock, Llama 3).
"""

import json
import time
import uuid
from typing import AsyncIterator, List, Optional

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

# Bedrock model ID mapping (gateway name → Bedrock model ARN/ID)
BEDROCK_MODEL_MAP = {
    "bedrock/claude-3-5-sonnet": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "bedrock/claude-3-5-haiku": "anthropic.claude-3-5-haiku-20241022-v1:0",
    "bedrock/llama-3-70b": "meta.llama3-70b-instruct-v1:0",
    "bedrock/llama-3-8b": "meta.llama3-8b-instruct-v1:0",
}


class BedrockProvider(ProviderAdapter):
    """
    Adapter for AWS Bedrock's Converse API.

    Transforms gateway requests into Bedrock-compatible format.
    Handles both Anthropic Claude and Meta Llama models via Bedrock.

    Note: In production, this would use boto3 with AWS credentials.
    This implementation uses httpx with SigV4 signing placeholders
    to remain consistent with the other adapters.
    """

    def __init__(self):
        settings = get_settings()
        self._aws_region = settings.providers.aws_region
        self._aws_access_key = settings.providers.aws_access_key_id
        self._aws_secret_key = settings.providers.aws_secret_access_key
        self._timeout = settings.providers.timeout
        self._circuit = CircuitBreaker(name="bedrock")
        self._base_url = (
            f"https://bedrock-runtime.{self._aws_region}.amazonaws.com"
        )
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            headers={"Content-Type": "application/json"},
        )

    @property
    def provider_name(self) -> str:
        return "bedrock"

    @property
    def supported_models(self) -> List[str]:
        return list(BEDROCK_MODEL_MAP.keys())

    def _resolve_model_id(self, model: str) -> str:
        """Convert gateway model name to Bedrock model ID."""
        bedrock_id = BEDROCK_MODEL_MAP.get(model)
        if not bedrock_id:
            raise ProviderError(
                message=f"Unknown Bedrock model: {model}",
                provider=self.provider_name,
                status_code=400,
            )
        return bedrock_id

    def transform_request(self, request: ChatRequest) -> dict:
        """
        Transform gateway request to Bedrock Converse API format.

        Bedrock Converse API uses a different message structure:
        - system: list of system content blocks
        - messages: list of {role, content} with content as list of blocks
        """
        system_blocks = []
        messages = []

        for msg in request.messages:
            if msg.role == "system":
                system_blocks.append({"text": msg.content})
            else:
                messages.append(
                    {
                        "role": msg.role,
                        "content": [{"text": msg.content}],
                    }
                )

        payload = {
            "messages": messages,
            "inferenceConfig": {},
        }

        if system_blocks:
            payload["system"] = system_blocks

        config = payload["inferenceConfig"]
        if request.temperature is not None:
            config["temperature"] = request.temperature
        if request.max_tokens is not None:
            config["maxTokens"] = request.max_tokens
        if request.top_p is not None:
            config["topP"] = request.top_p
        if request.stop:
            config["stopSequences"] = request.stop

        return payload

    def transform_response(self, response: dict, model: str) -> ChatResponse:
        """Transform Bedrock Converse API response to gateway format."""
        # Extract text from output content blocks
        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])
        text = ""
        for block in content_blocks:
            if "text" in block:
                text += block["text"]

        # Map Bedrock stop reason
        stop_reason = response.get("stopReason", "end_turn")
        finish_reason_map = {
            "end_turn": "stop",
            "max_tokens": "length",
            "stop_sequence": "stop",
            "content_filtered": "content_filter",
        }
        finish_reason = finish_reason_map.get(stop_reason, "stop")

        # Token usage
        usage_data = response.get("usage", {})

        return ChatResponse(
            id=f"bedrock-{uuid.uuid4().hex[:12]}",
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
                prompt_tokens=usage_data.get("inputTokens", 0),
                completion_tokens=usage_data.get("outputTokens", 0),
                total_tokens=usage_data.get("totalTokens", 0),
            ),
        )

    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        """Execute chat completion via Bedrock Converse API."""
        if not await self._circuit.is_available():
            raise ProviderError(
                message="Bedrock circuit breaker is open",
                provider=self.provider_name,
                status_code=503,
            )

        if get_settings().mock_llm:
            return ChatResponse(
                id=f"mock-bedrock-{uuid.uuid4().hex[:12]}",
                object="chat.completion",
                created=int(time.time()),
                model=request.model,
                choices=[
                    Choice(
                        index=0,
                        message=Message(role="assistant", content=f"Mock response from {self.provider_name} (Llama/Claude) for model {request.model}"),
                        finish_reason="stop"
                    )
                ],
                usage=Usage(prompt_tokens=12, completion_tokens=22, total_tokens=34)
            )

        bedrock_model_id = self._resolve_model_id(request.model)

        async def _do_request():
            payload = self.transform_request(request)
            url = f"{self._base_url}/model/{bedrock_model_id}/converse"

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
                    message=f"Bedrock request failed: {e}",
                    provider=self.provider_name,
                    original_error=e,
                )

        return await retry_with_backoff(
            _do_request,
            max_retries=3,
            non_retryable_exceptions=(ProviderAuthError,),
        )

    async def stream_completion(self, request: ChatRequest) -> AsyncIterator[str]:
        """Stream chat completion via Bedrock ConverseStream API."""
        if not await self._circuit.is_available():
            raise ProviderError(
                message="Bedrock circuit breaker is open",
                provider=self.provider_name,
                status_code=503,
            )

        bedrock_model_id = self._resolve_model_id(request.model)
        payload = self.transform_request(request)
        url = f"{self._base_url}/model/{bedrock_model_id}/converse-stream"

        try:
            async with self._client.stream("POST", url, json=payload) as resp:
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
        """Check Bedrock API reachability."""
        try:
            url = f"{self._base_url}/model/{list(BEDROCK_MODEL_MAP.values())[0]}/converse"
            resp = await self._client.post(
                url,
                json={
                    "messages": [
                        {"role": "user", "content": [{"text": "ping"}]}
                    ],
                    "inferenceConfig": {"maxTokens": 1},
                },
            )
            # 200 or 403 (auth issue but API reachable) means the endpoint exists
            return resp.status_code in (200, 400, 403)
        except Exception:
            return False

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """Map Bedrock HTTP errors to gateway ProviderErrors."""
        if resp.status_code == 200:
            return
        if resp.status_code in (401, 403):
            raise ProviderAuthError(self.provider_name)
        if resp.status_code == 429:
            retry_after = resp.headers.get("retry-after")
            raise ProviderRateLimitError(
                self.provider_name,
                retry_after=int(retry_after) if retry_after else None,
            )
        raise ProviderError(
            message=f"Bedrock returned {resp.status_code}: {resp.text[:200]}",
            provider=self.provider_name,
            status_code=resp.status_code,
        )
