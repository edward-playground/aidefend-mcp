"""Forward-compatible runtime discovery for framework schema metadata."""

import hashlib
from pathlib import Path

import pytest

import app.sync as sync_module
from app.config import settings


FUTURE_SCHEMA = """\
# AIDEFEND Data Schema Documentation

> **Version**: 1.8

```javascript
{
  version: {
    schemaVersion: "2.4",
  },
}
```
"""


def _extract(path: Path, root: Path) -> tuple[str, str]:
    return sync_module.extract_framework_schema_versions(path, base_dir=root)


def test_future_authoring_and_public_schema_versions_are_discovered(tmp_path):
    schema_path = tmp_path / sync_module.FRAMEWORK_SCHEMA_FILENAME
    schema_path.write_text(FUTURE_SCHEMA, encoding="utf-8-sig")

    assert _extract(schema_path, tmp_path) == ("1.8", "2.4")


def test_schema_format_drift_is_field_local_and_non_fatal(tmp_path):
    schema_path = tmp_path / sync_module.FRAMEWORK_SCHEMA_FILENAME
    schema_path.write_text(
        "> **Version**: 1.8\n"
        "schemaVersion: '2.4',\n",
        encoding="utf-8",
    )

    assert _extract(schema_path, tmp_path) == ("1.8", "unknown")


def test_duplicate_schema_declarations_are_ambiguous_not_guessed(tmp_path):
    schema_path = tmp_path / sync_module.FRAMEWORK_SCHEMA_FILENAME
    schema_path.write_text(
        FUTURE_SCHEMA
        + "\n> **Version**: 1.9\n"
        + 'schemaVersion: "2.5",\n',
        encoding="utf-8",
    )

    assert _extract(schema_path, tmp_path) == ("unknown", "unknown")


@pytest.mark.parametrize("failure_kind", ["missing", "non_utf8", "oversized", "outside_root"])
def test_schema_read_gates_fall_back_to_unknown(tmp_path, failure_kind):
    root = tmp_path / "allowed"
    root.mkdir()
    schema_path = root / sync_module.FRAMEWORK_SCHEMA_FILENAME

    if failure_kind == "non_utf8":
        schema_path.write_bytes(b"\xff\xfe\xfa")
    elif failure_kind == "oversized":
        schema_path.write_bytes(b"x" * (sync_module.MAX_FRAMEWORK_SCHEMA_BYTES + 1))
    elif failure_kind == "outside_root":
        schema_path = tmp_path / sync_module.FRAMEWORK_SCHEMA_FILENAME
        schema_path.write_text(FUTURE_SCHEMA, encoding="utf-8")

    assert _extract(schema_path, root) == ("unknown", "unknown")


def test_same_revision_transient_failure_retains_prior_safe_values():
    revision = "a" * 40
    assert sync_module.resolve_effective_framework_schema_versions(
        ("unknown", "unknown"),
        version_info={
            "source_revision": revision,
            "framework_authoring_schema_version": "1.7",
            "framework_public_schema_version": "2.3",
        },
        current_source_revision=revision,
        source_kind="github",
        metadata_available=False,
    ) == ("1.7", "2.3")


def test_changed_revision_never_inherits_unavailable_schema_metadata():
    assert sync_module.resolve_effective_framework_schema_versions(
        ("unknown", "unknown"),
        version_info={
            "source_revision": "a" * 40,
            "framework_authoring_schema_version": "1.7",
            "framework_public_schema_version": "2.3",
        },
        current_source_revision="b" * 40,
        source_kind="github",
        metadata_available=False,
    ) == ("unknown", "unknown")


def test_staged_malformed_github_metadata_never_uses_same_commit_fallback():
    revision = "a" * 40
    assert sync_module.resolve_effective_framework_schema_versions(
        ("unknown", "unknown"),
        version_info={
            "source_revision": revision,
            "framework_authoring_schema_version": "1.7",
            "framework_public_schema_version": "2.3",
        },
        current_source_revision=revision,
        source_kind="github",
        metadata_available=True,
    ) == ("unknown", "unknown")


def test_invalid_stored_versions_are_not_reused_on_remote_fetch_failure():
    revision = "a" * 40
    assert sync_module.resolve_effective_framework_schema_versions(
        ("unknown", "unknown"),
        version_info={
            "source_revision": revision,
            "framework_authoring_schema_version": "../../invalid",
            "framework_public_schema_version": "2.3",
        },
        current_source_revision=revision,
        source_kind="github",
        metadata_available=False,
    ) == ("unknown", "2.3")


