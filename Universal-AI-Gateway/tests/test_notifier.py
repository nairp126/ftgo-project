"""
Unit tests for webhook notifications service.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import uuid
from decimal import Decimal

from app.services.notifier import Notifier, get_notifier


@pytest.mark.asyncio
@patch("app.services.notifier.httpx.AsyncClient")
async def test_notifier_successful_notification(mock_client_class):
    """Verify notify executes successfully when a webhook is configured."""
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_client.post.return_value = mock_resp
    mock_client_class.return_value = mock_client

    notifier = Notifier()
    notifier.webhook_url = "https://example.com/webhook"

    tenant_id = uuid.uuid4()
    extra_data = {
        "tenant_id": tenant_id,
        "spend": Decimal("85.50"),
        "limit": Decimal("100.00")
    }

    # This will trigger clean_data, converting uuid and Decimal to string.
    # It will also log using alert_type (which was previously event_type causing NameError).
    await notifier.notify("BUDGET_WARNING", "Tenant budget high", extra_data)

    mock_client.post.assert_called_once()
    # Check payload serialization
    called_args = mock_client.post.call_args[1]
    payload = called_args["json"]
    assert payload["type"] == "BUDGET_WARNING"
    assert payload["message"] == "Tenant budget high"
    assert payload["data"]["tenant_id"] == str(tenant_id)
    assert payload["data"]["spend"] == "85.50"
    assert payload["data"]["limit"] == "100.00"

    await notifier.close()


class MagicMock(MagicMock):
    """Helper to mock async support if needed."""
    pass
