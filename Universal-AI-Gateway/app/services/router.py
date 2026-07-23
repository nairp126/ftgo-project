"""
Request routing engine.
Routes chat requests to the appropriate provider adapter based on
model name, with fallback chain support.

Supports Requirements 4.1–4.5.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from collections import deque

from app.providers.base import (
    ProviderAdapter,
    ProviderError,
    get_provider_for_model,
    MODEL_PROVIDER_MAP,
)
from app.providers.openai_provider import OpenAIProvider
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.bedrock_provider import BedrockProvider
from app.providers.google_provider import GoogleProvider
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

# Default model when no model is specified (Requirement 4.2)
DEFAULT_MODEL = "gpt-4o"

# Fallback chains: if the primary provider fails, try these in order (Requirement 4.3)
FALLBACK_CHAINS: Dict[str, List[str]] = {
    "openai": ["anthropic", "google", "bedrock"],
    "anthropic": ["openai", "google", "bedrock"],
    "google": ["openai", "anthropic", "bedrock"],
    "bedrock": ["openai", "anthropic", "google"],
}

# Default model per provider (used during fallback)
PROVIDER_DEFAULT_MODELS: Dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20241022",
    "google": "gemini-1.5-flash",
    "bedrock": "bedrock/claude-3-5-sonnet",
}


@dataclass
class RoutingDecision:
    """Records the reasoning behind a routing decision."""
    request_id: str
    original_model: str
    resolved_model: str
    provider: str
    reason: str
    fallback_attempted: bool = False
    fallback_providers: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "original_model": self.original_model,
            "resolved_model": self.resolved_model,
            "provider": self.provider,
            "reason": self.reason,
            "fallback_attempted": self.fallback_attempted,
            "fallback_providers": self.fallback_providers,
            "latency_ms": round(self.latency_ms, 2),
            "success": self.success,
            "error": self.error,
        }


class RoutingEngine:
    """
    Routes chat requests to the correct provider adapter.

    Supports:
    - Explicit model selection → provider lookup  (Req 4.1)
    - Default model when none specified            (Req 4.2)
    - Fallback chains on provider failure           (Req 4.3)
    - Routing decision logging                      (Req 4.4)
    - Routing metadata in responses                 (Req 4.5)
    """

    def __init__(self):
        self._providers: Dict[str, ProviderAdapter] = {}
        self._decisions = deque(maxlen=1000)
        self._init_providers()

    def _init_providers(self):
        """Lazily initialise provider adapters."""
        try:
            self._providers["openai"] = OpenAIProvider()
        except Exception as e:
            logger.warning("Failed to init OpenAI provider: %s", e)
        try:
            self._providers["anthropic"] = AnthropicProvider()
        except Exception as e:
            logger.warning("Failed to init Anthropic provider: %s", e)
        try:
            self._providers["bedrock"] = BedrockProvider()
        except Exception as e:
            logger.warning("Failed to init Bedrock provider: %s", e)
        try:
            self._providers["google"] = GoogleProvider()
        except Exception as e:
            logger.warning("Failed to init Google provider: %s", e)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def close_clients(self):
        """Close all provider HTTP clients."""
        for provider in self._providers.values():
            if hasattr(provider, '_client'):
                try:
                    await provider._client.aclose()
                except Exception as e:
                    logger.warning("Error closing provider %s: %s", provider.provider_name, e)

    def resolve_provider(self, model: Optional[str]) -> tuple:
        """
        Determine which provider and model to use.

        Args:
            model: Model name from the request, or None.

        Returns:
            (resolved_model, provider_name, reason)
        """
        if not model:
            return DEFAULT_MODEL, get_provider_for_model(DEFAULT_MODEL), "default_model"

        provider_name = get_provider_for_model(model)
        if provider_name:
            return model, provider_name, "explicit_model"

        # Unknown model — try default
        logger.warning("Unknown model '%s', falling back to default '%s'", model, DEFAULT_MODEL)
        return DEFAULT_MODEL, get_provider_for_model(DEFAULT_MODEL), "unknown_model_fallback"

    def get_provider(self, provider_name: str) -> Optional[ProviderAdapter]:
        """Get an initialised provider adapter by name."""
        return self._providers.get(provider_name)

    def get_fallback_chain(self, provider_name: str) -> List[str]:
        """Get the ordered fallback providers for a given primary provider."""
        return FALLBACK_CHAINS.get(provider_name, [])

    async def route_request(
        self,
        request: ChatRequest,
        request_id: Optional[str] = None,
    ) -> tuple:
        """
        Route a request to the appropriate provider, with fallback.

        Returns:
            (ChatResponse, RoutingDecision)

        Raises:
            ProviderError: If all providers in the chain fail.
        """
        request_id = request_id or str(uuid.uuid4())
        start = time.time()

        # Resolve model → provider
        resolved_model, provider_name, reason = self.resolve_provider(request.model)

        # Build the request with the resolved model
        routed_request = request.model_copy(update={"model": resolved_model})

        decision = RoutingDecision(
            request_id=request_id,
            original_model=request.model or "",
            resolved_model=resolved_model,
            provider=provider_name,
            reason=reason,
        )

        # Try primary provider
        provider = self.get_provider(provider_name)
        if provider:
            try:
                response = await provider.chat_completion(routed_request)
                decision.latency_ms = (time.time() - start) * 1000
                decision.success = True
                self._record_decision(decision)
                return response, decision
            except ProviderError as exc:
                logger.warning(
                    "Primary provider %s failed for %s: %s",
                    provider_name, resolved_model, exc,
                )
                decision.error = str(exc)

        # Fallback chain (Requirement 4.3)
        fallback_chain = self.get_fallback_chain(provider_name)
        decision.fallback_attempted = True
        decision.fallback_providers = fallback_chain

        for fb_provider_name in fallback_chain:
            fb_provider = self.get_provider(fb_provider_name)
            if not fb_provider:
                continue

            # Use the fallback provider's default model
            fb_model = PROVIDER_DEFAULT_MODELS.get(fb_provider_name)
            if not fb_model:
                continue

            fb_request = request.model_copy(update={"model": fb_model})

            try:
                response = await fb_provider.chat_completion(fb_request)
                decision.provider = fb_provider_name
                decision.resolved_model = fb_model
                decision.reason = f"fallback_from_{provider_name}"
                decision.latency_ms = (time.time() - start) * 1000
                decision.success = True
                self._record_decision(decision)
                return response, decision
            except ProviderError as exc:
                logger.warning(
                    "Fallback provider %s failed: %s", fb_provider_name, exc,
                )
                continue

        # All providers failed
        decision.latency_ms = (time.time() - start) * 1000
        decision.success = False
        self._record_decision(decision)

        raise ProviderError(
            message=f"All providers failed for model {resolved_model}",
            provider=provider_name,
            status_code=503,
        )

    async def stream_request(
        self, request: ChatRequest, request_id: str
    ) -> Tuple[Any, RoutingDecision]:
        """
        Route a streaming request to the appropriate provider.
        """
        # Mock LLM (Requirement 3.3) for testing
        if os.getenv("MOCK_LLM", "false").lower() == "true":
            decision = RoutingDecision(
                request_id=request_id,
                provider="mock",
                resolved_model=request.model,
                success=True,
                reason="mock_mode_streaming"
            )
            
            async def mock_generator():
                yield b'data: {"id": "mock-stream", "choices": [{"delta": {"role": "assistant", "content": "[MOCK] "}, "index": 0}]}\n\n'
                yield b'data: {"id": "mock-stream", "choices": [{"delta": {"content": "Streaming "}, "index": 0}]}\n\n'
                yield b'data: {"id": "mock-stream", "choices": [{"delta": {"content": "Response"}, "index": 0}]}\n\n'
                yield b'data: [DONE]\n\n'
                
            self._record_decision(decision)
            return mock_generator(), decision

        # 1. Determine base provider
        provider_name = self.get_provider_for_model(request.model)
        resolved_model = request.model
        
        # ... (Similar to route_request but for streaming)
        provider = self.get_provider(provider_name)
        if not provider:
            raise ProviderError(f"No provider found for model {request.model}")
            
        decision = RoutingDecision(
            request_id=request_id,
            provider=provider_name,
            resolved_model=resolved_model,
        )
        
        try:
            stream = await provider.stream_chat_completion(request)
            decision.success = True
            self._record_decision(decision)
            return stream, decision
        except Exception as e:
            logger.error(f"Streaming failed for {provider_name}: {e}")
            # Simplified fallback for streaming (can be enhanced)
            raise ProviderError(f"Streaming failed: {e}", provider=provider_name)

    # ------------------------------------------------------------------
    # Decision logging (Requirement 4.4)
    # ------------------------------------------------------------------

    def _record_decision(self, decision: RoutingDecision):
        """Log and store the routing decision."""
        self._decisions.append(decision)
        logger.info(
            "Routing decision: model=%s provider=%s reason=%s fallback=%s success=%s latency=%.1fms",
            decision.resolved_model,
            decision.provider,
            decision.reason,
            decision.fallback_attempted,
            decision.success,
            decision.latency_ms,
        )

    def get_recent_decisions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent routing decisions for analytics."""
        decisions_list = list(self._decisions)
        return [d.to_dict() for d in decisions_list[-limit:]]

    def get_routing_stats(self) -> Dict[str, Any]:
        """Aggregate routing statistics."""
        if not self._decisions:
            return {"total": 0, "success_rate": 0.0, "fallback_rate": 0.0}

        total = len(self._decisions)
        successes = sum(1 for d in self._decisions if d.success)
        fallbacks = sum(1 for d in self._decisions if d.fallback_attempted)

        return {
            "total": total,
            "success_rate": round(successes / total, 4),
            "fallback_rate": round(fallbacks / total, 4),
            "avg_latency_ms": round(
                sum(d.latency_ms for d in self._decisions) / total, 2
            ),
        }
