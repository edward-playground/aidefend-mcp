"""Fail-closed discovery of the framework's public data schema version.

The public schema belongs to the generated ``data/data.json`` dataset. It is
metadata only: tactics remain the indexed source, and no separate schema
document participates in this contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

import app.sync as sync_module
from app.config import settings

REVISION = "e10c1678ee49f03f8fb0c97d446ba3fbc3543655"
_DEFAULT_PAYLOAD = object()


def _dataset(schema_version: object = "2.3", **extra: object) -> dict:
    return {
        "version": {"schemaVersion": schema_version},
        "tactics": [],
        **extra,
    }


def _write_dataset(
    root: Path,
    payload: object = _DEFAULT_PAYLOAD,
    *,
    raw: bytes | None = None,
    filename: str | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / (filename or sync_module.FRAMEWORK_PUBLIC_DATA_FILENAME)
    if raw is not None:
        path.write_bytes(raw)
    else:
        value = _dataset() if payload is _DEFAULT_PAYLOAD else payload
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
    return path


def _write_github_dataset(
    root: Path,
    payload: object = _DEFAULT_PAYLOAD,
    *,
    revision: str = REVISION,
    raw: bytes | None = None,
) -> Path:
    return _write_dataset(
        root,
        payload,
        raw=raw,
        filename=sync_module.framework_public_data_staged_filename(revision),
    )


def _extract(path: Path, root: Path) -> str:
    return sync_module.extract_framework_public_schema_version(
        path,
        base_dir=root,
    )


def _stored_public_schema(revision: str = REVISION) -> dict:
    return {
        "source_kind": "github",
        "source_revision_kind": "git_commit_sha",
        "source_revision": revision,
        "source_repository": "edward-playground/aidefense-framework",
        "framework_public_schema_version": "2.3",
        "framework_public_schema_source": (sync_module.FRAMEWORK_PUBLIC_DATA_SOURCE_PATH),
    }


def test_public_dataset_discovery_contract_is_bounded_and_source_specific():
    assert sync_module.FRAMEWORK_PUBLIC_DATA_SOURCE_PATH == "data/data.json"
    assert sync_module.FRAMEWORK_PUBLIC_DATA_FILENAME == "framework-public-data.json"
    assert sync_module.MAX_FRAMEWORK_PUBLIC_DATA_BYTES == 8 * 1024 * 1024


def test_current_public_schema_version_is_read_from_root_version_object(tmp_path):
    path = _write_dataset(tmp_path, _dataset("2.3"))

    assert _extract(path, tmp_path) == "2.3"


def test_extractor_uses_bounded_file_reads(tmp_path, monkeypatch):
    path = _write_dataset(tmp_path, _dataset("2.3"))

    def fail_unbounded_read(*_args, **_kwargs):
        raise AssertionError("public schema discovery must not use Path.read_bytes()")

    monkeypatch.setattr(Path, "read_bytes", fail_unbounded_read)

    assert _extract(path, tmp_path) == "2.3"


def test_future_public_schema_version_is_dynamic_not_allowlisted(tmp_path):
    path = _write_dataset(tmp_path, _dataset("2.4"))

    assert _extract(path, tmp_path) == "2.4"


@pytest.mark.parametrize(
    "failure_kind",
    ["missing", "non-utf8", "outside-root"],
)
def test_public_dataset_read_gates_fail_closed(tmp_path, failure_kind):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    path = allowed_root / sync_module.FRAMEWORK_PUBLIC_DATA_FILENAME

    if failure_kind == "non-utf8":
        path.write_bytes(b"\xff\xfe\xfa")
    elif failure_kind == "outside-root":
        path = _write_dataset(tmp_path / "outside")

    assert _extract(path, allowed_root) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


def test_oversized_public_dataset_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_module, "MAX_FRAMEWORK_PUBLIC_DATA_BYTES", 64)
    path = _write_dataset(tmp_path, raw=b"{" + (b" " * 64) + b"}")

    assert _extract(path, tmp_path) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b'{"version": NaN}',
        b'{"version": Infinity}',
        b'{"version": -Infinity}',
    ],
    ids=["empty", "truncated", "nan", "infinity", "negative-infinity"],
)
def test_malformed_or_nonstandard_json_fails_closed(tmp_path, raw):
    path = _write_dataset(tmp_path, raw=raw)

    assert _extract(path, tmp_path) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


@pytest.mark.parametrize(
    "raw",
    [
        (
            b'{"version":{"schemaVersion":"2.3"},"nested":'
            + (b"[" * 10_000)
            + b"0"
            + (b"]" * 10_000)
            + b"}"
        ),
        (b'{"version":{"schemaVersion":"2.3"},"largeInteger":' + (b"9" * 5_000) + b"}"),
    ],
    ids=["excessive-nesting", "integer-conversion-limit"],
)
def test_json_parser_resource_limits_fail_closed_without_escaping(tmp_path, raw):
    path = _write_dataset(tmp_path, raw=raw)

    assert _extract(path, tmp_path) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


def test_public_dataset_json_depth_limit_is_interpreter_independent(tmp_path):
    maximum_nested_arrays = sync_module.MAX_FRAMEWORK_PUBLIC_DATA_JSON_DEPTH - 1
    accepted = _write_dataset(
        tmp_path / "accepted",
        raw=(
            b'{"version":{"schemaVersion":"2.3"},"nested":'
            + (b"[" * maximum_nested_arrays)
            + b"0"
            + (b"]" * maximum_nested_arrays)
            + b"}"
        ),
    )
    rejected = _write_dataset(
        tmp_path / "rejected",
        raw=(
            b'{"version":{"schemaVersion":"2.3"},"nested":'
            + (b"[" * sync_module.MAX_FRAMEWORK_PUBLIC_DATA_JSON_DEPTH)
            + b"0"
            + (b"]" * sync_module.MAX_FRAMEWORK_PUBLIC_DATA_JSON_DEPTH)
            + b"}"
        ),
    )

    assert _extract(accepted, accepted.parent) == "2.3"
    assert _extract(rejected, rejected.parent) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


def test_public_dataset_depth_scanner_ignores_delimiters_inside_strings(tmp_path):
    path = _write_dataset(
        tmp_path,
        {
            "version": {"schemaVersion": "2.4"},
            "text": "[" * 1_000 + "escaped quote: \\\"" + "}" * 1_000,
        },
    )

    assert _extract(path, tmp_path) == "2.4"


@pytest.mark.parametrize(
    "raw",
    [
        b'{"version":{"schemaVersion":"2.3"},"version":{"schemaVersion":"2.4"}}',
        b'{"version":{"schemaVersion":"2.3","schemaVersion":"2.4"}}',
        (b'{"version":{"schemaVersion":"2.3"},' b'"unrelated":{"duplicate":1,"duplicate":2}}'),
    ],
    ids=["root", "version", "unrelated-nested-object"],
)
def test_duplicate_json_keys_at_any_depth_fail_closed(tmp_path, raw):
    path = _write_dataset(tmp_path, raw=raw)

    assert _extract(path, tmp_path) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


@pytest.mark.parametrize(
    "root",
    [None, [], "string", 23],
    ids=["null", "array", "string", "number"],
)
def test_public_dataset_root_must_be_an_object(tmp_path, root):
    path = _write_dataset(tmp_path, root)

    assert _extract(path, tmp_path) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


@pytest.mark.parametrize(
    "version",
    [None, [], "2.3", 23],
    ids=["null", "array", "string", "number"],
)
def test_version_must_be_an_object(tmp_path, version):
    path = _write_dataset(tmp_path, {"version": version})

    assert _extract(path, tmp_path) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"version": {}},
        {"version": {"other": "2.3"}},
    ],
    ids=["missing-version", "missing-schema-version", "wrong-field"],
)
def test_version_schema_version_is_required_at_the_exact_root_path(tmp_path, payload):
    path = _write_dataset(tmp_path, payload)

    assert _extract(path, tmp_path) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


@pytest.mark.parametrize(
    "schema_version",
    [None, True, False, 2.3, [], {}],
    ids=["null", "true", "false", "number", "array", "object"],
)
def test_schema_version_must_be_a_string(tmp_path, schema_version):
    path = _write_dataset(tmp_path, _dataset(schema_version))

    assert _extract(path, tmp_path) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


@pytest.mark.parametrize(
    "schema_version",
    ["", " ", " 2.3", "2.3 ", ".2", "2/3", "x" * 65, "版本2.3"],
)
def test_schema_version_must_follow_the_bounded_component_contract(
    tmp_path,
    schema_version,
):
    path = _write_dataset(tmp_path, _dataset(schema_version))

    assert _extract(path, tmp_path) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


@pytest.mark.parametrize(
    "payload",
    [
        {"metadata": {"version": {"schemaVersion": "9.9"}}},
        {"version": {"metadata": {"schemaVersion": "9.9"}}},
    ],
    ids=["outside-version", "below-version"],
)
def test_unrelated_nested_schema_version_is_not_discovered(tmp_path, payload):
    path = _write_dataset(tmp_path, payload)

    assert _extract(path, tmp_path) == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION


def test_unrelated_nested_schema_version_does_not_override_exact_value(tmp_path):
    path = _write_dataset(
        tmp_path,
        _dataset("2.3", metadata={"schemaVersion": "9.9"}),
    )

    assert _extract(path, tmp_path) == "2.3"


def test_public_dataset_cannot_supply_authoring_schema_metadata(tmp_path):
    payload = _dataset("2.3", authoringSchemaVersion="9.9")
    payload["version"]["authoringSchemaVersion"] = "9.9"
    path = _write_dataset(tmp_path, payload)

    assert _extract(path, tmp_path) == "2.3"


def test_available_public_schema_is_authoritative_for_any_source_revision():
    assert (
        sync_module.resolve_effective_framework_public_schema_version(
            "2.4",
            version_info=_stored_public_schema("a" * 40),
            current_source_revision="b" * 40,
            source_kind="github",
            discovery_status=sync_module.FrameworkPublicDataDiscoveryStatus.AVAILABLE,
        )
        == "2.4"
    )


def test_same_github_revision_transient_failure_retains_matching_staged_value():
    assert (
        sync_module.resolve_effective_framework_public_schema_version(
            "2.3",
            version_info=_stored_public_schema(),
            current_source_revision=REVISION,
            source_kind="github",
            discovery_status=(sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE),
        )
        == "2.3"
    )


def test_transient_failure_without_revision_scoped_evidence_fails_closed():
    assert (
        sync_module.resolve_effective_framework_public_schema_version(
            sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
            version_info=_stored_public_schema(),
            current_source_revision=REVISION,
            source_kind="github",
            discovery_status=(sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE),
        )
        == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION
    )


@pytest.mark.parametrize(
    "version_info",
    [
        {
            "source_revision": REVISION,
            "framework_public_schema_version": "2.3",
        },
        {
            "source_revision": REVISION,
            "framework_public_schema_version": "../../invalid",
            "framework_public_schema_source": "data/data.json",
        },
        {
            "source_revision": REVISION,
            "framework_public_schema_version": "2.3",
            "framework_public_schema_source": "different/source.json",
        },
    ],
    ids=["unproven-source", "invalid-stored-version", "wrong-source-marker"],
)
def test_transient_fallback_requires_a_prior_verified_safe_value(version_info):
    assert (
        sync_module.resolve_effective_framework_public_schema_version(
            sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
            version_info=version_info,
            current_source_revision=REVISION,
            source_kind="github",
            discovery_status=(sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE),
        )
        == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION
    )


@pytest.mark.parametrize(
    "metadata_update",
    [
        {"source_kind": "local", "source_revision_kind": "local_content_sha1"},
        {"source_revision_kind": "local_content_sha1"},
        {"source_repository": "different-owner/different-framework"},
    ],
    ids=["local-origin", "wrong-revision-kind", "different-repository"],
)
def test_transient_fallback_requires_same_immutable_github_provenance(metadata_update):
    version_info = _stored_public_schema()
    version_info.update(metadata_update)

    assert (
        sync_module.resolve_effective_framework_public_schema_version(
            sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
            version_info=version_info,
            current_source_revision=REVISION,
            source_kind="github",
            current_source_repository="edward-playground/aidefense-framework",
            discovery_status=(sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE),
        )
        == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION
    )


def test_changed_github_revision_never_inherits_public_schema():
    assert (
        sync_module.resolve_effective_framework_public_schema_version(
            sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
            version_info=_stored_public_schema("a" * 40),
            current_source_revision="b" * 40,
            source_kind="github",
            discovery_status=(sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE),
        )
        == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION
    )


def test_local_source_never_inherits_public_schema_after_discovery_failure():
    assert (
        sync_module.resolve_effective_framework_public_schema_version(
            sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
            version_info=_stored_public_schema(),
            current_source_revision=REVISION,
            source_kind="local",
            discovery_status=(sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE),
        )
        == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION
    )


def test_invalid_same_revision_metadata_never_uses_transient_fallback():
    assert (
        sync_module.resolve_effective_framework_public_schema_version(
            sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
            version_info=_stored_public_schema(),
            current_source_revision=REVISION,
            source_kind="github",
            discovery_status=sync_module.FrameworkPublicDataDiscoveryStatus.INVALID,
        )
        == sync_module.UNKNOWN_FRAMEWORK_SCHEMA_VERSION
    )


@pytest.mark.asyncio
async def test_local_staging_reads_data_json_from_the_same_framework_root(
    tmp_path,
    monkeypatch,
):
    local_root = tmp_path / "framework"
    raw_root = tmp_path / "raw"
    source_path = local_root / "data" / "data.json"
    source_path.parent.mkdir(parents=True)
    raw_root.mkdir()
    source_bytes = json.dumps(_dataset("2.3"), ensure_ascii=False).encode("utf-8")
    source_path.write_bytes(source_bytes)

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", local_root)
    monkeypatch.setattr(settings, "RAW_PATH", raw_root)
    monkeypatch.setattr(sync_module, "set_secure_file_permissions", lambda _path: None)

    result = await sync_module.download_framework_public_data_file(REVISION)

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.AVAILABLE
    assert result.path == raw_root / sync_module.FRAMEWORK_PUBLIC_DATA_FILENAME
    assert result.path.read_bytes() == source_bytes
    assert _extract(result.path, raw_root) == "2.3"


@pytest.mark.asyncio
async def test_missing_local_public_dataset_clears_stale_staged_copy(
    tmp_path,
    monkeypatch,
):
    local_root = tmp_path / "framework"
    raw_root = tmp_path / "raw"
    local_root.mkdir()
    stale_path = _write_dataset(raw_root)

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", local_root)
    monkeypatch.setattr(settings, "RAW_PATH", raw_root)

    result = await sync_module.download_framework_public_data_file(REVISION)

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.INVALID
    assert result.path is None
    assert not stale_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_kind",
    ["non-utf8", "oversized"],
)
async def test_unsafe_local_public_dataset_is_rejected_and_stale_stage_cleared(
    tmp_path,
    monkeypatch,
    failure_kind,
):
    local_root = tmp_path / "framework"
    raw_root = tmp_path / "raw"
    source_path = local_root / "data" / "data.json"
    source_path.parent.mkdir(parents=True)
    stale_path = _write_dataset(raw_root)

    if failure_kind == "non-utf8":
        source_path.write_bytes(b"\xff\xfe\xfa")
    else:
        monkeypatch.setattr(sync_module, "MAX_FRAMEWORK_PUBLIC_DATA_BYTES", 64)
        source_path.write_bytes(b"x" * 65)

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", local_root)
    monkeypatch.setattr(settings, "RAW_PATH", raw_root)

    result = await sync_module.download_framework_public_data_file(REVISION)

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.INVALID
    assert result.path is None
    assert not stale_path.exists()


class _ResponseContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *_args):
        return None


class _FakeAsyncClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def stream(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        if self.error is not None:
            raise self.error
        return _ResponseContext(self.response)

    async def get(self, url, **kwargs):
        self.requests.append(("GET", url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def _http_response(status: int, content: bytes = b"") -> httpx.Response:
    request = httpx.Request("GET", "https://example.invalid/data/data.json")
    return httpx.Response(status, content=content, request=request)


@pytest.mark.asyncio
async def test_github_staging_uses_the_same_immutable_commit_sha(
    tmp_path,
    monkeypatch,
):
    content = json.dumps(_dataset("2.3")).encode("utf-8")
    client = _FakeAsyncClient(_http_response(200, content))
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(
        sync_module.httpx,
        "AsyncClient",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(sync_module, "set_secure_file_permissions", lambda _path: None)

    result = await sync_module.download_framework_public_data_file(REVISION)

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.AVAILABLE
    assert result.path == (tmp_path / sync_module.framework_public_data_staged_filename(REVISION))
    assert result.path.read_bytes() == content
    assert len(client.requests) == 1
    _, requested_url, _ = client.requests[0]
    assert f"/{REVISION}/{sync_module.FRAMEWORK_PUBLIC_DATA_SOURCE_PATH}" in requested_url
    assert "/main/" not in requested_url


@pytest.mark.asyncio
async def test_github_404_is_invalid_and_clears_stale_staged_copy(
    tmp_path,
    monkeypatch,
):
    stale_path = _write_github_dataset(tmp_path)
    client = _FakeAsyncClient(_http_response(404))
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(
        sync_module.httpx,
        "AsyncClient",
        lambda *_args, **_kwargs: client,
    )

    result = await sync_module.download_framework_public_data_file(
        REVISION,
        previous_source_revision=REVISION,
    )

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.INVALID
    assert result.path is None
    assert not stale_path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [408, 425, 429, 500, 503])
async def test_github_retryable_http_failure_is_transient(
    tmp_path,
    monkeypatch,
    status,
):
    client = _FakeAsyncClient(_http_response(status))
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(
        sync_module.httpx,
        "AsyncClient",
        lambda *_args, **_kwargs: client,
    )

    result = await sync_module.download_framework_public_data_file(
        REVISION,
        previous_source_revision=REVISION,
    )

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE
    assert result.path is None


@pytest.mark.asyncio
async def test_same_revision_transient_failure_can_retain_validated_staged_copy(
    tmp_path,
    monkeypatch,
):
    staged_path = _write_github_dataset(tmp_path, _dataset("2.3"))
    client = _FakeAsyncClient(_http_response(503))
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(
        sync_module.httpx,
        "AsyncClient",
        lambda *_args, **_kwargs: client,
    )

    result = await sync_module.download_framework_public_data_file(
        REVISION,
        previous_source_revision=REVISION,
    )

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE
    assert result.path == staged_path
    assert result.retained_previous is True
    assert _extract(result.path, tmp_path) == "2.3"


@pytest.mark.asyncio
async def test_same_revision_transient_failure_discards_recursion_bomb_stage(
    tmp_path,
    monkeypatch,
):
    staged_path = _write_github_dataset(
        tmp_path,
        raw=(
            b'{"version":{"schemaVersion":"2.3"},"nested":'
            + (b"[" * 10_000)
            + b"0"
            + (b"]" * 10_000)
            + b"}"
        ),
    )
    client = _FakeAsyncClient(_http_response(503))
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(
        sync_module.httpx,
        "AsyncClient",
        lambda *_args, **_kwargs: client,
    )

    result = await sync_module.download_framework_public_data_file(
        REVISION,
        previous_source_revision=REVISION,
    )

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE
    assert result.path is None
    assert result.retained_previous is False
    assert not staged_path.exists()


@pytest.mark.asyncio
async def test_changed_revision_transient_failure_discards_old_staged_copy(
    tmp_path,
    monkeypatch,
):
    previous_revision = "a" * 40
    stale_path = _write_github_dataset(
        tmp_path,
        _dataset("2.3"),
        revision=previous_revision,
    )
    client = _FakeAsyncClient(_http_response(503))
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(
        sync_module.httpx,
        "AsyncClient",
        lambda *_args, **_kwargs: client,
    )

    result = await sync_module.download_framework_public_data_file(
        REVISION,
        previous_source_revision=previous_revision,
    )

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE
    assert result.path is None
    assert result.retained_previous is False
    # The old file remains evidence for the still-active previous generation;
    # it is not selected as fallback for the changed revision.
    assert stale_path.exists()


def test_settled_github_generation_cleans_obsolete_revision_evidence(
    tmp_path,
    monkeypatch,
):
    previous_revision = "a" * 40
    previous_path = _write_github_dataset(
        tmp_path,
        revision=previous_revision,
    )
    current_path = _write_github_dataset(tmp_path, revision=REVISION)
    unscoped_path = _write_dataset(tmp_path)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)

    sync_module._cleanup_staged_framework_public_data_revisions(
        keep_revisions=[REVISION],
    )

    assert not previous_path.exists()
    assert current_path.exists()
    assert not unscoped_path.exists()


def test_candidate_cleanup_keeps_only_active_and_current_revisions(
    tmp_path,
    monkeypatch,
):
    active_revision = "a" * 40
    abandoned_revision = "b" * 40
    active_path = _write_github_dataset(
        tmp_path,
        revision=active_revision,
    )
    current_path = _write_github_dataset(tmp_path, revision=REVISION)
    abandoned_path = _write_github_dataset(
        tmp_path,
        revision=abandoned_revision,
    )
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)

    sync_module._cleanup_staged_framework_public_data_revisions(
        keep_revisions=[active_revision, REVISION],
    )

    assert active_path.exists()
    assert current_path.exists()
    assert not abandoned_path.exists()


@pytest.mark.asyncio
async def test_github_request_failure_is_transient(tmp_path, monkeypatch):
    request = httpx.Request("GET", "https://example.invalid/data/data.json")
    client = _FakeAsyncClient(error=httpx.ReadTimeout("timeout", request=request))
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(
        sync_module.httpx,
        "AsyncClient",
        lambda *_args, **_kwargs: client,
    )

    result = await sync_module.download_framework_public_data_file(
        REVISION,
        previous_source_revision=REVISION,
    )

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE
    assert result.path is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_kind",
    ["non-utf8", "oversized"],
)
async def test_unsafe_github_payload_is_invalid_and_not_staged(
    tmp_path,
    monkeypatch,
    failure_kind,
):
    if failure_kind == "non-utf8":
        content = b"\xff\xfe\xfa"
    else:
        monkeypatch.setattr(sync_module, "MAX_FRAMEWORK_PUBLIC_DATA_BYTES", 64)
        content = b"x" * 65
    client = _FakeAsyncClient(_http_response(200, content))
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(
        sync_module.httpx,
        "AsyncClient",
        lambda *_args, **_kwargs: client,
    )

    result = await sync_module.download_framework_public_data_file(REVISION)

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.INVALID
    assert result.path is None
    assert not (tmp_path / sync_module.framework_public_data_staged_filename(REVISION)).exists()


@pytest.mark.asyncio
async def test_chunked_github_payload_without_content_length_enforces_stream_limit(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(sync_module, "MAX_FRAMEWORK_PUBLIC_DATA_BYTES", 64)

    class ChunkedResponse:
        status_code = 200
        headers = {}

        async def aiter_bytes(self):
            yield b"x" * 40
            yield b"y" * 40

    client = _FakeAsyncClient(ChunkedResponse())
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(
        sync_module.httpx,
        "AsyncClient",
        lambda *_args, **_kwargs: client,
    )

    result = await sync_module.download_framework_public_data_file(REVISION)

    assert result.status is sync_module.FrameworkPublicDataDiscoveryStatus.INVALID
    assert result.path is None
    assert not (tmp_path / sync_module.framework_public_data_staged_filename(REVISION)).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("discovery_state", "expected_version", "expected_source"),
    [
        ("available", "2.3", "data/data.json"),
        ("transient-retained", "2.3", "data/data.json"),
        ("invalid", "unknown", None),
    ],
)
async def test_core_sync_commits_public_metadata_without_indexing_the_dataset(
    tmp_path,
    monkeypatch,
    discovery_state,
    expected_version,
    expected_source,
):
    data_root = tmp_path / "data"
    raw_root = data_root / "raw_content"
    database_root = data_root / "aidefend_kb.lancedb"
    raw_root.mkdir(parents=True)
    manifest_path = raw_root / sync_module.FRAMEWORK_MANIFEST_FILENAME
    intro_path = raw_root / sync_module.FRAMEWORK_INTRO_FILENAME
    tactic_path = raw_root / "model.js"
    manifest_path.write_text("export const aidefendData = {};", encoding="utf-8")
    intro_path.write_text('export const aidefendVersion = "1.20260805";', encoding="utf-8")
    tactic_path.write_text("export const modelTactic = {};", encoding="utf-8")

    public_path = _write_github_dataset(raw_root, _dataset("2.3"))
    if discovery_state == "invalid":
        public_path.unlink()
        public_result = sync_module.FrameworkPublicDataStageResult(
            None,
            sync_module.FrameworkPublicDataDiscoveryStatus.INVALID,
        )
    elif discovery_state == "transient-retained":
        public_result = sync_module.FrameworkPublicDataStageResult(
            public_path,
            sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE,
            "HTTP 503",
            retained_previous=True,
        )
    else:
        public_result = sync_module.FrameworkPublicDataStageResult(
            public_path,
            sync_module.FrameworkPublicDataDiscoveryStatus.AVAILABLE,
        )

    previous_revision = REVISION if discovery_state == "transient-retained" else "a" * 40
    version_info = _stored_public_schema(previous_revision)
    captured = {}

    async def fake_latest():
        return REVISION

    async def fake_manifest(_revision):
        return manifest_path

    async def fake_public_data(_revision, *, previous_source_revision=None):
        del previous_source_revision
        return public_result

    async def fake_migrations(_revision):
        return None

    async def fake_intro(_revision):
        return intro_path

    async def fake_tactic(_filename, _revision):
        return tactic_path

    async def fake_embed(
        documents,
        *,
        framework_labels=None,
        version_metadata_builder=None,
    ):
        del framework_labels
        statistics = {
            "overview": {
                "total_documents": len(documents),
                "total_actionable_items": 1,
            }
        }
        assert version_metadata_builder is not None
        captured["version_commit"] = version_metadata_builder(statistics)
        return True, statistics

    async def successful_cleanup():
        return True

    async def successful_vector_index():
        return True

    async def no_recovery_needed():
        return None

    monkeypatch.setattr(settings, "DATA_PATH", data_root)
    monkeypatch.setattr(settings, "RAW_PATH", raw_root)
    monkeypatch.setattr(settings, "DB_PATH", database_root)
    monkeypatch.setattr(settings, "VERSION_FILE", data_root / "local_version.json")
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(
        sync_module, "_recover_incomplete_generation_activation_locked", no_recovery_needed
    )
    monkeypatch.setattr(sync_module, "fetch_latest_commit_sha", fake_latest)
    monkeypatch.setattr(sync_module, "download_manifest_file", fake_manifest)
    monkeypatch.setattr(sync_module, "parse_staged_tactic_manifest", lambda _path: ["model.js"])
    monkeypatch.setattr(sync_module, "download_framework_public_data_file", fake_public_data)
    monkeypatch.setattr(sync_module, "download_framework_migrations_file", fake_migrations)
    monkeypatch.setattr(sync_module, "download_intro_file", fake_intro)
    monkeypatch.setattr(sync_module, "download_file", fake_tactic)
    monkeypatch.setattr(sync_module, "get_local_commit_sha", lambda: previous_revision)
    monkeypatch.setattr(sync_module, "load_version_info", lambda: version_info)
    monkeypatch.setattr(
        sync_module, "_compute_staged_framework_digest", lambda *_args, **_kwargs: "c" * 64
    )
    monkeypatch.setattr(sync_module, "extract_framework_version", lambda _path: "1.20260805")
    monkeypatch.setattr(
        sync_module,
        "parse_tactic_file",
        lambda _path: {"name": "Model", "techniques": []},
    )
    monkeypatch.setattr(sync_module, "validate_tactic_contract", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        sync_module,
        "validate_framework_migrations_corpus_contract",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        sync_module,
        "extract_documents_from_tactic",
        lambda _tactic: [{"source_id": "AID-M-999", "type": "technique"}],
    )
    monkeypatch.setattr(sync_module, "embed_and_index", fake_embed)
    monkeypatch.setattr(sync_module, "_cleanup_successful_sync_artifacts", successful_cleanup)
    monkeypatch.setattr(sync_module, "_create_vector_index_if_needed", successful_vector_index)

    from app.core import query_engine

    monkeypatch.setattr(query_engine, "_initialized", True)
    monkeypatch.setattr(query_engine, "_table", object())

    assert await sync_module.core_sync(force_rebuild=True) is True
    revision, metadata = captured["version_commit"]
    assert revision == REVISION
    assert metadata["framework_public_schema_version"] == expected_version
    assert metadata.get("framework_public_schema_source") == expected_source
    assert sync_module.FRAMEWORK_PUBLIC_DATA_SOURCE_PATH not in metadata["source_files"]
    assert public_path not in [raw_root / name for name in metadata["source_files"]]


@pytest.mark.asyncio
async def test_core_sync_noop_retains_verified_public_schema_for_same_github_revision(
    tmp_path,
    monkeypatch,
):
    data_root = tmp_path / "data"
    raw_root = data_root / "raw_content"
    database_root = data_root / "aidefend_kb.lancedb"
    (database_root / "aidefend.lance").mkdir(parents=True)
    raw_root.mkdir(parents=True)
    manifest_path = raw_root / sync_module.FRAMEWORK_MANIFEST_FILENAME
    manifest_path.write_text("export const aidefendData = {};", encoding="utf-8")
    public_path = _write_github_dataset(raw_root, _dataset("2.3"))
    source_files = ["model.js", sync_module.FRAMEWORK_INTRO_FILENAME]
    version_info = {
        **_stored_public_schema(REVISION),
        "source_ref": settings.GITHUB_BRANCH,
        "source_content_sha256": "c" * 64,
        "source_files": source_files,
        "index_schema_version": settings.CACHE_SCHEMA_VERSION,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimension": settings.EMBEDDING_DIMENSION,
    }
    events = []

    async def fake_public_data(_revision, *, previous_source_revision=None):
        assert _revision == REVISION
        assert previous_source_revision == REVISION
        return sync_module.FrameworkPublicDataStageResult(
            public_path,
            sync_module.FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE,
            "HTTP 503",
            retained_previous=True,
        )

    async def successful_cleanup():
        events.append("cleanup")
        return True

    async def no_recovery_needed():
        return None

    def save_timestamp():
        events.append("timestamp")

    async def unexpected_embed(*_args, **_kwargs):
        raise AssertionError("same-revision metadata fallback must remain a no-op")

    monkeypatch.setattr(settings, "DATA_PATH", data_root)
    monkeypatch.setattr(settings, "RAW_PATH", raw_root)
    monkeypatch.setattr(settings, "DB_PATH", database_root)
    monkeypatch.setattr(settings, "VERSION_FILE", data_root / "local_version.json")
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(
        sync_module,
        "_recover_incomplete_generation_activation_locked",
        no_recovery_needed,
    )

    async def fake_latest():
        return REVISION

    async def fake_manifest(_revision):
        return manifest_path

    async def fake_migrations(_revision):
        return None

    monkeypatch.setattr(sync_module, "fetch_latest_commit_sha", fake_latest)
    monkeypatch.setattr(sync_module, "download_manifest_file", fake_manifest)
    monkeypatch.setattr(sync_module, "parse_staged_tactic_manifest", lambda _path: ["model.js"])
    monkeypatch.setattr(
        sync_module,
        "_framework_source_files",
        lambda _files, **_kwargs: source_files,
    )
    monkeypatch.setattr(sync_module, "download_framework_public_data_file", fake_public_data)
    monkeypatch.setattr(sync_module, "download_framework_migrations_file", fake_migrations)
    monkeypatch.setattr(sync_module, "get_local_commit_sha", lambda: REVISION)
    monkeypatch.setattr(sync_module, "load_version_info", lambda: version_info)
    monkeypatch.setattr(sync_module, "embed_and_index", unexpected_embed)
    monkeypatch.setattr(sync_module, "_cleanup_successful_sync_artifacts", successful_cleanup)
    monkeypatch.setattr(sync_module, "save_sync_timestamp", save_timestamp)

    assert await sync_module.core_sync() is True
    assert events == ["cleanup", "timestamp"]
    assert public_path.is_file()
