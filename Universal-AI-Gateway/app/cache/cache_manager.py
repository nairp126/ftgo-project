"""
Cache manager for exact-match LLM response caching.
Supports Requirements 5.1–5.8.

Uses the existing RedisManager for Redis connectivity and builds
caching logic (key generation, TTL, size enforcement, bypass) on top.
"""

import hashlib
import json
import logging
import sys
import time
from typing import Any, Dict, Optional
import struct
import uuid

from app.cache.redis import RedisManager, redis_manager
from app.core.config import get_settings
from fastapi import Request
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.embeddings import get_embedding

logger = logging.getLogger(__name__)

# 1 MB size limit for cached entries (Requirement 5.8)
MAX_CACHE_ENTRY_BYTES = 1_048_576

# Default TTL: 24 hours (Requirement 5.3)
DEFAULT_TTL_SECONDS = 86_400

# Redis key prefix for cache entries
CACHE_KEY_PREFIX = "cache:exact:"


def generate_cache_key(request: ChatRequest) -> str:
    """
    Generate a deterministic SHA-256 cache key from request parameters.

    Key components (Requirement 5.1):
      - model
      - messages (JSON-serialized with sorted keys for determinism)
      - temperature
      - max_tokens
      - top_p

    Returns:
        Full Redis key like ``cache:exact:<sha256_hex>``
    """
    messages_data = [m.model_dump() for m in request.messages]

    key_components = [
        request.model,
        json.dumps(messages_data, sort_keys=True, ensure_ascii=True),
        str(request.temperature),
        str(request.max_tokens),
        str(request.top_p) if request.top_p is not None else "none",
    ]

    raw = "|".join(key_components)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{CACHE_KEY_PREFIX}{digest}"


