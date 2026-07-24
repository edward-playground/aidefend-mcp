"""Focused MCP rendering and protocol-error contracts for framework schema 2.3."""

import pytest
from mcp.server import Server
from mcp.types import CallToolRequest, CallToolRequestParams

import mcp_server
from app.schemas import ContextChunk


def _disable_audit(monkeypatch):
    monkeypatch.setattr(mcp_server, "audit_tool_call", lambda *args, **kwargs: object())
    monkeypatch.setattr(mcp_server, "audit_tool_completion", lambda *args, **kwargs: None)


def _comparison_record(source_id, scope_boundary=None):
    record = {
        "source_id": source_id,
        "name": f"Control {source_id}",
        "effectiveness_score": 80,
        "complexity_score": 30,
        "cost_score": 20,
        "tactic": "Harden",
        "pillar": ["model"],
        "phase": ["building"],
        "threat_coverage": {
            "owasp": 0,
            "atlas": 0,
            "maestro": 0,
            "by_framework": {},
        },
        "has_implementation_guidance": False,
        "has_code_snippets": False,
        "has_opensource_tools": False,
        "has_commercial_tools": False,
        "description": "A control description.",
    }
    if scope_boundary is not None:
        record["scope_boundary"] = scope_boundary
    return record


def test_scope_boundary_formatter_omits_absent_empty_and_malformed_values():
    assert mcp_server._format_scope_boundary(None) == ""
    assert mcp_server._format_scope_boundary({}) == ""
    assert mcp_server._format_scope_boundary({"responsibility": "   "}) == ""
    assert mcp_server._format_scope_boundary("not-an-object") == ""


@pytest.mark.asyncio
async def test_statistics_renderer_exposes_schema23_inventory_and_tolerates_legacy_sections(
    monkeypatch,
):
    _disable_audit(monkeypatch)

    base = {
        "overview": {
            "total_documents": 1200,
            "total_techniques": 92,
            "total_subtechniques": 263,
            "total_strategies": 845,
            "last_synced": "2026-07-22T00:00:00Z",
        },
        "by_tactic": {"Harden": 500},
        "threat_framework_coverage": {
            "by_framework": {
                "atlas": {
                    "label": "MITRE ATLAS",
                    "items_covered": 150,
                    "total_items": None,
                    "coverage_percentage": None,
                }
            },
            "techniques_with_threat_mappings": 298,
            "techniques_mapped_percentage": 100.0,
        },
    }
    current = {
        **base,
        "overview": {
            **base["overview"],
            "total_actionable_items": 298,
            "total_parent_families": 57,
            "total_standalone_techniques": 35,
        },
        "actionable_by_tactic": {"Harden": 80},
        "by_pillar": {"app": 120, "model": 90},
        "by_phase": {"building": 140, "operation": 200},
        "tools_availability": {
            "techniques_with_opensource_tools": 200,
            "techniques_with_source_available_tools": 250,
            "techniques_with_commercial_tools": 275,
            "controls_with_scope_boundaries": 353,
            "actionable_controls_with_scope_boundaries": 296,
            "opensource_coverage_percentage": 67.1,
            "source_available_coverage_percentage": 83.9,
            "commercial_coverage_percentage": 92.3,
        },
        "implementation_resources": {
            "documents_with_code_snippets": 800,
            "canonical_guidance_documents": 845,
            "strategies_total": 845,
            "code_coverage_percentage": 94.7,
        },
    }
    responses = [current, base]

    async def fake_statistics():
        return responses.pop(0)

    monkeypatch.setattr(mcp_server, "get_statistics", fake_statistics)
    output = (await mcp_server.handle_get_statistics({}))[0].text

    for expected in (
        "**Actionable Controls:** 298",
        "**Parent Families:** 57",
        "**Standalone Techniques:** 35",
        "## Actionable Controls by Pillar",
        "## Actionable Controls by Phase",
        "**Open Source:** 200 controls (67.1%)",
        "**Source Available / Open Weight:** 250 controls (83.9%)",
        "**Commercial:** 275 controls (92.3%)",
        "**Controls with Scope Boundaries:** 353",
        "**Actionable Controls with Scope Boundaries:** 296",
        "**Guidance Records:** 845",
        "**Canonical Guidance IDs:** 845",
        "**Guidance Records with Code:** 800",
        "**Guidance Code Coverage:** 94.7%",
    ):
        assert expected in output

    legacy_output = (await mcp_server.handle_get_statistics({}))[0].text
    assert "# AIDEFEND Knowledge Base Statistics" in legacy_output
    assert "## Tool and Scope Availability" not in legacy_output


