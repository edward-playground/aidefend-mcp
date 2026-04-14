"""
Tests for query_aidefend tool (basic search functionality).

Tests the core search functionality that powers the MCP query tool.
"""
import pytest
from app.core import query_engine
from app.schemas import QueryRequest
from app.security import InputValidationError


class TestQueryInputValidation:
    """Test input validation for query_aidefend."""

    @pytest.mark.asyncio
    async def test_empty_query(self):
        """Empty query should raise InputValidationError."""
        # Input validation happens in QueryRequest model
        with pytest.raises(Exception):  # Pydantic ValidationError
            QueryRequest(query_text="", top_k=5)

    @pytest.mark.asyncio
    async def test_query_too_long(self):
        """Query longer than MAX_TOTAL_QUERY_LENGTH should raise error."""
        from app.config import settings

        # Create query longer than limit
        long_query = "A" * (settings.MAX_TOTAL_QUERY_LENGTH + 1)

        with pytest.raises(Exception):  # Pydantic ValidationError
            QueryRequest(query_text=long_query, top_k=5)

    def test_long_query_within_chunking_limit_is_allowed(self):
        """Long queries within chunking limits should validate successfully."""
        from app.config import settings

        long_query = "A" * (settings.MAX_QUERY_LENGTH + 100)
        request = QueryRequest(query_text=long_query, top_k=5)

        assert len(request.query_text) == len(long_query)

    @pytest.mark.asyncio
    async def test_invalid_top_k_zero(self):
        """top_k of 0 should raise validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            QueryRequest(query_text="test query", top_k=0)

    @pytest.mark.asyncio
    async def test_invalid_top_k_negative(self):
        """Negative top_k should raise validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            QueryRequest(query_text="test query", top_k=-1)

    @pytest.mark.asyncio
    async def test_invalid_top_k_too_large(self):
        """top_k > 20 should raise validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            QueryRequest(query_text="test query", top_k=21)


class TestQueryRequestSchema:
    """Test QueryRequest schema validation."""

    def test_valid_query_request(self):
        """Valid query request should pass validation."""
        request = QueryRequest(query_text="prompt injection", top_k=5)

        assert request.query_text == "prompt injection"
        assert request.top_k == 5

    def test_query_trimmed(self):
        """Query text should be trimmed."""
        request = QueryRequest(query_text="  test query  ", top_k=5)

        # Pydantic should trim whitespace
        assert request.query_text == "test query"

    def test_default_top_k(self):
        """top_k should default to 5."""
        request = QueryRequest(query_text="test")

        assert request.top_k == 5

    def test_top_k_boundary_values(self):
        """Test top_k at boundary values (1 and 20)."""
        # Minimum
        request_min = QueryRequest(query_text="test", top_k=1)
        assert request_min.top_k == 1

        # Maximum
        request_max = QueryRequest(query_text="test", top_k=20)
        assert request_max.top_k == 20


class TestQueryEngineSearch:
    """Test QueryEngine search functionality (without database)."""

    @pytest.mark.asyncio
    async def test_search_without_initialization(self):
        """Search should fail gracefully if engine not initialized."""
        # Don't initialize query_engine
        # Just verify the method exists
        assert hasattr(query_engine, 'search')
        assert callable(query_engine.search)

    @pytest.mark.asyncio
    async def test_search_method_signature(self):
        """Verify search method has correct signature."""
        import inspect

        sig = inspect.signature(query_engine.search)
        params = list(sig.parameters.keys())

        # Should accept request parameter (QueryRequest object)
        assert 'request' in params


class TestQuerySanitization:
    """Test query text sanitization."""

    def test_query_with_special_characters(self):
        """Query with safe special characters should be allowed."""
        # These should be safe
        safe_queries = [
            "prompt injection",
            "What is RAG?",
            "How to defend against LLM01",
            "Model poisoning (MITRE ATLAS)",
            "Input validation - best practices"
        ]

        for query in safe_queries:
            request = QueryRequest(query_text=query, top_k=5)
            assert request.query_text == query

    def test_query_with_newlines(self):
        """Query with newlines should be handled."""
        query_with_newlines = "prompt\ninjection\nattack"
        request = QueryRequest(query_text=query_with_newlines, top_k=5)

        # Pydantic should preserve or normalize the query
        assert "prompt" in request.query_text
        assert "injection" in request.query_text


class TestQueryResponseStructure:
    """Test expected response structure from query (without database)."""

    def test_expected_response_format(self):
        """Document expected response structure."""
        # Mock expected structure
        expected_keys = {'results', 'total', 'query_text', 'top_k'}

        # This is the expected structure from search()
        mock_response = {
            "results": [],
            "total": 0,
            "query_text": "test",
            "top_k": 5
        }

        assert set(mock_response.keys()) == expected_keys

    def test_result_item_structure(self):
        """Document expected structure of result items."""
        # Each result should have these fields
        expected_fields = {
            'source_id', 'name', 'tactic', 'type',
            'description', 'score', 'pillar', 'phase'
        }

        # Mock result item
        mock_result = {
            "source_id": "AID-H-001",
            "name": "Input Validation",
            "tactic": "Harden",
            "type": "technique",
            "description": "Validate all inputs...",
            "score": 0.85,
            "pillar": "prevent",
            "phase": "development"
        }

        assert expected_fields.issubset(set(mock_result.keys()))


class TestQueryBehavior:
    """Test query behavior and edge cases."""

    def test_min_query_length(self):
        """Queries should have minimum length requirement of 3 characters."""
        # Query with less than 3 characters should fail
        short_query = "AI"  # Only 2 characters

        # Should raise ValidationError (min_length=3)
        with pytest.raises(Exception):  # Pydantic ValidationError
            QueryRequest(query_text=short_query, top_k=5)

        # Query with exactly 3 characters should pass
        valid_short_query = "RAG"
        request = QueryRequest(query_text=valid_short_query, top_k=5)
        assert request.query_text == valid_short_query

    def test_unicode_query(self):
        """Queries with unicode characters should be handled."""
        unicode_queries = [
            "提示注入攻擊",  # Chinese
            "モデル中毒",      # Japanese
            "프롬프트 주입",   # Korean
            "حقن السريع"      # Arabic
        ]

        for query in unicode_queries:
            request = QueryRequest(query_text=query, top_k=5)
            assert request.query_text == query


class TestQueryIntegrationPoints:
    """Test integration points with other components."""

    @pytest.mark.asyncio
    async def test_query_engine_initialization_check(self):
        """Verify query engine has initialization state tracking."""
        # QueryEngine only exposes is_ready property (not is_initialized)
        assert hasattr(query_engine, 'is_ready')
        assert isinstance(query_engine.is_ready, bool)

    @pytest.mark.asyncio
    async def test_query_engine_has_initialize_method(self):
        """Verify query engine has initialize method."""
        assert hasattr(query_engine, 'initialize')
        assert callable(query_engine.initialize)
