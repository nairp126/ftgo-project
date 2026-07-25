"""
Webhook and notification service.
Supports Requirement 12 (Alerting and Monitoring).
"""

import json
import uuid
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Notifier:
    """
    Service for sending notifications to external systems (Webhooks, Slack, etc.).
    """

    def __init__(self):
        settings = get_settings()
        # We assume a general WEBHOOK_URL in environment for now, or per-tenant in future
        self.webhook_url = getattr(settings, "webhook_url", None)
        self._client = httpx.AsyncClient(timeout=10.0)

    async def notify(self, alert_type: str, message: str, extra_data: Optional[Dict[str, Any]] = None):
        """
        Send an alert notification via Webhook.
        Supports Requirement 4.5.
        """
        if not self.webhook_url:
            logger.debug("No webhook URL configured; skipping notification [%s]", alert_type)
            return

        # Prepare payload
        def clean_data(d):
            if isinstance(d, dict):
                return {k: clean_data(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [clean_data(v) for v in d]
            elif isinstance(d, (uuid.UUID, Decimal)):
                return str(d)
            return d

        payload = {
            "type": alert_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": clean_data(extra_data) if extra_data else {}
        }

        try:
            resp = await self._client.post(self.webhook_url, json=payload)
            resp.raise_for_status()
            logger.info(f"Notification sent successfully: {alert_type}")
        except Exception as e:
            logger.error(f"Failed to send notification [{alert_type}]: {e}")

    async def close(self):
        await self._client.aclose()


# Singleton
_notifier = Notifier()

def get_notifier() -> Notifier:
    return _notifier
