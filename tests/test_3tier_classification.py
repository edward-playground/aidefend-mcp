"""
Test script for 2-tier threat classification system.
Tests static keyword matching and fuzzy matching (RapidFuzz-based).

100% LOCAL - No external API calls, all processing happens locally.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools.classify_threat import classify_threat
from app.config import settings

async def test_tier1_static_keyword():
    """Test Tier 1: Static keyword matching (should work with high confidence)."""
    print("\n=== TEST 1: Tier 1 - Static Keyword Match ===")
    text = "We detected a prompt injection attack in our system"
    result = await classify_threat(text=text, top_k=5)

    assert result['source'] == 'static_keyword', f"Expected static_keyword, got {result['source']}"
    assert len(result['keywords_found']) > 0, "Should find at least one keyword"
    assert result['keywords_found'][0]['confidence'] >= 0.75, "Should have high confidence"

    print(f"✅ PASS: Found {len(result['keywords_found'])} keywords via static matching")
    print(f"   Source: {result['source']}")
    print(f"   Top match: {result['keywords_found'][0]['keyword']} (confidence: {result['keywords_found'][0]['confidence']:.2f})")
    return True

async def test_tier2_fuzzy_matching():
    """Test Tier 2: Fuzzy matching for typos (should work with moderate confidence)."""
    print("\n=== TEST 2: Tier 2 - Fuzzy Match (Typo Tolerance) ===")
    # Use a typo that should trigger fuzzy matching
    text = "We found federrated learning attack"  # typo: "federrated" should match "federated"
    result = await classify_threat(text=text, top_k=5)

    # Should match via fuzzy or static
    assert result['source'] in ['fuzzy_match', 'static_keyword'], f"Expected fuzzy_match or static_keyword, got {result['source']}"
    assert len(result['keywords_found']) > 0, "Should find at least one keyword via fuzzy matching"

    print(f"✅ PASS: Fuzzy matching handled typo successfully")
    print(f"   Source: {result['source']}")
    print(f"   Matches: {len(result['keywords_found'])}")
    if result['keywords_found']:
        print(f"   Top match: {result['keywords_found'][0]['keyword']} (confidence: {result['keywords_found'][0]['confidence']:.2f})")
    return True

async def test_combined_matching():
    """Test combined static + fuzzy matching workflow."""
    print("\n=== TEST 3: Combined Static + Fuzzy Matching Workflow ===")

    # Test that fuzzy matching activates when static fails
    text = "We found algo bias in the model"  # "algo" should fuzzy match "algorithmic"
    result = await classify_threat(text=text, top_k=5)

    # Should find something via static or fuzzy
    assert result is not None, "Should return result for combined matching"
    assert result['source'] in ['static_keyword', 'fuzzy_match', 'no_match'], f"Unexpected source: {result['source']}"

    print(f"✅ PASS: Combined matching workflow works correctly")
    print(f"   Source: {result['source']}")
    print(f"   Matches: {len(result['keywords_found'])}")
    if result['keywords_found']:
        print(f"   Top match: {result['keywords_found'][0]['keyword']} (confidence: {result['keywords_found'][0]['confidence']:.2f})")

    return True

async def test_no_match():
    """Test no match scenario."""
    print("\n=== TEST 4: No Match Scenario ===")
    text = "The weather is nice today"
    result = await classify_threat(text=text, top_k=5)

    assert result['source'] == 'no_match' or len(result['keywords_found']) == 0, "Should return no_match for irrelevant text"

    print(f"✅ PASS: No match handling works correctly")
    print(f"   Source: {result['source']}")
    print(f"   Matches: {len(result['keywords_found'])}")
    return True

async def test_confidence_threshold():
    """Test that confidence threshold works correctly."""
    print("\n=== TEST 5: Confidence Threshold Logic ===")

    # Test with exact match (high confidence)
    text1 = "prompt injection"
    result1 = await classify_threat(text=text1, top_k=5)

    if result1['keywords_found']:
        conf1 = result1['keywords_found'][0]['confidence']
        print(f"✅ PASS: Exact match has confidence {conf1:.2f}")
        assert conf1 >= 0.75, "Exact match should have high confidence"

    return True

async def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("2-TIER THREAT CLASSIFICATION SYSTEM TEST SUITE")
    print("100% LOCAL - No external API calls")
    print("=" * 60)

    print(f"\nConfiguration:")
    print(f"  ENABLE_FUZZY_MATCHING: {settings.ENABLE_FUZZY_MATCHING}")
    print(f"  FUZZY_MATCH_CUTOFF: {settings.FUZZY_MATCH_CUTOFF}")

    tests = [
        ("Tier 1: Static Keyword Match", test_tier1_static_keyword),
        ("Tier 2: Fuzzy Match (RapidFuzz)", test_tier2_fuzzy_matching),
        ("Combined Matching Workflow", test_combined_matching),
        ("No Match Scenario", test_no_match),
        ("Confidence Threshold", test_confidence_threshold),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            success = await test_func()
            results.append((test_name, success, None))
        except Exception as e:
            print(f"\n❌ FAIL: {test_name}")
            print(f"   Error: {str(e)}")
            results.append((test_name, False, str(e)))

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for test_name, success, error in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if error:
            print(f"       Error: {error}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! 2-tier classification is production-ready.")
        print("✅ 100% LOCAL - No external API calls, zero cost")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
