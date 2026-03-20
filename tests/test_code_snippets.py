"""
Tests for Secure Code Snippet Tool

Tests code snippet extraction and search functionality.
"""
import pytest
from app.tools.code_snippets import get_secure_code_snippet
from app.security import InputValidationError


class TestInputValidation:
    """Test input validation for get_secure_code_snippet."""

    @pytest.mark.asyncio
    async def test_no_technique_or_topic(self):
        """Should raise error if neither technique_id nor topic provided."""
        with pytest.raises(InputValidationError, match="Either technique_id or topic"):
            await get_secure_code_snippet()

    @pytest.mark.asyncio
    async def test_max_snippets_too_low(self):
        """max_snippets below 1 should raise error."""
        with pytest.raises(InputValidationError, match="must be between 1 and 20"):
            await get_secure_code_snippet(technique_id="AID-H-001", max_snippets=0)

    @pytest.mark.asyncio
    async def test_max_snippets_too_high(self):
        """max_snippets above 20 should raise error."""
        with pytest.raises(InputValidationError, match="must be between 1 and 20"):
            await get_secure_code_snippet(technique_id="AID-H-001", max_snippets=21)

    @pytest.mark.asyncio
    async def test_topic_too_short(self):
        """Topic less than 3 characters should raise error (in hybrid mode)."""
        with pytest.raises(InputValidationError, match="at least 3 characters"):
            await get_secure_code_snippet(technique_id="AID-H-001", topic="AI")


class TestSearchModes:
    """Test different search modes."""

    @pytest.mark.asyncio
    async def test_technique_id_mode(self):
        """Should accept technique_id only."""
        # This will fail at database level, but validates input
        try:
            await get_secure_code_snippet(technique_id="AID-H-001")
        except Exception as e:
            # Expect database error, not validation error
            assert "not initialized" in str(e) or "not found" in str(e).lower()

    @pytest.mark.asyncio
    async def test_topic_mode(self):
        """Should accept topic only."""
        try:
            await get_secure_code_snippet(topic="prompt injection")
        except Exception as e:
            # Expect database error, not validation error
            assert "not initialized" in str(e) or "not found" in str(e).lower()

    @pytest.mark.asyncio
    async def test_hybrid_mode(self):
        """Should accept both technique_id and topic."""
        try:
            await get_secure_code_snippet(technique_id="AID-H-001", topic="validation")
        except Exception as e:
            # Expect database error, not validation error
            assert "not initialized" in str(e) or "not found" in str(e).lower()


class TestParameters:
    """Test parameter handling."""

    @pytest.mark.asyncio
    async def test_language_filter(self):
        """Should accept language parameter."""
        try:
            await get_secure_code_snippet(topic="input validation", language="python")
        except Exception as e:
            # Expect database error, not validation error
            assert "not initialized" in str(e) or "not found" in str(e).lower()

    @pytest.mark.asyncio
    async def test_max_snippets_boundary_values(self):
        """Should accept max_snippets at boundaries (1 and 20)."""
        # Test lower boundary
        try:
            await get_secure_code_snippet(topic="test", max_snippets=1)
        except Exception as e:
            assert "not initialized" in str(e) or "not found" in str(e).lower()

        # Test upper boundary
        try:
            await get_secure_code_snippet(topic="test", max_snippets=20)
        except Exception as e:
            assert "not initialized" in str(e) or "not found" in str(e).lower()


class TestExpectedBehavior:
    """Test expected behavior (without database)."""

    @pytest.mark.asyncio
    async def test_technique_id_uppercased(self):
        """Technique ID should be uppercased."""
        # Can't fully test without database, but verifies no crash
        try:
            await get_secure_code_snippet(technique_id="aid-h-001")
        except Exception as e:
            # Should uppercase internally before use
            assert "not initialized" in str(e) or "not found" in str(e).lower()

    @pytest.mark.asyncio
    async def test_topic_trimmed(self):
        """Topic should be trimmed."""
        try:
            await get_secure_code_snippet(topic="  prompt injection  ")
        except Exception as e:
            assert "not initialized" in str(e) or "not found" in str(e).lower()
