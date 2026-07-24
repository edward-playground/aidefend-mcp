"""Unit contracts for the permanent source-to-index release gate."""

import hashlib
import math

import pytest

from app.config import settings
from scripts.verify_index_manifest import (
    MANIFEST_FIELDS,
    ManifestVerificationError,
    _compare_manifests,
    _expected_framework_schema_metadata,
    _expected_framework_version,
    _records_by_id,
    _validate_storage_encodings,
    _validate_vectors,
)


def test_unknown_framework_version_matches_sync_metadata_fallback(monkeypatch):
    monkeypatch.setattr(
        "scripts.verify_index_manifest.extract_framework_version",
        lambda _path: None,
    )

    assert _expected_framework_version(settings.RAW_PATH / "unused-intro.js") == "unknown"


def test_local_verifier_discovers_future_schema_versions_from_framework_root(
    tmp_path, monkeypatch
):
    (tmp_path / "data-schema.md").write_text(
        "> **Version**: 1.8\n"
        '    schemaVersion: "2.4",\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", tmp_path)

    authoring, public, digest = _expected_framework_schema_metadata(
        {
            "source_revision": "a" * 40,
            "framework_authoring_schema_version": "1.7",
            "framework_public_schema_version": "2.3",
        },
        current_source_revision="b" * 40,
    )

    assert (authoring, public) == ("1.8", "2.4")
    assert digest == hashlib.sha256((tmp_path / "data-schema.md").read_bytes()).hexdigest()


def _record(source_id="AID-H-001"):
    return {
        "text": "Technique: Test",
        "source_id": source_id,
        "tactic": "Harden",
        "type": "technique",
        "name": "Test",
        "pillar": "",
        "phase": "",
        "defends_against": [],
        "tools_opensource": [],
        "tools_source_available": [],
        "tools_commercial": [],
        "parent_technique_id": "",
        "implementation_guidance": [],
        "guidance_id": "",
        "scope_boundary": {},
        "is_actionable": True,
        "is_parent_family": False,
        "has_code_snippets": False,
        "warnings": [],
    }


def test_manifest_normalizes_storage_encodings_and_rejects_duplicate_ids():
    expected = _records_by_id([_record()], label="test")
    stored = _record()
    stored["pillar"] = "[]"
    stored["scope_boundary"] = "{}"
    actual = _records_by_id([stored], label="test")

    _compare_manifests(expected, actual)
    assert set(expected["AID-H-001"]) == set(MANIFEST_FIELDS)

    with pytest.raises(ManifestVerificationError, match="duplicate"):
        _records_by_id([_record(), _record()], label="test")


def test_manifest_comparison_reports_field_drift():
    expected = _records_by_id([_record()], label="source")
    changed = _record()
    changed["name"] = "Wrong title"
    actual = _records_by_id([changed], label="index")

    with pytest.raises(ManifestVerificationError, match="field values"):
        _compare_manifests(expected, actual)


def test_vector_contract_rejects_wrong_dimensions_and_non_finite_values():
    good = {
        "source_id": "AID-H-001",
        "vector": [0.0] * settings.EMBEDDING_DIMENSION,
    }
    _validate_vectors([good])

    with pytest.raises(ManifestVerificationError, match="dimension"):
        _validate_vectors([{"source_id": "AID-H-001", "vector": [0.0]}])

    invalid = dict(good)
    invalid["vector"] = list(good["vector"])
    invalid["vector"][0] = math.nan
    with pytest.raises(ManifestVerificationError, match="non-finite"):
        _validate_vectors([invalid])


def test_storage_contract_rejects_json_encoded_scalars():
    stored = _record()
    for field in (
        "pillar",
        "phase",
        "defends_against",
        "tools_opensource",
        "tools_source_available",
        "tools_commercial",
        "implementation_guidance",
        "warnings",
    ):
        stored[field] = "[]"
    stored["scope_boundary"] = "{}"
    _validate_storage_encodings([stored])

    stored["pillar"] = '""'
    with pytest.raises(ManifestVerificationError, match="not a JSON array"):
        _validate_storage_encodings([stored])
