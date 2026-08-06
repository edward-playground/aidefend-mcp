"""Focused contracts for the one-click installer's vendored parser path."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from scripts import install as installer


def test_installer_accepts_python_314_and_rejects_below_floor(monkeypatch):
    monkeypatch.setattr(
        installer.sys,
        "version_info",
        SimpleNamespace(major=3, minor=14, micro=0),
    )
    assert installer.check_python_version() == (True, "3.14.0")

    monkeypatch.setattr(
        installer.sys,
        "version_info",
        SimpleNamespace(major=3, minor=9, micro=19),
    )
    assert installer.check_python_version() == (False, "3.9.19")


def test_node_version_check_does_not_require_or_invoke_npm(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[0].lower().startswith("npm"):
            raise AssertionError("npm must not be checked")
        return subprocess.CompletedProcess(command, 0, stdout="v18.19.1\n", stderr="")

    monkeypatch.setattr(installer.subprocess, "run", fake_run)

    valid, version = installer.check_node_version()

    assert valid is True
    assert version == "v18.19.1"
    assert calls == [["node", "--version"]]


def test_installer_download_url_allowlist_is_fail_closed():
    accepted = [
        "https://nodejs.org/dist/index.json",
        "https://aka.ms/vs/17/release/vc_redist.x64.exe",
        "https://download.visualstudio.microsoft.com/download/runtime.exe",
    ]
    rejected = [
        "http://nodejs.org/dist/index.json",
        "file:///tmp/node-installer",
        "https://example.com/node-installer",
        "https://user:password@nodejs.org/dist/index.json",
        "https://nodejs.org:8443/dist/index.json",
        "not a URL",
    ]

    for url in accepted:
        assert installer.validate_trusted_installer_url(url) == url
    for url in rejected:
        try:
            installer.validate_trusted_installer_url(url)
        except ValueError:
            pass
        else:
            raise AssertionError(f"untrusted installer URL was accepted: {url}")


def test_node_installer_rejects_untrusted_release_version(tmp_path, monkeypatch):
    download_calls = []
    monkeypatch.setattr(
        installer,
        "download_with_progress",
        lambda *args, **kwargs: download_calls.append((args, kwargs)) or True,
    )

    success, message = installer.download_nodejs_installer(
        {"version": "../../malicious", "lts_name": "Fake"},
        target_dir=tmp_path,
    )

    assert success is False
    assert message == "Invalid Node.js release version"
    assert download_calls == []


def test_historical_install_function_runs_only_bounded_node_checks(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        assert command[0] == "node"
        assert kwargs["timeout"] == 10
        assert kwargs["capture_output"] is True
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(installer.subprocess, "run", fake_run)

    assert installer.install_node_dependencies(verbose=False) is True
    assert len(calls) == 3
    assert calls[0][0][1] == "--check"
    assert calls[1][0][1] == "--check"
    assert "--eval" in calls[2][0]
    assert all(not call[0][0].lower().startswith("npm") for call in calls)


def test_vendored_parser_verification_executes_real_syntax_and_parse_checks():
    repository_root = Path(__file__).resolve().parents[1]

    assert installer.verify_vendored_parser(repository_root, verbose=False) is True


def test_vendored_acorn_matches_audited_official_package_metadata():
    repository_root = Path(__file__).resolve().parents[1]
    manifest = json.loads((repository_root / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((repository_root / "package-lock.json").read_text(encoding="utf-8"))
    acorn_lock = lock["packages"]["node_modules/acorn"]
    vendored_runtime = (repository_root / "vendor" / "acorn.mjs").read_bytes()

    assert manifest["dependencies"]["acorn"] == "8.18.0"
    assert lock["packages"][""]["dependencies"]["acorn"] == "8.18.0"
    assert acorn_lock == {
        "version": "8.18.0",
        "resolved": "https://registry.npmjs.org/acorn/-/acorn-8.18.0.tgz",
        "integrity": (
            "sha512-lGq+9yr1/GuAWaVYIHRjvvySG5/4VfKIvC8EWxStPdcDh/Ka7FG3twP6v4d5Bkrav"
            "UilhIAsG4Qj83t02LWUPQ=="
        ),
        "license": "MIT",
        "bin": {"acorn": "bin/acorn"},
        "engines": {"node": ">=0.4.0"},
    }
    assert hashlib.sha256(vendored_runtime).hexdigest() == installer.VENDORED_ACORN_SHA256
    assert b'var version = "8.18.0";' in vendored_runtime


def test_vendored_parser_verification_fails_closed_before_spawning_node(tmp_path, monkeypatch):
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Node must not run when bundled assets are missing")
        ),
    )

    assert installer.verify_vendored_parser(tmp_path, verbose=False) is False


def test_vendored_parser_integrity_rejects_tampered_runtime(tmp_path, monkeypatch):
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (tmp_path / "parse_js_module.mjs").write_text(
        "import * as acorn from './vendor/acorn.mjs';\n", encoding="utf-8"
    )
    (vendor / "acorn.mjs").write_text(
        'var version = "8.14.0";\nexport { version };\n', encoding="utf-8"
    )
    (vendor / "ACORN-LICENSE").write_text("MIT\n", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/acorn": {
                        "version": "8.18.0",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        installer.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Node must not run after an integrity mismatch")
        ),
    )

    assert installer.verify_vendored_parser(tmp_path, verbose=False) is False


def test_dry_run_describes_local_parser_verification_without_npm(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["install.py", "--dry-run", "--no-mcp"])
    monkeypatch.setattr(installer, "check_python_version", lambda: (True, "3.14.0"))
    monkeypatch.setattr(installer, "check_node_version", lambda: (True, "v20.19.0"))
    monkeypatch.setattr(
        installer,
        "install_node_dependencies",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("dry-run must not execute parser checks")
        ),
    )

    assert installer.main() == 0
    output = capsys.readouterr().out
    assert "Verifying bundled JavaScript parser [DRY RUN]" in output
    assert "bounded local syntax and parser checks" in output
    assert "npm install" not in output


def test_prerequisite_check_includes_bundled_parser_verification(monkeypatch, capsys):
    parser_checks = []
    monkeypatch.setattr(sys, "argv", ["install.py", "--check"])
    monkeypatch.setattr(installer.sys, "platform", "linux")
    monkeypatch.setattr(installer, "check_python_version", lambda: (True, "3.14.0"))
    monkeypatch.setattr(installer, "check_node_version", lambda: (True, "v20.19.0"))
    monkeypatch.setattr(
        installer,
        "install_node_dependencies",
        lambda verbose=False: parser_checks.append(verbose) or True,
    )
    monkeypatch.setattr(
        installer,
        "check_claude_desktop_installed",
        lambda: (False, "Claude Desktop not found"),
    )
    monkeypatch.setattr(installer, "check_internet_connectivity", lambda: False)

    assert installer.main() == 0
    output = capsys.readouterr().out
    assert parser_checks == [False]
    assert "[3/6] Verifying bundled JavaScript parser" in output
    assert "Bundled parser and Acorn runtime verified" in output


def test_claude_code_config_is_explicitly_machine_local(tmp_path, monkeypatch, capsys):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    monkeypatch.setattr(installer, "__file__", str(scripts_dir / "install.py"))
    monkeypatch.setattr(installer, "get_python_path", lambda: "/opt/aidefend/bin/python")
    monkeypatch.setattr(installer, "get_mcp_path", lambda: "/opt/aidefend/mcp")
    monkeypatch.setattr(installer, "validate_paths", lambda *_args: True)

    assert installer.configure_claude_code(auto=True) is True

    config = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    aidefend = config["mcpServers"]["aidefend"]
    assert aidefend["command"] == "/opt/aidefend/bin/python"
    assert aidefend["cwd"] == "/opt/aidefend/mcp"

    output = capsys.readouterr().out
    assert "machine-local configuration containing absolute paths" in output
    assert "Do not commit or share this file" in output
    assert "You can commit this file" not in output


def test_public_release_ignore_contracts_cover_machine_local_state_and_secrets():
    repository_root = Path(__file__).resolve().parents[1]
    gitignore = (repository_root / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (repository_root / ".dockerignore").read_text(encoding="utf-8")

    assert ".mcp.json" in gitignore.splitlines()
    assert "!.env.example" in gitignore.splitlines()
    required_git_rules = {
        "devtools/",
        "models/",
        "*.p8",
        "*.ppk",
        "id_rsa*",
        "id_ed25519*",
        ".npmrc",
        ".pypirc",
        ".netrc",
        "*credentials*.yaml",
        "*credentials*.yml",
        "*secrets*.yaml",
        "*secrets*.yml",
    }
    assert required_git_rules <= set(gitignore.splitlines())

    required_docker_rules = {
        "devtools/",
        "models/",
        ".mcp.json",
        "CLAUDE*.md",
        "*.key",
        "*.pem",
        "*.p12",
        "*.pfx",
        "*.p8",
        "*.ppk",
        "*.jks",
        "*.keystore",
        "id_rsa*",
        "id_ed25519*",
        ".npmrc",
        ".pypirc",
        ".netrc",
        "*credentials*.json",
        "*credentials*.yaml",
        "*credentials*.yml",
        "*secrets*.json",
        "*secrets*.yaml",
        "*secrets*.yml",
        ".mypy_cache/",
        ".pytest-*/",
        ".tmp_pytest*/",
        "*.tmp",
        "temp/",
        "tmp/",
        "docker-compose.override.yml",
        "docker-compose.override.yaml",
        "compose.override.yml",
        "compose.override.yaml",
    }
    assert required_docker_rules <= set(dockerignore.splitlines())
