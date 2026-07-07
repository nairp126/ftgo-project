import pytest
from unittest.mock import patch

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
