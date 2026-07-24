"""
Utility functions for AIDEFEND MCP Service.
"""

import json
import math
import os
import shutil
import site
import subprocess  # nosec B404
import sys
import sysconfig
import tempfile
import re
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from datetime import datetime, timezone
from app.config import settings
from app.logger import get_logger
from app.security import (
    validate_file_path,
    validate_file_extension,
    validate_file_size,
    set_secure_file_permissions,
)

logger = get_logger(__name__)

_PARSER_DISTRIBUTION_NAME = "aidefend-mcp"
_PARSER_FILENAME = "parse_js_module.mjs"
_PARSER_COMPANION_PATHS = (
    Path("vendor") / "acorn.mjs",
    Path("vendor") / "ACORN-LICENSE",
)


def _atomic_write_json(file_path: Path, payload: Dict[str, Any]) -> None:
    '''Durably replace JSON without exposing partial contents.'''
    destination = Path(file_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=destination.parent,
            prefix=f'.{destination.name}.', suffix='.tmp', delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        set_secure_file_permissions(temporary_path)
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                logger.warning(
                    'Could not remove incomplete version metadata file %s: %s',
                    temporary_path,
                    cleanup_error,
                )


def _parser_bundle_files(parser_script: Path) -> tuple[Path, ...]:
    """Return every file required by one self-contained parser bundle."""
    return (
        parser_script,
        *(parser_script.parent / relative for relative in _PARSER_COMPANION_PATHS),
    )


def _missing_parser_bundle_files(parser_script: Path) -> tuple[Path, ...]:
    """Return missing files from one self-contained parser installation."""
    return tuple(path for path in _parser_bundle_files(parser_script) if not path.is_file())


def _safe_sysconfig_data_root(scheme: Optional[str] = None) -> Optional[Path]:
    """Return one sysconfig data root without making module import fragile."""
    try:
        configured = (
            sysconfig.get_path("data")
            if scheme is None
            else sysconfig.get_path("data", scheme=scheme)
        )
        return Path(configured) if configured else None
    except (OSError, RuntimeError, KeyError, TypeError, ValueError):
        # A damaged or vendor-specific sysconfig implementation must not make
        # the MCP service unimportable. The remaining parser candidates can
        # still support source checkouts and ordinary virtual environments.
        return None


def _distribution_parser_candidates() -> Iterable[Path]:
    """Locate relocated wheel data through installed RECORD metadata."""
    try:
        distribution = importlib_metadata.distribution(_PARSER_DISTRIBUTION_NAME)
    except importlib_metadata.PackageNotFoundError:
        return

    for entry in distribution.files or ():
        normalized = str(entry).replace("\\", "/")
        if normalized != _PARSER_FILENAME and not normalized.endswith("/" + _PARSER_FILENAME):
            continue
        try:
            yield Path(distribution.locate_file(entry)).resolve(strict=False)
        except (OSError, RuntimeError, TypeError, ValueError):
            continue


def _node_parser_candidates(module_file: Optional[Path] = None) -> tuple[Path, ...]:
    """Return parser locations in trusted install-precedence order.

    Source checkouts keep the parser beside the project package. Installed
    distribution metadata is authoritative for wheel data relocated by pip,
    including user, pipx, and custom-prefix schemes. Sysconfig and user-base
    paths remain conservative fallbacks. No current-working-directory path is
    considered.
    """
    module_path = Path(module_file) if module_file is not None else Path(__file__)
    candidates = [module_path.resolve().parent.parent / "parse_js_module.mjs"]
    candidates.extend(_distribution_parser_candidates())

    current_data_root = _safe_sysconfig_data_root()
    if current_data_root is not None:
        candidates.append(current_data_root / "parse_js_module.mjs")

    try:
        user_scheme = sysconfig.get_preferred_scheme("user")
    except (AttributeError, OSError, RuntimeError, KeyError, TypeError, ValueError):
        user_scheme = None
    if user_scheme:
        user_data_root = _safe_sysconfig_data_root(user_scheme)
        if user_data_root is not None:
            candidates.append(user_data_root / "parse_js_module.mjs")

    try:
        user_base = site.getuserbase()
    except (AttributeError, TypeError):
        user_base = None
    if user_base:
        candidates.append(Path(user_base) / "parse_js_module.mjs")

    # RECORD, active, and user schemes can resolve to the same destination.
    # Preserve precedence while avoiding duplicate diagnostics/probes.
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            normalized_candidate = Path(candidate).resolve(strict=False)
        except (OSError, RuntimeError):
            normalized_candidate = Path(candidate)
        if normalized_candidate not in seen:
            seen.add(normalized_candidate)
            unique.append(normalized_candidate)
    return tuple(unique)


def _resolve_node_parser_script(candidates: Optional[tuple[Path, ...]] = None) -> Path:
    """Select the first complete bundle, retaining a deterministic fallback."""
    ordered = candidates or _node_parser_candidates()
    for candidate in ordered:
        try:
            if not _missing_parser_bundle_files(candidate):
                return candidate
        except OSError:
            continue

    active_data_root = _safe_sysconfig_data_root()
    if active_data_root is not None:
        return active_data_root / _PARSER_FILENAME
    return ordered[0]


# Source checkouts keep the parser in the project root. Wheels install it in
# Python's platform data directory alongside a minimal vendored Acorn runtime.
NODE_PARSER_CANDIDATES = _node_parser_candidates()
SOURCE_NODE_PARSER_SCRIPT = NODE_PARSER_CANDIDATES[0]
_ACTIVE_DATA_ROOT = _safe_sysconfig_data_root()
INSTALLED_NODE_PARSER_SCRIPT = (
    _ACTIVE_DATA_ROOT / _PARSER_FILENAME
    if _ACTIVE_DATA_ROOT is not None
    else SOURCE_NODE_PARSER_SCRIPT
)
NODE_PARSER_SCRIPT = _resolve_node_parser_script(NODE_PARSER_CANDIDATES)
NODE_BINARY = shutil.which("node")


class JavaScriptParserError(Exception):
    """Raised when JavaScript parsing fails."""

    pass


def parse_js_file_with_node(js_file_path: Path) -> Dict[str, Any]:
    """
    Parse JavaScript file using Node.js subprocess.

    This function uses Node.js to natively parse ES modules with full JavaScript
    syntax support (including template literals with backticks), then returns
    the exported object as a Python dict.

    Args:
        js_file_path: Path to .js file

    Returns:
        Parsed JavaScript object as Python dict

    Raises:
        JavaScriptParserError: If parsing fails
    """
    # Security validations
    try:
        validated_path = validate_file_path(js_file_path, settings.RAW_PATH)
        validate_file_extension(validated_path)
        validate_file_size(validated_path)
    except Exception as e:
        logger.error(f"Security validation failed for {js_file_path}: {e}")
        raise JavaScriptParserError(f"File validation failed: {e}")

    # Acorn is imported relative to the parser entry point, and its license is
    # a required wheel/runtime asset. Reject a partial installation explicitly.
    missing_parser_files = _missing_parser_bundle_files(NODE_PARSER_SCRIPT)
    if missing_parser_files:
        checked_locations = ", ".join(str(path) for path in NODE_PARSER_CANDIDATES)
        raise JavaScriptParserError(
            "Bundled JavaScript parser is incomplete. Missing: "
            + ", ".join(str(path) for path in missing_parser_files)
            + ". "
            f"Checked locations: {checked_locations}"
        )
    if not NODE_BINARY:
        raise JavaScriptParserError(
            "Node.js executable not found in PATH. Install Node.js 18+ and ensure "
            "the `node` command is available before syncing AIDEFEND content."
        )

    try:
        # Execute Node.js parser
        # Command: <absolute-node-path> parse_js_module.mjs /path/to/file.js
        result = subprocess.run(
            [NODE_BINARY, str(NODE_PARSER_SCRIPT), str(validated_path.resolve())],  # nosec B603
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,  # 30 second timeout
            check=True,  # Raise CalledProcessError if exit code != 0
        )

        # Parse JSON output from stdout
        parsed_data = json.loads(result.stdout)

        logger.info(
            f"Successfully parsed {js_file_path.name} with Node.js",
            extra={
                "tactic": parsed_data.get("name", "unknown"),
                "file_size": validated_path.stat().st_size,
            },
        )

        return parsed_data

    except FileNotFoundError:
        # Node.js not found in PATH
        raise JavaScriptParserError(
            "Node.js (node) not found in system PATH. "
            "Please install Node.js from https://nodejs.org/ and ensure 'node' "
            "command is available in your terminal."
        )

    except subprocess.TimeoutExpired:
        raise JavaScriptParserError(
            f"Node.js parser timed out after 30 seconds for {js_file_path.name}. "
            f"File may be too large or contain infinite loops."
        )

    except subprocess.CalledProcessError as e:
        # Node.js script exited with error
        error_output = e.stderr.strip() if e.stderr else "No error message"
        raise JavaScriptParserError(
            f"Node.js parser failed for {js_file_path.name}. "
            f"Exit code: {e.returncode}. Error: {error_output}"
        )

    except json.JSONDecodeError as e:
        # Node.js output was not valid JSON
        stdout_preview = result.stdout[:200] if result.stdout else "(empty)"
        raise JavaScriptParserError(
            f"Node.js parser produced invalid JSON for {js_file_path.name}. "
            f"JSON error: {e}. Output preview: {stdout_preview}"
        )

    except Exception as e:
        raise JavaScriptParserError(
            f"Unexpected error parsing {js_file_path.name} with Node.js: {e}"
        )


def sanitize_for_json(obj: Any) -> Any:
    """Recursively replace non-JSON-compliant float values with None.

    Records read from LanceDB via ``pandas.DataFrame.to_dict('records')`` represent
    missing/optional fields (e.g. a top-level technique's ``parent_technique_id``) as
    float ``NaN``. Starlette's ``JSONResponse`` serializes with ``allow_nan=False``, so
    any ``NaN``/``Inf`` reaching the REST layer raises
    ``ValueError: Out of range float values are not JSON compliant`` and returns HTTP 500.

    This helper walks dicts/lists and converts ``NaN``/``+Inf``/``-Inf`` (including numpy
    float subclasses) to ``None``; every other value is returned unchanged. Apply it to a
    tool's return value before it is serialized.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {key: sanitize_for_json(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    return obj


def escape_markdown(text: Any) -> str:
    """Neutralize user-supplied text before echoing it into Markdown/MCP output.

    Query text is deliberately NOT content-filtered on input (see
    ``app.security.validate_query_text``) because it is only embedded for vector search.
    Safety for the *display* path is therefore handled here, at render time: angle brackets
    and ampersands are HTML-encoded (so a query like ``<script>...`` can never render as
    live HTML in a Markdown client) and backticks are escaped (to prevent code-span
    breakout). All other characters are left readable, so legitimate security queries such
    as ``eval()``, ``${jndi:...}`` or ``../etc`` display verbatim.
    """
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("`", "\\`")


def save_version_info(commit_sha: str, additional_info: Optional[Dict[str, Any]] = None) -> None:
    """Save version information to local file."""
    version_data = {
        "commit_sha": commit_sha,
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
        "sync_timestamp": datetime.now(timezone.utc).timestamp(),
    }

    if additional_info:
        version_data.update(additional_info)

    try:
        _atomic_write_json(settings.VERSION_FILE, version_data)
        logger.info(f"Saved version info: {commit_sha[:8]}")
    except Exception as e:
        logger.error(f"Failed to save version info: {e}")
        raise


def save_sync_timestamp() -> None:
    """
    Update last_synced_at timestamp without changing commit SHA.

    Used when sync check completes but no update is needed.
    This indicates the service checked for updates even if none were available.
    """
    try:
        # Load existing version info
        existing_data = load_version_info()

        if existing_data is None:
            # No version file exists yet - create minimal version info
            version_data = {
                "commit_sha": "unknown",
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
                "sync_timestamp": datetime.now(timezone.utc).timestamp(),
            }
        else:
            # Update timestamp in existing data
            existing_data["last_synced_at"] = datetime.now(timezone.utc).isoformat()
            existing_data["sync_timestamp"] = datetime.now(timezone.utc).timestamp()
            version_data = existing_data

        # Do not expose a truncated marker if the write is interrupted.
        _atomic_write_json(settings.VERSION_FILE, version_data)
        logger.info("Updated sync timestamp (no content changes)")
    except Exception as e:
        logger.error(f"Failed to update sync timestamp: {e}")
        # Don't raise - timestamp update failure is not critical


def load_version_info() -> Optional[Dict[str, Any]]:
    """Load version information from local file."""
    try:
        if not settings.VERSION_FILE.exists():
            return None

        with open(settings.VERSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data
    except json.JSONDecodeError as e:
        logger.error(f"Invalid version file format: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load version info: {e}")
        return None


def get_local_commit_sha() -> Optional[str]:
    """Get the currently synced commit SHA."""
    version_info = load_version_info()
    if version_info:
        return version_info.get("commit_sha")
    return None


def format_bytes(bytes_size: int) -> str:
    """Format bytes into human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"
