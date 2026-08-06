#!/usr/bin/env python3
"""End-to-end smoke test for all AIDEFEND REST and MCP tools.

The default run is deliberately offline-safe: it requires an already-built
``DATA_PATH`` and replaces only the explicit manual-sync call with a successful
no-op. Startup, database access, model loading, FastAPI routing, MCP stdio
transport, and every other tool implementation are real.

Examples::

    python scripts/smoke_all_tools.py
    python scripts/smoke_all_tools.py --data-path C:\\path\\to\\data
    python scripts/smoke_all_tools.py --transport rest
    python scripts/smoke_all_tools.py --allow-sync  # may access the network
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

EXPECTED_TOOL_NAMES = (
    "query_aidefend",
    "get_aidefend_status",
    "sync_aidefend",
    "get_statistics",
    "validate_technique_id",
    "get_technique_detail",
    "get_defenses_for_threat",
    "get_secure_code_snippet",
    "analyze_coverage",
    "map_to_compliance_framework",
    "get_quick_reference",
    "get_threat_coverage",
    "get_implementation_plan",
    "classify_threat",
    "comprehensive_search",
    "analyze_security_posture",
    "compare_techniques",
    "generate_incident_playbook",
)

OPENAPI_HTTP_METHODS = {
    "delete",
    "get",
    "head",
    "options",
    "patch",
    "post",
    "put",
    "trace",
}


def openapi_route_inventory(app) -> set[tuple[str, str]]:
    """Return public HTTP operations without depending on router internals.

    FastAPI 0.139 keeps included routers behind private ``_IncludedRouter``
    objects, so iterating ``app.routes`` no longer exposes their leaf routes.
    OpenAPI is the stable public contract exercised by this smoke test.
    """
    schema = app.openapi()
    paths = schema.get("paths")
    if not isinstance(paths, dict):
        raise SmokeFailure("FastAPI OpenAPI schema has no paths object")

    inventory: set[tuple[str, str]] = set()
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            raise SmokeFailure("FastAPI OpenAPI paths contain an invalid path item")
        for method in path_item:
            normalized = str(method).lower()
            if normalized in OPENAPI_HTTP_METHODS:
                inventory.add((normalized.upper(), path))
    return inventory

INTEGER_TOOL_PARAMETERS = {
    "query_aidefend": "top_k",
    "get_defenses_for_threat": "top_k",
    "get_secure_code_snippet": "max_snippets",
    "get_quick_reference": "max_items",
    "get_implementation_plan": "top_k",
    "classify_threat": "top_k",
    "comprehensive_search": "max_results",
}

TACTIC_ID_SEGMENT = r"[A-Z][A-Z0-9]*"
CONTROL_ID_RE = re.compile(
    rf"^AID-{TACTIC_ID_SEGMENT}-\d{{3}}(?:\.\d{{3}})?$"
)
ANY_AIDEFEND_ID_RE = re.compile(
    rf"\bAID-{TACTIC_ID_SEGMENT}-\d{{3}}(?:\.\d{{3}})?"
    rf"(?:(?:\.S\d+)|(?:-G\d{{3}}))?\b"
)
THREAT_ID_RE = re.compile(
    r"\b(AML\.T\d{4}(?:\.\d{3})?|LLM\d{2}(?::\d{4})?|"
    r"ML\d{2}:\d{4}|ASI\d{2}:\d{4}|NISTAML\.\d{3})\b",
    re.IGNORECASE,
)
UNMAPPED_THREAT_ID = "AIDEFEND-SMOKE-UNMAPPED"


class SmokeFailure(AssertionError):
    """Raised when a transport or response contract fails its smoke check."""


@dataclass(frozen=True)
class DynamicFixtures:
    """Known-good inputs selected from the live LanceDB table."""

    control_ids: tuple[str, str]
    boundary_control_id: str
    boundary_responsibility: str
    boundary_related_ids: tuple[str, ...]
    source_available_control_id: str
    source_available_tools: tuple[str, ...]
    code_control_id: str
    missing_control_id: str
    threat_id: str
    topic: str
    row_count: int


@dataclass(frozen=True)
class SmokeCase:
    """One MCP tool and its corresponding REST route invocation."""

    name: str
    method: str
    route_path: str
    path: str
    mcp_arguments: Mapping[str, Any]
    mcp_heading: str
    rest_params: Mapping[str, Any] | None = None
    rest_json: Any = None


def _decode_json(value: Any, default: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _iter_threat_items(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return
        if not stripped.startswith(("[", "{")):
            yield stripped
            return
        decoded = _decode_json(stripped, [])
    else:
        decoded = value
    if isinstance(decoded, list):
        for entry in decoded:
            yield from _iter_threat_items(entry)
        return
    if isinstance(decoded, dict):
        items = decoded.get("items")
        if items is not None:
            yield from _iter_threat_items(items)
        else:
            for entry in decoded.values():
                yield from _iter_threat_items(entry)


def _record_contains_code(record: Mapping[str, Any]) -> bool:
    if not bool(record.get("has_code_snippets")):
        return False
    guidance = record.get("implementation_guidance", [])
    serialized = json.dumps(_decode_json(guidance, []), ensure_ascii=False).lower()
    return "<code" in serialized or "<pre" in serialized or "```" in serialized


def select_dynamic_fixtures(records: Sequence[Mapping[str, Any]]) -> DynamicFixtures:
    """Select live controls and record which optional capabilities are present."""
    controls: dict[str, Mapping[str, Any]] = {}
    parent_family_ids = {
        str(record.get("parent_technique_id") or "").strip().upper()
        for record in records
        if str(record.get("type") or "").lower() == "subtechnique"
    }
    for record in records:
        source_id = str(record.get("source_id") or "").strip().upper()
        record_type = str(record.get("type") or "").lower()
        if CONTROL_ID_RE.fullmatch(source_id) and record_type in {
            "technique",
            "subtechnique",
        }:
            if bool(record.get("is_parent_family")) or source_id in parent_family_ids:
                continue
            is_actionable = record.get("is_actionable")
            if is_actionable is not None and not bool(is_actionable):
                continue
            controls[source_id] = record

    if len(controls) < 2:
        raise SmokeFailure("Database must contain at least two actionable AIDEFEND controls")

    boundary_control_id = ""
    boundary_responsibility = ""
    boundary_related_ids: tuple[str, ...] = ()
    source_available_control_id = ""
    source_available_tools: tuple[str, ...] = ()
    preferred_pair_id = ""
    for control_id, record in controls.items():
        candidate_tools = _decode_json(record.get("tools_source_available"), [])
        valid_candidate_tools = (
            isinstance(candidate_tools, list)
            and bool(candidate_tools)
            and all(isinstance(tool, str) and tool.strip() for tool in candidate_tools)
        )
        if valid_candidate_tools and not source_available_control_id:
            source_available_control_id = control_id
            source_available_tools = tuple(candidate_tools)
        scope_boundary = _decode_json(record.get("scope_boundary"), {})
        if not isinstance(scope_boundary, dict):
            continue
        responsibility = str(scope_boundary.get("responsibility") or "").strip()
        related = scope_boundary.get("relatedTechniques", [])
        if not responsibility or not isinstance(related, list):
            continue
        related_ids = tuple(
            str(item.get("id") or "").strip().upper()
            for item in related
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        )
        if responsibility and not boundary_control_id:
            boundary_control_id = control_id
            boundary_responsibility = responsibility
            boundary_related_ids = related_ids
        if valid_candidate_tools and responsibility and (
            not preferred_pair_id or related_ids
        ):
            preferred_pair_id = control_id
            source_available_control_id = control_id
            source_available_tools = tuple(candidate_tools)
            boundary_control_id = control_id
            boundary_responsibility = responsibility
            boundary_related_ids = related_ids
            if related_ids:
                break

    code_control_id = ""
    for record in records:
        if not _record_contains_code(record):
            continue
        source_id = str(record.get("source_id") or "").strip().upper()
        parent_id = str(record.get("parent_technique_id") or "").strip().upper()
        candidate = parent_id if parent_id in controls else source_id
        if candidate in controls:
            code_control_id = candidate
            break
    mapped_control_id = ""
    mapped_threat_id = ""
    for control_id, record in controls.items():
        for item in _iter_threat_items(record.get("defends_against", [])):
            match = THREAT_ID_RE.search(item)
            if match:
                mapped_control_id = control_id
                mapped_threat_id = match.group(1).upper()
                break
        if mapped_threat_id:
            break
    selected = []
    for control_id in (
        preferred_pair_id,
        source_available_control_id,
        boundary_control_id,
        mapped_control_id,
        *controls,
    ):
        if len(selected) == 2:
            break
        if control_id and control_id not in selected:
            selected.append(control_id)

    topic = str(controls[selected[0]].get("name") or "AI security defense").strip()
    if len(topic) < 3:
        topic = "AI security defense"

    existing_ids = {
        str(record.get("source_id") or "").strip().upper()
        for record in records
        if str(record.get("source_id") or "").strip()
    }
    missing_control_id = ""
    # There are N live IDs and N+1 distinct candidates, so one candidate is
    # guaranteed to be absent without pinning today's tactic codes or counts.
    for index in range(len(existing_ids) + 1):
        candidate = f"AID-SMOKEMISSING{index}-999"
        if candidate not in existing_ids:
            missing_control_id = candidate
            break
    if not missing_control_id:
        raise SmokeFailure("Could not derive a syntactically valid absent control ID")

    return DynamicFixtures(
        control_ids=(selected[0], selected[1]),
        boundary_control_id=boundary_control_id,
        boundary_responsibility=boundary_responsibility,
        boundary_related_ids=boundary_related_ids,
        source_available_control_id=source_available_control_id,
        source_available_tools=source_available_tools,
        code_control_id=code_control_id,
        missing_control_id=missing_control_id,
        threat_id=mapped_threat_id,
        topic=topic[:180],
        row_count=len(records),
    )


def build_smoke_cases(fixtures: DynamicFixtures) -> list[SmokeCase]:
    """Build all 18 paired transport calls from live database fixtures."""
    controls = list(fixtures.control_ids)
    threat_id = fixtures.threat_id or UNMAPPED_THREAT_ID
    code_control_id = fixtures.code_control_id or controls[0]
    incident = "Prompt injection attempts caused an AI agent to expose restricted data."
    search_topic = "prompt injection defense"
    cases = [
        SmokeCase(
            "query_aidefend",
            "POST",
            "/api/v1/query",
            "/api/v1/query",
            {"query": fixtures.topic, "top_k": 3},
            "AIDEFEND Search Results",
            rest_json={"query_text": fixtures.topic, "top_k": 3},
        ),
        SmokeCase(
            "get_aidefend_status",
            "GET",
            "/api/v1/status",
            "/api/v1/status",
            {},
            "AIDEFEND Knowledge Base Status",
        ),
        SmokeCase(
            "sync_aidefend",
            "POST",
            "/api/v1/sync",
            "/api/v1/sync",
            {},
            "Starting AIDEFEND Knowledge Base Sync",
        ),
        SmokeCase(
            "get_statistics",
            "GET",
            "/api/v1/statistics",
            "/api/v1/statistics",
            {},
            "AIDEFEND Knowledge Base Statistics",
        ),
        SmokeCase(
            "validate_technique_id",
            "POST",
            "/api/v1/validate-technique-id",
            "/api/v1/validate-technique-id",
            {"technique_id": controls[0]},
            "Technique ID Validation",
            rest_params={"technique_id": controls[0]},
        ),
        SmokeCase(
            "get_technique_detail",
            "GET",
            "/api/v1/technique/{technique_id}",
            f"/api/v1/technique/{controls[0]}",
            {"technique_id": controls[0], "include_code": True, "include_tools": True},
            "Description",
            rest_params={"include_code": True, "include_tools": True},
        ),
        SmokeCase(
            "get_defenses_for_threat",
            "POST",
            "/api/v1/defenses-for-threat",
            "/api/v1/defenses-for-threat",
            {"threat_id": threat_id, "top_k": 5},
            "Defense Techniques for Threat",
            rest_params={"threat_id": threat_id, "top_k": 5},
        ),
        SmokeCase(
            "get_secure_code_snippet",
            "POST",
            "/api/v1/code-snippets",
            "/api/v1/code-snippets",
            {"technique_id": code_control_id, "max_snippets": 3},
            "Secure Code Snippets",
            rest_params={"technique_id": code_control_id, "max_snippets": 3},
        ),
        SmokeCase(
            "analyze_coverage",
            "POST",
            "/api/v1/analyze-coverage",
            "/api/v1/analyze-coverage",
            {"implemented_techniques": controls, "system_type": "rag"},
            "Defense Coverage Analysis",
            rest_params={"system_type": "rag"},
            rest_json=controls,
        ),
        SmokeCase(
            "map_to_compliance_framework",
            "POST",
            "/api/v1/compliance-mapping",
            "/api/v1/compliance-mapping",
            {"technique_ids": controls, "framework": "nist_ai_rmf"},
            "Compliance Mapping",
            rest_params={"framework": "nist_ai_rmf"},
            rest_json=controls,
        ),
        SmokeCase(
            "get_quick_reference",
            "POST",
            "/api/v1/quick-reference",
            "/api/v1/quick-reference",
            {"topic": search_topic, "format": "checklist", "max_items": 10},
            "Quick Reference",
            rest_params={"topic": search_topic, "format": "checklist", "max_items": 10},
        ),
        SmokeCase(
            "get_threat_coverage",
            "POST",
            "/api/v1/threat-coverage",
            "/api/v1/threat-coverage",
            {"implemented_techniques": controls},
            "Threat Coverage Analysis",
            rest_json={"implemented_techniques": controls},
        ),
        SmokeCase(
            "get_implementation_plan",
            "POST",
            "/api/v1/implementation-plan",
            "/api/v1/implementation-plan",
            {"implemented_techniques": controls, "top_k": 5, "detail_level": "basic"},
            "Defense Implementation Plan",
            rest_json={"implemented_techniques": controls, "top_k": 5, "detail_level": "basic"},
        ),
        SmokeCase(
            "classify_threat",
            "POST",
            "/api/v1/classify-threat",
            "/api/v1/classify-threat",
            {"text": incident, "top_k": 5},
            "Threat Classification Results",
            rest_json={"text": incident, "top_k": 5},
        ),
        SmokeCase(
            "comprehensive_search",
            "POST",
            "/api/v1/comprehensive-search",
            "/api/v1/comprehensive-search",
            {"topic": search_topic, "max_results": 10, "include_subtechniques": True},
            "Comprehensive Search Results",
            rest_params={
                "topic": search_topic,
                "max_results": 10,
                "include_subtechniques": True,
            },
        ),
        SmokeCase(
            "analyze_security_posture",
            "POST",
            "/api/v1/security-posture",
            "/api/v1/security-posture",
            {"implemented_techniques": controls, "view": "both", "system_type": "rag"},
            "Security Posture Analysis",
            rest_json={
                "implemented_techniques": controls,
                "view": "both",
                "system_type": "rag",
            },
        ),
        SmokeCase(
            "compare_techniques",
            "POST",
            "/api/v1/compare-techniques",
            "/api/v1/compare-techniques",
            {"technique_ids": controls, "include_recommendations": True},
            "Technique Comparison Matrix",
            rest_json={"technique_ids": controls, "include_recommendations": True},
        ),
        SmokeCase(
            "generate_incident_playbook",
            "POST",
            "/api/v1/incident-playbook",
            "/api/v1/incident-playbook",
            {"incident_description": incident, "include_defense_techniques": True},
            "Incident Response Playbook",
            rest_json={
                "incident_description": incident,
                "include_defense_techniques": True,
            },
        ),
    ]
    if tuple(case.name for case in cases) != EXPECTED_TOOL_NAMES:
        raise SmokeFailure("Internal smoke-case inventory does not match the 18-tool contract")
    return cases


def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SmokeFailure(f"{label} must be an object, got {type(value).__name__}")
    return value


def _list_field(data: Mapping[str, Any], key: str, label: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise SmokeFailure(f"{label}.{key} must be an array")
    return value


DIRECT_TOOL_LIST_FIELDS = (
    "tools_opensource",
    "tools_source_available",
    "tools_commercial",
)


def _assert_direct_tool_inventory(data: Mapping[str, Any], label: str) -> None:
    for field in DIRECT_TOOL_LIST_FIELDS:
        values = _list_field(data, field, label)
        if not all(isinstance(value, str) for value in values):
            raise SmokeFailure(f"{label}.{field} must contain only strings")


def _assert_exact_source_available_tools(
    data: Mapping[str, Any], fixtures: DynamicFixtures, label: str
) -> None:
    if not fixtures.source_available_tools:
        return
    actual = _list_field(data, "tools_source_available", label)
    if tuple(actual) != fixtures.source_available_tools:
        raise SmokeFailure(
            f"{label}.tools_source_available changed exact values or order: "
            f"expected={fixtures.source_available_tools!r}, actual={tuple(actual)!r}"
        )


def _mcp_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("`", "\\`")
    )


def _assert_mcp_source_available_inventory(
    text: str, fixtures: DynamicFixtures, label: str
) -> None:
    if not fixtures.source_available_tools:
        return
    if "Source Available / Open Weight" not in text:
        raise SmokeFailure(f"{label} omitted the source-available/open-weight category")
    for tool in fixtures.source_available_tools:
        rendered = _mcp_escape(tool)
        if rendered not in text:
            raise SmokeFailure(f"{label} omitted exact source-available tool {tool!r}")


def _dict_field(data: Mapping[str, Any], key: str, label: str) -> Mapping[str, Any]:
    return _as_mapping(data.get(key), f"{label}.{key}")


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SmokeFailure(f"{label} must be a non-negative integer")
    return value


def _positive_int(value: Any, label: str) -> int:
    parsed = _nonnegative_int(value, label)
    if parsed == 0:
        raise SmokeFailure(f"{label} must be greater than zero")
    return parsed


def _assert_control_id(value: Any, label: str) -> str:
    candidate = str(value or "")
    if not CONTROL_ID_RE.fullmatch(candidate):
        raise SmokeFailure(f"{label} is not a control ID: {candidate!r}")
    return candidate


def _assert_id_list(values: Sequence[Any], label: str) -> None:
    if not values:
        raise SmokeFailure(f"{label} must not be empty")
    for index, value in enumerate(values):
        candidate = str(value or "")
        if not ANY_AIDEFEND_ID_RE.fullmatch(candidate):
            raise SmokeFailure(f"{label}[{index}] is not an AIDEFEND ID: {candidate!r}")


def _assert_framework_arrays(value: Any, label: str) -> Mapping[str, Any]:
    frameworks = _as_mapping(value, label)
    if not frameworks:
        raise SmokeFailure(f"{label} must not be empty")
    for key, items in frameworks.items():
        if not isinstance(items, list):
            raise SmokeFailure(f"{label}.{key} must be an array")
    return frameworks


def _parse_markdown_count(text: str, label: str) -> int:
    match = re.search(rf"\*\*{re.escape(label)}:\*\*\s*([\d,]+)", text)
    if not match:
        raise SmokeFailure(f"MCP response is missing numeric '{label}'")
    return int(match.group(1).replace(",", ""))


def _parse_markdown_value(text: str, label: str) -> str:
    match = re.search(rf"\*\*{re.escape(label)}:\*\*\s*([^\r\n]+)", text)
    if not match:
        raise SmokeFailure(f"MCP response is missing '{label}'")
    return match.group(1).strip()


def assert_no_generic_mcp_error(text: str) -> None:
    """Reject error strings that MCP handlers otherwise return as normal text."""
    leading = text.lstrip().casefold()
    if leading.startswith(("error:", "failed to", "query failed:", "invalid query:")):
        raise SmokeFailure(f"MCP returned generic failure text: {text[:240]!r}")
    if "please try again or check the service logs" in leading[:600]:
        raise SmokeFailure(f"MCP returned generic error fallback: {text[:240]!r}")
    if re.search(r"(?im)^\s*\*\*[^\n]{0,12}sync failed\*\*", text[:800]):
        raise SmokeFailure(f"MCP sync reported failure: {text[:400]!r}")


def validate_mcp_text(
    case: SmokeCase,
    text: str,
    fixtures: DynamicFixtures,
    *,
    sync_skipped: bool,
) -> None:
    assert_no_generic_mcp_error(text)
    if case.mcp_heading not in text:
        raise SmokeFailure(
            f"{case.name} MCP response missing heading {case.mcp_heading!r}: {text[:240]!r}"
        )

    controls = fixtures.control_ids
    if case.name == "query_aidefend":
        if _parse_markdown_count(text, "Found") <= 0 or not ANY_AIDEFEND_ID_RE.search(text):
            raise SmokeFailure("query_aidefend returned no identifiable AIDEFEND results")
    elif case.name == "get_aidefend_status":
        if _parse_markdown_count(text, "Indexed Documents") != fixtures.row_count:
            raise SmokeFailure("MCP status document count differs from the live table")
        for label in (
            "Framework Public Schema",
            "MCP Index Schema",
            "Framework Migration Registry Schema",
        ):
            value = _parse_markdown_value(text, label)
            if value.casefold() in {"n/a", "none", "unknown", "unavailable"}:
                raise SmokeFailure(
                    f"MCP status did not report a verified {label} value"
                )
        if "Service is ready for queries" not in text:
            raise SmokeFailure("MCP status did not report a query-ready service")
    elif case.name == "sync_aidefend":
        if "Sync Completed Successfully" not in text:
            raise SmokeFailure("sync_aidefend did not report successful completion")
        if sync_skipped and "Starting AIDEFEND" not in text:
            raise SmokeFailure("offline-safe sync no-op did not traverse the real MCP handler")
    elif case.name == "get_statistics":
        if _parse_markdown_count(text, "Total Documents") != fixtures.row_count:
            raise SmokeFailure("MCP statistics document count differs from the live table")
    elif case.name in {"validate_technique_id", "get_technique_detail"}:
        if controls[0] not in text:
            raise SmokeFailure(f"{case.name} did not return the selected valid control ID")
        if case.name == "validate_technique_id" and "Valid Technique ID" not in text:
            raise SmokeFailure("validate_technique_id did not validate the live control")
        if case.name == "validate_technique_id":
            if controls[0] == fixtures.boundary_control_id and (
                "Scope Boundary" not in text
                or fixtures.boundary_responsibility not in text
            ):
                raise SmokeFailure(
                    "validation omitted the selected control's schema 2.3 boundary"
                )
        if case.name == "get_technique_detail":
            if controls[0] == fixtures.boundary_control_id:
                if "Scope Boundary" not in text:
                    raise SmokeFailure("technique detail omitted the schema 2.3 scope boundary")
                if fixtures.boundary_responsibility not in text:
                    raise SmokeFailure("technique detail omitted scopeBoundary responsibility")
                for related_id in fixtures.boundary_related_ids:
                    if related_id not in text:
                        raise SmokeFailure(
                            f"technique detail omitted scopeBoundary relationship {related_id}"
                        )
        if controls[0] == fixtures.source_available_control_id:
            _assert_mcp_source_available_inventory(text, fixtures, case.name)
    elif case.name == "get_defenses_for_threat":
        result_count = _parse_markdown_count(text, "Results")
        if fixtures.threat_id:
            if result_count <= 0 or not ANY_AIDEFEND_ID_RE.search(text):
                raise SmokeFailure("get_defenses_for_threat returned no defenses")
        elif result_count != 0:
            raise SmokeFailure(
                "get_defenses_for_threat did not return zero results for the "
                "unmapped capability probe"
            )
    elif case.name == "get_secure_code_snippet":
        snippet_count = _parse_markdown_count(text, "Snippets Found")
        if fixtures.code_control_id:
            if snippet_count <= 0:
                raise SmokeFailure("get_secure_code_snippet returned no code")
            if "```" not in text or fixtures.code_control_id not in text:
                raise SmokeFailure("code snippet response lacks code or its source control ID")
        elif snippet_count != 0:
            raise SmokeFailure(
                "get_secure_code_snippet did not return zero snippets when the "
                "live corpus has no code-bearing guidance"
            )
    elif case.name == "analyze_coverage":
        if _parse_markdown_count(text, "Implemented") != len(controls):
            raise SmokeFailure("analyze_coverage did not recognize both selected controls")
    elif case.name == "map_to_compliance_framework":
        if _parse_markdown_count(text, "Total Techniques Mapped") != len(controls):
            raise SmokeFailure("compliance mapping did not map both selected controls")
    elif case.name == "get_quick_reference":
        if not ANY_AIDEFEND_ID_RE.search(text):
            raise SmokeFailure("quick reference contains no AIDEFEND control IDs")
    elif case.name == "get_threat_coverage":
        if _parse_markdown_count(text, "Valid Techniques") != len(controls):
            raise SmokeFailure("threat coverage did not validate both controls")
        for control_id in controls:
            if control_id not in text:
                raise SmokeFailure(f"threat coverage omitted {control_id}")
    elif case.name == "get_implementation_plan":
        if _parse_markdown_count(text, "Recommendations Generated") <= 0:
            raise SmokeFailure("implementation plan returned no recommendations")
        if not ANY_AIDEFEND_ID_RE.search(text):
            raise SmokeFailure("implementation plan contains no AIDEFEND IDs")
    elif case.name == "classify_threat":
        if _parse_markdown_count(text, "Keywords Matched") <= 0:
            raise SmokeFailure("threat classifier did not recognize the incident")
        if not re.search(r"\b(?:LLM|AML\.T|ASI|NISTAML\.)", text):
            raise SmokeFailure("threat classifier returned no normalized threat ID")
    elif case.name == "comprehensive_search":
        if _parse_markdown_count(text, "Total Results") <= 0:
            raise SmokeFailure("comprehensive search returned no results")
        if not ANY_AIDEFEND_ID_RE.search(text):
            raise SmokeFailure("comprehensive search contains no AIDEFEND IDs")
    elif case.name == "analyze_security_posture":
        if _parse_markdown_count(text, "Techniques Analyzed") != len(controls):
            raise SmokeFailure("security posture did not analyze both controls")
    elif case.name == "compare_techniques":
        if _parse_markdown_count(text, "Techniques Compared") != len(controls):
            raise SmokeFailure("technique comparison did not compare both controls")
        for control_id in controls:
            if control_id not in text:
                raise SmokeFailure(f"technique comparison omitted {control_id}")
        if fixtures.boundary_control_id and (
            "Scope Boundary" not in text
            or fixtures.boundary_responsibility not in text
        ):
            raise SmokeFailure("technique comparison omitted schema 2.3 scopeBoundary data")
        if fixtures.source_available_control_id in controls:
            _assert_mcp_source_available_inventory(text, fixtures, case.name)
    elif case.name == "generate_incident_playbook":
        if "Incident Summary" not in text or "Action Items" not in text:
            raise SmokeFailure("incident playbook lacks its core sections")


def validate_rest_payload(
    case: SmokeCase,
    payload: Any,
    fixtures: DynamicFixtures,
    *,
    sync_skipped: bool,
) -> None:
    data = _as_mapping(payload, f"{case.name} REST payload")
    if data.get("error") or data.get("detail"):
        raise SmokeFailure(f"{case.name} returned an error payload: {data}")
    controls = fixtures.control_ids

    if case.name == "query_aidefend":
        chunks = _list_field(data, "context_chunks", case.name)
        if _positive_int(data.get("total_results"), f"{case.name}.total_results") != len(chunks):
            raise SmokeFailure("query total_results does not match context_chunks")
        _assert_id_list([chunk.get("source_id") for chunk in chunks], "query.context_chunks")
        for chunk in chunks:
            chunk = _as_mapping(chunk, "query context chunk")
            metadata = _dict_field(chunk, "metadata", "query context chunk")
            _assert_direct_tool_inventory(metadata, "query context chunk metadata")
    elif case.name == "get_aidefend_status":
        if data.get("status") != "online":
            raise SmokeFailure(f"REST status is not online: {data.get('status')!r}")
        sync_info = _dict_field(data, "sync_info", case.name)
        if sync_info.get("total_documents") != fixtures.row_count:
            raise SmokeFailure("REST status document count differs from the live table")
        required_metadata = (
            "framework_public_schema_version",
            "index_schema_version",
            "source_kind",
            "source_revision_kind",
            "source_revision",
            "source_repository",
            "source_ref",
            "source_content_sha256",
            "framework_migrations_schema_version",
            "framework_migrations_registry_version",
            "framework_migrations_sha256",
        )
        missing = [key for key in required_metadata if key not in sync_info]
        if missing:
            raise SmokeFailure(f"REST status schema is missing version provenance: {missing}")
        for schema_field in (
            "framework_public_schema_version",
            "index_schema_version",
            "framework_migrations_schema_version",
        ):
            schema_value = sync_info.get(schema_field)
            if not isinstance(schema_value, str) or schema_value.casefold() in {
                "",
                "n/a",
                "none",
                "unknown",
                "unavailable",
            }:
                raise SmokeFailure(
                    f"REST status did not report a verified {schema_field} value"
                )
        digest = sync_info.get("source_content_sha256")
        if digest is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", str(digest)):
            raise SmokeFailure("REST status source_content_sha256 is not a SHA-256 digest")
        migrations_digest = sync_info.get("framework_migrations_sha256")
        if migrations_digest is not None and not re.fullmatch(
            r"[0-9a-fA-F]{64}", str(migrations_digest)
        ):
            raise SmokeFailure(
                "REST status framework_migrations_sha256 is not a SHA-256 digest"
            )
    elif case.name == "sync_aidefend":
        if data.get("status") != "sync_triggered":
            raise SmokeFailure("REST sync route did not return sync_triggered")
        if sync_skipped and "background" not in str(data.get("message", "")).lower():
            raise SmokeFailure("offline-safe sync did not traverse the real REST route")
    elif case.name == "get_statistics":
        overview = _dict_field(data, "overview", case.name)
        if overview.get("total_documents") != fixtures.row_count:
            raise SmokeFailure("REST statistics document count differs from the live table")
        type_total = sum(
            _nonnegative_int(overview.get(key), f"statistics.overview.{key}")
            for key in ("total_techniques", "total_subtechniques", "total_strategies")
        )
        if type_total != fixtures.row_count:
            raise SmokeFailure("statistics type counts do not sum to total_documents")
        for key in ("by_tactic", "by_pillar", "by_phase", "threat_framework_coverage"):
            if not _dict_field(data, key, case.name):
                raise SmokeFailure(f"statistics.{key} must not be empty")
    elif case.name == "validate_technique_id":
        if data.get("valid") is not True:
            raise SmokeFailure("REST validation rejected the selected live control")
        technique = _dict_field(data, "technique", case.name)
        if technique.get("id") != controls[0]:
            raise SmokeFailure("REST validation returned the wrong control")
        for key in ("pillar", "phase"):
            if not isinstance(technique.get(key), list):
                raise SmokeFailure(f"validated technique {key} must be an array")
        _assert_direct_tool_inventory(technique, case.name)
        if controls[0] == fixtures.source_available_control_id:
            _assert_exact_source_available_tools(technique, fixtures, case.name)
        elif not fixtures.source_available_control_id and technique["tools_source_available"]:
            raise SmokeFailure(
                "REST validation returned source-available tools although the live "
                "corpus capability probe found none"
            )
        if controls[0] == fixtures.boundary_control_id:
            scope_boundary = _dict_field(technique, "scope_boundary", case.name)
            if scope_boundary.get("responsibility") != fixtures.boundary_responsibility:
                raise SmokeFailure("REST validation changed scopeBoundary responsibility")
        elif not fixtures.boundary_control_id and _dict_field(
            technique, "scope_boundary", case.name
        ):
            raise SmokeFailure(
                "REST validation returned scopeBoundary data although the live corpus "
                "capability probe found none"
            )
    elif case.name == "get_technique_detail":
        technique = _dict_field(data, "technique", case.name)
        if technique.get("id") != controls[0]:
            raise SmokeFailure("technique detail returned the wrong control")
        for key in ("pillar", "phase", "warnings"):
            if not isinstance(technique.get(key), list):
                raise SmokeFailure(f"technique detail {key} must be an array")
        tools = _dict_field(technique, "tools", case.name)
        for key in ("opensource", "source_available", "commercial"):
            values = _list_field(tools, key, f"{case.name}.tools")
            if not all(isinstance(value, str) for value in values):
                raise SmokeFailure(
                    f"{case.name}.tools.{key} must contain only strings"
                )
        if (
            controls[0] == fixtures.source_available_control_id
            and tuple(tools["source_available"]) != fixtures.source_available_tools
        ):
            raise SmokeFailure(
                "REST technique detail changed exact source-available tool values or order"
            )
        if not fixtures.source_available_control_id and tools["source_available"]:
            raise SmokeFailure(
                "REST technique detail returned source-available tools although the "
                "live corpus capability probe found none"
            )
        if controls[0] == fixtures.boundary_control_id:
            scope_boundary = _dict_field(technique, "scope_boundary", case.name)
            if scope_boundary.get("responsibility") != fixtures.boundary_responsibility:
                raise SmokeFailure("REST technique detail changed scopeBoundary responsibility")
            related = _list_field(scope_boundary, "relatedTechniques", case.name)
            related_ids = {
                str(_as_mapping(item, "scopeBoundary relationship").get("id") or "").upper()
                for item in related
            }
            if not set(fixtures.boundary_related_ids).issubset(related_ids):
                raise SmokeFailure("REST technique detail omitted scopeBoundary relationships")
        elif not fixtures.boundary_control_id and _dict_field(
            technique, "scope_boundary", case.name
        ):
            raise SmokeFailure(
                "REST technique detail returned scopeBoundary data although the live "
                "corpus capability probe found none"
            )
        _list_field(data, "subtechniques", case.name)
        _list_field(data, "strategies", case.name)
        _dict_field(data, "metadata", case.name)
    elif case.name == "get_defenses_for_threat":
        defenses = _list_field(data, "defense_techniques", case.name)
        result_count = _nonnegative_int(
            data.get("total_results"), "defenses.total_results"
        )
        if result_count != len(defenses):
            raise SmokeFailure("defense result count does not match its array")
        defense_techniques = [
            _dict_field(_as_mapping(item, "defense"), "technique", "defense")
            for item in defenses
        ]
        if fixtures.threat_id:
            if result_count == 0:
                raise SmokeFailure("get_defenses_for_threat returned no defenses")
            _assert_id_list(
                [technique.get("id") for technique in defense_techniques],
                "defense_techniques",
            )
        elif result_count != 0 or defenses:
            raise SmokeFailure(
                "REST defenses did not return a successful empty result for the "
                "unmapped capability probe"
            )
        for technique in defense_techniques:
            _assert_direct_tool_inventory(technique, "defense.technique")
    elif case.name == "get_secure_code_snippet":
        snippets = _list_field(data, "code_snippets", case.name)
        snippet_count = _nonnegative_int(
            data.get("total_snippets"), "code.total_snippets"
        )
        if snippet_count != len(snippets):
            raise SmokeFailure("code snippet count does not match its array")
        if fixtures.code_control_id and snippet_count == 0:
            raise SmokeFailure("get_secure_code_snippet returned no code")
        if not fixtures.code_control_id and (snippet_count != 0 or snippets):
            raise SmokeFailure(
                "REST code snippets did not return a successful empty result when "
                "the live corpus has no code-bearing guidance"
            )
        for snippet in snippets:
            snippet = _as_mapping(snippet, "code snippet")
            _assert_direct_tool_inventory(snippet, "code snippet")
            _assert_control_id(snippet.get("technique_id"), "code snippet technique_id")
            if not str(snippet.get("code") or "").strip():
                raise SmokeFailure("code snippet has empty code")
    elif case.name == "analyze_coverage":
        summary = _dict_field(data, "analysis_summary", case.name)
        if summary.get("techniques_implemented") != len(controls):
            raise SmokeFailure("coverage analysis did not recognize both controls")
        for key in ("critical_gaps", "recommendations"):
            _list_field(data, key, case.name)
        for key in ("coverage_by_tactic", "coverage_by_pillar", "coverage_by_phase"):
            _dict_field(data, key, case.name)
    elif case.name == "map_to_compliance_framework":
        mappings = _list_field(data, "mappings", case.name)
        if data.get("total_mapped") != len(controls) or len(mappings) != len(controls):
            raise SmokeFailure("compliance mapping did not map both controls")
        if {entry.get("technique_id") for entry in mappings} != set(controls):
            raise SmokeFailure("compliance mapping returned unexpected IDs")
    elif case.name == "get_quick_reference":
        total = _positive_int(data.get("total_items"), "quick_reference.total_items")
        categorized = sum(
            len(_list_field(data, key, case.name))
            for key in ("quick_wins", "must_haves", "nice_to_haves")
        )
        if total != categorized:
            raise SmokeFailure("quick-reference count does not match category arrays")
        for key in ("quick_wins", "must_haves", "nice_to_haves"):
            for item in _list_field(data, key, case.name):
                _assert_direct_tool_inventory(
                    _as_mapping(item, f"quick_reference.{key}"),
                    f"quick_reference.{key}",
                )
    elif case.name == "get_threat_coverage":
        if data.get("input_count") != len(controls) or data.get("valid_count") != len(controls):
            raise SmokeFailure("threat coverage did not validate both controls")
        if data.get("invalid_count") != 0 or data.get("invalid_techniques") != []:
            raise SmokeFailure("threat coverage unexpectedly rejected a live control")
        _assert_framework_arrays(data.get("covered"), "threat_coverage.covered")
        by_technique = _list_field(data, "by_technique", case.name)
        if len(by_technique) != len(controls):
            raise SmokeFailure("threat coverage by_technique count is inconsistent")
    elif case.name == "get_implementation_plan":
        recommendations = _list_field(data, "recommendations", case.name)
        if not recommendations or len(recommendations) > 5:
            raise SmokeFailure("implementation plan recommendation count is invalid")
        _assert_id_list([entry.get("technique_id") for entry in recommendations], "recommendations")
        for recommendation in recommendations:
            _assert_direct_tool_inventory(
                _as_mapping(recommendation, "implementation recommendation"),
                "implementation recommendation",
            )
        categories = _dict_field(data, "categories", case.name)
        for key in ("quick_wins", "high_priority", "standard"):
            if not isinstance(categories.get(key), list):
                raise SmokeFailure(f"implementation_plan.categories.{key} must be an array")
    elif case.name == "classify_threat":
        if not _list_field(data, "keywords_found", case.name):
            raise SmokeFailure("classifier found no threat keywords")
        normalized = _assert_framework_arrays(data.get("normalized_threats"), "normalized_threats")
        if not any(normalized.values()):
            raise SmokeFailure("classifier emitted no normalized threat IDs")
        mapping_status = _dict_field(data, "mapping_status", case.name)
        if mapping_status.get("all_emitted_claims_resolvable") is not True:
            raise SmokeFailure("classifier emitted unresolved threat claims")
    elif case.name == "comprehensive_search":
        results = _list_field(data, "results", case.name)
        if not results or len(results) > 10:
            raise SmokeFailure("comprehensive search result count is invalid")
        _assert_id_list([item.get("source_id") for item in results], "comprehensive results")
        for item in results:
            _assert_direct_tool_inventory(
                _as_mapping(item, "comprehensive result"),
                "comprehensive result",
            )
        if not _list_field(data, "queries_executed", case.name):
            raise SmokeFailure("comprehensive search executed no queries")
        _dict_field(data, "coverage_summary", case.name)
    elif case.name == "analyze_security_posture":
        if data.get("implemented_count") != len(controls) or data.get("view") != "both":
            raise SmokeFailure("security posture input summary is inconsistent")
        _dict_field(data, "technical_coverage", case.name)
        _dict_field(data, "threat_coverage", case.name)
        _dict_field(data, "summary", case.name)
    elif case.name == "compare_techniques":
        matrix = _list_field(data, "comparison_matrix", case.name)
        summary = _dict_field(data, "summary", case.name)
        if summary.get("techniques_compared") != len(controls) or len(matrix) != len(controls):
            raise SmokeFailure("technique comparison count is inconsistent")
        if summary.get("techniques_not_found") != []:
            raise SmokeFailure("technique comparison failed to resolve a live control")
        if {item.get("source_id") for item in matrix} != set(controls):
            raise SmokeFailure("technique comparison returned unexpected IDs")
        for item in matrix:
            _assert_direct_tool_inventory(
                _as_mapping(item, "comparison matrix item"),
                "comparison matrix item",
            )
            if not fixtures.source_available_control_id and item["tools_source_available"]:
                raise SmokeFailure(
                    "REST comparison returned source-available tools although the live "
                    "corpus capability probe found none"
                )
        if fixtures.boundary_control_id:
            boundary_item = next(
                item for item in matrix
                if item.get("source_id") == fixtures.boundary_control_id
            )
            scope_boundary = _dict_field(
                boundary_item, "scope_boundary", "compare_techniques"
            )
            if scope_boundary.get("responsibility") != fixtures.boundary_responsibility:
                raise SmokeFailure("REST comparison changed scopeBoundary responsibility")
        if fixtures.source_available_control_id:
            source_available_item = next(
                item for item in matrix
                if item.get("source_id") == fixtures.source_available_control_id
            )
            _assert_exact_source_available_tools(
                source_available_item, fixtures, "comparison source-available item"
            )
        if not fixtures.boundary_control_id:
            for item in matrix:
                if _dict_field(item, "scope_boundary", "comparison matrix item"):
                    raise SmokeFailure(
                        "REST comparison returned scopeBoundary data although the live "
                        "corpus capability probe found none"
                    )
    elif case.name == "generate_incident_playbook":
        summary = _dict_field(data, "incident_summary", case.name)
        _positive_int(summary.get("total_action_items"), "playbook.total_action_items")
        timeline = _dict_field(data, "timeline", case.name)
        if set(timeline) != {"immediate", "investigation", "containment", "recovery"}:
            raise SmokeFailure("incident playbook timeline phases are incomplete")
        for phase, phase_data in timeline.items():
            _list_field(
                _as_mapping(phase_data, f"timeline.{phase}"), "actions", f"timeline.{phase}"
            )
        defenses = _dict_field(data, "defense_techniques", case.name)
        playbook_defenses = _list_field(
            defenses, "defense_techniques", "playbook defenses"
        )
        if not playbook_defenses:
            raise SmokeFailure("incident playbook returned no defense techniques")
        for item in playbook_defenses:
            technique = _dict_field(
                _as_mapping(item, "playbook defense"),
                "technique",
                "playbook defense",
            )
            _assert_direct_tool_inventory(technique, "playbook defense technique")


def configure_environment(data_path: Path) -> dict[str, str]:
    """Pin both transports to one existing database and offline-safe defaults."""
    resolved = data_path.resolve()
    overrides = {
        "DATA_PATH": str(resolved),
        "DB_PATH": str(resolved / "aidefend_kb.lancedb"),
        "RAW_PATH": str(resolved / "raw_content"),
        "VERSION_FILE": str(resolved / "local_version.json"),
        "LOG_PATH": str(resolved / "logs" / "aidefend_mcp.log"),
        "AUTH_MODE": "no_auth",
        "API_HOST": "127.0.0.1",
        "ENABLE_AUTO_SYNC": "false",
        "ENABLE_RATE_LIMITING": "false",
        "ENABLE_FILE_LOGGING": "false",
        "PYTHONUNBUFFERED": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    os.environ.update(overrides)
    return overrides


def load_live_records(data_path: Path) -> list[dict[str, Any]]:
    """Fail closed unless DATA_PATH already contains a readable, nonempty table."""
    from app.config import settings
    import lancedb

    expected_db = (data_path / "aidefend_kb.lancedb").resolve()
    if settings.DB_PATH.resolve() != expected_db:
        raise SmokeFailure(f"Settings resolved DB_PATH={settings.DB_PATH}, expected {expected_db}")
    if not expected_db.is_dir():
        raise SmokeFailure(
            f"Existing LanceDB not found at {expected_db}. Build it before running smoke tests."
        )
    if not settings.VERSION_FILE.is_file():
        raise SmokeFailure(f"Version metadata not found at {settings.VERSION_FILE}")

    database = lancedb.connect(str(expected_db))
    table_names = database.table_names()
    if "aidefend" not in table_names:
        raise SmokeFailure(f"LanceDB has no 'aidefend' table (found: {table_names})")
    table = database.open_table("aidefend")
    row_count = table.count_rows()
    if row_count <= 0:
        raise SmokeFailure("The 'aidefend' table is empty")
    records = table.to_pandas().drop(columns=["vector"], errors="ignore").to_dict("records")
    if len(records) != row_count:
        raise SmokeFailure(f"Full table scan returned {len(records)} records, expected {row_count}")
    return records


async def run_mcp_smoke(
    cases: Sequence[SmokeCase],
    fixtures: DynamicFixtures,
    environment: Mapping[str, str],
    *,
    timeout_seconds: float,
    skip_sync: bool,
) -> None:
    """Launch the real server over stdio and invoke all 18 registered tools."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    child_env = os.environ.copy()
    child_env.update(environment)
    child_env["AIDEFEND_SMOKE_SKIP_SYNC"] = "1" if skip_sync else "0"
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).resolve()), "--mcp-child"],
        env=child_env,
        cwd=REPOSITORY_ROOT,
        encoding="utf-8",
        encoding_error_handler="replace",
    )
    timeout = timedelta(seconds=timeout_seconds)

    print("\n[MCP] launching real stdio server", flush=True)
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timeout,
        ) as session:
            await session.initialize()
            listed = await session.list_tools()
            listed_names = [tool.name for tool in listed.tools]
            if len(listed_names) != 18 or set(listed_names) != set(EXPECTED_TOOL_NAMES):
                missing = sorted(set(EXPECTED_TOOL_NAMES) - set(listed_names))
                extra = sorted(set(listed_names) - set(EXPECTED_TOOL_NAMES))
                raise SmokeFailure(
                    "MCP list_tools contract mismatch: "
                    f"count={len(listed_names)}, missing={missing}, extra={extra}"
                )
            print("[MCP] list_tools: exactly 18 expected tools", flush=True)

            listed_by_name = {tool.name: tool for tool in listed.tools}
            for tool_name, parameter_name in INTEGER_TOOL_PARAMETERS.items():
                schema = listed_by_name[tool_name].inputSchema
                parameter_schema = schema.get("properties", {}).get(parameter_name, {})
                if parameter_schema.get("type") != "integer":
                    raise SmokeFailure(
                        f"{tool_name}.{parameter_name} must advertise JSON integer"
                    )
            for tool_name, alternatives in {
                "get_defenses_for_threat": {"threat_id", "threat_keyword"},
                "get_secure_code_snippet": {"technique_id", "topic"},
            }.items():
                schema = listed_by_name[tool_name].inputSchema
                required_alternatives = {
                    required
                    for branch in schema.get("anyOf", [])
                    for required in branch.get("required", [])
                }
                if required_alternatives != alternatives:
                    raise SmokeFailure(
                        f"{tool_name} must advertise one of {sorted(alternatives)}"
                    )
            print("[MCP] input schemas: integer and alternative-field contracts ok", flush=True)

            for index, case in enumerate(cases, 1):
                result = await session.call_tool(
                    case.name,
                    dict(case.mcp_arguments),
                    read_timeout_seconds=timeout,
                )
                if bool(result.isError):
                    raise SmokeFailure(f"{case.name} MCP result has isError=true: {result}")
                text_blocks = [
                    str(block.text)
                    for block in result.content
                    if getattr(block, "type", None) == "text"
                    and getattr(block, "text", None) is not None
                ]
                if not text_blocks:
                    raise SmokeFailure(f"{case.name} MCP result contains no text content")
                combined = "\n".join(text_blocks)
                validate_mcp_text(case, combined, fixtures, sync_skipped=skip_sync)
                print(f"[MCP] {index:02d}/18 {case.name}: ok", flush=True)

            # Exercise each numeric contract with a JSON number that is not an
            # integer, plus both alternative-input requirements. MCP clients
            # must receive protocol errors rather than successful error text.
            invalid_calls = [
                ("query_aidefend", {"query": fixtures.topic, "top_k": 1.5}),
                (
                    "get_defenses_for_threat",
                    {
                        "threat_id": fixtures.threat_id or UNMAPPED_THREAT_ID,
                        "top_k": 1.5,
                    },
                ),
                (
                    "get_secure_code_snippet",
                    {
                        "technique_id": fixtures.code_control_id
                        or fixtures.control_ids[0],
                        "max_snippets": 1.5,
                    },
                ),
                (
                    "get_quick_reference",
                    {"topic": "prompt injection defense", "max_items": 5.5},
                ),
                (
                    "get_implementation_plan",
                    {"implemented_techniques": [], "top_k": 1.5},
                ),
                ("classify_threat", {"text": "prompt injection", "top_k": 1.5}),
                (
                    "comprehensive_search",
                    {"topic": "prompt injection defense", "max_results": 5.5},
                ),
                ("get_defenses_for_threat", {}),
                ("get_secure_code_snippet", {}),
            ]
            for tool_name, arguments in invalid_calls:
                invalid_result = await session.call_tool(
                    tool_name,
                    arguments,
                    read_timeout_seconds=timeout,
                )
                if not bool(invalid_result.isError):
                    raise SmokeFailure(
                        f"{tool_name} validation failure returned isError=false"
                    )
            print(
                f"[MCP] negative-path protocol errors: {len(invalid_calls)}/"
                f"{len(invalid_calls)} ok",
                flush=True,
            )


