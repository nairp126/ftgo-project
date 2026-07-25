"""
SQLAlchemy ORM models for the Universal LLM Gateway.
Supports Requirements 2.1, 2.6, 6.1, 6.2 for API key management and request logging.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    DateTime,
    Numeric,
    Text,
    ForeignKey,
    Index,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class Tenant(Base):
    """
    Multi-tenancy foundation model.
    Groups API keys and tracks usage per tenant organization.
    """

    __tablename__ = "tenants"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    api_keys = relationship("APIKey", back_populates="tenant", lazy="selectin")
    request_logs = relationship("RequestLog", back_populates="tenant", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name='{self.name}', active={self.is_active})>"


class APIKey(Base):
    """
    API key model with Argon2 hashing support.
    Supports Requirements 2.1 (key generation), 2.6 (Argon2 hashing),
    and 2.5 (rate limits and permissions per key).

    The raw API key is never stored — only the Argon2 hash.
    The key_prefix (first 8 chars) is stored for identification/lookup purposes.
    """

    __tablename__ = "api_keys"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key_prefix = Column(
        String(8),
        nullable=False,
        index=True,
        comment="First 8 characters of the API key for identification",
    )
    key_hash = Column(
        Text,
        nullable=False,
        comment="Argon2-hashed API key — raw key is never stored",
    )
    name = Column(
        String(255),
        nullable=False,
        comment="Human-readable name for this API key",
    )
    rate_limit_per_minute = Column(
        Integer,
        nullable=False,
        default=60,
        comment="Maximum requests per minute for this key",
    )
    daily_cost_limit = Column(
        Numeric(precision=10, scale=4),
        nullable=True,
        comment="Maximum daily cost in USD (null = unlimited)",
    )
    allowed_models = Column(
        JSON,
        nullable=False,
        default=list,
        comment="List of model names this key is authorized to use (empty = all)",
    )
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_used_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last successful request with this key",
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Optional expiration date for key rotation support",
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="api_keys")
    request_logs = relationship("RequestLog", back_populates="api_key", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<APIKey(id={self.id}, prefix='{self.key_prefix}...', "
            f"name='{self.name}', active={self.is_active})>"
        )


class RequestLog(Base):
    """
    Comprehensive request logging model for analytics, debugging, and billing.
    Supports Requirements 6.1 (UUID log entries), 6.2 (all required fields),
    and 6.3 (PostgreSQL storage).

    Designed for partitioning by created_at month for scalability.
    """

    __tablename__ = "request_logs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    request_id = Column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
        comment="Correlation ID for request tracing",
    )
    api_key_id = Column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Request metadata
    model = Column(String(100), nullable=False, comment="Requested model name")
    provider = Column(
        String(50), nullable=False, comment="Provider that handled the request"
    )
    endpoint = Column(
        String(255),
        nullable=False,
        default="/v1/chat/completions",
        comment="API endpoint called",
    )

    # Token usage
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)

    # Performance
    latency_ms = Column(
        Integer, nullable=False, default=0, comment="Total request latency in ms"
    )

    # Caching
    cache_status = Column(
        String(10),
        nullable=False,
        default="MISS",
        comment="HIT, MISS, or BYPASS",
    )

    # Cost
    cost_usd = Column(
        Numeric(precision=12, scale=8),
        nullable=False,
        default=Decimal("0.00000000"),
        comment="Calculated cost in USD",
    )

    # Response status
    status_code = Column(
        Integer, nullable=False, default=200, comment="HTTP response status code"
    )
    error_type = Column(
        String(100), nullable=True, comment="Error type if request failed"
    )
    error_message = Column(
        Text, nullable=True, comment="Error message if request failed"
    )

    # Routing metadata
    routing_tags = Column(
        JSON, nullable=True, comment="Tags provided by the client for routing"
    )
    routing_decision = Column(
        JSON,
        nullable=True,
        comment="Routing engine decision details (provider, reason, fallback info)",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    api_key = relationship("APIKey", back_populates="request_logs")
    tenant = relationship("Tenant", back_populates="request_logs")

    # Composite indexes for common query patterns
    __table_args__ = (
        Index("ix_request_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_request_logs_model_created", "model", "created_at"),
        Index("ix_request_logs_provider_created", "provider", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<RequestLog(id={self.id}, request_id='{self.request_id}', "
            f"model='{self.model}', provider='{self.provider}', "
            f"status={self.status_code})>"
        )
