"""
Tests for authentication and API key management.
Tests the API key service (generation, hashing, verification) in-memory.
"""

import uuid
from decimal import Decimal

import pytest

from app.services.api_key_service import APIKeyService, get_api_key_service
from app.api.dependencies import _extract_raw_key


class TestAPIKeyGeneration:
    """Tests for API key generation."""

    def setup_method(self):
        self.service = APIKeyService()

    def test_generated_key_is_string(self):
        key = self.service.generate_api_key()
        assert isinstance(key, str)

    def test_generated_key_minimum_length(self):
        """Requirement 2.1: at least 32 characters."""
        key = self.service.generate_api_key()
        assert len(key) >= 32, f"Key length {len(key)} is less than 32"

    def test_generated_keys_are_unique(self):
        keys = {self.service.generate_api_key() for _ in range(100)}
        assert len(keys) == 100, "Generated keys should be unique"

    def test_generated_key_is_url_safe(self):
        """Keys use secrets.token_urlsafe which produces URL-safe characters."""
        key = self.service.generate_api_key()
        # URL-safe base64 uses A-Z, a-z, 0-9, -, _
        import re
        assert re.match(r'^[A-Za-z0-9_-]+$', key), f"Key contains non-URL-safe chars: {key}"


class TestAPIKeyHashing:
    """Tests for Argon2 hashing."""

    def setup_method(self):
        self.service = APIKeyService()

    def test_hash_returns_string(self):
        key = self.service.generate_api_key()
        hash_value = self.service.hash_api_key(key)
        assert isinstance(hash_value, str)

    def test_hash_starts_with_argon2_prefix(self):
        """Requirement 2.6: Argon2 hashing."""
        key = self.service.generate_api_key()
        hash_value = self.service.hash_api_key(key)
        assert hash_value.startswith("$argon2"), f"Hash should start with $argon2: {hash_value[:20]}"

    def test_hash_is_not_the_raw_key(self):
        key = self.service.generate_api_key()
        hash_value = self.service.hash_api_key(key)
        assert hash_value != key

    def test_same_key_produces_different_hashes(self):
        """Argon2 uses a random salt, so same input → different hashes."""
        key = self.service.generate_api_key()
        hash1 = self.service.hash_api_key(key)
        hash2 = self.service.hash_api_key(key)
        assert hash1 != hash2, "Same key should produce different hashes (random salt)"


class TestAPIKeyVerification:
    """Tests for Argon2 verification."""

    def setup_method(self):
        self.service = APIKeyService()

    def test_valid_key_verifies(self):
        key = self.service.generate_api_key()
        hash_value = self.service.hash_api_key(key)
        assert self.service.verify_api_key(key, hash_value) is True

    def test_wrong_key_fails_verification(self):
        key = self.service.generate_api_key()
        hash_value = self.service.hash_api_key(key)
        wrong_key = self.service.generate_api_key()
        assert self.service.verify_api_key(wrong_key, hash_value) is False

    def test_empty_key_fails_verification(self):
        key = self.service.generate_api_key()
        hash_value = self.service.hash_api_key(key)
        assert self.service.verify_api_key("", hash_value) is False

    def test_malformed_hash_fails_verification(self):
        key = self.service.generate_api_key()
        assert self.service.verify_api_key(key, "not-a-valid-hash") is False

    def test_empty_hash_fails_verification(self):
        key = self.service.generate_api_key()
        assert self.service.verify_api_key(key, "") is False


class TestAPIKeyPrefix:
    """Tests for key prefix extraction."""

    def setup_method(self):
        self.service = APIKeyService()

    def test_prefix_length(self):
        key = self.service.generate_api_key()
        prefix = self.service.extract_prefix(key)
        assert len(prefix) == 8

    def test_prefix_matches_key_start(self):
        key = self.service.generate_api_key()
        prefix = self.service.extract_prefix(key)
        assert key.startswith(prefix)

    def test_same_key_same_prefix(self):
        key = self.service.generate_api_key()
        assert self.service.extract_prefix(key) == self.service.extract_prefix(key)


