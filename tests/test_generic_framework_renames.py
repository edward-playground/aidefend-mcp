"""Stable-key behavior for framework label changes beyond OWASP LLM."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app.framework_migrations import (
    FrameworkMigrationRegistryError,
    RESOLUTION_STATUSES,
    validate_framework_migration_registry,
)
from app.framework_utils import (
    UNKNOWN_FRAMEWORK_KEY_PREFIX,
    extract_framework_coverage,
    framework_coverage_key,
    framework_key,
    framework_labels_from_registry,
    normalize_framework_item,
)
from app.sync import validate_framework_migrations_corpus_contract
from tests.framework_migration_fixtures import owasp_llm_2026_registry


RENAMED_CISCO_LABEL = "Cisco AI Trust and Resilience Framework 2027"


def _generic_catalog(stable_key: str, active_label: str):
    return {
        "stableKey": stable_key,
        "activeEdition": "2027",
        "activeLabel": active_label,
        "officialTitle": active_label,
        "sourceUrl": "https://example.com/framework",
        "editions": {
            "2027": {"label": active_label, "status": "current"},
        },
        "responseContract": {
            "canonicalEdition": "2027",
            "canonicalIdFormat": "AITECH-n",
            "metadataField": "resolution",
            "metadataValues": sorted(RESOLUTION_STATUSES),
        },
        "activeItems": [
            {
                "id": "AITECH-1",
                "rank": 1,
                "name": "AI Security Governance",
                "description": "A generic active item used to test label migration.",
            }
        ],
        "migrations": [],
        "sourceArtifact": {},
        "sourceLicense": {},
        "resolutionPolicy": {},
    }


def _registry_with_renamed_cisco():
    registry = owasp_llm_2026_registry()
    registry["frameworks"]["cisco"] = _generic_catalog(
        "cisco", RENAMED_CISCO_LABEL
    )
    return registry


def test_arbitrary_current_cisco_label_resolves_to_stable_key():
    labels = framework_labels_from_registry(_registry_with_renamed_cisco())

    assert labels["cisco"] == RENAMED_CISCO_LABEL
    assert framework_key(
        RENAMED_CISCO_LABEL,
        framework_labels=labels,
    ) == "cisco"
    assert normalize_framework_item(
        RENAMED_CISCO_LABEL,
        "AITECH-1 AI Security Governance",
        framework_labels=labels,
    ) == "AITECH-1"


def test_renamed_label_keeps_cisco_coverage_key_and_item_normalization():
    labels = framework_labels_from_registry(_registry_with_renamed_cisco())
    coverage = extract_framework_coverage(
        [
            {
                "framework": RENAMED_CISCO_LABEL,
                "items": ["AITECH-1 AI Security Governance"],
            }
        ],
        framework_labels=labels,
    )

    assert coverage["cisco"] == {"AITECH-1"}
    assert framework_coverage_key(
        RENAMED_CISCO_LABEL,
        framework_labels=labels,
    ) == "cisco"


def test_registryless_static_labels_remain_backward_compatible():
    labels = framework_labels_from_registry(None)

    assert framework_key(labels["cisco"]) == "cisco"
    assert labels["owasp_llm"] == "OWASP LLM Top 10 2025"
    assert framework_key(labels["owasp_llm"]) == "owasp_llm"


def test_present_but_invalid_registry_fails_closed():
    registry = _registry_with_renamed_cisco()
    registry["frameworks"]["cisco"]["activeItems"] = []

    with pytest.raises(FrameworkMigrationRegistryError):
        framework_labels_from_registry(registry)


def test_registry_active_labels_cannot_collide_case_insensitively():
    registry = _registry_with_renamed_cisco()
    registry["frameworks"]["cisco"]["activeLabel"] = (
        "owasp llm top 10 2026"
    )
    registry["frameworks"]["cisco"]["editions"]["2027"]["label"] = (
        "owasp llm top 10 2026"
    )

    with pytest.raises(FrameworkMigrationRegistryError, match="collide"):
        validate_framework_migration_registry(registry)


def test_active_label_must_match_the_active_edition_label():
    registry = _registry_with_renamed_cisco()
    registry["frameworks"]["cisco"]["activeLabel"] = (
        "TrustSphere AI Defense 2027"
    )

    with pytest.raises(FrameworkMigrationRegistryError, match="active edition label"):
        validate_framework_migration_registry(registry)


def test_superseded_edition_label_remains_a_stable_key_alias_after_second_rename():
    registry = _registry_with_renamed_cisco()
    catalog = registry["frameworks"]["cisco"]
    catalog["activeEdition"] = "2028"
    catalog["activeLabel"] = "TrustSphere AI Defense 2028"
    catalog["officialTitle"] = "TrustSphere AI Defense 2028"
    catalog["editions"]["2027"]["status"] = "superseded"
    catalog["editions"]["2028"] = {
        "label": "TrustSphere AI Defense 2028",
        "status": "current",
    }
    catalog["responseContract"]["canonicalEdition"] = "2028"

    labels = framework_labels_from_registry(registry)

    assert labels["cisco"] == "TrustSphere AI Defense 2028"
    assert framework_key(
        RENAMED_CISCO_LABEL,
        framework_labels=labels,
    ) == "cisco"
    assert framework_key(
        "TrustSphere AI Defense 2028",
        framework_labels=labels,
    ) == "cisco"


def test_superseded_edition_labels_cannot_collide_across_catalogs():
    registry = _registry_with_renamed_cisco()
    registry["frameworks"]["cisco"]["editions"]["2026"] = {
        "label": "OWASP LLM Top 10 2025",
        "status": "superseded",
    }

    with pytest.raises(FrameworkMigrationRegistryError, match="collide"):
        validate_framework_migration_registry(registry)


def test_registry_label_cannot_collide_with_another_legacy_classifier():
    registry = _registry_with_renamed_cisco()
    colliding_label = "MAESTRO Security Catalog 2027"
    registry["frameworks"]["cisco"]["activeLabel"] = colliding_label
    registry["frameworks"]["cisco"]["editions"]["2027"]["label"] = (
        colliding_label
    )

    with pytest.raises(FrameworkMigrationRegistryError, match="legacy stable key"):
        framework_labels_from_registry(registry)


def test_unknown_additive_label_stays_collision_safe_with_dynamic_labels():
    labels = framework_labels_from_registry(_registry_with_renamed_cisco())
    unknown_label = "Future AI Threat Framework"

    assert framework_coverage_key(
        unknown_label,
        framework_labels=labels,
    ) == f"{UNKNOWN_FRAMEWORK_KEY_PREFIX}{unknown_label}"


def test_sync_corpus_contract_accepts_the_registry_active_generic_label():
    registry = _registry_with_renamed_cisco()
    parsed_tactics = [
        {
            "techniques": [
                {
                    "id": "AID-H-999",
                    "defendsAgainst": [
                        {
                            "framework": "OWASP LLM Top 10 2026",
                            "items": ["LLM01:2026 Prompt Injection"],
                        },
                        {
                            "framework": RENAMED_CISCO_LABEL,
                            "items": ["AITECH-1 AI Security Governance"],
                        },
                    ],
                }
            ]
        }
    ]

    validate_framework_migrations_corpus_contract(registry, parsed_tactics)


def test_sync_corpus_contract_accepts_multiword_maestro_item_ids():
    registry = _registry_with_renamed_cisco()
    del registry["frameworks"]["cisco"]
    maestro_label = "MAESTRO Threat Catalog 2027"
    maestro = _generic_catalog("maestro", maestro_label)
    maestro["responseContract"]["canonicalIdFormat"] = (
        "canonical threat label with layer suffix"
    )
    maestro["activeItems"] = [
        {
            "id": "Backdoor Attacks (L1)",
            "rank": 1,
            "name": "Backdoor Attacks (L1)",
            "description": "A model-layer backdoor threat.",
        },
        {
            "id": "Backdoor Attacks (L3)",
            "rank": 2,
            "name": "Backdoor Attacks (L3)",
            "description": "A framework-layer backdoor threat.",
        },
    ]
    registry["frameworks"]["maestro"] = maestro
    parsed_tactics = [
        {
            "techniques": [
                {
                    "id": "AID-H-999",
                    "defendsAgainst": [
                        {
                            "framework": "OWASP LLM Top 10 2026",
                            "items": ["LLM01:2026 Prompt Injection"],
                        },
                        {
                            "framework": maestro_label,
                            "items": [
                                "Backdoor Attacks (L1)",
                                "Backdoor Attacks (L3) (framework-layer validation)",
                            ],
                        },
                    ],
                }
            ]
        }
    ]

    validate_framework_migrations_corpus_contract(registry, parsed_tactics)
