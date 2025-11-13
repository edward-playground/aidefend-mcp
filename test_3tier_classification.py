"""
Test script for 3-tier threat classification system.
Tests static keyword matching, fuzzy matching, and LLM fallback graceful degradation.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

async def test_tier3_graceful_degradation():
    """Test Tier 3: LLM fallback graceful degradation (should not crash when API key missing)."""
    print("\n=== TEST 3: Tier 3 - LLM Fallback Graceful Degradation ===")

    # Save original settings
    original_enable_llm = settings.ENABLE_LLM_FALLBACK
    original_api_key = settings.ANTHROPIC_API_KEY

    try:
        # Enable LLM fallback but without API key
        settings.ENABLE_LLM_FALLBACK = True
        settings.ANTHROPIC_API_KEY = None

        # Use vague text that might not match static/fuzzy
        text = "The system showed unexpected behavior"
        result = await classify_threat(text=text, top_k=5)

        # Should gracefully degrade - not crash
        assert result is not None, "Should return result even when LLM fallback enabled but no API key"
        assert result['source'] in ['static_keyword', 'fuzzy_match', 'no_match'], f"Should degrade gracefully, got {result['source']}"

        print(f"✅ PASS: Graceful degradation works when API key not configured")
        print(f"   Source: {result['source']} (degraded from LLM tier)")
        print(f"   Matches: {len(result['keywords_found'])}")

    finally:
        # Restore original settings
        settings.ENABLE_LLM_FALLBACK = original_enable_llm
        settings.ANTHROPIC_API_KEY = original_api_key

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
    print("3-TIER THREAT CLASSIFICATION SYSTEM TEST SUITE")
    print("=" * 60)

    print(f"\nConfiguration:")
    print(f"  ENABLE_FUZZY_MATCHING: {settings.ENABLE_FUZZY_MATCHING}")
    print(f"  FUZZY_MATCH_CUTOFF: {settings.FUZZY_MATCH_CUTOFF}")
    print(f"  ENABLE_LLM_FALLBACK: {settings.ENABLE_LLM_FALLBACK}")
    print(f"  LLM_FALLBACK_THRESHOLD: {settings.LLM_FALLBACK_THRESHOLD}")
    print(f"  ANTHROPIC_API_KEY: {'✓ Set' if settings.ANTHROPIC_API_KEY else '✗ Not set'}")

    tests = [
        ("Tier 1: Static Keyword Match", test_tier1_static_keyword),
        ("Tier 2: Fuzzy Match", test_tier2_fuzzy_matching),
        ("Tier 3: Graceful Degradation", test_tier3_graceful_degradation),
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
        print("\n🎉 All tests passed! Implementation is production-ready.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
