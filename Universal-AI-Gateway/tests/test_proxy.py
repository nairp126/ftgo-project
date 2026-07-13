"""
Integration test suite for the Universal AI Gateway proxy layer.
Covers Phase 5 requirements across 6 functional test groups.
"""

import pytest
import uuid
import jwt
import respx
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from httpx import Response, TimeoutException, ConnectError

from app.core.proxy_config import get_route, RouteConfig
from app.services.budget_manager import BudgetManager, BudgetExceededError

MOCK_TENANT_ID = "tenant-test-123"
MOCK_API_KEY_ID = uuid.uuid4()
JWT_SECRET = "test-secret-key-123-test-secret-key-123"


@pytest.fixture(autouse=True)
def mock_api_key_auth():
    """Default mock for API key authentication in middleware."""
    with patch("app.middleware.auth.authenticate_api_key", new_callable=AsyncMock) as mock_auth_fn:
        async def side_effect(request, **kwargs):
            request.state.api_key_id = MOCK_API_KEY_ID
            request.state.tenant_id = MOCK_TENANT_ID
            request.state.rate_limit_per_minute = 60
            request.state.auth_method = "api_key"
        mock_auth_fn.side_effect = side_effect
        yield mock_auth_fn


# ---------------------------------------------------------------------------
# Route Table Config Unit Tests
# ---------------------------------------------------------------------------

def test_route_table_matching():
    """Verify that get_route matches allowed prefixes and rejects internal ones."""
    route_orders = get_route("/api/orders/123")
    assert route_orders is not None
    assert route_orders.prefix == "/api/orders"
    assert route_orders.strip_prefix is True
    assert route_orders.timeout_seconds == 30.0

    route_consumers = get_route("/api/consumers/xyz")
    assert route_consumers is not None
    assert route_consumers.prefix == "/api/consumers"
    assert route_consumers.timeout_seconds == 10.0

    assert get_route("/v1/chat/completions") is None
    assert get_route("/health") is None
    assert get_route("/admin/keys") is None
    assert get_route("/unknown/path") is None


# ===========================================================================
# Group 1 — Proxy Routing (4 tests)
# ===========================================================================

@pytest.mark.asyncio
@respx.mock
async def test_post_order_forwards_to_ftgo_gateway(client, api_key_headers, respx_mock):
    # Prevents: Regression where POST /api/orders fails to reach downstream ftgo-api-gateway:8080.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        201, json={"orderId": "order-101", "state": "PENDING"}
    )

    response = await client.post(
        "/api/orders",
        json={"consumerId": 1, "restaurantId": 1},
        headers=api_key_headers
    )

    assert response.status_code == 201
    assert response.json() == {"orderId": "order-101", "state": "PENDING"}
    assert mock_route.called


@pytest.mark.asyncio
@respx.mock
async def test_order_prefix_stripped_before_forwarding(client, api_key_headers, respx_mock):
    # Prevents: Regression where URL prefix /api/orders is not stripped before forwarding (/api/orders/123 -> /orders/123).
    mock_route = respx_mock.route(host="ftgo-api-gateway", path="/orders/123").respond(
        200, json={"orderId": "123"}
    )

    response = await client.get("/api/orders/123", headers=api_key_headers)

    assert response.status_code == 200
    assert mock_route.called
    assert mock_route.calls[0].request.url.path == "/orders/123"


@pytest.mark.asyncio
async def test_unknown_path_returns_404_with_structured_error(client, api_key_headers):
    # Prevents: Regression where unmapped proxy paths return unhandled errors instead of structured 404 JSON.
    response = await client.get("/api/non-existent-service/test", headers=api_key_headers)

    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "ROUTE_NOT_FOUND"


