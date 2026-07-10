"""
Integration tests — verifies full app wiring.
"""

import logging
import os
from unittest.mock import patch

import pytest

from app.core.config import get_settings, Settings
from app.services.metrics import MetricsCollector
from app.services.brute_force import BruteForceProtector
from app.middleware.security import SECURITY_HEADERS


# ===========================================================================
# Config Tests
# ===========================================================================


class TestConfig:

    def test_load_config_defaults(self):
        settings = get_settings()
        assert settings.app_name == "Universal LLM Gateway"
        assert settings.port == 8000

    def test_config_has_all_sections(self):
        settings = get_settings()
        assert settings.database is not None
        assert settings.redis is not None
        assert settings.providers is not None
        assert settings.rate_limit is not None
        assert settings.security is not None

    def test_config_database_url(self):
        settings = get_settings()
        assert "postgresql" in settings.database.url

    def test_config_redis_url(self):
        settings = get_settings()
        assert "redis://" in settings.redis.url






# ===========================================================================
# App Wiring Tests
# ===========================================================================


class TestAppWiring:

    def test_create_app_succeeds(self):
        from app.main import create_app
        app = create_app()
        assert app.title == "Universal LLM Gateway"

    def test_app_has_routes(self):
        from app.main import create_app
        app = create_app()
        route_paths = []
        for r in app.routes:
            if hasattr(r, "include_context"):
                for sub in r.include_context.included_router.routes:
                    route_paths.append(r.include_context.prefix + sub.path)
            elif hasattr(r, "path"):
                route_paths.append(r.path)
        assert "/v1/chat/completions" in route_paths
        assert "/health" in route_paths
        assert "/metrics" in route_paths

    def test_app_has_admin_routes(self):
        """Requirement 2.5, 6.5, 7.5: Admin routes must be wired."""
        from app.main import create_app
        app = create_app()
        route_paths = []
        for r in app.routes:
            if hasattr(r, "include_context"):
                for sub in r.include_context.included_router.routes:
                    route_paths.append(r.include_context.prefix + sub.path)
            elif hasattr(r, "path"):
                route_paths.append(r.path)
        assert "/admin/api-keys" in route_paths
        assert "/admin/analytics" in route_paths
        assert "/admin/logs" in route_paths



# ===========================================================================
# Component Sanity Checks
# ===========================================================================


class TestComponentSanity:

    def test_metrics_collector_works(self):
        mc = MetricsCollector()
        mc.record_request("openai", 100.0)
        mc.record_cache(hit=True)
        mc.record_cost(0.001)
        mc.record_tokens(100, 50)
        m = mc.get_metrics()
        assert m["gateway_requests_total"] == 1

    def test_brute_force_works(self):
        bf = BruteForceProtector()
        bf.record_failure("test")
        assert bf.get_failure_count("test") == 1

    def test_security_headers_defined(self):
        assert len(SECURITY_HEADERS) >= 4


# ===========================================================================
# Config Environment Override Tests (Requirement 11.1)
# ===========================================================================


class TestConfigEnvironmentOverrides:

    def test_default_model_available(self):
        """Requirement 11.2: Default model must be configurable."""
        settings = get_settings()
        assert settings.providers.default_model is not None

    def test_fallback_models_available(self):
        """Requirement 11.3: Fallback chain must be configurable."""
        settings = get_settings()
        assert len(settings.providers.fallback_models) > 0


# ===========================================================================
# Structured Logging Wiring Test (Requirement 15.8)
# ===========================================================================


class TestLoggingWiring:

    def test_core_logging_json_formatter(self):
        """Requirement 15.8: Core logging must produce JSON."""
        from app.core.logging import JSONFormatter
        import logging
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        import json
        output = json.loads(formatter.format(record))
        assert output["message"] == "hello"
        assert output["level"] == "INFO"
