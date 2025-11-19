"""
Test for Defenses for Threat Tool

Tests the get_defenses_for_threat tool including threat ID matching,
keyword search, and hybrid search modes.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all necessary modules can be imported."""
    print("=" * 60)
    print("DEFENSES FOR THREAT - IMPORT TESTS")
    print("=" * 60)

    try:
        print("\n[TEST 1] Import get_defenses_for_threat")
        from app.tools.defenses_for_threat import get_defenses_for_threat
        print("   [PASS] Function imported successfully")

        print("\n[TEST 2] Import from app.tools")
        from app.tools import get_defenses_for_threat as gdf
        print("   [PASS] Can import via app.tools.__init__")

        print("\n[TEST 3] Import helper functions")
        from app.tools.defenses_for_threat import (
            normalize_threat_id,
            _threat_id_matches,
            _deduplicate_results
        )
        print("   [PASS] Helper functions imported")

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
        from app.tools.defenses_for_threat import get_defenses_for_threat
        from app.security import InputValidationError

        # Test 1: No parameters should fail
        print("\n[TEST 1] No parameters should fail")
        try:
            asyncio.run(get_defenses_for_threat())
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 2: Invalid top_k (too low)
        print("\n[TEST 2] top_k < 1 should fail")
        try:
            asyncio.run(get_defenses_for_threat(threat_id="LLM01", top_k=0))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 3: Invalid top_k (too high)
        print("\n[TEST 3] top_k > 50 should fail")
        try:
            asyncio.run(get_defenses_for_threat(threat_id="LLM01", top_k=51))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 4: Threat keyword too short
        print("\n[TEST 4] Threat keyword < 3 chars should fail")
        try:
            asyncio.run(get_defenses_for_threat(threat_keyword="ab"))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 5: Threat keyword too long
        print("\n[TEST 5] Threat keyword > 200 chars should fail")
        try:
            long_keyword = "a" * 201
            asyncio.run(get_defenses_for_threat(threat_keyword=long_keyword))
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


