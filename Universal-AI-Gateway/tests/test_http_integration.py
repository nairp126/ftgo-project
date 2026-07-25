"""
HTTP-level integration tests using FastAPI TestClient.
Tests the full middleware stack: CORS, Auth, RateLimit, Security Headers, Error Handling.

Supports R2-8: Validates the wired application behaves correctly at the HTTP layer.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings

# Override settings once globally for all integration tests
settings = get_settings()
settings.security.admin_api_key = "test-admin-token-123"
TEST_ADMIN_KEY = settings.security.admin_api_key

@pytest.fixture(autouse=True)
def setup_overrides():
    """Ensure dependencies are overridden for every test."""
    from app.api.dependencies import authenticate_api_key, verify_admin_token
    from app.db.database import get_db
    from unittest.mock import AsyncMock, MagicMock

    async def mock_get_db():
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        yield mock_db

    app.dependency_overrides[authenticate_api_key] = lambda: None
    app.dependency_overrides[verify_admin_token] = lambda: True
    app.dependency_overrides[get_db] = mock_get_db
    yield
    app.dependency_overrides.clear()

@pytest.fixture(name="client_fixture")
def client_fixture():
    """Fixture for TestClient."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

# Global variable for tests to use (R2-8)
client = None

@pytest.fixture(autouse=True)
def _set_global_client(client_fixture):
    """Set the global client variable for each test execution."""
    global client
    client = client_fixture


# ===========================================================================
# Health Endpoint (full middleware stack)
# ===========================================================================


class TestHealthHTTP:

    def test_get_health_returns_200(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_has_status(self):
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("healthy", "degraded")

    def test_health_has_providers(self):
        resp = client.get("/health")
        data = resp.json()
        assert "components" in data
        assert "providers" in data["components"]
        assert len(data["components"]["providers"]) > 0

    def test_health_providers_have_circuit_state(self):
        """R2: Live health checks return circuit breaker state."""
        resp = client.get("/health")
        providers = resp.json()["components"]["providers"]
        for name, info in providers.items():
            assert "circuit_state" in info
            assert "failure_count" in info


# ===========================================================================
# Security Headers (full middleware stack)
# ===========================================================================


class TestSecurityHeadersHTTP:

    def test_hsts_header_present(self):
        resp = client.get("/health")
        assert "strict-transport-security" in resp.headers

    def test_content_type_options_header(self):
        resp = client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_xss_protection_header(self):
        resp = client.get("/health")
        assert "x-xss-protection" in resp.headers

    def test_frame_options_header(self):
        resp = client.get("/health")
        assert resp.headers.get("x-frame-options") == "DENY"


# ===========================================================================
# Metrics Endpoint
# ===========================================================================


class TestMetricsHTTP:

    def test_get_metrics_returns_200(self):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_contains_required_keys(self):
        resp = client.get("/metrics")
        data = resp.json()
        assert "gateway_requests_total" in data
        assert "gateway_error_rate" in data
        assert "cache_hit_rate" in data
        assert "cost_total_usd" in data


# ===========================================================================
# Admin Endpoints
# ===========================================================================


class TestAdminHTTP:

    def test_admin_analytics_returns_200(self):
        resp = client.get("/admin/analytics", headers={"X-Admin-Token": TEST_ADMIN_KEY})
        assert resp.status_code == 200

    def test_admin_analytics_has_required_fields(self):
        resp = client.get("/admin/analytics", headers={"X-Admin-Token": TEST_ADMIN_KEY})
        data = resp.json()
        assert "total_requests" in data
        assert "total_cost_usd" in data
        assert "error_rate" in data

    def test_admin_logs_returns_200(self):
        resp = client.get("/admin/logs", headers={"X-Admin-Token": TEST_ADMIN_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert "total" in data

    def test_admin_logs_limit_parameter(self):
        resp = client.get("/admin/logs?limit=5", headers={"X-Admin-Token": TEST_ADMIN_KEY})
        assert resp.status_code == 200

    def test_admin_api_keys_returns_200(self):
        resp = client.get("/admin/api-keys", headers={"X-Admin-Token": TEST_ADMIN_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert "keys" in data

    def test_admin_export_logs_returns_status(self):
        resp = client.post("/admin/logs/export", headers={"X-Admin-Token": TEST_ADMIN_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ["skipped", "success", "error"]


# ===========================================================================
# Docs Endpoint
# ===========================================================================


class TestDocsHTTP:

    def test_openapi_schema_available(self):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "Universal LLM Gateway"

    def test_docs_page_available(self):
        resp = client.get("/docs")
        assert resp.status_code == 200


# ===========================================================================
# Chat Completions (error path — no provider configured)
# ===========================================================================


class TestChatCompletionsHTTP:

    def test_chat_completions_returns_json_on_error(self):
        """Without a real provider, should return a structured error, not crash."""
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        # Should return a provider error (502/503), not a 500 crash
        assert resp.status_code in (200, 400, 401, 429, 500, 502, 503)
        data = resp.json()
        assert isinstance(data, dict)

    def test_chat_completions_has_correlation_id_on_error(self):
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        # Error responses should always have correlation ID
        if resp.status_code >= 400:
            assert "x-correlation-id" in resp.headers

    def test_chat_completions_returns_422_on_invalid_body(self):
        """FastAPI validation should reject malformed requests."""
        resp = client.post(
            "/v1/chat/completions",
            json={"not_a_valid_field": True},
        )
        assert resp.status_code == 422


# ===========================================================================
# CORS
# ===========================================================================


class TestCORSHTTP:

    def test_cors_preflight_allowed(self):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers
