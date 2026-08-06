"""Narrow compatibility contracts for the known legacy public framework."""

from copy import deepcopy

from app.sync import (
    LEGACY_FRAMEWORK_CONTENT_SHA256,
    LEGACY_FRAMEWORK_REPOSITORY,
    LEGACY_FRAMEWORK_SOURCE_REVISION,
    LEGACY_FRAMEWORK_VERSION,
    extract_documents_from_tactic,
    uses_legacy_framework_contract,
    validate_tactic_contract,
)


def _legacy_tactic():
    return {
        "name": "Harden",
        "purpose": "Synthetic legacy compatibility fixture.",
        "techniques": [
            {
                "id": "AID-H-001",
                "name": "Legacy parent",
                "description": "Historical navigation parent.",
                "defendsAgainst": [
                    {
                        "framework": "Synthetic Threat Matrix",
                        "items": ["PARENT-ONLY"],
                    }
                ],
                "subTechniques": [
                    {
                        "id": "AID-H-001.001",
                        "name": "First legacy control",
                        "description": "First actionable child.",
                        "pillar": ["app"],
                        "phase": ["building"],
                        "defendsAgainst": [
                            {
                                "framework": "Synthetic Threat Matrix",
                                "items": ["CHILD-ONE"],
                            }
                        ],
                        "implementationGuidance": [
                            {
                                "implementation": "Apply the first control.",
                                "howTo": "<p>Configure the first control.</p>",
                            }
                        ],
                    },
                    {
                        "id": "AID-H-001.002",
                        "name": "Second legacy control",
                        "description": "Second actionable child.",
                        "pillar": ["infra"],
                        "phase": ["operation"],
                        "defendsAgainst": [
                            {
                                "framework": "Synthetic Threat Matrix",
                                "items": ["CHILD-TWO"],
                            }
                        ],
                        "implementationGuidance": [
                            {
                                "implementation": "Apply the second control.",
                                "howTo": "<p>Configure the second control.</p>",
                            }
                        ],
                    },
                ],
            }
        ],
    }


def _profile(**overrides):
    values = {
        "source_kind": "github",
        "source_repository": LEGACY_FRAMEWORK_REPOSITORY,
        "source_revision": LEGACY_FRAMEWORK_SOURCE_REVISION,
        "source_content_sha256": LEGACY_FRAMEWORK_CONTENT_SHA256,
        "framework_version": LEGACY_FRAMEWORK_VERSION,
    }
    values.update(overrides)
    return uses_legacy_framework_contract(**values)


def test_only_exact_canonical_legacy_release_selects_legacy_contract():
    assert _profile() is True
    assert _profile(source_kind="local") is False
    assert _profile(source_repository="example.invalid/aidefense-framework") is False
    assert _profile(source_revision="a" * 40) is False
    assert _profile(source_content_sha256="b" * 64) is False
    assert _profile(framework_version="1.20260724") is False


def test_legacy_mode_accepts_only_known_missing_ids_and_parent_union_semantics():
    tactic = _legacy_tactic()

    strict_errors = validate_tactic_contract(tactic, "harden.js")
    assert sum("id must be a non-empty string" in error for error in strict_errors) == 2
    assert any("parent union is missing" in error for error in strict_errors)
    assert any("parent union introduces" in error for error in strict_errors)

    assert (
        validate_tactic_contract(
            tactic,
            "harden.js",
            legacy_contract=True,
        )
        == []
    )

    strategy_ids = {
        document["source_id"]
        for document in extract_documents_from_tactic(tactic)
        if document["type"] == "strategy"
    }
    assert strategy_ids == {
        "AID-H-001.001.S1",
        "AID-H-001.002.S1",
    }


def test_legacy_mode_rejects_any_modern_guidance_id_as_mixed_shape():
    tactic = _legacy_tactic()
    first_strategy = tactic["techniques"][0]["subTechniques"][0]["implementationGuidance"][0]
    first_strategy["id"] = "AID-H-001.001-G001"

    errors = validate_tactic_contract(
        tactic,
        "harden.js",
        legacy_contract=True,
    )

    assert any("modern guidance id marker" in error for error in errors)
    assert any("id must be a non-empty string" in error for error in errors)
    assert any("parent union is missing" in error for error in errors)


def test_legacy_mode_rejects_modern_control_markers_as_mixed_shape():
    modern_fields = {
        "scopeBoundary": {
            "responsibility": "Modern explicit ownership boundary.",
            "relatedTechniques": [],
        },
        "toolsSourceAvailable": ["Modern Tool (Model Terms; source-available)"],
    }

    for field, value in modern_fields.items():
        tactic = _legacy_tactic()
        tactic["techniques"][0]["subTechniques"][0][field] = value

        errors = validate_tactic_contract(
            tactic,
            "harden.js",
            legacy_contract=True,
        )

        assert any(f"modern marker field '{field}'" in error for error in errors)
        assert any("parent union is missing" in error for error in errors)


def test_schema_present_contract_keeps_guidance_owner_and_uniqueness_strict():
    tactic = _legacy_tactic()
    parent = tactic["techniques"][0]
    parent["defendsAgainst"][0]["items"] = ["CHILD-ONE", "CHILD-TWO"]
    first_child, second_child = parent["subTechniques"]
    first_child["implementationGuidance"][0]["id"] = "AID-H-001.001-G001"
    second_child["implementationGuidance"][0]["id"] = "AID-H-001.002-G001"
    assert validate_tactic_contract(tactic, "harden.js") == []

    wrong_owner = deepcopy(tactic)
    wrong_owner["techniques"][0]["subTechniques"][1]["implementationGuidance"][0][
        "id"
    ] = "AID-H-001.001-G001"
    errors = validate_tactic_contract(wrong_owner, "harden.js")
    assert any("does not belong to control" in error for error in errors)
    assert any("duplicate guidance id" in error for error in errors)