@pytest.mark.asyncio
async def test_technique_detail_renders_main_and_child_scope_boundaries(monkeypatch):
    _disable_audit(monkeypatch)

    async def fake_detail(*args, **kwargs):
        return {
            "metadata": {"total_subtechniques": 2},
            "technique": {
                "id": "AID-H-001",
                "name": "Parent control",
                "tactic": "Harden",
                "type": "technique",
                "description": "Parent description.",
                "scope_boundary": {
                    "responsibility": "Owns model hardening <only>.",
                    "relatedTechniques": [
                        {
                            "id": "AID-D-001",
                            "comparison": "Hardening changes behavior.\nDetection observes it.",
                        }
                    ],
                },
            },
            "subtechniques": [
                {
                    "id": "AID-H-001.001",
                    "name": "Scoped child",
                    "pillar": ["model"],
                    "phase": ["building"],
                    "warnings": [],
                    "scope_boundary": {
                        "responsibility": "Owns the child-specific control.",
                        "relatedTechniques": [],
                    },
                },
                {
                    "id": "AID-H-001.002",
                    "name": "Legacy child without boundary",
                    "pillar": ["model"],
                    "phase": ["validation"],
                    "warnings": [],
                    "scope_boundary": {},
                },
            ],
        }

    monkeypatch.setattr(mcp_server, "get_technique_detail", fake_detail)
    response = await mcp_server.handle_get_technique_detail({"technique_id": "AID-H-001"})
    output = response[0].text

    assert "## Scope Boundary" in output
    assert "#### Scope Boundary" in output
    assert output.count("Scope Boundary") == 2
    assert "Owns model hardening &lt;only&gt;." in output
    assert "**AID-D-001:** Hardening changes behavior. Detection observes it." in output
    assert "Owns the child-specific control." in output


@pytest.mark.asyncio
async def test_technique_detail_renders_all_tools_guidance_and_code(monkeypatch):
    _disable_audit(monkeypatch)

    strategy = {
        "guidance_id": "AID-H-002.002-G001",
        "implementation": "Apply the current control.",
        "how_to": "<p>Follow the <strong>verified</strong> procedure.</p>",
        "code_examples": [
            {"language": "python", "code": "policy = 'enforced'"}
        ],
    }

    async def fake_detail(*args, **kwargs):
        return {
            "metadata": {"total_subtechniques": 1},
            "technique": {
                "id": "AID-H-002",
                "name": "Current parent",
                "tactic": "Harden",
                "type": "technique",
                "description": "Parent description.",
                "scope_boundary": {},
                "tools": {
                    "opensource": ["OSS Tool"],
                    "source_available": ["Source Tool (vendor; source-available)"],
                    "commercial": ["Commercial Tool"],
                },
            },
            "strategies": [strategy],
            "subtechniques": [
                {
                    "id": "AID-H-002.002",
                    "name": "Current child",
                    "description": "Child description <current>.",
                    "pillar": ["app"],
                    "phase": ["building"],
                    "warnings": [],
                    "scope_boundary": {},
                    "defends_against": [
                        {"framework": "MITRE ATLAS", "items": ["AML.T0051"]}
                    ],
                    "tools": {
                        "opensource": [],
                        "source_available": ["Child Source Tool"],
                        "commercial": ["Child Commercial Tool"],
                    },
                    "strategies": [strategy],
                }
            ],
        }

    monkeypatch.setattr(mcp_server, "get_technique_detail", fake_detail)
    output = (
        await mcp_server.handle_get_technique_detail(
            {
                "technique_id": "AID-H-002",
                "include_code": True,
                "include_tools": True,
            }
        )
    )[0].text

    for expected in (
        "OSS Tool",
        "Source Tool",
        "Commercial Tool",
        "Child Source Tool",
        "Child Commercial Tool",
        "Child description &lt;current&gt;.",
        "AID-H-002.002-G001",
        "Apply the current control.",
        "Follow the verified procedure.",
        "policy = 'enforced'",
        "AML.T0051",
    ):
        assert expected in output
    assert output.count("Implementation Guidance") == 2


