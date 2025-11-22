"""
Authentication and authorization module for AIDEFEND MCP Service.

This module provides authentication mechanisms for the REST API mode.
MCP mode does not use HTTP authentication (secured via file permissions).
"""

import secrets
from typing import Optional
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

# Define the API key header
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def get_current_user(
    api_key_header_value: Optional[str] = Security(api_key_header)
) -> bool:
    """
    Unified authentication dependency for FastAPI.

    This function determines authentication requirements based on AUTH_MODE:
    - no_auth: Allow all requests (for local development)
    - api_key: Require valid API key in X-API-Key header

    Args:
        api_key_header_value: API key from X-API-Key header (optional)

    Returns:
        bool: True if authenticated

    Raises:
        HTTPException: 401 if authentication fails or is required but not provided

    Security Notes:
        - Uses secrets.compare_digest() to prevent timing attacks
        - Logs authentication failures for security monitoring
        - Does not log successful authentications to avoid log pollution
    """

    # Mode 1: No authentication (local development only)
    if settings.AUTH_MODE == "no_auth":
        return True

    # Mode 2: API Key authentication (production deployment)
    if settings.AUTH_MODE == "api_key":
        # Check if API key is configured (should be caught by config validator)
        if not settings.AIDEFEND_API_KEY:
            logger.error(
                "AUTH_MODE is 'api_key' but AIDEFEND_API_KEY is not configured. "
                "This should have been caught during initialization."
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server authentication misconfiguration"
            )

        # Check if API key header is provided
        if not api_key_header_value:
            logger.warning(
                "Authentication failed: No API key provided in X-API-Key header"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Provide API key in X-API-Key header.",
                headers={"WWW-Authenticate": "ApiKey"}
            )

        # Validate API key using constant-time comparison
        # This prevents timing attacks where an attacker could measure response time
        # to determine correct characters in the API key
        is_valid = secrets.compare_digest(
            api_key_header_value.strip(),
            settings.AIDEFEND_API_KEY.strip()
        )

        if not is_valid:
            logger.warning(
                "Authentication failed: Invalid API key provided. "
                f"Key prefix: {api_key_header_value[:8] if len(api_key_header_value) >= 8 else '***'}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"}
            )

        # Success - no need to log every successful auth (reduces log noise)
        return True

    # Unknown auth mode (should never happen due to Literal type constraint)
    logger.error(f"Unknown AUTH_MODE: {settings.AUTH_MODE}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Server authentication misconfiguration"
    )


def get_api_key_hint() -> str:
    """
    Get a hint about the configured API key for debugging.

    Returns:
        str: Partial API key (first 8 characters) or indication if not set

    Security Note:
        Only returns first 8 characters to prevent full key exposure in logs
    """
    if not settings.AIDEFEND_API_KEY:
        return "<not configured>"

    if len(settings.AIDEFEND_API_KEY) < 8:
        return "***"

    return f"{settings.AIDEFEND_API_KEY[:8]}..."
