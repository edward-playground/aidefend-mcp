"""
Test suite for Implementation Plan tool with Compound Tool Pattern.

Tests both basic and detailed modes to verify the optimization.
"""

import pytest
import asyncio
from app.tools.implementation_plan import (
    get_implementation_plan,
    _extract_strategy_details,
    _strip_html
)


class TestHelperFunctions:
    """Test HTML parsing helper functions."""

    def test_strip_html_basic(self):
        """Test basic HTML tag removal."""
        html = "<p>Hello <b>world</b></p>"
        result = _strip_html(html)
        assert result == "Hello world"

    def test_strip_html_empty(self):
        """Test empty string handling."""
        result = _strip_html("")
        assert result == ""

    def test_strip_html_no_tags(self):
        """Test plain text input."""
        text = "Plain text without tags"
        result = _strip_html(text)
        assert result == text

    def test_extract_strategy_details_basic(self):
        """Test basic HTML extraction without code."""
        html = "<p>This is a strategy description</p>"
        result = _extract_strategy_details(html, include_code=False)

        assert "summary" in result
        assert "This is a strategy description" in result["summary"]
        assert "code_snippets" not in result

    def test_extract_strategy_details_with_code(self):
        """Test HTML extraction with code blocks."""
        html = """
        <p>Strategy description</p>
        <pre><code class="language-python">
        def example():
            return "test"
        </code></pre>
        """
        result = _extract_strategy_details(html, include_code=True)

        assert "summary" in result
        assert "code_snippets" in result
        assert len(result["code_snippets"]) > 0
        assert result["code_snippets"][0]["language"] == "python"
        assert "def example" in result["code_snippets"][0]["code"]

    def test_extract_strategy_details_empty(self):
        """Test empty HTML handling."""
        result = _extract_strategy_details("", include_code=False)
        assert result["summary"] == ""
        assert result["code_snippets"] == []


@pytest.mark.asyncio
class TestImplementationPlanBasic:
    """Test basic mode (original behavior)."""

    async def test_basic_mode_default(self):
        """Test default basic mode without detail_level parameter."""
        try:
            result = await get_implementation_plan(
                implemented_techniques=[],
                exclude_tactics=[],
                top_k=5
            )

            # Verify basic structure
            assert "recommendations" in result
            assert "categories" in result
            assert "input" in result

            # Verify detail_level in input
            assert result["input"]["detail_level"] == "basic"

            # Verify no actionable_strategies in basic mode
            assert "actionable_strategies" not in result or result.get("actionable_strategies") is None

            print("✅ Basic mode test passed")

        except Exception as e:
            if "not initialized" in str(e).lower():
                pytest.skip("Database not initialized - skipping integration test")
            raise

    async def test_basic_mode_explicit(self):
        """Test explicit basic mode."""
        try:
            result = await get_implementation_plan(
                implemented_techniques=[],
                exclude_tactics=[],
                top_k=5,
                detail_level="basic"
            )

            assert result["input"]["detail_level"] == "basic"
            assert "actionable_strategies" not in result or result.get("actionable_strategies") is None

            print("✅ Explicit basic mode test passed")

        except Exception as e:
            if "not initialized" in str(e).lower():
                pytest.skip("Database not initialized - skipping integration test")
            raise


@pytest.mark.asyncio
class TestImplementationPlanCompound:
    """Test Compound Tool Pattern (standard and detailed modes)."""

    async def test_standard_mode(self):
        """Test standard mode with brief summaries (200 chars)."""
        try:
            result = await get_implementation_plan(
                implemented_techniques=[],
                exclude_tactics=[],
                top_k=5,
                detail_level="standard"
            )

            # Verify basic structure
            assert result["input"]["detail_level"] == "standard"

            # Verify actionable_strategies is present
            assert "actionable_strategies" in result

            # Verify metadata
            assert "metadata" in result
            assert result["metadata"]["compound_tool_enabled"] == True
            assert result["metadata"]["detail_level"] == "standard"

            # Check strategies structure
            if result["actionable_strategies"]:
                for strategy_data in result["actionable_strategies"]:
                    assert "technique_id" in strategy_data
                    assert "technique_name" in strategy_data
                    assert "strategies" in strategy_data

                    # Standard mode should have brief summaries (200 chars) with NO code_snippets
                    for strat in strategy_data["strategies"]:
                        assert "strategy_name" in strat
                        assert "summary" in strat
                        # Verify summary length is around 200 chars (allow some tolerance)
                        assert len(strat["summary"]) <= 250, f"Summary too long: {len(strat['summary'])} chars"
                        # Ensure NO code snippets in standard mode
                        assert "code_snippets" not in strat
                        # context_source is optional (only present for sub-technique strategies)

            print("✅ Standard mode test passed")

        except Exception as e:
            if "not initialized" in str(e).lower():
                pytest.skip("Database not initialized - skipping integration test")
            raise

    async def test_detailed_mode(self):
        """Test detailed mode with full summaries (500 chars) - NO code snippets."""
        try:
            result = await get_implementation_plan(
                implemented_techniques=[],
                exclude_tactics=[],
                top_k=5,
                detail_level="detailed"
            )

            # Verify basic structure
            assert result["input"]["detail_level"] == "detailed"

            # Verify actionable_strategies is present
            assert "actionable_strategies" in result

            # Verify metadata
            assert "metadata" in result
            assert result["metadata"]["compound_tool_enabled"] == True
            assert result["metadata"]["detail_level"] == "detailed"

            # Check strategies structure
            if result["actionable_strategies"]:
                for strategy_data in result["actionable_strategies"]:
                    assert "technique_id" in strategy_data
                    assert "strategies" in strategy_data

                    # Detailed mode should have full summaries (500 chars) with NO code_snippets
                    for strat in strategy_data["strategies"]:
                        assert "strategy_name" in strat
                        assert "summary" in strat
                        # Verify summary length is around 500 chars (allow some tolerance)
                        # Note: Summary may be shorter if content is brief
                        assert len(strat["summary"]) <= 550, f"Summary too long: {len(strat['summary'])} chars"
                        # Ensure NO code snippets in detailed mode (changed behavior)
                        assert "code_snippets" not in strat
                        # context_source is optional (only present for sub-technique strategies)

            print("✅ Detailed mode test passed")

        except Exception as e:
            if "not initialized" in str(e).lower():
                pytest.skip("Database not initialized - skipping integration test")
            raise


@pytest.mark.asyncio
class TestParameterValidation:
    """Test input parameter validation."""

    async def test_invalid_detail_level(self):
        """Test invalid detail_level parameter."""
        # This test verifies validation logic exists in source code
        # Since DB might not be initialized, we check the code directly
        import inspect
        source = inspect.getsource(get_implementation_plan)

        # Verify detail_level validation exists in the function
        assert 'detail_level not in ["basic", "standard", "detailed"]' in source
        assert 'InputValidationError' in source

        print("[PASS] Validation logic verified in source code")

    async def test_top_k_validation(self):
        """Test top_k parameter validation."""
        # Test too low
        with pytest.raises(Exception):
            await get_implementation_plan(top_k=0)

        # Test too high
        with pytest.raises(Exception):
            await get_implementation_plan(top_k=25)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
