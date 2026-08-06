"""Schema-2.3 metadata propagation across defense, validation, and incident paths."""

import json

import pytest

import app.core as core_module
import app.tools.defenses_for_threat as defenses_module
from app.tools.incident_response import _merge_defense_results
from app.tools.validation import validate_technique_id


BOUNDARY = {
    "responsibility": "Owns the test control boundary.",
    "relatedTechniques": [{"id": "AID-D-001", "comparison": "Detection observes this control."}],
}


def _record():
    return {
        "source_id": "AID-H-001.001",
        "name": "Schema 2.3 defense",
        "type": "subtechnique",
        "tactic": "Harden",
        "text": "Defense description.",
        "pillar": json.dumps(["model"]),
        "phase": json.dumps(["building"]),
        "parent_technique_id": "AID-H-001",
        "guidance_id": "",
        "scope_boundary": json.dumps(BOUNDARY),
        "is_actionable": True,
        "is_parent_family": False,
        "defends_against": json.dumps(
            [
                {
                    "framework": "OWASP LLM Top 10 2025",
                    "items": ["LLM01:2025 Prompt Injection"],
                }
            ]
        ),
        "tools_opensource": json.dumps(["Open Source Test Tool"]),
        "tools_source_available": json.dumps(
            ["Source Available Test Tool (Test License; source-available)"]
        ),
        "tools_commercial": json.dumps(["Commercial Test Tool"]),
        "implementation_guidance": "[]",
        "warnings": "[]",
        "_distance": 0.0,
    }


class FakeQueryEngine:
    is_ready = True
    active_embedding_model = "test-embedding"

    def __init__(self, records):
        self.records = records

    async def read_table(self, _operation):
        return [dict(record) for record in self.records]

    async def read_table_snapshot(self, _operation):
        from app.utils import load_version_info

        records = [dict(record) for record in self.records]
        return {
            "embedding_model_changed": False,
            "documents": records,
            "semantic_documents": records,
        }, load_version_info()

    def get_id_cache(self):
        return None


class FakeVector(list):
    def tolist(self):
        return list(self)


class FakeEmbedding:
    def __init__(self, *, model_name):
        assert model_name == "test-embedding"

    def embed(self, texts):
        assert texts
        return iter([FakeVector([0.1, 0.2])])


def _assert_schema23_payload(payload):
    assert payload["id"] == "AID-H-001.001"
    assert payload["type"] == "subtechnique"
    assert payload["parent_technique_id"] == "AID-H-001"
    assert payload["scope_boundary"] == BOUNDARY
    assert payload["is_actionable"] is True
    assert payload["is_parent_family"] is False
    assert payload["pillar"] == ["model"]
    assert payload["phase"] == ["building"]
    assert payload["tools_opensource"] == ["Open Source Test Tool"]
    assert payload["tools_source_available"] == [
        "Source Available Test Tool (Test License; source-available)"
    ]
    assert payload["tools_commercial"] == ["Commercial Test Tool"]


@pytest.mark.asyncio
async def test_exact_index_path_preserves_schema23_metadata(monkeypatch):
    from app import utils

    monkeypatch.setattr(core_module, "query_engine", FakeQueryEngine([_record()]))
    monkeypatch.setattr(
        utils,
        "load_version_info",
        lambda: {"statistics": {"threat_mappings": {"LLM01": ["AID-H-001.001"]}}},
    )

    result = await defenses_module.get_defenses_for_threat(threat_id="LLM01")

    assert result["search_method"] == "exact"
    _assert_schema23_payload(result["defense_techniques"][0]["technique"])


@pytest.mark.asyncio
async def test_full_scan_path_preserves_schema23_metadata(monkeypatch):
    from app import utils

    monkeypatch.setattr(core_module, "query_engine", FakeQueryEngine([_record()]))
    monkeypatch.setattr(utils, "load_version_info", lambda: None)

    result = await defenses_module.get_defenses_for_threat(threat_id="LLM01")

    assert result["search_method"] == "exact"
    _assert_schema23_payload(result["defense_techniques"][0]["technique"])


@pytest.mark.asyncio
async def test_semantic_path_preserves_schema23_metadata(monkeypatch):
    monkeypatch.setattr(core_module, "query_engine", FakeQueryEngine([_record()]))
    monkeypatch.setattr(defenses_module, "TextEmbedding", FakeEmbedding)

    result = await defenses_module.get_defenses_for_threat(threat_keyword="prompt injection")

    assert result["search_method"] == "semantic"
    assert result["defense_techniques"][0]["match_type"] == "semantic_search"
    _assert_schema23_payload(result["defense_techniques"][0]["technique"])


@pytest.mark.asyncio
async def test_validation_success_preserves_schema23_metadata(monkeypatch):
    monkeypatch.setattr(core_module, "query_engine", FakeQueryEngine([_record()]))

    result = await validate_technique_id("AID-H-001.001")

    assert result["valid"] is True
    _assert_schema23_payload(result["technique"])


def test_incident_defense_merge_preserves_schema23_metadata():
    technique = defenses_module._public_technique_payload(
        core_module.decode_framework_record(_record())
    )
    defense_entry = {
        "technique": technique,
        "relevance_score": 1.0,
        "matched_threats": ["LLM01:2025 Prompt Injection"],
    }

    merged = _merge_defense_results([("LLM01", {"defense_techniques": [defense_entry]})])

    _assert_schema23_payload(merged["defense_techniques"][0]["technique"])
