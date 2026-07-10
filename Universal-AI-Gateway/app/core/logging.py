"""
Structured logging configuration with JSON formatter.
Supports comprehensive logging for analytics, debugging, and monitoring.
"""

import logging
import logging.config
import json
import sys
from datetime import datetime
from typing import Dict, Any, Optional
import traceback
import uuid

from app.core.config import get_settings


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add correlation ID if available
        if hasattr(record, "correlation_id"):
            log_entry["correlation_id"] = record.correlation_id
        
        # Add request ID if available
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        
        # Add API key ID if available
        if hasattr(record, "api_key_id"):
            log_entry["api_key_id"] = record.api_key_id
        
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "lineno", "funcName", "created",
                "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "getMessage", "exc_info",
                "exc_text", "stack_info", "correlation_id", "request_id",
                "api_key_id"
            ]:
                log_entry[key] = value
        
        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        return json.dumps(log_entry, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter for development"""
    
    def __init__(self):
        super().__init__(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


def setup_logging():
    """Configure structured logging based on settings"""
    settings = get_settings()
    
    # Choose formatter based on configuration
    if settings.logging.format.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, settings.logging.level),
        format="%(message)s" if settings.logging.format.lower() == "json" else None,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set up handler with custom formatter
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
    
    # Configure specific loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.debug else logging.WARNING
    )
    logging.getLogger("redis").setLevel(logging.WARNING)
    
    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging configured with level={settings.logging.level}, "
        f"format={settings.logging.format}"
    )


class ContextualLogger:
    """Logger with contextual information for request tracking"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.context: Dict[str, Any] = {}
    
    def set_context(self, **kwargs):
        """Set contextual information"""
        self.context.update(kwargs)
    
    def clear_context(self):
        """Clear contextual information"""
        self.context.clear()
    
    def _log_with_context(self, level: int, message: str, *args, **kwargs):
        """Log message with contextual information"""
        exc_info = kwargs.pop('exc_info', None)
        extra = {**self.context, **kwargs}
        if exc_info is not None:
            self.logger.log(level, message, *args, extra=extra, exc_info=exc_info)
        else:
            self.logger.log(level, message, *args, extra=extra)
    
    def debug(self, message: str, *args, **kwargs):
        """Log debug message with context"""
        self._log_with_context(logging.DEBUG, message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """Log info message with context"""
        self._log_with_context(logging.INFO, message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Log warning message with context"""
        self._log_with_context(logging.WARNING, message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Log error message with context"""
        self._log_with_context(logging.ERROR, message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs):
        """Log critical message with context"""
        self._log_with_context(logging.CRITICAL, message, *args, **kwargs)


def get_logger(name: str) -> ContextualLogger:
    """Get contextual logger instance"""
    return ContextualLogger(name)


def generate_correlation_id() -> str:
    """Generate unique correlation ID for request tracking"""
    return str(uuid.uuid4())


def mask_sensitive_data(data: str) -> str:
    """Mask sensitive data in logs (basic implementation)"""
    settings = get_settings()
    
    if not settings.logging.log_pii_redaction:
        return data
    
    # Basic PII patterns - will be enhanced in later tasks
    import re
    
    # Mask email addresses
    data = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[REDACTED_EMAIL]', data)
    
    # Mask potential API keys (long alphanumeric strings)
    data = re.sub(r'\b[A-Za-z0-9]{20,}\b', '[REDACTED_KEY]', data)
    
    # Mask credit card numbers (basic pattern)
    data = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[REDACTED_CC]', data)
    
    # Mask SSN patterns
    data = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_SSN]', data)
    
    return data