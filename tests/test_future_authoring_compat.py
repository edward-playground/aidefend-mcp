from copy import deepcopy
from types import SimpleNamespace

import pytest
from tokenizers import Tokenizer, models, pre_tokenizers

from app.framework_utils import coverage_lists_from_sets, extract_framework_coverage
from app.sync import (
    EXPECTED_FRAMEWORK_LABELS,
    _validate_scope_boundary_token_visibility,
    _validate_tool_token_visibility,
    extract_documents_from_tactic,
    validate_tactic_contract,
)


def _mappings():
    return [
        {
            "framework": framework,
            "items": [f"N/A ({framework} is not applicable)"],
        }
        for framework in EXPECTED_FRAMEWORK_LABELS
    ]


def _tactic():
    return {
        "name": "Harden",
        "purpose": "Protect AI systems.",
        "techniques": [
            {
                "id": "AID-H-001",
                "name": "Future-Compatible Control",
                "description": "Control description that remains searchable.",
                "pillar": ["future-pillar"],
                "phase": ["future-phase"],
                "defendsAgainst": _mappings(),
                "toolsOpenSource": ["Example OSS Tool"],
                "toolsSourceAvailable": [
                    "Example Open Weight Tool (Model Terms; open-weight)"
                ],
                "toolsCommercial": ["Example Commercial Tool"],
                "scopeBoundary": {
                    "responsibility": "Own this exact control boundary.",
                    "relatedTechniques": [
                        {
                            "id": "AID-D-001",
                            "comparison": "Detection observes the same boundary.",
                        }
                    ],
                },
            }
        ],
    }


def _errors(tactic):
    return validate_tactic_contract(tactic, "harden.js")


def test_additive_authoring_fields_frameworks_and_dimension_values_are_accepted():
    tactic = _tactic()
    control = tactic["techniques"][0]
    control["warning"] = {
        "level": "Important",
        "description": "Review the boundary.",
        "futureMetadata": "allowed",
    }
    control["scopeBoundary"]["futureMetadata"] = True
    control["scopeBoundary"]["relatedTechniques"][0]["futureMetadata"] = True
    for mapping in control["defendsAgainst"]:
        mapping["futureMetadata"] = True
    control["defendsAgainst"].append(
        {
            "framework": "Future AI Threat Framework",
            "items": ["FUTURE-001 New threat"],
            "futureMetadata": True,
        }
    )
    control["defendsAgainst"] = list(reversed(control["defendsAgainst"]))

    assert _errors(tactic) == []


def test_framework_labels_may_be_removed_renamed_and_added_without_runtime_gate():
    tactic = _tactic()
    control = tactic["techniques"][0]
    renamed_framework = "Renamed AI Threat Framework"
    added_framework = "Future AI Threat Framework"
    control["defendsAgainst"] = [
        {
            "framework": renamed_framework,
            "items": ["RENAMED-001 Renamed threat"],
        },
        {
            "framework": added_framework,
            "items": ["FUTURE-001 New threat"],
        },
    ]

    assert _errors(tactic) == []

    document = extract_documents_from_tactic(tactic)[0]
    public_coverage = coverage_lists_from_sets(
        extract_framework_coverage(document["defends_against"])
    )
    assert public_coverage[renamed_framework] == ["RENAMED-001"]
    assert public_coverage[added_framework] == ["FUTURE-001"]


def test_optional_guidance_and_stable_reordered_or_gapped_ids_are_accepted():
    tactic = _tactic()
    control = tactic["techniques"][0]

    assert "implementationGuidance" not in control
    assert _errors(tactic) == []

    control["implementationGuidance"] = []
    assert _errors(tactic) == []

    control["implementationGuidance"] = [
        {
            "id": "AID-H-001-G009",
            "implementation": "Later stable guidance",
            "howTo": "<p>Do the later step.</p>",
        },
        {
            "id": "AID-H-001-G003",
            "implementation": "Earlier stable guidance",
            "howTo": "<p>Do the earlier step.</p>",
        },
    ]
    assert _errors(tactic) == []

    wrong_owner = deepcopy(tactic)
    wrong_owner["techniques"][0]["implementationGuidance"][0]["id"] = (
        "AID-D-001-G009"
    )
    assert any("does not belong to control" in error for error in _errors(wrong_owner))

    duplicate = deepcopy(tactic)
    duplicate["techniques"][0]["implementationGuidance"][1]["id"] = (
        "AID-H-001-G009"
    )
    assert any("duplicate guidance id" in error for error in _errors(duplicate))


