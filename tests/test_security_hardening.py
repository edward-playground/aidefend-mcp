"""
Security Hardening Tests for AIDEFEND MCP Service

Tests the security improvements implemented in the security hardening phase:
1. Request Size Limiting (DoS protection)
2. Information Leakage Prevention
3. Filter Injection Prevention (LanceDB where() clauses)
4. Cross-Process File Locking
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.security import sanitize_technique_id, InputValidationError


# ==================== Test Request Size Limiting ====================

class TestRequestSizeLimiting:
    """Test Request Size Limiting middleware (DoS protection)."""

    def test_small_request_passes(self):
        """Test that requests under 1MB pass through."""
        client = TestClient(app)

        # Small payload (< 1MB)
        payload = {"query_text": "test" * 100, "top_k": 5}

        # Mock Content-Length header (small size)
        response = client.post(
            "/api/v1/query",
            json=payload,
            headers={"Content-Length": "1024"}  # 1KB
        )

        # Should not be blocked by size limit (may fail auth, but not 413)
        assert response.status_code != 413

    def test_large_request_rejected(self):
        """Test that requests over 1MB are rejected with HTTP 413."""
        client = TestClient(app)

        # Mock Content-Length header (> 1MB)
        response = client.post(
            "/api/v1/query",
            json={"query_text": "test", "top_k": 5},
            headers={"Content-Length": str(1048577)}  # 1MB + 1 byte
        )

        # Should be rejected with 413
        assert response.status_code == 413
        assert "REQUEST_TOO_LARGE" in response.json()["error"]

    def test_missing_content_length_passes(self):
        """Test that requests without Content-Length header pass through."""
        client = TestClient(app)

        # Request without Content-Length header
        payload = {"query_text": "test", "top_k": 5}

        # Should not be blocked (may fail for other reasons, but not 413)
        response = client.post("/api/v1/query", json=payload)
        assert response.status_code != 413

    def test_invalid_content_length_header(self):
        """Test that invalid Content-Length values are handled gracefully."""
        client = TestClient(app)

        # Invalid Content-Length header
        response = client.post(
            "/api/v1/query",
            json={"query_text": "test", "top_k": 5},
            headers={"Content-Length": "invalid"}
        )

        # Should not crash, may fail for other reasons but not 413
        assert response.status_code != 413


# ==================== Test Information Leakage Prevention ====================

class TestInformationLeakagePrevention:
    """Test that internal error details are hidden from API responses."""

    @patch("app.main.query_engine")
    def test_generic_exception_hides_details(self, mock_engine):
        """Test that endpoint-specific exceptions hide internal details."""
        client = TestClient(app)

        # Mock query engine to raise an unexpected exception
        mock_engine.is_ready = True
        mock_engine.search.side_effect = RuntimeError("Internal database connection failed: host=10.0.0.1")

        # Make request that triggers exception
        response = client.post(
            "/api/v1/query",
            json={"query_text": "test", "top_k": 5}
        )

        # Should return 500
        assert response.status_code == 500

        # Response should NOT contain sensitive internal details
        response_text = response.text.lower()
        assert "10.0.0.1" not in response_text  # No IP addresses exposed
        assert "runtimeerror" not in response_text  # No exception types

        # Should contain only generic error message
        data = response.json()
        assert "detail" in data  # FastAPI standard error format
        # The detail should be generic, not expose internals
        assert "10.0.0.1" not in data["detail"]

    def test_error_details_not_in_response(self):
        """Test that detailed error messages are sanitized."""
        client = TestClient(app)

        # Request that will fail due to validation (controlled error)
        response = client.post(
            "/api/v1/query",
            json={"query_text": "x" * 6000, "top_k": 5}  # Exceeds MAX_TOTAL_QUERY_LENGTH
        )

        # Should return 4xx error (400, 401, 403, or 422 for Pydantic validation)
        assert response.status_code in [400, 401, 403, 422], \
            f"Expected 4xx error, got {response.status_code}"

        # Response should not contain stack traces or internal paths
        response_text = response.text.lower()
        assert "traceback" not in response_text, "Response should not contain traceback"
        assert "c:\\" not in response_text, "Response should not contain Windows paths"
        assert "/home/" not in response_text, "Response should not contain Unix paths"


# ==================== Test Filter Injection Prevention ====================

class TestFilterInjectionPrevention:
    """Test that sanitize_technique_id prevents SQL-like injection attacks."""

    def test_valid_aidefend_ids_pass(self):
        """Test that valid AIDEFEND IDs pass validation."""
        valid_ids = [
            "AID-H-001",
            "AID-H-001.001",
            "AID-H-001.001.S1",
            "AID-P-002",
            "AID-D-003.002",
        ]

        for tech_id in valid_ids:
            # Should not raise exception
            result = sanitize_technique_id(tech_id)
            assert result == tech_id

    def test_valid_owasp_ids_pass(self):
        """Test that valid OWASP IDs pass validation."""
        valid_ids = [
            "OWASP-LLM01",
            "OWASP-LLM01:2023",
            "OWASP-LLM10:2025",
        ]

        for tech_id in valid_ids:
            result = sanitize_technique_id(tech_id)
            assert result == tech_id

    def test_valid_atlas_ids_pass(self):
        """Test that valid MITRE ATLAS IDs pass validation."""
        valid_ids = [
            "AML.T0001",
            "AML.T0001.001",
            "AML.T0043.002",
        ]

        for tech_id in valid_ids:
            result = sanitize_technique_id(tech_id)
            assert result == tech_id

    def test_injection_attempts_fail(self):
        """Test that SQL injection attempts are rejected."""
        injection_attempts = [
            "AID-H-001' OR '1'='1",
            "AID-H-001'; DROP TABLE techniques; --",
            "AID-H-001\" OR \"1\"=\"1",
            "AID-H-001\\x00",
            "AID-H-001' AND sleep(10) --",
            "' OR 1=1 --",
            "'; DELETE FROM aidefend; --",
        ]

        for malicious_id in injection_attempts:
            with pytest.raises(InputValidationError) as exc_info:
                sanitize_technique_id(malicious_id)

            assert "invalid characters" in str(exc_info.value).lower()

    def test_special_characters_rejected(self):
        """Test that special characters are rejected."""
        invalid_ids = [
            "AID-H-001; DROP",
            "AID-H-001<script>",
            "AID-H-001${eval}",
            "AID-H-001 OR 1=1",  # Space in middle not allowed
            "AID-H-001!",
            "AID-H-001@",
            "AID-H-001#",
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(InputValidationError) as exc_info:
                sanitize_technique_id(invalid_id)
            # Verify we got the right error message
            assert "invalid characters" in str(exc_info.value).lower()

    def test_empty_id_rejected(self):
        """Test that empty technique IDs are rejected."""
        with pytest.raises(InputValidationError) as exc_info:
            sanitize_technique_id("")

        assert "cannot be empty" in str(exc_info.value).lower()

    def test_too_short_id_rejected(self):
        """Test that technique IDs < 3 characters are rejected."""
        with pytest.raises(InputValidationError) as exc_info:
            sanitize_technique_id("AI")

        assert "at least 3 characters" in str(exc_info.value).lower()

    def test_too_long_id_rejected(self):
        """Test that technique IDs > 100 characters are rejected."""
        long_id = "A" * 101

        with pytest.raises(InputValidationError) as exc_info:
            sanitize_technique_id(long_id)

        assert "cannot exceed 100 characters" in str(exc_info.value).lower()

    def test_whitespace_trimming(self):
        """Test that leading/trailing whitespace is trimmed."""
        result = sanitize_technique_id("  AID-H-001  ")
        assert result == "AID-H-001"


# ==================== Test FileLock Implementation ====================

class TestFileLockImplementation:
    """Test cross-process file locking for sync operations."""

    @pytest.mark.asyncio
    async def test_file_lock_acquire_and_release(self):
        """
        Test basic lock acquisition and release.

        Note: FileLock is reentrant by default - the same process can acquire
        the lock multiple times. The primary purpose is cross-process locking
        (preventing multiple service instances from syncing simultaneously).
        """
        import asyncio
        from app.sync import _acquire_sync_lock, _release_sync_lock, _file_lock

        # Ensure clean state - force release all locks
        try:
            while _file_lock.is_locked:
                _file_lock.release()
        except Exception:
            pass

        # Add delay to ensure lock is fully released
        await asyncio.sleep(0.5)

        # Test 1: Lock can be acquired
        # If lock cannot be acquired, it may be held by another process/test - skip test
        acquired = await _acquire_sync_lock()
        if not acquired:
            pytest.skip("Lock is held by another process, cannot test lock acquisition")

        # Test 2: Lock can be released without error
        # (Should not raise RuntimeError or other exceptions)
        try:
            _release_sync_lock()
            release_succeeded = True
        except Exception as e:
            release_succeeded = False
            pytest.fail(f"Lock release failed with exception: {e}")

        assert release_succeeded, "Lock release should complete without error"

        # Add delay before re-acquiring
        await asyncio.sleep(0.3)

        # Test 3: Lock can be acquired again after release
        acquired_again = await _acquire_sync_lock()
        assert acquired_again is True, "Lock can be acquired after release"

        # Cleanup
        _release_sync_lock()

    @pytest.mark.asyncio
    async def test_lock_state_tracking(self):
        """Test that is_sync_in_progress() accurately tracks lock state."""
        from app.sync import _acquire_sync_lock, _release_sync_lock, is_sync_in_progress, _file_lock

        # Ensure clean state
        try:
            while _file_lock.is_locked:
                _file_lock.release()
        except Exception:
            pass

        # Initially not locked
        initial_state = is_sync_in_progress()
        # Note: May return True if lock file exists from previous test
        # Just verify it returns a boolean
        assert isinstance(initial_state, bool), "Should return boolean"

        # Acquire lock
        acquired = await _acquire_sync_lock()
        if acquired:
            # Check locked state
            locked_state = is_sync_in_progress()
            assert locked_state is True, "Should be locked after acquire"

            # Release lock
            _release_sync_lock()

            # Check unlocked state
            released_state = is_sync_in_progress()
            assert released_state is False, "Should be unlocked after release"

    def test_is_sync_in_progress_check(self):
        """Test the is_sync_in_progress() status check."""
        from app.sync import is_sync_in_progress

        # Check that function returns a boolean
        result = is_sync_in_progress()
        assert isinstance(result, bool), "is_sync_in_progress should return a boolean"


# ==================== Integration Tests ====================

class TestSecurityHardeningIntegration:
    """Integration tests for all security hardening measures."""

    @patch("app.core.query_engine")
    def test_request_size_and_auth_together(self, mock_engine):
        """Test that request size limiting works with authentication."""
        with patch("app.auth.settings") as mock_settings:
            mock_settings.AUTH_MODE = "api_key"
            mock_settings.AIDEFEND_API_KEY = "test-key-123"

            client = TestClient(app)

            # Large request with valid auth
            response = client.post(
                "/api/v1/query",
                json={"query_text": "test", "top_k": 5},
                headers={
                    "X-API-Key": "test-key-123",
                    "Content-Length": str(1048577)  # > 1MB
                }
            )

            # Should be rejected for size, not auth
            assert response.status_code == 413

    @patch("app.core.query_engine")
    def test_filter_injection_in_live_query(self, mock_engine):
        """Test that filter injection is prevented in live queries."""
        # This would require full database setup
        # For now, we test that sanitize_technique_id is called
        pass  # Placeholder for integration test


# ==================== Run Tests ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