async def run_rest_smoke(
    cases: Sequence[SmokeCase],
    fixtures: DynamicFixtures,
    *,
    timeout_seconds: float,
    skip_sync: bool,
) -> None:
    """Run the real FastAPI lifespan and all 18 routes through ASGITransport."""
    import httpx
    import app.main as main_module

    sync_called = asyncio.Event()

    async def offline_sync_noop() -> bool:
        sync_called.set()
        return True

    original_run_sync = main_module.run_sync
    if skip_sync:
        main_module.run_sync = offline_sync_noop

    actual_routes = openapi_route_inventory(main_module.app)
    expected_tool_routes = {(case.method, case.route_path) for case in cases}
    actual_tool_routes = {
        route
        for route in actual_routes
        if route[1].startswith("/api/v1/")
    }
    if actual_tool_routes != expected_tool_routes:
        missing_routes = sorted(expected_tool_routes - actual_tool_routes)
        untested_routes = sorted(actual_tool_routes - expected_tool_routes)
        raise SmokeFailure(
            "FastAPI tool-route inventory differs from the 18-tool contract: "
            f"missing={missing_routes}, untested={untested_routes}"
        )

    transport = httpx.ASGITransport(app=main_module.app, raise_app_exceptions=False)
    try:
        print("\n[REST] entering real FastAPI lifespan", flush=True)
        async with main_module.app.router.lifespan_context(main_module.app):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://smoke.local",
                timeout=timeout_seconds,
            ) as client:
                health = await client.get("/health")
                if health.status_code != 200:
                    raise SmokeFailure(
                        f"REST readiness failed ({health.status_code}): {health.text[:600]}"
                    )
                health_payload = health.json()
                checks = _dict_field(_as_mapping(health_payload, "health"), "checks", "health")
                if checks.get("database") is not True or checks.get("embedding_model") is not True:
                    raise SmokeFailure(f"REST readiness dependencies are false: {checks}")
                print("[REST] /health: database and embedding model ready", flush=True)

                for index, case in enumerate(cases, 1):
                    request_kwargs: dict[str, Any] = {}
                    if case.rest_params is not None:
                        request_kwargs["params"] = dict(case.rest_params)
                    if case.rest_json is not None:
                        request_kwargs["json"] = case.rest_json
                    response = await client.request(case.method, case.path, **request_kwargs)
                    if not 200 <= response.status_code < 300:
                        raise SmokeFailure(
                            f"{case.name} REST {case.method} {case.path} returned "
                            f"HTTP {response.status_code}: {response.text[:1000]}"
                        )
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise SmokeFailure(
                            f"{case.name} REST response is not JSON: {response.text[:600]}"
                        ) from exc
                    validate_rest_payload(case, payload, fixtures, sync_skipped=skip_sync)
                    if case.name == "sync_aidefend" and skip_sync:
                        try:
                            await asyncio.wait_for(sync_called.wait(), timeout=2.0)
                        except TimeoutError as exc:
                            raise SmokeFailure(
                                "REST sync route never invoked the no-op sync task"
                            ) from exc
                    print(f"[REST] {index:02d}/18 {case.name}: ok", flush=True)

                negative_specs = [
                    (
                        "unknown technique",
                        "GET",
                        f"/api/v1/technique/{fixtures.missing_control_id}",
                        {},
                        404,
                    ),
                    (
                        "query fractional top_k",
                        "POST",
                        "/api/v1/query",
                        {"json": {"query_text": fixtures.topic, "top_k": 1.5}},
                        422,
                    ),
                    (
                        "defenses fractional top_k",
                        "POST",
                        "/api/v1/defenses-for-threat",
                        {
                            "params": {
                                "threat_id": fixtures.threat_id
                                or UNMAPPED_THREAT_ID,
                                "top_k": 1.5,
                            }
                        },
                        422,
                    ),
                    (
                        "code fractional max_snippets",
                        "POST",
                        "/api/v1/code-snippets",
                        {
                            "params": {
                                "technique_id": fixtures.code_control_id
                                or fixtures.control_ids[0],
                                "max_snippets": 1.5,
                            }
                        },
                        422,
                    ),
                    (
                        "quick reference fractional max_items",
                        "POST",
                        "/api/v1/quick-reference",
                        {"params": {"topic": "prompt injection", "max_items": 1.5}},
                        422,
                    ),
                    (
                        "implementation plan fractional top_k",
                        "POST",
                        "/api/v1/implementation-plan",
                        {
                            "json": {
                                "implemented_techniques": list(fixtures.control_ids),
                                "top_k": 1.5,
                            }
                        },
                        422,
                    ),
                    (
                        "classification fractional top_k",
                        "POST",
                        "/api/v1/classify-threat",
                        {"json": {"text": "prompt injection", "top_k": 1.5}},
                        422,
                    ),
                    (
                        "comprehensive fractional max_results",
                        "POST",
                        "/api/v1/comprehensive-search",
                        {"params": {"topic": "prompt injection", "max_results": 1.5}},
                        422,
                    ),
                    (
                        "defenses missing alternatives",
                        "POST",
                        "/api/v1/defenses-for-threat",
                        {},
                        400,
                    ),
                    (
                        "code snippets missing alternatives",
                        "POST",
                        "/api/v1/code-snippets",
                        {},
                        400,
                    ),
                ]
                for label, method, path, request_kwargs, expected_status in negative_specs:
                    response = await client.request(method, path, **request_kwargs)
                    if response.status_code != expected_status:
                        raise SmokeFailure(
                            f"REST negative path {label!r} returned "
                            f"{response.status_code}, expected {expected_status}: "
                            f"{response.text[:600]}"
                        )
                print(
                    f"[REST] negative-path protocol errors: "
                    f"{len(negative_specs)}/{len(negative_specs)}",
                    flush=True,
                )
    finally:
        main_module.run_sync = original_run_sync


