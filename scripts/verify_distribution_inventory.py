#!/usr/bin/env python3
"""Fail closed when release archives are incomplete or workspace-contaminated."""

from __future__ import annotations

import argparse
from collections import Counter
from email.message import Message
from email.parser import Parser
import json
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

from packaging.markers import Marker
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 release jobs
    import tomli as tomllib


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
    "app/framework_migrations.py",
    "app/framework_utils.py",
    "app/generation_identity.py",
    "app/instance_lock.py",
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
SDIST_REQUIRED_TEST_FILES = {
    ".dockerignore",
    ".gitignore",
    ".github/workflows/ci.yml",
    "Dockerfile",
    "INSTALL.md",
    "INSTALL-繁體中文.md",
    "README-繁體中文.md",
    "docker-compose.yml",
    "LICENSE",
    "requirements.txt",
    "scripts/build_release_artifacts.py",
    "scripts/create_lancedb_index.py",
    "scripts/install.py",
    "scripts/smoke_all_tools.py",
    "scripts/verify_distribution_inventory.py",
    "scripts/verify_index_manifest.py",
    "tests/__init__.py",
    "tests/README.md",
    "tests/fixtures/test_example.js",
    "tests/framework_migration_fixtures.py",
    "THIRD_PARTY_CONTENT.md",
    "vendor/README.md",
}
SDIST_REQUIRED_FILES = (
    COMMON_REQUIRED_FILES
    | SDIST_REQUIRED_TEST_FILES
    | {
        "parse_js_module.mjs",
        "vendor/acorn.mjs",
        "vendor/ACORN-LICENSE",
    }
)
WHEEL_REQUIRED_ASSET_SUFFIXES = {
    "service license": "/data/LICENSE",
    "third-party attribution": "/data/THIRD_PARTY_CONTENT.md",
    "parser": "/data/parse_js_module.mjs",
    "vendored Acorn runtime": "/data/vendor/acorn.mjs",
    "vendored Acorn license": "/data/vendor/ACORN-LICENSE",
    "vendored Acorn documentation": "/data/vendor/README.md",
}
WHEEL_FORBIDDEN_TOP_LEVEL = {"build", "data", "tests", "node_modules"}
SDIST_FORBIDDEN_TOP_LEVEL = {
    ".agents",
    ".cache",
    ".claude",
    ".codex",
    ".env",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "build",
    "data",
    "devtools",
    "dist",
    "env",
    "ENV",
    "htmlcov",
    "logs",
    "models",
    "node_modules",
    "temp",
    "test-artifacts",
    "tmp",
    "venv",
    "wheels",
}
SDIST_FORBIDDEN_PATH_COMPONENTS = {
    ".agents",
    ".cache",
    ".claude",
    ".codex",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "cache",
    "logs",
    "test-artifacts",
}
SDIST_FORBIDDEN_EXACT_FILENAMES = {
    ".coverage",
    ".mcp.json",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "_netrc",
    "bandit-report.json",
    "coverage.xml",
    "safety-report.json",
}
SDIST_FORBIDDEN_SECRET_SUFFIXES = (
    ".jks",
    ".key",
    ".keystore",
    ".p12",
    ".p8",
    ".pem",
    ".pfx",
    ".ppk",
)
PROJECT_FILE = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _requirement_without_marker(requirement: Requirement) -> str:
    extras = f"[{','.join(sorted(requirement.extras))}]" if requirement.extras else ""
    base = f"{requirement.name}{extras}"
    if requirement.url:
        return f"{base} @ {requirement.url}"
    return f"{base}{requirement.specifier}"


