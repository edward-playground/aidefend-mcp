"""
Synchronization service for AIDEFEND framework content.
Handles GitHub sync, parsing, embedding, and indexing with security.
"""

import asyncio
import hashlib
import httpx
import lancedb
import time
import re
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from fastembed import TextEmbedding
from bs4 import BeautifulSoup

from app.config import settings
from app.logger import get_logger
from app.security import (
    validate_commit_sha,
    validate_github_url,
    validate_file_path,
    sanitize_filename,
    set_secure_file_permissions
)
from app.utils import (
    parse_js_file_with_node,
    save_version_info,
    save_sync_timestamp,
    get_local_commit_sha,
    format_bytes
)
from app.embedding_cache import EmbeddingCache, compute_content_hash
from app.framework_utils import (
    build_framework_metrics,
    extract_framework_coverage,
    is_actionable_record,
    merge_framework_coverage_sets,
    normalize_framework_item,
    parse_json_list,
)

logger = get_logger(__name__)


# Custom cross-process file lock implementation
# Replaces filelock library to avoid modifying lock file timestamps
class SyncFileLock:
    """
    Cross-process file lock using OS-level primitives.

    CRITICAL: This implementation does NOT modify the lock file's mtime
    when checking lock status, which is essential for stale lock detection.

    Uses:
    - Unix/Linux/macOS: fcntl.flock()
    - Windows: msvcrt.locking()
    """

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self.lock_fd: Optional[int] = None
        self._is_locked = False

    def acquire(self, timeout: float = 0) -> bool:
        """
        Acquire the lock (non-blocking by default).

        CRITICAL: Preserves the mtime of existing lock files, which is
        essential for accurate stale lock detection.

        Args:
            timeout: Timeout in seconds (0 = non-blocking)

        Returns:
            True if lock acquired, False otherwise

        Raises:
            Exception: If lock file cannot be opened or system call fails
        """
        if self._is_locked:
            return True  # Already acquired by this instance

        try:
            # Save original mtime before any operations (for existing files)
            original_mtime = None
            if self.lock_path.exists():
                try:
                    stat_info = os.stat(str(self.lock_path))
                    original_mtime = (stat_info.st_atime, stat_info.st_mtime)
                except Exception:
                    logger.debug("Could not read existing lockfile timestamps", exc_info=True)

            # Create lock file if doesn't exist, but don't truncate if it does
            self.lock_fd = os.open(
                str(self.lock_path),
                os.O_CREAT | os.O_RDWR,  # Create if needed, read/write
                0o666  # rw-rw-rw-
            )

            # Platform-specific locking
            if sys.platform == "win32":
                import msvcrt
                # Try non-blocking lock
                msvcrt.locking(self.lock_fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                # Try non-blocking exclusive lock
                fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Success - write PID to lock file for debugging
            try:
                os.ftruncate(self.lock_fd, 0)  # Clear content
                os.lseek(self.lock_fd, 0, os.SEEK_SET)  # Seek to start
                os.write(self.lock_fd, f"{os.getpid()}\n".encode())

                # CRITICAL: Restore original mtime to preserve lock age
                if original_mtime is not None:
                    os.utime(str(self.lock_path), original_mtime)
            except Exception:
                logger.debug("Could not update lockfile metadata", exc_info=True)

            self._is_locked = True
            return True

        except (OSError, IOError) as e:
            # Lock held by another process
            if self.lock_fd is not None:
                try:
                    os.close(self.lock_fd)
                except Exception:
                    logger.debug("Could not close lockfile descriptor after contention", exc_info=True)
                self.lock_fd = None
            return False
        except Exception as e:
            # Other errors
            if self.lock_fd is not None:
                try:
                    os.close(self.lock_fd)
                except Exception:
                    logger.debug("Could not close lockfile descriptor after error", exc_info=True)
                self.lock_fd = None
            raise

    def release(self) -> None:
        """Release the lock."""
        if not self._is_locked or self.lock_fd is None:
            return

        try:
            # Platform-specific unlock
            if sys.platform == "win32":
                import msvcrt
                try:
                    # Windows: unlock before closing
                    msvcrt.locking(self.lock_fd, msvcrt.LK_UNLCK, 1)
                except (OSError, IOError):
                    # Lock may already be released, continue to close fd
                    pass
            else:
                import fcntl
                # Unix: unlock
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)

            # Close file descriptor
            os.close(self.lock_fd)
        except Exception as e:
            logger.warning(f"Error releasing lock: {e}")
        finally:
            self.lock_fd = None
            self._is_locked = False

    @property
    def is_locked(self) -> bool:
        """Check if this instance holds the lock."""
        return self._is_locked


# Cross-process file lock for sync operations
# This prevents concurrent sync across multiple processes (defense-in-depth)
# File lock is stored in DATA_PATH for cross-process visibility
_file_lock = SyncFileLock(settings.DATA_PATH / "sync.lock")

# Thread-safe global state for last sync error
import threading
_last_sync_error: Optional[str] = None
_sync_error_lock = threading.Lock()


async def _acquire_sync_lock() -> bool:
    """
    Acquire sync lock using cross-process file lock (non-blocking).

    Uses custom SyncFileLock that does NOT modify lock file timestamps.
    This is critical for accurate stale lock detection.

    Returns:
        True if lock acquired, False if another process holds the lock
    """
    loop = asyncio.get_event_loop()

    # Run acquire in executor to avoid blocking event loop
    acquired = await loop.run_in_executor(None, lambda: _file_lock.acquire(timeout=0))

    if acquired:
        logger.info("Acquired file-based sync lock")
        return True

    # Lock not acquired - provide diagnostic information
    # Use a single try block to avoid TOCTOU race (file could vanish between exists() and stat())
    lock_file = settings.DATA_PATH / "sync.lock"
    try:
        stat_info = lock_file.stat()
        mtime = datetime.fromtimestamp(stat_info.st_mtime)
        age = datetime.now() - mtime
        age_seconds = age.total_seconds()

        logger.warning(
            f"Sync already in progress (lock held by another process). "
            f"Lock file age: {age_seconds:.1f} seconds. "
            f"If sync is stuck, manually delete: {lock_file}"
        )
    except FileNotFoundError:
        logger.info("Sync lock acquisition failed (lock file does not exist)")
    except Exception as stat_error:
        logger.warning(
            f"Sync already in progress (file lock is held). "
            f"Failed to get lock file stats: {stat_error}"
        )

    return False


def _release_sync_lock() -> None:
    """
    Release file-based sync lock.

    Note: This is a synchronous function because release() is fast (< 1ms).
    """
    try:
        _file_lock.release()
        logger.info("Released file-based sync lock")
    except Exception as e:
        logger.warning(f"Error releasing lock: {e}")


def is_sync_in_progress() -> bool:
    """
    Check if sync is currently running (cross-process check).

    Note: This checks if the lock file exists and is locked.
    For cross-process checking, we verify the lock file's existence.

    Returns:
        True if file lock is currently held by current process
    """
    # FileLock.is_locked only works for current process
    # For cross-process check, we'd need to check lock file existence
    # or attempt a non-blocking acquire
    return _file_lock.is_locked


def is_lock_held_by_other_process() -> bool:
    """
    Check if lock is held by another process without modifying the file.

    This implementation uses OS-level locking primitives to check if another
    process holds the lock WITHOUT modifying the lock file's timestamp.

    CRITICAL: This function must not modify the lock file's mtime, as that
    would break stale lock detection (age would always show 0.0 seconds).

    Returns:
        True if lock is held by another process, False otherwise
    """
    import os
    import sys

    lock_file = settings.DATA_PATH / "sync.lock"

    if _file_lock.is_locked:
        # Current process holds the lock
        return False

    if not lock_file.exists():
        # No lock file exists
        return False

    # Use OS-specific lock checking to detect if another process holds the lock
    if sys.platform == "win32":
        # Windows: Try to lock file using msvcrt
        # CRITICAL: Must use O_RDWR because msvcrt.locking requires write access
        try:
            import msvcrt
            fd = os.open(str(lock_file), os.O_RDWR)
            try:
                # Try non-blocking lock (LK_NBLCK)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                # Successfully locked - no other process holds it
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                os.close(fd)
                return False
            except OSError:
                # Another process holds the lock
                os.close(fd)
                return True
        except OSError:
            # File may not exist or permission denied - assume not locked
            return False
        except Exception as e:
            logger.debug(f"Failed to check lock status on Windows: {e}")
            return False
    else:
        # Unix/Linux/macOS: Use fcntl
        try:
            import fcntl
            # Open in read mode (os.O_RDONLY) to avoid modifying mtime
            fd = os.open(str(lock_file), os.O_RDONLY)
            try:
                # Try non-blocking exclusive lock
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Successfully locked - no other process holds it
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                return False
            except (IOError, OSError):
                # Another process holds the lock
                os.close(fd)
                return True
        except Exception as e:
            logger.debug(f"Failed to check lock status on Unix: {e}")
            # Can't determine - assume not held by others
            return False


