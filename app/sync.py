"""
Synchronization service for AIDEFEND framework content.
Handles GitHub sync, parsing, embedding, and indexing with security.
"""

import asyncio
import hashlib
import httpx
import lancedb
import pyarrow as pa
import time
import re
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from datetime import datetime, timezone
from fastembed import TextEmbedding
from bs4 import BeautifulSoup

from app.config import settings
from app.logger import get_logger
from app.security import (
    PathTraversalError,
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
    load_version_info,
    format_bytes
)
from app.embedding_cache import EmbeddingCache, compute_content_hash
from app.framework_utils import (
    FRAMEWORK_LABELS,
    build_framework_metrics,
    extract_framework_coverage,
    is_actionable_record,
    merge_framework_coverage_sets,
    normalize_framework_item,
    parse_json_list,
)
from app.framework_manifest import (
    MAX_MANIFEST_BYTES,
    FrameworkManifestError,
    load_local_tactic_manifest,
    parse_tactic_manifest,
)

logger = get_logger(__name__)


FRAMEWORK_MANIFEST_FILENAME = "main.js"
FRAMEWORK_INTRO_FILENAME = "aidefend-intro.js"
FRAMEWORK_SCHEMA_FILENAME = "data-schema.md"
MAX_FRAMEWORK_SCHEMA_BYTES = 1024 * 1024
UNKNOWN_FRAMEWORK_SCHEMA_VERSION = "unknown"
LEGACY_FRAMEWORK_VERSION = "1.20260704"
LEGACY_FRAMEWORK_REPOSITORY = "edward-playground/aidefense-framework"
LEGACY_FRAMEWORK_SOURCE_REVISION = "145ab11c510e38c022073056fd5933fecc02cef8"
LEGACY_FRAMEWORK_CONTENT_SHA256 = (
    "3baac4cbdea29401d3b87c259b20ebe653e13708e7974b73d46a6d6ac3cf4fe9"
)
VALID_PILLARS = {"model", "app", "data", "infra"}
VALID_PHASES = {"scoping", "building", "validation", "operation", "response", "improvement"}
VALID_FRAMEWORK_LABELS = set(FRAMEWORK_LABELS.values())
EXPECTED_FRAMEWORK_LABELS = [
    "MITRE ATLAS",
    "MAESTRO",
    "OWASP LLM Top 10 2025",
    "OWASP ML Top 10 2023",
    "OWASP Top 10 for Agentic Applications 2026",
    "NIST Adversarial Machine Learning 2025",
    "Cisco Integrated AI Security and Safety Framework",
    "Google Secure AI Framework 2.0 - Risks",
    "Databricks AI Security Framework 3.0",
]
TACTIC_ID_SEGMENT = r"[A-Z][A-Z0-9]*"
CONTROL_ID_PATTERN = re.compile(
    rf"AID-{TACTIC_ID_SEGMENT}-\d{{3}}(?:\.\d{{3}})?\Z"
)
GUIDANCE_ID_PATTERN = re.compile(
    rf"(?P<control>AID-{TACTIC_ID_SEGMENT}-\d{{3}}(?:\.\d{{3}})?)"
    r"-G(?P<ordinal>\d{3})\Z"
)
NOT_APPLICABLE_PATTERN = re.compile(r"^N/A(?:\s+\([^\r\n]+\))?$", re.IGNORECASE)
SOURCE_AVAILABLE_TOOL_PATTERN = re.compile(
    r"^.+\s\([^();]+;\s(?:source-available|open-weight)\)$"
)
AUTHORING_TOOL_FIELDS = (
    "toolsOpenSource",
    "toolsSourceAvailable",
    "toolsCommercial",
)
_SCHEMA_VERSION_COMPONENT_PATTERN = r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}"
_AUTHORING_SCHEMA_DECLARATION_PATTERN = re.compile(
    r"^>[ \t]*\*\*Version\*\*[ \t]*:",
    re.MULTILINE,
)
_AUTHORING_SCHEMA_VERSION_PATTERN = re.compile(
    rf"^>[ \t]*\*\*Version\*\*[ \t]*:[ \t]*"
    rf"(?P<version>{_SCHEMA_VERSION_COMPONENT_PATTERN})[ \t]*$",
    re.MULTILINE,
)
_PUBLIC_SCHEMA_DECLARATION_PATTERN = re.compile(
    r"^[ \t]*schemaVersion[ \t]*:",
    re.MULTILINE,
)
_PUBLIC_SCHEMA_VERSION_PATTERN = re.compile(
    rf'^[ \t]*schemaVersion[ \t]*:[ \t]*"'
    rf'(?P<version>{_SCHEMA_VERSION_COMPONENT_PATTERN})"[ \t]*,?[ \t]*(?://[^\r\n]*)?$',
    re.MULTILINE,
)