def test_future_tactic_segment_is_accepted_for_control_guidance_owner_and_reference():
    tactic = _tactic()
    control = tactic["techniques"][0]
    control["id"] = "AID-GOVERNANCE-001"
    control["scopeBoundary"]["relatedTechniques"][0]["id"] = "AID-QA2-001"
    control["implementationGuidance"] = [
        {
            "id": "AID-GOVERNANCE-001-G007",
            "implementation": "Govern the future tactic.",
            "howTo": "<p>Apply governance.</p>",
        }
    ]

    assert _errors(tactic) == []


def test_missing_required_shapes_and_duplicates_still_fail_closed():
    missing_items = _tactic()
    del missing_items["techniques"][0]["defendsAgainst"][0]["items"]
    assert any("must contain framework and items" in error for error in _errors(missing_items))

    duplicate_mapping = _tactic()
    duplicate_mapping["techniques"][0]["defendsAgainst"].append(
        deepcopy(duplicate_mapping["techniques"][0]["defendsAgainst"][0])
    )
    assert any("duplicate framework label" in error for error in _errors(duplicate_mapping))

    duplicate_dimension = _tactic()
    duplicate_dimension["techniques"][0]["pillar"] = ["future", "future"]
    assert any("pillar must not contain duplicates" in error for error in _errors(duplicate_dimension))


def test_search_text_keeps_identity_scope_and_all_tools_before_long_content():
    tactic = _tactic()
    tactic["techniques"][0]["implementationGuidance"] = [
        {
            "id": "AID-H-001-G009",
            "implementation": "Stable guidance",
            "howTo": "<p>Apply the control.</p>",
        }
    ]

    documents = extract_documents_from_tactic(tactic)
    control = next(document for document in documents if document["type"] == "technique")
    strategy = next(document for document in documents if document["type"] == "strategy")

    assert (
        control["text"].index("ID:")
        < control["text"].index("Scope Boundary:")
        < control["text"].index("Tools:")
        < control["text"].index("Description:")
        < control["text"].index("Defends Against:")
    )
    assert (
        strategy["text"].index("Implementation Guidance:")
        < strategy["text"].index("ID:")
        < strategy["text"].index("Scope Boundary:")
        < strategy["text"].index("Tools:")
        < strategy["text"].index("Tactic:")
        < strategy["text"].index("How-To:")
    )
    for tool in (
        "Example OSS Tool",
        "Example Open Weight Tool (Model Terms; open-weight)",
        "Example Commercial Tool",
    ):
        assert tool in control["text"]
        assert tool in strategy["text"]


def _embedding_model(max_length):
    tokenizer = Tokenizer(models.WordLevel({"[UNK]": 0}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.enable_truncation(max_length=max_length)
    return SimpleNamespace(model=SimpleNamespace(tokenizer=tokenizer))


def test_tool_visibility_audit_uses_exact_text_and_allows_metadata_fallback():
    document = extract_documents_from_tactic(_tactic())[0]

    assert _validate_tool_token_visibility([document], _embedding_model(200)) > 0

    missing = deepcopy(document)
    missing["text"] = missing["text"].replace("Example Commercial Tool", "Removed")
    with pytest.raises(ValueError, match="exact tool inventory is absent"):
        _validate_tool_token_visibility([missing], _embedding_model(200))

    assert _validate_tool_token_visibility([document], _embedding_model(5)) > 5


def test_scope_visibility_audit_allows_exact_metadata_fallback():
    document = extract_documents_from_tactic(_tactic())[0]

    assert _validate_scope_boundary_token_visibility(
        [document], _embedding_model(5)
    ) > 5

    missing = deepcopy(document)
    missing["text"] = missing["text"].replace(
        "Own this exact control boundary.",
        "Removed",
    )
    with pytest.raises(ValueError, match="scopeBoundary responsibility is absent"):
        _validate_scope_boundary_token_visibility([missing], _embedding_model(200))
