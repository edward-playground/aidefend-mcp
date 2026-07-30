import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.build_release_artifacts import _safe_extract_sdist
from scripts.verify_distribution_inventory import (
    SDIST_FORBIDDEN_TOP_LEVEL,
    SDIST_REQUIRED_FILES,
    WHEEL_FORBIDDEN_TOP_LEVEL,
    WHEEL_REQUIRED_ASSET_SUFFIXES,
    COMMON_REQUIRED_FILES,
    DistributionInventoryError,
    _expected_requires_dist_lines,
    verify_distribution_inventory,
    verify_sdist,
    verify_wheel,
)


WHEEL_ASSET_FILES = {
    f"aidefend_mcp-1.2.0.data{suffix}" for suffix in WHEEL_REQUIRED_ASSET_SUFFIXES.values()
}
WHEEL_REQUIRED_FILES = COMMON_REQUIRED_FILES | WHEEL_ASSET_FILES


def _metadata_payload(
    requires_dist=None,
    *,
    name: str = "aidefend-mcp",
    version: str = "1.2.0",
) -> bytes:
    selected = (
        _expected_requires_dist_lines()
        if requires_dist is None
        else list(requires_dist)
    )
    lines = [
        "Metadata-Version: 2.4",
        f"Name: {name}",
        f"Version: {version}",
        *(f"Requires-Dist: {requirement}" for requirement in selected),
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _write_wheel(
    path: Path,
    members=None,
    *,
    requires_dist=None,
    metadata_name: str = "aidefend-mcp",
    metadata_version: str = "1.2.0",
) -> Path:
    selected = set(WHEEL_REQUIRED_FILES) if members is None else set(members)
    metadata_member = "aidefend_mcp-1.2.0.dist-info/METADATA"
    selected.add(metadata_member)
    with zipfile.ZipFile(path, mode="w") as archive:
        for member in sorted(selected):
            payload = (
                _metadata_payload(
                    requires_dist,
                    name=metadata_name,
                    version=metadata_version,
                )
                if member == metadata_member
                else b"fixture"
            )
            archive.writestr(member, payload)
    return path


def _write_sdist(path: Path, members=None) -> Path:
    selected = SDIST_REQUIRED_FILES if members is None else set(members)
    with tarfile.open(path, mode="w:gz") as archive:
        for member in sorted(selected):
            payload = b"fixture"
            info = tarfile.TarInfo(f"aidefend_mcp-1.2.0/{member}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return path


def test_valid_wheel_and_sdist_inventory_passes(tmp_path):
    wheel = _write_wheel(tmp_path / "aidefend_mcp-1.2.0-py3-none-any.whl")
    sdist = _write_sdist(tmp_path / "aidefend_mcp-1.2.0.tar.gz")

    summaries = verify_distribution_inventory([tmp_path])

    assert {summary["kind"] for summary in summaries} == {"wheel", "sdist"}
    assert verify_wheel(wheel)["members"]
    assert verify_sdist(sdist)["members"]


@pytest.mark.parametrize("missing", sorted(WHEEL_REQUIRED_FILES))
def test_wheel_rejects_every_missing_runtime_file(tmp_path, missing):
    wheel = _write_wheel(
        tmp_path / "aidefend_mcp-1.2.0-py3-none-any.whl",
        WHEEL_REQUIRED_FILES - {missing},
    )
    with pytest.raises(DistributionInventoryError, match="missing required"):
        verify_wheel(wheel)


@pytest.mark.parametrize("missing", sorted(SDIST_REQUIRED_FILES))
def test_sdist_rejects_every_missing_runtime_file(tmp_path, missing):
    sdist = _write_sdist(
        tmp_path / "aidefend_mcp-1.2.0.tar.gz",
        SDIST_REQUIRED_FILES - {missing},
    )
    with pytest.raises(DistributionInventoryError, match="missing required"):
        verify_sdist(sdist)


@pytest.mark.parametrize(
    "forbidden",
    ["__main__.py"]
    + [f"{directory}/contamination.txt" for directory in sorted(WHEEL_FORBIDDEN_TOP_LEVEL)]
    + ["stale_top_level_module.py"],
)
def test_wheel_rejects_workspace_contamination(tmp_path, forbidden):
    wheel = _write_wheel(
        tmp_path / "aidefend_mcp-1.2.0-py3-none-any.whl",
        WHEEL_REQUIRED_FILES | {forbidden},
    )
    with pytest.raises(DistributionInventoryError, match="forbidden wheel entries"):
        verify_wheel(wheel)


@pytest.mark.parametrize("directory", sorted(SDIST_FORBIDDEN_TOP_LEVEL))
def test_sdist_rejects_workspace_contamination(tmp_path, directory):
    sdist = _write_sdist(
        tmp_path / "aidefend_mcp-1.2.0.tar.gz",
        SDIST_REQUIRED_FILES | {f"{directory}/contamination.txt"},
    )
    with pytest.raises(DistributionInventoryError, match="forbidden sdist entries"):
        verify_sdist(sdist)


def test_distribution_directory_rejects_duplicate_artifact_kinds(tmp_path):
    _write_wheel(tmp_path / "aidefend_mcp-1.2.0-py3-none-any.whl")
    _write_wheel(tmp_path / "aidefend_mcp-1.2.1-py3-none-any.whl")
    _write_sdist(tmp_path / "aidefend_mcp-1.2.0.tar.gz")
    with pytest.raises(DistributionInventoryError, match="exactly one wheel and one sdist"):
        verify_distribution_inventory([tmp_path])


def test_wheel_rejects_archive_traversal(tmp_path):
    wheel = tmp_path / "aidefend_mcp-1.2.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, mode="w") as archive:
        archive.writestr("../escape.py", b"fixture")
    with pytest.raises(DistributionInventoryError, match="unsafe archive member"):
        verify_wheel(wheel)


def test_wheel_rejects_duplicate_archive_members(tmp_path):
    wheel = tmp_path / "aidefend_mcp-1.2.0-py3-none-any.whl"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(wheel, mode="w") as archive:
            archive.writestr("app/__init__.py", b"first")
            archive.writestr("app/__init__.py", b"second")
    with pytest.raises(DistributionInventoryError, match="duplicate member names"):
        verify_wheel(wheel)


@pytest.mark.parametrize(
    "extra",
    [
        "stale-1.0.data/data/garbage.txt",
        "stale-1.0.dist-info/METADATA",
    ],
)
def test_wheel_rejects_second_metadata_root(tmp_path, extra):
    wheel = _write_wheel(
        tmp_path / "aidefend_mcp-1.2.0-py3-none-any.whl",
        WHEEL_REQUIRED_FILES | {extra},
    )
    with pytest.raises(DistributionInventoryError, match="exactly one"):
        verify_wheel(wheel)


def test_wheel_rejects_mismatched_data_and_metadata_prefixes(tmp_path):
    members = {
        name.replace("aidefend_mcp-1.2.0.data", "wrong-1.2.0.data") for name in WHEEL_REQUIRED_FILES
    }
    wheel = _write_wheel(
        tmp_path / "aidefend_mcp-1.2.0-py3-none-any.whl",
        members,
    )
    with pytest.raises(DistributionInventoryError, match="same distribution/version"):
        verify_wheel(wheel)


def test_wheel_rejects_requires_dist_that_differs_from_pyproject(tmp_path):
    wheel = _write_wheel(
        tmp_path / "aidefend_mcp-1.2.0-py3-none-any.whl",
        requires_dist=["attacker-package==9.9.9"],
    )

    with pytest.raises(
        DistributionInventoryError,
        match="METADATA dependencies differ from pyproject.toml",
    ):
        verify_wheel(wheel)


@pytest.mark.parametrize(
    ("metadata_name", "metadata_version"),
    [("attacker-project", "1.2.0"), ("aidefend-mcp", "9.9.9")],
)
def test_wheel_rejects_metadata_identity_that_differs_from_pyproject(
    tmp_path, metadata_name, metadata_version
):
    wheel = _write_wheel(
        tmp_path / "aidefend_mcp-1.2.0-py3-none-any.whl",
        metadata_name=metadata_name,
        metadata_version=metadata_version,
    )

    with pytest.raises(
        DistributionInventoryError,
        match="METADATA identity differs from pyproject.toml",
    ):
        verify_wheel(wheel)


def test_sdist_builder_rejects_links_before_extraction(tmp_path):
    sdist = tmp_path / "unsafe.tar.gz"
    with tarfile.open(sdist, mode="w:gz") as archive:
        link = tarfile.TarInfo("aidefend_mcp-1.2.0/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../escape"
        archive.addfile(link)
    with pytest.raises(RuntimeError, match="Unsupported sdist member type"):
        _safe_extract_sdist(sdist, tmp_path / "extract")


def test_sdist_builder_extracts_valid_regular_files(tmp_path):
    sdist = _write_sdist(
        tmp_path / "safe.tar.gz",
        {"pyproject.toml", "app/__init__.py"},
    )
    extracted = _safe_extract_sdist(sdist, tmp_path / "extract")

    assert extracted == tmp_path / "extract" / "aidefend_mcp-1.2.0"
    assert (extracted / "pyproject.toml").read_bytes() == b"fixture"
    assert (extracted / "app" / "__init__.py").read_bytes() == b"fixture"


def test_sdist_builder_rejects_traversal_before_extraction(tmp_path):
    sdist = tmp_path / "traversal.tar.gz"
    with tarfile.open(sdist, mode="w:gz") as archive:
        payload = b"escape"
        info = tarfile.TarInfo("aidefend_mcp-1.2.0/../../escape.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    with pytest.raises(RuntimeError, match="Unsafe sdist member"):
        _safe_extract_sdist(sdist, tmp_path / "extract")
    assert not (tmp_path / "escape.txt").exists()
