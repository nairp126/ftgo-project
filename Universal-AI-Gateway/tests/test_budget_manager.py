import pytest
from httpx import AsyncClient, ASGITransport
from decimal import Decimal

from app.main import app
from app.services.budget_manager import BudgetManager, BudgetExceededError
from app.api.dependencies import authenticate_api_key
from fastapi import Request

@pytest.mark.asyncio
async def test_budget_manager_accumulation(mock_redis_globally):
    """Test that the budget manager correctly aggregates fractional USD."""
    manager = BudgetManager()
    
    tenant_id = "test_tenant_finance_1"
    
    # Add costs
    val1 = await manager.add_cost(tenant_id, 1.25)
    assert val1 == Decimal("1.25")
    
    val2 = await manager.add_cost(tenant_id, 0.50)
    assert val2 == Decimal("1.75")
    
    # Check retrieval
    total = await manager.get_tenant_spend(tenant_id)
    assert total == Decimal("1.75")
    
    # Check budget constraints
    assert await manager.check_budget(tenant_id, max_budget=Decimal("2.00")) is True
    
    with pytest.raises(BudgetExceededError):
        await manager.check_budget(tenant_id, max_budget=Decimal("1.00"))


@pytest.mark.asyncio
async def test_middleware_blocks_over_budget(mock_redis_globally):
    """Test that the API returns 402 Payment Required when budget exceeded."""
    from unittest.mock import patch
    
    tenant_id = "test_tenant_over_budget"
    
    # Pre-load the budget over the default 100.00
    with patch("app.services.budget_manager.get_redis", return_value=mock_redis_globally):
        manager = BudgetManager()
        await manager.add_cost(tenant_id, 150.00)
    
    # Mock the auth dependency to inject the test tenant
    async def override_get_current_api_key(request: Request):
        print("\n\nDEBUG OVERRIDE EXECUTED\n\n")
        request.state.tenant_id = tenant_id
        request.state.api_key_id = "key_123"
        request.state.rate_limit_per_minute = 60
        return type("APIKey", (), {"id": "key_123", "tenant_id": tenant_id, "rate_limit_per_minute": 60})()
        
    app.dependency_overrides[authenticate_api_key] = override_get_current_api_key
    
    with patch("app.services.budget_manager.get_redis", return_value=mock_redis_globally):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/v1/chat/completions",
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": "Hello"}],
                }
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 402
    assert "budget_exceeded" in response.json()["error"]["type"]