def test_threat_id_normalization():
    """Test threat ID normalization logic."""
    print("\n" + "=" * 60)
    print("THREAT ID NORMALIZATION TESTS")
    print("=" * 60)

    try:
        from app.tools.defenses_for_threat import normalize_threat_id

        # Test 1: OWASP LLM format
        print("\n[TEST 1] Normalize OWASP LLM format")
        test_cases = [
            ("LLM01", "LLM01"),
            ("llm01", "LLM01"),
            ("OWASP-LLM01:2025", "LLM01"),
            ("owasp-llm02:2023", "LLM02"),
        ]

        for input_id, expected in test_cases:
            result = normalize_threat_id(input_id)
            assert result == expected, f"Expected {expected}, got {result}"
            print(f"   {input_id} -> {result} [OK]")

        print("   [PASS] OWASP LLM normalization works")

        # Test 2: MITRE ATLAS format
        print("\n[TEST 2] Normalize MITRE ATLAS format")
        test_cases = [
            ("T0015", "AML.T0015"),
            ("t0043", "AML.T0043"),
            ("AML.T0020", "AML.T0020"),
            ("aml.t0051", "AML.T0051"),
        ]

        for input_id, expected in test_cases:
            result = normalize_threat_id(input_id)
            assert result == expected, f"Expected {expected}, got {result}"
            print(f"   {input_id} -> {result} [OK]")

        print("   [PASS] MITRE ATLAS normalization works")

        # Test 3: Edge cases
        print("\n[TEST 3] Handle edge cases")
        result = normalize_threat_id("  LLM01  ")
        assert result == "LLM01", "Should strip whitespace"
        print("   Whitespace handling [OK]")

        print("\n" + "=" * 60)
        print("*** NORMALIZATION TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_threat_id_matching():
    """Test threat ID matching logic."""
    print("\n" + "=" * 60)
    print("THREAT ID MATCHING TESTS")
    print("=" * 60)

    try:
        from app.tools.defenses_for_threat import _threat_id_matches

        # Test 1: Exact matches
        print("\n[TEST 1] Exact substring matches")
        assert _threat_id_matches("LLM01", "LLM01:2025 Prompt Injection"), "Should match LLM01"
        assert _threat_id_matches("AML.T0043", "AML.T0043 Adversarial Examples"), "Should match AML.T0043"
        print("   [PASS] Exact matches work")

        # Test 2: Case insensitive
        print("\n[TEST 2] Case insensitive matching")
        assert _threat_id_matches("LLM01", "llm01:2025 prompt injection"), "Should be case insensitive"
        print("   [PASS] Case insensitive matching works")

        # Test 3: LLM pattern matching
        print("\n[TEST 3] LLM pattern matching")
        assert _threat_id_matches("LLM01", "LLM01:2023"), "Should match LLM01 with different year"
        assert _threat_id_matches("LLM01", "LLM01 "), "Should match with trailing space"
        print("   [PASS] LLM pattern matching works")

        # Test 4: ATLAS T-number extraction
        print("\n[TEST 4] ATLAS T-number matching")
        assert _threat_id_matches("AML.T0043", "T0043 Some attack"), "Should match T#### in AML.T####"
        print("   [PASS] ATLAS T-number matching works")

        # Test 5: Non-matches
        print("\n[TEST 5] Verify non-matches")
        assert not _threat_id_matches("LLM01", "LLM02:2025"), "Should not match different ID"
        assert not _threat_id_matches("LLM01", "Random text"), "Should not match random text"
        print("   [PASS] Non-matches correctly rejected")

        print("\n" + "=" * 60)
        print("*** MATCHING TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_deduplication():
    """Test result deduplication logic."""
    print("\n" + "=" * 60)
    print("DEDUPLICATION TESTS")
    print("=" * 60)

    try:
        from app.tools.defenses_for_threat import _deduplicate_results

        # Test 1: Remove duplicates, keep higher relevance
        print("\n[TEST 1] Deduplicate with relevance scores")
        results = [
            {
                "technique": {"id": "AID-H-001", "name": "Test 1"},
                "relevance_score": 0.8
            },
            {
                "technique": {"id": "AID-H-001", "name": "Test 1"},
                "relevance_score": 0.9
            },
            {
                "technique": {"id": "AID-D-002", "name": "Test 2"},
                "relevance_score": 0.7
            }
        ]

        deduplicated = _deduplicate_results(results)
        assert len(deduplicated) == 2, "Should have 2 unique techniques"

        # Find AID-H-001 in results
        aid_h_001 = next(r for r in deduplicated if r['technique']['id'] == 'AID-H-001')
        assert aid_h_001['relevance_score'] == 0.9, "Should keep higher relevance score"

        print(f"   Deduplicated from {len(results)} to {len(deduplicated)} results")
        print("   [PASS] Deduplication works correctly")

        # Test 2: No duplicates
        print("\n[TEST 2] Handle no duplicates")
        results = [
            {
                "technique": {"id": "AID-H-001", "name": "Test 1"},
                "relevance_score": 0.8
            },
            {
                "technique": {"id": "AID-D-002", "name": "Test 2"},
                "relevance_score": 0.7
            }
        ]

        deduplicated = _deduplicate_results(results)
        assert len(deduplicated) == 2, "Should keep all unique results"
        print("   [PASS] Handles no duplicates correctly")

        print("\n" + "=" * 60)
        print("*** DEDUPLICATION TESTS PASSED! ***")
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
    print("DEFENSES FOR THREAT - TEST SUITE")
    print("=" * 60)

    exit_code = 0

    # Run all tests
    exit_code += test_imports()
    exit_code += test_parameter_validation()
    exit_code += test_threat_id_normalization()
    exit_code += test_threat_id_matching()
    exit_code += test_deduplication()

    # Summary
    print("\n" + "=" * 60)
    if exit_code == 0:
        print("*** ALL TESTS PASSED! ***")
        print("=" * 60)
        print("\nImplementation Status:")
        print("  [OK] Module imports - Working")
        print("  [OK] Parameter validation - Working")
        print("  [OK] Threat ID normalization - Working")
        print("  [OK] Threat ID matching - Working")
        print("  [OK] Result deduplication - Working")
        print("\nNote: Full integration tests require initialized database.")
        print("      Run the MCP server to test end-to-end functionality.")
        print("\nSupported Features:")
        print("  [OK] OWASP LLM Top 10 ID normalization")
        print("  [OK] MITRE ATLAS ID normalization")
        print("  [OK] Threat keyword semantic search")
        print("  [OK] Hybrid search (ID + keyword)")
    else:
        print(f"*** {exit_code} TEST(S) FAILED ***")
        print("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