async def _run_mcp_child() -> None:
    """Internal stdio child entrypoint used by the parent smoke process."""
    import mcp_server

    if os.environ.get("AIDEFEND_SMOKE_SKIP_SYNC", "1") == "1":

        async def offline_sync_noop() -> bool:
            return True

        mcp_server.run_sync = offline_sync_noop
    await mcp_server.serve()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Call all 18 AIDEFEND tools over real MCP stdio and FastAPI routing."
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=Path(os.environ.get("DATA_PATH", REPOSITORY_ROOT / "data")),
        help="Existing AIDEFEND data directory (default: DATA_PATH or repository data/)",
    )
    parser.add_argument(
        "--transport",
        choices=("both", "mcp", "rest"),
        default="both",
        help="Transport(s) to exercise; default runs MCP first, then REST",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Per-operation timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--allow-sync",
        action="store_true",
        help="Run the real manual sync tool (may access network/rebuild); default is a no-op",
    )
    return parser.parse_args(argv)


async def async_main(args: argparse.Namespace) -> None:
    data_path = args.data_path.resolve()
    environment = configure_environment(data_path)
    records = load_live_records(data_path)
    fixtures = select_dynamic_fixtures(records)
    cases = build_smoke_cases(fixtures)
    skip_sync = not args.allow_sync

    print("AIDEFEND 18-tool transport smoke", flush=True)
    print(f"DATA_PATH: {data_path}", flush=True)
    print(f"Rows: {fixtures.row_count}", flush=True)
    print(f"Controls: {', '.join(fixtures.control_ids)}", flush=True)
    print(f"Mapped threat: {fixtures.threat_id or 'none'}", flush=True)
    print(f"Code control: {fixtures.code_control_id or 'none'}", flush=True)
    print(
        f"Scope-boundary control: {fixtures.boundary_control_id or 'none'}",
        flush=True,
    )
    print(
        f"Source-available control: {fixtures.source_available_control_id or 'none'}",
        flush=True,
    )
    print(
        "Source-available tools: " + ", ".join(fixtures.source_available_tools),
        flush=True,
    )
    print(f"Manual sync: {'real' if not skip_sync else 'offline-safe no-op'}", flush=True)

    if args.transport in {"both", "mcp"}:
        await run_mcp_smoke(
            cases,
            fixtures,
            environment,
            timeout_seconds=args.timeout,
            skip_sync=skip_sync,
        )
    if args.transport in {"both", "rest"}:
        await run_rest_smoke(
            cases,
            fixtures,
            timeout_seconds=args.timeout,
            skip_sync=skip_sync,
        )

    transports = "MCP + REST" if args.transport == "both" else args.transport.upper()
    print(f"\nPASS: all 18 AIDEFEND tools passed over {transports}", flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.timeout <= 0:
        print("ERROR: --timeout must be greater than zero", file=sys.stderr)
        return 2
    try:
        asyncio.run(async_main(args))
    except SmokeFailure as exc:
        print(f"\nSMOKE FAILED: {exc}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        print("\nSmoke interrupted", file=sys.stderr, flush=True)
        return 130
    return 0


if __name__ == "__main__":
    if "--mcp-child" in sys.argv:
        asyncio.run(_run_mcp_child())
    else:
        raise SystemExit(main())
