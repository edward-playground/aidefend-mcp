"""
Utility functions for AIDEFEND MCP Service.
"""

import json
import subprocess
import sys
import re
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from app.config import settings
from app.logger import get_logger
from app.security import (
    validate_file_path,
    validate_file_extension,
    validate_file_size,
    set_secure_file_permissions
)

logger = get_logger(__name__)

# Path to Node.js parser script (in project root)
NODE_PARSER_SCRIPT = Path(__file__).parent.parent / "parse_js_module.mjs"


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

    # Check Node.js parser script exists
    if not NODE_PARSER_SCRIPT.exists():
        raise JavaScriptParserError(
            f"Node.js parser script not found at {NODE_PARSER_SCRIPT}. "
            f"Expected location: {NODE_PARSER_SCRIPT.resolve()}"
        )

    try:
        # Execute Node.js parser
        # Command: node parse_js_module.mjs /path/to/file.js
        result = subprocess.run(
            ["node", str(NODE_PARSER_SCRIPT), str(validated_path.resolve())],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30,  # 30 second timeout
            check=True   # Raise CalledProcessError if exit code != 0
        )

        # Parse JSON output from stdout
        parsed_data = json.loads(result.stdout)

        logger.info(
            f"Successfully parsed {js_file_path.name} with Node.js",
            extra={
                "tactic": parsed_data.get("name", "unknown"),
                "file_size": validated_path.stat().st_size
            }
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


def save_version_info(commit_sha: str, additional_info: Optional[Dict[str, Any]] = None) -> None:
    """Save version information to local file."""
    version_data = {
        "commit_sha": commit_sha,
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
        "sync_timestamp": datetime.now(timezone.utc).timestamp()
    }

    if additional_info:
        version_data.update(additional_info)

    try:
        settings.VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(settings.VERSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(version_data, f, indent=2)

        set_secure_file_permissions(settings.VERSION_FILE)
        logger.info(f"Saved version info: {commit_sha[:8]}")
    except Exception as e:
        logger.error(f"Failed to save version info: {e}")
        raise


def load_version_info() -> Optional[Dict[str, Any]]:
    """Load version information from local file."""
    try:
        if not settings.VERSION_FILE.exists():
            return None

        with open(settings.VERSION_FILE, 'r', encoding='utf-8') as f:
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
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to maximum length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix