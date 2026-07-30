"""Unit coverage for the 18-tool transport smoke harness itself."""

import json

import pytest
from fastapi import APIRouter, FastAPI

from scripts.smoke_all_tools import (
    ANY_AIDEFEND_ID_RE,
    CONTROL_ID_RE,
    EXPECTED_TOOL_NAMES,
    UNMAPPED_THREAT_ID,
    DynamicFixtures,
    SmokeFailure,
    assert_no_generic_mcp_error,
    build_smoke_cases,
    openapi_route_inventory,
    select_dynamic_fixtures,
    validate_mcp_text,
    validate_rest_payload,
)


SOURCE_AVAILABLE_TOOL = "BoundaryGuard Open Weight (model license; open-weight)"


def _synthetic_records():
    return [
        {
            "source_id": "AID-H-001.001",
            "type": "subtechnique",
            "name": "Prompt Boundary Validation",
            "is_parent_family": False,
            "has_code_snippets": False,
            "defends_against": "[]",
            "implementation_guidance": "[]",
            "parent_technique_id": "AID-H-001",
            "tools_opensource": json.dumps(["BoundaryGuard OSS"]),
            "tools_source_available": json.dumps([SOURCE_AVAILABLE_TOOL]),
            "tools_commercial": json.dumps(["BoundaryGuard Cloud"]),
            "scope_boundary": json.dumps({
                "responsibility": "Validate input at the trust boundary.",
                "relatedTechniques": [{
                    "id": "AID-D-002",
                    "comparison": "Detection observes attempts after validation.",
                }],
            }),
        },
        {
            "source_id": "AID-H-001.001.S1",
            "type": "strategy",
            "name": "Validate Prompt Boundaries",
            "is_parent_family": False,
            "has_code_snippets": True,
            "defends_against": "[]",
            "implementation_guidance": json.dumps(
                [{"implementation": "Validate", "howTo": "<pre><code>assert safe</code></pre>"}]
            ),
            "parent_technique_id": "AID-H-001.001",
        },
        {
            "source_id": "AID-D-002",
            "type": "technique",
            "name": "Prompt Injection Detection",
            "is_parent_family": False,
            "has_code_snippets": False,
            "defends_against": json.dumps(
                [{"framework": "MITRE ATLAS", "items": ["AML.T0051 LLM Prompt Injection"]}]
            ),
            "implementation_guidance": "[]",
            "parent_technique_id": "",
            "tools_opensource": "[]",
            "tools_source_available": "[]",
            "tools_commercial": "[]",
        },
    ]


def test_dynamic_fixtures_come_from_code_and_threat_mapped_records():
    fixtures = select_dynamic_fixtures(_synthetic_records())

    assert fixtures.control_ids == ("AID-H-001.001", "AID-D-002")
    assert fixtures.boundary_control_id == "AID-H-001.001"
    assert fixtures.boundary_responsibility == "Validate input at the trust boundary."
    assert fixtures.boundary_related_ids == ("AID-D-002",)
    assert fixtures.source_available_control_id == "AID-H-001.001"
    assert fixtures.source_available_tools == (SOURCE_AVAILABLE_TOOL,)
    assert fixtures.code_control_id == "AID-H-001.001"
    assert fixtures.missing_control_id == "AID-SMOKEMISSING0-999"
    assert fixtures.threat_id == "AML.T0051"
    assert fixtures.topic == "Prompt Boundary Validation"
    assert fixtures.row_count == 3


def test_smoke_inventory_pairs_exactly_18_tools_and_routes():
    fixtures = select_dynamic_fixtures(_synthetic_records())
    cases = build_smoke_cases(fixtures)

    assert len(cases) == 18
    assert tuple(case.name for case in cases) == EXPECTED_TOOL_NAMES
    assert len({(case.method, case.route_path) for case in cases}) == 18
    coverage = next(case for case in cases if case.name == "analyze_coverage")
    compliance = next(case for case in cases if case.name == "map_to_compliance_framework")
    assert coverage.rest_json == list(fixtures.control_ids)
    assert compliance.rest_json == list(fixtures.control_ids)


def test_route_inventory_uses_public_openapi_for_included_routers():
    router = APIRouter(prefix="/api/v1")

    @router.get("/status")
    async def status():
        return {"status": "ok"}

    app = FastAPI()
    app.include_router(router)

    assert ("GET", "/api/v1/status") in openapi_route_inventory(app)


@pytest.mark.parametrize(
    "text",
    [
        "Error: database unavailable",
        "Failed to get status: model missing",
        "Query failed: engine unavailable",
        "# Starting AIDEFEND Knowledge Base Sync\n\n**Sync Failed**\n",
        "Error: unexpected\n\nPlease try again or check the service logs",
    ],
)
def test_generic_mcp_failures_are_rejected(text):
    with pytest.raises(SmokeFailure):
        assert_no_generic_mcp_error(text)


