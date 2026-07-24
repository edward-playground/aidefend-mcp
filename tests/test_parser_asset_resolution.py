from pathlib import Path

import pytest

import app.utils as utils
from scripts.verify_distribution_inventory import (
    REQUIRED_RUNTIME_PYTHON_FILES,
    WHEEL_REQUIRED_ASSET_SUFFIXES,
)


class FakeDistribution:
    def __init__(self, parser: Path | None):
        self.parser = parser
        self.files = (
            (Path("../../parse_js_module.mjs"), Path("metadata/ignored.txt"))
            if parser is not None
            else ()
        )

    def locate_file(self, entry):
        assert self.parser is not None
        assert str(entry).replace("\\", "/").endswith("parse_js_module.mjs")
        return self.parser


def _bundle(root: Path) -> Path:
    parser = root / "parse_js_module.mjs"
    vendor = root / "vendor"
    vendor.mkdir(parents=True)
    parser.write_text("parser", encoding="utf-8")
    (vendor / "acorn.mjs").write_text("acorn", encoding="utf-8")
    (vendor / "ACORN-LICENSE").write_text("license", encoding="utf-8")
    return parser


def _configure(
    monkeypatch,
    *,
    current_root: Path,
    user_root: Path,
    distribution: FakeDistribution | None = None,
) -> None:
    def fake_get_path(name: str, scheme=None):
        assert name == "data"
        return str(user_root if scheme == "test-user" else current_root)

    def fake_distribution(name: str):
        assert name == "aidefend-mcp"
        if distribution is None:
            raise utils.importlib_metadata.PackageNotFoundError(name)
        return distribution

    monkeypatch.setattr(utils.sysconfig, "get_path", fake_get_path)
    monkeypatch.setattr(
        utils.sysconfig,
        "get_preferred_scheme",
        lambda purpose: "test-user" if purpose == "user" else "unexpected",
    )
    monkeypatch.setattr(utils.site, "getuserbase", lambda: str(user_root))
    monkeypatch.setattr(utils.importlib_metadata, "distribution", fake_distribution)


def test_source_complete_bundle_has_first_precedence(tmp_path, monkeypatch):
    source_root = tmp_path / "checkout"
    source_parser = _bundle(source_root)
    current_parser = _bundle(tmp_path / "interpreter")
    user_parser = _bundle(tmp_path / "user-base")
    module_file = source_root / "app" / "utils.py"
    _configure(
        monkeypatch,
        current_root=current_parser.parent,
        user_root=user_parser.parent,
    )

    candidates = utils._node_parser_candidates(module_file)

    assert candidates == (source_parser, current_parser, user_parser)
    assert utils._resolve_node_parser_script(candidates) == source_parser


def test_record_metadata_locates_user_or_custom_prefix_bundle(tmp_path, monkeypatch):
    module_file = tmp_path / "site-packages" / "app" / "utils.py"
    metadata_parser = _bundle(tmp_path / "custom-prefix")
    _configure(
        monkeypatch,
        current_root=tmp_path / "interpreter",
        user_root=tmp_path / "user-base",
        distribution=FakeDistribution(metadata_parser),
    )

    candidates = utils._node_parser_candidates(module_file)

    assert candidates[1] == metadata_parser
    assert utils._resolve_node_parser_script(candidates) == metadata_parser


def test_incomplete_metadata_bundle_is_skipped_for_complete_user_bundle(tmp_path, monkeypatch):
    module_file = tmp_path / "site-packages" / "app" / "utils.py"
    metadata_parser = tmp_path / "custom-prefix" / "parse_js_module.mjs"
    metadata_parser.parent.mkdir(parents=True)
    metadata_parser.write_text("partial", encoding="utf-8")
    user_parser = _bundle(tmp_path / "user-base")
    _configure(
        monkeypatch,
        current_root=tmp_path / "interpreter",
        user_root=user_parser.parent,
        distribution=FakeDistribution(metadata_parser),
    )

    candidates = utils._node_parser_candidates(module_file)

    assert candidates[1] == metadata_parser
    assert utils._missing_parser_bundle_files(metadata_parser)
    assert utils._resolve_node_parser_script(candidates) == user_parser


def test_runtime_diagnostic_lists_every_missing_bundle_file(tmp_path, monkeypatch):
    raw_path = tmp_path / "raw"
    raw_path.mkdir()
    fixture = raw_path / "fixture.js"
    fixture.write_text("export default {};", encoding="utf-8")
    missing_parser = tmp_path / "missing" / "parse_js_module.mjs"
    monkeypatch.setattr(utils.settings, "RAW_PATH", raw_path)
    monkeypatch.setattr(utils, "NODE_PARSER_SCRIPT", missing_parser)
    monkeypatch.setattr(utils, "NODE_PARSER_CANDIDATES", (missing_parser,))

    with pytest.raises(utils.JavaScriptParserError) as error:
        utils.parse_js_file_with_node(fixture)

    message = str(error.value)
    assert str(missing_parser) in message
    assert str(missing_parser.parent / "vendor" / "acorn.mjs") in message
    assert str(missing_parser.parent / "vendor" / "ACORN-LICENSE") in message


def test_sysconfig_runtime_errors_still_allow_source_bundle(tmp_path, monkeypatch):
    source_root = tmp_path / "checkout"
    source_parser = _bundle(source_root)
    module_file = source_root / "app" / "utils.py"

    def fail(*_args, **_kwargs):
        raise RuntimeError("broken sysconfig")

    monkeypatch.setattr(utils.sysconfig, "get_path", fail)
    monkeypatch.setattr(utils.sysconfig, "get_preferred_scheme", fail)
    monkeypatch.setattr(utils.site, "getuserbase", lambda: None)
    monkeypatch.setattr(
        utils.importlib_metadata,
        "distribution",
        lambda name: (_ for _ in ()).throw(utils.importlib_metadata.PackageNotFoundError(name)),
    )

    candidates = utils._node_parser_candidates(module_file)

    assert candidates == (source_parser,)
    assert utils._resolve_node_parser_script(candidates) == source_parser


def test_distribution_inventory_requires_parser_code_and_complete_bundle():
    assert "app/utils.py" in REQUIRED_RUNTIME_PYTHON_FILES
    assert set(WHEEL_REQUIRED_ASSET_SUFFIXES.values()) == {
        "/data/parse_js_module.mjs",
        "/data/vendor/acorn.mjs",
        "/data/vendor/ACORN-LICENSE",
    }
