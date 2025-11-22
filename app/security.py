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
from app.config import settings

logger = get_logger(__name__)

# Security constants
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_REQUEST_BODY_SIZE_MB = 1  # Maximum request body size in MB
MAX_REQUEST_BODY_SIZE_BYTES = MAX_REQUEST_BODY_SIZE_MB * 1024 * 1024
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
    if len(query) > settings.MAX_QUERY_LENGTH:
        logger.warning(
            f"Query exceeds maximum length",
            extra={"query_length": len(query), "max_length": settings.MAX_QUERY_LENGTH}
        )
        raise InputValidationError(
            f"Query exceeds maximum length of {settings.MAX_QUERY_LENGTH} characters"
        )

    # Strip and normalize whitespace
    sanitized = " ".join(query.strip().split())

    # Check for suspicious patterns (basic injection prevention)
    # Enhanced blacklist to catch more injection attempts
    dangerous_patterns = [
        r'<script', r'javascript:', r'onerror=', r'onclick=',
        r'\bexec\b', r'\beval\b', r'__import__', r'\{\{.*\}\}',
        r'\$\{.*\}', r'\.\./', r'\.\.\\'
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, sanitized, re.IGNORECASE):
            logger.warning(
                f"Suspicious pattern detected in query",
                extra={"pattern": pattern, "query_preview": sanitized[:100]}
            )
            raise InputValidationError("Query contains potentially malicious content")

    return sanitized


def validate_chunked_query(query_text: str) -> tuple[str, dict]:
    """
    Validate query text for chunked search with additional security checks.

    Performs comprehensive validation for long queries that will be chunked:
    1. Total length validation (MAX_TOTAL_QUERY_LENGTH)
    2. Chunk count estimation and validation (MAX_CHUNKS)
    3. Basic sanitization (reuses validate_query_text for each potential chunk)
    4. Security logging for long queries

    Args:
        query_text: User query text (potentially very long)

    Returns:
        Tuple of (sanitized_text, metadata_dict):
        - sanitized_text: Cleaned and validated query text
        - metadata_dict: Contains chunking information for monitoring

    Raises:
        InputValidationError: If query is invalid, too long, or would require too many chunks

    Security Notes:
        - Prevents DoS via excessive chunk counts
        - Logs all long queries for security audit
        - Each chunk will be independently validated before search

    Example:
        >>> text = "Very long security report..." * 100
        >>> sanitized, meta = validate_chunked_query(text)
        >>> print(meta['estimated_chunks'])  # Number of chunks needed
    """
    from app.chunking import estimate_chunk_count

    # Basic empty check
    if not query_text or not query_text.strip():
        raise InputValidationError("Query cannot be empty")

    # 1. Total length validation
    text_length = len(query_text)
    if text_length > settings.MAX_TOTAL_QUERY_LENGTH:
        logger.warning(
            f"Query too long for chunked search",
            extra={
                "query_length": text_length,
                "max_allowed": settings.MAX_TOTAL_QUERY_LENGTH,
                "query_preview": query_text[:200]
            }
        )
        raise InputValidationError(
            f"Query too long: {text_length} characters. "
            f"Maximum allowed: {settings.MAX_TOTAL_QUERY_LENGTH} characters"
        )

    # 2. Estimate chunk count (fast check before actual chunking)
    estimated_chunks = estimate_chunk_count(query_text)

    if estimated_chunks > settings.MAX_CHUNKS:
        logger.warning(
            f"Query would require too many chunks",
            extra={
                "query_length": text_length,
                "estimated_chunks": estimated_chunks,
                "max_chunks": settings.MAX_CHUNKS
            }
        )
        raise InputValidationError(
            f"Query would require {estimated_chunks} chunks. "
            f"Maximum allowed: {settings.MAX_CHUNKS} chunks. "
            f"Please use a shorter query."
        )

    # 3. Basic sanitization (same as regular queries)
    # Note: Individual chunks will be validated again during actual search
    sanitized = " ".join(query_text.strip().split())

    # 4. Check for dangerous patterns (same as validate_query_text)
    dangerous_patterns = [
        r'<script', r'javascript:', r'onerror=', r'onclick=',
        r'\bexec\b', r'\beval\b', r'__import__', r'\{\{.*\}\}',
        r'\$\{.*\}', r'\.\./', r'\.\.\\'
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, sanitized, re.IGNORECASE):
            logger.warning(
                f"Suspicious pattern in long query",
                extra={"pattern": pattern, "query_preview": sanitized[:100]}
            )
            raise InputValidationError("Query contains potentially malicious content")

    # 5. Security audit logging for long queries
    if text_length > settings.MAX_QUERY_LENGTH:
        logger.info(
            f"Long query validated (chunking required)",
            extra={
                "original_length": text_length,
                "estimated_chunks": estimated_chunks,
                "query_preview": sanitized[:200]
            }
        )

    # Build metadata
    metadata = {
        "original_length": text_length,
        "estimated_chunks": estimated_chunks,
        "chunking_required": text_length > settings.MAX_QUERY_LENGTH,
        "max_chunks_allowed": settings.MAX_CHUNKS,
        "chunk_size": settings.CHUNK_SIZE,
        "chunk_overlap": settings.CHUNK_OVERLAP
    }

    return sanitized, metadata


def sanitize_technique_id(technique_id: str) -> str:
    """
    Sanitize technique ID to prevent filter injection in LanceDB where() clauses.

    Validates that technique_id contains only safe characters using a whitelist approach.
    This prevents SQL-like injection attacks in LanceDB filter expressions.

    Args:
        technique_id: Technique ID from user input (e.g., "AID-H-001", "OWASP-LLM01:2023")

    Returns:
        Validated technique ID (unchanged if valid)

    Raises:
        InputValidationError: If technique_id contains unsafe characters or is invalid

    Security:
        - Uses whitelist regex: ^[A-Za-z0-9\\-\\._:]{3,100}$
        - Prevents injection via where() clause f-strings
        - Allows common formats: AID-H-001, OWASP-LLM01:2023, AML.T0001.001
    """
    if not technique_id or not technique_id.strip():
        raise InputValidationError("Technique ID cannot be empty")

    technique_id = technique_id.strip()

    # Length validation (3-100 characters)
    if len(technique_id) < 3:
        raise InputValidationError("Technique ID must be at least 3 characters")
    if len(technique_id) > 100:
        raise InputValidationError("Technique ID cannot exceed 100 characters")

    # Whitelist pattern: Allow only alphanumeric, dash, dot, underscore, colon
    # This supports common formats:
    # - AIDEFEND: AID-H-001, AID-P-002.001
    # - OWASP: OWASP-LLM01:2023, OWASP-LLM01
    # - MITRE ATLAS: AML.T0001.001, AML.T0001
    # - MAESTRO: similar patterns
    SAFE_TECHNIQUE_ID_PATTERN = re.compile(r'^[A-Za-z0-9\-\._:]{3,100}$')

    if not SAFE_TECHNIQUE_ID_PATTERN.match(technique_id):
        logger.warning(
            f"Invalid technique ID format (injection attempt?)",
            extra={
                "technique_id": technique_id[:50],  # Truncate for logging
                "length": len(technique_id)
            }
        )
        raise InputValidationError(
            "Technique ID contains invalid characters. "
            "Allowed: letters, numbers, dash (-), dot (.), underscore (_), colon (:)"
        )

    return technique_id


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