@pytest.mark.asyncio
async def test_direct_actionable_detail_renders_pillar_and_phase(monkeypatch):
    _disable_audit(monkeypatch)

    async def fake_detail(*args, **kwargs):
        return {
            "metadata": {"total_subtechniques": 0},
            "technique": {
                "id": "AID-H-002.002",
                "name": "Direct actionable control",
                "tactic": "Harden",
                "type": "subtechnique",
                "pillar": ["model", "application"],
                "phase": ["building", "operation"],
                "description": "Direct description.",
                "warnings": [],
                "scope_boundary": {},
            },
            "strategies": [],
            "subtechniques": [],
        }

    monkeypatch.setattr(mcp_server, "get_technique_detail", fake_detail)
    output = (
        await mcp_server.handle_get_technique_detail(
            {"technique_id": "AID-H-002.002"}
        )
    )[0].text

    assert "**Pillar:** model, application" in output
    assert "**Phase:** building, operation" in output


@pytest.mark.asyncio
async def test_mcp_renderers_honor_requested_result_counts(monkeypatch):
    _disable_audit(monkeypatch)

    children = [
        {
            "id": f"AID-D-005.{index:03d}",
            "name": f"Child {index}",
            "pillar": ["app"],
            "phase": ["operation"],
            "warnings": [],
            "scope_boundary": {},
        }
        for index in range(1, 12)
    ]

    async def fake_detail(*args, **kwargs):
        return {
            "metadata": {"total_subtechniques": len(children)},
            "technique": {
                "id": "AID-D-005",
                "name": "Large current family",
                "tactic": "Detect",
                "type": "technique",
                "description": "Parent description.",
                "scope_boundary": {},
            },
            "strategies": [],
            "subtechniques": children,
        }

    defenses = [
        {
            "technique": {
                "id": f"AID-H-{index:03d}",
                "name": f"Defense {index}",
                "tactic": "Harden",
                "scope_boundary": {},
            },
            "relevance_score": 1.0,
        }
        for index in range(1, 13)
    ]

    async def fake_defenses(**kwargs):
        return {
            "threat_query": {"threat_id": "LLM01"},
            "total_results": len(defenses),
            "defense_techniques": defenses,
        }

    monkeypatch.setattr(mcp_server, "get_technique_detail", fake_detail)
    monkeypatch.setattr(mcp_server, "get_defenses_for_threat", fake_defenses)

    detail_output = (
        await mcp_server.handle_get_technique_detail(
            {"technique_id": "AID-D-005"}
        )
    )[0].text
    defense_output = (
        await mcp_server.handle_get_defenses_for_threat(
            {"threat_id": "LLM01", "top_k": 12}
        )
    )[0].text

    assert "AID-D-005.011" in detail_output
    assert "AID-H-012" in defense_output
    assert defense_output.count("**Relevance:**") == 12


@pytest.mark.asyncio
async def test_compare_techniques_renders_only_present_scope_boundaries(monkeypatch):
    _disable_audit(monkeypatch)
    records = [
        _comparison_record(
            "AID-H-001",
            {
                "responsibility": "Owns training-time hardening.",
                "relatedTechniques": [],
            },
        ),
        _comparison_record("AID-D-001"),
    ]

    async def fake_compare(*args, **kwargs):
        return {
            "summary": {
                "techniques_compared": 2,
                "techniques_not_found": [],
                "average_effectiveness": 80,
                "average_complexity": 30,
                "average_cost": 20,
                "tactics_covered": ["Harden"],
                "pillars_covered": ["model"],
            },
            "comparison_matrix": records,
            "recommendations": [],
        }

    monkeypatch.setattr(mcp_server, "compare_techniques", fake_compare)
    response = await mcp_server.handle_compare_techniques(
        {
            "technique_ids": ["AID-H-001", "AID-D-001"],
            "include_recommendations": False,
        }
    )
    output = response[0].text

    assert output.count("#### Scope Boundary") == 1
    assert "Owns training-time hardening." in output
    assert "Related Techniques" not in output


