"""Discover tactic source files from the framework's root module manifest.

The framework deliberately keeps its ordered tactic list in ``main.js``.  This
module reads that small, static ES-module surface without executing JavaScript.
It accepts only direct imports from the configured tactics directory and a
plain ``aidefendData.tactics`` array of imported identifiers.  Anything
ambiguous fails closed so a sync can retain its last-known-good index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

MAX_MANIFEST_BYTES = 1024 * 1024
_IDENTIFIER_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_SAFE_PATH_SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_SAFE_TACTIC_FILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\.js")


class FrameworkManifestError(ValueError):
    """Raised when ``main.js`` is unsafe, ambiguous, or structurally invalid."""


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str
    offset: int


def _tokenize(source: str) -> list[_Token]:
    """Tokenize the small JavaScript subset needed by the manifest parser."""
    tokens: list[_Token] = []
    index = 0
    length = len(source)

    while index < length:
        char = source[index]
        if char.isspace():
            index += 1
            continue

        if source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = length if newline == -1 else newline + 1
            continue

        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end == -1:
                raise FrameworkManifestError("main.js contains an unterminated block comment")
            index = end + 2
            continue

        identifier = _IDENTIFIER_RE.match(source, index)
        if identifier:
            tokens.append(_Token("identifier", identifier.group(0), index))
            index = identifier.end()
            continue

        if char in {"'", '"', "`"}:
            quote = char
            start = index
            index += 1
            value: list[str] = []
            while index < length:
                char = source[index]
                if char == "\\":
                    if index + 1 >= length:
                        raise FrameworkManifestError("main.js contains an unterminated string")
                    value.append(source[index : index + 2])
                    index += 2
                    continue
                if char == quote:
                    index += 1
                    kind = "template" if quote == "`" else "string"
                    tokens.append(_Token(kind, "".join(value), start))
                    break
                if quote != "`" and char in {"\r", "\n"}:
                    raise FrameworkManifestError("main.js contains a multiline quoted string")
                value.append(char)
                index += 1
            else:
                raise FrameworkManifestError("main.js contains an unterminated string")
            continue

        tokens.append(_Token("punctuation", char, index))
        index += 1

    return tokens


def _validate_tactics_path(tactics_path: str) -> str:
    if not isinstance(tactics_path, str) or not tactics_path:
        raise FrameworkManifestError("configured tactics path must be a non-empty string")
    if tactics_path != tactics_path.strip() or "\\" in tactics_path:
        raise FrameworkManifestError("configured tactics path must use clean POSIX segments")

    parts = tactics_path.split("/")
    if any(
        not part
        or part in {".", ".."}
        or part.startswith(".")
        or not _SAFE_PATH_SEGMENT_RE.fullmatch(part)
        for part in parts
    ):
        raise FrameworkManifestError("configured tactics path is unsafe")
    return "/".join(parts)


def _import_bindings(tokens: Sequence[_Token]) -> list[str]:
    """Return local identifiers from the binding half of an import declaration."""
    if not tokens:
        return []

    bindings: list[str] = []
    index = 0

    if tokens[index].kind == "identifier":
        bindings.append(tokens[index].value)
        index += 1
        if index < len(tokens):
            if tokens[index].value != ",":
                raise FrameworkManifestError("unsupported tactic import binding")
            index += 1

    if index >= len(tokens):
        return bindings

    if tokens[index].value == "*":
        if (
            index + 2 >= len(tokens)
            or tokens[index + 1].value != "as"
            or tokens[index + 2].kind != "identifier"
            or index + 3 != len(tokens)
        ):
            raise FrameworkManifestError("invalid namespace tactic import")
        bindings.append(tokens[index + 2].value)
        return bindings

    if tokens[index].value != "{":
        raise FrameworkManifestError("unsupported tactic import binding")
    index += 1

    while index < len(tokens) and tokens[index].value != "}":
        if tokens[index].kind != "identifier":
            raise FrameworkManifestError("invalid named tactic import")
        imported = tokens[index].value
        index += 1
        local = imported
        if index < len(tokens) and tokens[index].value == "as":
            index += 1
            if index >= len(tokens) or tokens[index].kind != "identifier":
                raise FrameworkManifestError("invalid named tactic import alias")
            local = tokens[index].value
            index += 1
        bindings.append(local)

        if index < len(tokens) and tokens[index].value == ",":
            index += 1
            continue
        if index >= len(tokens) or tokens[index].value != "}":
            raise FrameworkManifestError("invalid named tactic import list")

    if index >= len(tokens) or tokens[index].value != "}" or index + 1 != len(tokens):
        raise FrameworkManifestError("invalid named tactic import list")
    if len(bindings) != len(set(bindings)):
        raise FrameworkManifestError("duplicate local binding in tactic import")
    return bindings


def _parse_imports(
    tokens: Sequence[_Token], tactics_path: str
) -> tuple[dict[str, str], dict[str, set[str]]]:
    prefix = f"./{tactics_path}/"
    bindings_to_files: dict[str, str] = {}
    files_to_bindings: dict[str, set[str]] = {}

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.kind != "identifier" or token.value != "import":
            index += 1
            continue
        if index + 1 < len(tokens) and tokens[index + 1].value in {"(", "."}:
            index += 1
            continue

        declaration_start = index + 1
        if declaration_start >= len(tokens):
            raise FrameworkManifestError("empty import declaration in main.js")

        if tokens[declaration_start].kind == "string":
            source_index = declaration_start
            source_token = tokens[source_index]
            binding_tokens: Sequence[_Token] = []
        else:
            from_index = declaration_start
            while from_index < len(tokens):
                item = tokens[from_index]
                if item.kind == "identifier" and item.value == "from":
                    break
                if item.value == ";" or (
                    from_index > declaration_start
                    and item.kind == "identifier"
                    and item.value == "import"
                ):
                    raise FrameworkManifestError("import declaration must contain exactly one from")
                from_index += 1
            if from_index + 1 >= len(tokens) or tokens[from_index + 1].kind != "string":
                raise FrameworkManifestError("import source must be a quoted literal")
            binding_tokens = tokens[declaration_start:from_index]
            source_index = from_index + 1
            source_token = tokens[source_index]

        # ES modules permit automatic semicolon insertion after an import.
        # Once the quoted source is consumed, continue at the next token; a
        # literal semicolon is consumed when present.
        index = source_index + 1
        if index < len(tokens) and tokens[index].value == ";":
            index += 1

        import_source = source_token.value
        source_parts = import_source.replace("\\", "/").split("/")
        if ".." in source_parts:
            raise FrameworkManifestError("path traversal is not allowed in manifest imports")
        if not import_source.startswith(prefix):
            continue

        basename = import_source[len(prefix) :]
        if "/" in basename or "\\" in import_source or not _SAFE_TACTIC_FILE_RE.fullmatch(basename):
            raise FrameworkManifestError(f"unsafe tactic filename in import: {import_source}")
        if basename in files_to_bindings:
            raise FrameworkManifestError(f"duplicate tactic import: {basename}")

        local_bindings = _import_bindings(binding_tokens)
        if not local_bindings:
            raise FrameworkManifestError(f"tactic import has no usable binding: {basename}")

        binding_set = set(local_bindings)
        for binding in binding_set:
            if binding in bindings_to_files:
                raise FrameworkManifestError(f"ambiguous tactic import binding: {binding}")
            bindings_to_files[binding] = basename
        files_to_bindings[basename] = binding_set

    return bindings_to_files, files_to_bindings


def _find_tactics_array(tokens: Sequence[_Token]) -> list[str]:
    assignments: list[int] = []
    for index, token in enumerate(tokens):
        if token.kind != "identifier" or token.value != "aidefendData":
            continue
        if (
            index + 2 < len(tokens)
            and tokens[index + 1].value == "="
            and tokens[index + 2].value == "{"
        ):
            assignments.append(index + 2)
    if len(assignments) != 1:
        raise FrameworkManifestError("main.js must define exactly one aidefendData object literal")

    object_start = assignments[0]
    depth = 0
    array_starts: list[int] = []
    index = object_start
    while index < len(tokens):
        value = tokens[index].value
        if value == "{":
            depth += 1
        elif value == "}":
            depth -= 1
            if depth == 0:
                break
        elif depth == 1 and (
            (tokens[index].kind == "identifier" and value == "tactics")
            or (tokens[index].kind == "string" and value == "tactics")
        ):
            if (
                index + 2 < len(tokens)
                and tokens[index + 1].value == ":"
                and tokens[index + 2].value == "["
            ):
                array_starts.append(index + 2)
        index += 1
    else:
        raise FrameworkManifestError("aidefendData object is unterminated")

    if len(array_starts) != 1:
        raise FrameworkManifestError("aidefendData must contain exactly one tactics array")

    members: list[str] = []
    index = array_starts[0] + 1
    expect_member = True
    while index < len(tokens):
        token = tokens[index]
        if token.value == "]":
            break
        if expect_member:
            if token.kind != "identifier":
                raise FrameworkManifestError("tactics array must contain imported identifiers only")
            members.append(token.value)
            expect_member = False
        else:
            if token.value != ",":
                raise FrameworkManifestError("tactics array members must be comma-separated")
            expect_member = True
        index += 1
    else:
        raise FrameworkManifestError("tactics array is unterminated")

    if not members:
        raise FrameworkManifestError("aidefendData.tactics must not be empty")
    if len(members) != len(set(members)):
        raise FrameworkManifestError("aidefendData.tactics contains duplicate identifiers")
    return members


def parse_tactic_manifest(source: str, tactics_path: str = "tactics") -> list[str]:
    """Return the unique tactic ``.js`` basenames in framework-defined order.

    The returned order comes from ``aidefendData.tactics`` rather than import
    declaration order.  Imports and array membership must form a one-to-one
    relationship; unused, duplicated, or locally constructed tactics are
    rejected.
    """
    if not isinstance(source, str) or not source.strip():
        raise FrameworkManifestError("main.js manifest must not be empty")
    safe_tactics_path = _validate_tactics_path(tactics_path)
    tokens = _tokenize(source)
    bindings_to_files, files_to_bindings = _parse_imports(tokens, safe_tactics_path)
    members = _find_tactics_array(tokens)

    ordered_files: list[str] = []
    used_bindings_by_file: dict[str, list[str]] = {}
    for member in members:
        basename = bindings_to_files.get(member)
        if basename is None:
            raise FrameworkManifestError(
                f"tactics array identifier is not imported from {safe_tactics_path}: {member}"
            )
        ordered_files.append(basename)
        used_bindings_by_file.setdefault(basename, []).append(member)

    if len(ordered_files) != len(set(ordered_files)):
        raise FrameworkManifestError("multiple tactics array identifiers resolve to one file")

    unused_files = sorted(set(files_to_bindings) - set(used_bindings_by_file))
    if unused_files:
        raise FrameworkManifestError(
            "tactic import(s) are not included in aidefendData.tactics: " + ", ".join(unused_files)
        )
    return ordered_files


def load_local_tactic_manifest(
    local_framework_path: Optional[Path] = None,
    tactics_path: Optional[str] = None,
) -> list[str]:
    """Read and parse ``LOCAL_FRAMEWORK_PATH/main.js`` without executing it.

    Explicit arguments make this helper straightforward to test and reuse.
    Omitted values are loaded lazily from :mod:`app.config`, avoiding config
    side effects for callers that only parse downloaded manifest text.
    """
    if local_framework_path is None or tactics_path is None:
        from app.config import settings

        if local_framework_path is None:
            local_framework_path = settings.LOCAL_FRAMEWORK_PATH
        if tactics_path is None:
            tactics_path = settings.GITHUB_TACTICS_PATH

    if local_framework_path is None:
        raise FrameworkManifestError(
            "LOCAL_FRAMEWORK_PATH is required for local manifest discovery"
        )

    root = Path(local_framework_path).resolve()
    if not root.is_dir():
        raise FrameworkManifestError(f"local framework path is not a directory: {root}")

    manifest_path = root / "main.js"
    try:
        resolved_manifest = manifest_path.resolve(strict=True)
        resolved_manifest.relative_to(root)
    except (OSError, ValueError) as exc:
        raise FrameworkManifestError(
            f"local framework main.js is missing or escapes its root: {manifest_path}"
        ) from exc
    if not resolved_manifest.is_file():
        raise FrameworkManifestError(f"local framework main.js is not a file: {manifest_path}")
    if resolved_manifest.stat().st_size > MAX_MANIFEST_BYTES:
        raise FrameworkManifestError("local framework main.js exceeds the size limit")

    try:
        source = resolved_manifest.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise FrameworkManifestError(f"cannot read local framework main.js: {exc}") from exc
    return parse_tactic_manifest(source, tactics_path=tactics_path)


__all__ = [
    "FrameworkManifestError",
    "load_local_tactic_manifest",
    "parse_tactic_manifest",
]
