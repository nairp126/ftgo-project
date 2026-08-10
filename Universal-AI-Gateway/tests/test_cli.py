"""
Unit tests for the Administrative CLI.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from typer.testing import CliRunner
import uuid

from app.cli import app
from app.db.models import Tenant, APIKey

runner = CliRunner()


def test_cli_help():
    """Verify CLI help command runs successfully."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Administrative CLI" in result.output


def test_cli_keys_help():
    """Verify keys subcommand help runs successfully."""
    result = runner.invoke(app, ["keys", "--help"])
    assert result.exit_code == 0
    assert "Manage client API keys" in result.output


@patch("app.cli.db_manager")
def test_cli_tenant_list_empty(mock_db_manager):
    """Verify tenant listing displays message when empty."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result
    
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_db_manager.create_session_factory.return_value = mock_session_factory

    result = runner.invoke(app, ["tenants", "list"])
    assert result.exit_code == 0
    assert "No tenants found" in result.output


@patch("app.cli.db_manager")
def test_cli_tenant_list_with_records(mock_db_manager):
    """Verify tenant listing prints table of records."""
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Enterprise Inc",
        description="Enterprise client",
        is_active=True
    )
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [tenant]
    mock_session.execute.return_value = mock_result
    
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_db_manager.create_session_factory.return_value = mock_session_factory

    result = runner.invoke(app, ["tenants", "list"])
    assert result.exit_code == 0
    assert "Enterprise Inc" in result.output
    assert "Yes" in result.output


@patch("app.cli.db_manager")
def test_cli_tenant_create(mock_db_manager):
    """Verify tenant creation writes record to database."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_db_manager.create_session_factory.return_value = mock_session_factory

    result = runner.invoke(app, ["tenants", "create", "-n", "New Tenant", "-d", "Brand new"])
    assert result.exit_code == 0
    assert "Tenant created" in result.output
    assert "New Tenant" in result.output


@patch("app.cli.db_manager")
@patch("app.cli.get_api_key_service")
def test_cli_key_create(mock_get_service, mock_db_manager):
    """Verify key creation generates and prints raw API key."""
    tenant_id = str(uuid.uuid4())
    
    # Mock tenant check to return a tenant (exists)
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = Tenant(id=uuid.UUID(tenant_id), name="Test Tenant")
    mock_session.execute.return_value = mock_result
    
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_db_manager.create_session_factory.return_value = mock_session_factory
    
    # Mock api key service
    mock_service = AsyncMock()
    mock_key = APIKey(
        id=uuid.uuid4(),
        tenant_id=uuid.UUID(tenant_id),
        key_prefix="prefix12",
        is_active=True
    )
    mock_service.create_key.return_value = ("raw_key_value_12345", mock_key)
    mock_get_service.return_value = mock_service

    result = runner.invoke(app, ["keys", "create", "-t", tenant_id, "-n", "Production Key"])
    assert result.exit_code == 0
    assert "API Key Created successfully" in result.output
    assert "raw_key_value_12345" in result.output
    assert "prefix12" in result.output
