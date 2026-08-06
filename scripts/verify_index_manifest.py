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
from app.framework_utils import framework_labels_from_registry
from app.sync import (
    FRAMEWORK_MANIFEST_FILENAME,
    FRAMEWORK_MIGRATIONS_FILENAME,
    FRAMEWORK_MIGRATIONS_SOURCE_PATH,
    FRAMEWORK_PUBLIC_DATA_FILENAME,
    FRAMEWORK_PUBLIC_DATA_SOURCE_PATH,
    UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
    _compute_staged_framework_digest,
    _framework_source_files,
    _staged_framework_filename,
    compute_framework_migrations_sha256,
    extract_documents_from_tactic,
    extract_framework_public_schema_version,
    extract_framework_version,
    framework_public_data_staged_filename,
    parse_staged_tactic_manifest,
    parse_tactic_file,
    uses_legacy_framework_contract,
    load_and_validate_framework_migrations,
    validate_framework_migrations_corpus_contract,
    validate_tactic_contract,
    acquire_service_instance_lock,
    release_service_instance_lock,
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


def _expected_framework_public_schema_version(
    *,
    current_source_revision: str,
) -> str:
    """Discover the public schema from the same source snapshot as runtime sync.

    Local verification intentionally reads the mutable framework working tree.
    GitHub verification reads the bounded staged copy that runtime obtained from
    the immutable commit recorded in version metadata.  A transient same-revision
    fallback remains independently verifiable because runtime retains only the
    previously validated staged copy for that unchanged immutable revision.
    """
    if settings.LOCAL_FRAMEWORK_PATH is not None:
        source_root = settings.LOCAL_FRAMEWORK_PATH
        public_data_path = source_root / Path(FRAMEWORK_PUBLIC_DATA_SOURCE_PATH)
    else:
        source_root = settings.RAW_PATH
        public_data_path = source_root / framework_public_data_staged_filename(
            current_source_revision
        )
    return extract_framework_public_schema_version(
        public_data_path,
        base_dir=source_root,
    )


def _metadata_differences(
    expected: Dict[str, Any],
    actual: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Compare the manifest fields derived from the staged source."""
    return {
        key: {"expected": expected_value, "actual": actual.get(key)}
        for key, expected_value in expected.items()
        if actual.get(key) != expected_value
    }

def verify() -> Dict[str, Any]:
    manifest_path = settings.RAW_PATH / FRAMEWORK_MANIFEST_FILENAME
    migration_path = settings.RAW_PATH / FRAMEWORK_MIGRATIONS_FILENAME
    try:
        tactic_files = parse_staged_tactic_manifest(manifest_path)
        source_files = _framework_source_files(
            tactic_files,
            include_framework_migrations=migration_path.is_file(),
        )
    except Exception as exc:
        raise ManifestVerificationError(f"Staged framework manifest is invalid: {exc}") from exc

    staged_files = [settings.RAW_PATH / _staged_framework_filename(name) for name in source_files]
    missing_staged = [str(path) for path in staged_files if not path.is_file()]
    if missing_staged:
        raise ManifestVerificationError(
            "Staged framework source is incomplete: " + ", ".join(missing_staged)
        )

    version_info = load_version_info()
    if not version_info:
        raise ManifestVerificationError("Version metadata is missing")
    try:
        framework_migrations = load_and_validate_framework_migrations(
            migration_path if migration_path.is_file() else None
        )
        framework_migrations_sha256 = (
            compute_framework_migrations_sha256(migration_path)
            if framework_migrations is not None
            else None
        )
    except Exception as exc:
        raise ManifestVerificationError(
            f"Staged framework migration registry is invalid: {exc}"
        ) from exc
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
    framework_public_schema_version = _expected_framework_public_schema_version(
        current_source_revision=expected_source_revision,
    )
    legacy_contract = uses_legacy_framework_contract(
        source_kind=expected_source_kind,
        source_repository=expected_source_repository,
        source_revision=expected_source_revision,
        source_content_sha256=expected_sha256,
        framework_version=framework_version,
    )

    expected_documents = []
    parsed_tactics = []
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
        parsed_tactics.append(tactic)
        expected_documents.extend(extract_documents_from_tactic(tactic))

    try:
        validate_framework_migrations_corpus_contract(
            framework_migrations,
            parsed_tactics,
        )
    except Exception as exc:
        raise ManifestVerificationError(
            f"Framework migration registry and staged corpus disagree: {exc}"
        ) from exc

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
        "framework_public_schema_version": framework_public_schema_version,
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
    if framework_public_schema_version != UNKNOWN_FRAMEWORK_SCHEMA_VERSION:
        metadata_contract["framework_public_schema_source"] = FRAMEWORK_PUBLIC_DATA_SOURCE_PATH
    elif (
        framework_public_schema_version == UNKNOWN_FRAMEWORK_SCHEMA_VERSION
        and "framework_public_schema_source" in version_info
    ):
        raise ManifestVerificationError(
            "Version metadata binds a public-schema source without a valid public " "schema version"
        )
    migration_metadata_keys = (
        "framework_migrations",
        "framework_migrations_schema_version",
        "framework_migrations_registry_version",
        "framework_migrations_sha256",
    )
    if framework_migrations is not None:
        metadata_contract.update(
            {
                "framework_migrations": framework_migrations,
                "framework_migrations_schema_version": framework_migrations["schemaVersion"],
                "framework_migrations_registry_version": framework_migrations["registryVersion"],
                "framework_migrations_sha256": framework_migrations_sha256,
            }
        )
    elif any(key in version_info for key in migration_metadata_keys):
        raise ManifestVerificationError(
            "Version metadata contains a migration registry that is absent from staged source"
        )
    metadata_differences = _metadata_differences(metadata_contract, version_info)
    if metadata_differences:
        raise ManifestVerificationError(
            "Version/provenance metadata differs from the staged source:\n"
            + json.dumps(metadata_differences, ensure_ascii=False, indent=2, default=str)
        )

    expected_framework_labels = framework_labels_from_registry(framework_migrations)
    stored_framework_metrics = (
        version_info.get("statistics", {})
        .get("threat_framework_coverage", {})
        .get("by_framework", {})
    )
    label_differences = {
        key: {
            "expected": expected_label,
            "actual": (
                stored_framework_metrics.get(key, {}).get("label")
                if isinstance(stored_framework_metrics.get(key), dict)
                else None
            ),
        }
        for key, expected_label in expected_framework_labels.items()
        if not isinstance(stored_framework_metrics.get(key), dict)
        or stored_framework_metrics[key].get("label") != expected_label
    }
    if label_differences:
        raise ManifestVerificationError(
            "Pre-computed framework metric labels differ from the atomically "
            "activated migration registry:\n"
            + json.dumps(label_differences, ensure_ascii=False, indent=2)
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

    summary = {
        "framework_version": framework_version,
        "framework_public_schema_version": framework_public_schema_version,
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
    if framework_migrations is not None:
        summary.update(
            {
                "framework_migrations_schema_version": framework_migrations["schemaVersion"],
                "framework_migrations_registry_version": framework_migrations["registryVersion"],
                "framework_migrations_sha256": framework_migrations_sha256,
            }
        )
    return summary


def main() -> int:
    if not acquire_service_instance_lock():
        print(
            "MANIFEST VERIFICATION FAILED: another AIDEFEND service owns DATA_PATH",
            file=sys.stderr,
        )
        return 1
    try:
        try:
            summary = verify()
        except Exception as exc:
            print(f"MANIFEST VERIFICATION FAILED: {exc}", file=sys.stderr)
            return 1
    finally:
        release_service_instance_lock()
    print("PASS: staged AIDEFEND source exactly matches the active index")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
