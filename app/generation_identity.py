"""Cryptographic binding between a LanceDB table and its version metadata.

The database directory and ``local_version.json`` are two separately replaced
filesystem objects.  A writer lock prevents in-process readers from crossing a
swap, but it cannot prove that the two objects still belong to the same
generation after process death.  Every current table therefore stores one
generation identifier in every row.  The identifier is derived from the
version/provenance fields that define the indexed corpus and is also persisted
in the atomic version snapshot.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Mapping, Optional

GENERATION_ID_FIELD = "generation_id"
GENERATION_BUILD_ID_FIELD = "generation_build_id"
GENERATION_ID_PATTERN = re.compile(r"[0-9a-f]{64}")

# Timestamps and derived statistics deliberately do not participate: a no-op
# freshness update must not change the identity of an unchanged table.
# ``framework_public_schema_version`` is intentionally not legacy; it remains
# part of every new fingerprint whenever public-schema discovery supplies it.
# Its internal source marker is likewise optional for old snapshots but bound
# into every new fingerprint that records how the public version was proven.
GENERATION_FINGERPRINT_FIELDS = (
    "commit_sha",
    GENERATION_BUILD_ID_FIELD,
    "framework_version",
    "framework_public_schema_version",
    "framework_public_schema_source",
    "framework_migrations_schema_version",
    "framework_migrations_registry_version",
    "framework_migrations_sha256",
    "total_documents",
    "total_actionable_items",
    "embedding_model",
    "embedding_dimension",
    "index_schema_version",
    "source_kind",
    "source_revision_kind",
    "source_revision",
    "source_repository",
    "source_ref",
    "source_content_sha256",
    "source_files",
)

CURRENT_GENERATION_REQUIRED_FIELDS = frozenset(
    {
        "commit_sha",
        GENERATION_BUILD_ID_FIELD,
        "framework_version",
        "total_documents",
        "index_schema_version",
        "source_kind",
        "source_revision",
        "source_content_sha256",
    }
)

# Old public installations predate source-provenance metadata.  These fields
# are the minimum trustworthy baseline needed to bind such an existing table
# during its one-time 3.2 -> 3.3 upgrade.
LEGACY_GENERATION_REQUIRED_FIELDS = frozenset(
    {
        "commit_sha",
        "framework_version",
        "total_documents",
        "embedding_model",
        "embedding_dimension",
        "index_schema_version",
    }
)


class GenerationIdentityError(RuntimeError):
    """Raised when table bytes and version metadata cannot be proven paired."""


def generation_fingerprint(version_info: Mapping[str, Any]) -> Dict[str, Any]:
    """Project metadata onto the stable fields that identify one generation.

    Projection is deliberately presence-sensitive: absent fields are not
    synthesized for a newly built generation.
    """
    return {
        field: version_info[field]
        for field in GENERATION_FINGERPRINT_FIELDS
        if field in version_info
    }


def generation_id(fingerprint: Mapping[str, Any]) -> str:
    """Return the canonical SHA-256 identifier for a generation fingerprint."""
    payload = json.dumps(
        dict(fingerprint),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def bind_version_generation(
    version_info: Mapping[str, Any],
    *,
    allow_legacy: bool = False,
) -> Dict[str, Any]:
    """Validate metadata and return a copy containing its generation ID.

    ``allow_legacy`` is intentionally narrow.  It permits a one-time binding of
    an existing pre-3.3 index only when enough historical metadata is present;
    it never permits an unbound table to serve as a rollback candidate.
    """
    if not isinstance(version_info, Mapping):
        raise GenerationIdentityError("Version metadata is missing or invalid")

    fingerprint = generation_fingerprint(version_info)
    required = (
        LEGACY_GENERATION_REQUIRED_FIELDS if allow_legacy else CURRENT_GENERATION_REQUIRED_FIELDS
    )
    missing = sorted(
        field for field in required if field not in fingerprint or fingerprint[field] in (None, "")
    )
    if missing:
        raise GenerationIdentityError("Generation metadata is incomplete: " + ", ".join(missing))

    build_id = fingerprint.get(GENERATION_BUILD_ID_FIELD)
    if build_id is not None and (
        not isinstance(build_id, str) or GENERATION_ID_PATTERN.fullmatch(build_id) is None
    ):
        raise GenerationIdentityError("Generation build ID is invalid")

    computed = generation_id(fingerprint)
    declared = version_info.get(GENERATION_ID_FIELD)
    if declared is not None and (
        not isinstance(declared, str)
        or GENERATION_ID_PATTERN.fullmatch(declared) is None
        or declared != computed
    ):
        raise GenerationIdentityError(
            "Version metadata generation_id does not match its fingerprint"
        )

    bound = dict(version_info)
    bound[GENERATION_ID_FIELD] = computed
    return bound


def assert_table_generation(
    table: Any,
    version_info: Mapping[str, Any],
    *,
    allow_legacy_unbound: bool = False,
) -> Optional[str]:
    """Prove that all table rows have the ID derived from ``version_info``.

    Returns the verified ID.  ``None`` is returned only for a pre-3.3 table and
    only when explicitly allowed for read compatibility.  A table that already
    has an ID is always checked, even if the version snapshot has not yet been
    augmented after a process interruption.
    """
    bound_version = bind_version_generation(version_info, allow_legacy=True)
    expected = bound_version[GENERATION_ID_FIELD]
    schema_names = set(getattr(table.schema, "names", ()))

    if GENERATION_ID_FIELD not in schema_names:
        if allow_legacy_unbound and GENERATION_ID_FIELD not in version_info:
            return None
        raise GenerationIdentityError("LanceDB table does not contain a persisted generation_id")

    total_rows = table.count_rows()
    if not isinstance(total_rows, int) or total_rows < 1:
        raise GenerationIdentityError(
            "LanceDB table generation identity cannot be verified on an empty table"
        )
    declared_rows = version_info.get("total_documents")
    if (
        not isinstance(declared_rows, int)
        or isinstance(declared_rows, bool)
        or declared_rows < 1
        or declared_rows != total_rows
    ):
        raise GenerationIdentityError("LanceDB table row count does not match generation metadata")
    matching_rows = table.count_rows(f"{GENERATION_ID_FIELD} = '{expected}'")
    if matching_rows != total_rows:
        raise GenerationIdentityError(
            "LanceDB table contains a missing, mixed, or mismatched generation_id"
        )
    return expected
