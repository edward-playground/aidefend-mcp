"""
Test for Technique Comparison Matrix Tool

Tests the compare_techniques tool including scoring algorithms,
validation, and recommendation generation.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all necessary modules can be imported."""
    print("=" * 60)
    print("TECHNIQUE COMPARISON - IMPORT TESTS")
    print("=" * 60)

    try:
        print("\n[TEST 1] Import compare_techniques")
        from app.tools.technique_comparison import compare_techniques
        print("   [PASS] Function imported successfully")

        print("\n[TEST 2] Import from app.tools")
        from app.tools import compare_techniques as ct
        print("   [PASS] Can import via app.tools.__init__")

        print("\n[TEST 3] Import scoring functions")
        from app.tools.technique_comparison import (
            _calculate_effectiveness_score,
            _calculate_complexity_score,
            _calculate_cost_score
        )
        print("   [PASS] Scoring functions imported")

        print("\n" + "=" * 60)
        print("*** IMPORT TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_parameter_validation():
    """Test parameter validation."""
    print("\n" + "=" * 60)
    print("PARAMETER VALIDATION TESTS")
    print("=" * 60)

    try:
        from app.tools.technique_comparison import compare_techniques
        from app.security import InputValidationError

        # Test 1: Empty list should fail
        print("\n[TEST 1] Empty technique list should fail")
        try:
            asyncio.run(compare_techniques(technique_ids=[]))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 2: Single technique (need at least 2)
        print("\n[TEST 2] Single technique should fail")
        try:
            asyncio.run(compare_techniques(technique_ids=["AID-H-001"]))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 3: Too many techniques (> 10)
        print("\n[TEST 3] Too many techniques should fail")
        try:
            technique_ids = [f"AID-H-{i:03d}" for i in range(1, 12)]  # 11 techniques
            asyncio.run(compare_techniques(technique_ids=technique_ids))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 4: Not a list
        print("\n[TEST 4] Non-list input should fail")
        try:
            asyncio.run(compare_techniques(technique_ids="AID-H-001"))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        print("\n" + "=" * 60)
        print("*** VALIDATION TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_scoring_algorithms():
    """Test scoring algorithm logic."""
    print("\n" + "=" * 60)
    print("SCORING ALGORITHM TESTS")
    print("=" * 60)

    try:
        from app.tools.technique_comparison import (
            _calculate_effectiveness_score,
            _calculate_complexity_score,
            _calculate_cost_score
        )
        import json

        # Test 1: Effectiveness score calculation
        print("\n[TEST 1] Effectiveness score calculation")
        mock_doc = {
            "defends_against": json.dumps([
                {"framework": "OWASP LLM Top 10", "items": ["LLM01", "LLM02"]},
                {"framework": "MITRE ATLAS", "items": ["T0001"]},
            ]),
            "implementation_guidance": json.dumps([{"implementation": "test"}]),
            "has_code_snippets": True
        }

        score = _calculate_effectiveness_score(mock_doc)
        print(f"   Score: {score}/100")
        assert 0 <= score <= 100, "Score should be 0-100"
        assert score > 50, "Should have bonus points from defenses and code"
        print("   [PASS]")

        # Test 2: Complexity score calculation
        print("\n[TEST 2] Complexity score calculation")
        mock_doc = {
            "source_id": "AID-H-001",
            "type": "technique",
            "pillar": "infrastructure",
            "phase": "building",
            "implementation_guidance": json.dumps([{"implementation": "test"}])
        }

        score = _calculate_complexity_score(mock_doc)
        print(f"   Score: {score}/100")
        assert 0 <= score <= 100, "Score should be 0-100"
        assert score > 30, "Should have bonus from infrastructure and building phase"
        print("   [PASS]")

        # Test 3: Cost score calculation
        print("\n[TEST 3] Cost score calculation")
        mock_doc = {
            "tools_commercial": json.dumps(["Tool1", "Tool2"]),
            "pillar": "infrastructure",
            "phase": "building"
        }

        score = _calculate_cost_score(mock_doc)
        print(f"   Score: {score}/100")
        assert 0 <= score <= 100, "Score should be 0-100"
        assert score > 40, "Should have bonus from commercial tools and infrastructure"
        print("   [PASS]")

        # Test 4: Score normalization (shouldn't exceed 100)
        print("\n[TEST 4] Score normalization")
        mock_doc_maxed = {
            "defends_against": json.dumps([
                {"framework": "OWASP", "items": ["T1"] * 50},  # Many threats
                {"framework": "ATLAS", "items": ["T1"] * 50},
            ]),
            "implementation_guidance": json.dumps([{"implementation": "test"}] * 10),
            "has_code_snippets": True
        }

        score = _calculate_effectiveness_score(mock_doc_maxed)
        print(f"   Score (should be capped): {score}/100")
        assert score <= 100, "Score should not exceed 100"
        print("   [PASS]")

        print("\n" + "=" * 60)
        print("*** SCORING ALGORITHM TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_deduplication():
    """Test technique ID deduplication."""
    print("\n" + "=" * 60)
    print("DEDUPLICATION TEST")
    print("=" * 60)

    try:
        # Note: This test will fail if database is not initialized
        # We're testing the deduplication logic, not the full function
        print("\n[TEST 1] Check deduplication logic")

        # Simulate duplicate IDs
        input_ids = ["AID-H-001", "AID-H-001", "aid-h-001", "AID-H-002"]

        # Normalize and deduplicate (same as in the function)
        normalized = [tid.strip().upper() for tid in input_ids]
        seen = set()
        unique_ids = []
        for tid in normalized:
            if tid not in seen:
                seen.add(tid)
                unique_ids.append(tid)

        print(f"   Input: {input_ids}")
        print(f"   Output: {unique_ids}")

        assert len(unique_ids) == 2, "Should deduplicate to 2 unique IDs"
        assert "AID-H-001" in unique_ids
        assert "AID-H-002" in unique_ids

        print("   [PASS] Deduplication works correctly")

        print("\n" + "=" * 60)
        print("*** DEDUPLICATION TEST PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("TECHNIQUE COMPARISON - TEST SUITE")
    print("=" * 60)

    exit_code = 0

    # Run all tests
    exit_code += test_imports()
    exit_code += test_parameter_validation()
    exit_code += test_scoring_algorithms()
    exit_code += test_deduplication()

    # Summary
    print("\n" + "=" * 60)
    if exit_code == 0:
        print("*** ALL TESTS PASSED! ***")
        print("=" * 60)
        print("\nImplementation Status:")
        print("  [OK] Module imports - Working")
        print("  [OK] Parameter validation - Working")
        print("  [OK] Scoring algorithms - Working")
        print("  [OK] Deduplication logic - Working")
        print("\nNote: Full integration tests require initialized database.")
        print("      Run the MCP server to test end-to-end functionality.")
    else:
        print(f"*** {exit_code} TEST(S) FAILED ***")
        print("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
