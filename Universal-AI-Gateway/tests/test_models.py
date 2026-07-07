"""
Tests for database models — validates SQLAlchemy model metadata in-memory.
No running database required; tests inspect the ORM model definitions directly.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import inspect

# Import Base (which triggers model registration via the models import in database.py)
from app.db.database import Base
from app.db.models import Tenant, APIKey, RequestLog


class TestModelRegistration:
    """Verify all models register with Base.metadata."""

    def test_all_tables_registered(self):
        table_names = set(Base.metadata.tables.keys())
        assert "tenants" in table_names
        assert "api_keys" in table_names
        assert "request_logs" in table_names

    def test_exactly_three_tables(self):
        assert len(Base.metadata.tables) == 3


class TestTenantModel:
    """Verify Tenant model schema matches design spec."""

    def test_table_name(self):
        assert Tenant.__tablename__ == "tenants"

    def test_columns_exist(self):
        columns = {c.name for c in Tenant.__table__.columns}
        expected = {"id", "name", "description", "is_active", "created_at", "updated_at"}
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_id_is_uuid(self):
        col = Tenant.__table__.c.id
        assert col.primary_key
        assert "UUID" in str(col.type).upper()

    def test_name_is_unique(self):
        col = Tenant.__table__.c.name
        assert col.unique

    def test_default_is_active(self):
        col = Tenant.__table__.c.is_active
        assert col.default is not None or col.server_default is not None


class TestAPIKeyModel:
    """Verify APIKey model schema matches design spec."""

    def test_table_name(self):
        assert APIKey.__tablename__ == "api_keys"

    def test_columns_exist(self):
        columns = {c.name for c in APIKey.__table__.columns}
        expected = {
            "id", "tenant_id", "key_prefix", "key_hash", "name",
            "rate_limit_per_minute", "daily_cost_limit", "allowed_models",
            "is_active", "created_at", "last_used_at", "expires_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_id_is_uuid(self):
        col = APIKey.__table__.c.id
        assert col.primary_key
        assert "UUID" in str(col.type).upper()

    def test_tenant_id_foreign_key(self):
        col = APIKey.__table__.c.tenant_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "tenants.id" in fk_targets

    def test_key_hash_not_nullable(self):
        col = APIKey.__table__.c.key_hash
        assert not col.nullable

    def test_key_prefix_indexed(self):
        col = APIKey.__table__.c.key_prefix
        assert col.index

    def test_daily_cost_limit_is_decimal(self):
        col = APIKey.__table__.c.daily_cost_limit
        assert "NUMERIC" in str(col.type).upper()

    def test_allowed_models_is_json(self):
        col = APIKey.__table__.c.allowed_models
        assert "JSON" in str(col.type).upper()

    def test_rate_limit_default(self):
        col = APIKey.__table__.c.rate_limit_per_minute
        assert col.default is not None or col.server_default is not None


class TestRequestLogModel:
    """Verify RequestLog model schema matches design spec."""

    def test_table_name(self):
        assert RequestLog.__tablename__ == "request_logs"

    def test_columns_exist(self):
        columns = {c.name for c in RequestLog.__table__.columns}
        expected = {
            "id", "request_id", "api_key_id", "tenant_id",
            "model", "provider", "endpoint",
            "prompt_tokens", "completion_tokens", "total_tokens",
            "latency_ms", "cache_status", "cost_usd",
            "status_code", "error_type", "error_message",
            "routing_tags", "routing_decision", "created_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_id_is_uuid(self):
        col = RequestLog.__table__.c.id
        assert col.primary_key
        assert "UUID" in str(col.type).upper()

    def test_request_id_unique(self):
        col = RequestLog.__table__.c.request_id
        assert col.unique

    def test_api_key_id_foreign_key(self):
        col = RequestLog.__table__.c.api_key_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "api_keys.id" in fk_targets

    def test_tenant_id_foreign_key(self):
        col = RequestLog.__table__.c.tenant_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "tenants.id" in fk_targets

    def test_cost_usd_precision(self):
        col = RequestLog.__table__.c.cost_usd
        assert "NUMERIC" in str(col.type).upper()

    def test_routing_fields_are_json(self):
        for name in ("routing_tags", "routing_decision"):
            col = RequestLog.__table__.c[name]
            assert "JSON" in str(col.type).upper(), f"{name} should be JSON"

    def test_composite_indexes_exist(self):
        """Verify composite indexes for analytics query patterns."""
        index_names = {idx.name for idx in RequestLog.__table__.indexes}
        assert "ix_request_logs_tenant_created" in index_names
        assert "ix_request_logs_model_created" in index_names
        assert "ix_request_logs_provider_created" in index_names

    def test_cache_status_default(self):
        col = RequestLog.__table__.c.cache_status
        assert col.default is not None or col.server_default is not None


class TestRelationships:
    """Verify FK relationships between models."""

    def test_tenant_has_api_keys_relationship(self):
        mapper = inspect(Tenant)
        rel_names = [r.key for r in mapper.relationships]
        assert "api_keys" in rel_names

    def test_tenant_has_request_logs_relationship(self):
        mapper = inspect(Tenant)
        rel_names = [r.key for r in mapper.relationships]
        assert "request_logs" in rel_names

    def test_api_key_has_tenant_relationship(self):
        mapper = inspect(APIKey)
        rel_names = [r.key for r in mapper.relationships]
        assert "tenant" in rel_names

    def test_api_key_has_request_logs_relationship(self):
        mapper = inspect(APIKey)
        rel_names = [r.key for r in mapper.relationships]
        assert "request_logs" in rel_names

    def test_request_log_has_api_key_relationship(self):
        mapper = inspect(RequestLog)
        rel_names = [r.key for r in mapper.relationships]
        assert "api_key" in rel_names

    def test_request_log_has_tenant_relationship(self):
        mapper = inspect(RequestLog)
        rel_names = [r.key for r in mapper.relationships]
        assert "tenant" in rel_names


class TestUUIDDefaults:
    """Verify UUID default generation is configured correctly."""

    def _assert_uuid4_default(self, col, model_name):
        """Assert that a column has a uuid4 callable as its default."""
        assert col.default is not None, f"{model_name}.id should have a default"
        assert callable(col.default.arg), f"{model_name}.id default should be callable"
        assert col.default.arg.__name__ == "uuid4", (
            f"{model_name}.id default should be uuid4, got {col.default.arg.__name__}"
        )

    def test_tenant_default_id(self):
        self._assert_uuid4_default(Tenant.__table__.c.id, "Tenant")

    def test_api_key_default_id(self):
        self._assert_uuid4_default(APIKey.__table__.c.id, "APIKey")

    def test_request_log_default_id(self):
        self._assert_uuid4_default(RequestLog.__table__.c.id, "RequestLog")
