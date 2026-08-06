"""Unit contracts for the permanent source-to-index release gate."""

import math

import pytest

from app.config import settings
from scripts.verify_index_manifest import (
    FRAMEWORK_PUBLIC_DATA_FILENAME,
    FRAMEWORK_PUBLIC_DATA_SOURCE_PATH,
    MANIFEST_FIELDS,
    ManifestVerificationError,
    _compare_manifests,
    _expected_framework_public_schema_version,
    _expected_framework_version,
    _framework_source_files,
    _records_by_id,
    _validate_storage_encodings,
    _validate_vectors,
    framework_public_data_staged_filename,
)


def test_unknown_framework_version_matches_sync_metadata_fallback(monkeypatch):
    monkeypatch.setattr(
        "scripts.verify_index_manifest.extract_framework_version",
        lambda _path: None,
    )

    assert _expected_framework_version(settings.RAW_PATH / "unused-intro.js") == "unknown"


def test_local_verifier_discovers_future_public_schema_from_framework_root(tmp_path, monkeypatch):
    public_data = tmp_path / "data" / "data.json"
    public_data.parent.mkdir()
    public_data.write_text(
        '{"version":{"schemaVersion":"2.4"},"tactics":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", tmp_path)

    assert (
        _expected_framework_public_schema_version(
            current_source_revision="a" * 40,
        )
        == "2.4"
    )


def test_github_verifier_reads_bounded_staged_public_dataset(tmp_path, monkeypatch):
    revision = "a" * 40
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    (raw_root / framework_public_data_staged_filename(revision)).write_text(
        '{"version":{"schemaVersion":"2.4"},"tactics":[]}',
        encoding="utf-8",
    )
    unrelated_local_root = tmp_path / "framework"
    (unrelated_local_root / "data").mkdir(parents=True)
    (unrelated_local_root / "data" / "data.json").write_text(
        '{"version":{"schemaVersion":"9.9"}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", raw_root)

    assert (
        _expected_framework_public_schema_version(
            current_source_revision=revision,
        )
        == "2.4"
    )


def test_github_verifier_rejects_staged_evidence_from_wrong_revision(tmp_path, monkeypatch):
    expected_revision = "a" * 40
    wrong_revision = "b" * 40
    (tmp_path / framework_public_data_staged_filename(wrong_revision)).write_text(
        '{"version":{"schemaVersion":"9.9"},"tactics":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)

    assert (
        _expected_framework_public_schema_version(
            current_source_revision=expected_revision,
        )
        == "unknown"
    )


def test_verifier_fails_closed_without_public_dataset_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)

    assert (
        _expected_framework_public_schema_version(
            current_source_revision="a" * 40,
        )
        == "unknown"
    )


def test_public_dataset_is_not_indexed_or_added_to_source_content_digest():
    source_files = _framework_source_files(
        ["model.js"],
        include_framework_migrations=True,
    )

    assert FRAMEWORK_PUBLIC_DATA_SOURCE_PATH not in source_files
    assert FRAMEWORK_PUBLIC_DATA_FILENAME not in source_files
    assert framework_public_data_staged_filename("a" * 40) not in source_files


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
