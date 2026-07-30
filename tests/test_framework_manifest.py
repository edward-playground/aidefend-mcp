"""Tests for safe, dynamic framework tactic discovery."""

import os
from pathlib import Path

import pytest

from app.config import settings
from app.framework_manifest import (
    FrameworkManifestError,
    load_local_tactic_manifest,
    parse_tactic_manifest,
)


def _manifest(imports: list[tuple[str, str]], members: list[str]) -> str:
    import_lines = "\n".join(
        f"import {{ {binding} }} from './tactics/{filename}';" for binding, filename in imports
    )
    member_lines = ",\n        ".join(members)
    return f"""
        import {{ aidefendIntroduction }} from './aidefend-intro.js';
        {import_lines}

        export const aidefendData = {{
            introduction: aidefendIntroduction,
            tactics: [
                {member_lines}
            ]
        }};
        export default aidefendData;
    """


@pytest.mark.current_snapshot
def test_current_framework_manifest_yields_the_seven_tactics_in_order():
    expected = [
        "model.js",
        "harden.js",
        "detect.js",
        "isolate.js",
        "deceive.js",
        "evict.js",
        "restore.js",
    ]

    if os.getenv("LOCAL_FRAMEWORK_PATH"):
        framework_root = Path(os.environ["LOCAL_FRAMEWORK_PATH"])
        assert load_local_tactic_manifest(framework_root, "tactics") == expected
        return

    # CI stages the immutable upstream manifest directly under RAW_PATH before
    # running the explicit current-snapshot gate; it does not check out a
    # sibling framework repository.
    staged_manifest = settings.RAW_PATH / "main.js"
    if staged_manifest.is_file():
        assert (
            parse_tactic_manifest(staged_manifest.read_text(encoding="utf-8"))
            == expected
        )
        return

    framework_root = Path(__file__).resolve().parents[2] / "aidefense-framework"
    if (framework_root / "main.js").is_file():
        assert load_local_tactic_manifest(framework_root, "tactics") == expected
        return

    pytest.fail("No AIDEFEND framework main.js is available for the release gate")


def test_synthetic_future_manifest_adds_and_renames_tactics_in_framework_order(tmp_path):
    source = _manifest(
        [
            ("modelTactic", "model-foundation.js"),
            ("detectTactic", "detect.js"),
            ("containTactic", "contain.js"),
            ("restoreTactic", "restore.js"),
        ],
        # Deliberately differs from import order: this is the framework's order.
        ["modelTactic", "containTactic", "detectTactic", "restoreTactic"],
    )
    (tmp_path / "main.js").write_text(source, encoding="utf-8")

    assert load_local_tactic_manifest(tmp_path, "tactics") == [
        "model-foundation.js",
        "contain.js",
        "detect.js",
        "restore.js",
    ]


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            _manifest([("escapeTactic", "../escape.js")], ["escapeTactic"]),
            "path traversal",
        ),
        (
            _manifest([("hiddenTactic", ".hidden.js")], ["hiddenTactic"]),
            "unsafe tactic filename",
        ),
        (
            _manifest([("backupTactic", "model.backup.js")], ["backupTactic"]),
            "unsafe tactic filename",
        ),
        (
            _manifest([("moduleTactic", "model.mjs")], ["moduleTactic"]),
            "unsafe tactic filename",
        ),
        (
            _manifest([], []),
            "must not be empty",
        ),
        (
            _manifest(
                [("modelTactic", "model.js"), ("modelAgain", "model.js")],
                ["modelTactic"],
            ),
            "duplicate tactic import",
        ),
        (
            """
                import { modelTactic } from './tactics/model.js';
                import { modelTactic } from './tactics/harden.js';
                export const aidefendData = { tactics: [modelTactic] };
            """,
            "ambiguous tactic import binding",
        ),
        (
            _manifest(
                [("modelTactic", "model.js"), ("unusedTactic", "unused.js")],
                ["modelTactic"],
            ),
            "not included in aidefendData.tactics",
        ),
        (
            _manifest([("modelTactic", "model.js")], ["locallyBuiltTactic"]),
            "is not imported from tactics",
        ),
        (
            _manifest([("modelTactic", "model.js")], ["modelTactic", "modelTactic"]),
            "duplicate identifiers",
        ),
    ],
)
def test_manifest_rejects_unsafe_duplicate_or_ambiguous_sources(source, message):
    with pytest.raises(FrameworkManifestError, match=message):
        parse_tactic_manifest(source)


def test_manifest_rejects_multiple_bindings_for_one_included_tactic_file():
    source = """
        import { modelTactic, modelAlias } from './tactics/model.js';
        export const aidefendData = { tactics: [modelTactic, modelAlias] };
    """

    with pytest.raises(FrameworkManifestError, match="resolve to one file"):
        parse_tactic_manifest(source)


@pytest.mark.parametrize(
    "tactics_path",
    ["", "../tactics", "/tactics", "tactics/../other", ".hidden", "tactics\\nested"],
)
def test_configured_tactics_path_must_be_safe(tactics_path):
    source = _manifest([("modelTactic", "model.js")], ["modelTactic"])

    with pytest.raises(FrameworkManifestError, match="tactics path"):
        parse_tactic_manifest(source, tactics_path=tactics_path)


def test_comments_and_dynamic_import_text_do_not_create_manifest_tactics():
    source = """
        // import { fakeTactic } from './tactics/fake.js';
        const example = `import { fakeAgain } from './tactics/fake-again.js';`;
        import { modelTactic as currentModel } from './tactics/model.js';
        export const aidefendData = {
            "tactics": [currentModel],
        };
        async function loadSomethingElse() {
            return import('./plugins/optional.js');
        }
    """

    assert parse_tactic_manifest(source) == ["model.js"]


def test_semicolonless_static_imports_are_supported():
    source = """
        import { aidefendIntroduction } from './aidefend-intro.js'
        import { modelTactic } from './tactics/model.js'
        import { respondTactic } from './tactics/respond.js'
        export const aidefendData = {
            introduction: aidefendIntroduction,
            tactics: [modelTactic, respondTactic],
        }
    """

    assert parse_tactic_manifest(source) == ["model.js", "respond.js"]


def test_local_helper_fails_closed_when_root_has_no_main_js(tmp_path):
    with pytest.raises(FrameworkManifestError, match="main.js is missing"):
        load_local_tactic_manifest(tmp_path, "tactics")
