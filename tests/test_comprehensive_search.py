"""
Simple test for comprehensive_search tool.
Tests basic functionality and query generation logic.

Note: Full integration tests require initialized database.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_query_generation():
    """Test query generation logic."""
    print("=" * 60)
    print("QUERY GENERATION TESTS")
    print("=" * 60)

    try:
        from app.tools.comprehensive_search import generate_related_queries

        # Test 1: Deepfakes topic
        print("\n[TEST 1] Generate queries for 'deepfakes'")
        queries1 = generate_related_queries("deepfakes", max_queries=5)
        print(f"   Generated {len(queries1)} queries:")
        for i, q in enumerate(queries1, 1):
            print(f"     {i}. {q}")
        assert len(queries1) >= 1, "Should generate at least 1 query"
        assert "deepfakes" in [q.lower() for q in queries1], "Should include original topic"
        print("   [PASS]")

        # Test 2: Prompt injection topic
        print("\n[TEST 2] Generate queries for 'prompt injection'")
        queries2 = generate_related_queries("prompt injection", max_queries=5)
        print(f"   Generated {len(queries2)} queries:")
        for i, q in enumerate(queries2, 1):
            print(f"     {i}. {q}")
        assert len(queries2) >= 1, "Should generate at least 1 query"
        print("   [PASS]")

        # Test 3: Generic topic (no specific expansion)
        print("\n[TEST 3] Generate queries for generic topic")
        queries3 = generate_related_queries("model security", max_queries=5)
        print(f"   Generated {len(queries3)} queries:")
        for i, q in enumerate(queries3, 1):
            print(f"     {i}. {q}")
        assert len(queries3) >= 1, "Should generate at least 1 query"
        print("   [PASS]")

        # Test 4: Limit queries
        print("\n[TEST 4] Test max_queries limit")
        queries4 = generate_related_queries("adversarial", max_queries=3)
        print(f"   Generated {len(queries4)} queries (limit=3):")
        for i, q in enumerate(queries4, 1):
            print(f"     {i}. {q}")
        assert len(queries4) <= 3, f"Should respect max_queries limit (got {len(queries4)})"
        print("   [PASS]")

        print("\n" + "=" * 60)
        print("*** QUERY GENERATION TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_deduplication():
    """Test deduplication logic."""
    print("\n" + "=" * 60)
    print("DEDUPLICATION TESTS")
    print("=" * 60)

    try:
        from app.tools.comprehensive_search import deduplicate_results

        # Test 1: Basic deduplication
        print("\n[TEST 1] Basic deduplication by source_id")
        results = [
            {"source_id": "AID-D-001", "name": "Test 1", "_distance": 0.5},
            {"source_id": "AID-D-002", "name": "Test 2", "_distance": 0.3},
            {"source_id": "AID-D-001", "name": "Test 1 duplicate", "_distance": 0.7},  # Duplicate, worse score
        ]
        deduped = deduplicate_results(results)
        print(f"   Input: {len(results)} results")
        print(f"   Output: {len(deduped)} results (deduplicated)")
        assert len(deduped) == 2, f"Expected 2 unique results, got {len(deduped)}"
        # Verify we kept the better score (0.5 < 0.7)
        d001 = [r for r in deduped if r["source_id"] == "AID-D-001"][0]
        assert d001["_distance"] == 0.5, f"Should keep better score (0.5), got {d001['_distance']}"
        print("   [PASS]")

        # Test 2: Sorted by relevance
        print("\n[TEST 2] Results sorted by relevance")
        results2 = [
            {"source_id": "AID-D-003", "name": "Test 3", "_distance": 0.8},
            {"source_id": "AID-D-001", "name": "Test 1", "_distance": 0.2},
            {"source_id": "AID-D-002", "name": "Test 2", "_distance": 0.5},
        ]
        deduped2 = deduplicate_results(results2)
        print(f"   Input scores: {[r['_distance'] for r in results2]}")
        print(f"   Output scores: {[r['_distance'] for r in deduped2]}")
        # Should be sorted ascending (lower distance = better)
        scores = [r["_distance"] for r in deduped2]
        assert scores == sorted(scores), f"Results should be sorted by distance"
        assert deduped2[0]["source_id"] == "AID-D-001", "Best match should be first"
        print("   [PASS]")

        print("\n" + "=" * 60)
        print("*** DEDUPLICATION TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_coverage_computation():
    """Test coverage summary computation."""
    print("\n" + "=" * 60)
    print("COVERAGE COMPUTATION TESTS")
    print("=" * 60)

    try:
        from app.tools.comprehensive_search import compute_coverage_summary

        # Test 1: Basic coverage
        print("\n[TEST 1] Basic coverage computation")
        results = [
            {
                "source_id": "AID-D-001",
                "type": "technique",
                "tactic": "Detect",
                "pillar": "app",
                "phase": "runtime"
            },
            {
                "source_id": "AID-H-001",
                "type": "technique",
                "tactic": "Harden",
                "pillar": "model",
                "phase": "building"
            },
            {
                "source_id": "AID-D-001.001",
                "type": "subtechnique",
                "tactic": "Detect",
                "pillar": "app",
                "phase": "runtime"
            },
        ]
        coverage = compute_coverage_summary(results)
        print(f"   Total results: {coverage['total_results']}")
        print(f"   Techniques: {coverage['techniques']}")
        print(f"   Sub-techniques: {coverage['subtechniques']}")
        print(f"   Tactics covered: {coverage['tactics_covered']}")

        assert coverage['total_results'] == 3, f"Expected 3 results, got {coverage['total_results']}"
        assert coverage['techniques'] == 2, f"Expected 2 techniques, got {coverage['techniques']}"
        assert coverage['subtechniques'] == 1, f"Expected 1 subtechnique, got {coverage['subtechniques']}"
        assert len(coverage['tactics_covered']) == 2, f"Expected 2 tactics, got {len(coverage['tactics_covered'])}"
        assert "Detect" in coverage['tactics_covered'], "Should include Detect tactic"
        assert "Harden" in coverage['tactics_covered'], "Should include Harden tactic"
        print("   [PASS]")

        print("\n" + "=" * 60)
        print("*** COVERAGE COMPUTATION TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_module_imports():
    """Test that all necessary modules can be imported."""
    print("\n" + "=" * 60)
    print("MODULE IMPORT TESTS")
    print("=" * 60)

    try:
        print("\n[TEST 1] Import comprehensive_search module")
        from app.tools.comprehensive_search import comprehensive_search
        print("   [PASS] comprehensive_search function imported")

        print("\n[TEST 2] Import helper functions")
        from app.tools.comprehensive_search import (
            generate_related_queries,
            deduplicate_results,
            compute_coverage_summary
        )
        print("   [PASS] All helper functions imported")

        print("\n[TEST 3] Import from app.tools")
        from app.tools import comprehensive_search as cs
        print("   [PASS] Can import via app.tools.__init__")

        print("\n" + "=" * 60)
        print("*** MODULE IMPORT TESTS PASSED! ***")
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
    print("COMPREHENSIVE SEARCH - TEST SUITE")
    print("=" * 60)

    exit_code = 0

    # Run all tests
    exit_code += test_module_imports()
    exit_code += test_query_generation()
    exit_code += test_deduplication()
    exit_code += test_coverage_computation()

    # Summary
    print("\n" + "=" * 60)
    if exit_code == 0:
        print("*** ALL TESTS PASSED! ***")
        print("=" * 60)
        print("\nImplementation Status:")
        print("  [OK] Query generation logic - Working")
        print("  [OK] Deduplication logic - Working")
        print("  [OK] Coverage computation - Working")
        print("  [OK] Module imports - Working")
        print("\nNote: Full integration tests require initialized database.")
        print("      Run the MCP server or REST API to test end-to-end.")
    else:
        print(f"*** {exit_code} TEST(S) FAILED ***")
        print("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