def test_local_same_tactic_revision_malformed_schema_never_inherits_old_values(
    tmp_path,
):
    revision = "a" * 40
    schema_path = tmp_path / sync_module.FRAMEWORK_SCHEMA_FILENAME
    schema_path.write_text(
        "> **Version**: not/a/version\n"
        "schemaVersion: '2.4',\n",
        encoding="utf-8",
    )
    current_digest = sync_module.compute_framework_schema_metadata_sha256(
        schema_path,
        base_dir=tmp_path,
    )
    old_digest = hashlib.sha256(FUTURE_SCHEMA.encode("utf-8")).hexdigest()
    version_info = {
        "source_revision": revision,
        "framework_authoring_schema_version": "1.7",
        "framework_public_schema_version": "2.3",
        "framework_schema_metadata_sha256": old_digest,
    }

    discovered = _extract(schema_path, tmp_path)
    effective_versions = sync_module.resolve_effective_framework_schema_versions(
        discovered,
        version_info=version_info,
        current_source_revision=revision,
        source_kind="local",
        metadata_available=True,
    )
    effective_digest = (
        sync_module.resolve_effective_framework_schema_metadata_sha256(
            current_digest,
            version_info=version_info,
            current_source_revision=revision,
            source_kind="local",
            metadata_available=True,
        )
    )

    assert effective_versions == ("unknown", "unknown")
    assert effective_digest == current_digest
    assert effective_digest != old_digest


@pytest.mark.asyncio
async def test_local_schema_staging_uses_root_path_and_preserves_utf8_bytes(
    tmp_path, monkeypatch
):
    local_root = tmp_path / "framework"
    raw_root = tmp_path / "raw"
    local_root.mkdir()
    raw_root.mkdir()
    source_path = local_root / sync_module.FRAMEWORK_SCHEMA_FILENAME
    source_path.write_text(FUTURE_SCHEMA + "\n<!-- 安全 -->\n", encoding="utf-8-sig")

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", local_root)
    monkeypatch.setattr(settings, "RAW_PATH", raw_root)
    monkeypatch.setattr(sync_module, "set_secure_file_permissions", lambda _path: None)

    staged_path = await sync_module.download_schema_metadata_file("a" * 40)

    assert staged_path == raw_root / sync_module.FRAMEWORK_SCHEMA_FILENAME
    assert staged_path.read_bytes() == source_path.read_bytes()
    assert _extract(staged_path, raw_root) == ("1.8", "2.4")


@pytest.mark.asyncio
async def test_missing_optional_local_schema_clears_stale_staged_copy(
    tmp_path, monkeypatch
):
    local_root = tmp_path / "framework"
    raw_root = tmp_path / "raw"
    local_root.mkdir()
    raw_root.mkdir()
    stale_path = raw_root / sync_module.FRAMEWORK_SCHEMA_FILENAME
    stale_path.write_text(FUTURE_SCHEMA, encoding="utf-8")

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", local_root)
    monkeypatch.setattr(settings, "RAW_PATH", raw_root)

    assert await sync_module.download_schema_metadata_file("a" * 40) is None
    assert not stale_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [b"\xff\xfe\xfa", b"x" * (1024 * 1024 + 1)],
    ids=["non-utf8", "oversized"],
)
async def test_remote_schema_download_rejects_unsafe_bytes_and_clears_stale_copy(
    tmp_path, monkeypatch, payload
):
    stale_path = tmp_path / sync_module.FRAMEWORK_SCHEMA_FILENAME
    stale_path.write_text(FUTURE_SCHEMA, encoding="utf-8")

    class FakeResponse:
        content = payload

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(sync_module.httpx, "AsyncClient", FakeClient)

    assert await sync_module.download_schema_metadata_file("a" * 40) is None
    assert not stale_path.exists()


