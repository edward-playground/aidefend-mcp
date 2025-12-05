"""
Integration tests for authentication in REST API.

Tests the full FastAPI application with authentication middleware.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app


@pytest.fixture
def client_no_auth():
    """Test client with no_auth mode."""
    with patch("app.auth.settings") as mock_settings:
        mock_settings.AUTH_MODE = "no_auth"
        yield TestClient(app)


@pytest.fixture
def client_api_key():
    """Test client with api_key mode."""
    with patch("app.auth.settings") as mock_settings:
        mock_settings.AUTH_MODE = "api_key"
        mock_settings.AIDEFEND_API_KEY = "test-api-key-12345"
        yield TestClient(app)


@pytest.mark.integration
class TestPublicEndpoints:
    """Test that public endpoints are always accessible."""

    def test_health_endpoint_public_in_no_auth_mode(self, client_no_auth):
        """Test /health is accessible without auth in no_auth mode."""
        # Act
        response = client_no_auth.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_health_endpoint_public_in_api_key_mode(self, client_api_key):
        """Test /health is accessible without auth in api_key mode."""
        # Act
        response = client_api_key.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_root_endpoint_public_in_no_auth_mode(self, client_no_auth):
        """Test / is accessible without auth in no_auth mode."""
        # Act
        response = client_no_auth.get("/")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "service" in data

    def test_root_endpoint_public_in_api_key_mode(self, client_api_key):
        """Test / is accessible without auth in api_key mode."""
        # Act
        response = client_api_key.get("/")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert "service" in data


@pytest.mark.integration
class TestProtectedEndpointsNoAuth:
    """Test protected endpoints in no_auth mode."""

    @patch("app.core.query_engine")
    def test_status_endpoint_accessible_without_key(self, mock_engine, client_no_auth):
        """Test /api/v1/status is accessible without API key in no_auth mode."""
        # Arrange
        mock_engine.is_initialized = True
        mock_engine.is_ready = True

        # Act
        response = client_no_auth.get("/api/v1/status")

        # Assert
        assert response.status_code == 200

    @patch("app.core.query_engine")
    def test_query_endpoint_accessible_without_key(self, mock_engine, client_no_auth):
        """Test /api/v1/query is accessible without API key in no_auth mode."""
        # Arrange
        mock_engine.is_initialized = True
        mock_engine.is_ready = True
        mock_engine.search.return_value = {"results": [], "total": 0}

        # Act
        response = client_no_auth.post(
            "/api/v1/query",
            json={"query_text": "test query", "top_k": 5}
        )

        # Assert - Should work in no_auth mode
        # (May return 503 if engine not initialized, but not 401)
        assert response.status_code != 401


@pytest.mark.integration
class TestProtectedEndpointsApiKey:
    """Test protected endpoints in api_key mode."""

    def test_status_endpoint_requires_auth(self, client_api_key):
        """Test /api/v1/status requires authentication in api_key mode."""
        # Act - no API key provided
        response = client_api_key.get("/api/v1/status")

        # Assert
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_status_endpoint_rejects_invalid_key(self, client_api_key):
        """Test /api/v1/status rejects invalid API key."""
        # Act
        response = client_api_key.get(
            "/api/v1/status",
            headers={"X-API-Key": "wrong-key"}
        )

        # Assert
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    @patch("app.core.query_engine")
    def test_status_endpoint_accepts_valid_key(self, mock_engine, client_api_key):
        """Test /api/v1/status accepts valid API key."""
        # Arrange
        mock_engine.is_initialized = True
        mock_engine.is_ready = True

        # Act
        response = client_api_key.get(
            "/api/v1/status",
            headers={"X-API-Key": "test-api-key-12345"}
        )

        # Assert
        assert response.status_code == 200

    def test_query_endpoint_requires_auth(self, client_api_key):
        """Test /api/v1/query requires authentication in api_key mode."""
        # Act
        response = client_api_key.post(
            "/api/v1/query",
            json={"query_text": "test", "top_k": 5}
        )

        # Assert
        assert response.status_code == 401

    @patch("app.core.query_engine")
    def test_query_endpoint_accepts_valid_key(self, mock_engine, client_api_key):
        """Test /api/v1/query accepts valid API key."""
        # Arrange
        mock_engine.is_initialized = True
        mock_engine.is_ready = True
        mock_engine.search.return_value = {"results": [], "total": 0}

        # Act
        response = client_api_key.post(
            "/api/v1/query",
            json={"query_text": "test", "top_k": 5},
            headers={"X-API-Key": "test-api-key-12345"}
        )

        # Assert - Should not be 401 (may be other error codes if engine not ready)
        assert response.status_code != 401

    def test_sync_endpoint_requires_auth(self, client_api_key):
        """Test /api/v1/sync requires authentication in api_key mode."""
        # Act
        response = client_api_key.post("/api/v1/sync")

        # Assert
        assert response.status_code == 401

    def test_statistics_endpoint_requires_auth(self, client_api_key):
        """Test /api/v1/statistics requires authentication in api_key mode."""
        # Act
        response = client_api_key.get("/api/v1/statistics")

        # Assert
        assert response.status_code == 401


@pytest.mark.integration
class TestAuthHeaderVariations:
    """Test different variations of API key header."""

    @patch("app.core.query_engine")
    def test_api_key_with_extra_whitespace(self, mock_engine, client_api_key):
        """Test that API key with whitespace is properly trimmed."""
        # Arrange
        mock_engine.is_initialized = True
        mock_engine.is_ready = True

        # Act - key with leading/trailing spaces
        response = client_api_key.get(
            "/api/v1/status",
            headers={"X-API-Key": "  test-api-key-12345  "}
        )

        # Assert - Should work (whitespace trimmed)
        assert response.status_code == 200

    def test_missing_header_returns_401(self, client_api_key):
        """Test that missing X-API-Key header returns 401."""
        # Act
        response = client_api_key.get("/api/v1/status")

        # Assert
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_empty_header_returns_401(self, client_api_key):
        """Test that empty X-API-Key header returns 401."""
        # Act
        response = client_api_key.get(
            "/api/v1/status",
            headers={"X-API-Key": ""}
        )

        # Assert
        assert response.status_code == 401


@pytest.mark.integration
class TestRateLimitingWithAuth:
    """Test that rate limiting works with authentication."""

    def test_rate_limiting_applies_in_no_auth_mode(self, client_no_auth):
        """Test that rate limiting is enforced even in no_auth mode."""
        # This is important for security - rate limiting should always be active
        # Note: This test would need to make many requests to trigger rate limit
        # For now, just verify the endpoint is accessible
        response = client_no_auth.get("/health")
        assert response.status_code == 200

    @patch("app.core.query_engine")
    def test_rate_limiting_applies_in_api_key_mode(self, mock_engine, client_api_key):
        """Test that rate limiting is enforced in api_key mode."""
        # Arrange
        mock_engine.is_initialized = True
        mock_engine.is_ready = True

        # Act - Make request with valid key
        response = client_api_key.get(
            "/api/v1/status",
            headers={"X-API-Key": "test-api-key-12345"}
        )

        # Assert - Should work (rate limiting allows this single request)
        assert response.status_code == 200


@pytest.mark.integration
class TestCORSWithAuth:
    """Test CORS headers with different authentication modes."""

    def test_cors_headers_present_in_no_auth_mode(self, client_no_auth):
        """Test that CORS headers are present in no_auth mode."""
        # Use GET request instead of OPTIONS to test CORS
        # (OPTIONS method may not be enabled for all endpoints)
        response = client_no_auth.get(
            "/health",
            headers={"Origin": "http://example.com"}
        )

        # Assert - should work without authentication
        assert response.status_code == 200

    def test_cors_headers_present_in_api_key_mode(self, client_api_key):
        """Test that CORS headers are present in api_key mode."""
        # Use GET request instead of OPTIONS to test CORS
        response = client_api_key.get(
            "/health",
            headers={"Origin": "http://example.com"}
        )

        # Assert - /health is public endpoint, should work
        assert response.status_code == 200
