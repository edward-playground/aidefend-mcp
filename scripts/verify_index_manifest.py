#!/usr/bin/env python3
"""Fail-closed source-to-index release verification for AIDEFEND.

Run this after synchronization. It compares every non-vector field in the
staged framework source with the live LanceDB table, then validates vector,
version, schema, provenance, and digest contracts.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable

import lancedb

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.config import settings
from app.core import decode_framework_record
from app.sync import (
    FRAMEWORK_MANIFEST_FILENAME,
    FRAMEWORK_SCHEMA_FILENAME,
    _compute_staged_framework_digest,
    _framework_source_files,
    compute_framework_schema_metadata_sha256,
    extract_framework_schema_versions,
    extract_documents_from_tactic,
    extract_framework_version,
    parse_staged_tactic_manifest,
    parse_tactic_file,
    resolve_effective_framework_schema_metadata_sha256,
    resolve_effective_framework_schema_versions,
    uses_legacy_framework_contract,
    validate_tactic_contract,
)
from app.utils import load_version_info

MANIFEST_FIELDS = (
    "text",
    "source_id",
    "tactic",
    "type",
    "name",
    "pillar",
    "phase",
    "defends_against",
    "tools_opensource",
    "tools_source_available",
    "tools_commercial",
    "parent_technique_id",
    "implementation_guidance",
    "guidance_id",
    "scope_boundary",
    "is_actionable",
    "is_parent_family",
    "has_code_snippets",
    "warnings",
)
STORED_LIST_FIELDS = (
    "pillar",
    "phase",
    "defends_against",
    "tools_opensource",
    "tools_source_available",
    "tools_commercial",
    "implementation_guidance",
    "warnings",
)


class ManifestVerificationError(AssertionError):
    """Raised when staged source and the active index differ."""


def _canonical_record(record: Dict[str, Any]) -> Dict[str, Any]:
    decoded = decode_framework_record(record)
    return {field: decoded.get(field) for field in MANIFEST_FIELDS}


def _records_by_id(records: Iterable[Dict[str, Any]], *, label: str) -> Dict[str, Dict[str, Any]]:
    canonical_records = [_canonical_record(record) for record in records]
    ids = [str(record.get("source_id") or "") for record in canonical_records]
    duplicates = sorted(source_id for source_id, count in Counter(ids).items() if count > 1)
    if "" in ids:
        raise ManifestVerificationError(f"{label} contains an empty source_id")
    if duplicates:
        raise ManifestVerificationError(f"{label} contains duplicate source IDs: {duplicates[:20]}")
    return {record["source_id"]: record for record in canonical_records}


def _compare_manifests(
    expected: Dict[str, Dict[str, Any]],
    actual: Dict[str, Dict[str, Any]],
) -> None:
    expected_ids = set(expected)
    actual_ids = set(actual)
    missing = sorted(expected_ids - actual_ids)
    extra = sorted(actual_ids - expected_ids)
    if missing or extra:
        raise ManifestVerificationError(
            "Index ID set differs from staged source: "
            f"missing={missing[:20]}, extra={extra[:20]}"
        )

    differences = []
    for source_id in sorted(expected_ids):
        expected_record = expected[source_id]
        actual_record = actual[source_id]
        for field in MANIFEST_FIELDS:
            if expected_record[field] != actual_record[field]:
                differences.append(
                    {
                        "source_id": source_id,
                        "field": field,
                        "expected": expected_record[field],
                        "actual": actual_record[field],
                    }
                )
                if len(differences) == 20:
                    break
        if len(differences) == 20:
            break
    if differences:
        raise ManifestVerificationError(
            "Index field values differ from staged source:\n"
            + json.dumps(differences, ensure_ascii=False, indent=2, default=str)
        )


def _validate_vectors(records: Iterable[Dict[str, Any]]) -> None:
    for record in records:
        source_id = str(record.get("source_id") or "")
        vector = record.get("vector")
        if vector is None or len(vector) != settings.EMBEDDING_DIMENSION:
            raise ManifestVerificationError(
                f"{source_id}: vector dimension is not " f"{settings.EMBEDDING_DIMENSION}"
            )
        if any(not math.isfinite(float(value)) for value in vector):
            raise ManifestVerificationError(f"{source_id}: vector contains a non-finite value")


def _validate_storage_encodings(records: Iterable[Dict[str, Any]]) -> None:
    """Reject JSON scalar drift hidden by compatibility decoders."""
    for record in records:
        source_id = str(record.get("source_id") or "")
        for field in STORED_LIST_FIELDS:
            raw_value = record.get(field)
            if not isinstance(raw_value, str):
                raise ManifestVerificationError(
                    f"{source_id}.{field}: storage value is not a JSON string"
                )
            try:
                decoded = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise ManifestVerificationError(
                    f"{source_id}.{field}: invalid JSON storage value"
                ) from exc
            if not isinstance(decoded, list):
                raise ManifestVerificationError(
                    f"{source_id}.{field}: storage value is not a JSON array"
                )
        raw_scope_boundary = record.get("scope_boundary")
        if not isinstance(raw_scope_boundary, str):
            raise ManifestVerificationError(
                f"{source_id}.scope_boundary: storage value is not a JSON string"
            )
        try:
            decoded_scope_boundary = json.loads(raw_scope_boundary)
        except json.JSONDecodeError as exc:
            raise ManifestVerificationError(
                f"{source_id}.scope_boundary: invalid JSON storage value"
            ) from exc
        if not isinstance(decoded_scope_boundary, dict):
            raise ManifestVerificationError(
                f"{source_id}.scope_boundary: storage value is not a JSON object"
            )


def _expected_framework_version(intro_path: Path) -> str:
    """Mirror sync's forward-compatible metadata value for version drift."""
    return extract_framework_version(intro_path) or "unknown"


