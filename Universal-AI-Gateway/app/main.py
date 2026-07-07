"""
Main FastAPI application — wires all components together.
Supports all requirements integration.

Uses app/core/config.py (Pydantic Settings) as the single config source.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import setup_logging

# Import routers
from app.api.routes import router as chat_router
from app.api.health import router as health_router
from app.api.admin import router as admin_router
from app.api.dependencies import authenticate_api_key

# Import middleware
from app.middleware.error_handler import GlobalExceptionMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.middleware.auth import AuthenticationMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

# Import services (for /metrics endpoint)
from app.services.metrics import metrics

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Application factory — creates and configures the FastAPI app.

    Middleware order (outermost first, added in reverse):
    1. GlobalExceptionMiddleware — catches unhandled exceptions
    2. AuthenticationMiddleware — assigns request IDs, validates auth
    3. RateLimitMiddleware — enforces per-key/tenant/global limits
    4. SecurityHeadersMiddleware — adds HSTS, CSP, etc.
    5. CORSMiddleware — handles CORS preflight
    """
    settings = get_settings()
    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "Starting %s v%s [%s]",
            settings.app_name, settings.app_version, settings.environment,
        )
        # Initialize database connection pool (R2-1)
        try:
            from app.db.database import init_database
            await init_database()
            logger.info("Database initialized")
        except Exception as exc:
            logger.warning("Database init skipped (not available): %s", exc)

        yield

        logger.info("Shutting down %s", settings.app_name)
        # Close database connections (R2-1)
        try:
            from app.db.database import close_database
            await close_database()
        except Exception:
            pass
        # Close provider HTTP clients (R2-4)
        try:
            from app.api.routes import close_router_clients
            await close_router_clients()
            logger.info("Provider HTTP clients closed")
        except Exception:
            pass

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Universal LLM Gateway — unified API for multiple LLM providers",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Initialize distributed tracing (Requirement R4-3)
    from app.core.tracing import setup_tracing
    setup_tracing(app)

    # ------------------------------------------------------------------
    # Middleware (added in reverse order — last added runs first)
    # ------------------------------------------------------------------

    # 5. CORS (innermost)
    has_wildcard = "*" in settings.security.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.security.cors_origins,
        allow_credentials=not has_wildcard,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 4. Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 3. Rate limiting (Requirement 7.2, 7.3)
    app.add_middleware(RateLimitMiddleware)

    # 2. Authentication (Requirement 2.2, 2.3)
    app.add_middleware(AuthenticationMiddleware)

    # 1. Global exception handler (outermost)
    app.add_middleware(GlobalExceptionMiddleware)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    from fastapi import Depends
    app.include_router(chat_router, dependencies=[Depends(authenticate_api_key)])
    app.include_router(health_router)
    app.include_router(admin_router)

    # Metrics endpoint (Requirement 15.1)
    @app.get("/metrics", tags=["Monitoring"])
    async def get_metrics():
        return metrics.get_metrics()

    # ------------------------------------------------------------------
    # Startup / shutdown events
    # ------------------------------------------------------------------

    # Startup and shutdown events are now handled by lifespan context manager

    return app


# Create the app instance
app = create_app()