"""Function-level forward-compatibility checks for evolving taxonomy values."""

import importlib
from types import SimpleNamespace

import pytest

import app.core as core_module
from app.schemas import ImplementationPlanRequest
from app.tools.implementation_plan import (
    UNKNOWN_PHASE_SCORE,
    UNKNOWN_PILLAR_SCORE,
    _calculate_recommendation_score,
    get_implementation_plan,
)

comprehensive_search_module = importlib.import_module(
    "app.tools.comprehensive_search"
)


def _record(source_id: str, tactic: str, *, pillar=None, phase=None):
    return {
        "source_id": source_id,
        "name": source_id,
        "type": "technique",
        "tactic": tactic,
        "text": "Future-compatible control",
        "pillar": pillar or ["app"],
        "phase": phase or ["operation"],
        "defends_against": [],
        "tools_opensource": [],
        "tools_source_available": [],
        "tools_commercial": [],
        "implementation_guidance": [],
        "warnings": [],
        "scope_boundary": {},
        "parent_technique_id": "",
        "guidance_id": "",
        "is_actionable": True,
        "is_parent_family": False,
        "has_code_snippets": False,
    }


def test_rest_schema_preserves_future_tactic_spelling():
    request = ImplementationPlanRequest(
        exclude_tactics=["  AI Governance  ", "eBPF Defense"]
    )

    assert request.exclude_tactics == ["AI Governance", "eBPF Defense"]


@pytest.mark.asyncio
async def test_implementation_plan_excludes_future_tactic_case_insensitively(monkeypatch):
    records = [
        _record("AID-GOVERNANCE-001", "AI Governance"),
        _record("AID-D-001", "Detect"),
    ]

    class FakeQueryEngine:
        is_ready = True

        async def read_table(self, _operation):
            return records

    monkeypatch.setattr(core_module, "query_engine", FakeQueryEngine())

    result = await get_implementation_plan(
        exclude_tactics=["ai governance"],
        top_k=5,
        detail_level="basic",
    )

    assert result["input"]["exclude_tactics"] == ["ai governance"]
    assert [item["technique_id"] for item in result["recommendations"]] == [
        "AID-D-001"
    ]


def test_future_dimension_values_receive_neutral_nonzero_scores():
    _score, breakdown = _calculate_recommendation_score(
        _record(
            "AID-GOVERNANCE-001",
            "AI Governance",
            pillar=["future-pillar"],
            phase=["future-phase"],
        )
    )

    assert breakdown["phase_weight"] == UNKNOWN_PHASE_SCORE
    assert breakdown["pillar_weight"] == UNKNOWN_PILLAR_SCORE


@pytest.mark.asyncio
async def test_comprehensive_search_suggests_future_tactic_from_live_id_cache(monkeypatch):
    detected = _record("AID-D-001", "Detect")
    chunk = SimpleNamespace(
        source_id=detected["source_id"],
        tactic=detected["tactic"],
        text=detected["text"],
        score=0.1,
        metadata=detected,
    )

    class FakeQueryEngine:
        is_ready = True

        async def search_batch(self, requests):
            return [[chunk] for _request in requests]

        def get_id_cache(self):
            return [
                detected,
                _record("AID-GV-001", "AI Governance"),
            ]

    monkeypatch.setattr(comprehensive_search_module, "query_engine", FakeQueryEngine())

    result = await comprehensive_search_module.comprehensive_search(
        "prompt injection",
        max_results=5,
    )

    assert any(
        "AI Governance" in suggestion for suggestion in result["related_searches"]
    )
