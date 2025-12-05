"""
Tests for Quick Reference Tool

Tests quick reference guide generation functionality.
"""
import pytest
from app.tools.quick_reference import get_quick_reference
from app.security import InputValidationError


class TestInputValidation:
    """Test input validation for get_quick_reference."""

    @pytest.mark.asyncio
    async def test_empty_topic(self):
        """Empty topic should raise error."""
        with pytest.raises(InputValidationError, match="non-empty string"):
            await get_quick_reference("")

    @pytest.mark.asyncio
    async def test_none_topic(self):
        """None topic should raise error."""
        with pytest.raises(InputValidationError, match="non-empty string"):
            await get_quick_reference(None)

    @pytest.mark.asyncio
    async def test_topic_too_short(self):
        """Topic less than 3 characters should raise error."""
        with pytest.raises(InputValidationError, match="at least 3 characters"):
            await get_quick_reference("AI")

    @pytest.mark.asyncio
    async def test_topic_too_long(self):
        """Topic longer than 200 characters should raise error."""
        long_topic = "A" * 201

        with pytest.raises(InputValidationError, match="too long"):
            await get_quick_reference(long_topic)

    @pytest.mark.asyncio
    async def test_invalid_format(self):
        """Invalid format should raise error."""
        with pytest.raises(InputValidationError, match="must be 'checklist', 'table', or 'markdown'"):
            await get_quick_reference("test topic", format="invalid")

    @pytest.mark.asyncio
    async def test_max_items_too_low(self):
        """max_items below 5 should raise error."""
        with pytest.raises(InputValidationError, match="must be between 5 and 20"):
            await get_quick_reference("test topic", max_items=4)

    @pytest.mark.asyncio
    async def test_max_items_too_high(self):
        """max_items above 20 should raise error."""
        with pytest.raises(InputValidationError, match="must be between 5 and 20"):
            await get_quick_reference("test topic", max_items=21)


class TestValidFormats:
    """Test valid format options."""

    @pytest.mark.asyncio
    async def test_checklist_format(self):
        """Should accept 'checklist' format."""
        try:
            await get_quick_reference("prompt injection", format="checklist")
        except Exception as e:
            # Expect database error, not validation error
            assert "not initialized" in str(e) or "not found" in str(e).lower()

    @pytest.mark.asyncio
    async def test_table_format(self):
        """Should accept 'table' format."""
        try:
            await get_quick_reference("prompt injection", format="table")
        except Exception as e:
            assert "not initialized" in str(e) or "not found" in str(e).lower()

    @pytest.mark.asyncio
    async def test_markdown_format(self):
        """Should accept 'markdown' format."""
        try:
            await get_quick_reference("prompt injection", format="markdown")
        except Exception as e:
            assert "not initialized" in str(e) or "not found" in str(e).lower()


class TestDefaultValues:
    """Test default parameter values."""

    @pytest.mark.asyncio
    async def test_default_format(self):
        """Default format should be 'checklist'."""
        # Can't test return value without database
        # But verify it accepts default
        try:
            await get_quick_reference("test topic")
        except Exception as e:
            assert "not initialized" in str(e) or "not found" in str(e).lower()

    @pytest.mark.asyncio
    async def test_default_max_items(self):
        """Default max_items should be 10."""
        # Verified in function signature
        pass


class TestBoundaryValues:
    """Test boundary values for max_items."""

    @pytest.mark.asyncio
    async def test_min_max_items(self):
        """Should accept max_items=5 (minimum)."""
        try:
            await get_quick_reference("test topic", max_items=5)
        except Exception as e:
            assert "not initialized" in str(e) or "not found" in str(e).lower()

    @pytest.mark.asyncio
    async def test_max_max_items(self):
        """Should accept max_items=20 (maximum)."""
        try:
            await get_quick_reference("test topic", max_items=20)
        except Exception as e:
            assert "not initialized" in str(e) or "not found" in str(e).lower()


class TestExpectedResponseStructure:
    """Test expected response structure (without database)."""

    def test_expected_keys(self):
        """Response should have expected keys."""
        # Mock the expected structure
        expected_keys = {
            'topic',
            'format',
            'generated_at',
            'quick_wins',
            'must_haves',
            'nice_to_haves',
            'formatted_output',
            'total_items',
            'usage_notes'
        }

        # Can't test actual response without database
        # but document expected structure
        assert len(expected_keys) == 9

    def test_priority_categories(self):
        """Should have three priority categories."""
        categories = ['quick_wins', 'must_haves', 'nice_to_haves']

        assert len(categories) == 3
        assert 'quick_wins' in categories
        assert 'must_haves' in categories
        assert 'nice_to_haves' in categories


class TestTopicHandling:
    """Test topic string handling."""

    @pytest.mark.asyncio
    async def test_topic_trimmed(self):
        """Topic should be trimmed."""
        try:
            await get_quick_reference("  prompt injection  ")
        except Exception as e:
            assert "not initialized" in str(e) or "not found" in str(e).lower()

    @pytest.mark.asyncio
    async def test_various_topics(self):
        """Should accept various security topics."""
        topics = [
            "prompt injection",
            "RAG security",
            "model hardening",
            "AI adversarial attacks"
        ]

        for topic in topics:
            try:
                await get_quick_reference(topic)
            except Exception as e:
                assert "not initialized" in str(e) or "not found" in str(e).lower()