@pytest.mark.asyncio
async def test_plan_and_comparison_render_source_available_tool_classification(monkeypatch):
    _disable_audit(monkeypatch)

    open_source_tool = "Open Source Comparison Tool"
    source_available_tool = (
        "Source Available Comparison Tool (Test License; source-available)"
    )
    commercial_tool = "Commercial Comparison Tool"
    records = [_comparison_record("AID-H-001"), _comparison_record("AID-D-001")]
    records[0]["has_opensource_tools"] = True
    records[0]["has_source_available_tools"] = True
    records[0]["has_commercial_tools"] = True
    records[0]["tools_opensource"] = [open_source_tool]
    records[0]["tools_source_available"] = [source_available_tool]
    records[0]["tools_commercial"] = [commercial_tool]

    async def fake_compare(*args, **kwargs):
        return {
            "summary": {
                "techniques_compared": 2,
                "techniques_not_found": [],
                "average_effectiveness": 80,
                "average_complexity": 30,
                "average_cost": 20,
                "tactics_covered": ["Harden"],
                "pillars_covered": ["model"],
            },
            "comparison_matrix": records,
            "recommendations": [],
        }

    async def fake_plan(**kwargs):
        return {
            "input": {
                "implemented_count": 0,
                "exclude_tactics": [],
            },
            "recommendations": [
                {
                    "rank": 1,
                    "technique_id": "AID-H-001",
                    "technique_name": "Source-available control",
                    "score": 7.0,
                    "tactic": "Harden",
                    "pillar": ["model"],
                    "phase": ["building"],
                    "score_breakdown": {
                        "threat_importance": 2,
                        "ease_of_implementation": 1,
                        "phase_weight": 1,
                        "pillar_weight": 2,
                        "tool_ecosystem": 1,
                    },
                    "reasoning": "Source-available tooling is present.",
                    "has_opensource_tools": False,
                    "has_source_available_tools": True,
                    "has_commercial_tools": True,
                    "tools_opensource": [open_source_tool],
                    "tools_source_available": [source_available_tool],
                    "tools_commercial": [commercial_tool],
                    "scope_boundary": {},
                }
            ],
            "categories": {"quick_wins": [], "high_priority": [], "standard": []},
        }

    monkeypatch.setattr(mcp_server, "compare_techniques", fake_compare)
    monkeypatch.setattr(mcp_server, "get_implementation_plan", fake_plan)

    comparison_output = (
        await mcp_server.handle_compare_techniques(
            {
                "technique_ids": ["AID-H-001", "AID-D-001"],
                "include_recommendations": False,
            }
        )
    )[0].text
    plan_output = (await mcp_server.handle_get_implementation_plan({}))[0].text

    label = "Source-available / open-weight tools available"
    assert label in comparison_output
    assert label in plan_output
    assert "Open-source tools available" in comparison_output
    assert "Commercial tools available" in comparison_output
    assert "Commercial tools required" not in comparison_output
    assert "Opensource tools available" not in comparison_output
    for output in (comparison_output, plan_output):
        assert "**Open Source:**" in output
        assert open_source_tool in output
        assert "**Source Available / Open Weight:**" in output
        assert source_available_tool in output
        assert "**Commercial:**" in output
        assert commercial_tool in output


@pytest.mark.asyncio
async def test_coverage_and_plan_render_shifted_id_diagnostics(monkeypatch):
    _disable_audit(monkeypatch)

    async def fake_coverage(**kwargs):
        return {
            "analysis_summary": {
                "coverage_percentage": 1.0,
                "coverage_level": "Minimal",
                "techniques_implemented": 2,
                "total_techniques_available": 200,
                "unrecognized_technique_ids": ["AID-H-025.003"],
                "expanded_parent_families": {"AID-H-001": ["AID-H-001.001", "AID-H-001.002"]},
            },
            "coverage_by_tactic": {},
            "critical_gaps": [],
            "recommendations": [],
        }

    async def fake_plan(**kwargs):
        return {
            "input": {
                "requested_count": 3,
                "implemented_count": 2,
                "invalid_count": 1,
                "unrecognized_technique_ids": ["AID-H-025.003"],
                "expanded_parent_families": {"AID-H-001": ["AID-H-001.001", "AID-H-001.002"]},
                "exclude_tactics": [],
            },
            "recommendations": [
                {
                    "rank": 1,
                    "technique_id": "AID-H-001.001",
                    "technique_name": "Recommended child",
                    "score": 8.0,
                    "tactic": "Harden",
                    "pillar": ["model"],
                    "phase": ["building"],
                    "score_breakdown": {
                        "threat_importance": 3,
                        "ease_of_implementation": 2,
                        "phase_weight": 1,
                        "pillar_weight": 1,
                        "tool_ecosystem": 1,
                    },
                    "reasoning": "High-value control.",
                    "has_opensource_tools": False,
                    "scope_boundary": {
                        "responsibility": "Plan-specific boundary.",
                        "relatedTechniques": [],
                    },
                }
            ],
            "categories": {"quick_wins": [], "high_priority": [], "standard": []},
        }

    monkeypatch.setattr(mcp_server, "analyze_coverage", fake_coverage)
    monkeypatch.setattr(mcp_server, "get_implementation_plan", fake_plan)

    coverage_text = (
        await mcp_server.handle_analyze_coverage(
            {"implemented_techniques": ["AID-H-001", "AID-H-025.003"]}
        )
    )[0].text
    plan_text = (
        await mcp_server.handle_get_implementation_plan(
            {"implemented_techniques": ["AID-H-001", "AID-H-025.003"]}
        )
    )[0].text

    for output in (coverage_text, plan_text):
        assert "Unrecognized Technique IDs" in output
        assert "AID-H-025.003" in output
        assert "Expanded Parent Families" in output
        assert "**AID-H-001** -> AID-H-001.001, AID-H-001.002" in output
    assert "**Requested Technique IDs:** 3" in plan_text
    assert "Plan-specific boundary." in plan_text


