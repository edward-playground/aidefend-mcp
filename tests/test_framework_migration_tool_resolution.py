"""End-user threat lookup behavior across OWASP LLM editions."""

from __future__ import annotations

import json

import pytest

import app.core as core_module
import app.tools.defenses_for_threat as defenses_module
import app.utils as utils_module
from app.framework_migrations import FrameworkMigrationRegistryError
from tests.framework_migration_fixtures import owasp_llm_2026_registry


class FakeQueryEngine:
    is_ready = True
    active_embedding_model = "test-embedding"

    def __init__(self, records):
        self.records = records
        self.read_count = 0

    async def read_table(self, _operation):
        self.read_count += 1
        return [dict(record) for record in self.records]

    async def read_table_snapshot(self, _operation):
        from app.utils import load_version_info

        self.read_count += 1
        records = [dict(record) for record in self.records]
        return {
            "embedding_model_changed": False,
            "documents": records,
            "semantic_documents": records,
        }, load_version_info()


def _record(
    threat_item: str,
    framework: str = "OWASP LLM Top 10 2026",
    source_id: str = "AID-H-001.001",
):
    return {
        "source_id": source_id,
        "name": "Test defense",
        "type": "subtechnique",
        "tactic": "Harden",
        "text": "Test defense description",
        "pillar": '["app"]',
        "phase": '["operation"]',
        "defends_against": json.dumps(
            [{"framework": framework, "items": [threat_item]}]
        ),
        "tools_opensource": "[]",
        "tools_source_available": "[]",
        "tools_commercial": "[]",
        "implementation_guidance": "[]",
        "scope_boundary": "{}",
        "parent_technique_id": "AID-H-001",
        "guidance_id": "",
        "is_actionable": True,
        "is_parent_family": False,
    }


@pytest.mark.asyncio
async def test_legacy_id_returns_current_semantic_successor_defenses(monkeypatch):
    engine = FakeQueryEngine([_record("LLM04:2026 Supply Chain")])
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        utils_module,
        "load_version_info",
        lambda: {
            "framework_migrations": owasp_llm_2026_registry(),
            "statistics": {
                "threat_mappings": {"LLM04": ["AID-H-001.001"]}
            },
        },
    )

    result = await defenses_module.get_defenses_for_threat(
        threat_id="LLM03:2025"
    )

    query = result["threat_query"]
    assert query["threat_id"] == "LLM03:2025"
    assert query["lookup_threat_id"] == "LLM04"
    assert query["canonical_threat_id"] == "LLM04:2026"
    assert query["resolution"]["status"] == "migrated"
    assert query["resolution"]["migratedFrom"]["id"] == "LLM03:2025"
    assert result["defense_techniques"][0]["matched_threats"] == [
        "LLM04:2026 Supply Chain"
    ]


@pytest.mark.asyncio
async def test_bare_id_means_current_edition_and_does_not_use_old_rank(monkeypatch):
    engine = FakeQueryEngine([_record("LLM03:2026 Excessive Agency")])
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        utils_module,
        "load_version_info",
        lambda: {
            "framework_migrations": owasp_llm_2026_registry(),
            "statistics": {
                "threat_mappings": {"LLM03": ["AID-H-001.001"]}
            },
        },
    )

    result = await defenses_module.get_defenses_for_threat(threat_id="LLM03")
    assert result["threat_query"]["canonical_threat_id"] == "LLM03:2026"
    assert result["threat_query"]["resolution"]["status"] == "fallback_latest"
    assert result["defense_techniques"][0]["matched_threats"] == [
        "LLM03:2026 Excessive Agency"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query, expected_status",
    [
        ("LLM03:2025x", "invalid"),
        ("LLM03:2025 / LLM06:2025", "ambiguous"),
    ],
)
async def test_invalid_and_ambiguous_queries_never_guess_or_scan(
    monkeypatch, query, expected_status
):
    engine = FakeQueryEngine([_record("LLM04:2026 Supply Chain")])
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        utils_module,
        "load_version_info",
        lambda: {
            "framework_migrations": owasp_llm_2026_registry(),
            "statistics": {
                "threat_mappings": {"LLM04": ["AID-H-001.001"]}
            },
        },
    )

    result = await defenses_module.get_defenses_for_threat(threat_id=query)
    assert result["search_method"] == "resolution_only"
    assert result["total_results"] == 0
    assert result["threat_query"]["lookup_threat_id"] is None
    assert result["threat_query"]["resolution"]["status"] == expected_status
    assert engine.read_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "AML.T0051 / LLM03:2025",
        "T0051 and LLM03:2025",
        "ML01:2023 / LLM03:2025",
    ],
)
async def test_mixed_framework_ids_never_bypass_owasp_migration(monkeypatch, query):
    engine = FakeQueryEngine([_record("LLM03:2026 Excessive Agency")])
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        utils_module,
        "load_version_info",
        lambda: {
            "framework_migrations": owasp_llm_2026_registry(),
            "statistics": {"threat_mappings": {"LLM03": ["AID-H-001.001"]}},
        },
    )

    result = await defenses_module.get_defenses_for_threat(threat_id=query)
    assert result["search_method"] == "resolution_only"
    assert result["threat_query"]["resolution"]["status"] == "invalid"
    assert result["total_results"] == 0
    assert engine.read_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    ["LLM03:2026", "LLM03:latest", "LLM03:2025x", "LLM03 latest"],
)
async def test_registryless_legacy_index_rejects_unprovable_current_or_malformed_ids(
    monkeypatch, query
):
    engine = FakeQueryEngine(
        [_record("LLM03:2025 Supply Chain", "OWASP LLM Top 10 2025")]
    )
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        utils_module,
        "load_version_info",
        lambda: {
            "statistics": {"threat_mappings": {"LLM03": ["AID-H-001.001"]}}
        },
    )

    result = await defenses_module.get_defenses_for_threat(threat_id=query)
    assert result["search_method"] == "resolution_only"
    assert result["threat_query"]["resolution"]["status"] == "invalid"
    assert result["total_results"] == 0
    assert engine.read_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query, expected_status",
    [
        ("LLM03:2025x", "invalid"),
        ("LLM03:2025 / LLM06:2025", "ambiguous"),
    ],
)
async def test_invalid_or_ambiguous_id_blocks_keyword_fallback(
    monkeypatch, query, expected_status
):
    engine = FakeQueryEngine([_record("LLM04:2026 Supply Chain")])
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        utils_module,
        "load_version_info",
        lambda: {
            "framework_migrations": owasp_llm_2026_registry(),
            "statistics": {"threat_mappings": {"LLM04": ["AID-H-001.001"]}},
        },
    )

    result = await defenses_module.get_defenses_for_threat(
        threat_id=query,
        threat_keyword="supply chain",
    )
    assert result["search_method"] == "resolution_only"
    assert result["threat_query"]["resolution"]["status"] == expected_status
    assert result["total_results"] == 0
    assert engine.read_count == 1


