"""
Unit tests for authentication module (app/auth.py).

Tests the authentication logic in isolation without FastAPI integration.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from app.auth import get_current_user, get_api_key_hint


@pytest.mark.asyncio
class TestAuthenticationLogic:
    """Test suite for authentication logic."""

    @patch("app.auth.settings")
    async def test_no_auth_mode_allows_all_requests(self, mock_settings):
        """Test that no_auth mode allows requests without API key."""
        # Arrange
        mock_settings.AUTH_MODE = "no_auth"

        # Act
        result = await get_current_user(api_key_header_value=None)

        # Assert
        assert result is True

    @patch("app.auth.settings")
    async def test_api_key_mode_with_valid_key(self, mock_settings):
        """Test that api_key mode accepts valid API key."""
        # Arrange
        mock_settings.AUTH_MODE = "api_key"
        mock_settings.AIDEFEND_API_KEY = "test-secret-key-12345"

        # Act
        result = await get_current_user(api_key_header_value="test-secret-key-12345")

        # Assert
        assert result is True

    @patch("app.auth.settings")
    async def test_api_key_mode_with_invalid_key(self, mock_settings):
        """Test that api_key mode rejects invalid API key."""
        # Arrange
        mock_settings.AUTH_MODE = "api_key"
        mock_settings.AIDEFEND_API_KEY = "correct-key"

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(api_key_header_value="wrong-key")

        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail

    @patch("app.auth.settings")
    async def test_api_key_mode_without_key_header(self, mock_settings):
        """Test that api_key mode rejects requests without API key header."""
        # Arrange
        mock_settings.AUTH_MODE = "api_key"
        mock_settings.AIDEFEND_API_KEY = "test-key"

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(api_key_header_value=None)

        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail

    @patch("app.auth.settings")
    async def test_api_key_mode_with_empty_key_header(self, mock_settings):
        """Test that api_key mode rejects empty API key header."""
        # Arrange
        mock_settings.AUTH_MODE = "api_key"
        mock_settings.AIDEFEND_API_KEY = "test-key"

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(api_key_header_value="")

        assert exc_info.value.status_code == 401

    @patch("app.auth.settings")
    async def test_api_key_mode_with_whitespace_key(self, mock_settings):
        """Test that API keys are properly trimmed (whitespace handling)."""
        # Arrange
        mock_settings.AUTH_MODE = "api_key"
        mock_settings.AIDEFEND_API_KEY = "  test-key-with-spaces  "

        # Act - should succeed with trimmed key
        result = await get_current_user(api_key_header_value="test-key-with-spaces")

        # Assert
        assert result is True

    @patch("app.auth.settings")
    async def test_api_key_mode_without_configured_key(self, mock_settings):
        """Test that api_key mode with no configured key returns 500."""
        # Arrange
        mock_settings.AUTH_MODE = "api_key"
        mock_settings.AIDEFEND_API_KEY = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(api_key_header_value="any-key")

        assert exc_info.value.status_code == 500
        assert "misconfiguration" in exc_info.value.detail.lower()

    @patch("app.auth.settings")
    async def test_timing_attack_resistance(self, mock_settings):
        """Test that authentication uses constant-time comparison."""
        # Arrange
        mock_settings.AUTH_MODE = "api_key"
        mock_settings.AIDEFEND_API_KEY = "secret-key-" + "a" * 100

        # Act - Try keys with different lengths and prefixes
        # All should fail, but should take similar time (not testable here)
        test_keys = [
            "wrong",
            "secret-key-wrong",
            "s" * 120,
            "",
        ]

        # Assert - All should raise 401
        for key in test_keys:
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(api_key_header_value=key)
            assert exc_info.value.status_code == 401


class TestApiKeyHint:
    """Test suite for API key hint utility."""

    @patch("app.auth.settings")
    def test_get_api_key_hint_with_long_key(self, mock_settings):
        """Test API key hint shows first 8 characters."""
        # Arrange
        mock_settings.AIDEFEND_API_KEY = "abcdefghijklmnop"

        # Act
        hint = get_api_key_hint()

        # Assert
        assert hint == "abcdefgh..."

    @patch("app.auth.settings")
    def test_get_api_key_hint_with_short_key(self, mock_settings):
        """Test API key hint masks short keys."""
        # Arrange
        mock_settings.AIDEFEND_API_KEY = "short"

        # Act
        hint = get_api_key_hint()

        # Assert
        assert hint == "***"

    @patch("app.auth.settings")
    def test_get_api_key_hint_without_key(self, mock_settings):
        """Test API key hint when no key is configured."""
        # Arrange
        mock_settings.AIDEFEND_API_KEY = None

        # Act
        hint = get_api_key_hint()

        # Assert
        assert hint == "<not configured>"


@pytest.mark.unit
class TestConfigValidation:
    """Test configuration validators in app/config.py."""

    def test_network_binding_validation_rejects_unsafe_config(self):
        """Test that 0.0.0.0 + no_auth is rejected."""
        from pydantic import ValidationError
        from app.config import Settings

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                AUTH_MODE="no_auth",
                API_HOST="0.0.0.0"
            )

        # Should contain security error message
        assert "SECURITY ERROR" in str(exc_info.value)
        assert "0.0.0.0" in str(exc_info.value)

    def test_network_binding_validation_allows_localhost(self):
        """Test that 127.0.0.1 + no_auth is allowed."""
        from app.config import Settings

        # Act - should not raise
        settings = Settings(
            AUTH_MODE="no_auth",
            API_HOST="127.0.0.1"
        )

        # Assert
        assert settings.API_HOST == "127.0.0.1"
        assert settings.AUTH_MODE == "no_auth"

    def test_network_binding_validation_allows_external_with_auth(self):
        """Test that 0.0.0.0 + api_key is allowed."""
        from app.config import Settings

        # Act - should not raise
        settings = Settings(
            AUTH_MODE="api_key",
            API_HOST="0.0.0.0",
            AIDEFEND_API_KEY="test-key-123"
        )

        # Assert
        assert settings.API_HOST == "0.0.0.0"
        assert settings.AUTH_MODE == "api_key"

    def test_api_key_requirement_validation(self):
        """Test that api_key mode requires AIDEFEND_API_KEY."""
        from pydantic import ValidationError
        from app.config import Settings

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                AUTH_MODE="api_key",
                AIDEFEND_API_KEY=None
            )

        # Should contain configuration error message
        assert "CONFIGURATION ERROR" in str(exc_info.value)
        assert "API Key required" in str(exc_info.value)

    def test_api_key_requirement_validation_allows_no_auth(self):
        """Test that no_auth mode does not require AIDEFEND_API_KEY."""
        from app.config import Settings

        # Act - should not raise
        settings = Settings(
            AUTH_MODE="no_auth",
            AIDEFEND_API_KEY=None
        )

        # Assert
        assert settings.AUTH_MODE == "no_auth"
        assert settings.AIDEFEND_API_KEY is None