def test_statistics_validator_checks_live_row_and_type_counts():
    fixtures = DynamicFixtures(
        control_ids=("AID-H-001.001", "AID-D-002"),
        boundary_control_id="AID-H-001.001",
        boundary_responsibility="Validate input at the trust boundary.",
        boundary_related_ids=("AID-D-002",),
        source_available_control_id="AID-H-001.001",
        source_available_tools=(SOURCE_AVAILABLE_TOOL,),
        code_control_id="AID-H-001.001",
        missing_control_id="AID-SMOKEMISSING0-999",
        threat_id="AML.T0051",
        topic="Prompt Boundary Validation",
        row_count=3,
    )
    case = next(case for case in build_smoke_cases(fixtures) if case.name == "get_statistics")
    payload = {
        "overview": {
            "total_documents": 3,
            "total_techniques": 1,
            "total_subtechniques": 1,
            "total_strategies": 1,
        },
        "by_tactic": {"Harden": 3},
        "by_pillar": {"app": 2},
        "by_phase": {"operation": 2},
        "threat_framework_coverage": {"by_framework": {}},
    }

    validate_rest_payload(case, payload, fixtures, sync_skipped=True)

    payload["overview"]["total_documents"] = 4
    with pytest.raises(SmokeFailure, match="document count"):
        validate_rest_payload(case, payload, fixtures, sync_skipped=True)


def test_dynamic_fixtures_tolerate_absent_optional_source_available_and_boundary():
    records = _synthetic_records()
    records[0]["tools_source_available"] = "[]"
    records[0]["scope_boundary"] = "{}"

    fixtures = select_dynamic_fixtures(records)

    assert fixtures.control_ids == ("AID-D-002", "AID-H-001.001")
    assert fixtures.boundary_control_id == ""
    assert fixtures.boundary_responsibility == ""
    assert fixtures.boundary_related_ids == ()
    assert fixtures.source_available_control_id == ""
    assert fixtures.source_available_tools == ()


def test_dynamic_fixtures_tolerate_all_absent_optional_capabilities():
    records = _synthetic_records()
    records[0]["tools_source_available"] = "[]"
    records[0]["scope_boundary"] = "{}"
    records[1]["has_code_snippets"] = False
    records[1]["implementation_guidance"] = "[]"
    records[2]["defends_against"] = "[]"

    fixtures = select_dynamic_fixtures(records)
    cases = {case.name: case for case in build_smoke_cases(fixtures)}

    assert fixtures.control_ids == ("AID-H-001.001", "AID-D-002")
    assert fixtures.boundary_control_id == ""
    assert fixtures.source_available_control_id == ""
    assert fixtures.code_control_id == ""
    assert fixtures.threat_id == ""
    assert cases["get_defenses_for_threat"].mcp_arguments == {
        "threat_id": UNMAPPED_THREAT_ID,
        "top_k": 5,
    }
    assert cases["get_defenses_for_threat"].rest_params == {
        "threat_id": UNMAPPED_THREAT_ID,
        "top_k": 5,
    }
    assert cases["get_secure_code_snippet"].mcp_arguments == {
        "technique_id": fixtures.control_ids[0],
        "max_snippets": 3,
    }
    assert cases["get_secure_code_snippet"].rest_params == {
        "technique_id": fixtures.control_ids[0],
        "max_snippets": 3,
    }


def test_smoke_id_patterns_accept_future_alphanumeric_tactic_segments():
    assert CONTROL_ID_RE.fullmatch("AID-D2-001")
    assert CONTROL_ID_RE.fullmatch("AID-AGENT007-001.002")
    assert CONTROL_ID_RE.fullmatch("AID-GOVERNANCE-001")
    assert ANY_AIDEFEND_ID_RE.fullmatch("AID-X9-001.002.S12")
    assert ANY_AIDEFEND_ID_RE.fullmatch("AID-X9-001-G004")
    assert not CONTROL_ID_RE.fullmatch("AID-9D-001")


def test_missing_control_fixture_is_derived_when_old_sentinel_becomes_live():
    records = _synthetic_records()
    records.append(
        {
            "source_id": "AID-SMOKEMISSING0-999",
            "type": "technique",
            "name": "Previously absent sentinel",
            "is_parent_family": False,
            "is_actionable": True,
            "has_code_snippets": False,
            "defends_against": "[]",
            "implementation_guidance": "[]",
            "parent_technique_id": "",
            "tools_opensource": "[]",
            "tools_source_available": "[]",
            "tools_commercial": "[]",
        }
    )

    fixtures = select_dynamic_fixtures(records)

    assert fixtures.missing_control_id == "AID-SMOKEMISSING1-999"


