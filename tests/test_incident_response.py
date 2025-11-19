"""
Test for Incident Response Playbook Generator

Tests the generate_incident_playbook tool including timeline generation,
threat integration, and action item creation.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all necessary modules can be imported."""
    print("=" * 60)
    print("INCIDENT RESPONSE PLAYBOOK - IMPORT TESTS")
    print("=" * 60)

    try:
        print("\n[TEST 1] Import generate_incident_playbook")
        from app.tools.incident_response import generate_incident_playbook
        print("   [PASS] Function imported successfully")

        print("\n[TEST 2] Import from app.tools")
        from app.tools import generate_incident_playbook as gip
        print("   [PASS] Can import via app.tools.__init__")

        print("\n[TEST 3] Import timeline generators")
        from app.tools.incident_response import (
            _generate_immediate_actions,
            _generate_investigation_actions,
            _generate_containment_actions,
            _generate_recovery_actions
        )
        print("   [PASS] Timeline generators imported")

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
        from app.tools.incident_response import generate_incident_playbook
        from app.security import InputValidationError

        # Test 1: Empty description should fail
        print("\n[TEST 1] Empty incident description should fail")
        try:
            asyncio.run(generate_incident_playbook(incident_description=""))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 2: Too short description (< 10 chars)
        print("\n[TEST 2] Too short description should fail")
        try:
            asyncio.run(generate_incident_playbook(incident_description="test"))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 3: Too long description (> 1000 chars)
        print("\n[TEST 3] Too long description should fail")
        try:
            long_desc = "test " * 300  # Way over 1000 chars
            asyncio.run(generate_incident_playbook(incident_description=long_desc))
            print("   [FAIL] Should have raised InputValidationError")
            return 1
        except InputValidationError as e:
            print(f"   [PASS] Correctly raised error: {e}")

        # Test 4: Not a string
        print("\n[TEST 4] Non-string input should fail")
        try:
            asyncio.run(generate_incident_playbook(incident_description=12345))
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


