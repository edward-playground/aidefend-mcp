"""
Security validation module for AIDEFEND MCP Service.
Implements comprehensive input validation, sanitization, and security checks.
"""

import re
import hashlib
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from app.logger import get_logger

logger = get_logger(__name__)

# Security constants
MAX_QUERY_LENGTH = 2000
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_QUERY_PATTERN = re.compile(r'^[\w\s\-.,!?()\'\":/]+$', re.UNICODE)
VALID_COMMIT_SHA_PATTERN = re.compile(r'^[a-f0-9]{40}$')
ALLOWED_FILE_EXTENSIONS = {'.js'}


class SecurityError(Exception):
    """Base exception for security validation failures."""
    pass


class InputValidationError(SecurityError):
    """Raised when input validation fails."""
    pass


class PathTraversalError(SecurityError):
    """Raised when path traversal attack is detected."""
    pass


class FileSizeError(SecurityError):
    """Raised when file size exceeds limits."""
    pass


def validate_query_text(query: str) -> str:
    """
    Validate and sanitize user query text.

    Args:
        query: User query string

    Returns:
        Sanitized query string

    Raises:
        InputValidationError: If query is invalid or malicious
    """
    if not query or not query.strip():
        raise InputValidationError("Query cannot be empty")

    # Length check
    if len(query) > MAX_QUERY_LENGTH:
        logger.warning(
            f"Query exceeds maximum length",
            extra={"query_length": len(query), "max_length": MAX_QUERY_LENGTH}
        )
        raise InputValidationError(
            f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters"
        )

    # Strip and normalize whitespace
    sanitized = " ".join(query.strip().split())

    # Check for suspicious patterns (basic injection prevention)
    dangerous_patterns = [
        r'<script', r'javascript:', r'onerror=', r'onclick=',
        r'\bexec\b', r'\beval\b', r'__import__', r'\{\{.*\}\}',
        r'\$\{.*\}', r'\.\./', r'\.\.\\'
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, sanitized, re.IGNORECASE):
            logger.warning(
                f"Suspicious pattern detected in query",
                extra={"pattern": pattern}
            )
            raise InputValidationError("Query contains potentially malicious content")

    # Validate allowed characters (relaxed for natural language)
    # Allow Unicode word characters, spaces, and common punctuation
    if not ALLOWED_QUERY_PATTERN.match(sanitized):
        raise InputValidationError("Query contains invalid characters")

    return sanitized


def validate_commit_sha(sha: str) -> str:
    """
    Validate GitHub commit SHA format.

    Args:
        sha: Commit SHA string

    Returns:
        Validated SHA string

    Raises:
        InputValidationError: If SHA is invalid
    """
    if not sha:
        raise InputValidationError("Commit SHA cannot be empty")

    sha = sha.strip().lower()

    if not VALID_COMMIT_SHA_PATTERN.match(sha):
        raise InputValidationError("Invalid commit SHA format (expected 40 hex chars)")

    return sha