def _expected_framework_schema_metadata(
    version_info: Dict[str, Any],
    *,
    current_source_revision: str,
) -> tuple[str, str, str | None]:
    """Mirror sync's dynamic schema metadata resolution for either source mode."""
    schema_root = settings.LOCAL_FRAMEWORK_PATH or settings.RAW_PATH
    schema_path = schema_root / FRAMEWORK_SCHEMA_FILENAME
    discovered_digest = compute_framework_schema_metadata_sha256(
        schema_path,
        base_dir=schema_root,
    )
    metadata_available = discovered_digest is not None
    discovered_versions = extract_framework_schema_versions(
        schema_path if metadata_available else None,
        base_dir=schema_root,
    )
    source_kind = "local" if settings.LOCAL_FRAMEWORK_PATH else "github"
    authoring_version, public_version = resolve_effective_framework_schema_versions(
        discovered_versions,
        version_info=version_info,
        current_source_revision=current_source_revision,
        source_kind=source_kind,
        metadata_available=metadata_available,
    )
    effective_digest = resolve_effective_framework_schema_metadata_sha256(
        discovered_digest,
        version_info=version_info,
        current_source_revision=current_source_revision,
        source_kind=source_kind,
        metadata_available=metadata_available,
    )
    return authoring_version, public_version, effective_digest


def _expected_framework_schema_versions(
    version_info: Dict[str, Any],
    *,
    current_source_revision: str,
) -> tuple[str, str]:
    """Compatibility wrapper for focused version-only verifier tests."""
    authoring, public, _digest = _expected_framework_schema_metadata(
        version_info,
        current_source_revision=current_source_revision,
    )
    return authoring, public