class CacheManager:
    """
    Exact-match response cache backed by Redis.

    Wraps :class:`RedisManager` to provide:
    - Deterministic cache key generation (SHA-256)
    - JSON serialisation / deserialisation of ``ChatResponse``
    - Configurable TTL (default 24 h)
    - 1 MB per-entry size limit
    - ``no-cache`` header bypass
    - Hit / miss / bypass counters for metrics
    """

    def __init__(self, redis: Optional[RedisManager] = None):
        self._redis = redis or redis_manager
        self._settings = get_settings()
        self._hits = 0
        self._misses = 0
        self._bypasses = 0
        self._semantic_index_created = False

    async def _init_semantic_index(self):
        """Idempotently initialize the RediSearch index for the semantic cache cache."""
        if self._semantic_index_created:
            return
            
        try:
            client = self._redis.get_client()
            # Check if index exists
            try:
                await client.execute_command("FT.INFO", "idx:semantic")
                self._semantic_index_created = True
                return
            except Exception:
                pass # Index does not exist
            
            # Create HNSW Vector Index on HASHes prefixed with "cache:semantic:"
            dim = self._settings.cache.semantic_cache_dimension
            await client.execute_command(
                "FT.CREATE", "idx:semantic", 
                "ON", "HASH", 
                "PREFIX", "1", "cache:semantic:", 
                "SCHEMA", 
                "model", "TAG",
                "embedding", "VECTOR", "HNSW", "6", "TYPE", "FLOAT32", "DIM", str(dim), "DISTANCE_METRIC", "COSINE"
            )
            self._semantic_index_created = True
            logger.info("Semantic cache RediSearch vector index generated.")
        except Exception as e:
            logger.error(f"Failed to initialize semantic index: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get(self, key: str, request: Optional[ChatRequest] = None) -> Optional[ChatResponse]:
        """
        Retrieve a cached response (Exact Match fallback to Semantic Match).

        Returns:
            ``ChatResponse`` on cache hit, ``None`` on miss.
        """
        # Exact match
        raw = await self._redis.get(key)
        if raw is not None:
            try:
                data = json.loads(raw)
                self._hits += 1
                return ChatResponse(**data)
            except (json.JSONDecodeError, Exception) as exc:
                logger.warning("Failed to deserialize exact cache entry %s: %s", key, exc)

        # Semantic fallback (Requirement R7-3)
        if request and self._settings.cache.semantic_cache_enabled:
            await self._init_semantic_index()
            try:
                # Combine all messages to infer intent
                prompt_text = "\n".join([m.content for m in request.messages])
                prompt_embedding = await get_embedding(prompt_text)
                
                if prompt_embedding:
                    client = self._redis.get_client()
                    
                    # Pack floats as binary for Redis
                    query_vec = struct.pack(f"{len(prompt_embedding)}f", *prompt_embedding)
                    
                    # Search vectors
                    # Query: "@model:{model_name} => [KNN 1 @embedding $vec AS score]"
                    # Use double quotes around model name in TAG field to handle hyphens
                    query = f'@model:{{ "{request.model}" }} => [KNN 1 @embedding $vec AS score]'
                    
                    res = await client.execute_command(
                        "FT.SEARCH", "idx:semantic", query, 
                        "PARAMS", "2", "vec", query_vec, 
                        "DIALECT", "2",
                        "RETURN", "2", "score", "response"
                    )
                    
                    # The RediSearch response format for FT.SEARCH looks like:
                    # [count, key1, [key-val array], key2, [key-val array], ...]
                    if res and res[0] > 0:
                        attributes = res[2]
                        # Parse attributes pairing [k1, v1, k2, v2...]
                        # attributes[i] and attributes[i+1] are already strings due to decode_responses=True
                        attr_map = {attributes[i]: attributes[i+1] for i in range(0, len(attributes), 2)}
                        
                        score = float(attr_map.get("score", 1.0))
                        
                        # Cosine distance < 1 - threshold
                        threshold = self._settings.cache.semantic_cache_threshold
                        if score < (1.0 - threshold):
                            raw_response = attr_map.get("response")
                            if raw_response:
                                data = json.loads(raw_response)
                                self._hits += 1
                                logger.info(f"Semantic Cache Hit! Confidence Distance: {score}")
                                return ChatResponse(**data)
                            
            except Exception as e:
                logger.error(f"Semantic cache lookup failed: {e}")

        self._misses += 1
        return None



    async def set(
        self,
        key: str,
        response: ChatResponse,
        ttl: Optional[int] = None,
        request: Optional[ChatRequest] = None
    ) -> bool:
        """
        Store a response in the cache.

        Args:
            key: Cache key (from ``generate_cache_key``).
            response: The ``ChatResponse`` to cache.
            ttl: Time-to-live in seconds.  Defaults to 24 hours.
            request: Providing ChatRequest triggers Semantic index caching if enabled.

        Returns:
            ``True`` if stored, ``False`` if rejected (e.g. too large).
        """
        ttl = ttl if ttl is not None else DEFAULT_TTL_SECONDS

        payload = response.model_dump_json()

        # Enforce 1 MB size limit (Requirement 5.8)
        encoded_payload_len = len(payload.encode("utf-8"))
        if encoded_payload_len > MAX_CACHE_ENTRY_BYTES:
            logger.warning(
                "Cache entry for %s exceeds 1 MB limit (%d bytes); skipping.",
                key,
                encoded_payload_len,
            )
            return False

        success = await self._redis.set(key, payload, ttl=ttl)
        
        # Populate semantic cache asynchronously
        if success and request and self._settings.cache.semantic_cache_enabled:
            import asyncio
            task = asyncio.create_task(self._set_semantic(request, response, ttl))
            task.add_done_callback(
                lambda t: logger.error("Semantic cache background task failed: %s", t.exception())
                if not t.cancelled() and t.exception() else None
            )
            
        return success
        
    async def _set_semantic(self, request: ChatRequest, response: ChatResponse, ttl: int):
        """Background coroutine to populate the vector search index."""
        try:
            await self._init_semantic_index()
            prompt_text = "\n".join([m.content for m in request.messages])
            prompt_embedding = await get_embedding(prompt_text)
            
            if prompt_embedding:
                client = self._redis.get_client()
                semantic_key = f"cache:semantic:{uuid.uuid4()}"
                
                query_vec = struct.pack(f"{len(prompt_embedding)}f", *prompt_embedding)
                payload = response.model_dump_json()
                
                # HSET
                await client.hset(semantic_key, mapping={
                    "model": request.model,
                    "embedding": query_vec,
                    "response": payload
                })
                # Set TTL
                await client.expire(semantic_key, ttl)
        except Exception as e:
            logger.error(f"Failed to populate semantic cache entry: {e}")

    async def invalidate(self, pattern: str) -> int:
        """
        Invalidate cache entries matching a glob *pattern*.

        Uses ``SCAN`` + ``DELETE`` to avoid blocking Redis with ``KEYS``.

        Returns:
            Number of keys deleted.
        """
        try:
            client = self._redis.get_client()
            deleted = 0
            async for key in client.scan_iter(match=pattern, count=100):
                await client.delete(key)
                deleted += 1
            return deleted
        except Exception as exc:
            logger.error("Cache invalidation failed for pattern %s: %s", pattern, exc)
            return 0

    @staticmethod
    def should_bypass(request: Request) -> bool:
        """
        Check whether the request should bypass the cache.

        Bypass conditions (Requirement 5.4):
        - Request method is not GET or HEAD (unless it is /v1/chat/completions)
        - ``Cache-Control: no-cache``
        - ``X-Cache-Bypass: true``
        """
        # Return True immediately if not GET/HEAD and not /v1/chat/completions
        if request.method not in ("GET", "HEAD") and request.url.path != "/v1/chat/completions":
            return True

        headers = request.headers
        if not headers:
            return False

        # Normalise header names to lowercase for case-insensitive lookup
        lower = {k.lower(): v for k, v in headers.items()}

        if lower.get("cache-control", "").lower() == "no-cache":
            return True
        if lower.get("x-cache-bypass", "").lower() == "true":
            return True

        return False

    def record_bypass(self) -> None:
        """Increment the bypass counter (called by the endpoint layer)."""
        self._bypasses += 1

    def get_stats(self) -> Dict[str, Any]:
        """Return cache hit / miss / bypass counters."""
        total = self._hits + self._misses + self._bypasses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "bypasses": self._bypasses,
            "total": total,
            "hit_rate": round(self._hits / total, 4) if total else 0.0,
        }

    def reset_stats(self) -> None:
        """Reset counters (useful for testing)."""
        self._hits = 0
        self._misses = 0
        self._bypasses = 0
