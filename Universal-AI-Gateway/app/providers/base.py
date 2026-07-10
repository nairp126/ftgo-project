"""
Base provider adapter interface.
Supports Requirements 3.4 (request transformation), 3.5 (response normalization),
3.7 (circuit breaker support), 3.8 (standardized error handling).
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional

from app.schemas.chat import ChatRequest, ChatResponse
from app.core.logging import get_logger

logger = get_logger(__name__)


# Model-to-provider mapping
MODEL_PROVIDER_MAP: Dict[str, str] = {
    # OpenAI models
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-4-turbo": "openai",
    "gpt-3.5-turbo": "openai",
    # Anthropic models
    "claude-3-5-sonnet-20241022": "anthropic",
    "claude-3-5-haiku-20241022": "anthropic",
    "claude-sonnet-4-5-20250514": "anthropic",
    "claude-haiku-4-5-20250514": "anthropic",
    # Bedrock models (prefixed with bedrock/)
    "bedrock/claude-3-5-sonnet": "bedrock",
    "bedrock/claude-3-5-haiku": "bedrock",
    "bedrock/llama-3-70b": "bedrock",
    "bedrock/llama-3-8b": "bedrock",
    # Google Gemini models
    "gemini-1.5-pro": "google",
    "gemini-1.5-flash": "google",
    "gemini-1.0-pro": "google",
}


def get_provider_for_model(model: str) -> Optional[str]:
    """Look up which provider handles a given model name."""
    return MODEL_PROVIDER_MAP.get(model)


class ProviderAdapter(ABC):
    """
    Abstract base class for LLM provider adapters.

    Each concrete adapter transforms gateway requests into provider-specific
    format and normalizes responses back to the unified gateway format.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier for this provider (e.g. 'openai', 'anthropic')."""
        ...

    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """List of model identifiers this provider supports."""
        ...

    @abstractmethod
    async def chat_completion(self, request: ChatRequest) -> ChatResponse:
        """
        Execute a non-streaming chat completion request.

        Args:
            request: The unified gateway ChatRequest.

        Returns:
            A unified ChatResponse.

        Raises:
            ProviderError: If the provider returns an error.
        """
        ...

    @abstractmethod
    async def stream_completion(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        Execute a streaming chat completion request.

        Yields SSE-formatted strings: 'data: {json}\n\n'

        Args:
            request: The unified gateway ChatRequest.

        Yields:
            SSE data strings.
        """
        ...

    @abstractmethod
    def transform_request(self, request: ChatRequest) -> dict:
        """
        Transform a gateway ChatRequest into provider-specific format.

        Args:
            request: The unified gateway ChatRequest.

        Returns:
            A dict suitable for the provider's HTTP API.
        """
        ...

    @abstractmethod
    def transform_response(self, response: dict, model: str) -> ChatResponse:
        """
        Transform a provider response into the unified gateway format.

        Args:
            response: The raw dict from the provider's API.
            model: The model identifier used for the request.

        Returns:
            A unified ChatResponse.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if this provider is reachable and operational.

        Returns:
            True if healthy, False otherwise.
        """
        ...

    def supports_model(self, model: str) -> bool:
        """Check if this adapter supports the given model."""
        return model in self.supported_models


# --- Provider Errors ---


class ProviderError(Exception):
    """Base exception for provider-related errors."""

    def __init__(
        self,
        message: str,
        provider: str,
        status_code: int = 502,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.original_error = original_error


class ProviderTimeoutError(ProviderError):
    """Provider request timed out."""

    def __init__(self, provider: str, timeout_seconds: float):
        super().__init__(
            message=f"Provider '{provider}' timed out after {timeout_seconds}s",
            provider=provider,
            status_code=504,
        )


class ProviderRateLimitError(ProviderError):
    """Provider rate limit exceeded."""

    def __init__(self, provider: str, retry_after: Optional[int] = None):
        super().__init__(
            message=f"Provider '{provider}' rate limit exceeded",
            provider=provider,
            status_code=429,
        )
        self.retry_after = retry_after


class ProviderAuthError(ProviderError):
    """Provider authentication failed (bad API key)."""

    def __init__(self, provider: str):
        super().__init__(
            message=f"Provider '{provider}' authentication failed — check API key",
            provider=provider,
            status_code=401,
        )