@pytest.mark.asyncio
async def test_security_posture_renders_top_level_resolution_metadata(monkeypatch):
    _disable_audit(monkeypatch)

    async def fake_posture(**kwargs):
        return {
            "view": "technical",
            "requested_count": 2,
            "implemented_count": 1,
            "implemented_actionable_count": 2,
            "invalid_technique_ids": ["AID-H-025.003"],
            "expanded_parent_families": {"AID-H-001": ["AID-H-001.001", "AID-H-001.002"]},
            "technical_coverage": {
                "analysis_summary": {
                    "coverage_percentage": 1.0,
                    "coverage_level": "Minimal",
                    "techniques_implemented": 2,
                    "total_techniques_available": 200,
                },
                "coverage_by_tactic": {},
                "critical_gaps": [],
                "recommendations": [],
            },
        }

    monkeypatch.setattr(mcp_server, "analyze_security_posture", fake_posture)
    response = await mcp_server.handle_analyze_security_posture(
        {
            "implemented_techniques": ["AID-H-001", "AID-H-025.003"],
            "view": "technical",
        }
    )
    output = response[0].text

    assert "**Requested Technique IDs:** 2" in output
    assert "**Actionable Controls Resolved:** 2" in output
    assert "Unrecognized Technique IDs" in output
    assert "AID-H-025.003" in output
    assert "Expanded Parent Families" in output


@pytest.mark.asyncio
async def test_security_posture_renders_nested_threat_scope_boundaries(monkeypatch):
    _disable_audit(monkeypatch)

    async def fake_posture(**kwargs):
        return {
            "view": "threat",
            "implemented_count": 1,
            "threat_coverage": {
                "coverage_rate": {},
                "covered": {},
                "framework_totals": {},
                "by_technique": [
                    {
                        "technique_id": "AID-H-001",
                        "technique_name": "Scoped threat control",
                        "scope_boundary": {
                            "responsibility": "Nested posture boundary.",
                            "relatedTechniques": [],
                        },
                    }
                ],
            },
        }

    monkeypatch.setattr(mcp_server, "analyze_security_posture", fake_posture)
    response = await mcp_server.handle_analyze_security_posture(
        {"implemented_techniques": ["AID-H-001"], "view": "threat"}
    )

    assert "Technique Scope Boundaries" in response[0].text
    assert "Nested posture boundary." in response[0].text


@pytest.mark.asyncio
async def test_additive_framework_labels_render_once_without_internal_prefix(monkeypatch):
    _disable_audit(monkeypatch)
    label = "OpenSSF AI Model Signing Profile"
    internal_key = f"framework:{label}"

    async def fake_threat_coverage(_implemented):
        return {
            "input_count": 1,
            "valid_count": 1,
            "invalid_count": 0,
            "invalid_techniques": [],
            "resolved_actionable_count": 1,
            "expanded_parent_families": {},
            "covered": {"owasp": [], label: ["AIM-1"]},
            "coverage_rate": {label: 0.5},
            "framework_totals": {label: 2},
            "by_technique": [],
        }

    async def fake_posture(**_kwargs):
        return {
            "view": "threat",
            "implemented_count": 1,
            "threat_coverage": await fake_threat_coverage([]),
        }

    comparison = _comparison_record("AID-H-001")
    comparison["threat_coverage"]["by_framework"] = {label: 1}

    async def fake_compare(*_args, **_kwargs):
        return {
            "summary": {
                "techniques_compared": 1,
                "techniques_not_found": [],
                "average_effectiveness": 80,
                "average_complexity": 30,
                "average_cost": 20,
                "tactics_covered": ["Harden"],
                "pillars_covered": ["model"],
            },
            "comparison_matrix": [comparison],
            "recommendations": [],
        }

    monkeypatch.setattr(mcp_server, "get_threat_coverage", fake_threat_coverage)
    threat_text = (await mcp_server.handle_get_threat_coverage({}))[0].text
    monkeypatch.setattr(mcp_server, "analyze_security_posture", fake_posture)
    posture_text = (
        await mcp_server.handle_analyze_security_posture(
            {"implemented_techniques": ["AID-H-001"], "view": "threat"}
        )
    )[0].text
    monkeypatch.setattr(mcp_server, "compare_techniques", fake_compare)
    comparison_text = (
        await mcp_server.handle_compare_techniques(
            {"technique_ids": ["AID-H-001"], "include_recommendations": False}
        )
    )[0].text

    for output in (threat_text, posture_text, comparison_text):
        assert output.count(label) == 1
        assert internal_key not in output