# Custom cross-process file lock implementation
# Replaces filelock library to avoid modifying lock file timestamps
class SyncFileLock:
    """
    Cross-process file lock using OS-level primitives.

    The lock file mtime records the beginning of the current acquisition.
    Read-only lock probes do not modify it.

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

        Args:
            timeout: Timeout in seconds (0 = non-blocking)

        Returns:
            True if lock acquired, False otherwise

        Raises:
            Exception: If lock file cannot be opened or system call fails
        """
        if self._is_locked:
            # A second acquisition by the same singleton is a concurrent sync,
            # not a re-entrant success. Returning True here allowed one process
            # to run two syncs against the same staging paths and database.
            return False

        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            # Create lock file if it does not exist, but do not truncate before
            # the OS lock has been acquired.
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

                os.fsync(self.lock_fd)
                # Make stale-lock diagnostics describe this acquisition rather
                # than an unrelated, previously released lock.
                os.utime(str(self.lock_path), None)
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

    Successful acquisition refreshes the lock-file timestamp to the start of
    that sync. Read-only probes do not modify it, preserving accurate stale
    lock diagnostics.

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
    return _file_lock.is_locked or is_lock_held_by_other_process()


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

        # A live OS lock is authoritative even when its mtime is unexpectedly
        # old (for example, a legitimately long first-time model build).
        if _file_lock.is_locked or is_lock_held_by_other_process():
            logger.debug("Lock file is actively held; stale cleanup skipped")
            return

        # Check if an unheld lock file is stale (older than threshold)
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
            success = await run_sync(force_rebuild=True)
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
            success = await run_sync(force_rebuild=True)
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
    actionable_tactic_counts = defaultdict(int)
    pillar_counts = defaultdict(int)
    phase_counts = defaultdict(int)

    # Enhanced features
    techniques_with_defenses = 0
    techniques_with_opensource_tools = 0
    techniques_with_source_available_tools = 0
    techniques_with_commercial_tools = 0
    controls_with_scope_boundaries = 0
    actionable_controls_with_scope_boundaries = 0
    documents_with_code = 0
    canonical_guidance_documents = 0

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

        scope_boundary = record.get('scope_boundary', '{}')
        has_scope_boundary = (
            bool(scope_boundary)
            if isinstance(scope_boundary, dict)
            else scope_boundary not in ('', '{}', 'null')
        )
        if doc_type in ('technique', 'subtechnique') and has_scope_boundary:
            controls_with_scope_boundaries += 1

        # Enhanced features (standalone techniques + sub-techniques)
        if is_actionable_record(record):
            actionable_total += 1
            actionable_tactic_counts[tactic] += 1

            for pillar in pillars:
                if pillar:
                    pillar_counts[pillar] += 1
            for phase in phases:
                if phase:
                    phase_counts[phase] += 1

            defends_against = parse_json_list(record.get('defends_against', '[]'))
            tools_opensource = parse_json_list(record.get('tools_opensource', '[]'))
            tools_source_available = parse_json_list(
                record.get('tools_source_available', '[]')
            )
            tools_commercial = parse_json_list(record.get('tools_commercial', '[]'))

            if defends_against:
                techniques_with_defenses += 1
                coverage = extract_framework_coverage(defends_against)
                covered_framework_sets = merge_framework_coverage_sets(covered_framework_sets, coverage)
                total_framework_sets = merge_framework_coverage_sets(total_framework_sets, coverage)

            if tools_opensource:
                techniques_with_opensource_tools += 1
            if tools_source_available:
                techniques_with_source_available_tools += 1
            if tools_commercial:
                techniques_with_commercial_tools += 1
            if has_scope_boundary:
                actionable_controls_with_scope_boundaries += 1

        # Check for code snippets
        has_code = record.get('has_code_snippets', False)
        if doc_type == 'strategy' and has_code:
            documents_with_code += 1
        if doc_type == 'strategy' and record.get('guidance_id'):
            canonical_guidance_documents += 1

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
            "total_parent_families": sum(
                1 for record in records if record.get('is_parent_family') is True
            ),
            "total_standalone_techniques": sum(
                1
                for record in records
                if record.get('type') == 'technique' and is_actionable_record(record)
            ),
            "total_actionable_items": actionable_total,
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "embedding_model": settings.EMBEDDING_MODEL,
            "database_path": settings.DB_PATH.name
        },
        "by_tactic": dict(sorted(tactic_counts.items())),
        "actionable_by_tactic": dict(sorted(actionable_tactic_counts.items())),
        "by_pillar": dict(sorted(pillar_counts.items())),
        "by_phase": dict(sorted(phase_counts.items())),
        "threat_framework_coverage": threat_framework_coverage,
        "tools_availability": {
            "techniques_with_opensource_tools": techniques_with_opensource_tools,
            "techniques_with_source_available_tools": techniques_with_source_available_tools,
            "techniques_with_commercial_tools": techniques_with_commercial_tools,
            "controls_with_scope_boundaries": controls_with_scope_boundaries,
            "actionable_controls_with_scope_boundaries": (
                actionable_controls_with_scope_boundaries
            ),
            "opensource_coverage_percentage": round(
                (techniques_with_opensource_tools / actionable_total) * 100, 1
            ) if actionable_total > 0 else 0,
            "source_available_coverage_percentage": round(
                (techniques_with_source_available_tools / actionable_total) * 100, 1
            ) if actionable_total > 0 else 0,
            "commercial_coverage_percentage": round(
                (techniques_with_commercial_tools / actionable_total) * 100, 1
            ) if actionable_total > 0 else 0,
        },
        "implementation_resources": {
            "documents_with_code_snippets": documents_with_code,
            "canonical_guidance_documents": canonical_guidance_documents,
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
    threat_mappings: Dict[str, List[str]] = {}
    casefolded_keys: Dict[str, str] = {}

    def add_mapping(key: Optional[str], technique_id: str) -> None:
        """Add one lookup key without case-insensitive duplicate JSON members."""
        if not key:
            return

        key = key.strip()
        if not key:
            return

        folded_key = key.casefold()
        stored_key = casefolded_keys.get(folded_key)
        if stored_key is None:
            stored_key = key
            casefolded_keys[folded_key] = stored_key
            threat_mappings[stored_key] = []

        if technique_id not in threat_mappings[stored_key]:
            threat_mappings[stored_key].append(technique_id)

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
                    add_mapping(normalized_id, technique_id)

                    # Store full item text as well (for exact matches)
                    # Normalized: strip whitespace, uppercase
                    normalized_text = item.strip().upper()
                    add_mapping(normalized_text, technique_id)

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
    if safe_filename in {
        FRAMEWORK_INTRO_FILENAME,
        FRAMEWORK_MANIFEST_FILENAME,
        FRAMEWORK_SCHEMA_FILENAME,
    }:
        return settings.LOCAL_FRAMEWORK_PATH / safe_filename
    return settings.local_framework_tactics_path / safe_filename


def _framework_source_files(tactic_files: Sequence[str]) -> List[str]:
    """Return the exact ordered file list covered by framework provenance hashes."""
    tactic_list = list(tactic_files)
    if not tactic_list or len(tactic_list) != len(set(tactic_list)):
        raise FrameworkManifestError("framework tactic file list must be non-empty and unique")
    return [FRAMEWORK_INTRO_FILENAME, *tactic_list]


def _compute_local_framework_signature(
    tactic_files: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Compute a stable content hash for the local framework source tree."""
    digest = hashlib.sha1(usedforsecurity=False)
    missing_required: List[str] = []
    if tactic_files is None:
        tactic_files = load_local_tactic_manifest()
    source_files = _framework_source_files(tactic_files)

    for filename in source_files:
        source_path = _get_local_framework_file(filename)
        if not source_path.exists():
            missing_required.append(filename)
            continue

        digest.update(filename.encode("utf-8"))
        digest.update(_read_canonical_framework_bytes(source_path))

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


def _read_canonical_framework_bytes(path: Path) -> bytes:
    """Read source bytes with Git-compatible text newline normalization.

    Git commonly normalizes text blobs to LF when committing a Windows working
    tree. Normalizing CRLF and lone CR here makes the local pre-push digest
    comparable with the immutable raw GitHub bytes after the framework is
    published, without changing the staged parser input.
    """
    source_bytes = path.read_bytes()
    return source_bytes.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _compute_staged_framework_digest(
    staged_files: List[Path],
    algorithm: str = "sha256",
    source_files: Optional[Sequence[str]] = None,
) -> str:
    """Hash the exact canonical bytes staged for one sync.

    Filenames and bytes are processed in framework-manifest order. This gives
    local-working-tree and immutable GitHub syncs a source-independent digest
    that can be compared during the post-push release gate.

    ``source_files`` intentionally excludes ``main.js``. The manifest controls
    membership and order, while the historical digest remains the hash of the
    intro plus tactic payloads. Omitting the argument preserves the legacy
    configured list for callers verifying an older staged index.
    """
    ordered_source_files = list(
        settings.AIDEFEND_FILES if source_files is None else source_files
    )
    if not ordered_source_files or len(ordered_source_files) != len(set(ordered_source_files)):
        raise ValueError("Cannot hash an empty or duplicate framework source file list")
    staged_by_name = {path.name: path for path in staged_files}
    missing = [
        filename
        for filename in ordered_source_files
        if filename not in staged_by_name
    ]
    if missing:
        raise ValueError(
            "Cannot hash incomplete staged framework source: "
            + ", ".join(missing)
        )

    if algorithm == "sha1":
        digest = hashlib.sha1(usedforsecurity=False)
    elif algorithm == "sha256":
        digest = hashlib.sha256()
    else:
        raise ValueError(f"Unsupported framework digest algorithm: {algorithm}")

    for filename in ordered_source_files:
        digest.update(filename.encode("utf-8"))
        digest.update(_read_canonical_framework_bytes(staged_by_name[filename]))

    return digest.hexdigest()


def _stage_local_framework_file(filename: str) -> Optional[Path]:
    """Copy a local framework file into RAW_PATH for normal parsing."""
    safe_filename = sanitize_filename(filename)
    source_path = _get_local_framework_file(safe_filename)

    if not source_path.exists():
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


def _unique_framework_schema_version(
    source: str,
    *,
    label: str,
    declaration_pattern: re.Pattern[str],
    value_pattern: re.Pattern[str],
) -> str:
    """Return one unambiguous schema version or the forward-compatible fallback."""
    declaration_count = len(declaration_pattern.findall(source))
    matches = value_pattern.findall(source)
    if declaration_count == 1 and len(matches) == 1:
        return matches[0]

    logger.warning(
        "Framework %s schema version metadata is missing, duplicated, or format-drifted; "
        "recording '%s'",
        label,
        UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
        extra={
            "schema_version_kind": label,
            "schema_declaration_count": declaration_count,
            "schema_valid_value_count": len(matches),
        },
    )
    return UNKNOWN_FRAMEWORK_SCHEMA_VERSION


def extract_framework_schema_versions(
    schema_path: Optional[Path],
    *,
    base_dir: Path,
) -> Tuple[str, str]:
    """Read authoring/public schema versions without blocking compatible content.

    ``data-schema.md`` is optional metadata. It is accepted only from the
    caller-provided root, below a small size limit, and as strict UTF-8. Missing,
    unsafe, oversized, unreadable, or format-drifted metadata is reported as
    ``unknown`` rather than retaining a stale built-in version.
    """
    if schema_path is None:
        logger.warning(
            "Framework data-schema.md is unavailable; recording schema versions as '%s'",
            UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
        )
        return (
            UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
            UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
        )

    try:
        validated_path = validate_file_path(Path(schema_path), Path(base_dir))
        if not validated_path.is_file():
            raise FileNotFoundError(f"framework schema metadata is missing: {validated_path}")
        file_size = validated_path.stat().st_size
        if file_size > MAX_FRAMEWORK_SCHEMA_BYTES:
            raise ValueError(
                "framework data-schema.md exceeds the "
                f"{MAX_FRAMEWORK_SCHEMA_BYTES}-byte size limit"
            )
        source = validated_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError, ValueError, PathTraversalError) as exc:
        logger.warning(
            "Framework schema metadata could not be safely read; recording schema "
            "versions as '%s': %s",
            UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
            exc,
        )
        return (
            UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
            UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
        )

    authoring_version = _unique_framework_schema_version(
        source,
        label="authoring",
        declaration_pattern=_AUTHORING_SCHEMA_DECLARATION_PATTERN,
        value_pattern=_AUTHORING_SCHEMA_VERSION_PATTERN,
    )
    public_version = _unique_framework_schema_version(
        source,
        label="public",
        declaration_pattern=_PUBLIC_SCHEMA_DECLARATION_PATTERN,
        value_pattern=_PUBLIC_SCHEMA_VERSION_PATTERN,
    )
    return authoring_version, public_version


def compute_framework_schema_metadata_sha256(
    schema_path: Optional[Path],
    *,
    base_dir: Path,
) -> Optional[str]:
    """Hash safely staged schema metadata without joining the content digest."""
    if schema_path is None:
        return None
    try:
        validated_path = validate_file_path(Path(schema_path), Path(base_dir))
        if not validated_path.is_file():
            return None
        if validated_path.stat().st_size > MAX_FRAMEWORK_SCHEMA_BYTES:
            return None
        return hashlib.sha256(validated_path.read_bytes()).hexdigest()
    except Exception as exc:
        logger.warning("Could not hash optional framework schema metadata: %s", exc)
        return None


def _stored_source_revision(version_info: Dict[str, Any]) -> str:
    return str(
        version_info.get("source_revision")
        or version_info.get("commit_sha")
        or ""
    )


def resolve_effective_framework_schema_versions(
    discovered_versions: Tuple[str, str],
    *,
    version_info: Dict[str, Any],
    current_source_revision: str,
    source_kind: str,
    metadata_available: bool,
) -> Tuple[str, str]:
    """Resolve optional metadata without a same-commit remote fetch downgrade.

    Only an unavailable GitHub fetch at the exact immutable commit may retain a
    previously stored safe value. A staged-but-malformed document is authoritative
    ``unknown`` in both source modes. Local metadata is mutable independently of
    the tactic digest, so it never inherits an old value when discovery fails.
    """
    stored_revision = _stored_source_revision(version_info)
    allow_remote_fetch_fallback = (
        source_kind == "github"
        and not metadata_available
        and bool(stored_revision)
        and stored_revision == current_source_revision
    )
    metadata_keys = (
        "framework_authoring_schema_version",
        "framework_public_schema_version",
    )
    effective_versions: List[str] = []

    for discovered, metadata_key in zip(discovered_versions, metadata_keys):
        if discovered != UNKNOWN_FRAMEWORK_SCHEMA_VERSION:
            effective_versions.append(discovered)
            continue

        stored_value = version_info.get(metadata_key)
        if (
            allow_remote_fetch_fallback
            and isinstance(stored_value, str)
            and re.fullmatch(_SCHEMA_VERSION_COMPONENT_PATTERN, stored_value)
        ):
            logger.warning(
                "Framework schema discovery was unavailable for unchanged source %s; "
                "retaining stored %s=%s",
                current_source_revision[:8],
                metadata_key,
                stored_value,
            )
            effective_versions.append(stored_value)
        else:
            effective_versions.append(UNKNOWN_FRAMEWORK_SCHEMA_VERSION)

    return effective_versions[0], effective_versions[1]


def resolve_effective_framework_schema_metadata_sha256(
    discovered_digest: Optional[str],
    *,
    version_info: Dict[str, Any],
    current_source_revision: str,
    source_kind: str,
    metadata_available: bool,
) -> Optional[str]:
    """Resolve the separately stored schema-document digest."""
    if discovered_digest is not None:
        return discovered_digest

    stored_digest = version_info.get("framework_schema_metadata_sha256")
    if (
        source_kind == "github"
        and not metadata_available
        and _stored_source_revision(version_info) == current_source_revision
        and isinstance(stored_digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", stored_digest)
    ):
        logger.warning(
            "Framework schema metadata fetch was unavailable for unchanged GitHub "
            "commit %s; retaining its stored document digest",
            current_source_revision[:8],
        )
        return stored_digest
    return None


def uses_legacy_framework_contract(
    *,
    source_kind: str,
    source_repository: str,
    source_revision: str,
    source_content_sha256: str,
    framework_version: str,
    schema_metadata_available: bool,
    framework_authoring_schema_version: str,
    framework_public_schema_version: str,
) -> bool:
    """Select the one pre-schema public release that needs compatibility.

    The legacy allowance is deliberately not inferred from missing schema
    metadata alone. A new or malformed release without data-schema.md must
    continue through the strict contract and fail closed. Only the canonical
    GitHub repository's known 2026-07-04 release may omit guidance IDs and use
    its historical parent threat-union semantics.
    """
    return (
        source_kind == "github"
        and source_repository.strip().lower() == LEGACY_FRAMEWORK_REPOSITORY
        and source_revision.strip().lower() == LEGACY_FRAMEWORK_SOURCE_REVISION
        and source_content_sha256.strip().lower() == LEGACY_FRAMEWORK_CONTENT_SHA256
        and framework_version == LEGACY_FRAMEWORK_VERSION
        and not schema_metadata_available
        and framework_authoring_schema_version == UNKNOWN_FRAMEWORK_SCHEMA_VERSION
        and framework_public_schema_version == UNKNOWN_FRAMEWORK_SCHEMA_VERSION
    )


def _discard_staged_framework_schema_file() -> None:
    """Remove optional schema metadata left by an older sync attempt."""
    try:
        staged_path = validate_file_path(
            settings.RAW_PATH / FRAMEWORK_SCHEMA_FILENAME,
            settings.RAW_PATH,
        )
        if staged_path.exists():
            staged_path.unlink()
    except Exception as exc:
        logger.warning("Could not discard stale framework schema metadata: %s", exc)


async def download_schema_metadata_file(commit_sha: str) -> Optional[Path]:
    """Stage optional root ``data-schema.md`` from the exact framework source."""
    filename = FRAMEWORK_SCHEMA_FILENAME
    try:
        destination = validate_file_path(settings.RAW_PATH / filename, settings.RAW_PATH)

        if _using_local_framework_source():
            local_framework_path = settings.LOCAL_FRAMEWORK_PATH
            if local_framework_path is None:
                raise RuntimeError('Local framework mode is active without LOCAL_FRAMEWORK_PATH')
            local_root = local_framework_path.resolve()
            source_path = validate_file_path(local_root / filename, local_root)
            if not source_path.is_file():
                raise FileNotFoundError(f"local framework schema metadata is missing: {source_path}")
            if source_path.stat().st_size > MAX_FRAMEWORK_SCHEMA_BYTES:
                raise ValueError("local framework data-schema.md exceeds the size limit")
            content = source_path.read_bytes()
            source_description = f"local framework {local_root}"
        else:
            immutable_sha = validate_commit_sha(commit_sha)
            url = f"{settings.github_raw_base_url}/{immutable_sha}/{filename}"
            validate_github_url(url, settings.github_repo_path)
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": "AIDEFEND-MCP-Service/1.0"},
                )
                response.raise_for_status()
                content = response.content
            source_description = f"immutable GitHub commit {immutable_sha[:8]}"

        if len(content) > MAX_FRAMEWORK_SCHEMA_BYTES:
            raise ValueError("framework data-schema.md exceeds the size limit")
        content.decode("utf-8-sig")

        destination.write_bytes(content)
        set_secure_file_permissions(destination)
        logger.info(
            "Staged %s from %s (%s)",
            filename,
            source_description,
            format_bytes(len(content)),
        )
        return destination
    except Exception as exc:
        _discard_staged_framework_schema_file()
        logger.warning(
            "Optional framework schema metadata is unavailable or invalid; content sync "
            "will continue with schema versions '%s': %s",
            UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
            exc,
        )
        return None


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

            # Save to raw content directory
            file_path = settings.RAW_PATH / safe_filename

            # Validate path
            validated_path = validate_file_path(file_path, settings.RAW_PATH)

            # Preserve the immutable GitHub blob bytes exactly. Parsing still
            # validates UTF-8/JavaScript later, while provenance hashing applies
            # only Git-compatible newline normalization.
            validated_path.write_bytes(response.content)

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


async def download_manifest_file(commit_sha: str) -> Optional[Path]:
    """Stage root ``main.js`` from the local tree or an immutable GitHub SHA."""
    filename = FRAMEWORK_MANIFEST_FILENAME
    if _using_local_framework_source():
        return await asyncio.to_thread(_stage_local_framework_file, filename)

    try:
        url = f"{settings.github_raw_base_url}/{commit_sha}/{filename}"
        validate_github_url(url, settings.github_repo_path)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "AIDEFEND-MCP-Service/1.0"},
            )
            response.raise_for_status()
            if len(response.content) > MAX_MANIFEST_BYTES:
                raise FrameworkManifestError("framework main.js exceeds the size limit")

            file_path = validate_file_path(settings.RAW_PATH / filename, settings.RAW_PATH)
            file_path.write_bytes(response.content)
            set_secure_file_permissions(file_path)
            logger.info(f"Downloaded {filename} from immutable commit {commit_sha[:8]}")
            return file_path
    except Exception as exc:
        logger.error(f"Failed to download {filename}: {exc}")
        return None


def parse_staged_tactic_manifest(manifest_path: Path) -> List[str]:
    """Parse a staged manifest with the same size and UTF-8 gates as local discovery."""
    if not manifest_path.is_file():
        raise FrameworkManifestError(f"framework manifest is missing: {manifest_path}")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise FrameworkManifestError("framework main.js exceeds the size limit")
    try:
        source = manifest_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise FrameworkManifestError(f"cannot read framework main.js: {exc}") from exc
    return parse_tactic_manifest(source, tactics_path=settings.GITHUB_TACTICS_PATH)


async def download_intro_file(commit_sha: str) -> Optional[Path]:
    """
    Download aidefend-intro.js file from repository root.

    This file is in the root directory, not in tactics/, so needs special handling.
    It is required release metadata used for version extraction.

    Args:
        commit_sha: Git commit SHA

    Returns:
        Path to downloaded file or None if failed
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
            file_path.write_bytes(response.content)
            set_secure_file_permissions(file_path)

            logger.info(f"Downloaded {filename} from root directory")
            return file_path

    except Exception as e:
        logger.error(f"Failed to download {filename}: {e}")
        return None


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


def validate_tactic_contract(
    tactic_data: Dict[str, Any],
    file_name: str,
    seen_control_ids: Optional[set[str]] = None,
    seen_guidance_ids: Optional[set[str]] = None,
    scope_references: Optional[List[Tuple[str, str]]] = None,
    *,
    legacy_contract: bool = False,
) -> List[str]:
    """Validate the source contract required to build a complete MCP index."""
    errors: List[str] = []
    seen_ids = seen_control_ids if seen_control_ids is not None else set()
    guidance_ids = seen_guidance_ids if seen_guidance_ids is not None else set()
    related_ids = scope_references if scope_references is not None else []

    tactic_name = tactic_data.get("name")
    if not isinstance(tactic_name, str) or not tactic_name.strip():
        errors.append(f"{file_name}: name must be a non-empty string")
    purpose = tactic_data.get("purpose")
    if not isinstance(purpose, str) or not purpose.strip():
        errors.append(f"{file_name}: purpose must be a non-empty string")

    techniques = tactic_data.get("techniques")
    if not isinstance(techniques, list) or not techniques:
        return errors + [f"{file_name}: techniques must be a non-empty array"]

    legacy_modern_markers: List[str] = []
    if legacy_contract:
        for technique_index, technique in enumerate(techniques):
            if not isinstance(technique, dict):
                continue
            technique_location = f"{file_name}.techniques[{technique_index}]"
            authored_controls = [(technique_location, technique)]
            subtechniques = technique.get("subTechniques")
            if isinstance(subtechniques, list):
                parent_location = technique.get("id") or technique_location
                authored_controls.extend(
                    (f"{parent_location}.subTechniques[{sub_index}]", subtechnique)
                    for sub_index, subtechnique in enumerate(subtechniques)
                    if isinstance(subtechnique, dict)
                )
            for control_location, control in authored_controls:
                for marker_key in ("scopeBoundary", "toolsSourceAvailable"):
                    if marker_key in control:
                        legacy_modern_markers.append(
                            f"{control_location}: legacy contract contains modern "
                            f"marker field '{marker_key}'"
                        )
                guidance = control.get("implementationGuidance")
                if isinstance(guidance, list):
                    for guidance_index, strategy in enumerate(guidance):
                        if isinstance(strategy, dict) and "id" in strategy:
                            legacy_modern_markers.append(
                                f"{control_location}.implementationGuidance"
                                f"[{guidance_index}]: legacy contract contains modern "
                                "guidance id marker"
                            )
        errors.extend(legacy_modern_markers)

    # A mixed legacy/modern payload is rejected and receives the full strict
    # validation pass. This prevents a forged old version label from disabling
    # modern guidance ownership or parent-union checks.
    legacy_shape_compatible = legacy_contract and not legacy_modern_markers

    def contains_parser_marker(value: Any) -> bool:
        if isinstance(value, str):
            return "<Identifier:" in value or "<Expression>" in value
        if isinstance(value, list):
            return any(contains_parser_marker(item) for item in value)
        if isinstance(value, dict):
            return any(contains_parser_marker(item) for item in value.values())
        return False

    if contains_parser_marker(tactic_data):
        errors.append(f"{file_name}: unresolved JavaScript expression marker found in parsed data")

    def validate_warning(value: Any, location: str) -> None:
        if value is None:
            return
        if not isinstance(value, dict):
            errors.append(f"{location}: warning must be an object")
            return
        required_keys = {"level", "description"}
        if not required_keys.issubset(value):
            errors.append(f"{location}: warning must contain level and description")
        for key in ("level", "description"):
            if not isinstance(value.get(key), str) or not value[key].strip():
                errors.append(f"{location}: warning.{key} must be a non-empty string")

    def validate_mappings(value: Any, location: str) -> None:
        if value is None:
            errors.append(f"{location}: defendsAgainst is required")
            return
        if not isinstance(value, list) or not value:
            errors.append(f"{location}: defendsAgainst must be a non-empty array")
            return
        seen_frameworks: set[str] = set()
        for index, mapping in enumerate(value):
            mapping_location = f"{location}.defendsAgainst[{index}]"
            if not isinstance(mapping, dict):
                errors.append(f"{mapping_location}: mapping must be an object")
                continue
            if not {"framework", "items"}.issubset(mapping):
                errors.append(
                    f"{mapping_location}: mapping must contain framework and items"
                )
            framework = mapping.get("framework")
            if not isinstance(framework, str) or not framework.strip():
                errors.append(f"{mapping_location}: framework must be a non-empty string")
            elif framework in seen_frameworks:
                errors.append(f"{mapping_location}: duplicate framework label '{framework}'")
            else:
                seen_frameworks.add(framework)
            items = mapping.get("items")
            if not isinstance(items, list) or not items or not all(
                isinstance(item, str) and item.strip() for item in items
            ):
                errors.append(f"{mapping_location}: items must be a non-empty array of strings")
            elif len(items) != len(set(items)):
                errors.append(f"{mapping_location}: items must not contain duplicates")
            elif any(NOT_APPLICABLE_PATTERN.fullmatch(item.strip()) for item in items) and (
                len(items) != 1
                or not NOT_APPLICABLE_PATTERN.fullmatch(items[0].strip())
            ):
                errors.append(
                    f"{mapping_location}: N/A must be the only mapping item"
                )
    def validate_scope_boundary(value: Any, control_id: str) -> None:
        if value is None:
            return
        location = f"{control_id}.scopeBoundary"
        if not isinstance(value, dict):
            errors.append(f"{location}: scopeBoundary must be an object")
            return
        if not {"responsibility", "relatedTechniques"}.issubset(value):
            errors.append(
                f"{location}: scopeBoundary must contain responsibility and relatedTechniques"
            )
        responsibility = value.get("responsibility")
        if not isinstance(responsibility, str) or not responsibility.strip():
            errors.append(f"{location}.responsibility must be a non-empty string")
        elif re.search(r"<[^>]+>", responsibility):
            errors.append(f"{location}.responsibility must be plain text, not HTML")
        relationships = value.get("relatedTechniques")
        if not isinstance(relationships, list):
            errors.append(f"{location}.relatedTechniques must be an array")
            return
        seen_related: set[str] = set()
        for index, relationship in enumerate(relationships):
            relationship_location = f"{location}.relatedTechniques[{index}]"
            if not isinstance(relationship, dict):
                errors.append(f"{relationship_location}: relationship must be an object")
                continue
            if not {"id", "comparison"}.issubset(relationship):
                errors.append(
                    f"{relationship_location}: relationship must contain id and comparison"
                )
            target_id = relationship.get("id")
            comparison = relationship.get("comparison")
            if not isinstance(target_id, str) or not CONTROL_ID_PATTERN.fullmatch(target_id):
                errors.append(f"{relationship_location}.id: invalid control id '{target_id}'")
            elif target_id == control_id:
                errors.append(f"{relationship_location}.id: control cannot reference itself")
            elif target_id in seen_related:
                errors.append(f"{relationship_location}.id: duplicate related id '{target_id}'")
            else:
                seen_related.add(target_id)
                related_ids.append((control_id, target_id))
            if not isinstance(comparison, str) or not comparison.strip():
                errors.append(f"{relationship_location}.comparison must be a non-empty string")
            elif re.search(r"<[^>]+>", comparison):
                errors.append(f"{relationship_location}.comparison must be plain text, not HTML")

    def validate_actionable(control: Dict[str, Any], location: str) -> None:
        pillars = control.get("pillar")
        phases = control.get("phase")
        guidance = control.get("implementationGuidance")

        if not isinstance(pillars, list) or not pillars:
            errors.append(f"{location}: pillar must be a non-empty array")
        elif not all(isinstance(pillar, str) and pillar.strip() for pillar in pillars):
            errors.append(f"{location}: pillar must contain non-empty strings")
        elif len(pillars) != len({pillar.strip() for pillar in pillars}):
            errors.append(f"{location}: pillar must not contain duplicates")

        if not isinstance(phases, list) or not phases:
            errors.append(f"{location}: phase must be a non-empty array")
        elif not all(isinstance(phase, str) and phase.strip() for phase in phases):
            errors.append(f"{location}: phase must contain non-empty strings")
        elif len(phases) != len({phase.strip() for phase in phases}):
            errors.append(f"{location}: phase must not contain duplicates")

        if "implementationGuidance" in control and not isinstance(guidance, list):
            errors.append(
                f"{location}: implementationGuidance must be an array when present"
            )
        elif isinstance(guidance, list):
            for index, strategy in enumerate(guidance):
                strategy_location = f"{location}.implementationGuidance[{index}]"
                if not isinstance(strategy, dict):
                    errors.append(f"{strategy_location}: strategy must be an object")
                    continue
                required_strategy_keys = (
                    ("implementation", "howTo")
                    if legacy_shape_compatible and "id" not in strategy
                    else ("id", "implementation", "howTo")
                )
                for key in required_strategy_keys:
                    if not isinstance(strategy.get(key), str) or not strategy[key].strip():
                        errors.append(f"{strategy_location}: {key} must be a non-empty string")

                guidance_id = strategy.get("id")
                if isinstance(guidance_id, str) and guidance_id:
                    guidance_match = GUIDANCE_ID_PATTERN.fullmatch(guidance_id)
                    if guidance_match is None:
                        errors.append(f"{strategy_location}: invalid guidance id '{guidance_id}'")
                    elif guidance_match.group("control") != location:
                        errors.append(
                            f"{strategy_location}: guidance id '{guidance_id}' "
                            f"does not belong to control '{location}'"
                        )
                    if guidance_id in guidance_ids:
                        errors.append(f"{strategy_location}: duplicate guidance id '{guidance_id}'")
                    else:
                        guidance_ids.add(guidance_id)

        for tools_key in AUTHORING_TOOL_FIELDS:
            tools = control.get(tools_key)
            if tools is not None and (
                not isinstance(tools, list)
                or not tools
                or not all(isinstance(tool, str) and tool.strip() for tool in tools)
            ):
                errors.append(
                    f"{location}: {tools_key} must be a non-empty array of strings when present"
                )
            elif isinstance(tools, list):
                normalized_tools = [tool.strip() for tool in tools]
                if len(normalized_tools) != len(set(normalized_tools)):
                    errors.append(f"{location}: {tools_key} must not contain duplicates")
                if tools_key == "toolsSourceAvailable":
                    for tool in normalized_tools:
                        if not SOURCE_AVAILABLE_TOOL_PATTERN.fullmatch(tool):
                            errors.append(
                                f"{location}: toolsSourceAvailable entry must name its "
                                f"non-OSI license and end in source-available or open-weight: {tool}"
                            )

        tool_sets = {
            tools_key: {
                tool.strip()
                for tool in control.get(tools_key, [])
                if isinstance(tool, str) and tool.strip()
            }
            for tools_key in AUTHORING_TOOL_FIELDS
            if isinstance(control.get(tools_key), list)
        }
        tool_keys = list(tool_sets)
        for left_index, left_key in enumerate(tool_keys):
            for right_key in tool_keys[left_index + 1:]:
                overlap = sorted(tool_sets[left_key] & tool_sets[right_key])
                if overlap:
                    errors.append(
                        f"{location}: identical tool entries must not appear in both "
                        f"{left_key} and {right_key}: {', '.join(overlap)}"
                    )

    def validate_parent_mapping_union(
        parent: Dict[str, Any],
        children: List[Dict[str, Any]],
        parent_id: str,
    ) -> None:
        """Validate the parent navigation union without external catalog files."""
        parent_by_framework = {
            mapping.get("framework"): mapping.get("items", [])
            for mapping in parent.get("defendsAgainst", [])
            if isinstance(mapping, dict)
        }
        framework_names: List[str] = []
        for mapping in parent.get("defendsAgainst", []):
            if isinstance(mapping, dict):
                framework = mapping.get("framework")
                if isinstance(framework, str) and framework not in framework_names:
                    framework_names.append(framework)
        for child in children:
            for mapping in child.get("defendsAgainst", []):
                if isinstance(mapping, dict):
                    framework = mapping.get("framework")
                    if isinstance(framework, str) and framework not in framework_names:
                        framework_names.append(framework)

        for framework in framework_names:
            parent_items = [
                item.strip()
                for item in parent_by_framework.get(framework, [])
                if isinstance(item, str) and item.strip()
            ]
            child_items: List[str] = []
            for child in children:
                for mapping in child.get("defendsAgainst", []):
                    if isinstance(mapping, dict) and mapping.get("framework") == framework:
                        child_items.extend(
                            item.strip()
                            for item in mapping.get("items", [])
                            if isinstance(item, str) and item.strip()
                        )

            parent_valid = [
                item for item in parent_items
                if not NOT_APPLICABLE_PATTERN.fullmatch(item)
            ]
            child_valid = [
                item for item in child_items
                if not NOT_APPLICABLE_PATTERN.fullmatch(item)
            ]
            if not child_valid:
                if len(parent_items) != 1 or not NOT_APPLICABLE_PATTERN.fullmatch(
                    parent_items[0] if parent_items else ""
                ):
                    errors.append(
                        f"{parent_id}: {framework} parent mapping must be N/A "
                        "because every child is N/A"
                    )
                continue

            if any(NOT_APPLICABLE_PATTERN.fullmatch(item) for item in parent_items):
                errors.append(
                    f"{parent_id}: {framework} parent mapping cannot be N/A "
                    "when a child has a mapping"
                )
                continue

            for child_item in child_valid:
                if not any(
                    child_item == parent_item
                    or child_item.startswith(f"{parent_item} (")
                    for parent_item in parent_valid
                ):
                    errors.append(
                        f"{parent_id}: {framework} parent union is missing "
                        f"child mapping '{child_item}'"
                    )
            for parent_item in parent_valid:
                if not any(
                    child_item == parent_item
                    or child_item.startswith(f"{parent_item} (")
                    for child_item in child_valid
                ):
                    errors.append(
                        f"{parent_id}: {framework} parent union introduces "
                        f"unsupported mapping '{parent_item}'"
                    )

    def validate_control_identity(control: Any, location: str) -> Optional[str]:
        if not isinstance(control, dict):
            errors.append(f"{location}: control must be an object")
            return None
        unknown_tool_fields = sorted(
            key
            for key in control
            if isinstance(key, str)
            and key.startswith("tools")
            and key not in AUTHORING_TOOL_FIELDS
        )
        if unknown_tool_fields:
            errors.append(
                f"{location}: unsupported tool field(s): "
                f"{', '.join(unknown_tool_fields)}; supported fields are "
                f"{', '.join(AUTHORING_TOOL_FIELDS)}"
            )
        control_id = control.get("id")
        if not isinstance(control_id, str) or not CONTROL_ID_PATTERN.fullmatch(control_id):
            errors.append(f"{location}: invalid or missing control id '{control_id}'")
            return None
        if control_id in seen_ids:
            errors.append(f"{location}: duplicate control id '{control_id}'")
        else:
            seen_ids.add(control_id)
        if not isinstance(control.get("name"), str) or not control["name"].strip():
            errors.append(f"{control_id}: name must be a non-empty string")
        if not isinstance(control.get("description"), str) or not control["description"].strip():
            errors.append(f"{control_id}: description must be a non-empty string")
        validate_warning(control.get("warning"), control_id)
        validate_mappings(control.get("defendsAgainst"), control_id)
        validate_scope_boundary(control.get("scopeBoundary"), control_id)
        return control_id

    for technique_index, technique in enumerate(techniques):
        location = f"{file_name}.techniques[{technique_index}]"
        technique_id = validate_control_identity(technique, location)
        if technique_id is None:
            continue

        subtechniques = technique.get("subTechniques")
        if isinstance(subtechniques, list) and subtechniques:
            if len(subtechniques) < 2:
                errors.append(f"{technique_id}: parent techniques must have at least two sub-techniques")
            if not technique.get("defendsAgainst"):
                errors.append(f"{technique_id}: parent technique must define shared defendsAgainst mappings")
            for forbidden_key in (
                "pillar",
                "phase",
                *AUTHORING_TOOL_FIELDS,
                "implementationGuidance",
            ):
                if forbidden_key in technique:
                    errors.append(f"{technique_id}: parent technique must not define {forbidden_key}")

            for sub_index, subtechnique in enumerate(subtechniques):
                sub_location = f"{technique_id}.subTechniques[{sub_index}]"
                sub_id = validate_control_identity(subtechnique, sub_location)
                if sub_id is None:
                    continue
                if not sub_id.startswith(f"{technique_id}."):
                    errors.append(f"{sub_id}: id does not belong to parent {technique_id}")
                validate_actionable(subtechnique, sub_id)
            if not legacy_shape_compatible:
                validate_parent_mapping_union(technique, subtechniques, technique_id)
        else:
            if subtechniques is not None and not isinstance(subtechniques, list):
                errors.append(f"{technique_id}: subTechniques must be an array when present")
            validate_actionable(technique, technique_id)

    return errors


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
        # Current framework releases export a scalar version and reference it
        # from a template literal. Resolve the scalar directly so the generic
        # AST serializer's <Identifier:...> marker never reaches status output.
        source_text = intro_file_path.read_text(encoding="utf-8")
        version_match = re.search(
            r"export\s+const\s+aidefendVersion\s*=\s*(['\"])([^'\"]+)\1",
            source_text,
        )
        if version_match:
            version = version_match.group(2).strip()
            if re.fullmatch(r"\d+\.\d{8}", version):
                logger.info(f"Extracted framework version from exported constant: {version}")
                return version
            logger.warning(f"Ignoring invalid exported framework version: {version}")

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
                        if re.fullmatch(r"\d+\.\d{8}", version):
                            logger.info(f"Extracted framework version: {version}")
                            return version
                        logger.warning(f"Ignoring invalid framework version value: {version}")

        logger.warning("Version field not found in aidefend-intro.js")
        return None

    except FileNotFoundError:
        logger.warning(f"aidefend-intro.js not found at {intro_file_path}")
        return None
    except Exception as e:
        logger.error(f"Failed to extract framework version: {e}")
        return None


def _merge_warnings(*warning_values: Any) -> List[Dict[str, str]]:
    """Normalize and de-duplicate inherited and control-specific warnings."""
    merged: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for value in warning_values:
        if not isinstance(value, dict):
            continue
        level = str(value.get("level", "")).strip()
        description = str(value.get("description", "")).strip()
        if not level and not description:
            continue
        key = (level, description)
        if key in seen:
            continue
        seen.add(key)
        merged.append({"level": level, "description": description})
    return merged


def _warnings_to_search_text(warnings: List[Dict[str, str]]) -> str:
    """Convert warning HTML to searchable plain text without losing its level."""
    parts: List[str] = []
    for warning in warnings:
        level = warning.get("level", "").strip()
        description_html = warning.get("description", "")
        description = BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True)
        combined = ": ".join(part for part in (level, description) if part)
        if combined:
            parts.append(combined)
    return " | ".join(parts)


def _rich_text_to_search_text(value: Any) -> str:
    """Convert an authored rich-text field to stable plain search text."""
    if not isinstance(value, str) or not value:
        return ""
    if "<" not in value:
        return " ".join(value.split())
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _scope_boundary_to_search_text(scope_boundary: Any) -> str:
    """Flatten schema-2.3 scope metadata without changing its meaning."""
    responsibility = _scope_boundary_responsibility_to_search_text(scope_boundary)
    relationships = _scope_boundary_relationships_to_search_text(scope_boundary)
    return " | ".join(part for part in (responsibility, relationships) if part)


def _scope_boundary_responsibility_to_search_text(scope_boundary: Any) -> str:
    """Render the ownership statement that must remain inside the token window."""
    if not isinstance(scope_boundary, dict):
        return ""
    responsibility = scope_boundary.get("responsibility")
    if isinstance(responsibility, str) and responsibility.strip():
        return f"Responsibility: {responsibility.strip()}"
    return ""


def _scope_boundary_relationships_to_search_text(scope_boundary: Any) -> str:
    """Render related-control comparisons without delaying tools in the prefix."""
    if not isinstance(scope_boundary, dict):
        return ""
    parts: List[str] = []
    for relationship in scope_boundary.get("relatedTechniques", []):
        if not isinstance(relationship, dict):
            continue
        related_id = relationship.get("id")
        comparison = relationship.get("comparison")
        if isinstance(related_id, str) and isinstance(comparison, str):
            parts.append(f"Related {related_id}: {comparison.strip()}")
    return " | ".join(part for part in parts if part)


def _tools_to_search_text(
    tools_opensource: List[str],
    tools_source_available: List[str],
    tools_commercial: List[str],
) -> str:
    """Expose all three framework tool-license classes to semantic search."""
    groups = []
    if tools_opensource:
        groups.append("Open source: " + ", ".join(tools_opensource))
    if tools_source_available:
        groups.append("Source available or open weight: " + ", ".join(tools_source_available))
    if tools_commercial:
        groups.append("Commercial: " + ", ".join(tools_commercial))
    return "; ".join(groups)


def _guidance_document_id(control_id: str, strategy: Dict[str, Any], ordinal: int) -> str:
    """Use schema-2.2 canonical IDs, with a legacy fallback for older sources."""
    guidance_id = strategy.get("id")
    if isinstance(guidance_id, str) and guidance_id.strip():
        return guidance_id.strip()
    return f"{control_id}.S{ordinal}"


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
        tech_desc_text = _rich_text_to_search_text(tech_desc)
        tech_warnings = _merge_warnings(technique.get("warning"))
        tech_scope_boundary = technique.get("scopeBoundary") or {}
        has_subtechniques = bool(technique.get("subTechniques"))

        # Extract threat framework mappings
        defends_against = technique.get("defendsAgainst", [])

        # Extract tool lists
        tools_opensource = technique.get("toolsOpenSource", [])
        tools_source_available = technique.get("toolsSourceAvailable", [])
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
        tech_text = f"Technique: {tech_name}\nID: {tech_id}"

        # Keep ownership boundaries near the start of the embedding input. The
        # framework mappings and warnings can be long enough to push this
        # schema-2.3 metadata beyond the embedding model's token window.
        scope_text = _scope_boundary_responsibility_to_search_text(
            tech_scope_boundary
        )
        scope_relationships_text = _scope_boundary_relationships_to_search_text(
            tech_scope_boundary
        )
        if scope_text:
            tech_text += f"\nScope Boundary: {scope_text}"

        tools_text = _tools_to_search_text(
            tools_opensource,
            tools_source_available,
            tools_commercial,
        )
        if tools_text:
            tech_text += f"\nTools: {tools_text}"

        tech_text += f"\nDescription: {tech_desc_text}"

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

        warning_text = _warnings_to_search_text(tech_warnings)
        if warning_text:
            tech_text += f"\nWarnings: {warning_text}"
        if scope_relationships_text:
            tech_text += f"\nScope Relationships: {scope_relationships_text}"

        documents.append({
            "text": tech_text,
            "source_id": tech_id,
            "tactic": tactic_name,
            "type": "technique",
            "name": tech_name,
            "pillar": technique.get("pillar", []),
            "phase": technique.get("phase", []),
            "defends_against": defends_against,
            "tools_opensource": tools_opensource,
            "tools_source_available": tools_source_available,
            "tools_commercial": tools_commercial,
            "parent_technique_id": "",
            "implementation_guidance": tech_implementation_strategies,  # Extract from technique
            "guidance_id": "",
            "scope_boundary": tech_scope_boundary,
            "is_actionable": not has_subtechniques,
            "is_parent_family": has_subtechniques,
            "has_code_snippets": tech_has_code,  # Check technique's strategies for code
            "warnings": tech_warnings,
        })

        # Documents for sub-techniques
        for sub_tech in technique.get("subTechniques", []):
            sub_id = sub_tech.get("id", "Unknown")
            sub_name = sub_tech.get("name", "Unknown")
            sub_desc = sub_tech.get("description", "")
            sub_desc_text = _rich_text_to_search_text(sub_desc)
            sub_pillar = sub_tech.get("pillar", "")
            sub_phase = sub_tech.get("phase", "")
            # Parent mappings are a navigation-only child union in framework
            # schema 1.7. They must never be promoted into an actionable child
            # claim. The fallback only keeps pre-schema sources readable.
            sub_defends_against = sub_tech.get("defendsAgainst") or defends_against
            sub_tools_opensource = sub_tech.get("toolsOpenSource", [])
            sub_tools_source_available = sub_tech.get("toolsSourceAvailable", [])
            sub_tools_commercial = sub_tech.get("toolsCommercial", [])
            sub_scope_boundary = sub_tech.get("scopeBoundary") or {}
            sub_warnings = _merge_warnings(
                technique.get("warning"),
                sub_tech.get("warning"),
            )

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
                f"ID: {sub_id}"
            )

            scope_text = _scope_boundary_responsibility_to_search_text(
                sub_scope_boundary
            )
            scope_relationships_text = _scope_boundary_relationships_to_search_text(
                sub_scope_boundary
            )
            if scope_text:
                sub_text += f"\nScope Boundary: {scope_text}"

            tools_text = _tools_to_search_text(
                sub_tools_opensource,
                sub_tools_source_available,
                sub_tools_commercial,
            )
            if tools_text:
                sub_text += f"\nTools: {tools_text}"

            sub_text += (
                f"\nParent: {tech_name}\n"
                f"Pillar: {sub_pillar}\n"
                f"Phase: {sub_phase}\n"
                f"Description: {sub_desc_text}"
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

            warning_text = _warnings_to_search_text(sub_warnings)
            if warning_text:
                sub_text += f"\nWarnings: {warning_text}"
            if scope_relationships_text:
                sub_text += f"\nScope Relationships: {scope_relationships_text}"

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
                "tools_source_available": sub_tools_source_available,
                "tools_commercial": sub_tools_commercial,
                "parent_technique_id": tech_id,
                "implementation_guidance": implementation_guidance,
                "guidance_id": "",
                "scope_boundary": sub_scope_boundary,
                "is_actionable": True,
                "is_parent_family": False,
                "has_code_snippets": has_code,
                "warnings": sub_warnings,
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

                strategy_id = _guidance_document_id(sub_id, strategy, i)
                strategy_text = (
                    f"Implementation Guidance: {strategy_name}\n"
                    f"ID: {strategy_id}"
                )

                scope_text = _scope_boundary_responsibility_to_search_text(
                    sub_scope_boundary
                )
                scope_relationships_text = _scope_boundary_relationships_to_search_text(
                    sub_scope_boundary
                )
                if scope_text:
                    strategy_text += f"\nScope Boundary: {scope_text}"

                strategy_tools_text = _tools_to_search_text(
                    sub_tools_opensource,
                    sub_tools_source_available,
                    sub_tools_commercial,
                )
                if strategy_tools_text:
                    strategy_text += f"\nTools: {strategy_tools_text}"

                strategy_text += (
                    f"\nTactic: {tactic_name}. Technique: {tech_name}. "
                    f"Sub-Technique: {sub_name}"
                )

                strategy_text += f"\nHow-To: {clean_how_to}"

                if sub_defends_against:
                    frameworks_text = []
                    for fw in sub_defends_against:
                        fw_name = fw.get("framework", "")
                        items = fw.get("items", [])
                        if items:
                            frameworks_text.append(f"{fw_name}: {', '.join(items)}")
                    if frameworks_text:
                        strategy_text += "\nDefends Against: " + "; ".join(frameworks_text)

                warning_text = _warnings_to_search_text(sub_warnings)
                if warning_text:
                    strategy_text += f"\nWarnings: {warning_text}"
                if scope_relationships_text:
                    strategy_text += (
                        f"\nScope Relationships: {scope_relationships_text}"
                    )

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
                    "tools_source_available": sub_tools_source_available,
                    "tools_commercial": sub_tools_commercial,
                    "parent_technique_id": sub_id,
                    "implementation_guidance": [strategy],
                    "guidance_id": strategy_id,
                    "scope_boundary": sub_scope_boundary,
                    "is_actionable": False,
                    "is_parent_family": False,
                    "has_code_snippets": has_code,
                    "warnings": sub_warnings,
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
                strategy_id = _guidance_document_id(tech_id, strategy, i)
                strategy_text = (
                    f"Implementation Guidance: {strategy_name}\n"
                    f"ID: {strategy_id}"
                )

                scope_text = _scope_boundary_responsibility_to_search_text(
                    tech_scope_boundary
                )
                scope_relationships_text = _scope_boundary_relationships_to_search_text(
                    tech_scope_boundary
                )
                if scope_text:
                    strategy_text += f"\nScope Boundary: {scope_text}"

                strategy_tools_text = _tools_to_search_text(
                    tools_opensource,
                    tools_source_available,
                    tools_commercial,
                )
                if strategy_tools_text:
                    strategy_text += f"\nTools: {strategy_tools_text}"

                strategy_text += f"\nTactic: {tactic_name}. Technique: {tech_name}"

                strategy_text += f"\nHow-To: {clean_how_to}"

                if defends_against:
                    frameworks_text = []
                    for fw in defends_against:
                        fw_name = fw.get("framework", "")
                        items = fw.get("items", [])
                        if items:
                            frameworks_text.append(f"{fw_name}: {', '.join(items)}")
                    if frameworks_text:
                        strategy_text += "\nDefends Against: " + "; ".join(frameworks_text)

                warning_text = _warnings_to_search_text(tech_warnings)
                if warning_text:
                    strategy_text += f"\nWarnings: {warning_text}"
                if scope_relationships_text:
                    strategy_text += (
                        f"\nScope Relationships: {scope_relationships_text}"
                    )

                documents.append({
                    "text": strategy_text,
                    "source_id": strategy_id,
                    "tactic": tactic_name,
                    "type": "strategy",
                    "name": f"{tech_name} - {strategy_name}",
                    "pillar": technique.get("pillar", []),
                    "phase": technique.get("phase", []),
                    "defends_against": defends_against,
                    "tools_opensource": tools_opensource,
                    "tools_source_available": tools_source_available,
                    "tools_commercial": tools_commercial,
                    "parent_technique_id": tech_id,
                    "implementation_guidance": [strategy],
                    "guidance_id": strategy_id,
                    "scope_boundary": tech_scope_boundary,
                    "is_actionable": False,
                    "is_parent_family": False,
                    "has_code_snippets": has_code,
                    "warnings": tech_warnings,
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


def _unique_table_artifact(stem: str) -> Path:
    """Return a non-existing Lance table path inside the configured DB root."""
    candidate = settings.DB_PATH / f"{stem}.lance"
    if not candidate.exists():
        return candidate
    while True:
        candidate = settings.DB_PATH / f"{stem}_{time.time_ns()}.lance"
        if not candidate.exists():
            return candidate


def _existing_backup_artifacts() -> List[Path]:
    """List retained rollback generations, newest first."""
    candidates = list(settings.DB_PATH.glob("aidefend_backup*.lance"))
    return sorted(
        candidates,
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )


async def _activate_staged_database(new_sync_path: Path) -> None:
    """Activate a staged table and preserve every usable rollback generation.

    A process can stop at any filesystem rename or between active-table
    initialization and the durable version write. Existing backups are never
    assumed stale here: the immediately previous active table is saved under a
    new path, and rollback tries each retained generation until one initializes.
    Successful core_sync() removes the artifacts only after version metadata is
    durably written.
    """
    aidefend_path = settings.DB_PATH / "aidefend.lance"
    backup_candidates = _existing_backup_artifacts()
    had_recovery_source = aidefend_path.exists() or bool(backup_candidates)
    current_backup_path: Optional[Path] = None
    activated_new = False

    if not new_sync_path.exists():
        raise RuntimeError(f"Staged database table is missing: {new_sync_path}")

    from app.core import query_engine
    async with query_engine.database_write_guard() as guarded_engine:
        guarded_engine._reset_database_handles_locked()
        logger.info("Query engine paused for database swap")

        try:
            # Recover the newest retained generation if a prior process stopped
            # after moving the active table away. Older generations stay in
            # place as fallbacks until this sync is durably committed.
            if not aidefend_path.exists() and backup_candidates:
                recovered_path = backup_candidates.pop(0)
                await asyncio.to_thread(recovered_path.rename, aidefend_path)
                logger.warning(
                    "Recovered an aidefend rollback generation from an "
                    "interrupted prior swap"
                )

            if aidefend_path.exists():
                current_backup_path = _unique_table_artifact("aidefend_backup")
                await asyncio.to_thread(
                    aidefend_path.rename,
                    current_backup_path,
                )
                logger.info(
                    f"Retained previous active table as {current_backup_path.name}"
                )

            await asyncio.to_thread(new_sync_path.rename, aidefend_path)
            activated_new = True
            logger.info("Atomic swap complete: aidefend_new_sync -> aidefend")

            if not await guarded_engine._do_initialize():
                raise RuntimeError("QueryEngine rejected the newly swapped database")

        except BaseException as swap_error:
            logger.error(
                f"Database swap failed: {swap_error}. Attempting rollback..."
            )
            guarded_engine._reset_database_handles_locked()
            rollback_error: Optional[BaseException] = None
            try:
                restored = False

                async def quarantine_active() -> None:
                    if aidefend_path.exists():
                        failed_path = _unique_table_artifact(
                            "aidefend_failed_sync"
                        )
                        await asyncio.to_thread(
                            aidefend_path.rename,
                            failed_path,
                        )

                if activated_new:
                    await quarantine_active()
                elif aidefend_path.exists():
                    # If active->backup itself failed, this can still be the
                    # untouched original table. Try it before any fallback.
                    restored = await guarded_engine._do_initialize()
                    if not restored:
                        guarded_engine._reset_database_handles_locked()
                        await quarantine_active()

                ordered_candidates = []
                if current_backup_path is not None:
                    ordered_candidates.append(current_backup_path)
                ordered_candidates.extend(backup_candidates)

                seen_paths = set()
                for candidate in ordered_candidates:
                    resolved = str(candidate.resolve(strict=False))
                    if resolved in seen_paths or not candidate.exists():
                        continue
                    seen_paths.add(resolved)
                    if aidefend_path.exists():
                        await quarantine_active()
                    await asyncio.to_thread(candidate.rename, aidefend_path)
                    restored = await guarded_engine._do_initialize()
                    if restored:
                        logger.info(
                            f"Rollback successful using {candidate.name}"
                        )
                        break
                    guarded_engine._reset_database_handles_locked()
                    await quarantine_active()

                if had_recovery_source and not restored:
                    raise RuntimeError(
                        "no retained database generation could be initialized"
                    )
            except BaseException as exc:
                rollback_error = exc
                logger.error(
                    f"Rollback also failed: {exc}. Manual intervention required.",
                    exc_info=True,
                )

            if rollback_error is not None:
                if isinstance(swap_error, asyncio.CancelledError):
                    raise swap_error from rollback_error
                raise RuntimeError(
                    f"Database swap failed ({swap_error}); rollback also "
                    f"failed ({rollback_error})"
                ) from rollback_error
            raise


async def _rollback_active_database_after_metadata_failure() -> bool:
    """Remove an uncommitted active table and restore the newest LKG table."""
    active_path = settings.DB_PATH / "aidefend.lance"

    from app.core import query_engine
    async with query_engine.database_write_guard() as guarded_engine:
        guarded_engine._reset_database_handles_locked()

        if active_path.exists():
            failed_path = _unique_table_artifact("aidefend_failed_metadata")
            await asyncio.to_thread(active_path.rename, failed_path)

        try:
            backup_candidates = _existing_backup_artifacts()
        except Exception as exc:
            logger.error(
                "Could not enumerate last-known-good database generations after "
                f"version metadata failure: {exc}"
            )
            backup_candidates = []

        for candidate in backup_candidates:
            if not candidate.exists():
                continue
            try:
                await asyncio.to_thread(candidate.rename, active_path)
                if await guarded_engine._do_initialize():
                    logger.warning(
                        "Restored last-known-good database after version metadata failure"
                    )
                    return True
            except Exception as exc:
                logger.error(
                    f"Could not restore rollback candidate {candidate.name}: {exc}"
                )

            guarded_engine._reset_database_handles_locked()
            if active_path.exists():
                failed_path = _unique_table_artifact("aidefend_failed_metadata")
                await asyncio.to_thread(active_path.rename, failed_path)

    logger.error("No usable last-known-good database was available for rollback")
    return False


def _validate_scope_boundary_token_visibility(
    documents: List[Dict[str, Any]],
    model: TextEmbedding,
) -> int:
    """Audit searchable scope visibility while preserving exact stored metadata."""
    embedding_model = getattr(model, "model", None)
    tokenizer = getattr(embedding_model, "tokenizer", None)
    truncation = getattr(tokenizer, "truncation", None)
    max_length = truncation.get("max_length") if isinstance(truncation, dict) else None
    if (
        tokenizer is None
        or not isinstance(max_length, int)
        or max_length < 1
        or not hasattr(tokenizer, "to_str")
        or not hasattr(type(tokenizer), "from_str")
    ):
        logger.warning(
            "Embedding tokenizer does not expose a verifiable context-length "
            "contract; scopeBoundary remains available as exact index metadata"
        )
        return 0

    audit_tokenizer = type(tokenizer).from_str(tokenizer.to_str())
    audit_tokenizer.no_truncation()
    audit_tokenizer.no_padding()

    prefixes: List[str] = []
    source_ids: List[str] = []
    for document in documents:
        boundary = document.get("scope_boundary")
        if not isinstance(boundary, dict):
            continue
        responsibility = boundary.get("responsibility")
        if not isinstance(responsibility, str) or not responsibility.strip():
            continue
        text = document.get("text")
        if not isinstance(text, str):
            raise ValueError(
                f"{document.get('source_id', 'Unknown')}: searchable text is missing"
            )
        marker_offset = text.find("\nScope Boundary:")
        responsibility_offset = text.find(responsibility, marker_offset)
        if marker_offset < 0 or responsibility_offset < marker_offset:
            raise ValueError(
                f"{document.get('source_id', 'Unknown')}: scopeBoundary responsibility "
                "is absent from searchable text"
            )
        prefixes.append(text[: responsibility_offset + len(responsibility)])
        source_ids.append(str(document.get("source_id") or "Unknown"))

    if not prefixes:
        return 0

    encoded = audit_tokenizer.encode_batch(prefixes)
    token_counts = [len(item.ids) for item in encoded]
    violations = [
        f"{source_id} ({token_count} tokens)"
        for source_id, token_count in zip(source_ids, token_counts)
        if token_count > max_length
    ]
    if violations:
        preview = ", ".join(violations[:10])
        logger.warning(
            "scopeBoundary responsibility falls outside the embedding context "
            "(%s tokens): %s. Exact scopeBoundary metadata will still be indexed.",
            max_length,
            preview,
        )

    maximum = max(token_counts)
    logger.info(
        "scopeBoundary embedding visibility verified: %s documents, max %s/%s tokens",
        len(token_counts),
        maximum,
        max_length,
    )
    return maximum


def _validate_tool_token_visibility(
    documents: List[Dict[str, Any]],
    model: TextEmbedding,
) -> int:
    """Audit searchable tool visibility while preserving exact stored metadata."""
    embedding_model = getattr(model, "model", None)
    tokenizer = getattr(embedding_model, "tokenizer", None)
    truncation = getattr(tokenizer, "truncation", None)
    max_length = truncation.get("max_length") if isinstance(truncation, dict) else None
    if (
        tokenizer is None
        or not isinstance(max_length, int)
        or max_length < 1
        or not hasattr(tokenizer, "to_str")
        or not hasattr(type(tokenizer), "from_str")
    ):
        logger.warning(
            "Embedding tokenizer does not expose a verifiable context-length "
            "contract; tool inventories remain available as exact index metadata"
        )
        return 0

    audit_tokenizer = type(tokenizer).from_str(tokenizer.to_str())
    audit_tokenizer.no_truncation()
    audit_tokenizer.no_padding()

    prefixes: List[str] = []
    source_ids: List[str] = []
    for document in documents:
        tool_values = [
            parse_json_list(document.get(field, []))
            for field in (
                "tools_opensource",
                "tools_source_available",
                "tools_commercial",
            )
        ]
        tools_text = _tools_to_search_text(*tool_values)
        if not tools_text:
            continue
        text = document.get("text")
        if not isinstance(text, str):
            raise ValueError(
                f"{document.get('source_id', 'Unknown')}: searchable text is missing"
            )
        marker = f"\nTools: {tools_text}"
        marker_offset = text.find(marker)
        if marker_offset < 0:
            raise ValueError(
                f"{document.get('source_id', 'Unknown')}: exact tool inventory "
                "is absent from searchable text"
            )
        prefixes.append(text[: marker_offset + len(marker)])
        source_ids.append(str(document.get("source_id") or "Unknown"))

    if not prefixes:
        return 0

    encoded = audit_tokenizer.encode_batch(prefixes)
    token_counts = [len(item.ids) for item in encoded]
    violations = [
        f"{source_id} ({token_count} tokens)"
        for source_id, token_count in zip(source_ids, token_counts)
        if token_count > max_length
    ]
    if violations:
        preview = ", ".join(violations[:10])
        logger.warning(
            "exact tool inventory falls outside the embedding context "
            "(%s tokens): %s. Exact tool metadata will still be indexed.",
            max_length,
            preview,
        )

    maximum = max(token_counts)
    logger.info(
        "Tool inventory embedding visibility verified: %s documents, max %s/%s tokens",
        len(token_counts),
        maximum,
        max_length,
    )
    return maximum


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
            model_cache_dir = str(settings.MODEL_CACHE_DIR) if settings.MODEL_CACHE_DIR else None
            model = await asyncio.wait_for(
                asyncio.to_thread(
                    TextEmbedding,
                    model_name=settings.EMBEDDING_MODEL,
                    cache_dir=model_cache_dir,
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

        _validate_scope_boundary_token_visibility(documents, model)
        _validate_tool_token_visibility(documents, model)

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
                # Update every 10 items for responsive progress without noisy logs.
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
                "pillar": json.dumps(parse_json_list(doc.get("pillar", []))),
                "phase": json.dumps(parse_json_list(doc.get("phase", []))),
                # New fields for enhanced functionality
                "defends_against": json.dumps(
                    parse_json_list(doc.get("defends_against", []))
                ),
                "tools_opensource": json.dumps(
                    parse_json_list(doc.get("tools_opensource", []))
                ),
                "tools_source_available": json.dumps(
                    parse_json_list(doc.get("tools_source_available", []))
                ),
                "tools_commercial": json.dumps(
                    parse_json_list(doc.get("tools_commercial", []))
                ),
                "parent_technique_id": doc.get("parent_technique_id", ""),
                "implementation_guidance": json.dumps(
                    parse_json_list(doc.get("implementation_guidance", []))
                ),
                "guidance_id": doc.get("guidance_id", ""),
                "scope_boundary": json.dumps(doc.get("scope_boundary", {})),
                "is_actionable": bool(doc.get("is_actionable", False)),
                "is_parent_family": bool(doc.get("is_parent_family", False)),
                "has_code_snippets": doc.get("has_code_snippets", False),
                "warnings": json.dumps(
                    parse_json_list(doc.get("warnings", []))
                ),
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

        # Declare every field explicitly. Schema inference can silently choose
        # a null/incorrect type when an additive framework field is empty in a
        # particular release.
        record_schema = pa.schema([
            pa.field("vector", pa.list_(pa.float32(), settings.EMBEDDING_DIMENSION)),
            pa.field("text", pa.string()),
            pa.field("source_id", pa.string()),
            pa.field("tactic", pa.string()),
            pa.field("type", pa.string()),
            pa.field("name", pa.string()),
            pa.field("pillar", pa.string()),
            pa.field("phase", pa.string()),
            pa.field("defends_against", pa.string()),
            pa.field("tools_opensource", pa.string()),
            pa.field("tools_source_available", pa.string()),
            pa.field("tools_commercial", pa.string()),
            pa.field("parent_technique_id", pa.string()),
            pa.field("implementation_guidance", pa.string()),
            pa.field("guidance_id", pa.string()),
            pa.field("scope_boundary", pa.string()),
            pa.field("is_actionable", pa.bool_()),
            pa.field("is_parent_family", pa.bool_()),
            pa.field("has_code_snippets", pa.bool_()),
            pa.field("warnings", pa.string()),
        ])
        logger.info(f"💾 Writing {len(records)} records to database ('{temp_table_name}' table)...")

        await asyncio.to_thread(
            db.create_table,
            temp_table_name,
            data=records,
            schema=record_schema,
        )

        logger.info(f"✅ Database write complete: {len(records)} records written")

        # Verify new table was created successfully
        table_names = await asyncio.to_thread(db.table_names)
        if temp_table_name not in table_names:
            raise Exception(f"Failed to create {temp_table_name} table")

        logger.info(f"Successfully created {temp_table_name} table. Performing atomic swap...")

        new_sync_path = settings.DB_PATH / f"{temp_table_name}.lance"

        # Release the builder connection before moving Lance directories. The
        # active QueryEngine handles are released under its writer guard below.
        try:
            del db
        except Exception:
            logger.debug("Could not release staging LanceDB handle", exc_info=True)

        # Hold QueryEngine's exclusive writer lock inside the transaction helper
        # so reads cannot observe renamed, absent, or half-reloaded table paths.
        await _activate_staged_database(new_sync_path)

        logger.info("Query engine reloaded successfully")

        logger.info("Zero-downtime sync complete!")

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


async def _cleanup_successful_sync_artifacts() -> bool:
    """Remove rollback/staging tables only after a successful committed sync."""
    artifact_paths = {
        settings.DB_PATH / "aidefend_new_sync.lance",
        *settings.DB_PATH.glob("aidefend_backup*.lance"),
        *settings.DB_PATH.glob("aidefend_failed_sync*.lance"),
        *settings.DB_PATH.glob("aidefend_failed_metadata*.lance"),
    }
    failures = []
    for artifact_path in sorted(artifact_paths, key=lambda path: path.name):
        artifact_name = artifact_path.name
        if not artifact_path.exists():
            continue
        try:
            await asyncio.to_thread(shutil.rmtree, artifact_path)
            logger.info(f"Removed successful-sync artifact: {artifact_name}")
        except Exception as exc:
            failures.append(f"{artifact_name}: {exc}")
            logger.error(
                f"Could not remove successful-sync artifact {artifact_name}: {exc}",
                exc_info=True,
            )
    if failures:
        _set_last_sync_error(
            "The new index is active, but sync artifact cleanup failed: "
            + "; ".join(failures)
        )
        return False
    return True


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

        # Resolve the tactic set from main.js at the same immutable revision
        # before deciding whether this sync is a no-op. This keeps renamed,
        # added, removed, and reordered tactics dynamic for both source modes.
        manifest_path = await download_manifest_file(latest_sha)
        if manifest_path is None:
            error_msg = (
                "Could not stage the AIDEFEND framework main.js manifest. "
                "The existing database and version marker were left unchanged."
            )
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False
        try:
            tactic_files = await asyncio.to_thread(
                parse_staged_tactic_manifest,
                manifest_path,
            )
            source_files = _framework_source_files(tactic_files)
        except Exception as manifest_error:
            error_msg = (
                "Framework main.js manifest validation failed; sync aborted and "
                f"the last-known-good index was retained: {manifest_error}"
            )
            logger.error(error_msg, exc_info=True)
            _set_last_sync_error(error_msg)
            return False

        # Schema documentation is provenance metadata, not indexed content. Read
        # it from the same local root or immutable GitHub SHA before the no-op
        # decision, but never block a compatible content sync when it is absent
        # or its documentation format changes.
        schema_metadata_path = await download_schema_metadata_file(latest_sha)
        (
            discovered_authoring_schema_version,
            discovered_public_schema_version,
        ) = await asyncio.to_thread(
            extract_framework_schema_versions,
            schema_metadata_path,
            base_dir=settings.RAW_PATH,
        )
        discovered_schema_metadata_sha256 = await asyncio.to_thread(
            compute_framework_schema_metadata_sha256,
            schema_metadata_path,
            base_dir=settings.RAW_PATH,
        )
        schema_metadata_available = (
            schema_metadata_path is not None
            and discovered_schema_metadata_sha256 is not None
        )

        # Rebuild not only when framework content changes, but also when the
        # MCP extraction/index contract or embedding configuration changes.
        local_sha = get_local_commit_sha()
        version_info = load_version_info() or {}
        expected_source_kind = "local" if _using_local_framework_source() else "github"
        (
            framework_authoring_schema_version,
            framework_public_schema_version,
        ) = resolve_effective_framework_schema_versions(
            (
                discovered_authoring_schema_version,
                discovered_public_schema_version,
            ),
            version_info=version_info,
            current_source_revision=latest_sha,
            source_kind=expected_source_kind,
            metadata_available=schema_metadata_available,
        )
        framework_schema_metadata_sha256 = (
            resolve_effective_framework_schema_metadata_sha256(
                discovered_schema_metadata_sha256,
                version_info=version_info,
                current_source_revision=latest_sha,
                source_kind=expected_source_kind,
                metadata_available=schema_metadata_available,
            )
        )
        logger.info(
            "Framework schema versions: authoring=%s, public=%s, metadata_sha256=%s",
            framework_authoring_schema_version,
            framework_public_schema_version,
            framework_schema_metadata_sha256 or "unavailable",
        )
        rebuild_reasons: List[str] = []
        if not (settings.DB_PATH / "aidefend.lance").is_dir():
            rebuild_reasons.append("active database table missing")
        if (
            version_info.get("framework_authoring_schema_version")
            != framework_authoring_schema_version
        ):
            rebuild_reasons.append(
                "framework authoring schema version "
                f"{version_info.get('framework_authoring_schema_version', 'missing')} -> "
                f"{framework_authoring_schema_version}"
            )
        if (
            version_info.get("framework_public_schema_version")
            != framework_public_schema_version
        ):
            rebuild_reasons.append(
                "framework public schema version "
                f"{version_info.get('framework_public_schema_version', 'missing')} -> "
                f"{framework_public_schema_version}"
            )
        if (
            version_info.get("framework_schema_metadata_sha256")
            != framework_schema_metadata_sha256
        ):
            rebuild_reasons.append("framework schema metadata digest changed or missing")
        if version_info.get("index_schema_version") != settings.CACHE_SCHEMA_VERSION:
            rebuild_reasons.append(
                "index schema "
                f"{version_info.get('index_schema_version', 'missing')} -> {settings.CACHE_SCHEMA_VERSION}"
            )
        if version_info.get("embedding_model") != settings.EMBEDDING_MODEL:
            rebuild_reasons.append("embedding model changed")
        if version_info.get("embedding_dimension") != settings.EMBEDDING_DIMENSION:
            rebuild_reasons.append("embedding dimension changed")
        expected_revision_kind = (
            "local_content_sha1" if _using_local_framework_source() else "git_commit_sha"
        )
        expected_source_repository = (
            "local-working-tree"
            if _using_local_framework_source()
            else settings.github_repo_path
        )
        expected_source_ref = (
            "working-tree"
            if _using_local_framework_source()
            else settings.GITHUB_BRANCH
        )
        if version_info.get("source_kind") != expected_source_kind:
            rebuild_reasons.append("source kind changed or missing")
        if version_info.get("source_revision_kind") != expected_revision_kind:
            rebuild_reasons.append("source revision kind changed or missing")
        if version_info.get("source_repository") != expected_source_repository:
            rebuild_reasons.append("source repository changed or missing")
        if version_info.get("source_ref") != expected_source_ref:
            rebuild_reasons.append("source ref changed or missing")
        if not version_info.get("source_content_sha256"):
            rebuild_reasons.append("source content digest missing")
        if version_info.get("source_files") != source_files:
            rebuild_reasons.append("framework source file manifest changed or missing")

        if local_sha == latest_sha and rebuild_reasons and not force_rebuild:
            logger.info(
                "Rebuilding unchanged framework source because MCP index metadata changed: "
                + "; ".join(rebuild_reasons)
            )
            force_rebuild = True

        if local_sha == latest_sha and not force_rebuild:
            logger.info(f"Already up-to-date (commit: {local_sha[:8]})")

            # A process interruption after a prior successful version write can
            # leave a backup/staging table behind. A no-op sync repairs that
            # residue before reporting a clean current state.
            if not await _cleanup_successful_sync_artifacts():
                return False

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
            logger.info(f"📥 Staging {len(source_files)} files from local framework...")
        else:
            logger.info(f"📥 Downloading {len(source_files)} files in parallel...")

        download_tasks = []
        for filename in source_files:
            if filename == FRAMEWORK_INTRO_FILENAME:
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
            filename = source_files[i]

            if isinstance(result, Exception):
                # Download task raised an exception
                logger.error(f"Failed to download {filename}: {result}")
                failed_required.append(filename)
            elif result is None:
                # Download failed (function returned None)
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

        # Check the exact required file set, including release metadata.
        required_files = set(source_files)
        downloaded_names = {path.name for path in downloaded_files}
        missing_required_files = sorted(required_files - downloaded_names)
        if missing_required_files:
            error_msg = (
                "Required tactic files are missing from the staged framework source\n\n"
                "Missing files:\n" +
                "\n".join(f"  - {filename}" for filename in missing_required_files) + "\n\n"
                f"This usually indicates network issues or incomplete downloads.\n\n"
                "Check the download errors in the logs above for specific failure reasons."
            )
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False

        logger.info(f"✅ Downloaded {len(downloaded_files)}/{len(source_files)} files")

        try:
            source_content_sha256 = _compute_staged_framework_digest(
                downloaded_files,
                algorithm="sha256",
                source_files=source_files,
            )
            if _using_local_framework_source():
                staged_local_signature = _compute_staged_framework_digest(
                    downloaded_files,
                    algorithm="sha1",
                    source_files=source_files,
                )
                if staged_local_signature != latest_sha:
                    error_msg = (
                        "Local framework changed while it was being staged; "
                        "sync aborted to avoid a mixed source snapshot. Retry once "
                        "the framework working tree is stable."
                    )
                    logger.error(error_msg)
                    _set_last_sync_error(error_msg)
                    return False
        except Exception as digest_error:
            error_msg = f"Failed to compute staged framework content digest: {digest_error}"
            logger.error(error_msg, exc_info=True)
            _set_last_sync_error(error_msg)
            return False

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
                logger.error(f"Failed to extract framework version: {e}")

        if not framework_version:
            # Non-fatal: a fresh customer must still get a usable knowledge base even if the
            # upstream aidefend-intro.js version string is missing or its format drifts (e.g.
            # a switch away from <major>.YYYYMMDD). Record "unknown" and continue indexing;
            # framework_version is only stored as version metadata (see below), never parsed.
            logger.warning(
                "aidefend-intro.js did not yield a valid framework version in the expected "
                "<major>.YYYYMMDD format; proceeding with 'unknown' so indexing still completes."
            )
            framework_version = "unknown"

        legacy_contract = uses_legacy_framework_contract(
            source_kind=expected_source_kind,
            source_repository=expected_source_repository,
            source_revision=latest_sha,
            source_content_sha256=source_content_sha256,
            framework_version=framework_version,
            schema_metadata_available=schema_metadata_available,
            framework_authoring_schema_version=framework_authoring_schema_version,
            framework_public_schema_version=framework_public_schema_version,
        )
        if legacy_contract:
            logger.warning(
                "Applying the narrowly scoped AIDEFEND %s legacy source contract: "
                "guidance IDs use deterministic index fallbacks and historical "
                "parent threat unions are accepted",
                framework_version,
            )

        # Parse and validate every required tactic before building a new index.
        # A partial knowledge base is unsafe, so any required-file failure is fatal.
        logger.info(f"📄 Parsing {len(downloaded_files)} files...")

        all_documents = []
        failed_files = []
        seen_control_ids: set[str] = set()
        seen_guidance_ids: set[str] = set()
        scope_references: List[Tuple[str, str]] = []
        total_files = len(tactic_files)
        parsed_count = 0

        for file_path in downloaded_files:
            # Skip aidefend-intro.js - it's for metadata only, not for embedding
            if file_path.name == FRAMEWORK_INTRO_FILENAME:
                logger.info(f"Skipping {file_path.name} (metadata only)")
                continue

            parsed_count += 1

            try:
                # Use asyncio.to_thread to avoid blocking the event loop
                # (parse_tactic_file involves file I/O and CPU-intensive regex operations)
                tactic_data = await asyncio.to_thread(parse_tactic_file, file_path)

                if tactic_data:
                    contract_errors = validate_tactic_contract(
                        tactic_data,
                        file_path.name,
                        seen_control_ids,
                        seen_guidance_ids,
                        scope_references,
                        legacy_contract=legacy_contract,
                    )
                    if contract_errors:
                        preview = "\n".join(f"  - {error}" for error in contract_errors[:20])
                        remaining = len(contract_errors) - 20
                        if remaining > 0:
                            preview += f"\n  ... and {remaining} more"
                        raise ValueError(
                            f"Framework source contract validation failed for {file_path.name}:\n{preview}"
                        )

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
                    "- Node.js v18+ is not installed or not in PATH\n"
                    "- Bundled parser files are missing or damaged "
                    "(parse_js_module.mjs or vendor/acorn.mjs)\n"
                    "- Invalid JavaScript syntax in source file\n"
                    "- Corrupted download\n\n"
                    "Check the bundled parser: node --check parse_js_module.mjs "
                    "and node --check vendor/acorn.mjs"
                )
                logger.error(error_msg, exc_info=True)
                _set_last_sync_error(error_msg)  # Record last error
                failed_files.append(file_path.name)

        logger.info(f"✅ Parsing complete: {len(all_documents)} documents extracted from {parsed_count} files")

        missing_scope_targets = sorted({
            (owner_id, target_id)
            for owner_id, target_id in scope_references
            if target_id not in seen_control_ids
        })
        if missing_scope_targets:
            preview = "\n".join(
                f"  - {owner_id} references missing {target_id}"
                for owner_id, target_id in missing_scope_targets[:20]
            )
            logger.error(f"Framework scopeBoundary references are invalid:\n{preview}")
            failed_files.append("scopeBoundary cross-reference validation")

        # Fail closed if any required tactic failed. Keep the previous database
        # and previous source SHA so the next sync retries the same release.
        if failed_files:
            error_msg = (
                f"Sync aborted - {len(failed_files)} required tactic file(s) failed validation or parsing\n\n"
                f"Failed files:\n" +
                "\n".join([f"  - {f}" for f in failed_files]) + "\n\n"
                "The existing database and version marker were left unchanged. Common causes:\n"
                "- Node.js not installed (check: node --version)\n"
                "- Bundled parser/runtime missing or damaged\n"
                "- Invalid or incomplete framework source\n"
                "- Parser script (parse_js_module.mjs) missing or broken\n\n"
                "Troubleshooting steps:\n"
                "1. Verify Node.js installed: node --version (need v18+)\n"
                "2. Check parser syntax: node --check parse_js_module.mjs\n"
                "3. Check bundled runtime: node --check vendor/acorn.mjs\n"
                "4. Try manual parse: node parse_js_module.mjs <file.js>"
            )
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False

        if not all_documents:
            error_msg = "Sync aborted - no documents were extracted from the required tactic files"
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False

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

        # embed_and_index performs the physical swap and initialization under
        # one QueryEngine writer guard. Do not reload a second time here.
        from app.core import query_engine
        if not query_engine.is_ready:
            error_msg = (
                "Database swap completed but QueryEngine is not ready. "
                "The previous database was retained or restored; see sync logs."
            )
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False

        # Save version info ONLY after reload succeeds and is_ready = True
        # This prevents the "false success" bug where sync fails but version is saved
        logger.info("Saving version info after successful reload...")
        version_metadata = {
            "framework_version": framework_version,
            "framework_authoring_schema_version": framework_authoring_schema_version,
            "framework_public_schema_version": framework_public_schema_version,
            "framework_schema_metadata_sha256": framework_schema_metadata_sha256,
            "total_documents": len(all_documents),
            "total_actionable_items": statistics.get("overview", {}).get("total_actionable_items"),
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dimension": settings.EMBEDDING_DIMENSION,
            "index_schema_version": settings.CACHE_SCHEMA_VERSION,
            "source_kind": expected_source_kind,
            "source_revision_kind": expected_revision_kind,
            "source_revision": latest_sha,
            "source_repository": expected_source_repository,
            "source_ref": expected_source_ref,
            "source_content_sha256": source_content_sha256,
            "source_files": source_files,
            "statistics": statistics,
        }
        try:
            save_version_info(latest_sha, version_metadata)
        except Exception as metadata_error:
            rollback_error = None
            try:
                restored_lkg = await _rollback_active_database_after_metadata_failure()
            except Exception as exc:
                restored_lkg = False
                rollback_error = exc

            recovery = (
                "The last-known-good database was restored."
                if restored_lkg
                else "The uncommitted database was taken offline."
            )
            if rollback_error is not None:
                recovery += f" Rollback also reported: {rollback_error}"
            error_msg = (
                f"Failed to durably save framework version metadata: {metadata_error}. "
                + recovery
            )
            logger.error(error_msg, exc_info=True)
            _set_last_sync_error(error_msg)
            return False

        # The backup is retained through active-table initialization and the
        # durable version/provenance write. Only now is rollback state obsolete.
        if not await _cleanup_successful_sync_artifacts():
            return False

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


async def run_sync(force_rebuild: bool = False) -> bool:
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
        return await core_sync(force_rebuild=force_rebuild)
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
    """Run an immediate update check, then sync periodically with failure backoff."""
    logger.info(
        f"Starting sync loop (interval: {settings.SYNC_INTERVAL_SECONDS}s)"
    )

    consecutive_failures = 0
    max_backoff = 3600 * 4  # Cap at 4 hours
    first_check = True

    while True:
        try:
            # Warm services check immediately. Subsequent checks wait for the
            # configured interval or exponential failure backoff.
            if first_check:
                first_check = False
            elif consecutive_failures > 0:
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
