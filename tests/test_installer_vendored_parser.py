"""Focused contracts for the one-click installer's vendored parser path."""

import json
import subprocess
import sys
from pathlib import Path

from scripts import install as installer


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


def test_vendored_parser_verification_fails_closed_before_spawning_node(
    tmp_path, monkeypatch
):
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
                        "version": "8.15.0",
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


def test_dry_run_describes_local_parser_verification_without_npm(
    monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", ["install.py", "--dry-run", "--no-mcp"])
    monkeypatch.setattr(installer, "check_python_version", lambda: (True, "3.13.5"))
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


def test_prerequisite_check_includes_bundled_parser_verification(
    monkeypatch, capsys
):
    parser_checks = []
    monkeypatch.setattr(sys, "argv", ["install.py", "--check"])
    monkeypatch.setattr(installer.sys, "platform", "linux")
    monkeypatch.setattr(installer, "check_python_version", lambda: (True, "3.13.5"))
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
