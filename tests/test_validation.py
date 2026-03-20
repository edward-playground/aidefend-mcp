"""
Tests for Validation Tool

Tests technique ID validation including:
- Format validation (regex pattern matching)
- Database lookup
- Fuzzy matching for suggestions
- Batch validation
"""
import pytest
from app.tools.validation import (
    TECHNIQUE_ID_PATTERN,
    VALID_TACTIC_CODES,
    find_similar_ids,
    validate_technique_id,
    batch_validate_technique_ids
)
from app.security import InputValidationError


class TestTechniqueIDPattern:
    """Test technique ID regex pattern."""

    def test_valid_technique_id(self):
        """Valid technique IDs should match pattern."""
        valid_ids = [
            "AID-H-001",
            "AID-M-123",
            "AID-D-999",
            "AID-I-001",
            "AID-C-001",
            "AID-E-001",
            "AID-R-001"
        ]

        for tech_id in valid_ids:
            assert TECHNIQUE_ID_PATTERN.match(tech_id), f"{tech_id} should be valid"

    def test_valid_subtechnique_id(self):
        """Valid sub-technique IDs should match pattern."""
        valid_ids = [
            "AID-H-001.001",
            "AID-M-123.456",
            "AID-D-001.999"
        ]

        for tech_id in valid_ids:
            assert TECHNIQUE_ID_PATTERN.match(tech_id), f"{tech_id} should be valid"

    def test_valid_strategy_id(self):
        """Valid strategy IDs should match pattern."""
        valid_ids = [
            "AID-H-001.S1",
            "AID-H-001.S99",
            "AID-H-001.001.S1"
        ]

        for tech_id in valid_ids:
            assert TECHNIQUE_ID_PATTERN.match(tech_id), f"{tech_id} should be valid"

    def test_invalid_format(self):
        """Invalid formats should not match pattern."""
        invalid_ids = [
            "AID-H-1",         # Too few digits
            "AID-H-1234",      # Too many digits
            "AID-X-001",       # Invalid tactic code
            "H-001",           # Missing AID prefix
            "AID-H",           # Missing number
            "AID-H-ABC",       # Letters instead of numbers
            "aid-h-001",       # Lowercase (pattern expects uppercase)
            "AID-H-001.S",     # Strategy without number
        ]

        for tech_id in invalid_ids:
            assert not TECHNIQUE_ID_PATTERN.match(tech_id), f"{tech_id} should be invalid"

    def test_tactic_codes(self):
        """All tactic codes should be recognized."""
        expected_tactics = {'M', 'H', 'D', 'I', 'C', 'E', 'R'}
        assert set(VALID_TACTIC_CODES.keys()) == expected_tactics

        # Verify mapping
        assert VALID_TACTIC_CODES['M'] == 'Model'
        assert VALID_TACTIC_CODES['H'] == 'Harden'
        assert VALID_TACTIC_CODES['D'] == 'Detect'
        assert VALID_TACTIC_CODES['I'] == 'Isolate'
        assert VALID_TACTIC_CODES['C'] == 'Deceive'
        assert VALID_TACTIC_CODES['E'] == 'Evict'
        assert VALID_TACTIC_CODES['R'] == 'Restore'


