"""Classifier claims must be checked against the synchronized framework."""

import importlib

import pytest

from app.threat_keywords import THREAT_KEYWORDS, canonicalize_classifier_frameworks
from app.tools.incident_response import _classified_threat_ids
from tests.framework_migration_fixtures import owasp_llm_2026_registry


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
            "framework_migrations": owasp_llm_2026_registry(),
            "statistics": {
                "threat_mappings": _mapping_for_keyword("prompt injection")
            }
        },
    )

    result = await classify_module.classify_threat("prompt injection", top_k=1)

    assert result["mapping_status"] | {
        "classifier_owasp_llm_edition": "2026",
        "classifier_owasp_llm_label": "OWASP LLM Top 10 2026",
        "active_index_owasp_llm_edition": "2026",
        "active_index_owasp_llm_label": "OWASP LLM Top 10 2026",
        "migration_registry_status": "active",
        "owasp_llm_catalog_aligned": True,
    } == result["mapping_status"]
    assert result["mapping_status"]["all_emitted_claims_resolvable"] is True
    assert result["mapping_status"]["corpus_mapping_available"] is True
    assert result["mapping_status"]["unresolved_claims"] == []
    assert result["mapping_status"]["unmapped_keywords"] == []
    assert result["threat_details"]
    assert all(detail["resolvable"] is True for detail in result["threat_details"])
    assert any(
        action["tool"] == "get_defenses_for_threat"
        for action in result["recommended_actions"]
    )


@pytest.mark.asyncio
async def test_versioned_llm_claim_co_resolves_against_bare_current_index_key(
    monkeypatch,
):
    """The public claim stays versioned even when the reverse index is bare."""
    monkeypatch.setattr(
        classify_module,
        "load_version_info",
        lambda: {
            "framework_migrations": owasp_llm_2026_registry(),
            "statistics": {
                "threat_mappings": {
                    "LLM01": ["AID-H-001.001"],
                }
            }
        },
    )

    result = await classify_module.classify_threat("prompt injection", top_k=1)

    assert result["normalized_threats"]["owasp"] == ["LLM01:2026"]
    owasp_detail = next(
        detail
        for detail in result["threat_details"]
        if detail["threat_id"] == "OWASP-LLM01:2026"
    )
    assert owasp_detail["resolvable"] is True
    assert {
        action["args"]["threat_id"]
        for action in result["recommended_actions"]
        if action["tool"] == "get_defenses_for_threat"
    } >= {"LLM01:2026"}


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
