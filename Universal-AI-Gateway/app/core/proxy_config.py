"""
Proxy routing configuration and route matcher.
Supports Requirements for path-based routing mapping.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from app.core.config import get_settings

@dataclass
class RouteConfig:
    """Configuration for a single reverse proxy route."""
    prefix: str
    upstream_url: str
    strip_prefix: bool
    timeout_seconds: float
    methods: List[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])


# Load downstream base URL from settings
settings = get_settings()
UPSTREAM_BASE_URL = settings.downstream_url

# Define route table (Step 1.2)
FTGO_ROUTES: List[RouteConfig] = [
    RouteConfig(
        prefix="/api/orders",
        upstream_url=UPSTREAM_BASE_URL,
        strip_prefix=True,
        timeout_seconds=30.0,
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    ),
    RouteConfig(
        prefix="/api/consumers",
        upstream_url=UPSTREAM_BASE_URL,
        strip_prefix=True,
        timeout_seconds=10.0,
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    ),
    RouteConfig(
        prefix="/api/kitchen",
        upstream_url=UPSTREAM_BASE_URL,
        strip_prefix=True,
        timeout_seconds=10.0,
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    ),
    RouteConfig(
        prefix="/api/restaurants",
        upstream_url=UPSTREAM_BASE_URL,
        strip_prefix=True,
        timeout_seconds=10.0,
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    ),
    RouteConfig(
        prefix="/api/accounting",
        upstream_url=UPSTREAM_BASE_URL,
        strip_prefix=True,
        timeout_seconds=10.0,
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    ),
    RouteConfig(
        prefix="/actuator/health",
        upstream_url=UPSTREAM_BASE_URL,
        strip_prefix=False,
        timeout_seconds=5.0,
        methods=["GET"],
    ),
]


def get_route(path: str) -> Optional[RouteConfig]:
    """
    Match an incoming request path to a RouteConfig from the route table.

    Exempts:
      - /v1/
      - /health
      - /admin/
    
    Returns the first matching route, or None if no match is found.
    """
    # Exclude internal routes explicitly
    for prefix in ("/v1", "/health", "/admin", "/metrics"):
        if path == prefix or path.startswith(prefix + "/"):
            return None

    # Find first matching route prefix
    for route in FTGO_ROUTES:
        if path.startswith(route.prefix):
            return route

    return None