def cleanup_stale_lock() -> None:
    """
    Clean up stale lock files from crashed processes.

    A lock is considered stale if it's older than LOCK_MAX_AGE_SECONDS.
    This prevents lock files from abandoned processes from blocking sync.

    Note: Only call this on service startup, not during normal operation.
    """
    lock_file = settings.DATA_PATH / "sync.lock"
    if not lock_file.exists():
        return

    try:
        # Check lock file age
        mtime = datetime.fromtimestamp(lock_file.stat().st_mtime)
        age = datetime.now() - mtime
        age_seconds = age.total_seconds()

        # Check if lock is stale (older than threshold)
        if age_seconds > settings.LOCK_MAX_AGE_SECONDS:
            logger.warning(
                f"Removing stale lock file (age: {age_seconds:.1f} seconds, "
                f"threshold: {settings.LOCK_MAX_AGE_SECONDS} seconds)"
            )
            try:
                lock_file.unlink()
                logger.info("Stale lock file removed successfully")
            except Exception as e:
                logger.error(f"Failed to remove stale lock file: {e}")
        else:
            logger.debug(
                f"Lock file exists but not stale (age: {age_seconds:.1f} seconds, "
                f"threshold: {settings.LOCK_MAX_AGE_SECONDS} seconds)"
            )
    except Exception as e:
        logger.error(f"Error checking stale lock: {e}")


def _set_last_sync_error(error: Optional[str]) -> None:
    """Set last sync error message (thread-safe)."""
    global _last_sync_error
    with _sync_error_lock:
        _last_sync_error = error


def get_last_sync_error() -> Optional[str]:
    """Get last sync error message (thread-safe)."""
    with _sync_error_lock:
        return _last_sync_error


def check_database_corruption() -> bool:
    """
    Check if the database is corrupted or incomplete.

    This function performs multiple checks to detect database issues:
    1. Database directory exists
    2. LanceDB table files exist
    3. Vector data files are present
    4. Basic query functionality works

    Returns:
        True if database is corrupted or incomplete, False if healthy

    Note: This is used for auto-repair during sync operations.
    """
    try:
        # Check 1: Database directory exists
        if not settings.DB_PATH.exists():
            logger.info("Database directory does not exist (not corrupted, just missing)")
            return False

        # Check 2: LanceDB table directory exists
        table_path = settings.DB_PATH / "aidefend.lance"
        if not table_path.exists():
            logger.warning("LanceDB table directory missing - database corrupted")
            return True

        # Check 3: Data directory exists
        data_path = table_path / "data"
        if not data_path.exists():
            logger.warning("LanceDB data directory missing - database corrupted")
            return True

        # Check 4: Check for data files
        try:
            data_files = list(data_path.glob("*.lance"))
            if len(data_files) == 0:
                logger.warning("No LanceDB data files found - database corrupted")
                return True
        except Exception as e:
            logger.warning(f"Failed to list data files: {e} - assuming corrupted")
            return True

        # Check 5: Try to open database and count records (most reliable check)
        try:
            import lancedb
            db = lancedb.connect(str(settings.DB_PATH))
            table = db.open_table("aidefend")
            count = table.count_rows()

            if count == 0:
                logger.warning("Database has 0 rows - likely corrupted or empty")
                return True

            logger.debug(f"Database health check passed: {count} rows")
            return False

        except Exception as e:
            logger.warning(f"Database query test failed: {e} - database corrupted")
            return True

    except Exception as e:
        logger.error(f"Error checking database corruption: {e}")
        # If we can't determine, assume it's okay to avoid unnecessary rebuilds
        return False


async def ensure_database_ready() -> bool:
    """
    Ensure database is ready for use (auto-initialize or repair if needed).

    This function is called during server startup to ensure:
    1. New installations automatically download knowledge base
    2. Corrupted databases are automatically repaired
    3. No manual intervention required

    Returns:
        True if database is ready, False if initialization/repair failed

    Raises:
        Exception: If database initialization fails critically
    """
    try:
        # Check if database exists and is healthy
        if not settings.DB_PATH.exists():
            logger.info("Database not found - initializing for first time...")
            logger.info("This will download the AIDEFEND knowledge base from GitHub")
            logger.info("Please wait, this may take 5-15 minutes...")

            # Run initial sync
            success = await run_sync()
            if not success:
                error_msg = get_last_sync_error() or "Unknown error"
                logger.error(f"Failed to initialize database: {error_msg}")
                raise RuntimeError(f"Database initialization failed: {error_msg}")

            logger.info("Database initialized successfully")
            return True

        # Database exists - check if it's corrupted
        if check_database_corruption():
            logger.warning("Database corruption detected - rebuilding...")
            logger.warning("This may take 5-15 minutes...")

            # Force rebuild by running sync
            success = await run_sync()
            if not success:
                error_msg = get_last_sync_error() or "Unknown error"
                logger.error(f"Failed to rebuild corrupted database: {error_msg}")
                raise RuntimeError(f"Database repair failed: {error_msg}")

            logger.info("Corrupted database repaired successfully")
            return True

        # Database exists and is healthy
        logger.debug("Database health check passed - no action needed")
        return True

    except Exception as e:
        logger.error(f"Fatal error ensuring database ready: {e}", exc_info=True)
        raise


def _calculate_statistics_from_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Pre-compute statistics from LanceDB records (optimization).

    This avoids expensive full table scans when get_statistics is called.
    Called during sync after records are prepared but before writing to DB.

    Args:
        records: List of LanceDB records

    Returns:
        Dict with pre-computed statistics matching get_statistics format
    """
    from collections import defaultdict

    total_documents = len(records)
    type_counts = defaultdict(int)
    tactic_counts = defaultdict(int)
    pillar_counts = defaultdict(int)
    phase_counts = defaultdict(int)

    # Enhanced features
    techniques_with_defenses = 0
    techniques_with_opensource_tools = 0
    techniques_with_commercial_tools = 0
    documents_with_code = 0

    covered_framework_sets = merge_framework_coverage_sets()
    total_framework_sets = merge_framework_coverage_sets()
    actionable_total = 0

    for record in records:
        doc_type = record.get('type', 'unknown')
        tactic = record.get('tactic', 'Unknown')
        pillar_raw = record.get('pillar', '')
        phase_raw = record.get('phase', '')

        # Parse pillar and phase (stored as JSON arrays)
        pillars = parse_json_list(pillar_raw)
        phases = parse_json_list(phase_raw)

        # Count by type
        type_counts[doc_type] += 1

        # Count by tactic
        tactic_counts[tactic] += 1

        # Count by pillar (iterate over array elements)
        if isinstance(pillars, list):
            for pillar in pillars:
                if pillar:
                    pillar_counts[pillar] += 1

        # Count by phase (iterate over array elements)
        if isinstance(phases, list):
            for phase in phases:
                if phase:
                    phase_counts[phase] += 1

        # Enhanced features (standalone techniques + sub-techniques)
        if is_actionable_record(record):
            actionable_total += 1

            defends_against = parse_json_list(record.get('defends_against', '[]'))
            tools_opensource = parse_json_list(record.get('tools_opensource', '[]'))
            tools_commercial = parse_json_list(record.get('tools_commercial', '[]'))

            if defends_against:
                techniques_with_defenses += 1
                coverage = extract_framework_coverage(defends_against)
                covered_framework_sets = merge_framework_coverage_sets(covered_framework_sets, coverage)
                total_framework_sets = merge_framework_coverage_sets(total_framework_sets, coverage)

            if tools_opensource:
                techniques_with_opensource_tools += 1
            if tools_commercial:
                techniques_with_commercial_tools += 1

        # Check for code snippets
        has_code = record.get('has_code_snippets', False)
        if has_code:
            documents_with_code += 1

    threat_framework_coverage = build_framework_metrics(
        covered_sets=covered_framework_sets,
        total_sets=total_framework_sets,
    )
    threat_framework_coverage["techniques_with_threat_mappings"] = techniques_with_defenses
    threat_framework_coverage["techniques_mapped_percentage"] = round(
        (techniques_with_defenses / actionable_total) * 100, 1
    ) if actionable_total > 0 else 0.0

    # Build statistics object (matching get_statistics format)
    statistics = {
        "overview": {
            "total_documents": total_documents,
            "total_techniques": type_counts.get('technique', 0),
            "total_subtechniques": type_counts.get('subtechnique', 0),
            "total_strategies": type_counts.get('strategy', 0),
            "total_actionable_items": actionable_total,
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "embedding_model": settings.EMBEDDING_MODEL,
            "database_path": settings.DB_PATH.name
        },
        "by_tactic": dict(sorted(tactic_counts.items())),
        "by_pillar": dict(sorted(pillar_counts.items())),
        "by_phase": dict(sorted(phase_counts.items())),
        "threat_framework_coverage": threat_framework_coverage,
        "tools_availability": {
            "techniques_with_opensource_tools": techniques_with_opensource_tools,
            "techniques_with_commercial_tools": techniques_with_commercial_tools,
            "opensource_coverage_percentage": round(
                (techniques_with_opensource_tools / actionable_total) * 100, 1
            ) if actionable_total > 0 else 0
        },
        "implementation_resources": {
            "documents_with_code_snippets": documents_with_code,
            "strategies_total": type_counts.get('strategy', 0),
            "code_coverage_percentage": round(
                (documents_with_code / type_counts.get('strategy', 1)) * 100, 1
            ) if type_counts.get('strategy', 0) > 0 else 0
        }
    }

    return statistics


def _build_threat_mappings(records: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Build reverse index: threat_id -> [technique_ids] (optimization).

    This allows O(1) lookup in defenses_for_threat tool instead of O(n) scan.

    Args:
        records: List of LanceDB records

    Returns:
        Dict mapping threat IDs to lists of technique IDs
    """
    threat_mappings = {}

    for record in records:
        # Only process actionable records so exact threat lookups return
        # directly implementable controls instead of umbrella parents.
        if not is_actionable_record(record):
            continue

        technique_id = record.get('source_id')
        defends_against = parse_json_list(record.get('defends_against', '[]'))

        try:
            if not defends_against:
                continue

            # Extract all threat items
            for framework_data in defends_against:
                framework_name = framework_data.get('framework', '')
                items = framework_data.get('items', [])

                for item in items:
                    normalized_id = normalize_framework_item(framework_name, item)
                    if normalized_id:
                        if normalized_id not in threat_mappings:
                            threat_mappings[normalized_id] = []
                        if technique_id not in threat_mappings[normalized_id]:
                            threat_mappings[normalized_id].append(technique_id)

                    # Store full item text as well (for exact matches)
                    # Normalized: strip whitespace, uppercase
                    normalized_text = item.strip().upper()
                    if normalized_text:
                        if normalized_text not in threat_mappings:
                            threat_mappings[normalized_text] = []
                        if technique_id not in threat_mappings[normalized_text]:
                            threat_mappings[normalized_text].append(technique_id)

        except (TypeError, AttributeError) as e:
            logger.warning(f"Failed to parse defends_against for {technique_id}: {e}")

    return threat_mappings


