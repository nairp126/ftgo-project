"""
Redis connection setup with connection pooling.
Supports Requirements 14.2, 14.4 for cache connectivity and connection pooling.
"""

from typing import Optional, Any
import json
import logging
from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import RedisError, ConnectionError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Redis connection manager with connection pooling"""
    
    def __init__(self):
        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None
        self._settings = get_settings()
    
    def create_pool(self) -> ConnectionPool:
        """Create Redis connection pool"""
        if self._pool is None:
            self._pool = ConnectionPool(
                host=self._settings.redis.host,
                port=self._settings.redis.port,
                password=self._settings.redis.password,
                db=self._settings.redis.db,
                max_connections=self._settings.redis.pool_size,
                socket_timeout=self._settings.redis.socket_timeout,
                socket_connect_timeout=self._settings.redis.socket_connect_timeout,
                decode_responses=True,  # Automatically decode responses to strings
                retry_on_timeout=True,
                health_check_interval=30,  # Health check every 30 seconds
            )
            logger.info(
                f"Created Redis connection pool with max_connections={self._settings.redis.pool_size}"
            )
        return self._pool
    
    def get_client(self) -> Redis:
        """Get Redis client with connection pooling"""
        if self._client is None:
            pool = self.create_pool()
            self._client = Redis(connection_pool=pool)
            logger.info("Created Redis client")
        return self._client
    
    async def close(self):
        """Close Redis connections"""
        if self._client:
            await self._client.close()
            logger.info("Redis connections closed")
        if self._pool:
            await self._pool.disconnect()
    
    async def health_check(self) -> bool:
        """Check Redis connectivity"""
        try:
            client = self.get_client()
            await client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        try:
            client = self.get_client()
            return await client.get(key)
        except RedisError as e:
            logger.error(f"Redis GET failed for key {key}: {e}")
            return None
    
    async def set(
        self, 
        key: str, 
        value: str, 
        ttl: Optional[int] = None
    ) -> bool:
        """Set value in Redis with optional TTL"""
        try:
            client = self.get_client()
            if ttl:
                return await client.setex(key, ttl, value)
            else:
                return await client.set(key, value)
        except RedisError as e:
            logger.error(f"Redis SET failed for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis"""
        try:
            client = self.get_client()
            result = await client.delete(key)
            return result > 0
        except RedisError as e:
            logger.error(f"Redis DELETE failed for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis"""
        try:
            client = self.get_client()
            return await client.exists(key) > 0
        except RedisError as e:
            logger.error(f"Redis EXISTS failed for key {key}: {e}")
            return False
    
    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment key value in Redis"""
        try:
            client = self.get_client()
            return await client.incr(key, amount)
        except RedisError as e:
            logger.error(f"Redis INCR failed for key {key}: {e}")
            return None
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL for existing key"""
        try:
            client = self.get_client()
            return await client.expire(key, ttl)
        except RedisError as e:
            logger.error(f"Redis EXPIRE failed for key {key}: {e}")
            return False
    
    async def get_json(self, key: str) -> Optional[Any]:
        """Get JSON value from Redis"""
        value = await self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON for key {key}: {e}")
            return None
    
    async def set_json(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """Set JSON value in Redis"""
        try:
            json_value = json.dumps(value)
            return await self.set(key, json_value, ttl)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to encode JSON for key {key}: {e}")
            return False


# Global Redis manager instance
redis_manager = RedisManager()


def get_redis() -> Redis:
    """Dependency for getting Redis client"""
    return redis_manager.get_client()


async def init_redis():
    """Initialize Redis connection"""
    try:
        client = redis_manager.get_client()
        await client.ping()
        logger.info("Redis initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")
        raise


async def close_redis():
    """Close Redis connections"""
    await redis_manager.close()