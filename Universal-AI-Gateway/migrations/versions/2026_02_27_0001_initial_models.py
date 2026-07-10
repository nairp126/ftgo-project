"""
Initial database migration: Create tenants, api_keys, and request_logs tables.

Revision ID: 0001
Revises: None
Create Date: 2026-02-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === Tenants table ===
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # === API Keys table ===
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "key_prefix",
            sa.String(length=8),
            nullable=False,
            comment="First 8 characters of the API key for identification",
        ),
        sa.Column(
            "key_hash",
            sa.Text(),
            nullable=False,
            comment="Argon2-hashed API key — raw key is never stored",
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
            comment="Human-readable name for this API key",
        ),
        sa.Column(
            "rate_limit_per_minute",
            sa.Integer(),
            nullable=False,
            server_default="60",
            comment="Maximum requests per minute for this key",
        ),
        sa.Column(
            "daily_cost_limit",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
            comment="Maximum daily cost in USD (null = unlimited)",
        ),
        sa.Column(
            "allowed_models",
            sa.JSON(),
            nullable=False,
            server_default="[]",
            comment="List of model names this key is authorized to use (empty = all)",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of last successful request with this key",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Optional expiration date for key rotation support",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])

    # === Request Logs table ===
    op.create_table(
        "request_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "request_id",
            sa.String(length=36),
            nullable=False,
            comment="Correlation ID for request tracing",
        ),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "model",
            sa.String(length=100),
            nullable=False,
            comment="Requested model name",
        ),
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=False,
            comment="Provider that handled the request",
        ),
        sa.Column(
            "endpoint",
            sa.String(length=255),
            nullable=False,
            server_default="/v1/chat/completions",
            comment="API endpoint called",
        ),
        sa.Column(
            "prompt_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "completion_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "latency_ms",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Total request latency in ms",
        ),
        sa.Column(
            "cache_status",
            sa.String(length=10),
            nullable=False,
            server_default="MISS",
            comment="HIT, MISS, or BYPASS",
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=12, scale=8),
            nullable=False,
            server_default="0.00000000",
            comment="Calculated cost in USD",
        ),
        sa.Column(
            "status_code",
            sa.Integer(),
            nullable=False,
            server_default="200",
            comment="HTTP response status code",
        ),
        sa.Column(
            "error_type",
            sa.String(length=100),
            nullable=True,
            comment="Error type if request failed",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Error message if request failed",
        ),
        sa.Column(
            "routing_tags",
            sa.JSON(),
            nullable=True,
            comment="Tags provided by the client for routing",
        ),
        sa.Column(
            "routing_decision",
            sa.JSON(),
            nullable=True,
            comment="Routing engine decision details",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["api_key_id"], ["api_keys.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    # Indexes for common query patterns
    op.create_index("ix_request_logs_request_id", "request_logs", ["request_id"])
    op.create_index("ix_request_logs_api_key_id", "request_logs", ["api_key_id"])
    op.create_index("ix_request_logs_tenant_id", "request_logs", ["tenant_id"])
    op.create_index("ix_request_logs_created_at", "request_logs", ["created_at"])
    op.create_index(
        "ix_request_logs_tenant_created", "request_logs", ["tenant_id", "created_at"]
    )
    op.create_index(
        "ix_request_logs_model_created", "request_logs", ["model", "created_at"]
    )
    op.create_index(
        "ix_request_logs_provider_created",
        "request_logs",
        ["provider", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("request_logs")
    op.drop_table("api_keys")
    op.drop_table("tenants")
