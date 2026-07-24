"""
Test for Security Posture Analysis Tool

Tests the unified analyze_security_posture tool that merges
analyze_coverage and get_threat_coverage functionality.
"""

import asyncio
import sys
from pathlib import Path

import pytest

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


    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        raise AssertionError("test branch reported failure")


@pytest.mark.asyncio
async def test_parameter_validation(monkeypatch):
    """Validate input contracts without treating arbitrary database errors as success."""
    import app.tools.security_posture as posture_module
    from app.security import InputValidationError

    with pytest.raises(InputValidationError):
        await posture_module.analyze_security_posture(
            implemented_techniques="AID-H-001",
            view="both",
        )

    with pytest.raises(InputValidationError):
        await posture_module.analyze_security_posture(
            implemented_techniques=["AID-H-001", 7],
            view="both",
        )

    with pytest.raises(InputValidationError):
        await posture_module.analyze_security_posture(
            implemented_techniques=["AID-H-001"] * 201,
            view="both",
        )

    with pytest.raises(InputValidationError):
        await posture_module.analyze_security_posture(
            implemented_techniques=["AID-H-001"],
            view="invalid",
        )

    async def technical_stub(*, implemented_techniques, system_type=None):
        return {
            "implemented": implemented_techniques,
            "system_type": system_type,
            "analysis_summary": {"coverage_percentage": 0},
        }

    async def threat_stub(*, implemented_techniques):
        return {"implemented": implemented_techniques, "coverage_rate": {}}

    monkeypatch.setattr(posture_module, "analyze_coverage", technical_stub)
    monkeypatch.setattr(posture_module, "get_threat_coverage", threat_stub)

    for view in ("both", "technical", "threat"):
        result = await posture_module.analyze_security_posture([], view=view)
        assert result["view"] == view
        assert result["implemented_count"] == 0
        assert ("technical_coverage" in result) is (view in {"both", "technical"})
        assert ("threat_coverage" in result) is (view in {"both", "threat"})


@pytest.mark.asyncio
async def test_current_ids_parent_expansion_and_stale_ids_are_reported(monkeypatch):
    """Posture counts must come from live resolution, not raw caller input."""
    import app.tools.security_posture as posture_module

    expected_input = ["AID-H-010", "AID-D-001", "AID-H-025.003"]
    expansion = {
        "AID-H-010": ["AID-H-010.001", "AID-H-010.002"]
    }

    async def technical_stub(*, implemented_techniques, system_type=None):
        assert implemented_techniques == expected_input
        return {
            "analysis_summary": {
                "coverage_percentage": 1.0,
                "techniques_implemented": 3,
                "expanded_parent_families": expansion,
                "unrecognized_technique_ids": ["AID-H-025.003"],
            },
            "critical_gaps": [],
            "recommendations": [],
        }

    async def threat_stub(*, implemented_techniques):
        assert implemented_techniques == expected_input
        return {
            "valid_count": 2,
            "invalid_count": 1,
            "invalid_techniques": ["AID-H-025.003"],
            "resolved_actionable_count": 3,
            "expanded_parent_families": expansion,
            "coverage_rate": {},
            "covered": {},
        }

    monkeypatch.setattr(posture_module, "analyze_coverage", technical_stub)
    monkeypatch.setattr(posture_module, "get_threat_coverage", threat_stub)

    result = await posture_module.analyze_security_posture(
        [" aid-h-010 ", "AID-H-010", "AID-D-001", "AID-H-025.003"],
        view="both",
    )

    assert result["requested_count"] == 3
    assert result["implemented_count"] == 2
    assert result["implemented_actionable_count"] == 3
    assert result["invalid_count"] == 1
    assert result["invalid_technique_ids"] == ["AID-H-025.003"]
    assert result["expanded_parent_families"] == expansion
    assert result["summary"]["techniques_implemented"] == 3


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


    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        raise AssertionError("test branch reported failure")


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