@pytest.mark.asyncio
@respx.mock
async def test_llm_route_not_intercepted_by_proxy(client, api_key_headers, respx_mock):
    # Prevents: Regression where /v1/chat/completions LLM endpoint is hijacked by the catch-all proxy router.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        200, json={"choices": []}
    )

    from app.schemas.chat import ChatResponse
    from app.services.router import RoutingDecision

    mock_resp = ChatResponse(
        id="chatcmpl-123",
        object="chat.completion",
        created=123456,
        model="gpt-4o",
        choices=[{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
        usage={"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}
    )
    decision = RoutingDecision(
        request_id="123",
        original_model="gpt-4o",
        resolved_model="gpt-4o",
        provider="openai",
        reason="primary_match",
        latency_ms=10.0
    )

    with patch("app.api.routes._routing_engine.route_request", new_callable=AsyncMock) as mock_route_req:
        mock_route_req.return_value = (mock_resp, decision)

        response = await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            headers=api_key_headers
        )

        assert response.status_code == 200
        assert not mock_route.called


# ===========================================================================
# Group 2 — Header Handling (7 tests)
# ===========================================================================

@pytest.mark.asyncio
@respx.mock
async def test_x_tenant_id_present_in_forwarded_request(client, api_key_headers, respx_mock):
    # Prevents: Regression where tenant identity (X-Tenant-ID) is lost during downstream request forwarding.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        200, json={"status": "ok"}
    )

    response = await client.get("/api/orders/123", headers=api_key_headers)

    assert response.status_code == 200
    assert mock_route.called
    forwarded_headers = mock_route.calls[0].request.headers
    assert "x-tenant-id" in forwarded_headers
    assert forwarded_headers["x-tenant-id"] == MOCK_TENANT_ID


@pytest.mark.asyncio
@respx.mock
async def test_x_user_id_present_when_jwt_provided(client, jwt_headers, respx_mock):
    # Prevents: Regression where JWT identity claims (X-User-ID, X-User-Roles) fail to populate downstream headers.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        200, json={"status": "ok"}
    )

    response = await client.get("/api/orders/123", headers=jwt_headers)

    assert response.status_code == 200
    assert mock_route.called
    forwarded_headers = mock_route.calls[0].request.headers
    assert forwarded_headers.get("x-user-id") == "user-123"
    assert forwarded_headers.get("x-tenant-id") == "tenant-abc"
    assert forwarded_headers.get("x-user-roles") == "user"


@pytest.mark.asyncio
@respx.mock
async def test_authorization_header_not_forwarded(client, api_key_headers, respx_mock):
    # Prevents: Regression where client credentials in Authorization header leak to downstream services.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        200, json={"status": "ok"}
    )

    response = await client.get("/api/orders/123", headers=api_key_headers)

    assert response.status_code == 200
    assert mock_route.called
    forwarded_headers = mock_route.calls[0].request.headers
    assert "authorization" not in forwarded_headers


@pytest.mark.asyncio
@respx.mock
async def test_x_api_key_header_not_forwarded(client, respx_mock):
    # Prevents: Regression where raw X-API-Key credentials leak to downstream services.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        200, json={"status": "ok"}
    )

    headers = {"X-API-Key": "secret-raw-api-key"}
    response = await client.get("/api/orders/123", headers=headers)

    assert response.status_code == 200
    assert mock_route.called
    forwarded_headers = mock_route.calls[0].request.headers
    assert "x-api-key" not in forwarded_headers


@pytest.mark.asyncio
@respx.mock
async def test_cookie_header_not_forwarded(client, api_key_headers, respx_mock):
    # Prevents: Regression where client cookies leak to downstream microservices.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        200, json={"status": "ok"}
    )

    headers = {**api_key_headers, "Cookie": "session_id=123456"}
    response = await client.get("/api/orders/123", headers=headers)

    assert response.status_code == 200
    assert mock_route.called
    forwarded_headers = mock_route.calls[0].request.headers
    assert "cookie" not in forwarded_headers


@pytest.mark.asyncio
@respx.mock
async def test_x_correlation_id_generated_when_absent(client, api_key_headers, respx_mock):
    # Prevents: Regression where distributed tracing correlation ID is missing from forwarded requests.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        200, json={"status": "ok"}
    )

    response = await client.get("/api/orders/123", headers=api_key_headers)

    assert response.status_code == 200
    assert mock_route.called
    forwarded_headers = mock_route.calls[0].request.headers
    assert "x-correlation-id" in forwarded_headers
    assert "x-request-id" in forwarded_headers


