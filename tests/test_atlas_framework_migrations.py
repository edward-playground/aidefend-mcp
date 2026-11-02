"""Current ATLAS catalog validation, retired-ID resolution, and consumer lookup contracts."""

import json
from pathlib import Path

import pytest

from app.framework_migrations import (
    FrameworkMigrationRegistryError,
    canonical_lookup_id,
    is_atlas_technique_reference,
    resolve_framework_reference,
    validate_framework_migration_registry,
)
from tests.framework_migration_fixtures import owasp_llm_2026_registry


def registry():
    value = owasp_llm_2026_registry()
    value["frameworks"]["atlas"] = json.loads(
        (Path(__file__).parent / "fixtures/atlas-2026.10-catalog.json").read_text(encoding="utf-8")
    )
    value["registryVersion"] = "2026-10-30"
    return value


def resolve(query, value=None):
    return resolve_framework_reference(query, value or registry(), framework_key="atlas")


def test_every_current_identifier_resolves_to_its_own_current_concept():
    value = registry()
    assert validate_framework_migration_registry(value) == value
    items = value["frameworks"]["atlas"]["activeItems"]
    assert len(items) == 221  # Pinned source fixture, not a runtime population limit.
    for item in items:
        for query in [
            item["id"],
            item["id"] + " " + item["name"],
            "MITRE ATLAS 2026.10 " + item["id"],
            item["id"].replace("AML.", ""),
        ]:
            result = resolve(query, value)
            assert result["status"] == "canonical", query
            assert result["canonical"]["id"] == item["id"]
            assert result["canonical"]["edition"] == "2026.10"
            assert canonical_lookup_id(result) == item["id"]


@pytest.mark.parametrize(
    "retired,successor",
    [
        ("AML.T0024.001", "AML.T0137.002"),
        ("AML.T0024.002", "AML.T0005.001"),
        ("AML.T0056", "AML.T0085.003"),
        ("T0056", "AML.T0085.003"),
        ("AML.T0056 Extract LLM System Prompt", "AML.T0085.003"),
        ("ATLAS 2026.09 AML.T0024.002", "AML.T0005.001"),
    ],
)
def test_retired_identifier_migrates_to_its_single_reviewed_successor(retired, successor):
    result = resolve(retired)
    assert result["status"] == "migrated"
    assert result["canonical"]["id"] == successor
    assert result["migratedFrom"]["edition"] == "2026.09"
    assert result["mappingCarryForward"] == "requires-semantic-review"
    assert canonical_lookup_id(result) == successor


@pytest.mark.parametrize("retired", ["AML.T0024.000", "AML.T0057", "ATLAS 2026.09 AML.T0057"])
def test_split_concept_requires_explicit_selection(retired):
    result = resolve(retired)
    assert result["status"] == "ambiguous"
    assert result["reasonCode"] == "split_concept"
    assert len(result["candidates"]) > 1
    assert canonical_lookup_id(result) is None


@pytest.mark.parametrize(
    "query,status,code",
    [
        ("AML.T9999", "invalid", "unknown_identifier"),
        ("AML.T0144.99", "invalid", "malformed_identifier"),
        ("AML.T0144 Wrong name", "invalid", "id_name_conflict"),
        ("AML.T0056 Wrong name", "invalid", "id_name_conflict"),
        ("ATLAS 2026.09 AML.T0144", "invalid", "unsupported_edition"),
        ("ATLAS 2026.08 AML.T0057", "invalid", "unsupported_edition"),
        ("AML.T0144 LLM01:2026", "invalid", "mixed_frameworks"),
        ("AML.T0144 AITech-1.1", "invalid", "mixed_frameworks"),
        ("AML.T0024.001 AML.T0057", "ambiguous", "multiple_identifiers"),
    ],
)
def test_malformed_conflicting_unknown_and_mixed_input_never_falls_back(query, status, code):
    result = resolve(query)
    assert result["status"] == status
    assert result["reasonCode"] == code
    assert canonical_lookup_id(result) is None


def test_tactics_and_prose_are_not_technique_references():
    for query in ["ATLAS reconnaissance", "AML.TA0001", "MITRE ATLAS tactics", "prompt injection"]:
        assert not is_atlas_technique_reference(query), query
    for query in ["AML.T0051", "aml.t0051.000", "T0051", "ATLAS 2026.10 T0051"]:
        assert is_atlas_technique_reference(query), query
    assert resolve("generic prompt injection") is None


