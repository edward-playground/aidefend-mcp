"""Rolling compatibility gates for future AIDEFEND framework content.

These tests deliberately derive every count, identifier, title, and tool value
from the source under test. Exact release-candidate assertions live behind the
``current_snapshot`` marker in ``test_current_framework_contract.py``.
"""

import os
import re
import shutil
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from app.config import settings
from app.framework_manifest import parse_tactic_manifest
from app.sync import (
    _compute_staged_framework_digest,
    _framework_source_files,
    extract_documents_from_tactic,
    extract_framework_version,
    parse_tactic_file,
    validate_tactic_contract,
)


def _framework_root() -> Path:
    candidates = []
    if os.getenv("LOCAL_FRAMEWORK_PATH"):
        candidates.append(Path(os.environ["LOCAL_FRAMEWORK_PATH"]))
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "aidefense-framework",
            settings.RAW_PATH.parent.parent,
        ]
    )
    candidates.append(settings.RAW_PATH)
    for candidate in candidates:
        manifest = candidate / "main.js"
        if not manifest.is_file():
            continue
        try:
            tactic_files = parse_tactic_manifest(
                manifest.read_text(encoding="utf-8-sig"),
                tactics_path=settings.GITHUB_TACTICS_PATH,
            )
        except Exception:
            continue
        if all(
            (candidate / "tactics" / file_name).is_file() or (candidate / file_name).is_file()
            for file_name in tactic_files
        ):
            return candidate
    pytest.fail("No complete AIDEFEND framework source is available for the rolling gate")


def _tactic_path(root: Path, file_name: str) -> Path:
    nested = root / "tactics" / file_name
    return nested if nested.exists() else root / file_name


def _tactic_files(root: Path) -> list[str]:
    return parse_tactic_manifest(
        (root / "main.js").read_text(encoding="utf-8-sig"),
        tactics_path=settings.GITHUB_TACTICS_PATH,
    )


def test_framework_source_is_structurally_parseable_without_snapshot_pins(tmp_path, monkeypatch):
    """Check relationships and propagation without fixing mutable corpus values."""
    root = _framework_root()
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    seen_ids: set[str] = set()
    seen_guidance_ids: set[str] = set()
    scope_references: list[tuple[str, str]] = []
    controls_by_id = {}
    documents = []
    top_level_total = 0
    subtechnique_total = 0
    guidance_total = 0
    framework_labels = set()
    tactic_files = _tactic_files(root)

    for file_name in tactic_files:
        staged_path = tmp_path / file_name
        shutil.copyfile(_tactic_path(root, file_name), staged_path)
        tactic = parse_tactic_file(staged_path)
        assert tactic is not None, file_name
        assert (
            validate_tactic_contract(
                tactic,
                file_name,
                seen_ids,
                seen_guidance_ids,
                scope_references,
            )
            == []
        )

        top_level_total += len(tactic["techniques"])
        for technique in tactic["techniques"]:
            controls_by_id[technique["id"]] = technique
            subtechniques = technique.get("subTechniques", [])
            subtechnique_total += len(subtechniques)
            for subtechnique in subtechniques:
                controls_by_id[subtechnique["id"]] = subtechnique
            for control in subtechniques or [technique]:
                guidance_total += len(control.get("implementationGuidance", []))
            for control in [technique, *subtechniques]:
                framework_labels.update(
                    mapping["framework"] for mapping in control.get("defendsAgainst", [])
                )
        documents.extend(extract_documents_from_tactic(tactic))

    document_types = Counter(document["type"] for document in documents)
    assert len(seen_ids) == len(controls_by_id)
    assert len(documents) == len(seen_ids) + len(seen_guidance_ids)
    assert document_types == {
        "technique": top_level_total,
        "subtechnique": subtechnique_total,
        "strategy": len(seen_guidance_ids),
    }
    assert guidance_total == len(seen_guidance_ids)
    assert not {target_id for _owner_id, target_id in scope_references if target_id not in seen_ids}
    assert framework_labels
    assert all(isinstance(label, str) and label.strip() for label in framework_labels)
    assert all(document["source_id"] != "Unknown" for document in documents)

    strategy_ids = {
        document["source_id"] for document in documents if document["type"] == "strategy"
    }
    assert strategy_ids == seen_guidance_ids
    assert all(
        re.fullmatch(
            r"AID-[A-Z][A-Z0-9]*-\d{3}(?:\.\d{3})?-G\d{3}",
            guidance_id,
        )
        for guidance_id in strategy_ids
    )

    # Mutable fields must flow from source records, not positional or ID tables.
    control_documents = {
        document["source_id"]: document
        for document in documents
        if document["type"] in {"technique", "subtechnique"}
    }
    assert set(control_documents) == seen_ids
    for control_id, control in controls_by_id.items():
        document = control_documents[control_id]
        assert document["name"] == control["name"]
        assert document["tools_opensource"] == control.get("toolsOpenSource", [])
        assert document["tools_source_available"] == control.get("toolsSourceAvailable", [])
        assert document["tools_commercial"] == control.get("toolsCommercial", [])
        assert document["scope_boundary"] == (control.get("scopeBoundary") or {})
        if document["scope_boundary"]:
            assert "\nScope Boundary:" in document["text"]
            assert document["scope_boundary"]["responsibility"].strip() in document["text"]


