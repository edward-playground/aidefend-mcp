"""Atomic 2025/2026 label behavior for runtime analytics surfaces."""

from __future__ import annotations

from copy import deepcopy
import json

import pytest

import app.core as core_module
import app.tools.security_posture as posture_module
import app.tools.statistics as statistics_module
import app.utils as utils_module
from app.framework_utils import framework_labels_from_registry
from tests.framework_migration_fixtures import owasp_llm_2026_registry


class FakeQueryEngine:
    is_ready = True
    active_embedding_model = "test-embedding"

    def __init__(self, records=None, version_info=None):
        self.records = records or []
        self.version_info = version_info

    async def read_table(self, _operation):
        return [dict(record) for record in self.records]

    async def read_table_snapshot(self, _operation):
        from app.utils import load_version_info

        version_info = (
            self.version_info
            if self.version_info is not None
            else load_version_info()
        )
        return [dict(record) for record in self.records], version_info


def _precomputed_statistics(label: str):
    return {
        "overview": {},
        "threat_framework_coverage": {
            "by_framework": {
                "owasp_llm": {
                    "label": label,
                    "items_covered": 1,
                    "total_items": 10,
                }
            }
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "registry, expected_label",
    [
        (None, "OWASP LLM Top 10 2025"),
        (owasp_llm_2026_registry(), "OWASP LLM Top 10 2026"),
    ],
)
async def test_statistics_fast_path_relabels_from_same_atomic_version_without_mutation(
    monkeypatch, registry, expected_label
):
    stored_statistics = _precomputed_statistics("stale label")
    version_info = {"statistics": stored_statistics}
    if registry is not None:
        version_info["framework_migrations"] = registry
    monkeypatch.setattr(utils_module, "load_version_info", lambda: version_info)
    monkeypatch.setattr(core_module, "query_engine", FakeQueryEngine())

    result = await statistics_module.get_statistics()
    assert result["threat_framework_coverage"]["by_framework"]["owasp_llm"][
        "label"
    ] == expected_label
    assert stored_statistics["threat_framework_coverage"]["by_framework"][
        "owasp_llm"
    ]["label"] == "stale label"


def _raw_actionable_record(label: str, item: str):
    return {
        "source_id": "AID-H-001.001",
        "name": "Test defense",
        "type": "subtechnique",
        "tactic": "Harden",
        "text": "Test defense",
        "pillar": '["app"]',
        "phase": '["operation"]',
        "defends_against": json.dumps(
            [{"framework": label, "items": [item]}]
        ),
        "tools_opensource": "[]",
        "tools_source_available": "[]",
        "tools_commercial": "[]",
        "implementation_guidance": "[]",
        "warnings": "[]",
        "scope_boundary": "{}",
        "parent_technique_id": "AID-H-001",
        "guidance_id": "",
        "is_actionable": True,
        "is_parent_family": False,
        "has_code_snippets": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "registry, source_label, item, expected_label",
    [
        (
            None,
            "OWASP LLM Top 10 2025",
            "LLM01:2025 Prompt Injection",
            "OWASP LLM Top 10 2025",
        ),
        (
            owasp_llm_2026_registry(),
            "OWASP LLM Top 10 2026",
            "LLM01:2026 Prompt Injection",
            "OWASP LLM Top 10 2026",
        ),
    ],
)
async def test_statistics_slow_path_uses_pre_read_atomic_version_snapshot(
    monkeypatch, registry, source_label, item, expected_label
):
    version_info = {}
    if registry is not None:
        version_info["framework_migrations"] = registry
    monkeypatch.setattr(utils_module, "load_version_info", lambda: version_info)
    monkeypatch.setattr(
        core_module,
        "query_engine",
        FakeQueryEngine([_raw_actionable_record(source_label, item)]),
    )

    result = await statistics_module.get_statistics()
    assert result["threat_framework_coverage"]["by_framework"]["owasp_llm"][
        "label"
    ] == expected_label


def test_security_posture_summary_accepts_effective_label_map():
    technical = {
        "analysis_summary": {"coverage_percentage": 0},
        "critical_gaps": [],
        "recommendations": [],
    }
    threat = {"coverage_rate": {"owasp_llm": 0}, "covered": {}}
    legacy = posture_module._generate_unified_summary(technical, threat, 0)
    current = posture_module._generate_unified_summary(
        technical,
        threat,
        0,
        framework_labels=framework_labels_from_registry(
            owasp_llm_2026_registry()
        ),
    )
    assert any(
        "OWASP LLM Top 10 2025" in insight
        for insight in legacy["key_insights"]
    )
    assert any(
        "OWASP LLM Top 10 2026" in insight
        for insight in current["key_insights"]
    )


@pytest.mark.asyncio
async def test_security_posture_shares_one_atomic_snapshot_between_children(
    monkeypatch,
):
    events = []
    version_info = {"framework_migrations": owasp_llm_2026_registry()}
    shared_records = [_raw_actionable_record(
        "OWASP LLM Top 10 2026",
        "LLM01:2026 Prompt Injection",
    )]
    shared_snapshot = (shared_records, version_info)

    class PostureQueryEngine(FakeQueryEngine):
        async def read_table_snapshot(self, _operation):
            events.append("snapshot")
            return shared_snapshot

    async def technical_stub(
        *, implemented_techniques, system_type=None, _snapshot=None
    ):
        assert events == ["snapshot"]
        assert _snapshot is shared_snapshot
        events.append("technical")
        return {
            "analysis_summary": {
                "coverage_percentage": 0,
                "techniques_implemented": 0,
                "expanded_parent_families": {},
                "unrecognized_technique_ids": [],
            },
            "critical_gaps": [],
            "recommendations": [],
        }

    async def threat_stub(*, implemented_techniques, _snapshot=None):
        assert events == ["snapshot", "technical"]
        assert _snapshot is shared_snapshot
        events.append("threat")
        return {
            "invalid_techniques": [],
            "resolved_actionable_count": 0,
            "expanded_parent_families": {},
            "coverage_rate": {"owasp_llm": 0},
            "covered": {},
        }

    monkeypatch.setattr(core_module, "query_engine", PostureQueryEngine())
    monkeypatch.setattr(posture_module, "analyze_coverage", technical_stub)
    monkeypatch.setattr(posture_module, "get_threat_coverage", threat_stub)

    result = await posture_module.analyze_security_posture([], view="both")
    assert events == ["snapshot", "technical", "threat"]
    assert any(
        "OWASP LLM Top 10 2026" in insight
        for insight in result["summary"]["key_insights"]
    )
