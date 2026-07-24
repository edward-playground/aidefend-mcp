"""Release-contract tests for the current AIDEFEND framework source."""

import os
import re
import shutil
from collections import Counter
from pathlib import Path

import pytest

from app.config import settings
from app.framework_utils import FRAMEWORK_LABELS
from app.sync import (
    EXPECTED_FRAMEWORK_LABELS,
    _compute_staged_framework_digest,
    extract_documents_from_tactic,
    extract_framework_version,
    parse_tactic_file,
    validate_tactic_contract,
)


EXPECTED_TACTIC_NAMES = {
    "model.js": "Model",
    "harden.js": "Harden",
    "detect.js": "Detect",
    "isolate.js": "Isolate",
    "deceive.js": "Deceive",
    "evict.js": "Evict",
    "restore.js": "Restore",
}


def _framework_root() -> Path:
    candidates = []
    if os.getenv("LOCAL_FRAMEWORK_PATH"):
        candidates.append(Path(os.environ["LOCAL_FRAMEWORK_PATH"]))
    candidates.extend([
        Path(__file__).resolve().parents[2] / "aidefense-framework",
        settings.RAW_PATH.parent.parent,
    ])

    for candidate in candidates:
        tactics = candidate / "tactics"
        if all((tactics / file_name).exists() for file_name in EXPECTED_TACTIC_NAMES):
            return candidate

    # CI stages upstream files directly under RAW_PATH before pytest.
    if all((settings.RAW_PATH / file_name).exists() for file_name in EXPECTED_TACTIC_NAMES):
        return settings.RAW_PATH

    pytest.fail("No complete AIDEFEND framework source is available for the release gate")


def _tactic_path(root: Path, file_name: str) -> Path:
    nested = root / "tactics" / file_name
    return nested if nested.exists() else root / file_name