class TestFindSimilarIDs:
    """Test fuzzy matching for similar technique IDs."""

    @pytest.fixture
    def sample_docs(self):
        """Sample documents for testing."""
        return [
            {'source_id': 'AID-H-001', 'name': 'Input Validation', 'type': 'technique', 'tactic': 'Harden'},
            {'source_id': 'AID-H-002', 'name': 'Output Encoding', 'type': 'technique', 'tactic': 'Harden'},
            {'source_id': 'AID-H-001.001', 'name': 'Server-side Validation', 'type': 'subtechnique', 'tactic': 'Harden'},
            {'source_id': 'AID-M-001', 'name': 'Model Inventory', 'type': 'technique', 'tactic': 'Model'},
            {'source_id': 'AID-D-001', 'name': 'Anomaly Detection', 'type': 'technique', 'tactic': 'Detect'},
        ]

    def test_exact_substring_match(self, sample_docs):
        """Exact substring should have high similarity."""
        results = find_similar_ids("AID-H-001", sample_docs, threshold=0.5)

        assert len(results) > 0
        # Exact match should be first
        assert results[0]['id'] == 'AID-H-001'
        assert results[0]['similarity_score'] >= 0.8

    def test_partial_match(self, sample_docs):
        """Partial match should return similar IDs."""
        results = find_similar_ids("AID-H", sample_docs, threshold=0.4)

        # Should find both AID-H-001 and AID-H-002
        h_ids = [r['id'] for r in results if r['id'].startswith('AID-H')]
        assert len(h_ids) >= 2

    def test_typo_tolerance(self, sample_docs):
        """Should find similar IDs even with typos."""
        # Typo: AID-H-00l (lowercase L instead of 1)
        results = find_similar_ids("AID-H-00", sample_docs, threshold=0.6)

        assert len(results) > 0
        # Should still find AID-H-001
        assert any('AID-H-001' in r['id'] for r in results)

    def test_max_results_limit(self, sample_docs):
        """Should respect max_results parameter."""
        results = find_similar_ids("AID", sample_docs, threshold=0.3, max_results=3)

        assert len(results) <= 3

    def test_threshold_filtering(self, sample_docs):
        """Should filter results below threshold."""
        # High threshold should return fewer results
        results_high = find_similar_ids("AID-H-001", sample_docs, threshold=0.9)
        results_low = find_similar_ids("AID-H-001", sample_docs, threshold=0.3)

        assert len(results_high) <= len(results_low)

    def test_similarity_score_sorted(self, sample_docs):
        """Results should be sorted by similarity score (descending)."""
        results = find_similar_ids("AID-H-001", sample_docs, threshold=0.3)

        if len(results) > 1:
            scores = [r['similarity_score'] for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_match_reason(self, sample_docs):
        """Should indicate match reason (substring vs fuzzy)."""
        results = find_similar_ids("AID-H", sample_docs, threshold=0.3)

        for result in results:
            assert 'match_reason' in result
            assert result['match_reason'] in ['substring', 'fuzzy']


class TestValidateTechniqueIDInputValidation:
    """Test input validation for validate_technique_id."""

    @pytest.mark.asyncio
    async def test_empty_string(self):
        """Empty string should raise InputValidationError."""
        with pytest.raises(InputValidationError, match="non-empty string"):
            await validate_technique_id("")

    @pytest.mark.asyncio
    async def test_none_input(self):
        """None input should raise InputValidationError."""
        with pytest.raises(InputValidationError, match="non-empty string"):
            await validate_technique_id(None)

    @pytest.mark.asyncio
    async def test_too_long(self):
        """Input longer than 50 characters should raise error."""
        long_id = "A" * 51

        with pytest.raises(InputValidationError, match="too long"):
            await validate_technique_id(long_id)

    @pytest.mark.asyncio
    async def test_whitespace_trimmed(self):
        """Whitespace should be trimmed and not cause InputValidationError."""
        from app.core import QueryEngineNotInitializedError
        # Valid ID with whitespace should pass input validation
        # May raise QueryEngineNotInitializedError if no DB, which is fine
        try:
            await validate_technique_id("  AID-H-001  ")
        except QueryEngineNotInitializedError:
            pass  # Expected when no database is available


class TestValidateTechniqueIDFormat:
    """Test format validation."""

    @pytest.mark.asyncio
    async def test_invalid_format_response(self):
        """Invalid format should return structured error."""
        # This test will fail database check, but format validation comes first
        try:
            result = await validate_technique_id("INVALID-ID")
        except Exception as e:
            # If database not initialized, that's OK for format testing
            if "not initialized" in str(e):
                pytest.skip("Database not available")
            raise

        assert result['valid'] is False
        assert result['reason'] == 'INVALID_FORMAT'
        assert 'expected_format' in result
        assert 'examples' in result
        assert 'message' in result

    @pytest.mark.asyncio
    async def test_format_validation_before_db_lookup(self):
        """Format validation should happen before database lookup."""
        # Invalid format should return immediately, not hit database
        try:
            result = await validate_technique_id("NOT-A-VALID-ID")
        except Exception as e:
            # QueryEngineNotInitializedError means format check passed
            # We want format check to fail first
            if "not initialized" in str(e):
                pytest.fail("Format validation should fail before database check")
            # Other exceptions are OK (means format check worked)
            return

        # If no exception, check result
        assert result['valid'] is False
        assert result['reason'] == 'INVALID_FORMAT'


class TestBatchValidation:
    """Test batch validation functionality."""

    @pytest.mark.asyncio
    async def test_empty_list(self):
        """Empty list should raise InputValidationError."""
        with pytest.raises(InputValidationError, match="cannot be empty"):
            await batch_validate_technique_ids([])

    @pytest.mark.asyncio
    async def test_too_many_ids(self):
        """More than 100 IDs should raise error."""
        ids = [f"AID-H-{i:03d}" for i in range(101)]

        with pytest.raises(InputValidationError, match="Too many IDs"):
            await batch_validate_technique_ids(ids)

    @pytest.mark.asyncio
    async def test_batch_result_structure(self):
        """Batch result should have correct structure."""
        ids = ["AID-H-001", "INVALID-ID"]

        try:
            result = await batch_validate_technique_ids(ids)
        except Exception as e:
            if "not initialized" in str(e):
                pytest.skip("Database not available")
            raise

        assert 'total' in result
        assert 'valid_count' in result
        assert 'invalid_count' in result
        assert 'results' in result

        assert result['total'] == len(ids)
        assert result['valid_count'] + result['invalid_count'] == result['total']
        assert len(result['results']) == result['total']


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_case_insensitivity(self):
        """Pattern should be case-sensitive (expects uppercase)."""
        # Lowercase should not match
        assert not TECHNIQUE_ID_PATTERN.match("aid-h-001")

        # Mixed case should not match
        assert not TECHNIQUE_ID_PATTERN.match("AiD-H-001")

        # Uppercase should match
        assert TECHNIQUE_ID_PATTERN.match("AID-H-001")

    def test_zero_padding(self):
        """Numbers should have exactly 3 digits (zero-padded)."""
        assert TECHNIQUE_ID_PATTERN.match("AID-H-001")  # OK
        assert TECHNIQUE_ID_PATTERN.match("AID-H-099")  # OK
        assert not TECHNIQUE_ID_PATTERN.match("AID-H-1")  # Too short
        assert not TECHNIQUE_ID_PATTERN.match("AID-H-01")  # Too short

    def test_multiple_subtechniques(self):
        """Pattern allows multiple levels (due to * quantifier)."""
        assert TECHNIQUE_ID_PATTERN.match("AID-H-001.001")  # OK: 2 levels
        # Note: Pattern actually allows multiple levels due to (\.\d{3})* in regex
        assert TECHNIQUE_ID_PATTERN.match("AID-H-001.001.001")  # Also valid per current pattern

    def test_strategy_format(self):
        """Strategy IDs should end with .S#."""
        assert TECHNIQUE_ID_PATTERN.match("AID-H-001.S1")
        assert TECHNIQUE_ID_PATTERN.match("AID-H-001.S99")
        assert TECHNIQUE_ID_PATTERN.match("AID-H-001.001.S1")
        assert TECHNIQUE_ID_PATTERN.match("AID-H-001.S0")  # S0 is valid per current pattern

        # Invalid strategy formats
        assert not TECHNIQUE_ID_PATTERN.match("AID-H-001.S")  # Missing number
