"""
Budget Manager Service.
Tracks accumulated financial costs per tenant in Redis and enforces budget limits.
"""

from typing import Optional
from decimal import Decimal

from app.cache.redis import get_redis
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.notifier import get_notifier

logger = get_logger(__name__)


class BudgetExceededError(Exception):
    """Raised when a tenant exceeds their defined financial limit."""
    pass


class BudgetManager:
    """
    Tracks and enforces financial bounds at a tenant level using Redis.
    """
    
    def __init__(self):
        self.settings = get_settings()
        # Default implicit budget if none is passed/specified (e.g. $100.00 / month)
        self.default_budget = Decimal("100.00")
        
    async def get_tenant_spend(self, tenant_id: str) -> Decimal:
        """Get the current accumulated spend for a tenant."""
        redis = get_redis()
        if not redis:
            logger.warning("Redis is not available; returning $0.00 spend")
            return Decimal("0.00")
            
        key = f"budget:tenant:{tenant_id}:cost"
        try:
            val = await redis.get(key)
            if val is None:
                return Decimal("0.00")
            return Decimal(val.decode("utf-8") if isinstance(val, bytes) else str(val))
        except Exception as e:
            logger.error("Failed to retrieve budget for tenant %s: %s", tenant_id, str(e))
            return Decimal("0.00")

    async def add_cost(self, tenant_id: str, cost_usd: float) -> Decimal:
        """Increment the given tenant's tracked spend by 'cost_usd'."""
        redis = get_redis()
        if not redis or cost_usd <= 0:
            return Decimal("0.00")
            
        key = f"budget:tenant:{tenant_id}:cost"
        try:
            # INCRBYFLOAT is atomic
            new_val = await redis.incrbyfloat(key, cost_usd)
            # Retain usage count indefinitely or set TTL for monthly rollup (e.g., 30 days)
            # await self.redis.expire(key, 86400 * 30)
            return Decimal(str(new_val))
        except Exception as e:
            logger.error("Failed to increment budget for tenant %s: %s", tenant_id, str(e))
            return Decimal("0.00")

    async def check_budget(self, tenant_id: str, max_budget: Optional[Decimal] = None) -> bool:
        """
        Check if the tenant is under budget.
        Raises BudgetExceededError if over the limit.
        """
        limit = max_budget if max_budget is not None else self.default_budget
        current_spend = await self.get_tenant_spend(tenant_id)
        
        notifier = get_notifier()
        
        # 100% Alert
        if current_spend > limit:
            await notifier.notify(
                "BUDGET_EXCEEDED",
                f"Tenant {tenant_id} has exceeded their budget of ${limit:.2f}",
                {"tenant_id": tenant_id, "spend": float(current_spend), "limit": float(limit)}
            )
            logger.warning(
                "Tenant %s exceeded budget. Spend: $%.4f / Limit: $%.4f",
                tenant_id, current_spend, limit
            )
            raise BudgetExceededError(f"Budget exceeded limit of ${limit:.2f}")
            
        # 80% Warning (Simplified logic - in production use a Redis flag to avoid spamming)
        if current_spend > (limit * Decimal("0.8")):
            await notifier.notify(
                "BUDGET_WARNING",
                f"Tenant {tenant_id} reached 80% of budget (${current_spend:.2f} / ${limit:.2f})",
                {"tenant_id": tenant_id, "spend": float(current_spend), "limit": float(limit)}
            )
            
        return True
