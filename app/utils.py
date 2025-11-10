"""
Utility functions for AIDEFEND MCP Service.
"""

import json
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


class JavaScriptParserError(Exception):
    """Raised when JavaScript parsing fails."""
    pass


def parse_js_file_with_regex(js_file_path: Path) -> Dict[str, Any]:
    """
    Parse JavaScript file using regex to extract exported object.

    This function extracts JSON data from JavaScript export statements like:
    export const tacticName = { ... };

    Note: This is designed for the specific AIDEFEND framework file format.
    If the format changes significantly, this parser may need updates.

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

    try:
        # Read file content
        with open(validated_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Pattern to match: export const <name> = { ... }; or { ... }
        # Semicolon is optional in JavaScript
        # Uses re.DOTALL to allow . to match newlines
        pattern = r'export\s+const\s+(\w+)\s*=\s*(\{.*?\})\s*;?'
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            logger.error(
                f"Could not find exported object in {js_file_path.name}",
                extra={"pattern": "export const <name> = {...};"}
            )
            raise JavaScriptParserError(
                f"No exported object found in {js_file_path.name}. "
                f"Expected format: 'export const <name> = {{...}};' (semicolon optional)"
            )

        tactic_name = match.group(1)
        obj_content = match.group(2)

        # Clean up JavaScript object to make it valid JSON:
        # 1. Remove JavaScript comments
        obj_content = re.sub(r'//.*?$', '', obj_content, flags=re.MULTILINE)  # Single-line comments
        obj_content = re.sub(r'/\*.*?\*/', '', obj_content, flags=re.DOTALL)  # Multi-line comments

        # 2. Remove trailing commas before closing braces/brackets
        obj_content = re.sub(r',(\s*[}\]])', r'\1', obj_content)

        # Note: AIDEFEND framework .js files already have quoted keys ("name", "id", etc.)
        # We do NOT add quotes to avoid corrupting HTML content in string values
        # (e.g., <h5>Concept:</h5> would become <h5>"Concept":</h5>)

        # Parse as JSON
        try:
            parsed_data = json.loads(obj_content)
            logger.info(
                f"Successfully parsed {js_file_path.name} using regex",
                extra={"tactic_name": tactic_name}
            )
            return parsed_data
        except json.JSONDecodeError as e:
            logger.error(
                f"JSON decode error for {js_file_path.name}",
                extra={
                    "error": str(e),
                    "line": e.lineno,
                    "column": e.colno,
                    "obj_preview": obj_content[:200]
                }
            )
            raise JavaScriptParserError(
                f"Failed to parse JavaScript object as JSON in {js_file_path.name}: {e}. "
                f"The file format may have changed. Please check the file structure."
            )

    except JavaScriptParserError:
        # Re-raise our custom errors
        raise
    except Exception as e:
        logger.error(f"Unexpected error parsing {js_file_path.name}: {e}")
        raise JavaScriptParserError(f"Unexpected parsing error: {e}")


def save_version_info(commit_sha: str, additional_info: Optional[Dict[str, Any]] = None) -> None:
    """
    Save version information to local file.

    Args:
        commit_sha: Git commit SHA
        additional_info: Additional metadata to save
    """
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

        # Set secure permissions
        set_secure_file_permissions(settings.VERSION_FILE)

        logger.info(f"Saved version info: {commit_sha[:8]}")
    except Exception as e:
        logger.error(f"Failed to save version info: {e}")
        raise


def load_version_info() -> Optional[Dict[str, Any]]:
    """
    Load version information from local file.

    Returns:
        Version data dict or None if not found
    """
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
    """
    Get the currently synced commit SHA.

    Returns:
        Commit SHA string or None
    """
    version_info = load_version_info()
    if version_info:
        return version_info.get("commit_sha")
    return None


def format_bytes(bytes_size: int) -> str:
    """
    Format bytes into human-readable string.

    Args:
        bytes_size: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} TB"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
