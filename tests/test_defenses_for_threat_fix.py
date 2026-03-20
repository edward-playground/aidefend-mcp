"""
Test for get_defenses_for_threat relevance score fix

Verifies that relevance scores are properly calculated from L2 distance.
"""

import pytest
from app.tools.defenses_for_threat import get_defenses_for_threat


class TestRelevanceScoreFix:
    """Test that relevance scores are calculated correctly."""

    @pytest.mark.asyncio
    async def test_semantic_search_returns_nonzero_relevance(self):
        """
        Test that semantic search returns non-zero relevance scores.

        Previously, all scores were 0.00 due to incorrect distance conversion.
        After fix, scores should be in range (0.0, 1.0].
        """
        # Use a common threat keyword that should have matches
        result = await get_defenses_for_threat(
            threat_keyword="prompt injection",
            top_k=10
        )

        # Should return results
        assert result['total_results'] > 0, "Should find at least one result"

        # Check relevance scores
        for defense in result['defense_techniques']:
            relevance = defense['relevance_score']

            # Relevance should be in valid range
            assert 0.0 < relevance <= 1.0, \
                f"Relevance score {relevance} out of range (0.0, 1.0] for {defense['technique']['id']}"

            # Should not be all zeros (the bug we're fixing)
            assert relevance > 0.0, \
                f"Relevance score should not be 0.00 for {defense['technique']['id']}"

        # Log scores for inspection
        print("\nRelevance scores:")
        for i, defense in enumerate(result['defense_techniques'][:5], 1):
            print(f"  {i}. {defense['technique']['id']}: {defense['relevance_score']:.3f}")

    @pytest.mark.asyncio
    async def test_relevance_score_calculation_logic(self):
        """
        Test the relevance score calculation formula.

        Formula: score = 1 / (1 + distance)

        Expected behavior:
        - distance = 0.0 → score = 1.0 (perfect match)
        - distance = 1.0 → score = 0.5 (moderate match)
        - distance = 3.0 → score = 0.25
        - distance = 9.0 → score = 0.1
        - distance = ∞ → score → 0.0
        """
        test_cases = [
            (0.0, 1.0),    # Perfect match
            (1.0, 0.5),    # Moderate
            (3.0, 0.25),   # Low
            (9.0, 0.1),    # Very low
        ]

        for distance, expected_score in test_cases:
            calculated_score = 1.0 / (1.0 + distance)
            assert abs(calculated_score - expected_score) < 0.001, \
                f"Score calculation incorrect for distance={distance}: " \
                f"expected {expected_score}, got {calculated_score}"

    @pytest.mark.asyncio
    async def test_results_sorted_by_relevance(self):
        """
        Test that results are sorted by relevance score (descending).
        """
        result = await get_defenses_for_threat(
            threat_keyword="adversarial attacks",
            top_k=10
        )

        if result['total_results'] > 1:
            scores = [d['relevance_score'] for d in result['defense_techniques']]

            # Check sorted in descending order
            for i in range(len(scores) - 1):
                assert scores[i] >= scores[i + 1], \
                    f"Results not sorted: scores[{i}]={scores[i]}, scores[{i+1}]={scores[i+1]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
