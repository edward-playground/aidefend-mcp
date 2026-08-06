"""Semantic contract for OWASP LLM Top 10 2026 classifier claims."""

import re

from app.threat_keywords import THREAT_KEYWORDS
from app.tools.classify_threat import _match_threats
from app.tools.incident_response import (
    _generate_containment_actions,
    _generate_immediate_actions,
)


OWASP_LLM_2026_ID = re.compile(r"LLM(?:0[1-9]|10):2026")


def _llm_claims(keyword: str) -> list[str]:
    return [
        threat_id
        for threat_id in THREAT_KEYWORDS[keyword]["frameworks"].get("owasp", [])
        if threat_id.startswith("LLM")
    ]


def _classification(*threat_ids: str) -> dict:
    return {
        "normalized_threats": {"owasp": list(threat_ids)},
        "threat_details": [
            {
                "threat_id": f"OWASP-{threat_id}",
                "matched_keyword": "test fixture",
            }
            for threat_id in threat_ids
        ],
    }


def test_all_authored_llm_claims_are_exact_2026_identifiers():
    claims = [
        threat_id
        for threat_data in THREAT_KEYWORDS.values()
        for threat_id in threat_data["frameworks"].get("owasp", [])
        if threat_id.startswith("LLM")
    ]

    assert claims
    assert all(OWASP_LLM_2026_ID.fullmatch(threat_id) for threat_id in claims)
    assert set(claims) == {f"LLM{index:02d}:2026" for index in range(1, 11)}


def test_primary_2026_concepts_use_their_actual_risk_ids():
    expected = {
        "prompt injection": "LLM01:2026",
        "sensitive information disclosure": "LLM02:2026",
        "excessive agency": "LLM03:2026",
        "supply chain compromise": "LLM04:2026",
        "training data poisoning": "LLM05:2026",
        "unbounded consumption": "LLM06:2026",
        "misinformation": "LLM07:2026",
        "hidden context exposure": "LLM08:2026",
        "vector and embedding weaknesses": "LLM09:2026",
        "insecure output handling": "LLM10:2026",
    }

    for keyword, threat_id in expected.items():
        assert _llm_claims(keyword) == [threat_id]


def test_moved_risks_are_not_migrated_by_rank_substitution():
    assert _llm_claims("excessive agency") == ["LLM03:2026"]
    assert _llm_claims("supply chain compromise") == ["LLM04:2026"]
    assert _llm_claims("training data poisoning") == ["LLM05:2026"]
    assert _llm_claims("unbounded consumption") == ["LLM06:2026"]
    assert _llm_claims("misinformation") == ["LLM07:2026"]
    assert _llm_claims("system prompt leakage") == ["LLM08:2026"]
    assert _llm_claims("vector and embedding weaknesses") == ["LLM09:2026"]
    assert _llm_claims("insecure output handling") == ["LLM10:2026"]


def test_rag_terms_are_split_by_causal_mechanism():
    assert _llm_claims("rag poisoning") == ["LLM05:2026"]
    assert _llm_claims("rag indirect prompt injection") == ["LLM01:2026"]
    assert _llm_claims("geometric retrieval poisoning") == ["LLM09:2026"]
    assert _llm_claims("compromised rag pipelines") == []

    # An exact, mechanism-specific phrase must outrank broader alias matches.
    assert _match_threats("rag poisoning")[0]["keyword"] == "rag poisoning"


def test_generic_or_agent_specific_terms_do_not_claim_an_llm_risk():
    generic_terms = {
        "agent tool misuse",
        "insecure plugin",
        "overreliance",
        "integration risk",
        "compromised observability tools",
        "lateral movement in ai infra",
        "rag bypass",
        "context window attack",
        "multi-modal attacks",
        "api rate limit bypass",
        "session hijacking",
        "unsecured credentials",
        "ml model inference api access",
        "bias",
        "model serving",
        "container escape",
    }

    assert all(_llm_claims(keyword) == [] for keyword in generic_terms)


def test_consumption_routing_covers_2026_mechanisms_without_generic_dos_claims():
    assert _llm_claims("context window exhaustion") == ["LLM06:2026"]
    assert _llm_claims("agent tool consumption loop") == ["LLM06:2026"]
    assert _llm_claims("high-volume llm model extraction") == ["LLM06:2026"]
    assert _llm_claims("llm api quota exhaustion") == ["LLM06:2026"]
    assert _llm_claims("dos on data infrastructure") == []
    assert _llm_claims("denial of service on evaluation infrastructure") == []


def test_incident_actions_route_by_exact_2026_ids_not_keyword_fragments():
    no_claim = {
        "normalized_threats": {"owasp": []},
        "threat_details": [
            {
                "threat_id": "MAESTRO-L2 Data Poisoning",
                "matched_keyword": "training resource prompt injection",
            }
        ],
    }
    assert len(_generate_immediate_actions("fixture", no_claim)) == 3
    assert len(_generate_containment_actions("fixture", no_claim, None)) == 3

    expected_immediate = {
        "LLM01:2026": "Isolate Affected LLM Interaction Path",
        "LLM05:2026": "Freeze Mutable Learning Sources",
        "LLM06:2026": "Trip Consumption Circuit Breakers",
    }
    expected_containment = {
        "LLM01:2026": "Enforce Instruction and Data Boundaries",
        "LLM05:2026": "Quarantine and Rebuild Poisoned State",
        "LLM06:2026": "Deploy End-to-End Consumption Budgets",
    }

    for threat_id, expected_action in expected_immediate.items():
        action_names = {
            action["action"]
            for action in _generate_immediate_actions(
                "fixture", _classification(threat_id)
            )
        }
        assert expected_action in action_names

    for threat_id, expected_action in expected_containment.items():
        action_names = {
            action["action"]
            for action in _generate_containment_actions(
                "fixture", _classification(threat_id), None
            )
        }
        assert expected_action in action_names


def test_legacy_or_wrong_version_ids_do_not_activate_2026_playbooks():
    for threat_id in ("LLM01", "LLM01:2025", "LLM05", "LLM06:2025"):
        assert len(
            _generate_immediate_actions("fixture", _classification(threat_id))
        ) == 3
        assert len(
            _generate_containment_actions(
                "fixture", _classification(threat_id), None
            )
        ) == 3