@pytest.mark.asyncio
async def test_registered_dispatcher_returns_mcp_error_result_on_exception(monkeypatch):
    async def failing_status():
        raise RuntimeError("protocol boom")

    monkeypatch.setattr(mcp_server, "handle_status", failing_status)
    server = Server("aidefend-mcp-error-test")
    mcp_server._register_call_tool_handler(server)

    request = CallToolRequest(
        params=CallToolRequestParams(
            name="get_aidefend_status",
            arguments={},
        )
    )
    response = await server.request_handlers[CallToolRequest](request)

    assert response.root.isError is True
    assert response.root.content[0].type == "text"
    assert "protocol boom" in response.root.content[0].text


@pytest.mark.asyncio
async def test_legacy_handlers_propagate_validation_readiness_and_runtime_failures(
    monkeypatch,
):
    with pytest.raises(mcp_server.InputValidationError, match="cannot be empty"):
        await mcp_server.handle_query({"query": ""})

    class RejectingQueryRequest:
        def __init__(self, **kwargs):
            raise mcp_server.SecurityError("rejected query")

    monkeypatch.setattr(mcp_server, "QueryRequest", RejectingQueryRequest)
    with pytest.raises(mcp_server.SecurityError, match="rejected query"):
        await mcp_server.handle_query({"query": "valid-looking input"})

    monkeypatch.undo()

    async def not_ready(_request):
        raise mcp_server.QueryEngineNotInitializedError("database not ready")

    monkeypatch.setattr(mcp_server.query_engine, "search", not_ready)
    with pytest.raises(mcp_server.QueryEngineNotInitializedError, match="database not ready"):
        await mcp_server.handle_query({"query": "prompt injection"})

    async def runtime_failure(_request):
        raise RuntimeError("search crashed")

    monkeypatch.setattr(mcp_server.query_engine, "search", runtime_failure)
    with pytest.raises(RuntimeError, match="search crashed"):
        await mcp_server.handle_query({"query": "prompt injection"})

    async def stats_failure():
        raise RuntimeError("stats crashed")

    monkeypatch.setattr(mcp_server.query_engine, "get_stats", stats_failure)
    with pytest.raises(RuntimeError, match="stats crashed"):
        await mcp_server.handle_status()

    async def unsuccessful_sync():
        return False

    monkeypatch.setattr(mcp_server, "run_sync", unsuccessful_sync)
    monkeypatch.setattr(mcp_server, "get_last_sync_error", lambda: "index rejected")
    with pytest.raises(RuntimeError, match="index rejected"):
        await mcp_server.handle_sync()

    async def sync_crash():
        raise RuntimeError("sync crashed")

    monkeypatch.setattr(mcp_server, "run_sync", sync_crash)
    with pytest.raises(RuntimeError, match="sync crashed"):
        await mcp_server.handle_sync()


@pytest.mark.asyncio
async def test_registered_legacy_handler_failure_is_mcp_error(monkeypatch):
    server = Server("aidefend-mcp-legacy-error-test")
    mcp_server._register_call_tool_handler(server)
    query_request = CallToolRequest(
        params=CallToolRequestParams(name="query_aidefend", arguments={"query": ""})
    )
    query_response = await server.request_handlers[CallToolRequest](query_request)

    async def stats_failure():
        raise RuntimeError("stats failed")

    monkeypatch.setattr(mcp_server.query_engine, "get_stats", stats_failure)
    status_request = CallToolRequest(
        params=CallToolRequestParams(name="get_aidefend_status", arguments={})
    )
    status_response = await server.request_handlers[CallToolRequest](status_request)

    async def unsuccessful_sync():
        return False

    monkeypatch.setattr(mcp_server, "run_sync", unsuccessful_sync)
    monkeypatch.setattr(mcp_server, "get_last_sync_error", lambda: "sync failed")
    sync_request = CallToolRequest(params=CallToolRequestParams(name="sync_aidefend", arguments={}))
    sync_response = await server.request_handlers[CallToolRequest](sync_request)

    assert query_response.root.isError is True
    assert "cannot be empty" in query_response.root.content[0].text
    assert status_response.root.isError is True
    assert "stats failed" in status_response.root.content[0].text
    assert sync_response.root.isError is True
    assert "sync failed" in sync_response.root.content[0].text


