import asyncio
import uuid
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from app.db.database import db_manager
from app.db.models import Tenant

async def seed():
    session_factory = db_manager.create_session_factory()
    async with session_factory() as session:
        # Check if any tenant exists
        from sqlalchemy import select
        stmt = select(Tenant).where(Tenant.name == "E2E Test Tenant")
        result = await session.execute(stmt)
        if result.scalar_one_or_none():
            print("Tenant already exists.")
            return

        tenant = Tenant(name="E2E Test Tenant", description="Tenant for end-to-end testing")
        session.add(tenant)
        await session.commit()
        print(f"Created tenant: {tenant.name} ({tenant.id})")

if __name__ == "__main__":
    asyncio.run(seed())