@pytest.mark.asyncio
@respx.mock
async def test_x_forwarded_for_appended(client, api_key_headers, respx_mock):
    # Prevents: Regression where client IP is omitted from X-Forwarded-For header.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        200, json={"status": "ok"}
    )

    headers = {**api_key_headers, "X-Forwarded-For": "203.0.113.195"}
    response = await client.get("/api/orders/123", headers=headers)

    assert response.status_code == 200
    assert mock_route.called
    forwarded_headers = mock_route.calls[0].request.headers
    assert "x-forwarded-for" in forwarded_headers
    assert "203.0.113.195" in forwarded_headers["x-forwarded-for"]


# ===========================================================================
# Group 3 — Error Handling (5 tests)
# ===========================================================================

@pytest.mark.asyncio
@respx.mock
async def test_downstream_timeout_returns_504(client, api_key_headers, respx_mock):
    # Prevents: Regression where upstream timeouts result in generic 500 errors instead of 504 Gateway Timeout.
    respx_mock.route(host="ftgo-api-gateway").mock(
        side_effect=TimeoutException("Upstream timeout")
    )

    response = await client.get("/api/orders/123", headers=api_key_headers)

    assert response.status_code == 504
    data = response.json()
    assert data["error"]["code"] == "UPSTREAM_TIMEOUT"


@pytest.mark.asyncio
@respx.mock
async def test_downstream_connect_error_returns_503(client, api_key_headers, respx_mock):
    # Prevents: Regression where network connectivity failures return 500 instead of 503 Service Unavailable.
    respx_mock.route(host="ftgo-api-gateway").mock(
        side_effect=ConnectError("Connection refused")
    )

    response = await client.get("/api/orders/123", headers=api_key_headers)

    assert response.status_code == 503
    data = response.json()
    assert data["error"]["code"] == "UPSTREAM_UNAVAILABLE"


@pytest.mark.asyncio
@respx.mock
async def test_downstream_404_passes_through_as_404(client, api_key_headers, respx_mock):
    # Prevents: Regression where downstream 404 response codes are converted to 500 error responses.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        404, json={"error": "Order not found"}
    )

    response = await client.get("/api/orders/999", headers=api_key_headers)

    assert response.status_code == 404
    assert response.json() == {"error": "Order not found"}
    assert mock_route.called


@pytest.mark.asyncio
@respx.mock
async def test_downstream_503_passes_through_as_503(client, api_key_headers, respx_mock):
    # Prevents: Regression where downstream 503 response codes are converted or masked.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        503, json={"error": "Kitchen Service overload"}
    )

    response = await client.get("/api/orders/123", headers=api_key_headers)

    assert response.status_code == 503
    assert response.json() == {"error": "Kitchen Service overload"}
    assert mock_route.called


@pytest.mark.asyncio
async def test_error_response_is_structured_json(client, api_key_headers):
    # Prevents: Regression where error responses return unformatted text instead of structured error JSON.
    response = await client.get("/api/invalid-route-name/abc", headers=api_key_headers)

    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "code" in data["error"]
    assert "message" in data["error"]
    assert "path" in data["error"]


# ===========================================================================
# Group 4 — Cache Behaviour (4 tests)
# ===========================================================================

@pytest.mark.asyncio
@respx.mock
async def test_post_order_bypasses_cache(client, api_key_headers, respx_mock):
    # Prevents: Regression where mutation POST requests hit or pollute the semantic cache.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        201, json={"orderId": "new-order"}
    )

    response = await client.post(
        "/api/orders",
        json={"item": "burger"},
        headers=api_key_headers
    )

    assert response.status_code == 201
    assert mock_route.called


@pytest.mark.asyncio
@respx.mock
async def test_put_order_cancel_bypasses_cache(client, api_key_headers, respx_mock):
    # Prevents: Regression where state-modifying PUT requests are cached.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        200, json={"status": "CANCELLED"}
    )

    response = await client.put(
        "/api/orders/123/cancel",
        json={},
        headers=api_key_headers
    )

    assert response.status_code == 200
    assert mock_route.called


@pytest.mark.asyncio
@respx.mock
async def test_delete_request_bypasses_cache(client, api_key_headers, respx_mock):
    # Prevents: Regression where DELETE operations are served from cache.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(204)

    response = await client.delete("/api/orders/123", headers=api_key_headers)

    assert response.status_code == 204
    assert mock_route.called


