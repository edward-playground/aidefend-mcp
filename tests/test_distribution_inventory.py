import io
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 release matrix
    import tomli as tomllib

from scripts.build_release_artifacts import _run_build, _safe_extract_sdist
from scripts.verify_distribution_inventory import (
    SDIST_FORBIDDEN_TOP_LEVEL,
    SDIST_REQUIRED_FILES,
    SDIST_REQUIRED_TEST_FILES,
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
    f"aidefend_mcp-1.3.0.data{suffix}" for suffix in WHEEL_REQUIRED_ASSET_SUFFIXES.values()
}
WHEEL_REQUIRED_FILES = COMMON_REQUIRED_FILES | WHEEL_ASSET_FILES


def _requirement_names(path: Path) -> set[str]:
    names = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-r "):
            continue
        names.add(Requirement(line).name.lower())
    return names


def _parsed_requirements(path: Path) -> list[Requirement]:
    requirements = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-r "):
            continue
        requirements.append(Requirement(line))
    return requirements


def _requirement_signature(value: Requirement) -> tuple[str, str, str]:
    return value.name.lower(), str(value.specifier), str(value.marker)


def test_direct_import_dependencies_are_explicit_in_both_install_surfaces():
    repository_root = Path(__file__).resolve().parents[1]
    runtime_requirements = _requirement_names(repository_root / "requirements.txt")
    dev_requirements = _requirement_names(repository_root / "requirements-dev.txt")
    with (repository_root / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)["project"]
    runtime_metadata = {Requirement(value).name.lower() for value in project["dependencies"]}
    dev_metadata = {
        Requirement(value).name.lower() for value in project["optional-dependencies"]["dev"]
    }

    direct_runtime = {"anyio", "numpy", "onnxruntime", "pyarrow"}
    direct_release_and_test = {"httpx2", "packaging", "tokenizers", "tomli"}
    assert direct_runtime <= runtime_requirements
    assert direct_runtime <= runtime_metadata
    assert direct_release_and_test <= dev_requirements
    assert direct_release_and_test <= dev_metadata


def test_dev_extra_matches_the_audited_requirement_contract():
    repository_root = Path(__file__).resolve().parents[1]
    audited = {
        _requirement_signature(value)
        for value in _parsed_requirements(repository_root / "requirements-dev.txt")
    }
    with (repository_root / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)["project"]
    dev_extra = {
        _requirement_signature(Requirement(value))
        for value in project["optional-dependencies"]["dev"]
    }

    assert dev_extra <= audited


def test_python_314_onnxruntime_contract_matches_fastembed_backend_ranges():
    repository_root = Path(__file__).resolve().parents[1]
    requirements = _parsed_requirements(repository_root / "requirements.txt")
    with (repository_root / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)["project"]
    metadata_requirements = [Requirement(value) for value in project["dependencies"]]

    requires_python = SpecifierSet(project["requires-python"])
    assert Version("3.9") not in requires_python
    assert Version("3.14") in requires_python
    assert "Programming Language :: Python :: 3.14" in project["classifiers"]

    requirement_onnx = [value for value in requirements if value.name.lower() == "onnxruntime"]
    metadata_onnx = [
        value for value in metadata_requirements if value.name.lower() == "onnxruntime"
    ]

    assert {_requirement_signature(value) for value in requirement_onnx} == {
        _requirement_signature(value) for value in metadata_onnx
    }

    for python_version in ("3.10", "3.11", "3.12", "3.13", "3.14", "3.15"):
        environment = default_environment()
        environment["python_version"] = python_version
        environment["python_full_version"] = f"{python_version}.0"
        matching = [
            value
            for value in requirement_onnx
            if value.marker is None or value.marker.evaluate(environment)
        ]
        assert len(matching) == 1, (python_version, matching)
        if Version(python_version) >= Version("3.14"):
            assert Version("1.24.2") in matching[0].specifier
            assert Version("1.24.1") not in matching[0].specifier


def test_pep561_classifier_requires_a_packaged_marker():
    """Do not advertise a typed public package without the PEP 561 marker."""
    repository_root = Path(__file__).resolve().parents[1]
    with (repository_root / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)["project"]

    if "Typing :: Typed" in project.get("classifiers", []):
        assert (repository_root / "app" / "py.typed").is_file()


