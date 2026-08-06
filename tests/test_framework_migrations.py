"""Framework migration registry, resolver, and dynamic-label contracts."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.framework_migrations import (
    FrameworkMigrationRegistryError,
    canonical_lookup_id,
    resolve_framework_reference,
    validate_framework_migration_registry,
)
from app.framework_utils import (
    build_framework_metrics,
    framework_labels_from_registry,
    framework_labels_from_version_info,
)
from tests.framework_migration_fixtures import (
    ACTIVE_NAMES,
    LEGACY_NAMES,
    LEGACY_TO_CURRENT_RANK,
    owasp_llm_2026_registry,
)


def test_registry_validation_returns_detached_copy_and_rejects_drift():
    registry = owasp_llm_2026_registry()
    validated = validate_framework_migration_registry(registry)
    assert validated == registry
    assert validated is not registry
    validated["frameworks"]["owasp_llm"]["activeLabel"] = "changed"
    assert registry["frameworks"]["owasp_llm"]["activeLabel"] == (
        "OWASP LLM Top 10 2026"
    )

    invalid_cases = []
    wrong_schema = deepcopy(registry)
    wrong_schema["schemaVersion"] = "2.0"
    invalid_cases.append(wrong_schema)
    duplicate_rank = deepcopy(registry)
    duplicate_rank["frameworks"]["owasp_llm"]["activeItems"][1]["rank"] = 1
    invalid_cases.append(duplicate_rank)
    wrong_target = deepcopy(registry)
    wrong_target["frameworks"]["owasp_llm"]["migrations"][0]["to"]["id"] = (
        "LLM02:2026"
    )
    invalid_cases.append(wrong_target)
    carry_forward = deepcopy(registry)
    carry_forward["frameworks"]["owasp_llm"]["migrations"][0][
        "mappingCarryForward"
    ] = "automatic"
    invalid_cases.append(carry_forward)
    duplicate_target = deepcopy(registry)
    duplicate_target["frameworks"]["owasp_llm"]["migrations"][0]["to"] = deepcopy(
        duplicate_target["frameworks"]["owasp_llm"]["migrations"][1]["to"]
    )
    invalid_cases.append(duplicate_target)
    bad_artifact_digest = deepcopy(registry)
    bad_artifact_digest["frameworks"]["owasp_llm"]["sourceArtifact"][
        "sha256"
    ] = "not-a-sha256"
    invalid_cases.append(bad_artifact_digest)
    missing_policy = deepcopy(registry)
    del missing_policy["frameworks"]["owasp_llm"]["resolutionPolicy"][
        "multipleConcepts"
    ]
    invalid_cases.append(missing_policy)
    two_current_editions = deepcopy(registry)
    two_current_editions["frameworks"]["owasp_llm"]["editions"]["2025"][
        "status"
    ] = "current"
    invalid_cases.append(two_current_editions)

    for invalid in invalid_cases:
        with pytest.raises(FrameworkMigrationRegistryError):
            validate_framework_migration_registry(invalid)


def test_all_legacy_ids_resolve_by_declared_concept_not_current_rank():
    registry = owasp_llm_2026_registry()
    for legacy_rank, current_rank in LEGACY_TO_CURRENT_RANK.items():
        resolution = resolve_framework_reference(
            f"LLM{legacy_rank:02d}:2025", registry
        )
        assert resolution["status"] == "migrated"
        assert resolution["migratedFrom"]["id"] == f"LLM{legacy_rank:02d}:2025"
        assert resolution["canonical"]["id"] == f"LLM{current_rank:02d}:2026"
        assert canonical_lookup_id(resolution) == f"LLM{current_rank:02d}"


def test_current_legacy_names_and_contextual_editions_resolve_deterministically():
    registry = owasp_llm_2026_registry()
    for rank, name in ACTIVE_NAMES.items():
        resolution = resolve_framework_reference(name, registry)
        assert resolution["status"] == "normalized"
        assert resolution["canonical"]["id"] == f"LLM{rank:02d}:2026"

    for legacy_rank, name in LEGACY_NAMES.items():
        resolution = resolve_framework_reference(
            f"OWASP LLM Top 10 2025 {name}", registry
        )
        assert resolution["status"] == "migrated"
        assert resolution["canonical"]["id"] == (
            f"LLM{LEGACY_TO_CURRENT_RANK[legacy_rank]:02d}:2026"
        )

    for query in (
        "OWASP LLM Top 10 2025 LLM03",
        "OWASP Top 10 for LLM Applications 2025 LLM03",
        "LLM03 OWASP 2025",
        "LLM03 2025",
        "2025 / LLM03",
        "LLM03 from 2025",
    ):
        resolution = resolve_framework_reference(query, registry)
        assert resolution["status"] == "migrated"
        assert resolution["canonical"]["id"] == "LLM04:2026"


def test_latest_conflicts_ambiguity_and_non_owasp_boundaries():
    registry = owasp_llm_2026_registry()
    assert resolve_framework_reference("LLM03:2026", registry)["status"] == "canonical"
    assert resolve_framework_reference("LLM03", registry)["status"] == "fallback_latest"
    assert resolve_framework_reference("LLM3 latest", registry)["canonical"]["id"] == (
        "LLM03:2026"
    )
    assert resolve_framework_reference("LLM03:latest", registry)["status"] == (
        "fallback_latest"
    )

    conflict = resolve_framework_reference("LLM03 Supply Chain", registry)
    assert conflict["status"] == "normalized"
    assert conflict["canonical"]["id"] == "LLM04:2026"
    assert conflict["inputNameConflict"]["resolvedBy"] == "recognized-risk-name"

    legacy_conflict = resolve_framework_reference(
        "LLM03:2025 Excessive Agency", registry
    )
    assert legacy_conflict["status"] == "normalized"
    assert legacy_conflict["canonical"]["id"] == "LLM03:2026"

    ambiguous = resolve_framework_reference(
        "LLM03:2025 / LLM06:2025", registry
    )
    assert ambiguous["status"] == "ambiguous"
    assert [candidate["id"] for candidate in ambiguous["candidates"]] == [
        "LLM03:2026",
        "LLM04:2026",
    ]

    for separated in (
        "LLM03:2026&LLM04:2026",
        "LLM03:2026? LLM04:2026",
        "LLM03:2026.LLM04:2026",
        "LLM03? / LLM04",
    ):
        separated_resolution = resolve_framework_reference(separated, registry)
        assert separated_resolution["status"] == "ambiguous", separated
        assert [
            candidate["id"] for candidate in separated_resolution["candidates"]
        ] == ["LLM03:2026", "LLM04:2026"]

    co_resolved = resolve_framework_reference(
        "LLM03:2025 / LLM04:2026 Supply Chain", registry
    )
    assert co_resolved["canonical"]["id"] == "LLM04:2026"
    assert co_resolved["coResolvedReferences"] == ["LLM03:2025", "LLM04:2026"]

    assert resolve_framework_reference("AML.T0051", registry) is None
    assert resolve_framework_reference(
        "Supply Chain Attacks (Cross-Layer)", registry
    ) is None

    cross_framework_residue = resolve_framework_reference(
        "LLM03 MAESTRO Supply Chain Attacks (Cross-Layer)", registry
    )
    assert cross_framework_residue["status"] == "fallback_latest"
    assert cross_framework_residue["canonical"]["id"] == "LLM03:2026"

    mixed_names = resolve_framework_reference(
        "OWASP LLM Prompt Injection System Prompt Leakage", registry
    )
    assert mixed_names["status"] == "ambiguous"
    assert [candidate["id"] for candidate in mixed_names["candidates"]] == [
        "LLM01:2026",
        "LLM08:2026",
    ]


@pytest.mark.parametrize(
    "query",
    [
        "LLM03:",
        "LLM03:foo",
        "LLM03:20X5",
        "LLM03:2025x",
        "LLM03:20250",
        "LLM0003:2026",
        "LLM01:2026.5",
        "LLM03:2026+LLM04:2026",
        "_LLM03:2026",
        "OWASP LLM Top 10 2025 LLM03:2026",
        "OWASP LLM Top 10 2025 LLM03 latest",
        "OWASP LLM 20250 LLM03",
        "LLM03 from 2025x",
        "LLM03 version 2025.1",
        "OWASP LLM Top 10 2027 LLM03",
        "LLM11:2026",
    ],
)
def test_malformed_or_unsupported_references_fail_closed(query):
    resolution = resolve_framework_reference(query, owasp_llm_2026_registry())
    assert resolution["status"] == "invalid"
    assert "canonical" not in resolution


def test_dynamic_labels_are_atomic_non_mutating_and_legacy_safe():
    registry = owasp_llm_2026_registry()
    legacy_labels = framework_labels_from_registry(None)
    current_labels = framework_labels_from_registry(registry)
    assert legacy_labels["owasp_llm"] == "OWASP LLM Top 10 2025"
    assert current_labels["owasp_llm"] == "OWASP LLM Top 10 2026"
    assert framework_labels_from_version_info(
        {"framework_migrations": registry}
    )["owasp_llm"] == "OWASP LLM Top 10 2026"

    malformed = deepcopy(registry)
    malformed["frameworks"]["owasp_llm"]["activeItems"] = []
    with pytest.raises(FrameworkMigrationRegistryError):
        framework_labels_from_registry(malformed)
    assert framework_labels_from_registry(None) is not legacy_labels

    empty_sets = {"owasp_llm": set()}
    legacy_metrics = build_framework_metrics(empty_sets, empty_sets)
    current_metrics = build_framework_metrics(
        empty_sets,
        empty_sets,
        framework_labels=current_labels,
    )
    assert legacy_metrics["by_framework"]["owasp_llm"]["label"] == (
        "OWASP LLM Top 10 2025"
    )
    assert current_metrics["by_framework"]["owasp_llm"]["label"] == (
        "OWASP LLM Top 10 2026"
    )