def test_timeline_generators():
    """Test timeline action generators."""
    print("\n" + "=" * 60)
    print("TIMELINE GENERATOR TESTS")
    print("=" * 60)

    try:
        from app.tools.incident_response import (
            _generate_immediate_actions,
            _generate_investigation_actions,
            _generate_containment_actions,
            _generate_recovery_actions
        )

        # Test 1: Immediate actions (without threat classification)
        print("\n[TEST 1] Generate immediate actions")
        actions = _generate_immediate_actions(
            "Suspicious activity detected",
            threat_classification=None
        )

        print(f"   Generated {len(actions)} immediate actions")
        assert len(actions) >= 3, "Should have at least 3 base actions"

        # Check required fields
        for action in actions:
            assert 'action' in action
            assert 'priority' in action
            assert 'description' in action
            assert 'estimated_time' in action

        print("   [PASS] All actions have required fields")

        # Test 2: Immediate actions with threat classification
        print("\n[TEST 2] Generate immediate actions with threat context")
        mock_threat = {
            "matched_threats": [
                {"keyword": "prompt injection", "confidence": 90}
            ]
        }

        actions_with_threat = _generate_immediate_actions(
            "Prompt injection detected",
            threat_classification=mock_threat
        )

        print(f"   Generated {len(actions_with_threat)} actions with threat context")
        assert len(actions_with_threat) > len(actions), "Should have additional threat-specific actions"
        print("   [PASS] Threat-specific actions added")

        # Test 3: Investigation actions
        print("\n[TEST 3] Generate investigation actions")
        inv_actions = _generate_investigation_actions(
            "Security incident under investigation",
            threat_classification=mock_threat
        )

        print(f"   Generated {len(inv_actions)} investigation actions")
        assert len(inv_actions) >= 4, "Should have at least 4 investigation actions"
        print("   [PASS]")

        # Test 4: Containment actions
        print("\n[TEST 4] Generate containment actions")
        cont_actions = _generate_containment_actions(
            "Containing security breach",
            threat_classification=mock_threat,
            defense_techniques=None
        )

        print(f"   Generated {len(cont_actions)} containment actions")
        assert len(cont_actions) >= 3, "Should have at least 3 containment actions"
        print("   [PASS]")

        # Test 5: Recovery actions
        print("\n[TEST 5] Generate recovery actions")
        rec_actions = _generate_recovery_actions(
            "Recovering from incident",
            threat_classification=mock_threat,
            defense_techniques=None
        )

        print(f"   Generated {len(rec_actions)} recovery actions")
        assert len(rec_actions) >= 5, "Should have at least 5 recovery actions"
        print("   [PASS]")

        # Test 6: Priority levels
        print("\n[TEST 6] Verify priority levels are valid")
        all_actions = actions + inv_actions + cont_actions + rec_actions
        valid_priorities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

        for action in all_actions:
            priority = action.get('priority', 'MEDIUM')
            assert priority in valid_priorities, f"Invalid priority: {priority}"

        print(f"   Checked {len(all_actions)} actions")
        print("   [PASS] All priorities are valid")

        print("\n" + "=" * 60)
        print("*** TIMELINE GENERATOR TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_threat_specific_actions():
    """Test threat-specific action generation."""
    print("\n" + "=" * 60)
    print("THREAT-SPECIFIC ACTION TESTS")
    print("=" * 60)

    try:
        from app.tools.incident_response import _generate_immediate_actions

        # Test 1: Prompt injection specific actions
        print("\n[TEST 1] Prompt injection threat")
        mock_threat = {
            "matched_threats": [
                {"keyword": "prompt injection", "confidence": 90}
            ]
        }

        actions = _generate_immediate_actions("Prompt injection", mock_threat)

        # Check for prompt injection specific action
        action_names = [a['action'] for a in actions]
        assert any('LLM' in name or 'injection' in name.lower() for name in action_names), \
            "Should have prompt injection specific action"
        print("   [PASS] Prompt injection actions generated")

        # Test 2: Data poisoning specific actions
        print("\n[TEST 2] Data poisoning threat")
        mock_threat = {
            "matched_threats": [
                {"keyword": "data poisoning", "confidence": 85}
            ]
        }

        actions = _generate_immediate_actions("Data poisoning attack", mock_threat)

        action_names = [a['action'] for a in actions]
        assert any('training' in name.lower() or 'pipeline' in name.lower() for name in action_names), \
            "Should have data poisoning specific action"
        print("   [PASS] Data poisoning actions generated")

        # Test 3: DoS specific actions
        print("\n[TEST 3] Denial of service threat")
        mock_threat = {
            "matched_threats": [
                {"keyword": "denial of service", "confidence": 80}
            ]
        }

        actions = _generate_immediate_actions("DoS attack", mock_threat)

        action_names = [a['action'] for a in actions]
        assert any('rate' in name.lower() or 'limiting' in name.lower() for name in action_names), \
            "Should have DoS specific action"
        print("   [PASS] DoS actions generated")

        print("\n" + "=" * 60)
        print("*** THREAT-SPECIFIC ACTION TESTS PASSED! ***")
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
    print("INCIDENT RESPONSE PLAYBOOK - TEST SUITE")
    print("=" * 60)

    exit_code = 0

    # Run all tests
    exit_code += test_imports()
    exit_code += test_parameter_validation()
    exit_code += test_timeline_generators()
    exit_code += test_threat_specific_actions()

    # Summary
    print("\n" + "=" * 60)
    if exit_code == 0:
        print("*** ALL TESTS PASSED! ***")
        print("=" * 60)
        print("\nImplementation Status:")
        print("  [OK] Module imports - Working")
        print("  [OK] Parameter validation - Working")
        print("  [OK] Timeline generators - Working")
        print("  [OK] Threat-specific actions - Working")
        print("\nNote: Full integration tests require initialized database.")
        print("      Run the MCP server to test end-to-end functionality.")
        print("\nTimeline Phases Tested:")
        print("  [OK] Immediate Actions (0-15 min)")
        print("  [OK] Investigation (15 min - 2 hours)")
        print("  [OK] Containment (2-8 hours)")
        print("  [OK] Recovery & Remediation (8+ hours)")
    else:
        print(f"*** {exit_code} TEST(S) FAILED ***")
        print("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