def _load_project_metadata(project_file: Path = PROJECT_FILE) -> dict[str, object]:
    try:
        with project_file.open("rb") as handle:
            return tomllib.load(handle)["project"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise DistributionInventoryError(
            f"Cannot read project metadata from {project_file}: {exc}"
        ) from exc


def _expected_requires_dist_lines(project_file: Path = PROJECT_FILE) -> list[str]:
    """Materialize runtime and optional PEP 508 dependencies from pyproject."""
    project = _load_project_metadata(project_file)
    expected = [str(item) for item in project.get("dependencies", [])]
    for extra, dependencies in project.get("optional-dependencies", {}).items():
        for raw_requirement in dependencies:
            try:
                requirement = Requirement(str(raw_requirement))
            except InvalidRequirement as exc:
                raise DistributionInventoryError(
                    f"Invalid pyproject dependency {raw_requirement!r}: {exc}"
                ) from exc
            extra_marker = f'extra == "{extra}"'
            marker = (
                Marker(f"({requirement.marker}) and {extra_marker}")
                if requirement.marker
                else Marker(extra_marker)
            )
            expected.append(f"{_requirement_without_marker(requirement)}; {marker}")
    return expected


def _requirement_key(raw_requirement: str, *, source: str) -> tuple[object, ...]:
    try:
        requirement = Requirement(raw_requirement)
    except InvalidRequirement as exc:
        raise DistributionInventoryError(
            f"{source}: invalid Requires-Dist value {raw_requirement!r}: {exc}"
        ) from exc
    return (
        canonicalize_name(requirement.name),
        tuple(sorted(canonicalize_name(extra) for extra in requirement.extras)),
        str(requirement.specifier),
        requirement.url or "",
        str(requirement.marker) if requirement.marker else "",
    )


def _read_wheel_metadata(wheel_path: Path, metadata_member: str) -> Message:
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            metadata = archive.read(metadata_member).decode("utf-8")
    except (KeyError, OSError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise DistributionInventoryError(f"{wheel_path.name}: unreadable METADATA: {exc}") from exc
    return Parser().parsestr(metadata)


def _verify_wheel_identity(
    wheel_path: Path,
    metadata: Message,
    dist_info_prefix: str,
    *,
    project_file: Path = PROJECT_FILE,
) -> None:
    project = _load_project_metadata(project_file)
    expected_name = str(project.get("name", ""))
    expected_version = str(project.get("version", ""))
    names = metadata.get_all("Name", [])
    versions = metadata.get_all("Version", [])
    if len(names) != 1 or len(versions) != 1:
        raise DistributionInventoryError(
            f"{wheel_path.name}: METADATA must contain exactly one Name and Version"
        )
    if (
        canonicalize_name(names[0]) != canonicalize_name(expected_name)
        or versions[0] != expected_version
    ):
        raise DistributionInventoryError(
            f"{wheel_path.name}: METADATA identity differs from pyproject.toml; "
            f"expected={expected_name} {expected_version}, "
            f"actual={names[0]} {versions[0]}"
        )
    expected_prefix = f"{canonicalize_name(expected_name).replace('-', '_')}-{expected_version}"
    if dist_info_prefix != expected_prefix:
        raise DistributionInventoryError(
            f"{wheel_path.name}: .dist-info identity differs from pyproject.toml; "
            f"expected={expected_prefix}, actual={dist_info_prefix}"
        )


def _verify_wheel_dependencies(
    wheel_path: Path,
    metadata: Message,
    *,
    project_file: Path = PROJECT_FILE,
) -> None:
    expected = Counter(
        _requirement_key(requirement, source=str(project_file))
        for requirement in _expected_requires_dist_lines(project_file)
    )
    actual = Counter(
        _requirement_key(requirement, source=wheel_path.name)
        for requirement in metadata.get_all("Requires-Dist", [])
    )
    if actual != expected:
        missing = sorted((expected - actual).elements())
        unexpected = sorted((actual - expected).elements())
        raise DistributionInventoryError(
            f"{wheel_path.name}: METADATA dependencies differ from pyproject.toml; "
            f"missing={missing}, unexpected={unexpected}"
        )


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
    metadata_member = f"{dist_info_roots[0]}/METADATA"
    if metadata_member not in members:
        raise DistributionInventoryError(f"{wheel_path.name}: missing required METADATA file")
    metadata = _read_wheel_metadata(wheel_path, metadata_member)
    _verify_wheel_identity(wheel_path, metadata, dist_info_prefix)
    _verify_wheel_dependencies(wheel_path, metadata)
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
    forbidden = sorted(name for name in members if _is_forbidden_sdist_member(name))
    if forbidden:
        raise DistributionInventoryError(f"{sdist_path.name}: forbidden sdist entries: {forbidden}")
    return {"kind": "sdist", "path": str(sdist_path), "members": len(members)}


def _is_forbidden_sdist_member(name: str) -> bool:
    """Reject workspace-only files even when they are nested under an allowed root."""
    parts = PurePosixPath(name).parts
    top_level = parts[0]
    filename = parts[-1]
    normalized_filename = filename.lower()
    if top_level in SDIST_FORBIDDEN_TOP_LEVEL:
        return True
    if any(part in SDIST_FORBIDDEN_PATH_COMPONENTS for part in parts):
        return True
    if top_level.startswith(".env.") and top_level != ".env.example":
        return True
    if any(part.endswith(".lancedb") for part in parts):
        return True
    if normalized_filename in SDIST_FORBIDDEN_EXACT_FILENAMES:
        return True
    if normalized_filename.endswith(SDIST_FORBIDDEN_SECRET_SUFFIXES):
        return True
    if normalized_filename.endswith((".json", ".yaml", ".yml")) and any(
        marker in normalized_filename for marker in ("credential", "secret")
    ):
        return True
    return normalized_filename.endswith((".db", ".log", ".pyc", ".pyo", ".sqlite", ".sqlite3"))


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
