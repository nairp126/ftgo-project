import os
os.environ["JWT_SECRET_KEY"] = "test-secret-key-123-test-secret-key-123"
os.environ["OTEL_SDK_DISABLED"] = "true"

import pytest
import pytest_asyncio
import jwt
import respx
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport

from app.main import app as fastapi_app
from app.api.dependencies import authenticate_api_key

JWT_SECRET = "test-secret-key-123-test-secret-key-123"


class FakeRedisClient:
    def __init__(self):
        self._data = {}

    async def get(self, key):
        return self._data.get(key)
        
    async def set(self, key, value, *args, **kwargs):
        self._data[key] = str(value)
        
    async def incr(self, key):
        val = int(self._data.get(key, "0")) + 1
        self._data[key] = str(val)
        return val
        
    async def incrbyfloat(self, key, amount):
        val = float(self._data.get(key, "0.0")) + float(amount)
        self._data[key] = str(val)
        return val
        
    async def delete(self, key):
        if key in self._data:
            del self._data[key]
            
    async def ping(self):
        return True


@pytest.fixture(autouse=True)
def mock_redis_globally():
    client = FakeRedisClient()
    with patch("app.cache.redis.redis_manager.get_client", return_value=client):
        yield client


@pytest.fixture(autouse=True)
def reset_proxy_client():
    import app.services.proxy as proxy_module
    proxy_module._client = None
    yield
    proxy_module._client = None


@pytest.fixture
def app():
    return fastapi_app


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def api_key_headers():
    return {"Authorization": "Bearer test-api-key-123"}


@pytest.fixture
def jwt_headers():
    payload = {
        "sub": "user-123",
        "tenant_id": "tenant-abc",
        "roles": ["user"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def exhausted_budget_headers():
    return {"Authorization": "Bearer exhausted-tenant-key", "X-Tenant-ID": "tenant-exhausted"}
