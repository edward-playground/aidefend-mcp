"""
Custom exceptions for AIDEFEND MCP Service.
"""

# Re-export exceptions from app.core for backward compatibility
from app.core import (
    QueryEngineError,
    QueryEngineNotInitializedError
)

__all__ = [
    'QueryEngineError',
    'QueryEngineNotInitializedError'
]