def _merge_defends_against(*mapping_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge parent/shared and child-specific framework mappings."""
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for mappings in mapping_lists:
        if not isinstance(mappings, list):
            continue

        for mapping in mappings:
            framework_name = mapping.get("framework", "")
            if not framework_name:
                continue

            if framework_name not in merged:
                merged[framework_name] = {
                    "framework": framework_name,
                    "items": [],
                }
                order.append(framework_name)

            for item in mapping.get("items", []):
                if item and item not in merged[framework_name]["items"]:
                    merged[framework_name]["items"].append(item)

    return [merged[name] for name in order]


def _using_local_framework_source() -> bool:
    """Return True when sync should stage files from a local framework repo."""
    return settings.LOCAL_FRAMEWORK_PATH is not None


def _get_local_framework_file(filename: str) -> Path:
    """Resolve a source file path inside the configured local framework repo."""
    if settings.LOCAL_FRAMEWORK_PATH is None:
        raise ValueError("LOCAL_FRAMEWORK_PATH is not configured")

    safe_filename = sanitize_filename(filename)
    if safe_filename == "aidefend-intro.js":
        return settings.LOCAL_FRAMEWORK_PATH / safe_filename
    return settings.local_framework_tactics_path / safe_filename


def _compute_local_framework_signature() -> Optional[str]:
    """Compute a stable content hash for the local framework source tree."""
    digest = hashlib.sha1(usedforsecurity=False)
    missing_required: List[str] = []

    for filename in settings.AIDEFEND_FILES:
        source_path = _get_local_framework_file(filename)
        if not source_path.exists():
            if filename == "aidefend-intro.js":
                continue
            missing_required.append(filename)
            continue

        digest.update(filename.encode("utf-8"))
        digest.update(source_path.read_bytes())

    if missing_required:
        logger.error(
            "Missing required files in local framework source",
            extra={
                "local_framework_path": str(settings.LOCAL_FRAMEWORK_PATH),
                "missing_files": missing_required,
            }
        )
        return None

    return digest.hexdigest()


def _stage_local_framework_file(filename: str) -> Optional[Path]:
    """Copy a local framework file into RAW_PATH for normal parsing."""
    safe_filename = sanitize_filename(filename)
    source_path = _get_local_framework_file(safe_filename)

    if not source_path.exists():
        if safe_filename == "aidefend-intro.js":
            logger.warning(f"Local source file missing (non-critical): {source_path}")
        else:
            logger.error(f"Local source file missing: {source_path}")
        return None

    file_path = settings.RAW_PATH / safe_filename
    validated_path = validate_file_path(file_path, settings.RAW_PATH)
    shutil.copyfile(source_path, validated_path)
    set_secure_file_permissions(validated_path)

    file_size = validated_path.stat().st_size
    logger.info(
        f"Staged {safe_filename} from local framework ({format_bytes(file_size)})",
        extra={"file_name": safe_filename, "source_path": str(source_path), "size": file_size}
    )
    return validated_path


async def fetch_latest_commit_sha() -> Optional[str]:
    """
    Fetch the latest commit SHA from GitHub repository.

    Returns:
        Commit SHA string or None if failed
    """
    if _using_local_framework_source():
        try:
            signature = _compute_local_framework_signature()
            if not signature:
                return None
            validated_signature = validate_commit_sha(signature)
            logger.info(f"Latest local framework signature: {validated_signature[:8]}")
            return validated_signature
        except Exception as e:
            error_detail = (
                f"Unexpected error computing local framework signature: "
                f"{type(e).__name__} - {str(e)}"
            )
            logger.error(error_detail)
            return None

    url = f"{settings.github_repo_api_url}/commits/{settings.GITHUB_BRANCH}"

    try:
        # Validate URL before making request
        validate_github_url(url, settings.github_repo_path)

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AIDEFEND-MCP-Service/1.0"
            }

            response = await client.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            sha = data.get("sha")

            if not sha:
                error_detail = "No SHA in GitHub response"
                logger.error(error_detail)
                return None

            # Validate SHA format
            validated_sha = validate_commit_sha(sha)
            logger.info(f"Latest GitHub commit: {validated_sha[:8]}")
            return validated_sha

    except httpx.HTTPStatusError as e:
        error_detail = f"GitHub API HTTP error: {e.response.status_code} - {e.response.reason_phrase} (URL: {url})"
        logger.error(error_detail)
        return None
    except httpx.RequestError as e:
        error_detail = f"GitHub API request error: {type(e).__name__} - {str(e)} (URL: {url})"
        logger.error(error_detail)
        return None
    except Exception as e:
        error_detail = f"Unexpected error fetching commit: {type(e).__name__} - {str(e)}"
        logger.error(error_detail)
        return None


async def download_file(filename: str, commit_sha: str) -> Optional[Path]:
    """
    Download a single file from GitHub.

    Args:
        filename: Name of file to download
        commit_sha: Git commit SHA

    Returns:
        Path to downloaded file or None if failed
    """
    if _using_local_framework_source():
        return await asyncio.to_thread(_stage_local_framework_file, filename)

    try:
        # Sanitize filename
        safe_filename = sanitize_filename(filename)

        # Construct URL
        url = settings.get_raw_file_url(safe_filename, commit_sha)

        # Validate URL
        validate_github_url(url, settings.github_repo_path)

        logger.info(f"Downloading {safe_filename}...")

        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {"User-Agent": "AIDEFEND-MCP-Service/1.0"}
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            content = response.text

            # Save to raw content directory
            file_path = settings.RAW_PATH / safe_filename

            # Validate path
            validated_path = validate_file_path(file_path, settings.RAW_PATH)

            # Write file
            validated_path.write_text(content, encoding='utf-8')

            # Set secure permissions
            set_secure_file_permissions(validated_path)

            # Log file info
            file_size = validated_path.stat().st_size
            logger.info(
                f"Downloaded {safe_filename} ({format_bytes(file_size)})",
                extra={"file_name": safe_filename, "size": file_size}
            )

            return validated_path

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Failed to download {filename}: HTTP {e.response.status_code}",
            extra={"file_name": filename, "status_code": e.response.status_code}
        )
        return None
    except Exception as e:
        logger.error(f"Error downloading {filename}: {e}")
        return None


async def download_intro_file(commit_sha: str) -> Optional[Path]:
    """
    Download aidefend-intro.js file from repository root.

    This file is in the root directory, not in tactics/, so needs special handling.
    It's optional for operation (used only for version extraction).

    Args:
        commit_sha: Git commit SHA

    Returns:
        Path to downloaded file or None if failed (non-critical)
    """
    filename = "aidefend-intro.js"
    if _using_local_framework_source():
        return await asyncio.to_thread(_stage_local_framework_file, filename)

    try:
        url = f"{settings.github_raw_base_url}/{commit_sha}/{filename}"

        logger.info(f"Downloading {filename} from root...")

        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {"User-Agent": "AIDEFEND-MCP-Service/1.0"}
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            file_path = settings.RAW_PATH / filename
            file_path.write_text(response.text, encoding='utf-8')
            set_secure_file_permissions(file_path)

            logger.info(f"Downloaded {filename} from root directory")
            return file_path

    except Exception as e:
        logger.warning(f"Failed to download {filename} (non-critical): {e}")
        return None  # Non-critical - intro file is optional


def parse_tactic_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Parse a tactic .js file using regex.

    Args:
        file_path: Path to .js file

    Returns:
        Parsed tactic data or None if failed
    """
    try:
        parsed_data = parse_js_file_with_node(file_path)

        # Validate expected structure
        if not isinstance(parsed_data, dict):
            logger.error(f"Parsed data is not a dict: {file_path.name}")
            return None

        required_keys = {"name", "techniques"}
        if not all(key in parsed_data for key in required_keys):
            logger.error(
                f"Missing required keys in {file_path.name}",
                extra={"required": list(required_keys), "found": list(parsed_data.keys())}
            )
            return None

        logger.info(
            f"Parsed {file_path.name}",
            extra={
                "tactic": parsed_data.get("name"),
                "techniques": len(parsed_data.get("techniques", []))
            }
        )

        return parsed_data

    except Exception as e:
        logger.error(f"Failed to parse {file_path.name}: {e}")
        return None


def extract_framework_version(intro_file_path: Path) -> Optional[str]:
    """
    Extract AIDEFEND framework version from aidefend-intro.js.

    Args:
        intro_file_path: Path to aidefend-intro.js file

    Returns:
        Version string (e.g., "1.20251107") or None if not found

    Example:
        >>> version = extract_framework_version(Path("data/raw_content/aidefend-intro.js"))
        >>> print(version)  # "1.20251107"
    """
    try:
        # Parse the intro file using Node.js parser
        parsed = parse_js_file_with_node(intro_file_path)

        if not isinstance(parsed, dict):
            logger.warning(f"aidefend-intro.js parsed data is not a dict")
            return None

        # Navigate the structure: sections -> find "Version & Date" -> extract version
        sections = parsed.get('sections', [])
        if not isinstance(sections, list):
            logger.warning(f"aidefend-intro.js 'sections' is not a list")
            return None

        for section in sections:
            if not isinstance(section, dict):
                continue

            title = section.get('title', '')
            if title == 'Version & Date':
                paragraphs = section.get('paragraphs', [])

                if not isinstance(paragraphs, list):
                    continue

                for para in paragraphs:
                    if isinstance(para, str) and para.strip().startswith('Version:'):
                        # Extract version number after "Version:"
                        version = para.split(':', 1)[1].strip()
                        logger.info(f"Extracted framework version: {version}")
                        return version

        logger.warning("Version field not found in aidefend-intro.js")
        return None

    except FileNotFoundError:
        logger.warning(f"aidefend-intro.js not found at {intro_file_path}")
        return None
    except Exception as e:
        logger.error(f"Failed to extract framework version: {e}")
        return None


def extract_documents_from_tactic(tactic_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Transform tactic data into flat document list for embedding.

    Args:
        tactic_data: Parsed tactic data

    Returns:
        List of document dicts
    """
    documents = []
    tactic_name = tactic_data.get("name", "Unknown")

    for technique in tactic_data.get("techniques", []):
        tech_id = technique.get("id", "Unknown")
        tech_name = technique.get("name", "Unknown")
        tech_desc = technique.get("description", "")

        # Extract threat framework mappings
        defends_against = technique.get("defendsAgainst", [])

        # Extract tool lists
        tools_opensource = technique.get("toolsOpenSource", [])
        tools_commercial = technique.get("toolsCommercial", [])

        # Extract implementation strategies for techniques WITHOUT subtechniques
        # Note: Techniques WITH subtechniques have strategies in subtechniques only
        #       Techniques WITHOUT subtechniques have strategies in parent technique
        tech_implementation_strategies = technique.get("implementationGuidance", [])

        # Check if technique has code snippets in its strategies
        tech_has_code = False
        for strat in tech_implementation_strategies:
            how_to = strat.get("howTo", "")
            if how_to:
                soup_check = BeautifulSoup(how_to, 'html.parser')
                if soup_check.find_all(['pre', 'code']):
                    tech_has_code = True
                    break

        # Document for technique
        tech_text = f"Technique: {tech_name}\nID: {tech_id}\nDescription: {tech_desc}"

        # Add defends-against info to text for better semantic search
        if defends_against:
            frameworks_text = []
            for fw in defends_against:
                fw_name = fw.get("framework", "")
                items = fw.get("items", [])
                if items:
                    frameworks_text.append(f"{fw_name}: {', '.join(items)}")
            if frameworks_text:
                tech_text += "\nDefends Against: " + "; ".join(frameworks_text)

        documents.append({
            "text": tech_text,
            "source_id": tech_id,
            "tactic": tactic_name,
            "type": "technique",
            "name": tech_name,
            "pillar": technique.get("pillar", ""),
            "phase": technique.get("phase", ""),
            "defends_against": defends_against,
            "tools_opensource": tools_opensource,
            "tools_commercial": tools_commercial,
            "parent_technique_id": None,  # Techniques have no parent (use None instead of empty string)
            "implementation_guidance": tech_implementation_strategies,  # Extract from technique
            "has_code_snippets": tech_has_code  # Check technique's strategies for code
        })

        # Documents for sub-techniques
        for sub_tech in technique.get("subTechniques", []):
            sub_id = sub_tech.get("id", "Unknown")
            sub_name = sub_tech.get("name", "Unknown")
            sub_desc = sub_tech.get("description", "")
            sub_pillar = sub_tech.get("pillar", "")
            sub_phase = sub_tech.get("phase", "")
            sub_defends_against = _merge_defends_against(
                defends_against,
                sub_tech.get("defendsAgainst", []),
            )
            sub_tools_opensource = sub_tech.get("toolsOpenSource", [])
            sub_tools_commercial = sub_tech.get("toolsCommercial", [])

            # Extract implementation strategies (preserve full HTML for code extraction)
            implementation_guidance = sub_tech.get("implementationGuidance", [])

            # Check if any strategy has code snippets (using BeautifulSoup for robustness)
            # This ensures consistency with code_snippets.py extraction logic
            has_code = False
            for strat in implementation_guidance:
                how_to = strat.get("howTo", "")
                if how_to:
                    soup_check = BeautifulSoup(how_to, 'html.parser')
                    if soup_check.find_all(['pre', 'code']):
                        has_code = True
                        break

            sub_text = (
                f"Sub-Technique: {sub_name}\n"
                f"ID: {sub_id}\n"
                f"Parent: {tech_name}\n"
                f"Pillar: {sub_pillar}\n"
                f"Phase: {sub_phase}\n"
                f"Description: {sub_desc}"
            )

            if sub_defends_against:
                frameworks_text = []
                for fw in sub_defends_against:
                    fw_name = fw.get("framework", "")
                    items = fw.get("items", [])
                    if items:
                        frameworks_text.append(f"{fw_name}: {', '.join(items)}")
                if frameworks_text:
                    sub_text += "\nDefends Against: " + "; ".join(frameworks_text)

            documents.append({
                "text": sub_text,
                "source_id": sub_id,
                "tactic": tactic_name,
                "type": "subtechnique",
                "name": sub_name,
                "pillar": sub_pillar,
                "phase": sub_phase,
                "defends_against": sub_defends_against,
                "tools_opensource": sub_tools_opensource,
                "tools_commercial": sub_tools_commercial,
                "parent_technique_id": tech_id,
                "implementation_guidance": implementation_guidance,
                "has_code_snippets": has_code
            })

            # Documents for implementation strategies
            for i, strategy in enumerate(sub_tech.get("implementationGuidance", []), 1):
                strategy_name = strategy.get("implementation", "Implementation")
                how_to_html = strategy.get("howTo", "")

                # For embedding text: Use BeautifulSoup to safely remove HTML
                soup = BeautifulSoup(how_to_html, 'html.parser')

                # Check if this strategy has code (before removing tags)
                has_code = bool(soup.find_all(['pre', 'code']))

                # Remove code tags - we don't want code in the embedding text
                for code_tag in soup.find_all(['pre', 'code']):
                    code_tag.decompose()

                # Get clean text
                clean_how_to = soup.get_text(separator=' ', strip=True)

                strategy_id = f"{sub_id}.S{i}"
                strategy_text = (
                    f"Tactic: {tactic_name}. Technique: {tech_name}. Sub-Technique: {sub_name}\n"
                    f"Implementation Guidance: {strategy_name}\n"
                    f"ID: {strategy_id}\n"
                    f"How-To: {clean_how_to}"
                )

                if sub_defends_against:
                    frameworks_text = []
                    for fw in sub_defends_against:
                        fw_name = fw.get("framework", "")
                        items = fw.get("items", [])
                        if items:
                            frameworks_text.append(f"{fw_name}: {', '.join(items)}")
                    if frameworks_text:
                        strategy_text += "\nDefends Against: " + "; ".join(frameworks_text)

                documents.append({
                    "text": strategy_text,
                    "source_id": strategy_id,
                    "tactic": tactic_name,
                    "type": "strategy",
                    "name": f"{sub_name} - {strategy_name}",
                    "pillar": sub_pillar,
                    "phase": sub_phase,
                    "defends_against": sub_defends_against,
                    "tools_opensource": sub_tools_opensource,
                    "tools_commercial": sub_tools_commercial,
                    "parent_technique_id": sub_id,
                    "implementation_guidance": [{
                        "implementation": strategy_name,
                        "howTo": how_to_html  # Preserve full HTML
                    }],
                    "has_code_snippets": has_code
                })

        # Standalone techniques need their own strategy documents.
        if not technique.get("subTechniques", []):
            for i, strategy in enumerate(tech_implementation_strategies, 1):
                strategy_name = strategy.get("implementation", "Implementation")
                how_to_html = strategy.get("howTo", "")

                soup = BeautifulSoup(how_to_html, 'html.parser')
                has_code = bool(soup.find_all(['pre', 'code']))

                for code_tag in soup.find_all(['pre', 'code']):
                    code_tag.decompose()

                clean_how_to = soup.get_text(separator=' ', strip=True)
                strategy_id = f"{tech_id}.S{i}"
                strategy_text = (
                    f"Tactic: {tactic_name}. Technique: {tech_name}\n"
                    f"Implementation Guidance: {strategy_name}\n"
                    f"ID: {strategy_id}\n"
                    f"How-To: {clean_how_to}"
                )

                if defends_against:
                    frameworks_text = []
                    for fw in defends_against:
                        fw_name = fw.get("framework", "")
                        items = fw.get("items", [])
                        if items:
                            frameworks_text.append(f"{fw_name}: {', '.join(items)}")
                    if frameworks_text:
                        strategy_text += "\nDefends Against: " + "; ".join(frameworks_text)

                documents.append({
                    "text": strategy_text,
                    "source_id": strategy_id,
                    "tactic": tactic_name,
                    "type": "strategy",
                    "name": f"{tech_name} - {strategy_name}",
                    "pillar": technique.get("pillar", ""),
                    "phase": technique.get("phase", ""),
                    "defends_against": defends_against,
                    "tools_opensource": tools_opensource,
                    "tools_commercial": tools_commercial,
                    "parent_technique_id": tech_id,
                    "implementation_guidance": [{
                        "implementation": strategy_name,
                        "howTo": how_to_html
                    }],
                    "has_code_snippets": has_code
                })

    logger.info(
        f"Extracted {len(documents)} documents from {tactic_name}",
        extra={"tactic": tactic_name, "doc_count": len(documents)}
    )

    return documents


def _register_custom_embedding_models_for_sync():
    """
    Register custom embedding models for sync operations.
    This is a duplicate of the registration in app/core.py to avoid circular imports.
    """
    try:
        from fastembed.common.model_description import PoolingType, ModelSource

        # Check if Xenova/multilingual-e5-base is already registered
        supported = [m["model"] for m in TextEmbedding.list_supported_models()]
        if "Xenova/multilingual-e5-base" in supported:
            logger.debug("Xenova/multilingual-e5-base already supported natively")
            return

        # Register Xenova/multilingual-e5-base (768-dim, 512 tokens, 100+ languages)
        # Using Xenova's pre-quantized Int8 version for 75% size reduction (1.1GB → 280MB)
        logger.info("Registering custom model for sync: Xenova/multilingual-e5-base (Quantized Int8)")
        TextEmbedding.add_custom_model(
            model="Xenova/multilingual-e5-base",
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf="Xenova/multilingual-e5-base"),
            dim=768,
            model_file="onnx/model_quantized.onnx",
            description="Multilingual E5 Base (Quantized Int8 version) - 768 dimensions, 512 tokens, 100+ languages",
            license="MIT",
            size_in_gb=0.28,
            additional_files=[]
        )



        logger.info("Custom embedding models registered successfully for sync")

    except Exception as e:
        logger.warning(f"Failed to register custom embedding models for sync: {e}")


async def embed_and_index(documents: List[Dict[str, Any]]) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Embed documents and store in LanceDB.

    Args:
        documents: List of document dicts

    Returns:
        Tuple of (success: bool, statistics: Optional[Dict])
        - success: True if successful, False otherwise
        - statistics: Pre-computed statistics dict, or None if failed
    """
    try:
        # Register custom models before loading (for multilingual-e5-base support)
        _register_custom_embedding_models_for_sync()

        logger.info("Loading embedding model: Xenova/multilingual-e5-base (Quantized Int8)")

        # Load embedding model with timeout (prevents hanging on network issues)
        try:
            model = await asyncio.wait_for(
                asyncio.to_thread(
                    TextEmbedding,
                    model_name=settings.EMBEDDING_MODEL
                ),
                timeout=300  # 5 minute timeout for model download
            )
        except asyncio.TimeoutError:
            raise Exception(
                f"Embedding model download timed out after 300 seconds\n\n"
                f"Model: {settings.EMBEDDING_MODEL}\n"
                f"Expected size: ~280 MB (quantized Int8)\n\n"
                "Possible causes:\n"
                "- Slow internet connection (need stable connection for model download)\n"
                "- HuggingFace service slow or unavailable\n"
                "- Firewall blocking huggingface.co domain\n\n"
                "Troubleshooting:\n"
                "1. Check internet speed (need >1 Mbps for model download)\n"
                "2. Check HuggingFace status: https://status.huggingface.co\n"
                "3. Try again in a few minutes\n"
                "4. Check if model is cached in ~/.cache/fastembed/"
            )
        except Exception as e:
            raise Exception(
                f"Failed to load embedding model\n\n"
                f"Model: {settings.EMBEDDING_MODEL}\n"
                f"Error type: {type(e).__name__}\n"
                f"Error message: {str(e)}\n\n"
                "Possible causes:\n"
                "- HuggingFace model download failed\n"
                "- Corrupted model cache\n"
                "- Insufficient disk space in ~/.cache/fastembed/\n"
                "- ONNX runtime initialization failure\n\n"
                "Troubleshooting:\n"
                "1. Clear model cache: rm -rf ~/.cache/fastembed/\n"
                "2. Check disk space: df -h ~/.cache/\n"
                "3. Verify internet connection to huggingface.co"
            )

        # Initialize embedding cache
        cache_file = settings.DATA_PATH / "embedding_cache.json"
        cache = EmbeddingCache(
            cache_file=cache_file,
            model_name=settings.EMBEDDING_MODEL,
            dimension=settings.EMBEDDING_DIMENSION
        )

        # Auto-cleanup: remove cache entries for deleted documents
        current_doc_ids = {doc["source_id"] for doc in documents}
        cache.auto_cleanup(current_doc_ids)

        # Check cache and generate embeddings (with progress indicators)
        logger.info(f"🔄 Generating embeddings for {len(documents)} documents (using cache when possible)...")

        embeddings = []
        texts_to_embed = []
        text_to_embed_indices = []

        # First pass: check cache for all documents
        for i, doc in enumerate(documents):
            content_hash = compute_content_hash(doc["text"], settings.EMBEDDING_MODEL)
            cached_embedding = cache.get(content_hash)

            if cached_embedding is not None:
                # Use cached embedding
                embeddings.append(cached_embedding)
            else:
                # Need to generate embedding
                embeddings.append(None)  # Placeholder
                texts_to_embed.append(doc["text"])
                text_to_embed_indices.append((i, content_hash, doc["source_id"]))

        cache_stats = cache.get_stats()
        logger.info(
            f"📊 Cache stats: {cache_stats['hits']} hits, {cache_stats['misses']} misses "
            f"({cache_stats['hit_rate']*100:.1f}% hit rate)"
        )

        # Second pass: generate embeddings for cache misses
        if texts_to_embed:
            total_to_embed = len(texts_to_embed)
            logger.info(f"🔄 Generating {total_to_embed} new embeddings...")
            logger.info(f"⏱️  Estimated time: {total_to_embed * 1.0 / 60:.1f}-{total_to_embed * 2.0 / 60:.1f} minutes (CPU-based, ~1-2 sec per document)")

            # Helper function to run embedding generation with progress in thread
            def generate_embeddings_with_progress():
                """Generate embeddings with progress logging (runs in thread)."""
                import gc
                import sys
                from datetime import datetime
                embeddings_list = []
                # Update every 10 items (~1.8% for 549 docs, real-time: every 10-20 seconds)
                progress_interval = 10

                # Generate embeddings (batch_size matches progress_interval for aligned updates)
                embeddings_generator = model.embed(texts_to_embed, batch_size=10)

                for idx, embedding in enumerate(embeddings_generator):
                    embeddings_list.append(embedding)

                    # Display progress every interval (console only, no duplicate logging)
                    if (idx + 1) % progress_interval == 0 or (idx + 1) == total_to_embed:
                        progress_pct = (idx + 1) / total_to_embed * 100
                        # Add timestamp like other log messages
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        progress_msg = f"{timestamp} - INFO - Progress: {idx + 1}/{total_to_embed} ({progress_pct:.1f}%) - {total_to_embed - (idx + 1)} remaining"

                        # Print to console with explicit flush for real-time display
                        print(progress_msg, file=sys.stderr)
                        sys.stderr.flush()  # Explicit flush to ensure immediate output

                    # Hint GC every 50 embeddings to manage memory for large datasets
                    if (idx + 1) % 50 == 0:
                        gc.collect()

                return embeddings_list

            # Run embedding generation in thread with progress reporting
            new_embeddings = await asyncio.to_thread(generate_embeddings_with_progress)

            # Store new embeddings in cache and fill placeholders
            for j, (orig_idx, content_hash, source_id) in enumerate(text_to_embed_indices):
                embedding = new_embeddings[j]
                embeddings[orig_idx] = embedding
                cache.set(content_hash, source_id, embedding)

            logger.info(f"✅ Generated and cached {len(new_embeddings)} new embeddings")
        else:
            logger.info(f"✅ All {len(documents)} embeddings retrieved from cache!")

        # Save cache to disk
        cache.save()

        logger.info(f"✅ Embedding complete: {len(embeddings)} vectors ready (768 dimensions each)")
        logger.info("💾 Creating LanceDB records...")

        # Prepare LanceDB records with extended schema
        records = []
        for i, doc in enumerate(documents):
            # Convert complex types to JSON strings for LanceDB storage
            import json

            records.append({
                "vector": embeddings[i].tolist(),
                "text": doc["text"],
                "source_id": doc["source_id"],
                "tactic": doc["tactic"],
                "type": doc["type"],
                "name": doc["name"],
                # Convert pillar and phase to JSON strings (they are arrays now)
                "pillar": json.dumps(doc.get("pillar", [])),
                "phase": json.dumps(doc.get("phase", [])),
                # New fields for enhanced functionality
                "defends_against": json.dumps(doc.get("defends_against", [])),
                "tools_opensource": json.dumps(doc.get("tools_opensource", [])),
                "tools_commercial": json.dumps(doc.get("tools_commercial", [])),
                "parent_technique_id": doc.get("parent_technique_id", ""),
                "implementation_guidance": json.dumps(doc.get("implementation_guidance", [])),
                "has_code_snippets": doc.get("has_code_snippets", False)
            })

        # Pre-compute statistics from records (optimization for get_statistics tool)
        logger.info("📊 Pre-computing statistics from records...")
        statistics = _calculate_statistics_from_records(records)
        logger.info(f"✅ Statistics pre-computed: {statistics['overview']['total_documents']} documents")

        # Build threat mappings reverse index (optimization for defenses_for_threat tool)
        logger.info("🔗 Building threat mappings reverse index...")
        threat_mappings = _build_threat_mappings(records)
        statistics['threat_mappings'] = threat_mappings
        logger.info(f"✅ Threat mappings built: {len(threat_mappings)} unique threat IDs")

        # Connect to LanceDB
        logger.info(f"💾 Connecting to LanceDB: {settings.DB_PATH.name}")
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))

        # Blue-Green Deployment: Write to temporary table first
        temp_table_name = "aidefend_new_sync"

        # Drop temporary table if exists (from previous failed sync)
        try:
            table_names = await asyncio.to_thread(db.table_names)
            if temp_table_name in table_names:
                await asyncio.to_thread(db.drop_table, temp_table_name)
                logger.info(f"Cleaned up orphaned '{temp_table_name}' table from previous failed sync")
        except Exception as cleanup_err:
            logger.warning(f"Could not clean up temp table '{temp_table_name}': {cleanup_err}")

        # Create new table with explicit schema
        logger.info(f"💾 Writing {len(records)} records to database ('{temp_table_name}' table)...")

        await asyncio.to_thread(
            db.create_table,
            temp_table_name,
            data=records
        )

        logger.info(f"✅ Database write complete: {len(records)} records written")

        # Verify new table was created successfully
        table_names = await asyncio.to_thread(db.table_names)
        if temp_table_name not in table_names:
            raise Exception(f"Failed to create {temp_table_name} table")

        logger.info(f"Successfully created {temp_table_name} table. Performing atomic swap...")

        # Atomic swap: Rename tables for zero-downtime deployment
        # Uses rollback on failure to prevent inconsistent state

        aidefend_path = settings.DB_PATH / "aidefend.lance"
        backup_path = settings.DB_PATH / "aidefend_backup.lance"
        new_sync_path = settings.DB_PATH / f"{temp_table_name}.lance"
        backed_up = False

        # 1. Delete old backup if exists
        try:
            if backup_path.exists():
                import shutil
                await asyncio.to_thread(shutil.rmtree, str(backup_path))
                logger.info("Deleted old backup table")
        except Exception as e:
            logger.warning(f"Could not delete old backup (non-critical): {e}")

        # 2. Pause query engine before swap to prevent read errors
        from app.core import query_engine
        query_engine._initialized = False
        logger.info("Query engine paused for database swap")

        try:
            # 3. Rename current aidefend to aidefend_backup (if exists)
            if aidefend_path.exists():
                await asyncio.to_thread(
                    aidefend_path.rename,
                    backup_path
                )
                backed_up = True
                logger.info("Renamed aidefend -> aidefend_backup")

            # 4. Rename new_sync to aidefend
            # On Windows, target must not exist (ensured by step 3)
            await asyncio.to_thread(
                new_sync_path.rename,
                aidefend_path
            )

            logger.info("Atomic swap complete: aidefend_new_sync -> aidefend")

        except Exception as swap_error:
            # ROLLBACK: restore backup if swap failed
            logger.error(f"Database swap failed: {swap_error}. Attempting rollback...")
            if backed_up and backup_path.exists() and not aidefend_path.exists():
                try:
                    await asyncio.to_thread(backup_path.rename, aidefend_path)
                    logger.info("Rollback successful: restored aidefend from backup")
                except Exception as rollback_error:
                    logger.error(f"Rollback also failed: {rollback_error}. Manual intervention required.")
            raise swap_error

        # 5. Reload query engine to use new table
        reload_success = await query_engine.reload()
        if reload_success:
            logger.info("Query engine reloaded successfully")
        else:
            logger.warning("Query engine reload reported failure (may still work)")

        logger.info("Zero-downtime sync complete!")

        # Close LanceDB connection explicitly to release file handles
        try:
            del db
        except Exception:
            logger.debug("Could not explicitly release LanceDB handle", exc_info=True)

        # Set secure permissions on database directory
        db_dir = settings.DB_PATH
        if db_dir.exists():
            for file in db_dir.rglob("*"):
                if file.is_file():
                    set_secure_file_permissions(file)

        # Return success with pre-computed statistics
        return (True, statistics)

    except Exception as e:
        # Provide detailed error information
        error_detail = (
            f"Embedding and indexing failed\n\n"
            f"Error type: {type(e).__name__}\n"
            f"Error message: {str(e)}\n\n"
        )

        # Add context based on error type
        if "timeout" in str(e).lower():
            error_detail += (
                "This appears to be a timeout error.\n"
                "The embedding model download or generation took too long.\n"
            )
        elif "memory" in str(e).lower() or isinstance(e, MemoryError):
            error_detail += (
                "This appears to be a memory error.\n"
                f"Processing {len(documents)} documents requires significant RAM.\n"
                "Try freeing up memory or reducing batch size.\n"
            )
        elif "permission" in str(e).lower() or "access" in str(e).lower():
            error_detail += (
                "This appears to be a file permission error.\n"
                f"Cannot write to database path: {settings.DB_PATH}\n"
                "Check directory permissions.\n"
            )
        elif "disk" in str(e).lower() or "space" in str(e).lower():
            error_detail += (
                "This appears to be a disk space error.\n"
                f"Database path: {settings.DB_PATH}\n"
                "Check available disk space: df -h\n"
            )
        else:
            error_detail += (
                "Check the full stack trace in the logs for diagnostic information.\n"
            )

        logger.error(error_detail, exc_info=True)
        return (False, None)


