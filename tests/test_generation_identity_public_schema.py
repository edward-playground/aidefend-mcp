"""Generation identity contracts for Framework Public Schema metadata."""

from app.generation_identity import (
    GENERATION_ID_FIELD,
    bind_version_generation,
    generation_fingerprint,
)

SOURCE_REVISION = "e10c1678ee49f03f8fb0c97d446ba3fbc3543655"

VERSION_INFO = {
    "commit_sha": SOURCE_REVISION,
    "generation_build_id": "a" * 64,
    "framework_version": "1.20260805",
    "framework_public_schema_version": "2.3",
    "framework_public_schema_source": "data/data.json",
    "framework_migrations_schema_version": "1.0",
    "framework_migrations_registry_version": "2026-08-05",
    "framework_migrations_sha256": "b" * 64,
    "total_documents": 1208,
    "total_actionable_items": 1151,
    "embedding_model": "BAAI/bge-base-en-v1.5",
    "embedding_dimension": 768,
    "index_schema_version": "3.3",
    "source_kind": "github",
    "source_revision_kind": "git_commit_sha",
    "source_revision": SOURCE_REVISION,
    "source_repository": "edward-playground/aidefense-framework",
    "source_ref": SOURCE_REVISION,
    "source_content_sha256": "c" * 64,
    "source_files": ["main.js", "tactics/detect.js"],
}


def test_generation_identity_binds_public_schema_version():
    bound = bind_version_generation(VERSION_INFO)
    fingerprint = generation_fingerprint(bound)

    assert fingerprint["framework_public_schema_version"] == "2.3"
    assert fingerprint["framework_public_schema_source"] == "data/data.json"

    changed = {**VERSION_INFO, "framework_public_schema_version": "2.4"}
    assert (
        bind_version_generation(changed)[GENERATION_ID_FIELD]
        != bound[GENERATION_ID_FIELD]
    )


def test_generation_identity_binds_public_schema_source():
    bound = bind_version_generation(VERSION_INFO)
    without_source = dict(VERSION_INFO)
    without_source.pop("framework_public_schema_source")
    changed_source = {
        **VERSION_INFO,
        "framework_public_schema_source": "different/source.json",
    }

    assert (
        bind_version_generation(without_source)[GENERATION_ID_FIELD]
        != bound[GENERATION_ID_FIELD]
    )
    assert (
        bind_version_generation(changed_source)[GENERATION_ID_FIELD]
        != bound[GENERATION_ID_FIELD]
    )