def test_absent_code_and_threat_capabilities_accept_successful_empty_transports():
    records = _synthetic_records()
    records[1]["has_code_snippets"] = False
    records[1]["implementation_guidance"] = "[]"
    records[2]["defends_against"] = "[]"
    fixtures = select_dynamic_fixtures(records)
    cases = {case.name: case for case in build_smoke_cases(fixtures)}

    validate_mcp_text(
        cases["get_defenses_for_threat"],
        "# Defense Techniques for Threat\n\n**Results:** 0\n",
        fixtures,
        sync_skipped=True,
    )
    validate_mcp_text(
        cases["get_secure_code_snippet"],
        "# Secure Code Snippets\n\n**Snippets Found:** 0\n",
        fixtures,
        sync_skipped=True,
    )
    validate_rest_payload(
        cases["get_defenses_for_threat"],
        {"total_results": 0, "defense_techniques": []},
        fixtures,
        sync_skipped=True,
    )
    validate_rest_payload(
        cases["get_secure_code_snippet"],
        {"total_snippets": 0, "code_snippets": []},
        fixtures,
        sync_skipped=True,
    )

    with pytest.raises(SmokeFailure, match="unmapped capability probe"):
        validate_mcp_text(
            cases["get_defenses_for_threat"],
            "# Defense Techniques for Threat\n\n**Results:** 1\nAID-H-001.001\n",
            fixtures,
            sync_skipped=True,
        )
    with pytest.raises(SmokeFailure, match="zero snippets"):
        validate_mcp_text(
            cases["get_secure_code_snippet"],
            "# Secure Code Snippets\n\n**Snippets Found:** 1\n```python\npass\n```\n",
            fixtures,
            sync_skipped=True,
        )


def test_absent_source_available_and_boundary_require_empty_rest_metadata():
    records = _synthetic_records()
    records[0]["tools_source_available"] = "[]"
    records[0]["scope_boundary"] = "{}"
    fixtures = select_dynamic_fixtures(records)
    cases = {case.name: case for case in build_smoke_cases(fixtures)}

    validation_payload = {
        "valid": True,
        "technique": {
            "id": fixtures.control_ids[0],
            "pillar": [],
            "phase": [],
            "tools_opensource": [],
            "tools_source_available": [],
            "tools_commercial": [],
            "scope_boundary": {},
        },
    }
    validate_rest_payload(
        cases["validate_technique_id"],
        validation_payload,
        fixtures,
        sync_skipped=True,
    )

    detail_payload = {
        "technique": {
            "id": fixtures.control_ids[0],
            "pillar": [],
            "phase": [],
            "warnings": [],
            "tools": {
                "opensource": [],
                "source_available": [],
                "commercial": [],
            },
            "scope_boundary": {},
        },
        "subtechniques": [],
        "strategies": [],
        "metadata": {},
    }
    validate_rest_payload(
        cases["get_technique_detail"],
        detail_payload,
        fixtures,
        sync_skipped=True,
    )

    comparison_payload = {
        "summary": {
            "techniques_compared": 2,
            "techniques_not_found": [],
        },
        "comparison_matrix": [
            {
                "source_id": control_id,
                "tools_opensource": [],
                "tools_source_available": [],
                "tools_commercial": [],
                "scope_boundary": {},
            }
            for control_id in fixtures.control_ids
        ],
    }
    validate_rest_payload(
        cases["compare_techniques"],
        comparison_payload,
        fixtures,
        sync_skipped=True,
    )

    validation_payload["technique"]["tools_source_available"] = ["Unexpected"]
    with pytest.raises(SmokeFailure, match="capability probe found none"):
        validate_rest_payload(
            cases["validate_technique_id"],
            validation_payload,
            fixtures,
            sync_skipped=True,
        )


@pytest.mark.parametrize(
    ("case_name", "text"),
    [
        (
            "validate_technique_id",
            "# Technique ID Validation\n\nValid Technique ID\nAID-H-001.001\n"
            "## Scope Boundary\nValidate input at the trust boundary.\n"
            "## Tools\n**Source Available / Open Weight:**\n",
        ),
        (
            "get_technique_detail",
            "# Description\nAID-H-001.001\n## Scope Boundary\n"
            "Validate input at the trust boundary.\nAID-D-002\n"
            "## Tools\n**Source Available / Open Weight:**\n",
        ),
        (
            "compare_techniques",
            "# Technique Comparison Matrix\n**Techniques Compared:** 2\n"
            "AID-H-001.001\nAID-D-002\n## Scope Boundary\n"
            "Validate input at the trust boundary.\n"
            "## Tools\n**Source Available / Open Weight:**\n",
        ),
    ],
)
def test_selected_control_mcp_renderers_require_exact_source_available_tools(
    case_name, text
):
    fixtures = select_dynamic_fixtures(_synthetic_records())
    case = next(case for case in build_smoke_cases(fixtures) if case.name == case_name)
    complete = text + f"- {SOURCE_AVAILABLE_TOOL}\n"

    validate_mcp_text(case, complete, fixtures, sync_skipped=True)

    with pytest.raises(SmokeFailure, match="omitted exact source-available tool"):
        validate_mcp_text(case, text, fixtures, sync_skipped=True)


