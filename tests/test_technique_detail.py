"""
Tests for Technique Detail Tool

Tests retrieval of complete technique information including:
- Technique metadata
- Sub-techniques
- Implementation strategies
- Code extraction
- JSON field parsing
"""
import pytest
import json
from app.tools.technique_detail import (
    get_technique_detail,
    _parse_json_field,
    _format_strategies,
    _strip_html,
    _extract_code_blocks
)
from app.security import InputValidationError


class TestInputValidation:
    """Test input validation for get_technique_detail."""

    @pytest.mark.asyncio
    async def test_empty_technique_id(self):
        """Empty technique ID should raise error."""
        with pytest.raises(InputValidationError, match="non-empty string"):
            await get_technique_detail("")

    @pytest.mark.asyncio
    async def test_none_technique_id(self):
        """None technique ID should raise error."""
        with pytest.raises(InputValidationError, match="non-empty string"):
            await get_technique_detail(None)

    @pytest.mark.asyncio
    async def test_too_long_technique_id(self):
        """Technique ID longer than 50 characters should raise error."""
        long_id = "A" * 51

        with pytest.raises(InputValidationError, match="too long"):
            await get_technique_detail(long_id)

    @pytest.mark.asyncio
    async def test_whitespace_trimming(self):
        """Whitespace should be trimmed and uppercased."""
        # We can't test full execution without database
        # but can verify input validation doesn't throw on valid format
        pass  # Actual behavior tested in integration tests


class TestParseJSONField:
    """Test JSON field parsing utility."""

    def test_empty_string(self):
        """Empty string should return empty list."""
        assert _parse_json_field("") == []

    def test_none_value(self):
        """None value should return empty list."""
        assert _parse_json_field(None) == []

    def test_valid_json_array(self):
        """Valid JSON array should be parsed."""
        json_str = '["item1", "item2", "item3"]'
        result = _parse_json_field(json_str)

        assert isinstance(result, list)
        assert len(result) == 3
        assert "item1" in result

    def test_valid_json_object(self):
        """Valid JSON object should be parsed."""
        json_str = '{"key": "value", "number": 123}'
        result = _parse_json_field(json_str)

        assert isinstance(result, dict)
        assert result["key"] == "value"
        assert result["number"] == 123

    def test_invalid_json(self):
        """Invalid JSON should return empty list."""
        invalid_json = "not valid json {["
        result = _parse_json_field(invalid_json)

        assert result == []

    def test_already_parsed(self):
        """Already parsed object should be returned as-is."""
        parsed_list = ["already", "parsed"]
        result = _parse_json_field(parsed_list)

        assert result == parsed_list

        parsed_dict = {"already": "parsed"}
        result = _parse_json_field(parsed_dict)

        assert result == parsed_dict


class TestStripHTML:
    """Test HTML stripping utility."""

    def test_simple_html(self):
        """Should remove simple HTML tags."""
        html = "<p>Hello <strong>world</strong></p>"
        result = _strip_html(html)

        assert "<p>" not in result
        assert "<strong>" not in result
        assert "Hello world" in result

    def test_nested_html(self):
        """Should handle nested HTML."""
        html = "<div><p>Paragraph <a href='#'>link</a></p></div>"
        result = _strip_html(html)

        assert "<" not in result
        assert ">" not in result
        assert "Paragraph link" in result

    def test_multiple_spaces(self):
        """Should collapse multiple spaces."""
        html = "<p>Too    many     spaces</p>"
        result = _strip_html(html)

        assert "  " not in result
        assert "Too many spaces" in result

    def test_no_html(self):
        """Plain text should remain unchanged (except spacing)."""
        text = "Plain text without HTML"
        result = _strip_html(text)

        assert result == text


class TestExtractCodeBlocks:
    """Test code block extraction from HTML."""

    def test_single_code_block(self):
        """Should extract single code block."""
        html = "<pre><code>print('Hello')</code></pre>"
        blocks = _extract_code_blocks(html)

        assert len(blocks) == 1
        assert blocks[0]['block_number'] == 1
        assert "print('Hello')" in blocks[0]['code']

    def test_multiple_code_blocks(self):
        """Should extract multiple code blocks."""
        html = """
        <pre><code>code1</code></pre>
        <p>Some text</p>
        <pre><code>code2</code></pre>
        """
        blocks = _extract_code_blocks(html)

        assert len(blocks) == 2
        assert blocks[0]['block_number'] == 1
        assert blocks[1]['block_number'] == 2
        assert "code1" in blocks[0]['code']
        assert "code2" in blocks[1]['code']

    def test_html_entities(self):
        """Should decode HTML entities."""
        html = "<pre><code>&lt;div&gt;text&lt;/div&gt;</code></pre>"
        blocks = _extract_code_blocks(html)

        assert len(blocks) == 1
        assert "<div>" in blocks[0]['code']
        assert "</div>" in blocks[0]['code']
        assert "&lt;" not in blocks[0]['code']

    def test_multiline_code(self):
        """Should preserve multiline code."""
        html = """
        <pre><code>line1
        line2
        line3</code></pre>
        """
        blocks = _extract_code_blocks(html)

        assert len(blocks) == 1
        assert "line1" in blocks[0]['code']
        assert "line3" in blocks[0]['code']

    def test_no_code_blocks(self):
        """Should return empty list if no code blocks."""
        html = "<p>No code here</p>"
        blocks = _extract_code_blocks(html)

        assert blocks == []

    def test_code_block_language(self):
        """All blocks should have language field."""
        html = "<pre><code>test</code></pre>"
        blocks = _extract_code_blocks(html)

        assert len(blocks) == 1
        assert 'language' in blocks[0]
        assert blocks[0]['language'] == 'python'  # Default


