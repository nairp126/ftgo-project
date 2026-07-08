"""
Integration and regression tests for Phase 2 & 3: Reverse Proxy Layer & JWT
"""

import pytest
import uuid
import jwt
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.proxy_config import get_route, RouteConfig
from app.api.dependencies import authenticate_api_key


# Define a mock authentication identity
MOCK_TENANT_ID = uuid.uuid4()
MOCK_API_KEY_ID = uuid.uuid4()
JWT_SECRET = "test-secret-key-123-test-secret-key-123"

# Helper to generate test JWT
def generate_test_jwt(claims: dict, secret: str = JWT_SECRET, expires_in: int = 3600) -> str:
    payload = claims.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return jwt.encode(payload, secret, algorithm="HS256")


async def mock_auth_dependency(request: Request):
    # This is the FastAPI dependency override
    if getattr(request.state, "auth_method", None) in ("api_key", "jwt"):
        return None
    request.state.api_key_id = MOCK_API_KEY_ID
    request.state.tenant_id = MOCK_TENANT_ID
    request.state.rate_limit_per_minute = 60


@pytest.fixture
def app_instance() -> FastAPI:
    from app.main import create_app
    app = create_app()
    # Override auth dependency
    app.dependency_overrides[authenticate_api_key] = mock_auth_dependency
    yield app
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_middleware_api_key_auth():
    # Mock authenticate_api_key called inside auth middleware to avoid DB lookup
    with patch("app.middleware.auth.authenticate_api_key", new_callable=AsyncMock) as mock_auth_fn:
        async def side_effect(request, **kwargs):
            request.state.api_key_id = MOCK_API_KEY_ID
            request.state.tenant_id = MOCK_TENANT_ID
            request.state.rate_limit_per_minute = 60
            request.state.auth_method = "api_key"
        mock_auth_fn.side_effect = side_effect
        yield mock_auth_fn


@pytest.fixture
def test_client(app_instance) -> TestClient:
    return TestClient(app_instance, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Route Table Config Tests
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
# Proxy Forwarding Tests (API Key flow)
# ---------------------------------------------------------------------------

@patch("httpx.AsyncClient.send", new_callable=AsyncMock)
def test_proxy_forward_success(mock_send, test_client):
    """
    Test successful proxy request to /api/orders/123 using API Key flow.
    Verifies:
      - Path prefix stripping (/api/orders/123 -> /orders/123)
      - Header filtering (Authorization stripped, X-Tenant-ID injected)
      - Status code preservation
    """
    mock_resp = httpx.Response(
        201,
        json={"orderId": "order-123"},
        headers={"Content-Type": "application/json", "Connection": "keep-alive"}
    )
    mock_send.return_value = mock_resp

    headers = {
        "Authorization": "Bearer some-token",
        "X-API-Key": "my-secret-key",
        "Cookie": "session=abc",
        "X-User-Role": "admin",
        "X-Correlation-ID": "test-correlation-123"
    }
    response = test_client.post("/api/orders/123", json={"item": "burger"}, headers=headers)

    assert response.status_code == 201
    assert response.json() == {"orderId": "order-123"}
    assert "Connection" not in response.headers

    assert mock_send.call_count == 1
    sent_request = mock_send.call_args[0][0]
    
    assert sent_request.url.path == "/orders/123"
    assert "Authorization" not in sent_request.headers
    assert "X-API-Key" not in sent_request.headers
    assert "Cookie" not in sent_request.headers
    assert sent_request.headers.get("X-Tenant-ID") == str(MOCK_TENANT_ID)
    assert sent_request.headers.get("X-Authenticated") == "true"


# ---------------------------------------------------------------------------
# JWT Authentication Integration Tests (Phase 3)
# ---------------------------------------------------------------------------

@patch("httpx.AsyncClient.send", new_callable=AsyncMock)
def test_jwt_auth_success(mock_send, test_client):
    """
    Verify that a valid JWT token succeeds, sets request state,
    and forwards identity headers (X-User-ID, X-Tenant-ID, X-User-Roles) downstream.
    """
    mock_resp = httpx.Response(
        200,
        json={"status": "success"},
        headers={"Content-Type": "application/json"}
    )
    mock_send.return_value = mock_resp

    # Generate valid JWT
    token_claims = {
        "sub": "user-999",
        "tenant_id": "tenant-888",
        "roles": ["customer", "subscriber"],
        "email": "user@example.com"
    }
    jwt_token = generate_test_jwt(token_claims)

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "X-Correlation-ID": "jwt-test-123"
    }
    response = test_client.get("/api/orders/my-active", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "success"}

    assert mock_send.call_count == 1
    sent_request = mock_send.call_args[0][0]

    # Verify injected downstream identity headers
    assert sent_request.headers.get("X-Tenant-ID") == "tenant-888"
    assert sent_request.headers.get("X-User-ID") == "user-999"
    assert sent_request.headers.get("X-User-Roles") == "customer,subscriber"
    assert sent_request.headers.get("X-Authenticated") == "true"