def verify() -> Dict[str, Any]:
    manifest_path = settings.RAW_PATH / FRAMEWORK_MANIFEST_FILENAME
    try:
        tactic_files = parse_staged_tactic_manifest(manifest_path)
        source_files = _framework_source_files(tactic_files)
    except Exception as exc:
        raise ManifestVerificationError(f"Staged framework manifest is invalid: {exc}") from exc

    staged_files = [settings.RAW_PATH / name for name in source_files]
    missing_staged = [str(path) for path in staged_files if not path.is_file()]
    if missing_staged:
        raise ManifestVerificationError(
            "Staged framework source is incomplete: " + ", ".join(missing_staged)
        )

    version_info = load_version_info()
    if not version_info:
        raise ManifestVerificationError("Version metadata is missing")
    framework_version = _expected_framework_version(settings.RAW_PATH / "aidefend-intro.js")
    expected_sha256 = _compute_staged_framework_digest(
        staged_files,
        algorithm="sha256",
        source_files=source_files,
    )
    expected_source_kind = "local" if settings.LOCAL_FRAMEWORK_PATH else "github"
    expected_revision_kind = (
        "local_content_sha1" if settings.LOCAL_FRAMEWORK_PATH else "git_commit_sha"
    )
    expected_source_repository = (
        "local-working-tree" if settings.LOCAL_FRAMEWORK_PATH else settings.github_repo_path
    )
    expected_source_ref = (
        "working-tree" if settings.LOCAL_FRAMEWORK_PATH else settings.GITHUB_BRANCH
    )
    if expected_source_kind == "local":
        expected_source_revision = _compute_staged_framework_digest(
            staged_files,
            algorithm="sha1",
            source_files=source_files,
        )
    else:
        # The staged GitHub files are pinned by this revision in version metadata;
        # immutable raw source does not otherwise encode its commit in the files.
        expected_source_revision = str(
            version_info.get("source_revision") or version_info.get("commit_sha") or ""
        )
    (
        framework_authoring_schema_version,
        framework_public_schema_version,
        framework_schema_metadata_sha256,
    ) = _expected_framework_schema_metadata(
        version_info=version_info,
        current_source_revision=expected_source_revision,
    )
    schema_root = settings.LOCAL_FRAMEWORK_PATH or settings.RAW_PATH
    schema_metadata_available = (
        compute_framework_schema_metadata_sha256(
            schema_root / FRAMEWORK_SCHEMA_FILENAME,
            base_dir=schema_root,
        )
        is not None
    )
    legacy_contract = uses_legacy_framework_contract(
        source_kind=expected_source_kind,
        source_repository=expected_source_repository,
        source_revision=expected_source_revision,
        source_content_sha256=expected_sha256,
        framework_version=framework_version,
        schema_metadata_available=schema_metadata_available,
        framework_authoring_schema_version=framework_authoring_schema_version,
        framework_public_schema_version=framework_public_schema_version,
    )

    expected_documents = []
    seen_control_ids: set[str] = set()
    seen_guidance_ids: set[str] = set()
    scope_references: list[tuple[str, str]] = []
    for file_name in tactic_files:
        tactic = parse_tactic_file(settings.RAW_PATH / file_name)
        if tactic is None:
            raise ManifestVerificationError(f"Could not parse staged framework file: {file_name}")
        contract_errors = validate_tactic_contract(
            tactic,
            file_name,
            seen_control_ids,
            seen_guidance_ids,
            scope_references,
            legacy_contract=legacy_contract,
        )
        if contract_errors:
            raise ManifestVerificationError(
                f"Staged framework contract failed for {file_name}: "
                + "; ".join(contract_errors[:20])
            )
        expected_documents.extend(extract_documents_from_tactic(tactic))

    missing_scope_targets = sorted(
        (owner_id, target_id)
        for owner_id, target_id in scope_references
        if target_id not in seen_control_ids
    )
    if missing_scope_targets:
        raise ManifestVerificationError(
            f"Staged framework has missing scopeBoundary targets: {missing_scope_targets[:20]}"
        )

    if not settings.DB_PATH.is_dir():
        raise ManifestVerificationError(f"LanceDB directory does not exist: {settings.DB_PATH}")
    database = lancedb.connect(str(settings.DB_PATH))
    table_names = set(database.table_names())
    if table_names != {"aidefend"}:
        raise ManifestVerificationError(
            f"Unexpected LanceDB tables (temporary/old swap residue): {sorted(table_names)}"
        )
    table = database.open_table("aidefend")
    actual_records = table.to_pandas().to_dict("records")
    if table.count_rows() != len(actual_records):
        raise ManifestVerificationError("LanceDB row count differs from its full-table scan")

    _validate_storage_encodings(actual_records)
    expected = _records_by_id(expected_documents, label="staged source")
    actual = _records_by_id(actual_records, label="LanceDB index")
    _compare_manifests(expected, actual)
    _validate_vectors(actual_records)

    metadata_contract = {
        "framework_version": framework_version,
        "framework_authoring_schema_version": framework_authoring_schema_version,
        "framework_public_schema_version": framework_public_schema_version,
        "framework_schema_metadata_sha256": framework_schema_metadata_sha256,
        "index_schema_version": settings.CACHE_SCHEMA_VERSION,
        "total_documents": len(expected_documents),
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimension": settings.EMBEDDING_DIMENSION,
        "source_kind": expected_source_kind,
        "source_revision_kind": expected_revision_kind,
        "source_repository": expected_source_repository,
        "source_ref": expected_source_ref,
        "source_content_sha256": expected_sha256,
        "source_files": source_files,
    }
    metadata_differences = {
        key: {"expected": expected_value, "actual": version_info.get(key)}
        for key, expected_value in metadata_contract.items()
        if version_info.get(key) != expected_value
    }
    if metadata_differences:
        raise ManifestVerificationError(
            "Version/provenance metadata differs from the staged source:\n"
            + json.dumps(metadata_differences, ensure_ascii=False, indent=2, default=str)
        )
    source_revision = str(version_info.get("source_revision") or "")
    if expected_source_kind == "local":
        if source_revision != expected_source_revision:
            raise ManifestVerificationError(
                "Local source revision does not match canonical staged bytes"
            )
    elif not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ManifestVerificationError(
            "GitHub source revision is not an immutable 40-character commit SHA"
        )

    return {
        "framework_version": framework_version,
        "framework_authoring_schema_version": framework_authoring_schema_version,
        "framework_public_schema_version": framework_public_schema_version,
        "framework_schema_metadata_sha256": framework_schema_metadata_sha256,
        "documents": len(expected_documents),
        "controls": sum(
            document["type"] in {"technique", "subtechnique"} for document in expected_documents
        ),
        "guidance": sum(document["type"] == "strategy" for document in expected_documents),
        "scope_boundary_documents": sum(
            bool(document["scope_boundary"]) for document in expected_documents
        ),
        "source_kind": expected_source_kind,
        "source_content_sha256": expected_sha256,
        "index_schema_version": settings.CACHE_SCHEMA_VERSION,
        "vector_dimension": settings.EMBEDDING_DIMENSION,
    }


def main() -> int:
    try:
        summary = verify()
    except Exception as exc:
        print(f"MANIFEST VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 1
    print("PASS: staged AIDEFEND source exactly matches the active index")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