@pytest.mark.current_snapshot
def test_current_framework_is_fully_parseable_and_contract_valid(tmp_path, monkeypatch):
    root = _framework_root()
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    seen_ids = set()
    seen_guidance_ids = set()
    scope_references = []
    all_documents = []
    guidance_total = 0
    framework_labels = set()
    actionable_total = 0
    parent_total = 0
    tool_category_stats = {
        "toolsOpenSource": {"controls": 0, "entries": 0, "unique": set()},
        "toolsSourceAvailable": {"controls": 0, "entries": 0, "unique": set()},
        "toolsCommercial": {"controls": 0, "entries": 0, "unique": set()},
    }
    scope_boundary_controls = 0

    for file_name in EXPECTED_TACTIC_NAMES:
        staged_path = tmp_path / file_name
        shutil.copyfile(_tactic_path(root, file_name), staged_path)
        tactic = parse_tactic_file(staged_path)
        assert tactic is not None, file_name
        assert validate_tactic_contract(
            tactic,
            file_name,
            seen_ids,
            seen_guidance_ids,
            scope_references,
        ) == []

        for technique in tactic["techniques"]:
            controls = technique.get("subTechniques") or [technique]
            parent_total += int(bool(technique.get("subTechniques")))
            for control in controls:
                actionable_total += 1
                guidance_total += len(control.get("implementationGuidance", []))
                for field, stats in tool_category_stats.items():
                    tools = control.get(field, [])
                    stats["controls"] += int(bool(tools))
                    stats["entries"] += len(tools)
                    stats["unique"].update(tools)
            for control in [technique, *technique.get("subTechniques", [])]:
                scope_boundary_controls += int(bool(control.get("scopeBoundary")))
                framework_labels.update(
                    mapping["framework"] for mapping in control.get("defendsAgainst", [])
                )

        all_documents.extend(extract_documents_from_tactic(tactic))

    document_types = Counter(document["type"] for document in all_documents)
    assert len(seen_ids) == 357
    assert len(seen_guidance_ids) == 851
    assert guidance_total == 851
    assert len(all_documents) == 1208
    assert document_types == {
        "technique": 92,
        "subtechnique": 265,
        "strategy": 851,
    }
    assert actionable_total == 300
    assert parent_total == 57
    assert {
        field: (stats["controls"], stats["entries"], len(stats["unique"]))
        for field, stats in tool_category_stats.items()
    } == {
        "toolsOpenSource": (299, 1781, 627),
        "toolsSourceAvailable": (34, 69, 28),
        "toolsCommercial": (275, 1343, 666),
    }
    assert scope_boundary_controls == 355
    assert len(scope_references) == 751
    assert not {
        target_id
        for _owner_id, target_id in scope_references
        if target_id not in seen_ids
    }
    assert framework_labels == set(EXPECTED_FRAMEWORK_LABELS)
    assert framework_labels == set(FRAMEWORK_LABELS.values())
    assert all(document["source_id"] != "Unknown" for document in all_documents)
    strategy_ids = {
        document["source_id"]
        for document in all_documents
        if document["type"] == "strategy"
    }
    scope_boundary_documents = [
        document for document in all_documents if document["scope_boundary"]
    ]
    assert len(scope_boundary_documents) == 1204
    for document in scope_boundary_documents:
        text = document["text"]
        scope_marker = "\nScope Boundary:"
        assert scope_marker in text, document["source_id"]
        scope_offset = text.index(scope_marker)
        responsibility = document["scope_boundary"]["responsibility"].strip()
        responsibility_end = (
            text.index(responsibility, scope_offset) + len(responsibility)
        )
        # multilingual-e5-base truncates at 512 tokens. For this release the
        # The runtime audit checks this with the exact shipped tokenizer; this
        # cache-independent snapshot guard catches ordering/content drift.
        assert responsibility_end <= 2000, document["source_id"]
        for later_marker in ("\nHow-To:", "\nDefends Against:", "\nWarnings:", "\nTools:"):
            if later_marker in text:
                assert scope_offset < text.index(later_marker), document["source_id"]

    assert strategy_ids == seen_guidance_ids
    assert all(
        re.fullmatch(
            r"AID-(?:M|H|D|I|DV|E|R)-\d{3}(?:\.\d{3})?-G\d{3}",
            guidance_id,
        )
        for guidance_id in strategy_ids
    )


def test_contract_rejects_unknown_tool_prefixed_authoring_field():
    tactic = {
        "name": "Future Governance",
        "purpose": "Synthetic breaking-contract fixture.",
        "techniques": [
            {
                "id": "AID-GOVERNANCE-001",
                "name": "Future Control",
                "description": "A valid control with one unsupported tool category.",
                "pillar": ["governance"],
                "phase": ["validation"],
                "defendsAgainst": [
                    {
                        "framework": "Future Threat Matrix",
                        "items": ["N/A (synthetic compatibility fixture)"],
                    }
                ],
                "implementationGuidance": [],
                "toolsFutureCategory": ["Future Tool"],
            }
        ],
    }

    errors = validate_tactic_contract(tactic, "future-governance.js")

    assert any(
        "unsupported tool field(s): toolsFutureCategory" in error
        for error in errors
    )


@pytest.mark.current_snapshot
def test_current_framework_version_export_is_resolved():
    root = _framework_root()
    intro = root / "aidefend-intro.js"
    if not intro.exists():
        intro = settings.RAW_PATH / "aidefend-intro.js"
    if not intro.exists():
        pytest.fail("aidefend-intro.js is not available for the release gate")

    version = extract_framework_version(intro)
    assert version == "1.20260724"
    assert "Identifier" not in version

    staged_files = [intro]
    staged_files.extend(
        _tactic_path(root, file_name)
        for file_name in settings.AIDEFEND_FILES[1:]
    )
    assert _compute_staged_framework_digest(
        staged_files, algorithm="sha256"
    ) == "f817a4c8dbb9982d9ea6460a0db5d24e680363062e173fc4dd941f52820d751d"


