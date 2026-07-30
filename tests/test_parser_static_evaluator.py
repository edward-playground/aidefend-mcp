"""Security and compatibility tests for the closed JavaScript static grammar."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.utils import NODE_BINARY, NODE_PARSER_SCRIPT


def _run_module(tmp_path: Path, source: str) -> subprocess.CompletedProcess[str]:
    assert NODE_BINARY, "Node.js is required by the framework parser contract"
    module_path = tmp_path / "static-parser-case.js"
    module_path.write_text(source, encoding="utf-8")
    return subprocess.run(
        [NODE_BINARY, str(NODE_PARSER_SCRIPT), str(module_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def _parse_expression(tmp_path: Path, expression: str) -> object:
    completed = _run_module(tmp_path, f"export default {{ value: {expression} }};")
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)["value"]


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ('["alpha", "beta"].join("")', "alphabeta"),
        (
            '["alpha OLD", " omega"].join("").replace("OLD", "NEW")'
            '.replace("omega", "tail")',
            "alpha NEW tail",
        ),
        (
            '["first", "<code>second</code>"]'
            '.map((section, index) => index === 1'
            ' ? section.replace("<code>", "<code># header\\n") : section)'
            '.join("")',
            "first<code># header\nsecond</code>",
        ),
        (r"String.raw`line\nnext`", r"line\nnext"),
        ('"static " + "concatenation"', "static concatenation"),
    ],
)
def test_closed_static_grammar_materializes_known_expressions(
    tmp_path: Path,
    expression: str,
    expected: str,
):
    assert _parse_expression(tmp_path, expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        'eval("2 + 2")',
        'Function("return 4")()',
        'new Function("return 4")()',
        'import("./payload.mjs")',
        'fetch("https://example.invalid/")',
        'require("fs").readFileSync("secret")',
        'process.getBuiltinModule("child_process").execSync("whoami")',
        '["safe"]["join"]("")',
        '["safe"]?.join("")',
        '["safe"].concat(["dynamic"]).join("")',
        "outside",
        '["safe", ...outside]',
        "({ ...outside })",
        "({ [outside]: \"safe\" })",
        "`safe ${outside}`",
        '["a"].join("").replace(/a/, "b")',
        '["a"].join("").replace("a", (value) => value)',
        '"abcX".replace("X", "$`$`")',
        '["safe"].map(transform).join("")',
        '["safe"].map((section) => { return section; }).join("")',
        '["safe"].map(async (section) => section).join("")',
        '["safe"].map(([section]) => section).join("")',
        '["safe"].map((String) => String.raw`shadowed`).join("")',
        (
            '["safe"].map((String) => ["nested"].map((section) => '
            'String.raw`shadowed`).join("")).join("")'
        ),
        '({ "__proto__": { injected: true } })',
        (
            '["safe"].map((section, index) => index === 0'
            ' ? section : fetch("https://example.invalid/")).join("")'
        ),
    ],
)
def test_unknown_or_effectful_ast_is_rejected_fail_closed(
    tmp_path: Path,
    expression: str,
):
    completed = _run_module(
        tmp_path,
        f"export default {{ value: {expression} }};",
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "Static evaluation rejected" in completed.stderr


def test_rejected_source_cannot_create_a_side_effect_marker(tmp_path: Path):
    marker = tmp_path / "must-not-exist.txt"
    marker_literal = json.dumps(str(marker))
    completed = _run_module(
        tmp_path,
        "export default { value: ("
        f'process.getBuiltinModule("fs").writeFileSync({marker_literal}, "owned"),'
        ' "apparently-safe") };',
    )

    assert completed.returncode != 0
    assert not marker.exists()


def test_unselected_map_branch_is_still_prevalidated(tmp_path: Path):
    completed = _run_module(
        tmp_path,
        'export default { value: ["safe"].map((section, index) => '
        'index === 0 ? section : eval("unreachable")).join("") };',
    )

    assert completed.returncode != 0
    assert "Static evaluation rejected" in completed.stderr


def test_named_export_cannot_shadow_string_raw_intrinsic(tmp_path: Path):
    completed = _run_module(
        tmp_path,
        "export const String = { value: String.raw`shadowed` };",
    )

    assert completed.returncode != 0
    assert "Named export binding 'String' is unsupported" in completed.stderr


def test_maximum_call_chain_depth_is_enforced(tmp_path: Path):
    accepted = '["x"].join("")' + '.replace("x", "x")' * 15
    rejected = accepted + '.replace("x", "x")'

    assert _parse_expression(tmp_path, accepted) == "x"
    completed = _run_module(
        tmp_path,
        f"export default {{ value: {rejected} }};",
    )
    assert completed.returncode != 0
    assert "call chain exceeds 16 operations" in completed.stderr


def test_maximum_array_length_is_enforced(tmp_path: Path):
    expression = "[" + ",".join('"x"' for _ in range(4_097)) + "]"
    completed = _run_module(
        tmp_path,
        f"export default {{ value: {expression} }};",
    )

    assert completed.returncode != 0
    assert "array exceeds 4096 elements" in completed.stderr


def test_maximum_string_result_length_is_enforced(tmp_path: Path):
    expression = json.dumps("x" * 1_048_577)
    completed = _run_module(
        tmp_path,
        f"export default {{ value: {expression} }};",
    )

    assert completed.returncode != 0
    assert "string result exceeds 1048576 characters" in completed.stderr


def test_join_length_is_preflighted_before_native_allocation(tmp_path: Path):
    large_literal = json.dumps("x" * 700_000)
    completed = _run_module(
        tmp_path,
        'export default { value: ["first", "second"]'
        f".map((section) => {large_literal}).join(\"\") }};",
    )

    assert completed.returncode != 0
    assert "string result exceeds 1048576 characters" in completed.stderr


def test_map_aggregate_length_is_bounded(tmp_path: Path):
    large_literal = json.dumps("x" * 1_048_576)
    source = ",".join('"item"' for _ in range(17))
    completed = _run_module(
        tmp_path,
        f"export default {{ value: [{source}].map((section) => {large_literal}) }};",
    )

    assert completed.returncode != 0
    assert "map result exceeds 16777216 aggregate characters" in completed.stderr


def test_serialized_output_is_preflighted_before_json_stringify(tmp_path: Path):
    large_literal = json.dumps("x" * 1_000_000)
    source = ",".join('"item"' for _ in range(9))
    completed = _run_module(
        tmp_path,
        "export default {"
        f" first: [{source}].map((section) => {large_literal}),"
        f" second: [{source}].map((section) => {large_literal})"
        " };",
    )

    assert completed.returncode != 0
    assert "serialized output exceeds 16777216 characters" in completed.stderr


def test_maximum_operation_count_is_enforced(tmp_path: Path):
    properties = ",".join(f"k{index}:0" for index in range(25_000))
    completed = _run_module(tmp_path, f"export default {{{properties}}};")

    assert completed.returncode != 0
    assert "operation count exceeds 50000" in completed.stderr


def test_maximum_ast_node_count_is_enforced(tmp_path: Path):
    properties = ",".join(f"k{index}:0" for index in range(34_000))
    completed = _run_module(tmp_path, f"export default {{{properties}}};")

    assert completed.returncode != 0
    assert "JavaScript AST exceeds 100000 nodes" in completed.stderr


def test_maximum_token_count_aborts_during_parse(tmp_path: Path):
    elements = ",".join("0" for _ in range(75_001))
    completed = _run_module(
        tmp_path,
        f"export default {{ value: [{elements}] }};",
    )

    assert completed.returncode != 0
    assert "JavaScript token count exceeds 150000" in completed.stderr


def test_maximum_syntax_nesting_aborts_during_parse(tmp_path: Path):
    expression = "[" * 257 + '"x"' + "]" * 257
    completed = _run_module(
        tmp_path,
        f"export default {{ value: {expression} }};",
    )

    assert completed.returncode != 0
    assert "JavaScript syntax nesting exceeds 256" in completed.stderr
