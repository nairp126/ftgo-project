"""
Prometheus metrics service.
Exposes /metrics endpoint and tracks RED metrics, cache, provider, cost, tokens.
Supports Requirements 15.1–15.6.
"""

import logging
import time
from typing import Dict, Any

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    In-memory metrics collector.

    In production this would use prometheus_client counters/histograms.
    This implementation tracks the same metrics in-memory for testing.
    """

    def __init__(self):
        # RED metrics (Requirement 15.2)
        self._request_count = 0
        self._error_count = 0
        self._latency_sum = 0.0
        self._latency_count = 0

        # Cache metrics (Requirement 15.3)
        self._cache_hits = 0
        self._cache_misses = 0

        # Provider metrics (Requirement 15.4)
        self._provider_requests: Dict[str, int] = {}
        self._provider_errors: Dict[str, int] = {}
        self._provider_latency: Dict[str, float] = {}

        # Cost metrics (Requirement 15.5)
        self._total_cost = 0.0
        self._cost_count = 0

        # Token metrics (Requirement 15.6)
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0

    # ------------------------------------------------------------------
    # Recording methods
    # ------------------------------------------------------------------

    def record_request(self, provider: str, latency_ms: float, error: bool = False):
        """Record a request (RED metrics + provider metrics)."""
        self._request_count += 1
        self._latency_sum += latency_ms
        self._latency_count += 1

        if error:
            self._error_count += 1
            self._provider_errors[provider] = self._provider_errors.get(provider, 0) + 1

        self._provider_requests[provider] = self._provider_requests.get(provider, 0) + 1
        self._provider_latency[provider] = (
            self._provider_latency.get(provider, 0.0) + latency_ms
        )

    def record_cache(self, hit: bool):
        """Record a cache hit or miss."""
        if hit:
            self._cache_hits += 1
        else:
            self._cache_misses += 1

    def record_cost(self, cost_usd: float):
        """Record cost for a request."""
        self._total_cost += cost_usd
        self._cost_count += 1

    def record_tokens(self, prompt_tokens: int, completion_tokens: int):
        """Record token usage."""
        self._total_prompt_tokens += prompt_tokens
        self._total_completion_tokens += completion_tokens

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_metrics(self) -> Dict[str, Any]:
        """
        Return all metrics in a dict suitable for /metrics endpoint.

        Mirrors Prometheus metric naming conventions.
        """
        avg_latency = (
            self._latency_sum / self._latency_count
            if self._latency_count > 0
            else 0.0
        )
        error_rate = (
            self._error_count / self._request_count
            if self._request_count > 0
            else 0.0
        )
        cache_total = self._cache_hits + self._cache_misses
        cache_hit_rate = (
            self._cache_hits / cache_total if cache_total > 0 else 0.0
        )

        return {
            # RED metrics
            "gateway_requests_total": self._request_count,
            "gateway_errors_total": self._error_count,
            "gateway_error_rate": round(error_rate, 4),
            "gateway_latency_avg_ms": round(avg_latency, 2),
            # Cache metrics
            "cache_hits_total": self._cache_hits,
            "cache_misses_total": self._cache_misses,
            "cache_hit_rate": round(cache_hit_rate, 4),
            # Provider metrics
            "provider_requests": dict(self._provider_requests),
            "provider_errors": dict(self._provider_errors),
            # Cost metrics
            "cost_total_usd": round(self._total_cost, 8),
            "cost_avg_usd": round(
                self._total_cost / self._cost_count if self._cost_count > 0 else 0.0, 8
            ),
            # Token metrics
            "tokens_prompt_total": self._total_prompt_tokens,
            "tokens_completion_total": self._total_completion_tokens,
            "tokens_total": self._total_prompt_tokens + self._total_completion_tokens,
        }

    def reset(self):
        """Reset all metrics (useful for testing)."""
        self.__init__()


# Singleton instance
metrics = MetricsCollector()