@pytest.mark.asyncio
async def test_chunked_query_preserves_nested_metadata_and_scope_boundary(monkeypatch):
    from app.tools import chunked_search

    boundary = {
        "responsibility": "Chunked-query boundary.",
        "relatedTechniques": [],
    }

    async def fake_chunked_search(**kwargs):
        return {
            "results": [
                {
                    "source_id": "AID-H-001",
                    "tactic": "Harden",
                    "text": "Chunked result description.",
                    "metadata": {
                        "type": "technique",
                        "name": "Nested metadata control",
                        "pillar": ["model"],
                        "phase": ["building"],
                        "scope_boundary": boundary,
                    },
                    "score": 0.2,
                }
            ]
        }

    monkeypatch.setattr(mcp_server.settings, "MAX_QUERY_LENGTH", 1)
    monkeypatch.setattr(chunked_search, "search_with_chunking", fake_chunked_search)

    output = (await mcp_server.handle_query({"query": "long query"}))[0].text

    assert "Nested metadata control" in output
    assert "**Type:** Technique" in output
    assert "Chunked-query boundary." in output
    assert "N/A" not in output


def test_regular_query_result_renders_scope_boundary_and_exact_tool_inventory():
    result = ContextChunk(
        source_id="AID-H-001",
        tactic="Harden",
        text="Result description.",
        metadata={
            "type": "technique",
            "name": "Scoped search result",
            "scope_boundary": {
                "responsibility": "Search-result boundary.",
                "relatedTechniques": [],
            },
            "tools_opensource": ["Query OSS Tool"],
            "tools_source_available": [
                "Query Open Weight Tool (Test License; open-weight)"
            ],
            "tools_commercial": ["Query Commercial Tool"],
        },
        score=0.2,
    )

    output = mcp_server.format_search_results("hardening", [result], 1)

    assert "Search-result boundary." in output
    assert "**Open Source:**" in output
    assert "Query OSS Tool" in output
    assert "**Source Available / Open Weight:**" in output
    assert "Query Open Weight Tool (Test License; open-weight)" in output
    assert "**Commercial:**" in output
    assert "Query Commercial Tool" in output


