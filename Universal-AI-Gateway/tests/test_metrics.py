"""
Tests for Prometheus metrics and structured logging.
"""

import json
import logging

import pytest

from app.services.metrics import MetricsCollector
from app.services.logging_config import JSONFormatter, configure_logging


# ===========================================================================
# Metrics Collector Tests
# ===========================================================================


class TestMetricsCollector:

    def setup_method(self):
        self.mc = MetricsCollector()

    def test_initial_metrics_zeros(self):
        m = self.mc.get_metrics()
        assert m["gateway_requests_total"] == 0
        assert m["gateway_errors_total"] == 0
        assert m["cache_hits_total"] == 0
        # Edge case: rates should be 0, not error on division
        assert m["gateway_error_rate"] == 0.0
        assert m["cache_hit_rate"] == 0.0
        assert m["cost_avg_usd"] == 0.0

    def test_record_request(self):
        self.mc.record_request("openai", 100.0)
        m = self.mc.get_metrics()
        assert m["gateway_requests_total"] == 1
        assert m["gateway_latency_avg_ms"] == 100.0

    def test_record_error(self):
        self.mc.record_request("openai", 50.0, error=True)
        m = self.mc.get_metrics()
        assert m["gateway_errors_total"] == 1
        assert m["gateway_error_rate"] > 0

    def test_record_cache_hit(self):
        self.mc.record_cache(hit=True)
        self.mc.record_cache(hit=False)
        m = self.mc.get_metrics()
        assert m["cache_hits_total"] == 1
        assert m["cache_misses_total"] == 1
        assert m["cache_hit_rate"] == 0.5

    def test_record_provider_breakdown(self):
        self.mc.record_request("openai", 100.0)
        self.mc.record_request("anthropic", 200.0)
        m = self.mc.get_metrics()
        assert m["provider_requests"]["openai"] == 1
        assert m["provider_requests"]["anthropic"] == 1

    def test_record_cost(self):
        self.mc.record_cost(0.001)
        self.mc.record_cost(0.002)
        m = self.mc.get_metrics()
        assert m["cost_total_usd"] == 0.003

    def test_record_tokens(self):
        self.mc.record_tokens(100, 50)
        self.mc.record_tokens(200, 100)
        m = self.mc.get_metrics()
        assert m["tokens_prompt_total"] == 300
        assert m["tokens_completion_total"] == 150
        assert m["tokens_total"] == 450

    def test_reset(self):
        self.mc.record_request("openai", 100.0)
        self.mc.reset()
        m = self.mc.get_metrics()
        assert m["gateway_requests_total"] == 0

    def test_metrics_has_all_required_keys(self):
        """Requirements 15.1–15.6: All metric categories must be present."""
        m = self.mc.get_metrics()
        required = {
            "gateway_requests_total", "gateway_errors_total", "gateway_error_rate",
            "gateway_latency_avg_ms", "cache_hits_total", "cache_misses_total",
            "cache_hit_rate", "provider_requests", "provider_errors",
            "cost_total_usd", "cost_avg_usd",
            "tokens_prompt_total", "tokens_completion_total", "tokens_total",
        }
        assert required.issubset(m.keys())


# ===========================================================================
# Structured Logging Tests
# ===========================================================================


class TestJSONFormatter:

    def test_produces_valid_json(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Hello", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "Hello"
        assert parsed["level"] == "INFO"

    def test_includes_timestamp(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="", lineno=0,
            msg="Warning msg", args=(), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "timestamp" in parsed

    def test_includes_extra_fields(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test", args=(), exc_info=None,
        )
        record.correlation_id = "abc-123"
        record.request_id = "req-456"
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["correlation_id"] == "abc-123"
        assert parsed["request_id"] == "req-456"