def test_jwt_auth_expired(test_client):
    """Verify expired JWT returns 401 Token expired."""
    token_claims = {
        "sub": "user-999",
        "tenant_id": "tenant-888"
    }
    expired_token = generate_test_jwt(token_claims, expires_in=-10)

    headers = {
        "Authorization": f"Bearer {expired_token}"
    }
    response = test_client.get("/api/orders/my-active", headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["type"] == "authentication_error"
    assert data["error"]["message"] == "Token expired"


def test_jwt_auth_invalid_signature(test_client):
    """Verify JWT with invalid signature returns 401 Invalid token."""
    token_claims = {
        "sub": "user-999",
        "tenant_id": "tenant-888"
    }
    invalid_token = generate_test_jwt(token_claims, secret="wrong-secret-key")

    headers = {
        "Authorization": f"Bearer {invalid_token}"
    }
    response = test_client.get("/api/orders/my-active", headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["type"] == "authentication_error"
    assert data["error"]["message"] == "Invalid token"


def test_jwt_auth_missing_claims(test_client):
    """Verify JWT missing sub or tenant_id returns 401 Token missing required claims."""
    # Missing sub
    token_claims = {
        "tenant_id": "tenant-888"
    }
    token = generate_test_jwt(token_claims)

    headers = {
        "Authorization": f"Bearer {token}"
    }
    response = test_client.get("/api/orders/my-active", headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["message"] == "Token missing required claims"


# ---------------------------------------------------------------------------
# Proxy Error Handling Tests
# ---------------------------------------------------------------------------

@patch("httpx.AsyncClient.send", new_callable=AsyncMock)
def test_proxy_timeout_error(mock_send, test_client):
    """Verify that httpx.TimeoutException maps to 504 UPSTREAM_TIMEOUT."""
    mock_send.side_effect = httpx.TimeoutException("Request timed out")

    headers = {"Authorization": "Bearer some-token"}
    response = test_client.get("/api/consumers/info", headers=headers)
    assert response.status_code == 504
    data = response.json()
    assert data["error"]["code"] == "UPSTREAM_TIMEOUT"
    assert "correlation_id" in data["error"]


@patch("httpx.AsyncClient.send", new_callable=AsyncMock)
def test_proxy_connect_error(mock_send, test_client):
    """Verify that httpx.ConnectError maps to 503 UPSTREAM_UNAVAILABLE."""
    mock_send.side_effect = httpx.ConnectError("Connection refused")

    headers = {"Authorization": "Bearer some-token"}
    response = test_client.get("/api/kitchen/status", headers=headers)
    assert response.status_code == 503
    data = response.json()
    assert data["error"]["code"] == "UPSTREAM_UNAVAILABLE"


@patch("httpx.AsyncClient.send", new_callable=AsyncMock)
def test_proxy_other_error(mock_send, test_client):
    """Verify that other httpx errors map to 502 UPSTREAM_ERROR."""
    mock_send.side_effect = httpx.ReadError("Socket closed prematurely")

    headers = {"Authorization": "Bearer some-token"}
    response = test_client.get("/api/restaurants/details", headers=headers)
    assert response.status_code == 502
    data = response.json()
    assert data["error"]["code"] == "UPSTREAM_ERROR"


def test_proxy_route_not_found(test_client):
    """Verify that unmatched paths return 404 ROUTE_NOT_FOUND."""
    headers = {"Authorization": "Bearer some-token"}
    response = test_client.get("/api/unknown-service/xyz", headers=headers)
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "ROUTE_NOT_FOUND"


# ---------------------------------------------------------------------------
# GET /actuator/health Tests
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
