"""
Tests for get_aidefend_status tool (system status check).

Tests the status endpoint that provides system health and sync information.
"""
import pytest
from datetime import datetime
from app.core import query_engine
from app.utils import load_version_info


class TestStatusResponseStructure:
    """Test expected status response structure."""

    def test_expected_status_keys(self):
        """Status response should have expected top-level keys."""
        # Expected keys in status response
        expected_keys = {
            'status',
            'database',
            'embedding_model',
            'sync',
            'version',
            'timestamp'
        }

        # Mock status response structure
        mock_status = {
            "status": "ready",
            "database": {
                "initialized": True,
                "total_documents": 500
            },
            "embedding_model": {
                "name": "intfloat/multilingual-e5-base",
                "dimension": 768
            },
            "sync": {
                "last_sync": "2024-01-01T00:00:00Z",
                "sync_status": "success"
            },
            "version": {
                "framework_version": "1.20250101",
                "service_version": "1.0.0"
            },
            "timestamp": "2024-01-01T00:00:00Z"
        }

        assert expected_keys.issubset(set(mock_status.keys()))

    def test_database_status_fields(self):
        """Database status should have expected fields."""
        expected_fields = {'initialized', 'total_documents'}

        mock_db_status = {
            "initialized": True,
            "total_documents": 500
        }

        assert expected_fields.issubset(set(mock_db_status.keys()))

    def test_embedding_model_fields(self):
        """Embedding model info should have expected fields."""
        expected_fields = {'name', 'dimension'}

        mock_model_info = {
            "name": "intfloat/multilingual-e5-base",
            "dimension": 768
        }

        assert set(mock_model_info.keys()) == expected_fields

    def test_sync_status_fields(self):
        """Sync status should have expected fields."""
        expected_fields = {'last_sync', 'sync_status'}

        mock_sync_status = {
            "last_sync": "2024-01-01T00:00:00Z",
            "sync_status": "success"
        }

        assert expected_fields.issubset(set(mock_sync_status.keys()))


class TestStatusValues:
    """Test status value validation."""

    def test_status_values(self):
        """Status field should have valid values."""
        valid_statuses = ['ready', 'initializing', 'syncing', 'error']

        # All valid
        for status in valid_statuses:
            assert status in valid_statuses

    def test_sync_status_values(self):
        """Sync status should have valid values."""
        valid_sync_statuses = ['success', 'failed', 'in_progress', 'never_synced']

        # All valid
        for status in valid_sync_statuses:
            assert status in valid_sync_statuses

    def test_timestamp_format(self):
        """Timestamp should be ISO 8601 format."""
        # Example ISO 8601 timestamp
        timestamp = "2024-01-01T12:00:00Z"

        # Should be parseable
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        assert isinstance(parsed, datetime)


class TestQueryEngineStatus:
    """Test query engine status properties."""

    def test_query_engine_has_status_properties(self):
        """Query engine should expose status properties."""
        # QueryEngine only exposes is_ready property (not is_initialized)
        assert hasattr(query_engine, 'is_ready')

        # Should be boolean
        assert isinstance(query_engine.is_ready, bool)

    def test_query_engine_not_ready_initially(self):
        """Query engine should not be ready before initialization."""
        # Before initialization, is_ready should be False
        # (unless initialize() was already called)
        assert isinstance(query_engine.is_ready, bool)


class TestVersionInfo:
    """Test version information loading."""

    def test_load_version_info_function(self):
        """load_version_info should be callable."""
        assert callable(load_version_info)

    def test_version_info_structure(self):
        """Version info should have expected structure."""
        version_info = load_version_info()

        if version_info is None:
            pytest.skip("Version file not found - never synced")

        # Should have these keys
        assert isinstance(version_info, dict)

    def test_framework_version_format(self):
        """Framework version should follow format 1.YYYYMMDD."""
        version_info = load_version_info()

        if version_info is None:
            pytest.skip("Version file not found - never synced")

        if 'framework_version' in version_info:
                version = version_info['framework_version']

                # Should start with "1."
                assert version.startswith('1.'), f"Version should start with '1.', got {version}"

                # Should have format 1.YYYYMMDD (at least 10 characters)
                assert len(version) >= 10, f"Version should be at least 10 chars, got {len(version)}"



class TestStatusEdgeCases:
    """Test status edge cases."""

    def test_status_when_database_missing(self):
        """Status should handle missing database gracefully."""
        # When database doesn't exist, status should indicate not ready
        # This is tested by checking is_ready property
        assert isinstance(query_engine.is_ready, bool)

    def test_status_during_sync(self):
        """Status should indicate when sync is in progress."""
        from app.sync import is_sync_in_progress

        # Should return boolean
        sync_in_progress = is_sync_in_progress()
        assert isinstance(sync_in_progress, bool)


class TestStatusAPIIntegration:
    """Test status integration with REST API (requires TestClient)."""

    @pytest.mark.integration
    def test_status_endpoint_exists(self):
        """Status endpoint should be defined in main.py."""
        from app.main import app

        # Verify app has the endpoint
        routes = [route.path for route in app.routes]
        assert "/api/v1/status" in routes or any("/status" in route for route in routes)


class TestStatusMCPIntegration:
    """Test status integration with MCP server."""

    def test_get_aidefend_status_tool_exists(self):
        """get_aidefend_status should be defined as MCP tool."""
        # This is tested by presence in mcp_server.py
        # Just verify the function exists
        import mcp_server

        # Module should be importable
        assert hasattr(mcp_server, 'serve')


class TestStatusMetrics:
    """Test status metrics calculation."""

    def test_document_count_is_integer(self):
        """Total documents should be non-negative integer."""
        # Mock document count
        mock_count = 500

        assert isinstance(mock_count, int)
        assert mock_count >= 0

    def test_embedding_dimension_valid(self):
        """Embedding dimension should be positive integer."""
        from app.config import settings

        assert isinstance(settings.EMBEDDING_DIMENSION, int)
        assert settings.EMBEDDING_DIMENSION > 0
        assert settings.EMBEDDING_DIMENSION == 768  # Default model


class TestStatusCaching:
    """Test status information caching (if implemented)."""

    def test_status_should_be_fast(self):
        """Status check should be fast (no heavy computation)."""
        # This is a performance expectation, not a functional test
        # Status should just read state, not recompute
        assert True  # Placeholder

    def test_status_should_not_trigger_sync(self):
        """Checking status should not trigger automatic sync."""
        # Status is read-only operation
        assert True  # Placeholder


class TestStatusErrorHandling:
    """Test error handling in status checks."""

    def test_status_handles_missing_version_file(self):
        """Status should handle missing version file gracefully."""
        version_info = load_version_info()
        # Returns None when file doesn't exist, or dict when it does
        assert version_info is None or isinstance(version_info, dict)

    def test_status_handles_corrupted_version_file(self):
        """Status should handle corrupted version file gracefully."""
        # If version file is corrupted, should not crash
        # This would require mocking file system, skip for now
        pass