@pytest.mark.asyncio
async def test_registryless_old_index_keeps_legacy_rank_behavior(monkeypatch):
    engine = FakeQueryEngine(
        [_record("LLM03:2025 Supply Chain", "OWASP LLM Top 10 2025")]
    )
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        utils_module,
        "load_version_info",
        lambda: {
            "statistics": {
                "threat_mappings": {"LLM03": ["AID-H-001.001"]}
            }
        },
    )

    result = await defenses_module.get_defenses_for_threat(
        threat_id="LLM03:2025"
    )
    assert result["threat_query"]["lookup_threat_id"] == "LLM03"
    assert result["threat_query"]["canonical_threat_id"] is None
    assert result["threat_query"]["resolution"] is None
    assert result["defense_techniques"][0]["framework"] == (
        "OWASP LLM Top 10 2025"
    )


@pytest.mark.asyncio
async def test_invalid_registry_fails_closed_for_atlas_lookup(monkeypatch):
    engine = FakeQueryEngine(
        [_record("AML.T0051 LLM Prompt Injection", "MITRE ATLAS")]
    )
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        utils_module,
        "load_version_info",
        lambda: {
            "framework_migrations": {"schemaVersion": "broken"},
            "statistics": {
                "threat_mappings": {"AML.T0051": ["AID-H-001.001"]}
            },
        },
    )

    with pytest.raises(
        FrameworkMigrationRegistryError,
        match="schemaVersion is unsupported",
    ):
        await defenses_module.get_defenses_for_threat(threat_id="AML.T0051")
    assert engine.read_count == 1


@pytest.mark.asyncio
async def test_invalid_registry_fails_closed_for_generic_framework_lookup(
    monkeypatch,
):
    engine = FakeQueryEngine([_record("MST: Model Security", "Google Secure AI Framework")])
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        utils_module,
        "load_version_info",
        lambda: {
            "framework_migrations": {"schemaVersion": "broken"},
            "statistics": {"threat_mappings": {"MST": ["AID-H-001.001"]}},
        },
    )

    with pytest.raises(
        FrameworkMigrationRegistryError,
        match="schemaVersion is unsupported",
    ):
        await defenses_module.get_defenses_for_threat(threat_id="MST")
    assert engine.read_count == 1


@pytest.mark.asyncio
async def test_fast_index_candidate_must_match_active_record_before_return(monkeypatch):
    wrong = _record(
        "LLM04:2026 Supply Chain",
        source_id="AID-H-001.001",
    )
    correct = _record(
        "LLM03:2026 Excessive Agency",
        source_id="AID-H-001.002",
    )
    engine = FakeQueryEngine([wrong, correct])
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        utils_module,
        "load_version_info",
        lambda: {
            "framework_migrations": owasp_llm_2026_registry(),
            "statistics": {"threat_mappings": {"LLM03": ["AID-H-001.001"]}},
        },
    )

    result = await defenses_module.get_defenses_for_threat(threat_id="LLM03:2026")
    returned_ids = [item["technique"]["id"] for item in result["defense_techniques"]]
    assert returned_ids == ["AID-H-001.002"]
    assert engine.read_count == 1