def validate_github_url(url: str, expected_repo: str) -> str:
    """
    Validate GitHub URL to prevent SSRF attacks.

    Args:
        url: GitHub URL to validate
        expected_repo: Expected repository path (e.g., "owner/repo")

    Returns:
        Validated URL

    Raises:
        InputValidationError: If URL is invalid or suspicious
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise InputValidationError(f"Invalid URL format: {e}")

    # Check protocol
    if parsed.scheme not in {'https', 'http'}:
        raise InputValidationError("URL must use HTTP or HTTPS protocol")

    # Check domain (allow github.com and api.github.com)
    allowed_domains = {'github.com', 'api.github.com', 'raw.githubusercontent.com'}
    if parsed.netloc not in allowed_domains:
        logger.warning(f"Blocked URL with suspicious domain", extra={"domain": parsed.netloc})
        raise InputValidationError("URL must be from github.com domain")

    # Check if expected repo is in path
    if expected_repo and expected_repo not in parsed.path:
        logger.warning(
            f"URL does not match expected repository",
            extra={"url": url, "expected_repo": expected_repo}
        )
        raise InputValidationError("URL does not match expected repository")

    return url


def validate_file_path(file_path: Path, base_dir: Path) -> Path:
    """
    Validate file path to prevent directory traversal attacks.

    Args:
        file_path: File path to validate
        base_dir: Base directory that should contain the file

    Returns:
        Resolved and validated Path object

    Raises:
        PathTraversalError: If path traversal is detected
    """
    try:
        # Resolve to absolute path
        resolved_file = file_path.resolve()
        resolved_base = base_dir.resolve()

        # Check if file is within base directory
        if not str(resolved_file).startswith(str(resolved_base)):
            logger.warning(
                f"Path traversal attempt detected",
                extra={
                    "attempted_path": str(file_path),
                    "base_dir": str(base_dir)
                }
            )
            raise PathTraversalError("Access denied: path outside allowed directory")

        return resolved_file

    except (ValueError, OSError) as e:
        raise PathTraversalError(f"Invalid file path: {e}")


def validate_file_extension(file_path: Path) -> Path:
    """
    Validate file extension.

    Args:
        file_path: File path to validate

    Returns:
        Validated Path object

    Raises:
        InputValidationError: If file extension is not allowed
    """
    if file_path.suffix.lower() not in ALLOWED_FILE_EXTENSIONS:
        raise InputValidationError(
            f"File extension {file_path.suffix} not allowed. "
            f"Allowed: {', '.join(ALLOWED_FILE_EXTENSIONS)}"
        )

    return file_path


def validate_file_size(file_path: Path) -> Path:
    """
    Validate file size to prevent resource exhaustion.

    Args:
        file_path: File path to check

    Returns:
        Validated Path object

    Raises:
        FileSizeError: If file is too large
    """
    if not file_path.exists():
        raise FileSizeError(f"File does not exist: {file_path}")

    file_size = file_path.stat().st_size

    if file_size > MAX_FILE_SIZE_BYTES:
        logger.warning(
            f"File exceeds maximum size",
            extra={
                "file": str(file_path),
                "size_mb": file_size / (1024 * 1024),
                "max_mb": MAX_FILE_SIZE_MB
            }
        )
        raise FileSizeError(
            f"File exceeds maximum size of {MAX_FILE_SIZE_MB}MB"
        )

    return file_path


def compute_file_checksum(file_path: Path, algorithm: str = "sha256") -> str:
    """
    Compute cryptographic checksum of a file.

    Args:
        file_path: Path to file
        algorithm: Hash algorithm (sha256, sha512, etc.)

    Returns:
        Hexadecimal hash string

    Raises:
        ValueError: If algorithm is not supported
    """
    try:
        hasher = hashlib.new(algorithm)
    except ValueError:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")

    with open(file_path, 'rb') as f:
        # Read in chunks to handle large files
        for chunk in iter(lambda: f.read(8192), b''):
            hasher.update(chunk)

    return hasher.hexdigest()


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent injection attacks.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename

    Raises:
        InputValidationError: If filename is invalid
    """
    if not filename:
        raise InputValidationError("Filename cannot be empty")

    # Remove path components
    filename = Path(filename).name

    # Allow only alphanumeric, dots, hyphens, underscores
    if not re.match(r'^[\w\-\.]+$', filename):
        raise InputValidationError("Filename contains invalid characters")

    # Prevent hidden files
    if filename.startswith('.'):
        raise InputValidationError("Hidden files not allowed")

    # Prevent double extensions (e.g., file.txt.exe)
    if filename.count('.') > 1:
        raise InputValidationError("Multiple file extensions not allowed")

    return filename


def validate_top_k(top_k: int, max_allowed: int = 20) -> int:
    """
    Validate top_k parameter for search results.

    Args:
        top_k: Number of results requested
        max_allowed: Maximum allowed value

    Returns:
        Validated top_k value

    Raises:
        InputValidationError: If top_k is out of range
    """
    if top_k < 1:
        raise InputValidationError("top_k must be at least 1")

    if top_k > max_allowed:
        logger.warning(
            f"top_k exceeds maximum",
            extra={"requested": top_k, "max": max_allowed}
        )
        raise InputValidationError(f"top_k cannot exceed {max_allowed}")

    return top_k


def set_secure_file_permissions(file_path: Path, mode: int = 0o600) -> None:
    """
    Set secure file permissions (owner read/write only).

    Args:
        file_path: Path to file
        mode: Permission mode (default: 0o600 = rw-------)
    """
    try:
        file_path.chmod(mode)
        logger.debug(f"Set secure permissions on {file_path}", extra={"mode": oct(mode)})
    except Exception as e:
        logger.warning(f"Could not set secure permissions on {file_path}: {e}")
