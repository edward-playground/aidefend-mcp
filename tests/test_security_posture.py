"""
Test for Security Posture Analysis Tool

Tests the unified analyze_security_posture tool that merges
analyze_coverage and get_threat_coverage functionality.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all necessary modules can be imported."""
    print("=" * 60)
    print("SECURITY POSTURE ANALYSIS - IMPORT TESTS")
    print("=" * 60)

    try:
        print("\n[TEST 1] Import analyze_security_posture")
        from app.tools.security_posture import analyze_security_posture
        print("   [PASS] Function imported successfully")

        print("\n[TEST 2] Import from app.tools")
        from app.tools import analyze_security_posture as asp
        print("   [PASS] Can import via app.tools.__init__")

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
        from app.tools.security_posture import analyze_security_posture
        from app.security import InputValidationError

        # Test 1: Empty techniques list
        print("\n[TEST 1] Empty techniques list should fail")
        try:
            asyncio.run(analyze_security_posture(
                implemented_techniques=[],
                view="both"
            ))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 2: Invalid view
        print("\n[TEST 2] Invalid view parameter should fail")
        try:
            asyncio.run(analyze_security_posture(
                implemented_techniques=["AID-H-001"],
                view="invalid"
            ))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 3: Valid parameters
        print("\n[TEST 3] Valid view parameters")
        valid_views = ["both", "technical", "threat"]
        for view in valid_views:
            print(f"   Testing view='{view}'... ", end="")
            # Just check that it doesn't raise validation error
            # (will fail later due to missing database, but that's expected)
            try:
                asyncio.run(analyze_security_posture(
                    implemented_techniques=["AID-H-001"],
                    view=view
                ))
            except InputValidationError:
                print(f"[FAIL] Should not raise InputValidationError for view='{view}'")
                return 1
            except Exception:
                # Expected to fail due to missing database
                print("[PASS]")

        print("\n" + "=" * 60)
        print("*** VALIDATION TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_summary_generation():
    """Test summary generation logic."""
    print("\n" + "=" * 60)
    print("SUMMARY GENERATION TESTS")
    print("=" * 60)

    try:
        from app.tools.security_posture import _generate_unified_summary

        # Test 1: Basic summary generation
        print("\n[TEST 1] Generate summary from mock data")
        technical_cov = {
            "overall_coverage": {"percentage": 45.5},
            "critical_gaps": [
                {"technique_id": "AID-H-001", "name": "Adversarial Robustness", "tactic": "Harden"}
            ]
        }
        threat_cov = {
            "coverage_rate": {"owasp": 60.0, "atlas": 40.0, "maestro": 50.0},
            "uncovered_threats": {"owasp": ["LLM01", "LLM02", "LLM03"]}
        }

        summary = _generate_unified_summary(technical_cov, threat_cov, 10)

        print(f"   Techniques: {summary['techniques_implemented']}")
        print(f"   Overall posture: {summary['overall_posture']}")
        print(f"   Key insights: {len(summary['key_insights'])}")
        print(f"   Top priorities: {len(summary['top_priorities'])}")

        assert summary["techniques_implemented"] == 10, "Should have 10 techniques"
        assert summary["overall_posture"] in ["strong", "moderate", "developing", "early"], \
            "Posture should be valid"
        assert len(summary["key_insights"]) > 0, "Should have insights"

        print("   [PASS]")

        print("\n" + "=" * 60)
        print("*** SUMMARY GENERATION TESTS PASSED! ***")
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
    print("SECURITY POSTURE ANALYSIS - TEST SUITE")
    print("=" * 60)

    exit_code = 0

    # Run all tests
    exit_code += test_imports()
    exit_code += test_parameter_validation()
    exit_code += test_summary_generation()

    # Summary
    print("\n" + "=" * 60)
    if exit_code == 0:
        print("*** ALL TESTS PASSED! ***")
        print("=" * 60)
        print("\nImplementation Status:")
        print("  [OK] Module imports - Working")
        print("  [OK] Parameter validation - Working")
        print("  [OK] Summary generation - Working")
        print("  [OK] View parameter support - Working")
        print("\nNote: Full integration tests require initialized database.")
        print("      Run the MCP server to test end-to-end functionality.")
    else:
        print(f"*** {exit_code} TEST(S) FAILED ***")
        print("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