class TestCreateKeyData:
    """Tests for the create_key_data convenience method."""

    def setup_method(self):
        self.service = APIKeyService()
        self.tenant_id = uuid.uuid4()

    def test_returns_all_required_fields(self):
        data = self.service.create_key_data(
            tenant_id=self.tenant_id,
            name="test-key",
        )
        required_keys = {
            "raw_key", "key_prefix", "key_hash",
            "tenant_id", "name", "rate_limit_per_minute",
            "daily_cost_limit", "allowed_models",
        }
        assert required_keys == set(data.keys())

    def test_raw_key_is_valid(self):
        data = self.service.create_key_data(
            tenant_id=self.tenant_id, name="test"
        )
        assert len(data["raw_key"]) >= 32
        assert data["key_prefix"] == data["raw_key"][:8]

    def test_hash_verifies_against_raw_key(self):
        data = self.service.create_key_data(
            tenant_id=self.tenant_id, name="test"
        )
        assert self.service.verify_api_key(data["raw_key"], data["key_hash"])

    def test_default_rate_limit(self):
        data = self.service.create_key_data(
            tenant_id=self.tenant_id, name="test"
        )
        assert data["rate_limit_per_minute"] == 60

    def test_custom_rate_limit(self):
        data = self.service.create_key_data(
            tenant_id=self.tenant_id,
            name="test",
            rate_limit_per_minute=120,
        )
        assert data["rate_limit_per_minute"] == 120

    def test_default_allowed_models_is_empty(self):
        data = self.service.create_key_data(
            tenant_id=self.tenant_id, name="test"
        )
        assert data["allowed_models"] == []

    def test_custom_allowed_models(self):
        models = ["gpt-4o", "claude-3-5-sonnet"]
        data = self.service.create_key_data(
            tenant_id=self.tenant_id,
            name="test",
            allowed_models=models,
        )
        assert data["allowed_models"] == models

    def test_daily_cost_limit(self):
        data = self.service.create_key_data(
            tenant_id=self.tenant_id,
            name="test",
            daily_cost_limit=Decimal("10.50"),
        )
        assert data["daily_cost_limit"] == Decimal("10.50")

    def test_tenant_id_passed_through(self):
        data = self.service.create_key_data(
            tenant_id=self.tenant_id, name="test"
        )
        assert data["tenant_id"] == self.tenant_id


class TestNeedsRehash:
    """Tests for rehash detection."""

    def setup_method(self):
        self.service = APIKeyService()

    def test_fresh_hash_no_rehash(self):
        """A hash created with current settings should not need rehash."""
        key = self.service.generate_api_key()
        hash_value = self.service.hash_api_key(key)
        assert self.service.needs_rehash(hash_value) is False


class TestExtractRawKey:
    """Tests for the _extract_raw_key helper."""

    def test_bearer_token(self):
        result = _extract_raw_key("Bearer my-secret-key", None)
        assert result == "my-secret-key"

    def test_bearer_case_insensitive(self):
        result = _extract_raw_key("bearer my-secret-key", None)
        assert result == "my-secret-key"

    def test_x_api_key_header(self):
        result = _extract_raw_key(None, "my-secret-key")
        assert result == "my-secret-key"

    def test_bearer_takes_priority(self):
        result = _extract_raw_key("Bearer bearer-key", "x-api-key")
        assert result == "bearer-key"

    def test_no_headers_returns_none(self):
        result = _extract_raw_key(None, None)
        assert result is None

    def test_malformed_auth_header_returns_none(self):
        result = _extract_raw_key("InvalidFormat", None)
        assert result is None

    def test_empty_bearer_returns_none(self):
        """Auth header with just 'Bearer' and no key."""
        result = _extract_raw_key("Bearer", None)
        assert result is None

    def test_basic_auth_returns_none(self):
        """Basic auth should not be accepted."""
        result = _extract_raw_key("Basic base64string", None)
        assert result is None

    def test_malformed_auth_does_not_fall_through(self):
        """If Authorization is present but malformed, don't check X-API-Key."""
        result = _extract_raw_key("InvalidFormat", "fallback-key")
        assert result is None


class TestGetAPIKeyServiceSingleton:
    """Test the singleton getter."""

    def test_returns_instance(self):
        service = get_api_key_service()
        assert isinstance(service, APIKeyService)

    def test_returns_same_instance(self):
        s1 = get_api_key_service()
        s2 = get_api_key_service()
        assert s1 is s2
