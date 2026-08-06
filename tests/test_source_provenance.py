"""Release-gate tests for local-to-GitHub source provenance."""

from pathlib import Path

import httpx
import pytest

import app.sync as sync_module
from app.config import settings


def _write_sources(root: Path, newline: bytes) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in ("first.js", "second.js"):
        path = root / name
        path.write_bytes(newline.join((b"export const value = 1;", b"export default value;", b"")))
        paths.append(path)
    return paths


def test_framework_content_digest_is_stable_across_git_newline_normalization(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "AIDEFEND_FILES", ["first.js", "second.js"])
    lf_paths = _write_sources(tmp_path / "lf", b"\n")
    crlf_paths = _write_sources(tmp_path / "crlf", b"\r\n")

    for algorithm in ("sha1", "sha256"):
        assert sync_module._compute_staged_framework_digest(
            lf_paths, algorithm=algorithm
        ) == sync_module._compute_staged_framework_digest(crlf_paths, algorithm=algorithm)


def test_local_signature_uses_dynamic_manifest_membership_and_order(tmp_path, monkeypatch):
    tactics_path = tmp_path / "tactics"
    tactics_path.mkdir()
    (tmp_path / "aidefend-intro.js").write_text(
        "export const version = 'future';", encoding="utf-8"
    )
    migrations_path = tmp_path / "data" / "framework-migrations.json"
    migrations_path.parent.mkdir()
    migrations_path.write_text('{"schemaVersion":"1.0"}', encoding="utf-8")
    (tactics_path / "alpha.js").write_text("export const alpha = {};", encoding="utf-8")
    (tactics_path / "respond.js").write_text("export const respond = {};", encoding="utf-8")

    def write_manifest(members):
        imports = "\n".join(
            f"import {{ {name}Tactic }} from './tactics/{name}.js';" for name in members
        )
        array = ", ".join(f"{name}Tactic" for name in members)
        (tmp_path / "main.js").write_text(
            f"{imports}\nexport const aidefendData = {{ tactics: [{array}] }};",
            encoding="utf-8",
        )

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", tmp_path)
    monkeypatch.setattr(settings, "GITHUB_TACTICS_PATH", "tactics")
    write_manifest(["alpha", "respond"])
    first = sync_module._compute_local_framework_signature()
    assert first == sync_module._compute_staged_framework_digest(
        [
            tmp_path / "aidefend-intro.js",
            migrations_path,
            tactics_path / "alpha.js",
            tactics_path / "respond.js",
        ],
        algorithm="sha1",
        source_files=[
            "aidefend-intro.js",
            "data/framework-migrations.json",
            "alpha.js",
            "respond.js",
        ],
    )

    migrations_path.write_text('{"schemaVersion":"1.1"}', encoding="utf-8")
    assert sync_module._compute_local_framework_signature() != first
    migrations_path.write_text('{"schemaVersion":"1.0"}', encoding="utf-8")
    write_manifest(["respond", "alpha"])
    assert sync_module._compute_local_framework_signature() != first


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_kind", ["tactic", "intro", "manifest", "migration"]
)
async def test_github_download_preserves_immutable_response_bytes(
    tmp_path, monkeypatch, source_kind
):
    payload = b"export const label = '\xe5\xae\x89\xe5\x85\xa8';\r\nexport default label;\n"

    class FakeResponse:
        content = payload
        status_code = 200

        @property
        def text(self):
            raise AssertionError("GitHub source downloads must not round-trip through text mode")

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
    monkeypatch.setattr(sync_module, "set_secure_file_permissions", lambda _path: None)

    if source_kind == "intro":
        downloaded = await sync_module.download_intro_file("a" * 40)
        expected_name = "aidefend-intro.js"
    elif source_kind == "manifest":
        downloaded = await sync_module.download_manifest_file("a" * 40)
        expected_name = "main.js"
    elif source_kind == "migration":
        downloaded = await sync_module.download_framework_migrations_file("a" * 40)
        expected_name = "framework-migrations.json"
    else:
        downloaded = await sync_module.download_file("model.js", "a" * 40)
        expected_name = "model.js"

    assert downloaded == tmp_path / expected_name
    assert downloaded.read_bytes() == payload


@pytest.mark.asyncio
async def test_missing_github_migration_registry_removes_stale_stage(
    tmp_path, monkeypatch
):
    stale = tmp_path / sync_module.FRAMEWORK_MIGRATIONS_FILENAME
    stale.write_text("stale", encoding="utf-8")

    class MissingResponse:
        status_code = 404
        content = b""

        def raise_for_status(self):
            raise AssertionError("404 is handled as legacy absence")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return MissingResponse()

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(sync_module.httpx, "AsyncClient", FakeClient)

    assert await sync_module.download_framework_migrations_file("a" * 40) is None
    assert not stale.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "network"])
async def test_migration_registry_download_failures_are_not_legacy_absence(
    tmp_path, monkeypatch, failure
):
    request = httpx.Request("GET", "https://raw.githubusercontent.com/example/repo/file")

    class ErrorResponse:
        status_code = 503
        content = b""

        def raise_for_status(self):
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("unavailable", request=request, response=response)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            if failure == "network":
                raise httpx.RequestError("offline", request=request)
            return ErrorResponse()

    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(sync_module.httpx, "AsyncClient", FakeClient)

    with pytest.raises(
        sync_module.FrameworkMigrationRegistryError,
        match="failed to download framework migration registry",
    ):
        await sync_module.download_framework_migrations_file("a" * 40)