def test_index_without_atlas_catalog_reports_registry_unavailable():
    result = resolve_framework_reference(
        "AML.T0051", owasp_llm_2026_registry(), framework_key="atlas"
    )
    assert result["status"] == "invalid"
    assert result["reasonCode"] == "registry_unavailable"


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "malformed_id",
        "orphaned_parent",
        "retired_current",
        "successor_absent",
        "duplicate_successor",
        "no_successor",
        "duplicate_retirement",
        "future_retirement",
        "carry_forward",
        "mapping_policy",
        "policy_fields",
        "edition",
        "artifact_revision",
        "artifact_edition",
        "digest",
        "source_host",
        "label_collision",
    ],
)
def test_registry_drift_rejected(mutation):
    value = registry()
    catalog = value["frameworks"]["atlas"]
    items = catalog["activeItems"]
    migrations = catalog["migrations"]
    if mutation == "duplicate":
        items[1]["id"] = items[0]["id"]
    if mutation == "malformed_id":
        items[0]["id"] = "AML.T00000"
    if mutation == "orphaned_parent":
        catalog["activeItems"] = [item for item in items if item["id"] != "AML.T0000"]
    if mutation == "retired_current":
        migrations[0]["from"]["id"] = "AML.T0051"
    if mutation == "successor_absent":
        migrations[0]["successors"] = ["AML.T9999"]
    if mutation == "duplicate_successor":
        migrations[1]["successors"] = ["AML.T0137.002", "AML.T0137.002"]
    if mutation == "no_successor":
        migrations[1]["successors"] = []
    if mutation == "duplicate_retirement":
        migrations[1]["from"]["id"] = migrations[0]["from"]["id"]
    if mutation == "future_retirement":
        migrations[0]["from"]["edition"] = "2026.11"
    if mutation == "carry_forward":
        migrations[0]["mappingCarryForward"] = "automatic"
    if mutation == "mapping_policy":
        catalog["resolutionPolicy"]["mappingCarryForward"] = "automatic"
    if mutation == "policy_fields":
        catalog["resolutionPolicy"]["idNameConflict"] = "reject"
    if mutation == "edition":
        catalog["activeEdition"] = "2026.13"
    if mutation == "artifact_revision":
        catalog["sourceArtifact"]["git_revision"] = "0" * 40
    if mutation == "artifact_edition":
        catalog["activeEdition"] = "2026.11"
    if mutation == "digest":
        catalog["sourceArtifact"]["sha256"] = "invalid"
    if mutation == "source_host":
        catalog["sourceUrl"] = "https://example.com/"
    if mutation == "label_collision":
        catalog["activeLabel"] = value["frameworks"]["owasp_llm"]["activeLabel"]
    with pytest.raises(FrameworkMigrationRegistryError):
        validate_framework_migration_registry(value)


def test_query_routing_uses_the_resolver_only_for_an_atlas_generation():
    from app.tools.defenses_for_threat import _resolve_requested_threat_id

    metadata = {"framework_migrations": registry()}
    resolution, identifier = _resolve_requested_threat_id("AML.T0057", metadata)
    assert (resolution["reasonCode"], identifier) == ("split_concept", None)
    resolution, identifier = _resolve_requested_threat_id("T0056", metadata)
    assert (resolution["status"], identifier) == ("migrated", "AML.T0085.003")
    resolution, identifier = _resolve_requested_threat_id("AML.T0051", metadata)
    assert (resolution["status"], identifier) == ("canonical", "AML.T0051")
    resolution, identifier = _resolve_requested_threat_id("AML.T0051 LLM03:2026", metadata)
    assert (resolution["reasonCode"], identifier) == ("mixed_frameworks", None)

    # An index synchronized before the Framework published an ATLAS catalog
    # maps its own generation's identifiers and keeps the legacy exact lookup.
    for legacy in [None, {}, {"framework_migrations": owasp_llm_2026_registry()}]:
        assert _resolve_requested_threat_id("AML.T0057", legacy) == (None, "AML.T0057")


def _corpus(atlas_item):
    return [
        {
            "name": "Harden",
            "techniques": [
                {
                    "id": "AID-H-001",
                    "defendsAgainst": [
                        {
                            "framework": "OWASP LLM Top 10 2026",
                            "items": ["LLM01:2026 Prompt Injection"],
                        },
                        {"framework": "MITRE ATLAS", "items": [atlas_item]},
                    ],
                }
            ],
        }
    ]


def test_ingestion_accepts_current_items_and_rejects_retired_semantics():
    from app.sync import validate_framework_migrations_corpus_contract

    for item in [
        "AML.T0051 LLM Prompt Injection",
        "AML.T0051.000 LLM Prompt Injection: Direct (input boundary)",
        "N/A",
        "N/A (outside this attack taxonomy)",
    ]:
        validate_framework_migrations_corpus_contract(registry(), _corpus(item))
    for item in [
        "AML.T0057 LLM Data Leakage",
        "AML.T0056 Extract LLM System Prompt",
        "AML.T0051 Prompt Injection",
        "N/A ()",
    ]:
        with pytest.raises(FrameworkMigrationRegistryError):
            validate_framework_migrations_corpus_contract(registry(), _corpus(item))


@pytest.mark.asyncio
async def test_actual_tool_queries_successor_and_never_searches_split_concepts(monkeypatch):
    import app.core as core_module
    import app.tools.defenses_for_threat as defenses_module
    import app.utils as utils_module
    from tests.test_framework_migration_tool_resolution import FakeQueryEngine, _record

    successor_item = "AML.T0085.003 Data from AI Services: System Instructions"
    engine = FakeQueryEngine([_record(successor_item, framework="MITRE ATLAS")])
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        utils_module,
        "load_version_info",
        lambda: {
            "framework_migrations": registry(),
            "statistics": {"threat_mappings": {"AML.T0085.003": ["AID-H-001.001"]}},
        },
    )
    migrated = await defenses_module.get_defenses_for_threat(threat_id="AML.T0056")
    assert migrated["threat_query"]["resolution"]["status"] == "migrated"
    assert migrated["threat_query"]["lookup_threat_id"] == "AML.T0085.003"
    assert migrated["threat_query"]["canonical_threat_id"] == "AML.T0085.003"
    assert migrated["total_results"] == 1
    assert migrated["defense_techniques"][0]["matched_threats"] == [successor_item]

    split = await defenses_module.get_defenses_for_threat(threat_id="AML.T0057")
    assert split["search_method"] == "resolution_only"
    assert split["defense_techniques"] == []
    assert split["threat_query"]["resolution"]["reasonCode"] == "split_concept"
    assert split["threat_query"]["lookup_threat_id"] is None