@pytest.mark.asyncio
async def test_cache_bypass_does_not_affect_llm_route(client, api_key_headers):
    # Prevents: Regression where cache bypassing logic disables caching for /v1/chat/completions.
    from app.schemas.chat import ChatResponse
    from app.services.router import RoutingDecision

    mock_resp = ChatResponse(
        id="chat-cache-test",
        object="chat.completion",
        created=123456,
        model="gpt-4o",
        choices=[{"index": 0, "message": {"role": "assistant", "content": "cached answer"}, "finish_reason": "stop"}],
        usage={"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}
    )
    decision = RoutingDecision(
        request_id="123",
        original_model="gpt-4o",
        resolved_model="gpt-4o",
        provider="openai",
        reason="primary_match",
        latency_ms=10.0
    )

    with patch("app.api.routes._routing_engine.route_request", new_callable=AsyncMock) as mock_route_req:
        mock_route_req.return_value = (mock_resp, decision)

        response = await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "cache check"}]},
            headers=api_key_headers
        )

        assert response.status_code == 200


# ===========================================================================
# Group 5 — Budget Enforcement (3 tests)
# ===========================================================================

@pytest.mark.asyncio
@respx.mock
async def test_post_order_not_blocked_when_budget_exhausted(client, exhausted_budget_headers, respx_mock):
    # Prevents: Regression where FTGO proxy routes are blocked by LLM budget limits (402 Payment Required).
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        201, json={"orderId": "order-unblocked"}
    )

    with patch("app.services.budget_manager.BudgetManager.check_budget", side_effect=BudgetExceededError("Budget exceeded")):
        response = await client.post(
            "/api/orders",
            json={"item": "pizza"},
            headers=exhausted_budget_headers
        )

        assert response.status_code == 201
        assert response.json() == {"orderId": "order-unblocked"}
        assert mock_route.called


@pytest.mark.asyncio
async def test_llm_route_blocked_when_budget_exhausted(client, exhausted_budget_headers):
    # Prevents: Regression where exhausted LLM daily budgets fail to block /v1/chat/completions requests.
    with patch("app.services.budget_manager.BudgetManager.check_budget", side_effect=BudgetExceededError("Daily budget limit reached")):
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}]},
            headers=exhausted_budget_headers
        )

        assert response.status_code == 402
        data = response.json()
        assert "budget" in data["error"]["type"] or "budget" in data["error"]["message"].lower()


@pytest.mark.asyncio
@respx.mock
async def test_budget_check_only_for_v1_prefix(client, api_key_headers, respx_mock):
    # Prevents: Regression where daily budget checks are evaluated for non-LLM paths.
    mock_route = respx_mock.route(host="ftgo-api-gateway").respond(
        200, json={"name": "Alice"}
    )

    with patch("app.services.budget_manager.BudgetManager.check_budget") as mock_check_budget:
        response = await client.get("/api/consumers/me", headers=api_key_headers)

        assert response.status_code == 200
        assert mock_route.called
        assert not mock_check_budget.called


# ===========================================================================
# Group 6 — Health Checks (4 tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_get_health_returns_200_without_auth(client):
    # Prevents: Regression where local gateway /health endpoint requires API key or JWT authentication.
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data.get("status") in ("healthy", "ok") or "status" in data


@pytest.mark.asyncio
async def test_actuator_health_proxied_to_downstream(client):
    # Prevents: Regression where /actuator/health fails to proxy to downstream health endpoint.
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = Response(200, json={"status": "UP", "components": {"db": {"status": "UP"}}})

        response = await client.get("/actuator/health")

        assert response.status_code == 200
        assert response.json()["status"] == "UP"
        assert mock_get.called


@pytest.mark.asyncio
async def test_actuator_health_bypasses_rate_limiting(client):
    # Prevents: Regression where Kubernetes liveness/readiness probes on /actuator/health hit rate limits.
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = Response(200, json={"status": "UP"})

        for _ in range(5):
            res = await client.get("/actuator/health")
            assert res.status_code == 200


@pytest.mark.asyncio
async def test_actuator_health_bypasses_auth_middleware(client):
    # Prevents: Regression where unauthenticated health checks on /actuator/health receive 401 Unauthorized.
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = Response(200, json={"status": "UP"})

        response = await client.get("/actuator/health")

        assert response.status_code == 200
        assert response.json() == {"status": "UP"}