def test_rest_validation_requires_three_direct_tool_arrays_and_exact_values():
    fixtures = select_dynamic_fixtures(_synthetic_records())
    case = next(
        case for case in build_smoke_cases(fixtures)
        if case.name == "validate_technique_id"
    )
    payload = {
        "valid": True,
        "technique": {
            "id": fixtures.boundary_control_id,
            "pillar": ["app"],
            "phase": ["operation"],
            "tools_opensource": ["BoundaryGuard OSS"],
            "tools_source_available": [SOURCE_AVAILABLE_TOOL],
            "tools_commercial": ["BoundaryGuard Cloud"],
            "scope_boundary": {
                "responsibility": fixtures.boundary_responsibility,
                "relatedTechniques": [],
            },
        },
    }

    validate_rest_payload(case, payload, fixtures, sync_skipped=True)

    payload["technique"]["tools_source_available"] = ["Wrong Tool"]
    with pytest.raises(SmokeFailure, match="changed exact values or order"):
        validate_rest_payload(case, payload, fixtures, sync_skipped=True)


def test_rest_detail_requires_three_nested_tool_arrays_and_exact_values():
    fixtures = select_dynamic_fixtures(_synthetic_records())
    case = next(
        case for case in build_smoke_cases(fixtures)
        if case.name == "get_technique_detail"
    )
    payload = {
        "technique": {
            "id": fixtures.boundary_control_id,
            "pillar": ["app"],
            "phase": ["operation"],
            "warnings": [],
            "tools": {
                "opensource": ["BoundaryGuard OSS"],
                "source_available": [SOURCE_AVAILABLE_TOOL],
                "commercial": ["BoundaryGuard Cloud"],
            },
            "scope_boundary": {
                "responsibility": fixtures.boundary_responsibility,
                "relatedTechniques": [
                    {"id": fixtures.boundary_related_ids[0], "comparison": "Related"}
                ],
            },
        },
        "subtechniques": [],
        "strategies": [],
        "metadata": {},
    }

    validate_rest_payload(case, payload, fixtures, sync_skipped=True)

    del payload["technique"]["tools"]["commercial"]
    with pytest.raises(SmokeFailure, match=r"tools\.commercial must be an array"):
        validate_rest_payload(case, payload, fixtures, sync_skipped=True)


def test_rest_defenses_require_three_direct_tool_arrays_on_every_result():
    fixtures = select_dynamic_fixtures(_synthetic_records())
    case = next(
        case for case in build_smoke_cases(fixtures)
        if case.name == "get_defenses_for_threat"
    )
    payload = {
        "total_results": 1,
        "defense_techniques": [
            {
                "technique": {
                    "id": "AID-D-002",
                    "tools_opensource": [],
                    "tools_source_available": [],
                    "tools_commercial": [],
                }
            }
        ],
    }

    validate_rest_payload(case, payload, fixtures, sync_skipped=True)

    payload["defense_techniques"][0]["technique"]["tools_source_available"] = {}
    with pytest.raises(SmokeFailure, match="tools_source_available must be an array"):
        validate_rest_payload(case, payload, fixtures, sync_skipped=True)


def test_rest_comparison_requires_three_direct_arrays_and_exact_boundary_values():
    fixtures = select_dynamic_fixtures(_synthetic_records())
    case = next(
        case for case in build_smoke_cases(fixtures)
        if case.name == "compare_techniques"
    )
    payload = {
        "summary": {"techniques_compared": 2, "techniques_not_found": []},
        "comparison_matrix": [
            {
                "source_id": fixtures.boundary_control_id,
                "tools_opensource": ["BoundaryGuard OSS"],
                "tools_source_available": [SOURCE_AVAILABLE_TOOL],
                "tools_commercial": ["BoundaryGuard Cloud"],
                "scope_boundary": {
                    "responsibility": fixtures.boundary_responsibility,
                    "relatedTechniques": [],
                },
            },
            {
                "source_id": fixtures.control_ids[1],
                "tools_opensource": [],
                "tools_source_available": [],
                "tools_commercial": [],
            },
        ],
    }

    validate_rest_payload(case, payload, fixtures, sync_skipped=True)

    payload["comparison_matrix"][0]["tools_source_available"] = ["Wrong Tool"]
    with pytest.raises(SmokeFailure, match="changed exact values or order"):
        validate_rest_payload(case, payload, fixtures, sync_skipped=True)