@pytest.mark.asyncio
async def test_other_structured_mcp_results_render_scope_boundary(monkeypatch):
    _disable_audit(monkeypatch)
    boundary = {
        "responsibility": "Cross-tool boundary marker.",
        "relatedTechniques": [],
    }
    open_source_tool = "Open Source Test Tool"
    source_available_tool = (
        "Source Available Test Tool (Test License; source-available)"
    )
    commercial_tool = "Commercial Test Tool"

    async def fake_validation(_technique_id):
        return {
            "valid": True,
            "technique": {
                "id": "AID-H-001",
                "name": "Validated control",
                "type": "technique",
                "tactic": "Harden",
                "pillar": ["model"],
                "phase": ["building"],
                "scope_boundary": boundary,
                "tools_opensource": [open_source_tool],
                "tools_source_available": [source_available_tool],
                "tools_commercial": [commercial_tool],
                "is_actionable": True,
                "is_parent_family": False,
            },
        }

    async def fake_defenses(**kwargs):
        return {
            "threat_query": {"threat_keyword": "prompt injection"},
            "total_results": 1,
            "defense_techniques": [
                {
                    "technique": {
                        "id": "AID-H-001",
                        "name": "Defense",
                        "tactic": "Harden",
                        "scope_boundary": boundary,
                        "tools_opensource": [open_source_tool],
                        "tools_source_available": [source_available_tool],
                        "tools_commercial": [commercial_tool],
                    },
                    "relevance_score": 1.0,
                }
            ],
        }

    async def fake_snippets(**kwargs):
        return {
            "query": {"technique_id": "AID-H-001"},
            "total_snippets": 1,
            "code_snippets": [
                {
                    "technique_name": "Snippet control",
                    "technique_id": "AID-H-001",
                    "language": "python",
                    "implementation": "Use the control.",
                    "code": "pass",
                    "scope_boundary": boundary,
                    "tools_opensource": [open_source_tool],
                    "tools_source_available": [source_available_tool],
                    "tools_commercial": [commercial_tool],
                }
            ],
        }

    async def fake_compliance(**kwargs):
        return {
            "framework": {"name": "NIST", "version": "1"},
            "total_mapped": 1,
            "mappings": [
                {
                    "technique_id": "AID-H-001",
                    "technique_name": "Mapped control",
                    "framework_controls": [],
                    "mapping_confidence": "medium",
                    "scope_boundary": boundary,
                }
            ],
            "disclaimer": "Review this mapping.",
        }

    async def fake_quick_reference(**kwargs):
        return {
            "topic": "hardening",
            "total_items": 1,
            "formatted_output": "Checklist body.",
            "quick_wins": [
                {
                    "technique_id": "AID-H-001",
                    "name": "Quick control",
                    "scope_boundary": boundary,
                    "tools_opensource": [open_source_tool],
                    "tools_source_available": [source_available_tool],
                    "tools_commercial": [commercial_tool],
                }
            ],
            "must_haves": [],
            "nice_to_haves": [],
        }

    async def fake_threat_coverage(_implemented):
        return {
            "input_count": 1,
            "valid_count": 1,
            "invalid_count": 0,
            "invalid_techniques": [],
            "resolved_actionable_count": 1,
            "expanded_parent_families": {},
            "covered": {"owasp": [], "atlas": []},
            "coverage_rate": {},
            "framework_totals": {},
            "by_technique": [
                {
                    "technique_id": "AID-H-001",
                    "technique_name": "Threat control",
                    "coverage_scope": "single_control",
                    "threats_covered": {},
                    "scope_boundary": boundary,
                }
            ],
        }

    async def fake_comprehensive(**kwargs):
        return {
            "input_topic": "hardening",
            "queries_executed": ["hardening"],
            "total_results_after_dedup": 1,
            "total_results_before_dedup": 1,
            "coverage_summary": {
                "techniques": 1,
                "subtechniques": 0,
                "tactics_covered": ["Harden"],
            },
            "results": [
                {
                    "name": "Search control",
                    "source_id": "AID-H-001",
                    "tactic": "Harden",
                    "type": "technique",
                    "_distance": 0.2,
                    "matched_query": "hardening",
                    "description": "Description.",
                    "scope_boundary": boundary,
                    "tools_opensource": [open_source_tool],
                    "tools_source_available": [source_available_tool],
                    "tools_commercial": [commercial_tool],
                }
            ],
            "related_searches": [],
        }

    async def fake_playbook(**kwargs):
        return {
            "generated_at": "2026-07-22T00:00:00Z",
            "incident_summary": {
                "description": "Incident description.",
                "total_action_items": 0,
                "estimated_total_time": "0 minutes",
            },
            "timeline": {},
            "defense_techniques": {
                "defense_techniques": [
                    {
                        "technique": {
                            "id": "AID-H-001",
                            "name": "Incident control",
                            "tactic": "Harden",
                            "description": "Description.",
                            "scope_boundary": boundary,
                            "tools_opensource": [open_source_tool],
                            "tools_source_available": [source_available_tool],
                            "tools_commercial": [commercial_tool],
                        }
                    }
                ]
            },
            "threat_classification": None,
        }

    calls = [
        (
            "validate_technique_id",
            fake_validation,
            mcp_server.handle_validate_technique_id,
            {"technique_id": "AID-H-001"},
        ),
        ("get_defenses_for_threat", fake_defenses, mcp_server.handle_get_defenses_for_threat, {}),
        ("get_secure_code_snippet", fake_snippets, mcp_server.handle_get_secure_code_snippet, {}),
        (
            "map_to_compliance_framework",
            fake_compliance,
            mcp_server.handle_map_to_compliance_framework,
            {},
        ),
        ("get_quick_reference", fake_quick_reference, mcp_server.handle_get_quick_reference, {}),
        ("get_threat_coverage", fake_threat_coverage, mcp_server.handle_get_threat_coverage, {}),
        (
            "comprehensive_search",
            fake_comprehensive,
            mcp_server.handle_comprehensive_search,
            {},
        ),
        (
            "generate_incident_playbook",
            fake_playbook,
            mcp_server.handle_generate_incident_playbook,
            {"incident_description": "Incident description."},
        ),
    ]

    for attribute, fake_tool, handler, arguments in calls:
        monkeypatch.setattr(mcp_server, attribute, fake_tool)
        output = (await handler(arguments))[0].text
        assert "Cross-tool boundary marker." in output, attribute
        if attribute in {
            "validate_technique_id",
            "get_defenses_for_threat",
            "get_secure_code_snippet",
            "get_quick_reference",
            "comprehensive_search",
            "generate_incident_playbook",
        }:
            assert "**Open Source:**" in output, attribute
            assert open_source_tool in output, attribute
            assert "**Source Available / Open Weight:**" in output, attribute
            assert source_available_tool in output, attribute
            assert "**Commercial:**" in output, attribute
            assert commercial_tool in output, attribute