def _write_manifest(path: Path) -> None:
    path.write_text(
        "import { modelTactic } from './tactics/model.js';\n"
        "export const aidefendData = { tactics: [modelTactic] };\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_same_revision_transient_schema_failure_remains_a_noop(
    tmp_path, monkeypatch
):
    revision = "a" * 40
    raw_root = tmp_path / "raw"
    database_root = tmp_path / "db"
    raw_root.mkdir()
    (database_root / "aidefend.lance").mkdir(parents=True)
    manifest_path = raw_root / sync_module.FRAMEWORK_MANIFEST_FILENAME
    _write_manifest(manifest_path)
    source_files = [sync_module.FRAMEWORK_INTRO_FILENAME, "model.js"]
    version_info = {
        "commit_sha": revision,
        "source_revision": revision,
        "framework_authoring_schema_version": "1.7",
        "framework_public_schema_version": "2.3",
        "framework_schema_metadata_sha256": "d" * 64,
        "index_schema_version": settings.CACHE_SCHEMA_VERSION,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimension": settings.EMBEDDING_DIMENSION,
        "source_kind": "github",
        "source_revision_kind": "git_commit_sha",
        "source_repository": settings.github_repo_path,
        "source_ref": settings.GITHUB_BRANCH,
        "source_content_sha256": "c" * 64,
        "source_files": source_files,
    }
    timestamp_saved = False

    async def fake_manifest(_revision):
        return manifest_path

    async def fake_schema(_revision):
        return None

    async def fake_cleanup():
        return True

    def fake_timestamp():
        nonlocal timestamp_saved
        timestamp_saved = True

    async def unexpected_download(*_args, **_kwargs):
        raise AssertionError("same-revision metadata retry must remain a no-op")

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", raw_root)
    monkeypatch.setattr(settings, "DB_PATH", database_root)
    monkeypatch.setattr(sync_module, "fetch_latest_commit_sha", lambda: None)

    async def fake_latest():
        return revision

    monkeypatch.setattr(sync_module, "fetch_latest_commit_sha", fake_latest)
    monkeypatch.setattr(sync_module, "download_manifest_file", fake_manifest)
    monkeypatch.setattr(sync_module, "download_schema_metadata_file", fake_schema)
    monkeypatch.setattr(sync_module, "get_local_commit_sha", lambda: revision)
    monkeypatch.setattr(sync_module, "load_version_info", lambda: version_info)
    monkeypatch.setattr(sync_module, "download_file", unexpected_download)
    monkeypatch.setattr(sync_module, "download_intro_file", unexpected_download)
    monkeypatch.setattr(sync_module, "_cleanup_successful_sync_artifacts", fake_cleanup)
    monkeypatch.setattr(sync_module, "save_sync_timestamp", fake_timestamp)

    assert await sync_module.core_sync() is True
    assert timestamp_saved is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("schema_contents", "expected_versions"),
    [
        (FUTURE_SCHEMA, ("1.8", "2.4")),
        (None, ("unknown", "unknown")),
    ],
)
async def test_changed_revision_saves_discovered_or_unknown_schema_versions(
    tmp_path, monkeypatch, schema_contents, expected_versions
):
    old_revision = "a" * 40
    new_revision = "b" * 40
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    manifest_path = raw_root / sync_module.FRAMEWORK_MANIFEST_FILENAME
    intro_path = raw_root / sync_module.FRAMEWORK_INTRO_FILENAME
    tactic_path = raw_root / "model.js"
    schema_path = raw_root / sync_module.FRAMEWORK_SCHEMA_FILENAME
    _write_manifest(manifest_path)
    intro_path.write_text('export const aidefendVersion = "future";', encoding="utf-8")
    tactic_path.write_text("export const modelTactic = {};", encoding="utf-8")
    if schema_contents is not None:
        schema_path.write_text(schema_contents, encoding="utf-8")
        expected_schema_digest = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    else:
        expected_schema_digest = None
    saved = {}

    async def fake_latest():
        return new_revision

    async def fake_manifest(_revision):
        return manifest_path

    async def fake_schema(_revision):
        return schema_path if schema_contents is not None else None

    async def fake_intro(_revision):
        return intro_path

    async def fake_tactic(_filename, _revision):
        return tactic_path

    async def fake_embed(documents):
        return True, {
            "overview": {
                "total_documents": len(documents),
                "total_actionable_items": 1,
            }
        }

    async def fake_cleanup():
        return True

    async def fake_vector_index():
        return None

    def capture_version(revision, metadata):
        saved["revision"] = revision
        saved["metadata"] = metadata

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", raw_root)
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "db")
    monkeypatch.setattr(sync_module, "fetch_latest_commit_sha", fake_latest)
    monkeypatch.setattr(sync_module, "download_manifest_file", fake_manifest)
    monkeypatch.setattr(sync_module, "download_schema_metadata_file", fake_schema)
    monkeypatch.setattr(sync_module, "download_intro_file", fake_intro)
    monkeypatch.setattr(sync_module, "download_file", fake_tactic)
    monkeypatch.setattr(sync_module, "get_local_commit_sha", lambda: old_revision)
    monkeypatch.setattr(
        sync_module,
        "load_version_info",
        lambda: {
            "source_revision": old_revision,
            "framework_authoring_schema_version": "1.7",
            "framework_public_schema_version": "2.3",
        },
    )
    monkeypatch.setattr(sync_module, "extract_framework_version", lambda _path: "future")
    monkeypatch.setattr(sync_module, "parse_tactic_file", lambda _path: {"name": "Model"})
    monkeypatch.setattr(sync_module, "validate_tactic_contract", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        sync_module,
        "extract_documents_from_tactic",
        lambda _tactic: [{"source_id": "AID-M-999", "type": "technique"}],
    )
    monkeypatch.setattr(sync_module, "embed_and_index", fake_embed)
    monkeypatch.setattr(sync_module, "save_version_info", capture_version)
    monkeypatch.setattr(sync_module, "_cleanup_successful_sync_artifacts", fake_cleanup)
    monkeypatch.setattr(sync_module, "_create_vector_index_if_needed", fake_vector_index)

    from app.core import query_engine

    monkeypatch.setattr(query_engine, "_initialized", True)
    monkeypatch.setattr(query_engine, "_table", object())

    assert await sync_module.core_sync() is True
    assert saved["revision"] == new_revision
    assert (
        saved["metadata"]["framework_authoring_schema_version"],
        saved["metadata"]["framework_public_schema_version"],
    ) == expected_versions
    assert (
        saved["metadata"]["framework_schema_metadata_sha256"]
        == expected_schema_digest
    )
    assert saved["metadata"]["source_files"] == [
        sync_module.FRAMEWORK_INTRO_FILENAME,
        "model.js",
    ]
    assert sync_module.FRAMEWORK_SCHEMA_FILENAME not in saved["metadata"]["source_files"]
