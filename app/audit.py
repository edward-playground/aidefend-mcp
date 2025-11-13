"""
Audit Logging Module for AIDEFEND MCP Service

This module provides audit logging functionality to track all tool usage,
including who used which tool, when, with what parameters, and the result.

Audit logs are stored in JSON Lines format for easy parsing and analysis.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from logging.handlers import TimedRotatingFileHandler

from app.config import settings


class AuditLogger:
    """
    Audit logger for tracking tool usage and security events.

    Logs are written in JSON Lines format to enable easy parsing and analysis.
    Each log entry includes timestamp, tool name, parameters, result, and execution time.
    """

    def __init__(self):
        """Initialize audit logger with file handler."""
        self.logger = logging.getLogger("aidefend.audit")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False  # Don't propagate to root logger

        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        # Create audit log file handler with daily rotation
        audit_log_path = log_dir / "audit.log"

        # Rotate daily, keep 30 days of logs
        handler = TimedRotatingFileHandler(
            filename=str(audit_log_path),
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8"
        )

        # Use plain formatter (we'll format as JSON in log_event)
        handler.setFormatter(logging.Formatter('%(message)s'))

        self.logger.addHandler(handler)

    def log_event(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        result_summary: str,
        success: bool,
        execution_time_ms: float,
        user_id: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Log an audit event for tool usage.

        Args:
            tool_name: Name of the tool/endpoint used
            parameters: Input parameters (will be sanitized)
            result_summary: Brief summary of the result
            success: Whether the operation succeeded
            execution_time_ms: Execution time in milliseconds
            user_id: Optional user identifier
            error_message: Optional error message if failed
        """
        # Sanitize parameters (remove sensitive data)
        sanitized_params = self._sanitize_parameters(parameters)

        # Build audit log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "tool_name": tool_name,
            "parameters": sanitized_params,
            "result_summary": result_summary,
            "success": success,
            "execution_time_ms": round(execution_time_ms, 2),
            "user_id": user_id or "anonymous",
            "error_message": error_message
        }

        # Write as JSON Line
        self.logger.info(json.dumps(log_entry))

    def log_tool_call(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        start_time: datetime
    ) -> Dict[str, Any]:
        """
        Log the start of a tool call and return context for completion logging.

        Args:
            tool_name: Name of the tool
            parameters: Input parameters
            start_time: When the tool call started

        Returns:
            Context dict to pass to log_tool_completion
        """
        return {
            "tool_name": tool_name,
            "parameters": parameters,
            "start_time": start_time
        }

    def log_tool_completion(
        self,
        context: Dict[str, Any],
        success: bool,
        result_summary: str,
        error_message: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """
        Log the completion of a tool call.

        Args:
            context: Context from log_tool_call
            success: Whether the call succeeded
            result_summary: Summary of the result
            error_message: Optional error message
            user_id: Optional user identifier
        """
        execution_time_ms = (datetime.now() - context["start_time"]).total_seconds() * 1000

        self.log_event(
            tool_name=context["tool_name"],
            parameters=context["parameters"],
            result_summary=result_summary,
            success=success,
            execution_time_ms=execution_time_ms,
            user_id=user_id,
            error_message=error_message
        )

    def log_security_event(
        self,
        event_type: str,
        description: str,
        severity: str = "WARNING",
        source_ip: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a security-related event (rate limiting, validation failure, etc.).

        Args:
            event_type: Type of security event (e.g., "RATE_LIMIT", "VALIDATION_ERROR")
            description: Description of the event
            severity: Severity level (INFO, WARNING, ERROR, CRITICAL)
            source_ip: Optional source IP address
            additional_context: Optional additional context
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": "SECURITY_EVENT",
            "security_event_type": event_type,
            "description": description,
            "severity": severity,
            "source_ip": source_ip,
            "additional_context": additional_context or {}
        }

        self.logger.warning(json.dumps(log_entry))

    def _sanitize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize parameters by removing or masking sensitive data.

        Args:
            parameters: Raw parameters dict

        Returns:
            Sanitized parameters dict
        """
        # Keywords that indicate sensitive data
        sensitive_keywords = {
            "password", "token", "secret", "key", "api_key",
            "auth", "credential", "private"
        }

        sanitized = {}

        for key, value in parameters.items():
            key_lower = key.lower()

            # Check if key contains sensitive keywords
            is_sensitive = any(keyword in key_lower for keyword in sensitive_keywords)

            if is_sensitive:
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, str) and len(value) > 500:
                # Truncate very long strings
                sanitized[key] = value[:500] + "... (truncated)"
            elif isinstance(value, dict):
                # Recursively sanitize nested dicts
                sanitized[key] = self._sanitize_parameters(value)
            elif isinstance(value, list) and len(value) > 10:
                # Truncate long lists
                sanitized[key] = value[:10] + ["... (truncated)"]
            else:
                sanitized[key] = value

        return sanitized


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """
    Get or create the global audit logger instance.

    Returns:
        AuditLogger instance
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def audit_tool_call(tool_name: str, parameters: Dict[str, Any], start_time: datetime) -> Dict[str, Any]:
    """
    Convenience function to log a tool call start.

    Args:
        tool_name: Name of the tool
        parameters: Input parameters
        start_time: Start time of the call

    Returns:
        Context for completion logging
    """
    logger = get_audit_logger()
    return logger.log_tool_call(tool_name, parameters, start_time)


def audit_tool_completion(
    context: Dict[str, Any],
    success: bool,
    result_summary: str,
    error_message: Optional[str] = None,
    user_id: Optional[str] = None
) -> None:
    """
    Convenience function to log a tool call completion.

    Args:
        context: Context from audit_tool_call
        success: Whether the call succeeded
        result_summary: Summary of the result
        error_message: Optional error message
        user_id: Optional user identifier
    """
    logger = get_audit_logger()
    logger.log_tool_completion(context, success, result_summary, error_message, user_id)


def audit_security_event(
    event_type: str,
    description: str,
    severity: str = "WARNING",
    source_ip: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Convenience function to log a security event.

    Args:
        event_type: Type of security event
        description: Description of the event
        severity: Severity level
        source_ip: Optional source IP
        additional_context: Optional additional context
    """
    logger = get_audit_logger()
    logger.log_security_event(event_type, description, severity, source_ip, additional_context)