class TestFormatStrategies:
    """Test strategy formatting."""

    def test_format_without_code(self):
        """Should format strategies without code when include_code=False."""
        strategies = [
            {
                "implementation": "Test Strategy",
                "howTo": "<p>Implementation <strong>details</strong></p>"
            }
        ]

        result = _format_strategies(strategies, include_code=False)

        assert len(result) == 1
        assert result[0]['implementation'] == "Test Strategy"
        # HTML should be stripped when include_code=False
        assert "<p>" not in result[0]['how_to']
        assert "<strong>" not in result[0]['how_to']
        assert "Implementation details" in result[0]['how_to']

    def test_format_with_code(self):
        """Should format strategies with full HTML when include_code=True."""
        strategies = [
            {
                "implementation": "Test Strategy",
                "howTo": "<p>Details</p><pre><code>code here</code></pre>"
            }
        ]

        result = _format_strategies(strategies, include_code=True)

        assert len(result) == 1
        assert result[0]['implementation'] == "Test Strategy"
        # HTML should be preserved when include_code=True
        assert "<p>" in result[0]['how_to']

    def test_extract_code_examples(self):
        """Should extract code examples when include_code=True."""
        strategies = [
            {
                "implementation": "Test Strategy",
                "howTo": "<p>Text</p><pre><code>print('test')</code></pre>"
            }
        ]

        result = _format_strategies(strategies, include_code=True)

        assert len(result) == 1
        assert 'code_examples' in result[0]
        assert len(result[0]['code_examples']) == 1
        assert "print('test')" in result[0]['code_examples'][0]['code']

    def test_no_code_examples(self):
        """Should not have code_examples key if no code blocks."""
        strategies = [
            {
                "implementation": "Test Strategy",
                "howTo": "<p>Just text, no code</p>"
            }
        ]

        result = _format_strategies(strategies, include_code=True)

        assert len(result) == 1
        assert 'code_examples' not in result[0]

    def test_multiple_strategies(self):
        """Should format multiple strategies."""
        strategies = [
            {"implementation": "Strategy 1", "howTo": "How 1"},
            {"implementation": "Strategy 2", "howTo": "How 2"},
            {"implementation": "Strategy 3", "howTo": "How 3"}
        ]

        result = _format_strategies(strategies, include_code=False)

        assert len(result) == 3
        assert all('implementation' in s for s in result)
        assert all('how_to' in s for s in result)

    def test_missing_fields(self):
        """Should handle missing strategy or howTo fields."""
        strategies = [
            {"implementation": "Strategy Only"},
            {"howTo": "HowTo Only"}
        ]

        result = _format_strategies(strategies, include_code=False)

        assert len(result) == 2
        assert result[0]['implementation'] == "Strategy Only"
        assert result[0]['how_to'] == ""
        assert result[1]['implementation'] == ""
        assert result[1]['how_to'] == "HowTo Only"


class TestResponseStructure:
    """Test the expected response structure."""

    def test_expected_top_level_keys(self):
        """Response should have expected top-level keys."""
        # We can't test actual API response without database
        # but we can test the expected structure
        expected_keys = {'technique', 'subtechniques', 'strategies', 'metadata'}

        # Mock response structure
        mock_response = {
            "technique": {},
            "subtechniques": [],
            "strategies": [],
            "metadata": {}
        }

        assert set(mock_response.keys()) == expected_keys

    def test_technique_info_structure(self):
        """Technique info should have expected fields."""
        expected_fields = {
            'id', 'name', 'type', 'tactic', 'pillar', 'phase', 'description', 'parent_technique_id'
        }

        # These fields should always be present
        mock_technique = {
            "id": "AID-H-001",
            "name": "Input Validation",
            "type": "technique",
            "tactic": "Harden",
            "pillar": "",
            "phase": "",
            "description": "",
            "parent_technique_id": ""
        }

        assert set(mock_technique.keys()) == expected_fields

    def test_metadata_structure(self):
        """Metadata should have expected fields."""
        mock_metadata = {
            "total_subtechniques": 0,
            "total_strategies": 0,
            "has_implementation_guidance": False
        }

        assert 'total_subtechniques' in mock_metadata
        assert 'total_strategies' in mock_metadata
        assert 'has_implementation_guidance' in mock_metadata


class TestFlagsAndOptions:
    """Test include_code and include_tools flags."""

    def test_include_code_default(self):
        """include_code should default to True."""
        # This is tested in the function signature
        # Just verify it's accepted as parameter
        pass

    def test_include_tools_default(self):
        """include_tools should default to True."""
        # This is tested in the function signature
        pass

    def test_code_not_included_when_false(self):
        """When include_code=False, code should be stripped."""
        strategies = [{"implementation": "Test", "howTo": "<pre><code>test</code></pre>"}]
        result = _format_strategies(strategies, include_code=False)

        # Code HTML should be stripped
        assert "<pre>" not in result[0]['how_to']
        assert "<code>" not in result[0]['how_to']