def test_release_build_subprocess_forces_utf8(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs

    monkeypatch.setattr("scripts.build_release_artifacts.subprocess.run", fake_run)

    _run_build("--sdist", "--outdir", "release-output")

    assert captured["argv"][:3] == [sys.executable, "-m", "build"]
    assert captured["kwargs"]["check"] is True
    environment = captured["kwargs"]["env"]
    assert environment["PYTHONUTF8"] == "1"
    assert environment["PYTHONIOENCODING"] == "utf-8"


def _metadata_payload(
    requires_dist=None,
    *,
    name: str = "aidefend-mcp",
    version: str = "1.3.0",
) -> bytes:
    selected = _expected_requires_dist_lines() if requires_dist is None else list(requires_dist)
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
    metadata_version: str = "1.3.0",
) -> Path:
    selected = set(WHEEL_REQUIRED_FILES) if members is None else set(members)
    metadata_member = "aidefend_mcp-1.3.0.dist-info/METADATA"
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
            info = tarfile.TarInfo(f"aidefend_mcp-1.3.0/{member}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return path


def test_valid_wheel_and_sdist_inventory_passes(tmp_path):
    wheel = _write_wheel(tmp_path / "aidefend_mcp-1.3.0-py3-none-any.whl")
    sdist = _write_sdist(tmp_path / "aidefend_mcp-1.3.0.tar.gz")

    summaries = verify_distribution_inventory([tmp_path])

    assert {summary["kind"] for summary in summaries} == {"wheel", "sdist"}
    assert verify_wheel(wheel)["members"]
    assert verify_sdist(sdist)["members"]


@pytest.mark.parametrize("missing", sorted(WHEEL_REQUIRED_FILES))
def test_wheel_rejects_every_missing_runtime_file(tmp_path, missing):
    wheel = _write_wheel(
        tmp_path / "aidefend_mcp-1.3.0-py3-none-any.whl",
        WHEEL_REQUIRED_FILES - {missing},
    )
    with pytest.raises(DistributionInventoryError, match="missing required"):
        verify_wheel(wheel)


@pytest.mark.parametrize("missing", sorted(SDIST_REQUIRED_FILES))
def test_sdist_rejects_every_missing_runtime_file(tmp_path, missing):
    sdist = _write_sdist(
        tmp_path / "aidefend_mcp-1.3.0.tar.gz",
        SDIST_REQUIRED_FILES - {missing},
    )
    with pytest.raises(DistributionInventoryError, match="missing required"):
        verify_sdist(sdist)


def test_release_contract_requires_generation_identity_runtime_module():
    assert "app/generation_identity.py" in COMMON_REQUIRED_FILES


def test_release_contract_requires_sdist_test_support_files():
    assert {
        "LICENSE",
        "THIRD_PARTY_CONTENT.md",
        "tests/__init__.py",
        "tests/README.md",
        "tests/fixtures/test_example.js",
        "tests/framework_migration_fixtures.py",
        "vendor/README.md",
    } <= SDIST_REQUIRED_TEST_FILES


def test_release_contract_requires_wheel_license_and_attribution_assets():
    assert {
        "service license",
        "third-party attribution",
        "vendored Acorn license",
        "vendored Acorn documentation",
    } <= WHEEL_REQUIRED_ASSET_SUFFIXES.keys()


def test_release_contract_requires_sdist_test_imports_and_static_inputs():
    assert {
        ".dockerignore",
        ".gitignore",
        ".github/workflows/ci.yml",
        "Dockerfile",
        "INSTALL.md",
        "INSTALL-繁體中文.md",
        "README-繁體中文.md",
        "docker-compose.yml",
        "requirements.txt",
        "scripts/build_release_artifacts.py",
        "scripts/create_lancedb_index.py",
        "scripts/install.py",
        "scripts/smoke_all_tools.py",
        "scripts/verify_distribution_inventory.py",
        "scripts/verify_index_manifest.py",
    } <= SDIST_REQUIRED_TEST_FILES


@pytest.mark.parametrize("missing", sorted(SDIST_REQUIRED_TEST_FILES))
def test_sdist_rejects_missing_test_support_file(tmp_path, missing):
    sdist = _write_sdist(
        tmp_path / "aidefend_mcp-1.3.0.tar.gz",
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
        tmp_path / "aidefend_mcp-1.3.0-py3-none-any.whl",
        WHEEL_REQUIRED_FILES | {forbidden},
    )
    with pytest.raises(DistributionInventoryError, match="forbidden wheel entries"):
        verify_wheel(wheel)


@pytest.mark.parametrize("directory", sorted(SDIST_FORBIDDEN_TOP_LEVEL))
def test_sdist_rejects_workspace_contamination(tmp_path, directory):
    sdist = _write_sdist(
        tmp_path / "aidefend_mcp-1.3.0.tar.gz",
        SDIST_REQUIRED_FILES | {f"{directory}/contamination.txt"},
    )
    with pytest.raises(DistributionInventoryError, match="forbidden sdist entries"):
        verify_sdist(sdist)


@pytest.mark.parametrize(
    "forbidden",
    [
        ".env.production",
        "app/__pycache__/core.cpython-313.pyc",
        "tests/.pytest_cache/state.json",
        "app/cache/model.bin",
        "app/logs/service.log",
        "assets/search-index.lancedb/data.bin",
        "runtime.log",
        ".mcp.json",
        ".coverage",
        "coverage.xml",
        "private-key.pem",
        "credentials-production.json",
        "secrets-local.json",
        "team-credentials.yaml",
        "deployment-secrets.yml",
        "signing-key.p8",
        "putty-private-key.ppk",
        ".npmrc",
        "runtime.sqlite3",
    ],
)
def test_sdist_rejects_nested_or_pattern_workspace_contamination(tmp_path, forbidden):
    sdist = _write_sdist(
        tmp_path / "aidefend_mcp-1.3.0.tar.gz",
        SDIST_REQUIRED_FILES | {forbidden},
    )

    with pytest.raises(DistributionInventoryError, match="forbidden sdist entries"):
        verify_sdist(sdist)


def test_sdist_allows_public_environment_example(tmp_path):
    sdist = _write_sdist(
        tmp_path / "aidefend_mcp-1.3.0.tar.gz",
        SDIST_REQUIRED_FILES | {".env.example"},
    )

    assert verify_sdist(sdist)["members"]


def test_distribution_directory_rejects_duplicate_artifact_kinds(tmp_path):
    _write_wheel(tmp_path / "aidefend_mcp-1.3.0-py3-none-any.whl")
    _write_wheel(tmp_path / "aidefend_mcp-1.2.1-py3-none-any.whl")
    _write_sdist(tmp_path / "aidefend_mcp-1.3.0.tar.gz")
    with pytest.raises(DistributionInventoryError, match="exactly one wheel and one sdist"):
        verify_distribution_inventory([tmp_path])


def test_wheel_rejects_archive_traversal(tmp_path):
    wheel = tmp_path / "aidefend_mcp-1.3.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, mode="w") as archive:
        archive.writestr("../escape.py", b"fixture")
    with pytest.raises(DistributionInventoryError, match="unsafe archive member"):
        verify_wheel(wheel)


def test_wheel_rejects_duplicate_archive_members(tmp_path):
    wheel = tmp_path / "aidefend_mcp-1.3.0-py3-none-any.whl"
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
        tmp_path / "aidefend_mcp-1.3.0-py3-none-any.whl",
        WHEEL_REQUIRED_FILES | {extra},
    )
    with pytest.raises(DistributionInventoryError, match="exactly one"):
        verify_wheel(wheel)


