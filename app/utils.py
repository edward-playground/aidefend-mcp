"""
Utility functions for AIDEFEND MCP Service.
"""

import json
import subprocess
import tempfile
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


class NodeJSParserError(Exception):
    """Raised when Node.js parsing fails."""
    pass


def parse_js_file_with_nodejs(js_file_path: Path) -> Dict[str, Any]:
    """
    Parse JavaScript file using Node.js to safely extract exported object.

    Args:
        js_file_path: Path to .js file

    Returns:
        Parsed JavaScript object as Python dict

    Raises:
        NodeJSParserError: If parsing fails
    """
    # Security validations
    try:
        validated_path = validate_file_path(js_file_path, settings.RAW_PATH)
        validate_file_extension(validated_path)
        validate_file_size(validated_path)
    except Exception as e:
        logger.error(f"Security validation failed for {js_file_path}: {e}")
        raise NodeJSParserError(f"File validation failed: {e}")

    # Create temporary Node.js script to parse the file
    parser_script = f"""
const module = {{}};
const exports = {{}};

// Read the file
const fs = require('fs');
const content = fs.readFileSync({json.dumps(str(validated_path))}, 'utf-8');

// Use Function constructor to safely evaluate the export
// This extracts the exported object without executing arbitrary code
const extractExport = new Function('exports', 'module', content + '; return exports;');
const exported = extractExport(exports, module);

// Find the exported constant (e.g., modelTactic, hardenTactic, etc.)
let result = null;
for (const key in exported) {{
    if (key.endsWith('Tactic')) {{
        result = exported[key];
        break;
    }}
}}

// If not found in exports, try to extract from content directly
if (!result) {{
    const match = content.match(/export\\s+const\\s+(\\w+Tactic)\\s*=\\s*(\\{{[\\s\\S]*?\\}});?\\s*$/m);
    if (match) {{
        const objContent = match[2];
        result = eval('(' + objContent + ')');
    }}
}}

if (!result) {{
    console.error('ERROR: Could not find exported tactic object');
    process.exit(1);
}}

// Output as JSON
console.log(JSON.stringify(result, null, 2));
"""

    try:
        # Write parser script to temporary file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.js',
            delete=False,
            encoding='utf-8'
        ) as tmp_script:
            tmp_script.write(parser_script)
            tmp_script_path = tmp_script.name

        # Execute Node.js parser
        result = subprocess.run(
            [settings.NODE_EXECUTABLE, tmp_script_path],
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
            check=False
        )

        # Clean up temporary script
        Path(tmp_script_path).unlink(missing_ok=True)

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            logger.error(
                f"Node.js parser failed for {js_file_path.name}",
                extra={"error": error_msg}
            )
            raise NodeJSParserError(f"Node.js parsing failed: {error_msg}")

        # Parse JSON output
        try:
            parsed_data = json.loads(result.stdout)
            logger.info(f"Successfully parsed {js_file_path.name}")
            return parsed_data
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {js_file_path.name}: {e}")
            raise NodeJSParserError(f"Invalid JSON output from Node.js parser: {e}")

    except subprocess.TimeoutExpired:
        logger.error(f"Node.js parser timeout for {js_file_path.name}")
        raise NodeJSParserError("Node.js parser timeout (30s)")
    except Exception as e:
        logger.error(f"Unexpected error parsing {js_file_path.name}: {e}")
        raise NodeJSParserError(f"Unexpected parsing error: {e}")


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


def check_nodejs_available() -> bool:
    """
    Check if Node.js is available and working.

    Returns:
        True if Node.js is available, False otherwise
    """
    try:
        result = subprocess.run(
            [settings.NODE_EXECUTABLE, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            logger.info(f"Node.js available: {version}")
            return True
        else:
            logger.warning(f"Node.js check failed: {result.stderr}")
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"Node.js not available: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking Node.js: {e}")
        return False


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
