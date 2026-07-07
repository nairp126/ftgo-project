#!/usr/bin/env python3
"""
Development server startup script for the Universal LLM Gateway.
"""

import uvicorn
from app.core.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.logging.level.lower(),
        access_log=True,
    )