async def core_sync(force_rebuild: bool = False) -> bool:
    """
    Core sync logic (shared between CLI and MCP).

    This function contains the main sync logic without lock management.
    Caller is responsible for acquiring/releasing locks.

    Args:
        force_rebuild: If True, rebuild database even if already up-to-date

    Returns:
        True if sync successful, False otherwise

    Note: This function does NOT acquire locks - caller must handle locking.
    """
    _set_last_sync_error(None)

    try:
        logger.info("=" * 60)
        logger.info("Starting AIDEFEND sync process")
        logger.info(f"Cache schema version: {settings.CACHE_SCHEMA_VERSION}")
        if _using_local_framework_source():
            logger.info(f"Sync source: local framework ({settings.LOCAL_FRAMEWORK_PATH})")
        else:
            logger.info(f"Sync source: GitHub {settings.github_repo_path}@{settings.GITHUB_BRANCH}")
        logger.info("=" * 60)

        # Fetch latest commit
        latest_sha = await fetch_latest_commit_sha()
        if not latest_sha:
            if _using_local_framework_source():
                error_msg = (
                    "Could not read local AIDEFEND framework source\n\n"
                    "Possible causes:\n"
                    "- LOCAL_FRAMEWORK_PATH points to the wrong directory\n"
                    "- Required tactic files are missing from the local repo\n"
                    "- Files cannot be read due to permissions\n\n"
                    f"Local framework path: {settings.LOCAL_FRAMEWORK_PATH}\n"
                    f"Tactics path: {settings.local_framework_tactics_path}\n\n"
                    "Check the logs for missing or unreadable files."
                )
            else:
                error_msg = (
                    "Could not fetch latest commit from GitHub\n\n"
                    "Possible causes:\n"
                    "- Network connectivity issues (check internet connection)\n"
                    "- GitHub API rate limiting (wait a few minutes)\n"
                    "- GitHub service unavailable (check https://www.githubstatus.com)\n"
                    "- Repository URL configured incorrectly\n\n"
                    f"Repository: {settings.github_repo_path}\n"
                    f"Branch: {settings.GITHUB_BRANCH}\n\n"
                    "Check the logs for detailed HTTP error codes and network diagnostics."
                )
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False

        # Check if update needed (unless force_rebuild=True)
        local_sha = get_local_commit_sha()
        if local_sha == latest_sha and not force_rebuild:
            logger.info(f"Already up-to-date (commit: {local_sha[:8]})")

            # Update timestamp to indicate sync check completed
            # This shows users that the service checked for updates even if none were available
            save_sync_timestamp()

            return True

        if force_rebuild:
            logger.info(f"Force rebuild requested (current: {local_sha[:8] if local_sha else 'None'})")
        else:
            logger.info(f"Update available: {local_sha[:8] if local_sha else 'None'} -> {latest_sha[:8]}")

        # Download all files in parallel (faster than serial downloads)
        if _using_local_framework_source():
            logger.info(f"📥 Staging {len(settings.AIDEFEND_FILES)} files from local framework...")
        else:
            logger.info(f"📥 Downloading {len(settings.AIDEFEND_FILES)} files in parallel...")

        download_tasks = []
        for filename in settings.AIDEFEND_FILES:
            if filename == "aidefend-intro.js":
                # Special handling for intro file (in root directory)
                download_tasks.append(download_intro_file(latest_sha))
            else:
                download_tasks.append(download_file(filename, latest_sha))

        # Execute all downloads concurrently
        download_results = await asyncio.gather(*download_tasks, return_exceptions=True)

        # Process results
        downloaded_files: List[Path] = []
        failed_required = []

        for i, result in enumerate(download_results):
            filename = settings.AIDEFEND_FILES[i]

            if isinstance(result, Exception):
                # Download task raised an exception
                if filename == "aidefend-intro.js":
                    logger.warning(f"Failed to download {filename} (non-critical): {result}")
                else:
                    logger.error(f"Failed to download {filename}: {result}")
                    failed_required.append(filename)
            elif result is None:
                # Download failed (function returned None)
                if filename == "aidefend-intro.js":
                    logger.warning(f"Failed to download {filename} (non-critical)")
                else:
                    logger.error(f"Failed to download {filename}")
                    failed_required.append(filename)
            else:
                # Download successful
                downloaded_files.append(result)

        # Check if any required files failed
        if failed_required:
            if _using_local_framework_source():
                error_msg = (
                    f"Failed to stage {len(failed_required)} required file(s) from local framework\n\n"
                    f"Failed files:\n" +
                    "\n".join([f"  - {f}" for f in failed_required]) + "\n\n"
                    "Possible causes:\n"
                    "- Files were renamed or removed in the local repo\n"
                    "- LOCAL_FRAMEWORK_PATH points to the wrong checkout\n"
                    "- File permissions prevent reading source files\n\n"
                    f"Local framework path: {settings.LOCAL_FRAMEWORK_PATH}\n"
                    f"Source signature: {latest_sha[:8]}\n\n"
                    "Check the logs above for the specific missing or unreadable file."
                )
            else:
                error_msg = (
                    f"Failed to download {len(failed_required)} required file(s) from GitHub\n\n"
                    f"Failed files:\n" +
                    "\n".join([f"  - {f}" for f in failed_required]) + "\n\n"
                    "Possible causes:\n"
                    "- Network connectivity issues\n"
                    "- GitHub rate limiting (429 status code)\n"
                    "- Files moved/deleted in repository\n"
                    "- Firewall blocking raw.githubusercontent.com\n\n"
                    f"Repository: {settings.github_repo_path}\n"
                    f"Commit: {latest_sha[:8]}\n\n"
                    "Check the logs above for specific HTTP error codes (404, 403, 500, etc.) "
                    "and network error details for each failed file."
                )
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False

        # Check if enough files downloaded (intro.js is optional)
        required_count = len(settings.AIDEFEND_FILES) - 1  # Exclude optional intro.js
        if len(downloaded_files) < required_count:
            error_msg = (
                f"Too few files downloaded: {len(downloaded_files)}/{required_count} required files\n\n"
                f"Expected {required_count} tactic files but only got {len(downloaded_files)}.\n"
                f"This usually indicates network issues or incomplete downloads.\n\n"
                "Check the download errors in the logs above for specific failure reasons."
            )
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False

        logger.info(f"✅ Downloaded {len(downloaded_files)}/{len(settings.AIDEFEND_FILES)} files")

        # Extract framework version from aidefend-intro.js (if present)
        framework_version = None
        intro_file_path = settings.RAW_PATH / "aidefend-intro.js"
        if intro_file_path.exists():
            try:
                framework_version = await asyncio.to_thread(
                    extract_framework_version,
                    intro_file_path
                )
                if framework_version:
                    logger.info(f"Framework version: {framework_version}")
            except Exception as e:
                logger.warning(f"Failed to extract framework version: {e}")
                # Non-critical failure, continue sync

        # Parse all files with resilient error handling
        # Single file failure should not fail entire sync
        logger.info(f"📄 Parsing {len(downloaded_files)} files...")

        all_documents = []
        failed_files = []
        total_files = len(downloaded_files)
        parsed_count = 0

        for file_path in downloaded_files:
            # Skip aidefend-intro.js - it's for metadata only, not for embedding
            if file_path.name == "aidefend-intro.js":
                logger.info(f"Skipping {file_path.name} (metadata only)")
                continue

            parsed_count += 1

            try:
                # Use asyncio.to_thread to avoid blocking the event loop
                # (parse_tactic_file involves file I/O and CPU-intensive regex operations)
                tactic_data = await asyncio.to_thread(parse_tactic_file, file_path)

                if tactic_data:
                    # Use asyncio.to_thread for extract_documents_from_tactic as well
                    # (involves CPU-intensive data transformation)
                    documents = await asyncio.to_thread(extract_documents_from_tactic, tactic_data)
                    all_documents.extend(documents)

                    # Show progress every 10 files or at completion
                    if parsed_count % 10 == 0 or parsed_count == total_files:
                        progress_pct = (parsed_count / total_files) * 100
                        logger.info(f"📄 Parsing progress: {parsed_count}/{total_files} ({progress_pct:.1f}%) - {len(documents)} docs from {file_path.name}")
                else:
                    # parse_tactic_file returned None
                    raise Exception("parse_tactic_file returned None")

            except Exception as e:
                error_msg = (
                    f"Failed to parse {file_path.name}\n\n"
                    f"Error type: {type(e).__name__}\n"
                    f"Error message: {str(e)}\n\n"
                    "Possible causes:\n"
                    "- Missing Node.js dependencies (run: npm install)\n"
                    "- Invalid JavaScript syntax in source file\n"
                    "- Node.js not installed or not in PATH\n"
                    "- Corrupted download\n\n"
                    "Check if 'acorn' parser is installed: npm list acorn"
                )
                logger.error(error_msg, exc_info=True)
                _set_last_sync_error(error_msg)  # Record last error
                failed_files.append(file_path.name)
                # Continue processing other files instead of returning False

        logger.info(f"✅ Parsing complete: {len(all_documents)} documents extracted from {parsed_count} files")

        # Only fail if ALL files failed to parse
        if not all_documents:
            error_msg = (
                f"No documents extracted - all {len(failed_files)} file(s) failed to parse\n\n"
                f"Failed files:\n" +
                "\n".join([f"  - {f}" for f in failed_files]) + "\n\n"
                "This is a critical failure. Common causes:\n"
                "- Node.js not installed (check: node --version)\n"
                "- Missing npm dependencies (run: npm install)\n"
                "- All downloaded files are corrupted\n"
                "- Parser script (parse_js_module.mjs) missing or broken\n\n"
                "Troubleshooting steps:\n"
                "1. Verify Node.js installed: node --version (need v18+)\n"
                "2. Install dependencies: npm install\n"
                "3. Check parser exists: verify parse_js_module.mjs file present\n"
                "4. Try manual test: node parse_js_module.mjs <file.js>"
            )
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False

        # Warn if partial failure occurred
        if failed_files:
            warning_msg = (
                f"⚠️ Partial sync - {len(failed_files)} file(s) failed to parse\n\n"
                f"Failed files:\n" +
                "\n".join([f"  - {f}" for f in failed_files[:5]]) +  # Show first 5
                (f"\n  ... and {len(failed_files) - 5} more" if len(failed_files) > 5 else "") + "\n\n"
                f"Successfully parsed: {parsed_count - len(failed_files)}/{parsed_count} files\n"
                f"Documents indexed: {len(all_documents)}\n\n"
                "The knowledge base is functional but incomplete. "
                "Check the detailed error messages above for each failed file."
            )
            logger.warning(warning_msg)
            # Update _last_sync_error to show partial failure with details
            _set_last_sync_error(warning_msg)

        # Embed and index
        success, statistics = await embed_and_index(all_documents)
        if not success:
            error_msg = (
                "Failed to embed and index documents\n\n"
                "This step involves:\n"
                "1. Downloading embedding model from HuggingFace (if not cached)\n"
                "2. Generating 768-dim vectors for each document\n"
                "3. Writing to LanceDB database\n\n"
                "Possible causes:\n"
                "- HuggingFace model download failed (network/timeout)\n"
                "- Insufficient disk space for database\n"
                "- Insufficient memory for embedding model\n"
                "- Database file permissions issue\n"
                "- Corrupted embedding cache\n\n"
                f"Model: {settings.EMBEDDING_MODEL}\n"
                f"Database path: {settings.DB_PATH}\n\n"
                "Check the detailed error in the logs above for the specific failure point:\n"
                "- Model loading timeout (300s limit)\n"
                "- Embedding generation error\n"
                "- LanceDB write error"
            )
            _set_last_sync_error(error_msg)
            return False

        # Verify we actually got documents (catch edge cases)
        # Fixed: total_documents is nested in overview dict
        total_docs = statistics.get("overview", {}).get("total_documents", 0) if statistics else 0
        if total_docs == 0:
            error_msg = (
                "Sync completed but resulted in 0 documents\n\n"
                "This should never happen if embed_and_index() succeeded.\n"
                "This indicates a logic error in the sync pipeline.\n\n"
                f"Documents extracted: {len(all_documents)}\n"
                f"Statistics returned: {'Yes' if statistics else 'No'}\n\n"
                "This is a bug - please report this issue."
            )
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False

        logger.info(f"Successfully indexed {total_docs} documents")

        # Reload query engine to use new database
        # THIS IS CRITICAL - sync is NOT successful if reload fails
        try:
            # Import here to avoid circular import issues
            from app.core import query_engine
            logger.info("Reloading query engine to use updated database...")
            reload_success = await query_engine.reload()

            if not reload_success:
                error_msg = (
                    "Query engine failed to reload after sync\n\n"
                    "The database was updated successfully, but the query engine "
                    "could not reload to use the new data.\n\n"
                    "Possible causes:\n"
                    "- Database corruption during atomic swap\n"
                    "- File permissions on new database\n"
                    "- Embedding model mismatch\n"
                    "- LanceDB table schema incompatibility\n\n"
                    f"Database path: {settings.DB_PATH}\n"
                    f"Expected table: aidefend\n\n"
                    "Try restarting the service or running with --resync flag."
                )
                logger.error(error_msg)
                _set_last_sync_error(error_msg)
                return False

            # Verify reload actually made service ready
            if not query_engine.is_ready:
                error_msg = (
                    "Query engine reload completed but service not ready\n\n"
                    "The reload function returned success but is_ready = False.\n"
                    "This indicates the database loaded but model initialization failed.\n\n"
                    f"Database loaded: {query_engine._table is not None if hasattr(query_engine, '_table') else 'Unknown'}\n"
                    f"Model loaded: {query_engine._model is not None if hasattr(query_engine, '_model') else 'Unknown'}\n\n"
                    "Check the query engine logs for model loading errors."
                )
                logger.error(error_msg)
                _set_last_sync_error(error_msg)
                return False

            logger.info("Query engine reloaded successfully")

        except Exception as e:
            error_msg = (
                f"Failed to reload query engine after sync\n\n"
                f"Error type: {type(e).__name__}\n"
                f"Error message: {str(e)}\n\n"
                "The database sync completed successfully but the query engine "
                "crashed while trying to reload.\n\n"
                "Possible causes:\n"
                "- Corrupted database file during atomic swap\n"
                "- Import error (circular dependency)\n"
                "- Model initialization failure\n"
                "- Database schema incompatibility\n\n"
                "The service may need to be restarted. Check the full stack trace in the logs."
            )
            logger.error(error_msg, exc_info=True)
            _set_last_sync_error(error_msg)
            return False

        # Save version info ONLY after reload succeeds and is_ready = True
        # This prevents the "false success" bug where sync fails but version is saved
        logger.info("Saving version info after successful reload...")
        save_version_info(
            latest_sha,
            {
                "framework_version": framework_version,  # AIDEFEND semantic version (e.g., "1.20251107")
                "total_documents": len(all_documents),
                "total_actionable_items": statistics.get("overview", {}).get("total_actionable_items"),
                "embedding_model": settings.EMBEDDING_MODEL,  # Store model used for this sync
                "embedding_dimension": settings.EMBEDDING_DIMENSION,  # Store dimension for this sync
                "statistics": statistics  # Pre-computed statistics for get_statistics tool
            }
        )

        # Auto-create vector index for faster queries (if enabled)
        # This is done AFTER sync succeeds and query engine reloads
        # Non-critical failure won't affect sync success
        await _create_vector_index_if_needed()

        logger.info("=" * 60)
        logger.info(f"Sync complete! Updated to commit {latest_sha[:8]}")
        logger.info(f"Indexed {len(all_documents)} documents")
        logger.info(f"Query engine ready state: {query_engine.is_ready}")
        logger.info("=" * 60)

        return True

    except Exception as e:
        error_msg = (
            f"Unexpected error during sync\n\n"
            f"Error type: {type(e).__name__}\n"
            f"Error message: {str(e)}\n\n"
            "An unexpected exception occurred that was not caught by specific error handlers.\n"
            "This could be:\n"
            "- Python runtime error (MemoryError, OSError, etc.)\n"
            "- Uncaught validation error\n"
            "- Third-party library exception\n"
            "- Logic bug in sync code\n\n"
            "Check the full stack trace in the logs for diagnostic information."
        )
        logger.error(error_msg, exc_info=True)
        _set_last_sync_error(error_msg)
        return False


