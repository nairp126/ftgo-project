"""
Integration and regression tests for Phase 2: Reverse Proxy Layer
"""

import pytest
import uuid
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.proxy_config import get_route, RouteConfig
from app.api.dependencies import authenticate_api_key


# Define a mock authentication dependency that populates tenant_id
MOCK_TENANT_ID = uuid.uuid4()
MOCK_API_KEY_ID = uuid.uuid4()

async def mock_auth(request: Request):
    request.state.api_key_id = MOCK_API_KEY_ID
    request.state.tenant_id = MOCK_TENANT_ID
    request.state.rate_limit_per_minute = 60


@pytest.fixture
def app_instance() -> FastAPI:
    from app.main import create_app
    app = create_app()
    # Override auth dependency
    app.dependency_overrides[authenticate_api_key] = mock_auth
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def test_client(app_instance) -> TestClient:
    return TestClient(app_instance, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Route Table Config Tests (Step 1 Verification)
# ---------------------------------------------------------------------------

def test_route_table_matching():
    """Verify that get_route matches allowed prefixes and rejects internal ones."""
    # Matches orders
    route_orders = get_route("/api/orders/123")
    assert route_orders is not None
    assert route_orders.prefix == "/api/orders"
    assert route_orders.strip_prefix is True
    assert route_orders.timeout_seconds == 30.0

    # Matches consumers
    route_consumers = get_route("/api/consumers/xyz")
    assert route_consumers is not None
    assert route_consumers.prefix == "/api/consumers"
    assert route_consumers.timeout_seconds == 10.0

    # Excluded routes
    assert get_route("/v1/chat/completions") is None
    assert get_route("/health") is None
    assert get_route("/admin/keys") is None
    assert get_route("/unknown/path") is None


# ---------------------------------------------------------------------------
# Proxy Forwarding Tests (Step 2 & 3 Verification)
# ---------------------------------------------------------------------------

@patch("httpx.AsyncClient.send", new_callable=AsyncMock)
def test_proxy_forward_success(mock_send, test_client):
    """
    Test successful proxy request to /api/orders/123.
    Verifies:
      - Path prefix stripping (/api/orders/123 -> /orders/123)
      - Header filtering (Authorization stripped, X-Tenant-ID injected)
      - Status code preservation
    """
    # Mock downstream response
    mock_resp = httpx.Response(
        201,
        json={"orderId": "order-123"},
        headers={"Content-Type": "application/json", "Connection": "keep-alive"}
    )
    mock_send.return_value = mock_resp

    # Make request to gateway
    headers = {
        "Authorization": "Bearer some-token",
        "X-API-Key": "my-secret-key",
        "Cookie": "session=abc",
        "X-User-Role": "admin",
        "X-Correlation-ID": "test-correlation-123"
    }
    response = test_client.post("/api/orders/123", json={"item": "burger"}, headers=headers)

    # Assert gateway response
    assert response.status_code == 201
    assert response.json() == {"orderId": "order-123"}
    # Verifies connection headers are stripped from response
    assert "Connection" not in response.headers

    # Verify downstream request structure
    assert mock_send.call_count == 1
    sent_request = mock_send.call_args[0][0]
    
    # 1. Path prefix stripped: /api/orders/123 -> /orders/123
    assert sent_request.url.path == "/orders/123"
    
    # 2. Blacklisted headers stripped
    assert "Authorization" not in sent_request.headers
    assert "X-API-Key" not in sent_request.headers
    assert "Cookie" not in sent_request.headers
    
    # 3. Whitelisted / identity headers injected
    assert sent_request.headers.get("X-Tenant-ID") == str(MOCK_TENANT_ID)
    assert sent_request.headers.get("X-Authenticated") == "true"
    assert sent_request.headers.get("X-User-Role") == "admin"
    assert sent_request.headers.get("X-Correlation-ID") == "test-correlation-123"


@patch("httpx.AsyncClient.send", new_callable=AsyncMock)
def test_proxy_timeout_error(mock_send, test_client):
    """Verify that httpx.TimeoutException maps to 504 UPSTREAM_TIMEOUT."""
    mock_send.side_effect = httpx.TimeoutException("Request timed out")

    response = test_client.get("/api/consumers/info")
    assert response.status_code == 504
    data = response.json()
    assert data["error"]["code"] == "UPSTREAM_TIMEOUT"
    assert "correlation_id" in data["error"]


@patch("httpx.AsyncClient.send", new_callable=AsyncMock)
def test_proxy_connect_error(mock_send, test_client):
    """Verify that httpx.ConnectError maps to 503 UPSTREAM_UNAVAILABLE."""
    mock_send.side_effect = httpx.ConnectError("Connection refused")

    response = test_client.get("/api/kitchen/status")
    assert response.status_code == 503
    data = response.json()
    assert data["error"]["code"] == "UPSTREAM_UNAVAILABLE"


@patch("httpx.AsyncClient.send", new_callable=AsyncMock)
def test_proxy_other_error(mock_send, test_client):
    """Verify that other httpx errors map to 502 UPSTREAM_ERROR."""
    mock_send.side_effect = httpx.ReadError("Socket closed prematurely")

    response = test_client.get("/api/restaurants/details")
    assert response.status_code == 502
    data = response.json()
    assert data["error"]["code"] == "UPSTREAM_ERROR"


def test_proxy_route_not_found(test_client):
    """Verify that unmatched paths return 404 ROUTE_NOT_FOUND."""
    response = test_client.get("/api/unknown-service/xyz")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "ROUTE_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /actuator/health Tests (from Phase 1)
# ---------------------------------------------------------------------------

@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
def test_actuator_health_proxies_success(mock_get, test_client):
    """
    GET /actuator/health should proxy to DOWNSTREAM_HEALTH_URL and return 200.
    It should bypass both authentication and rate-limiting.
    """
    settings = get_settings()
    downstream_url = settings.downstream_health_url

    mock_resp = httpx.Response(200, json={"status": "UP"})
    mock_get.return_value = mock_resp

    response = test_client.get("/actuator/health")
    assert response.status_code == 200
    assert response.json() == {"status": "UP"}
    mock_get.assert_called_once_with(downstream_url)


@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
def test_actuator_health_downstream_unavailable(mock_get, test_client):
    """
    GET /actuator/health should return 503 if downstream is unreachable.
    """
    settings = get_settings()
    downstream_url = settings.downstream_health_url

    mock_get.side_effect = httpx.ConnectError("Connection refused")

    response = test_client.get("/actuator/health")
    assert response.status_code == 503
    assert response.json() == {"status": "DOWNSTREAM_UNAVAILABLE"}
    mock_get.assert_called_once_with(downstream_url)
