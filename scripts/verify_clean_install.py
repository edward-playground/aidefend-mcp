#!/usr/bin/env python3
"""Prove that a built wheel works without a source checkout or local caches."""

from __future__ import annotations

import importlib.metadata
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def main() -> int:
    source_root_value = (
        os.environ.get("AIDEFEND_SOURCE_ROOT")
        or os.environ.get("GITHUB_WORKSPACE")
    )
    source_root = (
        Path(source_root_value).resolve()
        if source_root_value
        else Path(__file__).resolve().parents[1]
    )

    import app
    import mcp_server
    from app.config import settings
    from app.utils import NODE_PARSER_SCRIPT, parse_js_file_with_node

    installed_modules = (Path(app.__file__).resolve(), Path(mcp_server.__file__).resolve())
    for module_path in installed_modules:
        assert not _is_within(module_path, source_root), (
            f"Imported source checkout instead of installed wheel: {module_path}"
        )

    distribution = importlib.metadata.distribution("aidefend-mcp")
    assert distribution.version
    assert NODE_PARSER_SCRIPT.is_file(), NODE_PARSER_SCRIPT
    vendor_runtime = NODE_PARSER_SCRIPT.parent / "vendor" / "acorn.mjs"
    vendor_license = NODE_PARSER_SCRIPT.parent / "vendor" / "ACORN-LICENSE"
    assert vendor_runtime.is_file(), vendor_runtime
    assert vendor_license.is_file(), vendor_license

    node = shutil.which("node")
    assert node, "Node.js is required for framework synchronization"
    node_major = int(
        subprocess.check_output(
            [node, "-p", "process.versions.node.split('.')[0]"],
            text=True,
            timeout=10,
        ).strip()
    )
    assert node_major >= 18, node_major

    settings.RAW_PATH.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="aidefend-clean-install-", dir=settings.RAW_PATH
    ) as temp_directory:
        fixture = Path(temp_directory) / "fixture.js"
        fixture.write_text(
            'export const fixture = {name: "Clean Install", '
            'description: `vendored parser`, techniques: []};',
            encoding="utf-8",
        )
        parsed = parse_js_file_with_node(fixture)
        assert parsed == {
            "name": "Clean Install",
            "description": "vendored parser",
            "techniques": [],
        }

    settings.DATA_PATH.mkdir(parents=True, exist_ok=True)
    write_probe = settings.DATA_PATH / ".clean-install-write-probe"
    write_probe.write_text("ok", encoding="utf-8")
    assert write_probe.read_text(encoding="utf-8") == "ok"
    write_probe.unlink()
    assert all(not _is_within(settings.DATA_PATH, path.parent) for path in installed_modules)
    assert not _is_within(settings.DATA_PATH, source_root)

    console = shutil.which("aidefend-mcp")
    assert console, "Installed console script was not created"
    help_result = subprocess.run(
        [console, "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "AIDEFEND MCP Service" in help_result.stdout

    print(
        "clean-install-ok",
        f"version={distribution.version}",
        f"python={sys.version.split()[0]}",
        f"module={installed_modules[0]}",
        f"data={settings.DATA_PATH}",
        f"parser={NODE_PARSER_SCRIPT}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
