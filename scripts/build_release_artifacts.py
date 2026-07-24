#!/usr/bin/env python3
"""Build an sdist, then build and verify a wheel from a clean extraction."""

from __future__ import annotations

import argparse
import shutil

# The only subprocess is the fixed current-interpreter ``-m build`` command.
import subprocess  # nosec B404
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Sequence

if __package__:
    from .verify_distribution_inventory import verify_distribution_inventory
else:
    from verify_distribution_inventory import verify_distribution_inventory


def _run_build(*arguments: str) -> None:
    # A fixed argv prefix is used and no shell is involved.
    subprocess.run(  # nosec B603
        [sys.executable, "-m", "build", *arguments],
        check=True,
    )


def _safe_extract_sdist(sdist_path: Path, destination: Path) -> Path:
    """Extract only ordinary files/directories whose resolved paths stay inside destination."""
    destination = destination.resolve()
    with tarfile.open(sdist_path, mode="r:gz") as archive:
        members = archive.getmembers()
        roots: set[str] = set()
        normalized_names: set[str] = set()
        for member in members:
            raw_name = member.name
            name = PurePosixPath(raw_name)
            if (
                not raw_name
                or "\\" in raw_name
                or name.is_absolute()
                or ".." in name.parts
                or not name.parts
                or ":" in name.parts[0]
            ):
                raise RuntimeError(f"Unsafe sdist member: {raw_name!r}")
            normalized = "/".join(name.parts)
            if normalized in normalized_names:
                raise RuntimeError(f"Duplicate sdist member: {raw_name!r}")
            normalized_names.add(normalized)
            target = destination.joinpath(*name.parts).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise RuntimeError(f"Unsafe sdist member: {raw_name!r}") from exc
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise RuntimeError(f"Unsupported sdist member type: {raw_name!r}")
            roots.add(name.parts[0])
        if len(roots) != 1:
            raise RuntimeError(f"Expected one sdist root, found: {sorted(roots)}")
        for member in members:
            name = PurePosixPath(member.name)
            target = destination.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"Could not read sdist member: {member.name!r}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)

    extracted_root = destination / next(iter(roots))
    if not extracted_root.is_dir():
        raise RuntimeError(f"Extracted sdist root is missing: {extracted_root}")
    return extracted_root


def build_release_artifacts(
    source_root: Path,
    output_directory: Path,
) -> tuple[Path, Path]:
    source_root = source_root.resolve()
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    existing = (
        sorted(output_directory.glob("*.whl"))
        + sorted(output_directory.glob("*.tar.gz"))
        + sorted(output_directory.glob("*.tgz"))
    )
    if existing:
        raise RuntimeError(
            "Output directory already contains distribution artifacts: "
            f"{[path.name for path in existing]}"
        )

    _run_build("--sdist", "--outdir", str(output_directory), str(source_root))
    sdists = sorted(output_directory.glob("*.tar.gz"))
    if len(sdists) != 1:
        raise RuntimeError(f"Expected one built sdist, found: {sdists}")

    with tempfile.TemporaryDirectory(prefix="aidefend-clean-sdist-") as temp_directory:
        extracted_root = _safe_extract_sdist(sdists[0], Path(temp_directory))
        _run_build(
            "--wheel",
            "--outdir",
            str(output_directory),
            str(extracted_root),
        )

    wheels = sorted(output_directory.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected one built wheel, found: {wheels}")
    verify_distribution_inventory([output_directory])
    return sdists[0], wheels[0]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build release artifacts without reusing the checkout's build tree."
    )
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--outdir", type=Path, default=Path("dist"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        sdist, wheel = build_release_artifacts(args.source, args.outdir)
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        tarfile.TarError,
    ) as exc:
        print(f"RELEASE BUILD FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Built and verified clean sdist: {sdist}")
    print(f"Built and verified clean wheel: {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
