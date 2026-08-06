"""Regression tests for schema-2.3 IDs and threat-to-defense routing."""

from types import SimpleNamespace

import pytest

from app.framework_utils import MAESTRO_CANONICAL_THREATS
from app.threat_keywords import THREAT_KEYWORDS
from app.tools.classify_threat import classify_threat
from app.tools.defenses_for_threat import (
    _threat_id_matches,
    normalize_threat_id,
)
from app.tools.validation import TECHNIQUE_ID_PATTERN


def test_schema23_id_pattern_accepts_only_canonical_shapes():
    accepted = {
        "AID-C-001",
        "AID-DV-001",
        "AID-H-001",
        "AID-H-001.001",
        "AID-H-001-G001",
        "AID-H-001.001-G001",
    }
    rejected = {
        "AID-1-001",
        "AID--001",
        "aid-H-001",
        "AID-H-001.S1",
        "AID-H-001.001.001",
        "AID-H-001-G1",
    }

    assert all(TECHNIQUE_ID_PATTERN.fullmatch(value) for value in accepted)
    assert not any(TECHNIQUE_ID_PATTERN.fullmatch(value) for value in rejected)


def test_static_dictionary_contains_only_resolvable_claims():
    atlas_ids = set()
    maestro_ids = set()
    for threat_data in THREAT_KEYWORDS.values():
        atlas_ids.update(threat_data["frameworks"].get("atlas", []))
        maestro_ids.update(threat_data["frameworks"].get("maestro", []))

    assert "AML.T0002" not in atlas_ids
    assert "AML.T0028" not in atlas_ids
    assert "AML.T0024.002" in atlas_ids
    assert maestro_ids
    assert maestro_ids <= MAESTRO_CANONICAL_THREATS
    assert not any(
        value.startswith(("L1-", "L2-", "L3-", "L4-", "L5-", "L6-", "L7-", "Cross-"))
        for value in maestro_ids
    )


@pytest.mark.asyncio
async def test_classifier_emits_canonical_maestro_and_marks_unmapped_keyword():
    resolved = await classify_threat("compromised agent registry", top_k=1)
    assert resolved["normalized_threats"]["maestro"] == [
        "Compromised Agent Registry (L7)"
    ]
    assert resolved["threat_details"][0]["threat_id"] == (
        "MAESTRO-Compromised Agent Registry (L7)"
    )
    assert resolved["recommended_actions"][0]["args"]["threat_id"] == (
        "Compromised Agent Registry (L7)"
    )

    unmapped = await classify_threat("marketplace manipulation", top_k=1)
    assert all(not values for values in unmapped["normalized_threats"].values())
    assert unmapped["threat_details"] == []
    assert unmapped["mapping_status"]["unmapped_keywords"] == [
        "marketplace manipulation"
    ]


def test_exact_threat_matching_does_not_collapse_atlas_subtechniques():
    assert normalize_threat_id("L7-Compromised-Agent-Registry") == (
        "Compromised Agent Registry (L7)"
    )
    assert _threat_id_matches(
        "Compromised Agent Registry (L7)",
        "Compromised Agent Registry (L7) (registry poisoning)",
        "MAESTRO",
    )
    assert _threat_id_matches(
        "AML.T0051.001",
        "AML.T0051.001 LLM Prompt Injection: Indirect",
        "MITRE ATLAS",
    )
    assert not _threat_id_matches(
        "AML.T0051.001",
        "AML.T0051.000 LLM Prompt Injection: Direct",
        "MITRE ATLAS",
    )


@pytest.mark.asyncio
async def test_incident_playbook_merges_every_classified_threat(monkeypatch):
    import app.tools.incident_response as incident

    classification = {
        "source": "static_keyword",
        "keywords_found": [{"keyword": "prompt injection", "confidence": 0.98}],
        "threat_details": [
            {
                "threat_id": "OWASP-LLM01:2026",
                "threat_name": "Prompt Injection",
                "confidence": 0.98,
                "matched_keyword": "prompt injection",
            },
            {
                "threat_id": "ATLAS-AML.T0051",
                "threat_name": "Prompt Injection",
                "confidence": 0.98,
                "matched_keyword": "prompt injection",
            },
            {
                "threat_id": "MAESTRO-Compromised Agent Registry (L7)",
                "threat_name": "Compromised Agent Registry",
                "confidence": 0.85,
                "matched_keyword": "compromised agent registry",
            },
        ],
    }
    calls = []

    async def fake_classify(_text):
        return classification

    async def fake_defenses(*, threat_id=None, threat_keyword=None, top_k=10):
        calls.append((threat_id, threat_keyword))
        suffix = "001" if threat_id != "Compromised Agent Registry (L7)" else "002"
        return {
            "defense_techniques": [
                {
                    "technique": {
                        "id": f"AID-H-999.{suffix}",
                        "name": f"Defense {suffix}",
                        "description": "Test defense",
                    },
                    "relevance_score": 1.0,
                    "matched_threats": [threat_id],
                    "match_type": "exact_threat_id",
                }
            ],
            "total_results": 1,
        }

    monkeypatch.setattr(incident, "query_engine", SimpleNamespace(is_ready=True))
    monkeypatch.setattr(incident, "classify_threat", fake_classify)
    monkeypatch.setattr(incident, "get_defenses_for_threat", fake_defenses)

    result = await incident.generate_incident_playbook(
        "Prompt injection through a compromised agent registry"
    )

    assert [threat_id for threat_id, _ in calls] == [
        "LLM01:2026",
        "AML.T0051",
        "Compromised Agent Registry (L7)",
    ]
    assert all(keyword is None for _, keyword in calls)
    defenses = result["defense_techniques"]
    assert defenses["total_results"] == 2
    duplicate = next(
        entry
        for entry in defenses["defense_techniques"]
        if entry["technique"]["id"] == "AID-H-999.001"
    )
    assert duplicate["matched_classified_threat_ids"] == [
        "LLM01:2026",
        "AML.T0051",
    ]


@pytest.mark.asyncio
async def test_incident_playbook_uses_semantic_fallback_for_unmapped_keyword(
    monkeypatch,
):
    import app.tools.incident_response as incident

    calls = []

    async def fake_classify(_text):
        return {
            "source": "static_keyword",
            "keywords_found": [
                {"keyword": "marketplace manipulation", "confidence": 0.85}
            ],
            "threat_details": [],
        }

    async def fake_defenses(*, threat_id=None, threat_keyword=None, top_k=10):
        calls.append((threat_id, threat_keyword))
        return {"defense_techniques": [], "total_results": 0}

    monkeypatch.setattr(incident, "query_engine", SimpleNamespace(is_ready=True))
    monkeypatch.setattr(incident, "classify_threat", fake_classify)
    monkeypatch.setattr(incident, "get_defenses_for_threat", fake_defenses)

    result = await incident.generate_incident_playbook(
        "Marketplace manipulation affected the public agent catalog"
    )

    assert calls == [(None, "marketplace manipulation")]
    assert result["defense_techniques"]["search_method"] == "semantic_fallback"
