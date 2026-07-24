#!/usr/bin/env python3
"""Fail closed when release archives are incomplete or workspace-contaminated."""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


class DistributionInventoryError(RuntimeError):
    """Raised when a wheel or sdist violates the release inventory contract."""


REQUIRED_RUNTIME_PYTHON_FILES = {
    "app/__init__.py",
    "app/audit.py",
    "app/auth.py",
    "app/chunking.py",
    "app/cli.py",
    "app/config.py",
    "app/core.py",
    "app/embedding_cache.py",
    "app/exceptions.py",
    "app/framework_manifest.py",
    "app/framework_utils.py",
    "app/logger.py",
    "app/main.py",
    "app/schemas.py",
    "app/security.py",
    "app/sync.py",
    "app/threat_keywords.py",
    "app/utils.py",
    "app/tools/__init__.py",
    "app/tools/chunked_search.py",
    "app/tools/classify_threat.py",
    "app/tools/code_snippets.py",
    "app/tools/compliance_mapping.py",
    "app/tools/comprehensive_search.py",
    "app/tools/coverage_analysis.py",
    "app/tools/defenses_for_threat.py",
    "app/tools/implementation_plan.py",
    "app/tools/incident_response.py",
    "app/tools/quick_reference.py",
    "app/tools/security_posture.py",
    "app/tools/statistics.py",
    "app/tools/technique_comparison.py",
    "app/tools/technique_detail.py",
    "app/tools/threat_coverage.py",
    "app/tools/validation.py",
    "mcp_server.py",
}
COMMON_REQUIRED_FILES = REQUIRED_RUNTIME_PYTHON_FILES
SDIST_REQUIRED_FILES = COMMON_REQUIRED_FILES | {
    "parse_js_module.mjs",
    "vendor/acorn.mjs",
    "vendor/ACORN-LICENSE",
}
WHEEL_REQUIRED_ASSET_SUFFIXES = {
    "parser": "/data/parse_js_module.mjs",
    "vendored Acorn runtime": "/data/vendor/acorn.mjs",
    "vendored Acorn license": "/data/vendor/ACORN-LICENSE",
}
WHEEL_FORBIDDEN_TOP_LEVEL = {"build", "data", "tests", "node_modules"}
SDIST_FORBIDDEN_TOP_LEVEL = {
    ".git",
    ".venv",
    "build",
    "data",
    "dist",
    "htmlcov",
    "node_modules",
    "test-artifacts",
    "venv",
}


def _normalize_member_name(raw_name: str, *, artifact: Path) -> str:
    if "\\" in raw_name:
        raise DistributionInventoryError(
            f"{artifact.name}: archive member uses a backslash: {raw_name!r}"
        )
    member = PurePosixPath(raw_name)
    if member.is_absolute() or ".." in member.parts:
        raise DistributionInventoryError(f"{artifact.name}: unsafe archive member: {raw_name!r}")
    normalized = "/".join(part for part in member.parts if part not in ("", "."))
    if not normalized:
        raise DistributionInventoryError(f"{artifact.name}: archive contains an empty member name")
    return normalized


def _wheel_members(wheel_path: Path) -> set[str]:
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            normalized_members = [
                _normalize_member_name(name, artifact=wheel_path) for name in archive.namelist()
            ]
            if len(normalized_members) != len(set(normalized_members)):
                raise DistributionInventoryError(
                    f"{wheel_path.name}: archive contains duplicate member names"
                )
            return set(normalized_members)
    except (OSError, zipfile.BadZipFile) as exc:
        raise DistributionInventoryError(f"{wheel_path.name}: unreadable wheel: {exc}") from exc


def _sdist_members(sdist_path: Path) -> set[str]:
    try:
        with tarfile.open(sdist_path, mode="r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                    raise DistributionInventoryError(
                        f"{sdist_path.name}: unsupported archive member type: " f"{member.name!r}"
                    )
            normalized_members = [
                _normalize_member_name(member.name, artifact=sdist_path) for member in members
            ]
            if len(normalized_members) != len(set(normalized_members)):
                raise DistributionInventoryError(
                    f"{sdist_path.name}: archive contains duplicate member names"
                )
            raw_members = set(normalized_members)
    except (OSError, tarfile.TarError) as exc:
        raise DistributionInventoryError(f"{sdist_path.name}: unreadable sdist: {exc}") from exc
    roots = {name.split("/", 1)[0] for name in raw_members}
    if len(roots) != 1:
        raise DistributionInventoryError(
            f"{sdist_path.name}: expected one archive root, found {sorted(roots)}"
        )
    root = next(iter(roots))
    prefix = f"{root}/"
    return {
        name[len(prefix) :]
        for name in raw_members
        if name.startswith(prefix) and len(name) > len(prefix)
    }


