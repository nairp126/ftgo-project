"""
Database connection setup with async SQLAlchemy 2.0.
Supports Requirements 14.2, 14.4 for database connectivity and connection pooling.
"""

from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all database models"""
    pass


# Models are imported locally in init_database() to avoid circular imports.models register with Base.metadata for Alembic autogenerate.


class DatabaseManager:
    """Database connection manager with async SQLAlchemy 2.0"""

    def __init__(self):
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def create_engine(self) -> AsyncEngine:
        """Create async database engine with connection pooling"""
        if self._engine is None:
            settings = get_settings()
            self._engine = create_async_engine(
                settings.database.url,
                pool_size=settings.database.pool_size,
                max_overflow=settings.database.max_overflow,
                pool_timeout=settings.database.pool_timeout,
                pool_pre_ping=True,  # Validate connections before use
                echo=settings.debug,  # Log SQL queries in debug mode
                future=True,  # Use SQLAlchemy 2.0 style
            )
            logger.info(
                f"Created database engine with url={settings.database.url}"
            )
        return self._engine

    def create_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Create async session factory"""
        if self._session_factory is None:
            engine = self.create_engine()
            self._session_factory = async_sessionmaker(
                engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=True,
                autocommit=False,
            )
            logger.info("Created database session factory")
        return self._session_factory

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get async database session"""
        session_factory = self.create_session_factory()
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self):
        """Close database connections"""
        if self._engine:
            await self._engine.dispose()
            logger.info("Database connections closed")

    async def health_check(self) -> bool:
        """Check database connectivity"""
        try:
            session_factory = self.create_session_factory()
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# Global database manager instance
db_manager = DatabaseManager()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session"""
    async for session in db_manager.get_session():
        yield session


async def init_database():
    """Create all database tables on startup (only in non-production environments)."""
    try:
        engine = db_manager.create_engine()
        # Test connection
        if await db_manager.health_check():
            logger.info("Database connection verified successfully")
        else:
            raise Exception("Database connection health check failed")
            
        settings = get_settings()
        if settings.environment == "production":
            logger.info("Skipping metadata create_all in production. Use Alembic migrations.")
            return

        import app.db.models  # noqa: F401
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database metadata schema applied successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


async def close_database():
    """Close database connections"""
    await db_manager.close()