def test_wheel_rejects_mismatched_data_and_metadata_prefixes(tmp_path):
    members = {
        name.replace("aidefend_mcp-1.3.0.data", "wrong-1.3.0.data") for name in WHEEL_REQUIRED_FILES
    }
    wheel = _write_wheel(
        tmp_path / "aidefend_mcp-1.3.0-py3-none-any.whl",
        members,
    )
    with pytest.raises(DistributionInventoryError, match="same distribution/version"):
        verify_wheel(wheel)


def test_wheel_rejects_requires_dist_that_differs_from_pyproject(tmp_path):
    wheel = _write_wheel(
        tmp_path / "aidefend_mcp-1.3.0-py3-none-any.whl",
        requires_dist=["attacker-package==9.9.9"],
    )

    with pytest.raises(
        DistributionInventoryError,
        match="METADATA dependencies differ from pyproject.toml",
    ):
        verify_wheel(wheel)


@pytest.mark.parametrize(
    ("metadata_name", "metadata_version"),
    [("attacker-project", "1.3.0"), ("aidefend-mcp", "9.9.9")],
)
def test_wheel_rejects_metadata_identity_that_differs_from_pyproject(
    tmp_path, metadata_name, metadata_version
):
    wheel = _write_wheel(
        tmp_path / "aidefend_mcp-1.3.0-py3-none-any.whl",
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
        link = tarfile.TarInfo("aidefend_mcp-1.3.0/link")
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

    assert extracted == tmp_path / "extract" / "aidefend_mcp-1.3.0"
    assert (extracted / "pyproject.toml").read_bytes() == b"fixture"
    assert (extracted / "app" / "__init__.py").read_bytes() == b"fixture"


def test_sdist_builder_rejects_traversal_before_extraction(tmp_path):
    sdist = tmp_path / "traversal.tar.gz"
    with tarfile.open(sdist, mode="w:gz") as archive:
        payload = b"escape"
        info = tarfile.TarInfo("aidefend_mcp-1.3.0/../../escape.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    with pytest.raises(RuntimeError, match="Unsafe sdist member"):
        _safe_extract_sdist(sdist, tmp_path / "extract")
    assert not (tmp_path / "escape.txt").exists()
