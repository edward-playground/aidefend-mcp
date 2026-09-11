"""Synthetic compatible releases exercise metadata evolution, not future Cisco facts."""

import pytest

from app.framework_migrations import (
    FrameworkMigrationRegistryError,
    resolve_framework_reference,
    validate_framework_migration_registry,
)
from app.tools.defenses_for_threat import _resolve_requested_threat_id
from tests.test_cisco_framework_migrations import registry
from tests.test_generic_framework_renames import _registry_with_renamed_cisco


def evolved():
    value = registry()
    catalog = value["frameworks"]["cisco"]
    label = "TrustSphere AI Defense"
    catalog.update(
        activeEdition="3.1.0",
        activeLabel=label,
        officialTitle=label,
        displayLabel=label + " v3.1.0",
    )
    catalog["editions"]["2.0.0"]["status"] = "superseded"
    catalog["editions"]["3.1.0"] = {"label": label, "status": "current"}
    catalog["responseContract"]["canonicalEdition"] = "3.1.0"
    catalog["sourceArtifact"]["release"] = "v3.1.0"
    catalog["activeItems"].append(
        {"id": "AITech-20.1", "name": "Synthetic Defense Test", "parentObjective": "OB-020"}
    )
    catalog["historicalItems"].append(
        {
            "edition": "2.0.0",
            "id": "AITech-20.2",
            "name": "Synthetic Removed Test",
            "status": "retired",
        }
    )
    return value


def test_compatible_release_uses_catalog_version_label_and_population():
    value = evolved()
    assert validate_framework_migration_registry(value) == value
    for query in [
        "AITech-20.1",
        "Cisco v3.1 AITech-20.1",
        "AITech-20.1:3.1.0",
        "TrustSphere AI Defense Synthetic Defense Test",
        "TrustSphere AI Defense v3.1.0 AITech-20.1",
    ]:
        resolution, lookup = _resolve_requested_threat_id(query, {"framework_migrations": value})
        assert lookup == "AITECH-20.1", (query, resolution)
        assert resolution["canonical"]["edition"] == "3.1.0"
        assert resolution["canonical"]["framework"] == "TrustSphere AI Defense"
    for query in ["Cisco v2 AITech-20.1", "Cisco v1 AITech-2.1"]:
        result = resolve_framework_reference(query, value, framework_key="cisco")
        assert result["reasonCode"] == "unsupported_edition"
        assert "canonical" not in result
    # Bare major 3 cannot silently select 3.1.0.
    result = resolve_framework_reference("Cisco v3 AITech-20.1", value, framework_key="cisco")
    assert result["status"] == "invalid"


def test_removing_an_item_is_checked_against_the_actual_ingested_corpus():
    from app.sync import validate_framework_migrations_corpus_contract
    from tests.test_cisco_framework_migrations import corpus

    value = evolved()
    catalog = value["frameworks"]["cisco"]
    catalog["activeItems"] = [x for x in catalog["activeItems"] if x["id"] != "AITech-20.1"]
    validate_framework_migration_registry(value)
    with pytest.raises(FrameworkMigrationRegistryError):
        validate_framework_migrations_corpus_contract(
            value, corpus("AITech-20.1 Synthetic Defense Test")
        )


@pytest.mark.parametrize(
    "mutation", ["label", "response", "release", "aliases", "history", "parent", "format"]
)
def test_evolved_catalog_still_rejects_inconsistent_metadata(mutation):
    value = evolved()
    catalog = value["frameworks"]["cisco"]
    if mutation == "label":
        catalog["activeLabel"] = "Conflicting Label"
    if mutation == "response":
        catalog["responseContract"]["canonicalEdition"] = "2.0.0"
    if mutation == "release":
        catalog["sourceArtifact"]["release"] = "v2.0.0"
    if mutation == "aliases":
        catalog["editions"]["3.1"] = {"label": "Old label", "status": "superseded"}
    if mutation == "history":
        catalog["historicalItems"][0]["edition"] = "3.1.0"
    if mutation == "parent":
        child = next(x for x in catalog["activeItems"] if "parentTechnique" in x)
        child["parentTechnique"] = child["id"]
    if mutation == "format":
        catalog["responseContract"]["canonicalIdFormat"] = "unsupported"
        del catalog["historicalItems"]
    with pytest.raises(FrameworkMigrationRegistryError):
        validate_framework_migration_registry(value)


def test_generic_catalog_remains_ingestible_but_unknown_query_profile_is_explicit():
    value = _registry_with_renamed_cisco()
    validate_framework_migration_registry(value)
    resolution, lookup = _resolve_requested_threat_id("AITECH-1", {"framework_migrations": value})
    assert lookup is None
    assert resolution["reasonCode"] == "unsupported_catalog_profile"