def verify_wheel(wheel_path: Path) -> dict[str, object]:
    wheel_path = wheel_path.resolve()
    members = _wheel_members(wheel_path)
    missing_common = sorted(COMMON_REQUIRED_FILES - members)
    missing_assets = sorted(
        label
        for label, suffix in WHEEL_REQUIRED_ASSET_SUFFIXES.items()
        if not any(name.endswith(suffix) for name in members)
    )
    if missing_common or missing_assets:
        raise DistributionInventoryError(
            f"{wheel_path.name}: missing required files={missing_common}, "
            f"missing required assets={missing_assets}"
        )
    roots = {PurePosixPath(name).parts[0] for name in members}
    data_roots = sorted(root for root in roots if root.endswith(".data"))
    dist_info_roots = sorted(root for root in roots if root.endswith(".dist-info"))
    if len(data_roots) != 1 or len(dist_info_roots) != 1:
        raise DistributionInventoryError(
            f"{wheel_path.name}: expected exactly one .data and one .dist-info root; "
            f"found data={data_roots}, dist-info={dist_info_roots}"
        )
    data_prefix = data_roots[0][: -len(".data")]
    dist_info_prefix = dist_info_roots[0][: -len(".dist-info")]
    if data_prefix != dist_info_prefix:
        raise DistributionInventoryError(
            f"{wheel_path.name}: .data and .dist-info roots do not share "
            "the same distribution/version prefix"
        )
    allowed_roots = {"app", "mcp_server.py", data_roots[0], dist_info_roots[0]}
    forbidden = sorted(
        name
        for name in members
        if name == "__main__.py"
        or PurePosixPath(name).parts[0] in WHEEL_FORBIDDEN_TOP_LEVEL
        or PurePosixPath(name).parts[0] not in allowed_roots
    )
    if forbidden:
        raise DistributionInventoryError(f"{wheel_path.name}: forbidden wheel entries: {forbidden}")
    return {"kind": "wheel", "path": str(wheel_path), "members": len(members)}


def verify_sdist(sdist_path: Path) -> dict[str, object]:
    sdist_path = sdist_path.resolve()
    members = _sdist_members(sdist_path)
    missing = sorted(SDIST_REQUIRED_FILES - members)
    if missing:
        raise DistributionInventoryError(f"{sdist_path.name}: missing required files: {missing}")
    forbidden = sorted(
        name for name in members if PurePosixPath(name).parts[0] in SDIST_FORBIDDEN_TOP_LEVEL
    )
    if forbidden:
        raise DistributionInventoryError(f"{sdist_path.name}: forbidden sdist entries: {forbidden}")
    return {"kind": "sdist", "path": str(sdist_path), "members": len(members)}


def _discover_artifacts(inputs: Iterable[Path]) -> tuple[Path, Path]:
    discovered: set[Path] = set()
    for input_path in inputs:
        resolved = input_path.resolve()
        if resolved.is_dir():
            discovered.update(path.resolve() for path in resolved.glob("*.whl"))
            discovered.update(path.resolve() for path in resolved.glob("*.tar.gz"))
            discovered.update(path.resolve() for path in resolved.glob("*.tgz"))
        elif resolved.is_file():
            discovered.add(resolved)
        else:
            raise DistributionInventoryError(f"Artifact path does not exist: {resolved}")
    wheels = sorted(path for path in discovered if path.suffix == ".whl")
    sdists = sorted(
        path for path in discovered if path.name.endswith(".tar.gz") or path.suffix == ".tgz"
    )
    unsupported = sorted(set(discovered) - set(wheels) - set(sdists))
    if unsupported:
        raise DistributionInventoryError(
            f"Unsupported distribution artifacts: {[str(path) for path in unsupported]}"
        )
    if len(wheels) != 1 or len(sdists) != 1:
        raise DistributionInventoryError(
            "Expected exactly one wheel and one sdist; "
            f"found wheels={[path.name for path in wheels]}, "
            f"sdists={[path.name for path in sdists]}"
        )
    return wheels[0], sdists[0]


def verify_distribution_inventory(inputs: Iterable[Path]) -> list[dict[str, object]]:
    wheel, sdist = _discover_artifacts(inputs)
    return [verify_wheel(wheel), verify_sdist(sdist)]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the required and forbidden contents of release archives."
    )
    parser.add_argument("artifacts", nargs="+", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summaries = verify_distribution_inventory(args.artifacts)
    except DistributionInventoryError as exc:
        print(f"DISTRIBUTION INVENTORY FAILED: {exc}", file=sys.stderr)
        return 1
    print("PASS: wheel and sdist inventory satisfy the release contract")
    print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