@pytest.mark.current_snapshot
def test_runtime_and_published_documentation_use_current_control_ids_and_json_names(
    tmp_path, monkeypatch
):
    root = _framework_root()
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    current_names = {}

    for file_name in EXPECTED_TACTIC_NAMES:
        staged_path = tmp_path / file_name
        shutil.copyfile(_tactic_path(root, file_name), staged_path)
        tactic = parse_tactic_file(staged_path)
        assert tactic is not None, file_name
        for technique in tactic["techniques"]:
            current_names[technique["id"]] = technique["name"]
            for subtechnique in technique.get("subTechniques", []):
                current_names[subtechnique["id"]] = subtechnique["name"]

    repository_root = Path(__file__).resolve().parents[1]
    published_paths = [
        repository_root / "README.md",
        repository_root / "README-繁體中文.md",
        repository_root / "INSTALL.md",
        repository_root / "INSTALL-繁體中文.md",
        *sorted((repository_root / "docs").rglob("*.md")),
    ]
    runtime_paths = [
        repository_root / "mcp_server.py",
        *sorted((repository_root / "app").rglob("*.py")),
    ]
    control_pattern = re.compile(
        r"AID-(?:M|H|D|I|DV|E|R)-\d{3}(?:\.\d{3})?"
    )
    json_pair_pattern = re.compile(
        r'"(?:id|source_id|technique_id)"\s*:\s*"'
        r"(?P<id>AID-(?:M|H|D|I|DV|E|R)-\d{3}(?:\.\d{3})?)"
        r'"\s*,\s*"name"\s*:\s*"(?P<name>[^"]+)"'
    )
    intentionally_invalid_examples = {"AID-H-999"}
    unknown_references = []
    mismatched_json_names = []

    for path in [*published_paths, *runtime_paths]:
        text = path.read_text(encoding="utf-8")
        for control_id in control_pattern.findall(text):
            if (
                control_id not in current_names
                and control_id not in intentionally_invalid_examples
            ):
                unknown_references.append((path.name, control_id))
        for match in json_pair_pattern.finditer(text):
            control_id = match.group("id")
            if (
                control_id in current_names
                and match.group("name") != current_names[control_id]
            ):
                mismatched_json_names.append(
                    (
                        path.name,
                        control_id,
                        match.group("name"),
                        current_names[control_id],
                    )
                )

    assert unknown_references == []
    assert mismatched_json_names == []


def test_warning_is_inherited_and_preserved_in_search_documents():
    warning = {
        "level": "High operational impact",
        "description": "<p>Validate rollback before deployment.</p>",
    }
    guidance = [{
        "id": "AID-M-999.001-G001",
        "implementation": "Test",
        "howTo": "<p>Apply safely.</p>",
    }]
    tactic = {
        "name": "Model",
        "techniques": [{
            "id": "AID-M-999",
            "name": "Warning Test",
            "description": "Parent warning test.",
            "defendsAgainst": [{"framework": "MITRE ATLAS", "items": ["AML.T0000"]}],
            "warning": warning,
            "subTechniques": [
                {
                    "id": "AID-M-999.001",
                    "name": "First",
                    "description": "First child.",
                    "pillar": ["model"],
                    "phase": ["validation"],
                    "implementationGuidance": guidance,
                },
                {
                    "id": "AID-M-999.002",
                    "name": "Second",
                    "description": "Second child.",
                    "pillar": ["model"],
                    "phase": ["validation"],
                    "implementationGuidance": [{
                        "id": "AID-M-999.002-G001",
                        "implementation": "Test",
                        "howTo": "<p>Apply safely.</p>",
                    }],
                },
            ],
        }],
    }

    documents = extract_documents_from_tactic(tactic)
    child = next(doc for doc in documents if doc["source_id"] == "AID-M-999.001")
    strategy = next(
        doc for doc in documents
        if doc["source_id"] == "AID-M-999.001-G001"
    )
    assert child["warnings"] == [warning]
    assert strategy["warnings"] == [warning]
    assert strategy["guidance_id"] == "AID-M-999.001-G001"
    assert "Validate rollback before deployment" in child["text"]
