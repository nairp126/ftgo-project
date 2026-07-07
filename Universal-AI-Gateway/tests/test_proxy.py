"""
Integration and regression tests for Phase 1 fixes:
1. GET /actuator/health proxying
"""

import pytest
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import get_settings


@pytest.fixture
def app_instance() -> FastAPI:
    from app.main import create_app
    return create_app()


@pytest.fixture
def test_client(app_instance) -> TestClient:
    return TestClient(app_instance, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /actuator/health Tests
# ---------------------------------------------------------------------------

def test_actuator_health_proxies_success(test_client):
    """
    GET /actuator/health should proxy to DOWNSTREAM_HEALTH_URL and return 200.
    It should bypass both authentication and rate-limiting.
    """
    settings = get_settings()
    downstream_url = settings.downstream_health_url

    mock_resp = httpx.Response(200, json={"status": "UP"})
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        response = test_client.get("/actuator/health")
        assert response.status_code == 200
        assert response.json() == {"status": "UP"}
        mock_get.assert_called_once_with(downstream_url)


def test_actuator_health_downstream_unavailable(test_client):
    """
    GET /actuator/health should return 503 if downstream is unreachable.
    """
    settings = get_settings()
    downstream_url = settings.downstream_health_url

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        response = test_client.get("/actuator/health")
        assert response.status_code == 503
        assert response.json() == {"status": "DOWNSTREAM_UNAVAILABLE"}
        mock_get.assert_called_once_with(downstream_url)
