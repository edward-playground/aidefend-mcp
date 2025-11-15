"""
Structured logging configuration for AIDEFEND MCP Service.
Implements secure logging with no sensitive data exposure.
"""

import logging
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class SecureJSONFormatter(logging.Formatter):
    """
    Custom JSON formatter that excludes sensitive information.
    """

    SENSITIVE_KEYS = {
        "password", "token", "secret", "api_key", "authorization",
        "cookie", "session", "private_key", "credential"
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with sensitive data filtering."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields, filtering sensitive keys
        if hasattr(record, "extra"):
            extra = self._filter_sensitive(record.extra)
            log_data["extra"] = extra

        return json.dumps(log_data)

    def _filter_sensitive(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively filter sensitive keys from dict."""
        if not isinstance(data, dict):
            return data

        filtered = {}
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_KEYS):
                filtered[key] = "[REDACTED]"
            elif isinstance(value, dict):
                filtered[key] = self._filter_sensitive(value)
            else:
                filtered[key] = value

        return filtered


def setup_logger(
    name: str = "aidefend_mcp",
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    enable_console: bool = True
) -> logging.Logger:
    """
    Configure and return a secure logger instance.

    Args:
        name: Logger name
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        enable_console: Whether to log to console

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))
    logger.handlers.clear()  # Remove existing handlers

    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # File handler with JSON formatting
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Fixed: Set encoding='utf-8' for Windows cp950 compatibility
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(SecureJSONFormatter())
        logger.addHandler(file_handler)

    return logger


# Create default logger instance
default_logger = setup_logger()


def get_logger(name: str = "aidefend_mcp") -> logging.Logger:
    """Get or create a logger instance."""
    return logging.getLogger(name)
