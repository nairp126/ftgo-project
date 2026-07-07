"""
Embeddings Service.
Converts text prompts into highly dimensional vector payloads (float lists)
so they can be queried using KNN similarity against a vector database.
"""

import httpx
from typing import List, Optional
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

class EmbeddingsService:
    """Singleton service for generating embeddings using a shared HTTP client."""
    
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        
    def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=5.0)
        return self._client
        
    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("Embeddings HTTP client closed")
            
    async def get_embedding(self, text: str, model: str = "text-embedding-3-small") -> Optional[List[float]]:
        settings = get_settings()
        api_key = settings.providers.openai_api_key
        
        if not api_key and not settings.mock_llm:
            logger.warning("No OPENAI_API_KEY provided; cannot generate embeddings for semantic cache.")
            return None

        if settings.mock_llm:
            dim = settings.cache.semantic_cache_dimension
            import hashlib
            h = hashlib.sha256(text.encode()).digest()
            seed_floats = [float(b) / 255.0 for b in h]
            multiplier = (dim // 32) + 1
            return (seed_floats * multiplier)[:dim]
            
        url = "https://api.openai.com/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": text,
            "model": model
        }
        
        try:
            client = self.get_client()
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Failed to generate embedding: {str(e)}")
            return None

_embeddings_service = EmbeddingsService()

def get_embeddings_service() -> EmbeddingsService:
    return _embeddings_service

async def get_embedding(text: str, model: str = "text-embedding-3-small") -> Optional[List[float]]:
    return await _embeddings_service.get_embedding(text, model)

async def close_embeddings_client():
    await _embeddings_service.close()
