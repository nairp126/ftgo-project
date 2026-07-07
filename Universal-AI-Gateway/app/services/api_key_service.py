"""
API Key generation and validation service.
Supports Requirements 2.1 (key generation), 2.2 (validation),
2.6 (Argon2 hashing), and 13.5 (secure storage).
"""

import secrets
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db.models import APIKey

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class APIKeyService:
    """
    Service for generating, hashing, and validating API keys.

    Security model:
    - Raw API keys are generated using `secrets.token_urlsafe` (cryptographically secure)
    - Only the Argon2 hash is stored in the database — raw key is shown once at creation
    - The first 8 characters (key_prefix) are stored for identification/lookup
    - Validation compares the submitted key against the Argon2 hash
    """

    def __init__(self):
        settings = get_settings()
        self._hasher = PasswordHasher(
            time_cost=settings.security.argon2_time_cost,
            memory_cost=settings.security.argon2_memory_cost,
            parallelism=settings.security.argon2_parallelism,
        )
        self._key_length = settings.security.api_key_length

    def generate_api_key(self) -> str:
        """
        Generate a cryptographically secure API key.

        Returns a URL-safe token of at least 32 characters.
        The caller should store the hash (via hash_api_key) and show
        the raw key to the user exactly once.
        """
        # secrets.token_urlsafe produces ~1.3 chars per byte, so we over-allocate
        raw_key = secrets.token_urlsafe(self._key_length)
        logger.info(
            f"Generated new API key with prefix '{raw_key[:8]}...'",
            key_length=len(raw_key),
        )
        return raw_key

    def hash_api_key(self, raw_key: str) -> str:
        """
        Hash an API key using Argon2id for secure storage.

        Args:
            raw_key: The plaintext API key to hash.

        Returns:
            The Argon2 hash string (includes salt, params, and hash).
        """
        return self._hasher.hash(raw_key)

    def verify_api_key(self, raw_key: str, key_hash: str) -> bool:
        """
        Verify a raw API key against its Argon2 hash.

        Args:
            raw_key: The plaintext API key submitted by the client.
            key_hash: The stored Argon2 hash.

        Returns:
            True if the key matches, False otherwise.
        """
        try:
            return self._hasher.verify(key_hash, raw_key)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, key_hash: str) -> bool:
        """
        Check if a stored hash needs to be rehashed (e.g., after config change).

        Returns True if the hash parameters don't match current settings.
        """
        return self._hasher.check_needs_rehash(key_hash)

    @staticmethod
    def extract_prefix(raw_key: str) -> str:
        """
        Extract the first 8 characters of an API key for identification.

        The prefix is stored alongside the hash for quick lookup
        without needing to hash-compare against every key.
        """
        return raw_key[:8]

    def create_key_data(
        self,
        tenant_id: uuid.UUID,
        name: str,
        rate_limit_per_minute: int = 60,
        daily_cost_limit: Optional[Decimal] = None,
        allowed_models: Optional[List[str]] = None,
    ) -> dict:
        """
        Generate a new API key and return all data needed to create the DB record.

        Returns:
            dict with keys:
              - raw_key: The plaintext key (show to user once, never store)
              - key_prefix: First 8 chars for identification
              - key_hash: Argon2 hash for storage
              - tenant_id, name, rate_limit_per_minute, daily_cost_limit, allowed_models
        """
        raw_key = self.generate_api_key()
        return {
            "raw_key": raw_key,
            "key_prefix": self.extract_prefix(raw_key),
            "key_hash": self.hash_api_key(raw_key),
            "tenant_id": tenant_id,
            "name": name,
            "rate_limit_per_minute": rate_limit_per_minute,
            "daily_cost_limit": daily_cost_limit,
            "allowed_models": allowed_models or [],
        }

    async def create_key(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        name: str,
        rate_limit_per_minute: int = 60,
        daily_cost_limit: Optional[Decimal] = None,
        allowed_models: Optional[List[str]] = None,
        expires_in_days: Optional[int] = None,
    ) -> Tuple[str, APIKey]:
        """Create a new API key in the database."""
        key_data = self.create_key_data(
            tenant_id=tenant_id,
            name=name,
            rate_limit_per_minute=rate_limit_per_minute,
            daily_cost_limit=daily_cost_limit,
            allowed_models=allowed_models,
        )
        
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            
        new_key = APIKey(
            tenant_id=key_data["tenant_id"],
            key_prefix=key_data["key_prefix"],
            key_hash=key_data["key_hash"],
            name=key_data["name"],
            rate_limit_per_minute=key_data["rate_limit_per_minute"],
            daily_cost_limit=key_data["daily_cost_limit"],
            allowed_models=key_data["allowed_models"],
            expires_at=expires_at,
        )
        
        db.add(new_key)
        await db.commit()
        await db.refresh(new_key)
        
        return key_data["raw_key"], new_key

    async def deactivate_key(self, db: AsyncSession, key_id: uuid.UUID) -> bool:
        """Deactivate an API key."""
        stmt = (
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(is_active=False)
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount > 0

    async def rotate_key(
        self,
        db: AsyncSession,
        key_id: uuid.UUID,
        expires_in_days: Optional[int] = None,
    ) -> Tuple[str, APIKey]:
        """
        Rotate an API key.
        Deactivates the old key and creates a new one with the same settings.
        """
        # 1. Fetch old key settings
        stmt = select(APIKey).where(APIKey.id == key_id)
        result = await db.execute(stmt)
        old_key = result.scalar_one_or_none()
        
        if not old_key:
            raise ValueError(f"API key {key_id} not found")
            
        # 2. Deactivate old key
        old_key.is_active = False
        
        # 3. Create new key with same settings
        raw_key, new_key = await self.create_key(
            db=db,
            tenant_id=old_key.tenant_id,
            name=f"{old_key.name} (Rotated)",
            rate_limit_per_minute=old_key.rate_limit_per_minute,
            daily_cost_limit=old_key.daily_cost_limit,
            allowed_models=old_key.allowed_models,
            expires_in_days=expires_in_days,
        )
        
        return raw_key, new_key


# Module-level singleton for convenience
_api_key_service: Optional[APIKeyService] = None


def get_api_key_service() -> APIKeyService:
    """Get the singleton APIKeyService instance."""
    global _api_key_service
    if _api_key_service is None:
        _api_key_service = APIKeyService()
    return _api_key_service
