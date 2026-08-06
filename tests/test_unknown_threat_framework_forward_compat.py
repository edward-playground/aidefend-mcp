"""Forward-compatibility tests for additive threat frameworks."""

import pytest

import app.core as core_module
from app.framework_utils import (
    FRAMEWORK_LABELS,
    UNKNOWN_FRAMEWORK_KEY_PREFIX,
    build_framework_metrics,
    coverage_lists_from_sets,
    extract_framework_coverage,
    framework_coverage_key,
    merge_framework_coverage_sets,
    normalize_framework_item,
    public_framework_coverage_mapping,
)
from app.tools.defenses_for_threat import _threat_id_matches
from app.tools.threat_coverage import get_threat_coverage


FUTURE_FRAMEWORK = "Future AI Threat Framework"
FUTURE_FRAMEWORK_KEY = framework_coverage_key(FUTURE_FRAMEWORK)


def test_unknown_framework_coverage_key_preserves_raw_label():
    assert FUTURE_FRAMEWORK_KEY == f"{UNKNOWN_FRAMEWORK_KEY_PREFIX}{FUTURE_FRAMEWORK}"


def test_public_framework_mapping_retains_prefix_only_for_key_collisions():
    public = public_framework_coverage_mapping(
        {
            "atlas": {"AML.T0001"},
            f"{UNKNOWN_FRAMEWORK_KEY_PREFIX}atlas": {"FUTURE-001"},
            FUTURE_FRAMEWORK_KEY: {"FUTURE-002"},
        }
    )

    assert public == {
        "atlas": {"AML.T0001"},
        f"{UNKNOWN_FRAMEWORK_KEY_PREFIX}atlas": {"FUTURE-001"},
        FUTURE_FRAMEWORK: {"FUTURE-002"},
    }


def test_unknown_framework_exact_prefix_is_normalized_and_matched():
    item = "FUTURE-001 New threat"

    assert normalize_framework_item(FUTURE_FRAMEWORK, item) == "FUTURE-001"
    assert _threat_id_matches("FUTURE-001", item, FUTURE_FRAMEWORK)
    assert _threat_id_matches(item, item, FUTURE_FRAMEWORK)
    assert not _threat_id_matches("FUTURE-002", item, FUTURE_FRAMEWORK)


def test_unknown_framework_survives_coverage_merge_and_metrics():
    covered = merge_framework_coverage_sets(
        extract_framework_coverage(
            [
                {
                    "framework": "OWASP LLM Top 10 2025",
                    "items": ["LLM01:2025 Prompt Injection"],
                },
                {
                    "framework": FUTURE_FRAMEWORK,
                    "items": ["FUTURE-001 New threat"],
                },
            ]
        )
    )
    available = merge_framework_coverage_sets(
        extract_framework_coverage(
            [
                {
                    "framework": FUTURE_FRAMEWORK,
                    "items": ["FUTURE-001 New threat", "FUTURE-002 Another threat"],
                },
            ]
        )
    )

    assert covered[FUTURE_FRAMEWORK_KEY] == {"FUTURE-001"}
    assert available[FUTURE_FRAMEWORK_KEY] == {"FUTURE-001", "FUTURE-002"}

    public_coverage = coverage_lists_from_sets(covered)
    metrics = build_framework_metrics(covered, available)

    assert public_coverage[FUTURE_FRAMEWORK] == ["FUTURE-001"]
    assert public_coverage["owasp_llm"] == ["LLM01"]
    assert metrics["by_framework"]["owasp_llm"] == {
        "label": FRAMEWORK_LABELS["owasp_llm"],
        "items_covered": 1,
        "total_items": 10,
        "coverage_percentage": 10.0,
        "coverage_scope": "authoritative_top_level_total",
    }
    assert metrics["by_framework"]["atlas"] == {
        "label": FRAMEWORK_LABELS["atlas"],
        "items_covered": 0,
        "total_items": None,
        "coverage_percentage": None,
        "coverage_scope": "mapped_items_count_only",
    }
    assert metrics["by_framework"][FUTURE_FRAMEWORK] == {
        "label": FUTURE_FRAMEWORK,
        "items_covered": 1,
        "total_items": None,
        "coverage_percentage": None,
        "coverage_scope": "mapped_items_count_only",
    }
    assert metrics["owasp_llm_items_covered"] == 1
    assert metrics["mitre_atlas_items_covered"] == 0


@pytest.mark.asyncio
async def test_unknown_framework_is_retained_in_threat_coverage_output(monkeypatch):
    class FakeQueryEngine:
        is_ready = True

        async def read_table(self, _operation):
            return [
                {
                    "source_id": "AID-H-999",
                    "name": "Future threat defense",
                    "type": "technique",
                    "tactic": "Harden",
                    "pillar": ["application"],
                    "phase": ["operation"],
                    "defends_against": [
                        {
                            "framework": FUTURE_FRAMEWORK,
                            "items": ["FUTURE-001 New threat"],
                        }
                    ],
                    "scope_boundary": {},
                    "is_actionable": True,
                    "is_parent_family": False,
                }
            ]

        async def read_table_snapshot(self, operation):
            return await self.read_table(operation), None

    monkeypatch.setattr(core_module, "query_engine", FakeQueryEngine())

    result = await get_threat_coverage(["AID-H-999"])

    assert result["covered"][FUTURE_FRAMEWORK] == ["FUTURE-001"]
    assert result["framework_totals"][FUTURE_FRAMEWORK] == 1
    assert result["coverage_rate"][FUTURE_FRAMEWORK] == 1.0
    assert result["by_technique"][0]["threats_covered"][FUTURE_FRAMEWORK] == ["FUTURE-001"]
