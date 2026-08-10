"""
Comprehensive request logging service.
Creates structured log entries for every gateway request, with PII redaction.
Supports Requirements 6.1, 6.2, 6.3, 6.4.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    import boto3
except ImportError:
    boto3 = None

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.services.pii_redactor import redact_pii
from app.db.models import RequestLog

logger = logging.getLogger(__name__)

# All required fields per Requirement 6.2
REQUIRED_LOG_FIELDS = frozenset({
    "request_id",
    "api_key_id",
    "timestamp",
    "model",
    "provider",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "latency_ms",
    "cost_usd",
    "cache_status",
    "error_status",
})


@dataclass
class RequestLogEntry:
    """Structured log entry for a single gateway request."""

    # Identity (Requirement 6.1 — UUID)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Auth context
    api_key_id: Optional[str] = None
    tenant_id: Optional[str] = None

    # Timing
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    latency_ms: float = 0.0

    # Request info
    model: str = ""
    provider: str = ""
    endpoint: str = "/v1/chat/completions"

    # Token counts
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    # Cost
    cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))

    # Cache
    cache_status: str = "MISS"  # HIT | MISS | BYPASS

    # Status
    status_code: int = 200
    error_status: Optional[str] = None
    error_message: Optional[str] = None

    # Routing
    routing_decision: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for storage / serialisation."""
        d = asdict(self)
        # Convert Decimal to string for JSON
        d["cost_usd"] = str(self.cost_usd)
        return d

    def has_required_fields(self) -> bool:
        """Check that all required fields are present in the dict."""
        d = self.to_dict()
        return all(f in d for f in REQUIRED_LOG_FIELDS)


class RequestLogger:
    """
    In-memory request logger with PII redaction.

    In production this would write to PostgreSQL (Requirement 6.3).
    The in-memory implementation enables full testing without a database.
    """

    def __init__(self):
        self._logs: List[RequestLogEntry] = []
        from app.db.database import db_manager
        self._session_factory = db_manager.create_session_factory()

    def create_entry(self, **kwargs) -> RequestLogEntry:
        """Create a new log entry with a fresh UUID."""
        entry = RequestLogEntry(**kwargs)
        return entry

    async def log_to_db(self, entry: RequestLogEntry):
        """Persist a log entry to PostgreSQL."""
        # Record log entry to DB (R1.1, 15.2)
        try:
            import uuid
            
            async with self._session_factory() as session:
                # Ensure we pass UUID objects for UUID columns and dicts for JSON columns
                db_entry = RequestLog(
                    id=uuid.uuid4(),
                    request_id=str(entry.request_id),
                    api_key_id=uuid.UUID(entry.api_key_id) if isinstance(entry.api_key_id, str) else entry.api_key_id,
                    tenant_id=uuid.UUID(entry.tenant_id) if isinstance(entry.tenant_id, str) else entry.tenant_id,
                    model=entry.model,
                    provider=entry.provider,
                    endpoint=entry.endpoint,
                    prompt_tokens=entry.prompt_tokens,
                    completion_tokens=entry.completion_tokens,
                    total_tokens=entry.total_tokens,
                    latency_ms=int(entry.latency_ms),
                    cost_usd=entry.cost_usd,
                    cache_status=entry.cache_status,
                    status_code=entry.status_code,
                    error_type=entry.error_status,
                    error_message=entry.error_message,
                    routing_decision=entry.routing_decision.to_dict() if hasattr(entry.routing_decision, "to_dict") else entry.routing_decision
                )
                session.add(db_entry)
                await session.commit()
        except Exception as e:
            logger.error("Failed to persist request log to DB: %s", e)
            # Don't re-raise; we don't want to break the request if logging fails

    def log(self, entry: RequestLogEntry) -> RequestLogEntry:
        """
        Persist a log entry to memory (with PII redaction).
        """
        if entry.error_message:
            entry.error_message = redact_pii(entry.error_message)

        self._logs.append(entry)
        logger.info(
            "Request logged (memory): id=%s model=%s provider=%s latency=%.1fms cost=%s",
            entry.request_id,
            entry.model,
            entry.provider,
            entry.latency_ms,
            entry.cost_usd,
        )
        return entry

    def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return recent logs as dicts (Requirement 6.5)."""
        return [e.to_dict() for e in self._logs[-limit:]]

    def get_log_by_id(self, request_id: str) -> Optional[RequestLogEntry]:
        """Find a log entry by request_id."""
        for entry in self._logs:
            if entry.request_id == request_id:
                return entry
        return None

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate logging statistics."""
        if not self._logs:
            return {"total": 0}

        total = len(self._logs)
        errors = sum(1 for e in self._logs if e.error_status)
        cache_hits = sum(1 for e in self._logs if e.cache_status == "HIT")
        total_cost = sum(e.cost_usd for e in self._logs)

        return {
            "total": total,
            "errors": errors,
            "error_rate": round(errors / total, 4),
            "cache_hits": cache_hits,
            "cache_hit_rate": round(cache_hits / total, 4),
            "total_cost_usd": str(total_cost),
        }

    def clear(self):
        """Clear all logs (useful for testing)."""
        self._logs.clear()

    def log_request(self, **kwargs) -> RequestLogEntry:
        """
        Sync convenience method for testing.
        """
        entry = self.create_entry(**kwargs)
        return self.log(entry)

    async def log_request_async(self, db: Optional[AsyncSession] = None, **kwargs) -> RequestLogEntry:
        """
        Async convenience method: create and persist a log entry (memory + DB if provided).
        """
        entry = self.create_entry(**kwargs)
        self.log(entry)
        if db:
            await self.log_to_db(entry)
        return entry

    def export_logs_to_s3(self) -> Dict[str, Any]:
        """
        Export current logs to AWS S3 (Requirement 6.6).
        Returns status dictionary.
        """
        if not self._logs:
            return {"status": "skipped", "message": "No logs to export"}
            
        settings = get_settings()
        bucket = settings.logging.s3_log_bucket
        
        if not bucket or not boto3:
            return {
                "status": "error", 
                "message": "S3 export not configured (missing bucket or boto3)"
            }
            
        try:
            # Configure boto3 client using existing provider AWS credentials
            s3 = boto3.client(
                's3',
                region_name=settings.providers.aws_region,
                aws_access_key_id=settings.providers.aws_access_key_id,
                aws_secret_access_key=settings.providers.aws_secret_access_key
            )
            
            # Create JSONL content
            jsonl_content = "\n".join(json.dumps(e.to_dict()) for e in self._logs)
            
            # Generate object key based on current timestamp
            timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d/%H%M%S")
            object_key = f"gateway_logs/{timestamp}_logs.jsonl"
            
            s3.put_object(
                Bucket=bucket,
                Key=object_key,
                Body=jsonl_content.encode('utf-8'),
                ContentType='application/x-ndjson'
            )
            
            count = len(self._logs)
            logger.info(f"Successfully exported {count} logs to s3://{bucket}/{object_key}")
            return {
                "status": "success", 
                "message": f"Exported {count} logs to S3",
                "object_key": object_key
            }
        except Exception as e:
            logger.error(f"Failed to export logs to S3: {str(e)}")
            return {"status": "error", "message": str(e)}
