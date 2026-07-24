"""Classifier claims must be checked against the synchronized framework."""

import importlib

import pytest

from app.threat_keywords import THREAT_KEYWORDS, canonicalize_classifier_frameworks
from app.tools.incident_response import _classified_threat_ids


classify_module = importlib.import_module("app.tools.classify_threat")


def _mapping_for_keyword(keyword: str) -> dict[str, list[str]]:
    frameworks = canonicalize_classifier_frameworks(
        THREAT_KEYWORDS[keyword]["frameworks"]
    )
    return {
        threat_id: ["AID-GOVERNANCE-001"]
        for threat_ids in frameworks.values()
        for threat_id in threat_ids
    }


@pytest.mark.asyncio
async def test_classifier_verifies_every_claim_against_current_index(monkeypatch):
    monkeypatch.setattr(
        classify_module,
        "load_version_info",
        lambda: {
            "statistics": {
                "threat_mappings": _mapping_for_keyword("prompt injection")
            }
        },
    )

    result = await classify_module.classify_threat("prompt injection", top_k=1)

    assert result["mapping_status"] == {
        "all_emitted_claims_resolvable": True,
        "corpus_mapping_available": True,
        "unresolved_claims": [],
        "unmapped_keywords": [],
    }
    assert result["threat_details"]
    assert all(detail["resolvable"] is True for detail in result["threat_details"])
    assert any(
        action["tool"] == "get_defenses_for_threat"
        for action in result["recommended_actions"]
    )


@pytest.mark.asyncio
async def test_removed_or_renamed_claims_are_reported_and_not_recommended(monkeypatch):
    monkeypatch.setattr(
        classify_module,
        "load_version_info",
        lambda: {
            "statistics": {
                "threat_mappings": {
                    "FUTURE-001": ["AID-GOVERNANCE-001"],
                }
            }
        },
    )

    result = await classify_module.classify_threat("prompt injection", top_k=1)

    status = result["mapping_status"]
    assert status["all_emitted_claims_resolvable"] is False
    assert status["corpus_mapping_available"] is True
    assert status["unresolved_claims"]
    assert all(detail["resolvable"] is False for detail in result["threat_details"])
    assert not any(
        action["tool"] == "get_defenses_for_threat"
        for action in result["recommended_actions"]
    )
    assert _classified_threat_ids(result) == []


@pytest.mark.asyncio
async def test_missing_index_mapping_metadata_never_claims_resolution(monkeypatch):
    monkeypatch.setattr(classify_module, "load_version_info", lambda: None)

    result = await classify_module.classify_threat("prompt injection", top_k=1)

    assert result["mapping_status"]["corpus_mapping_available"] is False
    assert result["mapping_status"]["all_emitted_claims_resolvable"] is False
    assert result["mapping_status"]["unresolved_claims"]