def test_framework_version_and_digest_are_resolved_without_snapshot_pin():
    root = _framework_root()
    intro = root / "aidefend-intro.js"
    if not intro.exists():
        intro = settings.RAW_PATH / "aidefend-intro.js"
    if not intro.exists():
        pytest.fail("aidefend-intro.js is not available for the rolling gate")

    version = extract_framework_version(intro)
    assert version is None or (isinstance(version, str) and version.strip())
    if version is not None:
        assert "Identifier" not in version

    tactic_files = _tactic_files(root)
    source_files = _framework_source_files(tactic_files)
    staged_files = [intro]
    staged_files.extend(_tactic_path(root, file_name) for file_name in tactic_files)
    digest = _compute_staged_framework_digest(
        staged_files,
        algorithm="sha256",
        source_files=source_files,
    )
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert digest == _compute_staged_framework_digest(
        staged_files,
        algorithm="sha256",
        source_files=source_files,
    )


def _synthetic_mappings() -> list[dict]:
    return [
        {"framework": framework, "items": ["N/A (synthetic compatibility fixture)"]}
        for framework in ("Renamed Threat Matrix", "Future Community Framework")
    ]


def _synthetic_control(control_id: str, name: str, description: str) -> dict:
    return {
        "id": control_id,
        "name": name,
        "description": description,
        "pillar": ["model"],
        "phase": ["validation"],
        "defendsAgainst": _synthetic_mappings(),
        "implementationGuidance": [
            {
                "id": f"{control_id}-G001",
                "implementation": f"Implement {name}",
                "howTo": f"<p>Apply the current guidance for {name}.</p>",
            }
        ],
    }


def test_id_title_content_count_order_and_additive_metadata_are_dynamic():
    """Model common future content churn without relying on today's corpus."""
    original = {
        "name": "Governance Next",
        "purpose": "Synthetic compatibility baseline.",
        "techniques": [
            _synthetic_control("AID-M-901", "Original Alpha", "Original alpha content."),
            _synthetic_control("AID-M-902", "Original Beta", "Original beta content."),
        ],
    }
    assert validate_tactic_contract(original, "governance-next.js") == []
    original_documents = extract_documents_from_tactic(original)

    renamed = deepcopy(original["techniques"][0])
    renamed["name"] = "Renamed Alpha"
    renamed["description"] = "Completely revised alpha content for a later release."
    renamed["futureOptionalMetadata"] = {"introducedBy": "future schema"}
    renamed["implementationGuidance"][0]["futureEvidence"] = ["additive", "optional"]
    renamed["scopeBoundary"] = {
        "responsibility": "Alpha owns the first half of this synthetic boundary.",
        "relatedTechniques": [{"id": "AID-M-907", "comparison": "Beta owns the second half."}],
    }

    renumbered = deepcopy(original["techniques"][1])
    renumbered["id"] = "AID-M-907"
    renumbered["name"] = "Shifted Beta"
    renumbered["description"] = "The same concept after a valid ID shift."
    renumbered["implementationGuidance"][0]["id"] = "AID-M-907-G001"
    renumbered["scopeBoundary"] = {
        "responsibility": "Beta owns the second half of this synthetic boundary.",
        "relatedTechniques": [{"id": "AID-M-901", "comparison": "Alpha owns the first half."}],
    }

    added = _synthetic_control(
        "AID-M-903", "New Gamma", "A newly added control in a later release."
    )
    added["toolsSourceAvailable"] = ["Future Tool (Example License; source-available)"]

    future = {
        "name": "Renamed Governance Tactic",
        "purpose": "Synthetic compatibility fixture after content churn.",
        "futureSchemaMetadata": {"revision": 2},
        # New item, shifted ID, changed title/content, and source reordering.
        "techniques": [added, renumbered, renamed],
    }
    seen_ids: set[str] = set()
    seen_guidance_ids: set[str] = set()
    scope_references: list[tuple[str, str]] = []
    assert (
        validate_tactic_contract(
            future,
            "renamed-governance.js",
            seen_ids,
            seen_guidance_ids,
            scope_references,
        )
        == []
    )
    assert {target for _owner, target in scope_references} <= seen_ids

    future_documents = extract_documents_from_tactic(future)
    future_controls = [
        document
        for document in future_documents
        if document["type"] in {"technique", "subtechnique"}
    ]
    assert len(original_documents) == 4
    assert len(future_documents) == 6
    assert [document["source_id"] for document in future_controls] == [
        "AID-M-903",
        "AID-M-907",
        "AID-M-901",
    ]
    assert [document["name"] for document in future_controls] == [
        "New Gamma",
        "Shifted Beta",
        "Renamed Alpha",
    ]
    assert "Completely revised alpha content" in future_controls[2]["text"]
    assert future_controls[0]["tools_source_available"] == [
        "Future Tool (Example License; source-available)"
    ]
    assert future_controls[2]["scope_boundary"] == renamed["scopeBoundary"]


@pytest.mark.parametrize("invalid_name", [None, "", "   ", [], {}])
def test_tactic_name_must_remain_a_non_empty_string(invalid_name):
    tactic = {
        "name": invalid_name,
        "purpose": "Synthetic compatibility fixture.",
        "techniques": [_synthetic_control("AID-GV-901", "Synthetic", "Synthetic content.")],
    }

    errors = validate_tactic_contract(tactic, "future-tactic.js")

    assert "future-tactic.js: name must be a non-empty string" in errors