async def run_sync() -> bool:
    """
    Execute complete sync process with file-based locking.

    This is a wrapper around core_sync() that handles lock acquisition and release.
    For backward compatibility and auto-sync scenarios.

    Returns:
        True if sync successful, False otherwise
    """
    # Try to acquire lock
    if not await _acquire_sync_lock():
        logger.warning("Sync already in progress, skipping")
        return False

    try:
        # Call core sync logic (no force rebuild, normal sync)
        return await core_sync(force_rebuild=False)
    finally:
        # Always release lock when done
        _release_sync_lock()


async def _create_vector_index_if_needed() -> bool:
    """
    Create LanceDB vector index for faster searches (2-5x speedup).

    This is automatically called after first successful sync.
    Users can disable with AUTO_CREATE_INDEX=false in .env

    Returns:
        True if index created or already exists, False on failure
    """
    try:
        import lancedb

        # Check if indexing is enabled
        if not settings.AUTO_CREATE_INDEX:
            logger.info("AUTO_CREATE_INDEX=false, skipping index creation")
            return True

        # Check if database exists
        if not settings.DB_PATH.exists():
            logger.warning("Database not found, cannot create index")
            return False

        logger.info("Checking if vector index needed...")

        # Connect to database
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

        # Check if index already exists
        # LanceDB doesn't have a direct "has_index()" method, but we can check indices list
        try:
            indices = await asyncio.to_thread(lambda: table.list_indices())
            if indices and len(indices) > 0:
                logger.info(f"✅ Vector index already exists ({len(indices)} indices found), skipping creation")
                return True
        except Exception:
            # list_indices() might not be available or might error - proceed with creation
            logger.debug("Could not inspect existing LanceDB indices; continuing with creation", exc_info=True)

        # Get row count
        row_count = await asyncio.to_thread(table.count_rows)

        # For small datasets (< 1000 rows), index creation has minimal benefit
        # and can cause KMeans warnings about empty clusters
        if row_count < 1000:
            logger.info(
                f"Database has {row_count} rows (< 1000). "
                "Vector index provides minimal benefit for small datasets. Skipping index creation."
            )
            return True

        # Calculate optimal index parameters based on dataset size
        # Small-medium datasets (1K-10K): Use sqrt(row_count) partitions
        # Large datasets (>10K): Use more partitions for better performance
        if row_count < 10000:
            num_partitions = max(8, int(row_count ** 0.5))
        else:
            num_partitions = max(256, int(row_count ** 0.5))

        dimension = settings.EMBEDDING_DIMENSION
        num_sub_vectors = dimension // 16

        logger.info("=" * 60)
        logger.info("CREATING VECTOR INDEX (This may take 5-10 minutes)")
        logger.info("=" * 60)
        logger.info(f"Database rows: {row_count}")
        logger.info(f"Index partitions: {num_partitions}")
        logger.info(f"Sub-vectors: {num_sub_vectors}")
        logger.info("This is a one-time operation for 2-5x faster queries...")

        # Create index
        await asyncio.to_thread(
            table.create_index,
            metric="cosine",
            num_partitions=num_partitions,
            num_sub_vectors=num_sub_vectors
        )

        logger.info("=" * 60)
        logger.info("✅ Vector index created successfully!")
        logger.info("Future queries will be 2-5x faster")
        logger.info("=" * 60)

        return True

    except Exception as e:
        # Non-critical failure - service still works without index
        logger.warning(
            f"Failed to create vector index (non-critical): {e}",
            exc_info=True
        )
        logger.info("Service will continue to work (queries may be slower without index)")
        return False


async def sync_loop():
    """Background task that runs sync periodically with exponential backoff on failure."""
    logger.info(
        f"Starting sync loop (interval: {settings.SYNC_INTERVAL_SECONDS}s)"
    )

    consecutive_failures = 0
    max_backoff = 3600 * 4  # Cap at 4 hours

    while True:
        try:
            # Calculate sleep with backoff on consecutive failures
            if consecutive_failures > 0:
                backoff = min(
                    settings.SYNC_INTERVAL_SECONDS * (2 ** consecutive_failures),
                    max_backoff
                )
                logger.warning(
                    f"Sync backoff: waiting {backoff:.0f}s after {consecutive_failures} consecutive failure(s)"
                )
                await asyncio.sleep(backoff)
            else:
                await asyncio.sleep(settings.SYNC_INTERVAL_SECONDS)

            if settings.ENABLE_AUTO_SYNC:
                success = await run_sync()
                if success:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    logger.warning(
                        f"Sync failed ({consecutive_failures} consecutive). "
                        f"Next retry with backoff."
                    )
        except asyncio.CancelledError:
            logger.info("Sync loop cancelled")
            break
        except Exception as e:
            consecutive_failures += 1
            logger.error(f"Error in sync loop: {e}", exc_info=True)
