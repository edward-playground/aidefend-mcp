"""
Synchronization service for AIDEFEND framework content.
Handles GitHub sync, parsing, embedding, and indexing with security.
"""

import asyncio
import hashlib
import json
import httpx
import lancedb
import pyarrow as pa
import time
import re
import os
import shutil
import secrets
import stat
import sys
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, NoReturn, Optional, Sequence, Tuple
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
    set_secure_file_permissions,
)
from app.utils import (
    _await_cancellation_safe,
    _atomic_write_json,
    _durable_rename,
    _durable_unlink,
    parse_js_file_with_node,
    save_version_info,
    save_sync_timestamp,
    get_local_commit_sha,
    load_version_info,
    format_bytes,
)
from app.embedding_cache import EmbeddingCache, compute_content_hash
from app.framework_utils import (
    build_framework_metrics,
    extract_framework_coverage,
    framework_labels_from_registry,
    framework_key,
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
from app.framework_migrations import (
    FrameworkMigrationRegistryError,
    validate_framework_migration_registry,
)
from app.generation_identity import (
    GENERATION_FINGERPRINT_FIELDS,
    GENERATION_BUILD_ID_FIELD,
    GENERATION_ID_FIELD,
    GENERATION_ID_PATTERN,
    GenerationIdentityError,
    assert_table_generation,
    bind_version_generation,
    generation_fingerprint as _generation_fingerprint,
    generation_id as _generation_id,
)
from app.instance_lock import is_lock_file_held_by_other_process

logger = get_logger(__name__)


FRAMEWORK_MANIFEST_FILENAME = "main.js"
FRAMEWORK_INTRO_FILENAME = "aidefend-intro.js"
FRAMEWORK_PUBLIC_DATA_SOURCE_PATH = "data/data.json"
FRAMEWORK_PUBLIC_DATA_FILENAME = "framework-public-data.json"
FRAMEWORK_PUBLIC_DATA_REVISION_PREFIX = "framework-public-data-"
FRAMEWORK_MIGRATIONS_SOURCE_PATH = "data/framework-migrations.json"
FRAMEWORK_MIGRATIONS_FILENAME = "framework-migrations.json"
MAX_FRAMEWORK_PUBLIC_DATA_BYTES = 8 * 1024 * 1024
MAX_FRAMEWORK_PUBLIC_DATA_JSON_DEPTH = 128
MAX_FRAMEWORK_MIGRATIONS_BYTES = 512 * 1024
GENERATION_ACTIVATION_MARKER_FILENAME = "generation_activation.pending.json"
GENERATION_ACTIVATION_MARKER_SCHEMA = "aidefend.mcp-generation-activation.v2"
MAX_GENERATION_ACTIVATION_MARKER_BYTES = 64 * 1024
GENERATION_BACKUP_METADATA_SCHEMA = "aidefend.mcp-generation-backup.v1"
MAX_GENERATION_VERSION_METADATA_BYTES = 16 * 1024 * 1024
MAX_GENERATION_BACKUP_METADATA_BYTES = 20 * 1024 * 1024
MAX_DURABLE_TOMBSTONES_PER_CLEANUP = 32
_DURABLE_TOMBSTONE_PATTERN = re.compile(
    r"^\.(?:generation_activation\.pending\.json|"
    r"aidefend_backup(?:_\d+)?\.version\.json)"
    r"\.deleted-\d+-[0-9a-f]{16}$"
)
_FRAMEWORK_PUBLIC_DATA_REVISION_FILENAME_PATTERN = re.compile(
    rf"^{re.escape(FRAMEWORK_PUBLIC_DATA_REVISION_PREFIX)}[0-9a-f]{{40}}\.json$"
)
UNKNOWN_FRAMEWORK_SCHEMA_VERSION = "unknown"
LEGACY_FRAMEWORK_VERSION = "1.20260704"
LEGACY_FRAMEWORK_REPOSITORY = "edward-playground/aidefense-framework"
LEGACY_FRAMEWORK_SOURCE_REVISION = "145ab11c510e38c022073056fd5933fecc02cef8"
LEGACY_FRAMEWORK_CONTENT_SHA256 = "3baac4cbdea29401d3b87c259b20ebe653e13708e7974b73d46a6d6ac3cf4fe9"
VALID_PILLARS = {"model", "app", "data", "infra"}
VALID_PHASES = {"scoping", "building", "validation", "operation", "response", "improvement"}
EXPECTED_FRAMEWORK_LABELS = [
    "MITRE ATLAS",
    "MAESTRO",
    "OWASP LLM Top 10 2026",
    "OWASP ML Top 10 2023",
    "OWASP Top 10 for Agentic Applications 2026",
    "NIST Adversarial Machine Learning 2025",
    "Cisco Integrated AI Security and Safety Framework",
    "Google Secure AI Framework 2.0 - Risks",
    "Databricks AI Security Framework 3.0",
]
TACTIC_ID_SEGMENT = r"[A-Z][A-Z0-9]*"
CONTROL_ID_PATTERN = re.compile(rf"AID-{TACTIC_ID_SEGMENT}-\d{{3}}(?:\.\d{{3}})?\Z")
GUIDANCE_ID_PATTERN = re.compile(
    rf"(?P<control>AID-{TACTIC_ID_SEGMENT}-\d{{3}}(?:\.\d{{3}})?)" r"-G(?P<ordinal>\d{3})\Z"
)
NOT_APPLICABLE_PATTERN = re.compile(r"^N/A(?:\s+\([^\r\n]+\))?$", re.IGNORECASE)
SOURCE_AVAILABLE_TOOL_PATTERN = re.compile(r"^.+\s\([^();]+;\s(?:source-available|open-weight)\)$")


class GenerationRestoreRetryableError(RuntimeError):
    """A verified backup was preserved but could not become operational."""


AUTHORING_TOOL_FIELDS = (
    "toolsOpenSource",
    "toolsSourceAvailable",
    "toolsCommercial",
)
_SCHEMA_VERSION_COMPONENT_PATTERN = r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}"


class FrameworkPublicDataDiscoveryStatus(str, Enum):
    """Outcome classes used by public-schema fallback policy."""

    AVAILABLE = "available"
    TRANSIENT_UNAVAILABLE = "transient_unavailable"
    INVALID = "invalid"


@dataclass(frozen=True)
class FrameworkPublicDataStageResult:
    """Result of staging the public dataset used only for schema discovery."""

    path: Optional[Path]
    status: FrameworkPublicDataDiscoveryStatus
    detail: str = ""
    retained_previous: bool = False


class FrameworkPublicDataError(ValueError):
    """The optional public dataset cannot safely provide schema metadata."""


def framework_public_data_staged_filename(source_revision: str) -> str:
    """Return the bounded staging name for one immutable GitHub revision."""
    immutable_sha = validate_commit_sha(source_revision)
    return f"{FRAMEWORK_PUBLIC_DATA_REVISION_PREFIX}{immutable_sha}.json"


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
                0o666,  # rw-rw-rw-
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
                    logger.debug(
                        "Could not close lockfile descriptor after contention", exc_info=True
                    )
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


# Stable cross-process ownership lease for the complete DATA_PATH. Long-lived
# REST/MCP services hold it for their lifetime; standalone sync/recovery borrows
# it for one operation. Keeping the historical sync.lock path also blocks older
# AIDEFEND writers that do not understand the lifetime-lease protocol.
_file_lock = SyncFileLock(settings.DATA_PATH / "sync.lock")

import threading

_lease_state_lock = threading.Lock()
_sync_operation_lock = threading.Lock()
_lifetime_lease_owned = False
_operation_borrows_lifetime_lease = False

# Thread-safe global state for last sync error
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
    global _operation_borrows_lifetime_lease

    # Serialize recovery/sync inside the owning service process.  The lifetime
    # OS lease is deliberately non-reentrant, so operations borrow it instead
    # of trying to lock the same file again.
    if not _sync_operation_lock.acquire(blocking=False):
        logger.warning("Another sync or recovery operation is already in progress")
        return False

    with _lease_state_lock:
        if _lifetime_lease_owned:
            _operation_borrows_lifetime_lease = True
            acquired = True
        else:
            _operation_borrows_lifetime_lease = False
            # This is a non-blocking OS-lock attempt. Calling it directly keeps
            # ownership and task cancellation atomic; a cancelled executor
            # future could otherwise leak a lock acquired by its worker.
            acquired = _file_lock.acquire(timeout=0)

    if acquired:
        logger.info(
            "Acquired sync-operation lock%s",
            (
                " under the service lifetime lease"
                if _operation_borrows_lifetime_lease
                else " and DATA_PATH lease"
            ),
        )
        return True

    _sync_operation_lock.release()

    # Lock not acquired - provide diagnostic information
    # Use a single try block to avoid TOCTOU race (file could vanish between exists() and stat())
    lock_file = settings.DATA_PATH / "sync.lock"
    try:
        stat_info = lock_file.stat()
        mtime = datetime.fromtimestamp(stat_info.st_mtime)
        age = datetime.now() - mtime
        age_seconds = age.total_seconds()

        logger.warning(
            f"DATA_PATH is owned by another AIDEFEND process. "
            f"Lock file age: {age_seconds:.1f} seconds. "
            "Stop that process before retrying; do not delete the lock file."
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
    global _operation_borrows_lifetime_lease

    if not _sync_operation_lock.locked():
        return
    try:
        with _lease_state_lock:
            borrowed = _operation_borrows_lifetime_lease
            _operation_borrows_lifetime_lease = False
            if not borrowed:
                _file_lock.release()
        logger.info("Released sync-operation lock")
    except Exception as e:
        logger.warning(f"Error releasing lock: {e}")
    finally:
        _sync_operation_lock.release()


def acquire_service_instance_lock() -> bool:
    """Claim exclusive lifetime ownership of the configured data directory."""
    global _lifetime_lease_owned

    with _lease_state_lock:
        if _lifetime_lease_owned or _sync_operation_lock.locked():
            acquired = False
        else:
            acquired = _file_lock.acquire(timeout=0)
            if acquired:
                _lifetime_lease_owned = True
    if acquired:
        logger.info("Acquired exclusive AIDEFEND service-instance lock")
    else:
        logger.error(
            "Another AIDEFEND service instance already owns DATA_PATH: %s",
            settings.DATA_PATH,
        )
    return acquired


def release_service_instance_lock() -> None:
    """Release this process's lifetime DATA_PATH ownership, if held."""
    global _lifetime_lease_owned

    with _lease_state_lock:
        if not _lifetime_lease_owned:
            return
        if _sync_operation_lock.locked():
            logger.critical(
                "Refusing to release the DATA_PATH lifetime lease while a sync "
                "or recovery operation is still running"
            )
            return
        _file_lock.release()
        _lifetime_lease_owned = False
    logger.info("Released AIDEFEND service-instance lock")


@asynccontextmanager
async def service_instance_guard(service_name: str):
    """Fail closed when another long-lived service shares ``DATA_PATH``."""
    if not acquire_service_instance_lock():
        raise RuntimeError(
            f"Cannot start {service_name}: another AIDEFEND REST or MCP service "
            f"is already using DATA_PATH {settings.DATA_PATH}. Stop the other "
            "instance or configure a distinct DATA_PATH."
        )
    try:
        yield
    finally:
        release_service_instance_lock()


def is_sync_in_progress() -> bool:
    """
    Check if sync is currently running (cross-process check).

    Note: This checks if the lock file exists and is locked.
    For cross-process checking, we verify the lock file's existence.

    Returns:
        True if file lock is currently held by current process
    """
    # A service normally holds the OS lease even while idle. The process-local
    # operation mutex is therefore the authoritative in-service sync state.
    return _sync_operation_lock.locked()


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
    lock_file = settings.DATA_PATH / "sync.lock"

    if _file_lock.is_locked:
        # Current process holds the lock
        return False
    return is_lock_file_held_by_other_process(lock_file)


def cleanup_stale_lock() -> None:
    """
    Report stale lock-file metadata without deleting the lock inode.

    OS advisory locks are released automatically when a process exits.  The
    persistent file is only a stable rendezvous point plus diagnostic PID/age
    metadata; an unheld file never blocks a later acquisition.  Deleting it
    after a separate "not held" probe creates a check/unlink race on Unix: a
    new owner can lock the old inode just before it is unlinked while another
    process creates and locks a replacement inode.  Two writers would then
    believe they hold the same logical lock.

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

        # An old unheld file is harmless and intentionally retained so every
        # process continues to coordinate on the same inode.
        if age_seconds > settings.LOCK_MAX_AGE_SECONDS:
            logger.warning(
                f"Inactive sync lock metadata is stale (age: {age_seconds:.1f} "
                f"seconds, threshold: {settings.LOCK_MAX_AGE_SECONDS} seconds); "
                "retaining the stable lock file because the OS lock is not held"
            )
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
        # Resolve an interrupted DB/metadata generation before any health check
        # can declare a physically valid but semantically mismatched table ready.
        await recover_incomplete_generation_activation()

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
            logger.warning("This may take several minutes, depending on the host...")

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


def _calculate_statistics_from_records(
    records: List[Dict[str, Any]],
    *,
    framework_labels: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
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
        doc_type = record.get("type", "unknown")
        tactic = record.get("tactic", "Unknown")
        pillar_raw = record.get("pillar", "")
        phase_raw = record.get("phase", "")

        # Parse pillar and phase (stored as JSON arrays)
        pillars = parse_json_list(pillar_raw)
        phases = parse_json_list(phase_raw)

        # Count by type
        type_counts[doc_type] += 1

        # Count by tactic
        tactic_counts[tactic] += 1

        scope_boundary = record.get("scope_boundary", "{}")
        has_scope_boundary = (
            bool(scope_boundary)
            if isinstance(scope_boundary, dict)
            else scope_boundary not in ("", "{}", "null")
        )
        if doc_type in ("technique", "subtechnique") and has_scope_boundary:
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

            defends_against = parse_json_list(record.get("defends_against", "[]"))
            tools_opensource = parse_json_list(record.get("tools_opensource", "[]"))
            tools_source_available = parse_json_list(record.get("tools_source_available", "[]"))
            tools_commercial = parse_json_list(record.get("tools_commercial", "[]"))

            if defends_against:
                techniques_with_defenses += 1
                coverage = extract_framework_coverage(
                    defends_against,
                    framework_labels=framework_labels,
                )
                covered_framework_sets = merge_framework_coverage_sets(
                    covered_framework_sets, coverage
                )
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
        has_code = record.get("has_code_snippets", False)
        if doc_type == "strategy" and has_code:
            documents_with_code += 1
        if doc_type == "strategy" and record.get("guidance_id"):
            canonical_guidance_documents += 1

    threat_framework_coverage = build_framework_metrics(
        covered_sets=covered_framework_sets,
        total_sets=total_framework_sets,
        framework_labels=framework_labels,
    )
    threat_framework_coverage["techniques_with_threat_mappings"] = techniques_with_defenses
    threat_framework_coverage["techniques_mapped_percentage"] = (
        round((techniques_with_defenses / actionable_total) * 100, 1)
        if actionable_total > 0
        else 0.0
    )

    # Build statistics object (matching get_statistics format)
    statistics = {
        "overview": {
            "total_documents": total_documents,
            "total_techniques": type_counts.get("technique", 0),
            "total_subtechniques": type_counts.get("subtechnique", 0),
            "total_strategies": type_counts.get("strategy", 0),
            "total_parent_families": sum(
                1 for record in records if record.get("is_parent_family") is True
            ),
            "total_standalone_techniques": sum(
                1
                for record in records
                if record.get("type") == "technique" and is_actionable_record(record)
            ),
            "total_actionable_items": actionable_total,
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "embedding_model": settings.EMBEDDING_MODEL,
            "database_path": settings.DB_PATH.name,
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
            "opensource_coverage_percentage": (
                round((techniques_with_opensource_tools / actionable_total) * 100, 1)
                if actionable_total > 0
                else 0
            ),
            "source_available_coverage_percentage": (
                round((techniques_with_source_available_tools / actionable_total) * 100, 1)
                if actionable_total > 0
                else 0
            ),
            "commercial_coverage_percentage": (
                round((techniques_with_commercial_tools / actionable_total) * 100, 1)
                if actionable_total > 0
                else 0
            ),
        },
        "implementation_resources": {
            "documents_with_code_snippets": documents_with_code,
            "canonical_guidance_documents": canonical_guidance_documents,
            "strategies_total": type_counts.get("strategy", 0),
            "code_coverage_percentage": (
                round((documents_with_code / type_counts.get("strategy", 1)) * 100, 1)
                if type_counts.get("strategy", 0) > 0
                else 0
            ),
        },
    }

    return statistics


def _build_threat_mappings(
    records: List[Dict[str, Any]],
    *,
    framework_labels: Optional[Mapping[str, str]] = None,
) -> Dict[str, List[str]]:
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

        technique_id = record.get("source_id")
        defends_against = parse_json_list(record.get("defends_against", "[]"))

        try:
            if not defends_against:
                continue

            # Extract all threat items
            for framework_data in defends_against:
                framework_name = framework_data.get("framework", "")
                items = framework_data.get("items", [])

                for item in items:
                    normalized_id = normalize_framework_item(
                        framework_name,
                        item,
                        framework_labels=framework_labels,
                    )
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

    if filename == FRAMEWORK_MIGRATIONS_SOURCE_PATH:
        framework_root = settings.LOCAL_FRAMEWORK_PATH.resolve()
        return validate_file_path(
            framework_root / "data" / FRAMEWORK_MIGRATIONS_FILENAME,
            framework_root,
        )

    safe_filename = sanitize_filename(filename)
    if safe_filename in {
        FRAMEWORK_INTRO_FILENAME,
        FRAMEWORK_MANIFEST_FILENAME,
    }:
        return settings.LOCAL_FRAMEWORK_PATH / safe_filename
    return settings.local_framework_tactics_path / safe_filename


def _staged_framework_filename(source_name: str) -> str:
    """Map one repository-relative source name to its bounded staging filename."""
    if source_name == FRAMEWORK_MIGRATIONS_SOURCE_PATH:
        return FRAMEWORK_MIGRATIONS_FILENAME
    return sanitize_filename(source_name)


def _framework_source_files(
    tactic_files: Sequence[str],
    *,
    include_framework_migrations: bool = False,
) -> List[str]:
    """Return the exact ordered file list covered by framework provenance hashes."""
    tactic_list = list(tactic_files)
    if not tactic_list or len(tactic_list) != len(set(tactic_list)):
        raise FrameworkManifestError("framework tactic file list must be non-empty and unique")
    metadata_files = [FRAMEWORK_MIGRATIONS_SOURCE_PATH] if include_framework_migrations else []
    return [FRAMEWORK_INTRO_FILENAME, *metadata_files, *tactic_list]


def _compute_local_framework_signature(
    tactic_files: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Compute a stable content hash for the local framework source tree."""
    digest = hashlib.sha1(usedforsecurity=False)
    missing_required: List[str] = []
    if tactic_files is None:
        tactic_files = load_local_tactic_manifest()
    migration_path = _get_local_framework_file(FRAMEWORK_MIGRATIONS_SOURCE_PATH)
    source_files = _framework_source_files(
        tactic_files,
        include_framework_migrations=migration_path.is_file(),
    )

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
            },
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
    tactic membership and order; when present, the public migration registry is
    hashed by its repository-relative source path before the tactic payloads.
    Omitting the argument preserves the legacy configured list for callers
    verifying an older staged index.
    """
    ordered_source_files = list(settings.AIDEFEND_FILES if source_files is None else source_files)
    if not ordered_source_files or len(ordered_source_files) != len(set(ordered_source_files)):
        raise ValueError("Cannot hash an empty or duplicate framework source file list")
    staged_by_name = {path.name: path for path in staged_files}
    missing = [
        source_name
        for source_name in ordered_source_files
        if _staged_framework_filename(source_name) not in staged_by_name
    ]
    if missing:
        raise ValueError("Cannot hash incomplete staged framework source: " + ", ".join(missing))

    if algorithm == "sha1":
        digest = hashlib.sha1(usedforsecurity=False)
    elif algorithm == "sha256":
        digest = hashlib.sha256()
    else:
        raise ValueError(f"Unsupported framework digest algorithm: {algorithm}")

    for source_name in ordered_source_files:
        staged_name = _staged_framework_filename(source_name)
        digest.update(source_name.encode("utf-8"))
        digest.update(_read_canonical_framework_bytes(staged_by_name[staged_name]))

    return digest.hexdigest()


def _stage_local_framework_file(filename: str) -> Optional[Path]:
    """Copy a local framework file into RAW_PATH for normal parsing."""
    safe_filename = _staged_framework_filename(filename)
    source_path = _get_local_framework_file(filename)

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
        extra={"file_name": safe_filename, "source_path": str(source_path), "size": file_size},
    )
    return validated_path


def _reject_framework_public_data_duplicate_keys(
    pairs: List[Tuple[str, Any]],
) -> Dict[str, Any]:
    """Reject ambiguous keys at every nesting depth of the public dataset."""
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FrameworkPublicDataError(
                f"framework public dataset contains duplicate JSON key {key!r}"
            )
        result[key] = value
    return result


def _reject_framework_public_data_constant(value: str) -> NoReturn:
    raise FrameworkPublicDataError(
        f"framework public dataset contains non-standard JSON value {value!r}"
    )


def _validate_framework_public_data_json_depth(source: str) -> None:
    """Reject deeply nested JSON independently of interpreter recursion behavior.

    CPython's JSON decoder recursion behavior is an implementation detail and
    changed in Python 3.14. Count structural delimiters before decoding so a
    bounded metadata read cannot become a parser recursion or memory bomb. JSON
    syntax, including delimiter matching, remains the decoder's responsibility.
    """
    depth = 0
    in_string = False
    escaped = False
    for character in source:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_FRAMEWORK_PUBLIC_DATA_JSON_DEPTH:
                raise FrameworkPublicDataError(
                    "framework public dataset exceeds the JSON nesting-depth "
                    f"limit of {MAX_FRAMEWORK_PUBLIC_DATA_JSON_DEPTH}"
                )
        elif character in "]}" and depth > 0:
            depth -= 1


def _parse_framework_public_schema_bytes(content: bytes) -> str:
    """Extract the exact root ``version.schemaVersion`` from bounded JSON bytes."""
    if not content or len(content) > MAX_FRAMEWORK_PUBLIC_DATA_BYTES:
        raise FrameworkPublicDataError(
            "framework public dataset size must be between 1 and "
            f"{MAX_FRAMEWORK_PUBLIC_DATA_BYTES} bytes"
        )
    try:
        source = content.decode("utf-8")
        _validate_framework_public_data_json_depth(source)
        payload = json.loads(
            source,
            object_pairs_hook=_reject_framework_public_data_duplicate_keys,
            parse_constant=_reject_framework_public_data_constant,
        )
    except FrameworkPublicDataError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise FrameworkPublicDataError(
            f"framework public dataset is not strict UTF-8 JSON: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise FrameworkPublicDataError("framework public dataset root must be an object")
    version = payload.get("version")
    if not isinstance(version, dict):
        raise FrameworkPublicDataError("framework public dataset version must be an object")
    schema_version = version.get("schemaVersion")
    if (
        not isinstance(schema_version, str)
        or re.fullmatch(
            _SCHEMA_VERSION_COMPONENT_PATTERN,
            schema_version,
        )
        is None
    ):
        raise FrameworkPublicDataError(
            "framework public dataset version.schemaVersion must be a valid "
            "schema-version component string"
        )
    return schema_version


def _read_bounded_framework_public_data(path: Path) -> bytes:
    """Read at most one byte beyond the public-dataset limit."""
    with path.open("rb") as handle:
        return handle.read(MAX_FRAMEWORK_PUBLIC_DATA_BYTES + 1)


def extract_framework_public_schema_version(
    public_data_path: Optional[Path],
    *,
    base_dir: Path,
) -> str:
    """Safely discover the public schema version or return ``unknown``.

    Only the root object's ``version.schemaVersion`` is accepted. The parser is
    intentionally independent of README text, release names, file names, and MCP
    constants so future valid framework schema versions are discovered dynamically.
    """
    if public_data_path is None:
        return UNKNOWN_FRAMEWORK_SCHEMA_VERSION
    try:
        validated_path = validate_file_path(Path(public_data_path), Path(base_dir))
        if not validated_path.is_file():
            raise FileNotFoundError(f"framework public dataset is missing: {validated_path}")
        size = validated_path.stat().st_size
        if size <= 0 or size > MAX_FRAMEWORK_PUBLIC_DATA_BYTES:
            raise FrameworkPublicDataError(
                "framework public dataset size must be between 1 and "
                f"{MAX_FRAMEWORK_PUBLIC_DATA_BYTES} bytes"
            )
        return _parse_framework_public_schema_bytes(
            _read_bounded_framework_public_data(validated_path)
        )
    except (
        OSError,
        PathTraversalError,
        FrameworkPublicDataError,
    ) as exc:
        logger.warning(
            "Framework public schema metadata could not be safely discovered; "
            "recording '%s': %s",
            UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
            exc,
        )
        return UNKNOWN_FRAMEWORK_SCHEMA_VERSION


def _stored_source_revision(version_info: Dict[str, Any]) -> str:
    return str(version_info.get("source_revision") or version_info.get("commit_sha") or "")


def resolve_effective_framework_public_schema_version(
    discovered_version: str,
    *,
    version_info: Dict[str, Any],
    current_source_revision: str,
    source_kind: str,
    current_source_repository: Optional[str] = None,
    discovery_status: FrameworkPublicDataDiscoveryStatus,
) -> str:
    """Apply the narrowly bounded same-revision public-schema fallback policy."""
    stored_revision = _stored_source_revision(version_info)
    stored_version = version_info.get("framework_public_schema_version")
    stored_source = version_info.get("framework_public_schema_source")
    expected_repository = (
        current_source_repository
        if current_source_repository is not None
        else settings.github_repo_path
    )
    stored_value_is_bound = (
        isinstance(stored_version, str)
        and re.fullmatch(_SCHEMA_VERSION_COMPONENT_PATTERN, stored_version) is not None
        and stored_source == FRAMEWORK_PUBLIC_DATA_SOURCE_PATH
    )
    same_immutable_github_revision = (
        source_kind == "github"
        and version_info.get("source_kind") == "github"
        and version_info.get("source_revision_kind") == "git_commit_sha"
        and str(version_info.get("source_repository", "")).strip().lower()
        == expected_repository.strip().lower()
        and re.fullmatch(r"[0-9a-f]{40}", current_source_revision) is not None
        and bool(stored_revision)
        and stored_revision == current_source_revision
    )

    discovered_is_valid = (
        isinstance(discovered_version, str)
        and re.fullmatch(
            _SCHEMA_VERSION_COMPONENT_PATTERN,
            discovered_version,
        )
        is not None
    )
    if discovery_status == FrameworkPublicDataDiscoveryStatus.AVAILABLE:
        return discovered_version if discovered_is_valid else UNKNOWN_FRAMEWORK_SCHEMA_VERSION

    if (
        discovery_status == FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE
        and same_immutable_github_revision
        and stored_value_is_bound
        and discovered_is_valid
        and discovered_version == stored_version
    ):
        logger.warning(
            "Framework public dataset fetch was temporarily unavailable for "
            "unchanged GitHub commit %s; retaining its previously verified public "
            "schema version %s",
            current_source_revision[:8],
            stored_version,
        )
        return str(stored_version)

    return UNKNOWN_FRAMEWORK_SCHEMA_VERSION


def uses_legacy_framework_contract(
    *,
    source_kind: str,
    source_repository: str,
    source_revision: str,
    source_content_sha256: str,
    framework_version: str,
) -> bool:
    """Select the one known historical release that needs compatibility.

    This is deliberately tied to the canonical source identity and content, not
    optional metadata. Only the known 2026-07-04 GitHub release may omit guidance
    IDs and use its historical parent threat-union semantics.
    """
    return (
        source_kind == "github"
        and source_repository.strip().lower() == LEGACY_FRAMEWORK_REPOSITORY
        and source_revision.strip().lower() == LEGACY_FRAMEWORK_SOURCE_REVISION
        and source_content_sha256.strip().lower() == LEGACY_FRAMEWORK_CONTENT_SHA256
        and framework_version == LEGACY_FRAMEWORK_VERSION
    )


def _discard_staged_framework_migrations_file() -> None:
    """Remove a stale migration registry when the selected source has none."""
    try:
        staged_path = validate_file_path(
            settings.RAW_PATH / FRAMEWORK_MIGRATIONS_FILENAME,
            settings.RAW_PATH,
        )
        if staged_path.exists():
            staged_path.unlink()
    except Exception as exc:
        logger.warning("Could not discard stale framework migration metadata: %s", exc)


def _reject_duplicate_json_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    """Build a JSON object while rejecting duplicate keys at every depth."""
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FrameworkMigrationRegistryError(
                f"framework migration registry contains duplicate JSON key {key!r}"
            )
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> NoReturn:
    """Reject NaN and infinities, which are not valid JSON values."""
    raise FrameworkMigrationRegistryError(
        f"framework migration registry contains non-standard JSON value {value!r}"
    )


def load_and_validate_framework_migrations(
    registry_path: Optional[Path],
) -> Optional[Dict[str, Any]]:
    """Load one bounded UTF-8 registry and apply the shared fail-closed contract."""
    if registry_path is None:
        return None
    registry_path = validate_file_path(registry_path, settings.RAW_PATH)
    if not registry_path.is_file():
        return None
    size = registry_path.stat().st_size
    if size <= 0 or size > MAX_FRAMEWORK_MIGRATIONS_BYTES:
        raise FrameworkMigrationRegistryError(
            "framework migration registry size must be between 1 and "
            f"{MAX_FRAMEWORK_MIGRATIONS_BYTES} bytes"
        )
    try:
        text = registry_path.read_bytes().decode("utf-8-sig")
        registry = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except FrameworkMigrationRegistryError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FrameworkMigrationRegistryError(
            f"framework migration registry is not valid UTF-8 JSON: {exc}"
        ) from exc
    if not isinstance(registry, dict):
        raise FrameworkMigrationRegistryError("framework migration registry root must be an object")
    return validate_framework_migration_registry(registry)


def compute_framework_migrations_sha256(registry_path: Path) -> str:
    """Hash the exact staged registry bytes using the framework newline policy."""
    registry_path = validate_file_path(registry_path, settings.RAW_PATH)
    if not registry_path.is_file():
        raise FrameworkMigrationRegistryError(
            "framework migration registry is missing from staged content"
        )
    return hashlib.sha256(_read_canonical_framework_bytes(registry_path)).hexdigest()


async def download_framework_migrations_file(commit_sha: str) -> Optional[Path]:
    """Stage the optional public migration registry from the exact source revision.

    Absence is retained for the known legacy 2025 source contract. A present but
    invalid, oversized, or unavailable artifact is an update failure so the
    last-known-good database remains active.
    """
    destination = validate_file_path(
        settings.RAW_PATH / FRAMEWORK_MIGRATIONS_FILENAME,
        settings.RAW_PATH,
    )
    if _using_local_framework_source():
        source_path = _get_local_framework_file(FRAMEWORK_MIGRATIONS_SOURCE_PATH)
        if not source_path.is_file():
            _discard_staged_framework_migrations_file()
            return None
        if source_path.stat().st_size > MAX_FRAMEWORK_MIGRATIONS_BYTES:
            raise FrameworkMigrationRegistryError(
                "local framework migration registry exceeds the size limit"
            )
        content = source_path.read_bytes()
        try:
            content.decode("utf-8-sig")
        except UnicodeError as exc:
            raise FrameworkMigrationRegistryError(
                "local framework migration registry is not UTF-8"
            ) from exc
        destination.write_bytes(content)
        set_secure_file_permissions(destination)
        logger.info(
            "Staged %s from local framework (%s)",
            FRAMEWORK_MIGRATIONS_SOURCE_PATH,
            format_bytes(len(content)),
        )
        return destination

    immutable_sha = validate_commit_sha(commit_sha)
    url = f"{settings.github_raw_base_url}/{immutable_sha}/" f"{FRAMEWORK_MIGRATIONS_SOURCE_PATH}"
    validate_github_url(url, settings.github_repo_path)
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "AIDEFEND-MCP-Service/1.3"},
            )
            if response.status_code == 404:
                _discard_staged_framework_migrations_file()
                return None
            response.raise_for_status()
            content = response.content
    except httpx.HTTPStatusError as exc:
        raise FrameworkMigrationRegistryError(
            "failed to download framework migration registry from immutable "
            f"commit: HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise FrameworkMigrationRegistryError(
            f"failed to download framework migration registry: {exc}"
        ) from exc

    if len(content) > MAX_FRAMEWORK_MIGRATIONS_BYTES:
        raise FrameworkMigrationRegistryError(
            "downloaded framework migration registry exceeds the size limit"
        )
    try:
        content.decode("utf-8-sig")
    except UnicodeError as exc:
        raise FrameworkMigrationRegistryError(
            "downloaded framework migration registry is not UTF-8"
        ) from exc
    destination.write_bytes(content)
    set_secure_file_permissions(destination)
    logger.info(
        "Downloaded %s from immutable commit %s (%s)",
        FRAMEWORK_MIGRATIONS_SOURCE_PATH,
        immutable_sha[:8],
        format_bytes(len(content)),
    )
    return destination


def validate_framework_migrations_corpus_contract(
    registry: Optional[Mapping[str, Any]],
    parsed_tactics: Sequence[Mapping[str, Any]],
) -> None:
    """Bind migration metadata to the exact framework corpus being indexed."""
    validated = validate_framework_migration_registry(registry) if registry is not None else None
    effective_labels = framework_labels_from_registry(validated)
    mappings: List[Mapping[str, Any]] = []
    for tactic in parsed_tactics:
        for technique in tactic.get("techniques", []):
            if not isinstance(technique, Mapping):
                continue
            raw_children = technique.get("subTechniques", [])
            children = raw_children if isinstance(raw_children, list) else []
            controls = [technique, *children]
            for control in controls:
                if isinstance(control, Mapping):
                    mappings.extend(
                        mapping
                        for mapping in control.get("defendsAgainst", [])
                        if isinstance(mapping, Mapping)
                    )

    mappings_by_key: Dict[str, List[Mapping[str, Any]]] = {}
    for mapping in mappings:
        raw_label = mapping.get("framework")
        if not isinstance(raw_label, str):
            raise FrameworkMigrationRegistryError(
                f"framework mapping labels must be strings, found {raw_label!r}"
            )
        stable_key = framework_key(
            raw_label,
            framework_labels=effective_labels,
        )
        if stable_key is None:
            continue
        if raw_label != raw_label.strip():
            raise FrameworkMigrationRegistryError(
                "framework labels must be exact non-padded strings: " f"{raw_label!r}"
            )
        mappings_by_key.setdefault(stable_key, []).append(mapping)

    owasp_mappings = mappings_by_key.get("owasp_llm", [])
    labels = {mapping["framework"] for mapping in owasp_mappings}

    if registry is None:
        if labels != {"OWASP LLM Top 10 2025"}:
            raise FrameworkMigrationRegistryError(
                "a missing migration registry is allowed only for the exact legacy "
                f"OWASP LLM Top 10 2025 corpus; found labels {sorted(labels)!r}"
            )
        return

    if validated is None:
        raise FrameworkMigrationRegistryError(
            "the migration registry disappeared after successful validation"
        )
    for stable_key, catalog in validated["frameworks"].items():
        framework_mappings = mappings_by_key.get(stable_key, [])
        framework_labels = {mapping["framework"] for mapping in framework_mappings}
        expected_label = catalog["activeLabel"]
        if framework_labels != {expected_label}:
            raise FrameworkMigrationRegistryError(
                f"{stable_key} corpus label does not match the migration registry: "
                f"expected {expected_label!r}, found {sorted(framework_labels)!r}"
            )

        active_by_normalized_id: Dict[str, Mapping[str, Any]] = {}
        for active_item in catalog["activeItems"]:
            normalized_active_id = normalize_framework_item(
                expected_label,
                active_item["id"],
                framework_labels=effective_labels,
            )
            if not normalized_active_id:
                raise FrameworkMigrationRegistryError(
                    f"{stable_key} active registry item cannot be normalized: "
                    f"{active_item['id']!r}"
                )
            if normalized_active_id in active_by_normalized_id:
                raise FrameworkMigrationRegistryError(
                    f"{stable_key} active registry items normalize to the same ID: "
                    f"{normalized_active_id!r}"
                )
            active_by_normalized_id[normalized_active_id] = active_item
        for mapping in framework_mappings:
            raw_items = mapping.get("items")
            if not isinstance(raw_items, list):
                raise FrameworkMigrationRegistryError(
                    f"{stable_key} mapping items must be an array"
                )
            for raw_item in raw_items:
                if not isinstance(raw_item, str) or raw_item != raw_item.strip():
                    raise FrameworkMigrationRegistryError(
                        f"{stable_key} mapping items must be exact non-padded strings: "
                        f"{raw_item!r}"
                    )
                item = raw_item
                if item == "N/A":
                    continue
                identifier = normalize_framework_item(
                    expected_label,
                    item,
                    framework_labels=effective_labels,
                )
                active_item = active_by_normalized_id.get(identifier or "")
                if active_item is None:
                    raise FrameworkMigrationRegistryError(
                        f"{stable_key} mapping uses an item outside the active registry: "
                        f"{item!r}"
                    )
                active_identifier = active_item["id"]
                if stable_key in {"maestro", "databricks"}:
                    canonical = active_identifier
                elif stable_key == "google_saif":
                    canonical = f"{active_identifier}: {active_item['name']}"
                elif active_identifier.casefold() == active_item["name"].casefold():
                    canonical = active_identifier
                else:
                    canonical = f"{active_identifier} {active_item['name']}"
                if item == canonical:
                    continue
                if not (
                    item.startswith(canonical + " (")
                    and item.endswith(")")
                    and len(item) > len(canonical) + 3
                ):
                    raise FrameworkMigrationRegistryError(
                        f"{stable_key} mapping name or annotation does not match the "
                        f"active registry item: {item!r}"
                    )


def _discard_staged_framework_public_data_file(
    source_revision: Optional[str] = None,
) -> None:
    """Remove public-schema discovery bytes that are no longer trustworthy."""
    try:
        filename = (
            framework_public_data_staged_filename(source_revision)
            if source_revision is not None
            else FRAMEWORK_PUBLIC_DATA_FILENAME
        )
        staged_path = validate_file_path(
            settings.RAW_PATH / filename,
            settings.RAW_PATH,
        )
        if staged_path.exists():
            staged_path.unlink()
    except Exception as exc:
        logger.warning("Could not discard stale framework public dataset: %s", exc)


def _cleanup_staged_framework_public_data_revisions(
    *,
    keep_revisions: Sequence[str],
) -> None:
    """Bound revision-scoped metadata files after a generation is settled."""
    try:
        raw_root = settings.RAW_PATH.resolve()
        if not raw_root.is_dir():
            return
        keep_filenames = {
            framework_public_data_staged_filename(revision) for revision in keep_revisions
        }
        for candidate in raw_root.iterdir():
            if (
                _FRAMEWORK_PUBLIC_DATA_REVISION_FILENAME_PATTERN.fullmatch(candidate.name) is None
                or candidate.name in keep_filenames
            ):
                continue
            try:
                validated = validate_file_path(candidate, raw_root)
                if validated.is_file():
                    validated.unlink()
            except Exception as cleanup_error:
                logger.warning(
                    "Could not remove obsolete framework public dataset %s: %s",
                    candidate,
                    cleanup_error,
                )

        # Remove the unscoped pre-release staging name when operating in GitHub
        # mode. It cannot prove which immutable revision supplied its bytes.
        if keep_revisions:
            _discard_staged_framework_public_data_file()
    except Exception as exc:
        logger.warning("Could not clean framework public dataset revisions: %s", exc)


def _atomic_stage_framework_public_data(destination: Path, content: bytes) -> None:
    """Atomically replace the bounded public-schema discovery artifact."""
    destination = validate_file_path(destination, settings.RAW_PATH)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
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
                    "Could not remove incomplete framework public dataset %s: %s",
                    temporary_path,
                    cleanup_error,
                )


def _retained_framework_public_data_path(source_revision: str) -> Optional[Path]:
    """Return a still-valid staged dataset suitable for same-revision fallback."""
    try:
        staged_path = validate_file_path(
            settings.RAW_PATH / framework_public_data_staged_filename(source_revision),
            settings.RAW_PATH,
        )
        if not staged_path.is_file():
            return None
        content = _read_bounded_framework_public_data(staged_path)
        _parse_framework_public_schema_bytes(content)
        return staged_path
    except (OSError, PathTraversalError, FrameworkPublicDataError):
        _discard_staged_framework_public_data_file(source_revision)
        return None


def _framework_public_data_http_status(
    status_code: int,
) -> FrameworkPublicDataDiscoveryStatus:
    """Classify only retryable HTTP failures as transient."""
    if status_code in {408, 425, 429} or 500 <= status_code <= 599:
        return FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE
    return FrameworkPublicDataDiscoveryStatus.INVALID


async def download_framework_public_data_file(
    commit_sha: str,
    *,
    previous_source_revision: Optional[str] = None,
) -> FrameworkPublicDataStageResult:
    """Stage ``data/data.json`` solely for public-schema discovery.

    GitHub bytes are fetched from the exact immutable tactic revision and streamed
    through a hard byte limit. Local mode reads the matching configured framework
    root. All failures are metadata-only and therefore return a typed fail-closed
    result instead of aborting compatible tactic ingestion.
    """
    if _using_local_framework_source():
        destination = validate_file_path(
            settings.RAW_PATH / FRAMEWORK_PUBLIC_DATA_FILENAME,
            settings.RAW_PATH,
        )
        try:
            local_framework_path = settings.LOCAL_FRAMEWORK_PATH
            if local_framework_path is None:
                raise RuntimeError("Local framework mode is active without LOCAL_FRAMEWORK_PATH")
            local_root = local_framework_path.resolve()
            source_path = validate_file_path(
                local_root / Path(FRAMEWORK_PUBLIC_DATA_SOURCE_PATH),
                local_root,
            )
            if not source_path.is_file():
                raise FileNotFoundError(f"local framework public dataset is missing: {source_path}")
            size = source_path.stat().st_size
            if size <= 0 or size > MAX_FRAMEWORK_PUBLIC_DATA_BYTES:
                raise FrameworkPublicDataError(
                    "local framework public dataset exceeds the size limit"
                )
            content = _read_bounded_framework_public_data(source_path)
            _parse_framework_public_schema_bytes(content)
            _atomic_stage_framework_public_data(destination, content)
            logger.info(
                "Staged %s from local framework (%s)",
                FRAMEWORK_PUBLIC_DATA_SOURCE_PATH,
                format_bytes(len(content)),
            )
            return FrameworkPublicDataStageResult(
                destination,
                FrameworkPublicDataDiscoveryStatus.AVAILABLE,
            )
        except Exception as exc:
            _discard_staged_framework_public_data_file()
            logger.warning(
                "Local framework public schema discovery failed closed to '%s': %s",
                UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
                exc,
            )
            return FrameworkPublicDataStageResult(
                None,
                FrameworkPublicDataDiscoveryStatus.INVALID,
                str(exc),
            )

    try:
        immutable_sha = validate_commit_sha(commit_sha)
        destination = validate_file_path(
            settings.RAW_PATH / framework_public_data_staged_filename(immutable_sha),
            settings.RAW_PATH,
        )
        url = (
            f"{settings.github_raw_base_url}/{immutable_sha}/"
            f"{FRAMEWORK_PUBLIC_DATA_SOURCE_PATH}"
        )
        validate_github_url(url, settings.github_repo_path)
    except Exception as exc:
        return FrameworkPublicDataStageResult(
            None,
            FrameworkPublicDataDiscoveryStatus.INVALID,
            str(exc),
        )

    status = FrameworkPublicDataDiscoveryStatus.INVALID
    detail = ""
    content: Optional[bytes] = None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "GET",
                url,
                headers={"User-Agent": "AIDEFEND-MCP-Service/1.3"},
            ) as response:
                if response.status_code != 200:
                    status = _framework_public_data_http_status(response.status_code)
                    detail = f"HTTP {response.status_code}"
                else:
                    content_length = response.headers.get("content-length")
                    if content_length is not None:
                        try:
                            declared_size = int(content_length)
                        except ValueError as exc:
                            raise FrameworkPublicDataError(
                                "framework public dataset has invalid Content-Length"
                            ) from exc
                        if declared_size <= 0 or declared_size > MAX_FRAMEWORK_PUBLIC_DATA_BYTES:
                            raise FrameworkPublicDataError(
                                "framework public dataset exceeds the size limit"
                            )

                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_FRAMEWORK_PUBLIC_DATA_BYTES:
                            raise FrameworkPublicDataError(
                                "framework public dataset exceeds the size limit"
                            )
                    content = bytes(body)
                    _parse_framework_public_schema_bytes(content)
                    status = FrameworkPublicDataDiscoveryStatus.AVAILABLE
    except httpx.RequestError as exc:
        status = FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE
        detail = str(exc)
    except FrameworkPublicDataError as exc:
        status = FrameworkPublicDataDiscoveryStatus.INVALID
        detail = str(exc)
    except Exception as exc:
        status = FrameworkPublicDataDiscoveryStatus.INVALID
        detail = str(exc)

    if status == FrameworkPublicDataDiscoveryStatus.AVAILABLE and content is not None:
        try:
            _atomic_stage_framework_public_data(destination, content)
        except Exception as exc:
            _discard_staged_framework_public_data_file(immutable_sha)
            logger.warning(
                "Could not safely stage framework public dataset; public schema is '%s': %s",
                UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
                exc,
            )
            return FrameworkPublicDataStageResult(
                None,
                FrameworkPublicDataDiscoveryStatus.INVALID,
                str(exc),
            )
        logger.info(
            "Staged %s from immutable GitHub commit %s (%s)",
            FRAMEWORK_PUBLIC_DATA_SOURCE_PATH,
            immutable_sha[:8],
            format_bytes(len(content)),
        )
        return FrameworkPublicDataStageResult(destination, status)

    if (
        status == FrameworkPublicDataDiscoveryStatus.TRANSIENT_UNAVAILABLE
        and previous_source_revision == immutable_sha
    ):
        retained_path = _retained_framework_public_data_path(immutable_sha)
        if retained_path is not None:
            logger.warning(
                "Framework public dataset fetch was temporarily unavailable for "
                "unchanged commit %s; retaining the previously validated staged copy: %s",
                immutable_sha[:8],
                detail,
            )
            return FrameworkPublicDataStageResult(
                retained_path,
                status,
                detail,
                retained_previous=True,
            )

    _discard_staged_framework_public_data_file(immutable_sha)
    logger.warning(
        "Framework public schema discovery failed closed to '%s' for commit %s: %s",
        UNKNOWN_FRAMEWORK_SCHEMA_VERSION,
        immutable_sha[:8],
        detail or status.value,
    )
    return FrameworkPublicDataStageResult(None, status, detail)


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
                "User-Agent": "AIDEFEND-MCP-Service/1.0",
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
                extra={"file_name": safe_filename, "size": file_size},
            )

            return validated_path

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Failed to download {filename}: HTTP {e.response.status_code}",
            extra={"file_name": filename, "status_code": e.response.status_code},
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
                extra={"required": list(required_keys), "found": list(parsed_data.keys())},
            )
            return None

        logger.info(
            f"Parsed {file_path.name}",
            extra={
                "tactic": parsed_data.get("name"),
                "techniques": len(parsed_data.get("techniques", [])),
            },
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
                errors.append(f"{mapping_location}: mapping must contain framework and items")
            framework = mapping.get("framework")
            if not isinstance(framework, str) or not framework.strip():
                errors.append(f"{mapping_location}: framework must be a non-empty string")
            elif framework in seen_frameworks:
                errors.append(f"{mapping_location}: duplicate framework label '{framework}'")
            else:
                seen_frameworks.add(framework)
            items = mapping.get("items")
            if (
                not isinstance(items, list)
                or not items
                or not all(isinstance(item, str) and item.strip() for item in items)
            ):
                errors.append(f"{mapping_location}: items must be a non-empty array of strings")
            elif len(items) != len(set(items)):
                errors.append(f"{mapping_location}: items must not contain duplicates")
            elif any(NOT_APPLICABLE_PATTERN.fullmatch(item.strip()) for item in items) and (
                len(items) != 1 or not NOT_APPLICABLE_PATTERN.fullmatch(items[0].strip())
            ):
                errors.append(f"{mapping_location}: N/A must be the only mapping item")

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
            errors.append(f"{location}: implementationGuidance must be an array when present")
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
            for right_key in tool_keys[left_index + 1 :]:
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
                item for item in parent_items if not NOT_APPLICABLE_PATTERN.fullmatch(item)
            ]
            child_valid = [
                item for item in child_items if not NOT_APPLICABLE_PATTERN.fullmatch(item)
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
                    child_item == parent_item or child_item.startswith(f"{parent_item} (")
                    for parent_item in parent_valid
                ):
                    errors.append(
                        f"{parent_id}: {framework} parent union is missing "
                        f"child mapping '{child_item}'"
                    )
            for parent_item in parent_valid:
                if not any(
                    child_item == parent_item or child_item.startswith(f"{parent_item} (")
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
            if isinstance(key, str) and key.startswith("tools") and key not in AUTHORING_TOOL_FIELDS
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
                errors.append(
                    f"{technique_id}: parent techniques must have at least two sub-techniques"
                )
            if not technique.get("defendsAgainst"):
                errors.append(
                    f"{technique_id}: parent technique must define shared defendsAgainst mappings"
                )
            for forbidden_key in (
                "pillar",
                "phase",
                *AUTHORING_TOOL_FIELDS,
                "implementationGuidance",
            ):
                if forbidden_key in technique:
                    errors.append(
                        f"{technique_id}: parent technique must not define {forbidden_key}"
                    )

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
        sections = parsed.get("sections", [])
        if not isinstance(sections, list):
            logger.warning(f"aidefend-intro.js 'sections' is not a list")
            return None

        for section in sections:
            if not isinstance(section, dict):
                continue

            title = section.get("title", "")
            if title == "Version & Date":
                paragraphs = section.get("paragraphs", [])

                if not isinstance(paragraphs, list):
                    continue

                for para in paragraphs:
                    if isinstance(para, str) and para.strip().startswith("Version:"):
                        # Extract version number after "Version:"
                        version = para.split(":", 1)[1].strip()
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
                soup_check = BeautifulSoup(how_to, "html.parser")
                if soup_check.find_all(["pre", "code"]):
                    tech_has_code = True
                    break

        # Document for technique
        tech_text = f"Technique: {tech_name}\nID: {tech_id}"

        # Keep ownership boundaries near the start of the embedding input. The
        # framework mappings and warnings can be long enough to push this
        # schema-2.3 metadata beyond the embedding model's token window.
        scope_text = _scope_boundary_responsibility_to_search_text(tech_scope_boundary)
        scope_relationships_text = _scope_boundary_relationships_to_search_text(tech_scope_boundary)
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

        documents.append(
            {
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
            }
        )

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
                    soup_check = BeautifulSoup(how_to, "html.parser")
                    if soup_check.find_all(["pre", "code"]):
                        has_code = True
                        break

            sub_text = f"Sub-Technique: {sub_name}\n" f"ID: {sub_id}"

            scope_text = _scope_boundary_responsibility_to_search_text(sub_scope_boundary)
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

            documents.append(
                {
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
                }
            )

            # Documents for implementation strategies
            for i, strategy in enumerate(sub_tech.get("implementationGuidance", []), 1):
                strategy_name = strategy.get("implementation", "Implementation")
                how_to_html = strategy.get("howTo", "")

                # For embedding text: Use BeautifulSoup to safely remove HTML
                soup = BeautifulSoup(how_to_html, "html.parser")

                # Check if this strategy has code (before removing tags)
                has_code = bool(soup.find_all(["pre", "code"]))

                # Remove code tags - we don't want code in the embedding text
                for code_tag in soup.find_all(["pre", "code"]):
                    code_tag.decompose()

                # Get clean text
                clean_how_to = soup.get_text(separator=" ", strip=True)

                strategy_id = _guidance_document_id(sub_id, strategy, i)
                strategy_text = f"Implementation Guidance: {strategy_name}\n" f"ID: {strategy_id}"

                scope_text = _scope_boundary_responsibility_to_search_text(sub_scope_boundary)
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
                    strategy_text += f"\nScope Relationships: {scope_relationships_text}"

                documents.append(
                    {
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
                    }
                )

        # Standalone techniques need their own strategy documents.
        if not technique.get("subTechniques", []):
            for i, strategy in enumerate(tech_implementation_strategies, 1):
                strategy_name = strategy.get("implementation", "Implementation")
                how_to_html = strategy.get("howTo", "")

                soup = BeautifulSoup(how_to_html, "html.parser")
                has_code = bool(soup.find_all(["pre", "code"]))

                for code_tag in soup.find_all(["pre", "code"]):
                    code_tag.decompose()

                clean_how_to = soup.get_text(separator=" ", strip=True)
                strategy_id = _guidance_document_id(tech_id, strategy, i)
                strategy_text = f"Implementation Guidance: {strategy_name}\n" f"ID: {strategy_id}"

                scope_text = _scope_boundary_responsibility_to_search_text(tech_scope_boundary)
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
                    strategy_text += f"\nScope Relationships: {scope_relationships_text}"

                documents.append(
                    {
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
                    }
                )

    logger.info(
        f"Extracted {len(documents)} documents from {tactic_name}",
        extra={"tactic": tactic_name, "doc_count": len(documents)},
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
        logger.info(
            "Registering custom model for sync: Xenova/multilingual-e5-base (Quantized Int8)"
        )
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
            additional_files=[],
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


def _generation_activation_marker_path() -> Path:
    """Return the transaction marker beside the atomic version snapshot."""
    return settings.VERSION_FILE.with_name(GENERATION_ACTIVATION_MARKER_FILENAME)


def _load_version_info_strict() -> Optional[Dict[str, Any]]:
    """Read transaction metadata without collapsing operational I/O failures.

    Missing or structurally invalid metadata is deterministic identity evidence;
    an ``OSError`` is retryable and deliberately propagates so recovery retains
    the marker and every table/sidecar byte for the next attempt.
    """
    version_path = settings.VERSION_FILE
    if version_path.is_symlink():
        raise GenerationIdentityError("Generation version metadata path is not a regular file")
    try:
        raw = version_path.read_bytes()
    except FileNotFoundError:
        return None
    except IsADirectoryError as exc:
        raise GenerationIdentityError(
            "Generation version metadata path is not a regular file"
        ) from exc
    if not raw or len(raw) > MAX_GENERATION_VERSION_METADATA_BYTES:
        raise GenerationIdentityError("Generation version metadata has an invalid size")

    def reject_duplicate_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise GenerationIdentityError(f"Generation version metadata duplicates key {key!r}")
            value[key] = item
        return value

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                GenerationIdentityError(
                    f"Generation version metadata contains non-finite value {value!r}"
                )
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GenerationIdentityError(
            "Generation version metadata is not valid UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise GenerationIdentityError("Generation version metadata must be a JSON object")
    return payload


def _assert_json_payload_size(
    payload: Mapping[str, Any],
    *,
    maximum_bytes: int,
    label: str,
) -> int:
    """Preflight the same formatted JSON shape used by the atomic writer."""
    try:
        encoded = json.dumps(
            dict(payload),
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GenerationIdentityError(f"{label} is not canonical JSON") from exc
    size = len(encoded)
    if size < 1 or size > maximum_bytes:
        raise GenerationIdentityError(
            f"{label} exceeds its recovery-reader size limit " f"({size} > {maximum_bytes} bytes)"
        )
    return size


def _write_generation_version_snapshot(version_info: Mapping[str, Any]) -> None:
    """Validate and durably write a recovery-readable version snapshot."""
    _assert_json_payload_size(
        version_info,
        maximum_bytes=MAX_GENERATION_VERSION_METADATA_BYTES,
        label="Generation version metadata",
    )
    _atomic_write_json(settings.VERSION_FILE, dict(version_info))


def _open_generation_table(table_path: Path):
    """Open one known transaction table without accepting an arbitrary path."""
    table_path = Path(table_path)
    expected_parent = settings.DB_PATH.resolve(strict=False)
    if table_path.parent.resolve(strict=False) != expected_parent:
        raise GenerationIdentityError("Generation table is outside the database root")
    if not re.fullmatch(
        r"aidefend(?:_new_sync|_backup(?:_\d+)?)?\.lance",
        table_path.name,
    ):
        raise GenerationIdentityError(f"Unsafe generation table name: {table_path.name!r}")
    if not table_path.is_dir() or table_path.is_symlink():
        raise GenerationIdentityError(f"Generation table is missing or unsafe: {table_path.name}")
    db = lancedb.connect(str(settings.DB_PATH))
    return db.open_table(table_path.name.removesuffix(".lance"))


def _assert_table_path_generation(
    table_path: Path,
    version_info: Mapping[str, Any],
    *,
    allow_legacy_unbound: bool = False,
) -> Optional[str]:
    table = _open_generation_table(table_path)
    return assert_table_generation(
        table,
        version_info,
        allow_legacy_unbound=allow_legacy_unbound,
    )


def _backup_metadata_path(table_path: Path) -> Path:
    """Return the exact metadata sidecar paired with a retained table."""
    if not re.fullmatch(r"aidefend_backup(?:_\d+)?\.lance", table_path.name):
        raise GenerationIdentityError(f"Unsafe backup table name: {table_path.name!r}")
    return table_path.with_suffix(".version.json")


def _bind_declared_backup_version(
    version_info: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate a current or legacy snapshot that is already table-bound."""
    if GENERATION_ID_FIELD not in version_info:
        raise GenerationIdentityError(
            "Rollback metadata is not bound to a persisted table generation"
        )
    return bind_version_generation(version_info, allow_legacy=True)


def _write_backup_metadata(
    table_path: Path,
    version_info: Mapping[str, Any],
) -> Path:
    """Durably save the version snapshot that belongs to ``table_path``."""
    bound = _bind_declared_backup_version(version_info)
    metadata_path = _backup_metadata_path(table_path)
    payload = {
        "schema_version": GENERATION_BACKUP_METADATA_SCHEMA,
        "table": table_path.name,
        "generation_id": bound[GENERATION_ID_FIELD],
        "version_info": bound,
    }
    _assert_json_payload_size(
        payload,
        maximum_bytes=MAX_GENERATION_BACKUP_METADATA_BYTES,
        label="Generation backup metadata",
    )
    _atomic_write_json(metadata_path, payload)
    return metadata_path


def _load_backup_metadata(table_path: Path) -> Dict[str, Any]:
    """Load and validate a backup's exact paired version snapshot."""
    metadata_path = _backup_metadata_path(table_path)
    if not metadata_path.is_file() or metadata_path.is_symlink():
        raise GenerationIdentityError(
            f"Backup {table_path.name} has no safe paired version metadata"
        )
    raw = metadata_path.read_bytes()
    if not raw or len(raw) > MAX_GENERATION_BACKUP_METADATA_BYTES:
        raise GenerationIdentityError(f"Backup metadata for {table_path.name} has an invalid size")

    def reject_duplicate_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise GenerationIdentityError(f"Backup metadata duplicates key {key!r}")
            value[key] = item
        return value

    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                GenerationIdentityError(f"Backup metadata contains non-finite value {value!r}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GenerationIdentityError(
            f"Backup metadata for {table_path.name} is not valid UTF-8 JSON"
        ) from exc

    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "table",
        "generation_id",
        "version_info",
    }:
        raise GenerationIdentityError("Backup metadata fields are invalid")
    if payload["schema_version"] != GENERATION_BACKUP_METADATA_SCHEMA:
        raise GenerationIdentityError("Backup metadata schema is unsupported")
    if payload["table"] != table_path.name:
        raise GenerationIdentityError("Backup metadata names a different table")
    declared = payload["generation_id"]
    if not isinstance(declared, str) or GENERATION_ID_PATTERN.fullmatch(declared) is None:
        raise GenerationIdentityError("Backup generation_id is invalid")
    version_info = payload["version_info"]
    bound = _bind_declared_backup_version(version_info)
    if bound[GENERATION_ID_FIELD] != declared:
        raise GenerationIdentityError(
            "Backup metadata generation_id does not match its version fingerprint"
        )
    return bound


def _bind_existing_active_generation(
    active_path: Path,
    version_info: Mapping[str, Any],
) -> Dict[str, Any]:
    """One-time bind a pre-3.3 active table before it can become a backup.

    The Lance column is committed first.  If the process stops before the
    metadata replacement, the persisted table ID is still independently
    derivable from the unchanged legacy metadata and the next startup can
    safely finish the metadata augmentation.
    """
    bound = bind_version_generation(version_info, allow_legacy=True)
    table = _open_generation_table(active_path)
    verified = assert_table_generation(
        table,
        version_info,
        allow_legacy_unbound=True,
    )
    if verified is None:
        generation = bound[GENERATION_ID_FIELD]
        table.add_columns({GENERATION_ID_FIELD: f"'{generation}'"})
        assert_table_generation(table, bound, allow_legacy_unbound=False)
        logger.info(
            "Bound legacy active table to generation %s before upgrade",
            generation[:12],
        )

    # Also completes the recoverable table-first transition after a process
    # interruption between add_columns() and the atomic metadata replacement.
    if version_info.get(GENERATION_ID_FIELD) != bound[GENERATION_ID_FIELD]:
        _write_generation_version_snapshot(bound)
    _assert_table_path_generation(active_path, bound)
    return bound


def _write_generation_activation_marker(
    *,
    commit_sha: str,
    version_metadata: Mapping[str, Any],
    backup_table: Optional[str],
    backup_metadata: Optional[str] = None,
    previous_generation_id: Optional[str] = None,
    staged_table: str,
) -> Dict[str, Any]:
    """Durably record enough state to recover any interrupted table activation."""
    final_version = bind_version_generation(
        {"commit_sha": commit_sha, **dict(version_metadata)},
        allow_legacy=False,
    )
    fingerprint = _generation_fingerprint(final_version)
    if backup_table is not None and not re.fullmatch(
        r"aidefend_backup(?:_\d+)?\.lance", backup_table
    ):
        raise RuntimeError(f"Unsafe generation backup table name: {backup_table!r}")
    if backup_metadata is not None and not re.fullmatch(
        r"aidefend_backup(?:_\d+)?\.version\.json", backup_metadata
    ):
        raise RuntimeError(f"Unsafe generation backup metadata name: {backup_metadata!r}")
    if (backup_table is None) != (backup_metadata is None):
        raise RuntimeError("Generation backup table and metadata must be recorded together")
    if backup_table is not None and (
        Path(backup_table).with_suffix(".version.json").name != backup_metadata
    ):
        raise RuntimeError("Generation backup table and metadata names do not pair")
    if previous_generation_id is not None and (
        not isinstance(previous_generation_id, str)
        or GENERATION_ID_PATTERN.fullmatch(previous_generation_id) is None
    ):
        raise RuntimeError("Previous generation_id is invalid")
    if (backup_table is None) != (previous_generation_id is None):
        raise RuntimeError("Generation backup evidence and previous generation_id must agree")
    if not re.fullmatch(r"aidefend_new_sync\.lance", staged_table):
        raise RuntimeError(f"Unsafe staged table name: {staged_table!r}")

    marker = {
        "schema_version": GENERATION_ACTIVATION_MARKER_SCHEMA,
        "generation_id": final_version[GENERATION_ID_FIELD],
        "expected_version": fingerprint,
        "previous_generation_id": previous_generation_id,
        "backup_table": backup_table,
        "backup_metadata": backup_metadata,
        "staged_table": staged_table,
    }
    _assert_json_payload_size(
        marker,
        maximum_bytes=MAX_GENERATION_ACTIVATION_MARKER_BYTES,
        label="Generation activation marker",
    )
    _atomic_write_json(_generation_activation_marker_path(), marker)
    logger.info(
        "Prepared database generation transaction %s",
        marker["generation_id"][:12],
    )
    return marker


def _load_generation_activation_marker() -> Optional[Dict[str, Any]]:
    """Load and strictly validate an interrupted activation marker."""
    marker_path = _generation_activation_marker_path()
    if marker_path.is_symlink():
        raise RuntimeError("Generation activation marker must not be a symbolic link")
    if marker_path.is_dir():
        raise RuntimeError("Generation activation marker must be a regular file")
    try:
        raw = marker_path.read_bytes()
    except FileNotFoundError:
        return None
    except IsADirectoryError as exc:
        raise RuntimeError("Generation activation marker must be a regular file") from exc
    if not raw or len(raw) > MAX_GENERATION_ACTIVATION_MARKER_BYTES:
        raise RuntimeError("Generation activation marker has an invalid size")

    def reject_duplicate_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise RuntimeError(f"Generation activation marker duplicates key {key!r}")
            value[key] = item
        return value

    try:
        marker = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Generation activation marker is not valid UTF-8 JSON") from exc
    if not isinstance(marker, dict) or set(marker) != {
        "schema_version",
        "generation_id",
        "expected_version",
        "previous_generation_id",
        "backup_table",
        "backup_metadata",
        "staged_table",
    }:
        raise RuntimeError("Generation activation marker fields are invalid")
    if marker.get("schema_version") != GENERATION_ACTIVATION_MARKER_SCHEMA:
        raise RuntimeError("Generation activation marker schema is unsupported")
    expected = marker.get("expected_version")
    if not isinstance(expected, dict) or not expected:
        raise RuntimeError("Generation activation marker fingerprint is invalid")
    if set(expected) - set(GENERATION_FINGERPRINT_FIELDS):
        raise RuntimeError("Generation activation marker fingerprint has unknown fields")
    generation_id = marker.get("generation_id")
    if (
        not isinstance(generation_id, str)
        or not re.fullmatch(r"[0-9a-f]{64}", generation_id)
        or generation_id != _generation_id(expected)
    ):
        raise RuntimeError("Generation activation marker digest does not match")
    backup_table = marker.get("backup_table")
    if backup_table is not None and (
        not isinstance(backup_table, str)
        or not re.fullmatch(r"aidefend_backup(?:_\d+)?\.lance", backup_table)
    ):
        raise RuntimeError("Generation activation marker backup name is unsafe")
    backup_metadata = marker.get("backup_metadata")
    if backup_metadata is not None and (
        not isinstance(backup_metadata, str)
        or not re.fullmatch(
            r"aidefend_backup(?:_\d+)?\.version\.json",
            backup_metadata,
        )
    ):
        raise RuntimeError("Generation activation marker backup metadata is unsafe")
    if (backup_table is None) != (backup_metadata is None):
        raise RuntimeError("Generation activation marker backup evidence is incomplete")
    if backup_table is not None and (
        Path(backup_table).with_suffix(".version.json").name != backup_metadata
    ):
        raise RuntimeError("Generation activation marker backup evidence does not pair")
    previous_generation_id = marker.get("previous_generation_id")
    if previous_generation_id is not None and (
        not isinstance(previous_generation_id, str)
        or GENERATION_ID_PATTERN.fullmatch(previous_generation_id) is None
    ):
        raise RuntimeError("Generation activation marker previous ID is invalid")
    if (backup_table is None) != (previous_generation_id is None):
        raise RuntimeError("Generation activation marker previous evidence is incomplete")
    if marker.get("staged_table") != "aidefend_new_sync.lance":
        raise RuntimeError("Generation activation marker staged name is unsafe")
    return marker


def _remove_generation_activation_marker() -> None:
    marker_path = _generation_activation_marker_path()
    _durable_unlink(marker_path, missing_ok=True)


def _unlink_transaction_artifact_best_effort(path: Optional[Path]) -> None:
    """Remove non-authoritative transaction debris without failing recovery."""
    if path is None:
        return
    try:
        _durable_unlink(path, missing_ok=True)
    except OSError as exc:
        logger.warning(
            "Could not remove transaction artifact %s; it will be retried by "
            "a later successful cleanup: %s",
            path.name,
            exc,
        )


def _cleanup_durable_tombstones_best_effort() -> None:
    """Bound cleanup of harmless write-through deletion tombstones.

    Only exact regular-file names emitted by ``_durable_unlink`` are eligible.
    Directories, symlinks, unknown names, and anything beyond the bounded scan
    are retained rather than broadening deletion scope.
    """
    # VERSION_FILE may be explicitly placed in a nested directory under the
    # locked DATA_PATH.  Its write-through marker tombstones are emitted in
    # VERSION_FILE.parent, while table-sidecar tombstones live beside DB_PATH.
    # Canonicalize first so aliased configured paths do not consume the bounded
    # scan more than once.
    roots = []
    for configured_root in (
        settings.DATA_PATH,
        settings.DB_PATH,
        settings.VERSION_FILE.parent,
    ):
        try:
            canonical_root = Path(configured_root).resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            logger.warning(
                "Could not canonicalize transaction tombstone root %s: %s",
                configured_root,
                exc,
            )
            continue
        if canonical_root not in roots:
            roots.append(canonical_root)
    examined = 0
    for root in roots:
        try:
            candidates = sorted(root.iterdir(), key=lambda path: path.name)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError as exc:
            logger.warning("Could not inspect transaction tombstones in %s: %s", root, exc)
            continue

        for candidate in candidates:
            if _DURABLE_TOMBSTONE_PATTERN.fullmatch(candidate.name) is None:
                continue
            examined += 1
            if examined > MAX_DURABLE_TOMBSTONES_PER_CLEANUP:
                return
            try:
                candidate_mode = os.lstat(candidate).st_mode
                if not stat.S_ISREG(candidate_mode):
                    logger.warning(
                        "Refusing to remove non-regular transaction tombstone %s",
                        candidate,
                    )
                    continue
                os.unlink(candidate)
            except FileNotFoundError:
                continue
            except OSError as exc:
                logger.warning(
                    "Could not remove retained transaction tombstone %s: %s",
                    candidate,
                    exc,
                )


async def _quarantine_generation_table(table_path: Path, stem: str) -> Optional[Path]:
    if not table_path.exists():
        return None
    failed_path = _unique_table_artifact(stem)
    # Same-volume rename is the transaction boundary.  Do not dispatch it to
    # a cancellable executor future: cancelling the coroutine cannot stop the
    # worker, so rollback could observe the pre-rename state and then have the
    # worker mutate it after the marker was removed.
    _durable_rename(table_path, failed_path)
    return failed_path


async def _restore_backup_generation(
    backup_path: Path,
    active_path: Path,
    guarded_engine: Any,
    *,
    expected_generation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Restore one proven table/version pair while the writer lock is held."""
    version_info = _load_backup_metadata(backup_path)
    generation = _assert_table_path_generation(backup_path, version_info)
    if expected_generation_id is not None and generation != expected_generation_id:
        raise GenerationIdentityError(
            f"Backup {backup_path.name} does not match the marker-bound generation"
        )
    if active_path.exists():
        raise GenerationIdentityError("Active table must be quarantined before rollback")

    try:
        # Commit the paired metadata while no active table is present, then do
        # the same-volume rename. A crash between these steps leaves
        # version=old + backup=old + marker, which startup can retry without a
        # split active table/version generation.
        _write_generation_version_snapshot(version_info)
        _durable_rename(backup_path, active_path)
        if not await guarded_engine._do_initialize(expected_version_info=version_info):
            raise RuntimeError(f"Rollback table {backup_path.name} failed initialization")
        durable_version = _load_version_info_strict()
        if not isinstance(durable_version, Mapping):
            raise GenerationIdentityError("Rollback version metadata is not durable")
        durable_bound = _bind_declared_backup_version(durable_version)
        if durable_bound[GENERATION_ID_FIELD] != generation:
            raise GenerationIdentityError("Rollback version metadata changed during activation")
        _assert_table_path_generation(active_path, durable_bound)
    except BaseException as restore_error:
        guarded_engine._reset_database_handles_locked()
        # The candidate was cryptographically verified before the rename.  An
        # operational metadata/model/I/O failure must not consume that LKG;
        # return it to its exact paired backup path so startup can retry.
        if active_path.exists() and not backup_path.exists():
            try:
                _durable_rename(active_path, backup_path)
            except BaseException as retain_error:
                if isinstance(restore_error, asyncio.CancelledError):
                    raise restore_error from retain_error
                raise RuntimeError(
                    f"Verified rollback generation {backup_path.name} could "
                    "not be retained after activation failure"
                ) from retain_error
        if isinstance(restore_error, asyncio.CancelledError):
            raise
        raise GenerationRestoreRetryableError(
            f"Verified rollback generation {backup_path.name} could not be activated"
        ) from restore_error
    else:
        return version_info


async def _activate_staged_database(
    new_sync_path: Path,
    *,
    version_commit: Optional[Tuple[str, Mapping[str, Any]]] = None,
) -> None:
    """Activate a staged table and preserve every usable rollback generation.

    A process can stop at any filesystem rename or between active-table
    initialization and the durable version write. Existing backups are never
    assumed stale here: the immediately previous active table is saved under a
    new path, and rollback tries each retained generation until one initializes.
    When ``version_commit`` is supplied, the physical table, migration registry,
    and version/provenance snapshot are committed while the same writer guard is
    held. A durable marker lets startup distinguish a committed generation from
    any interruption point and recover the exact previous table.
    """
    if version_commit is None:
        raise RuntimeError("A staged table cannot be activated without atomic version metadata")

    commit_sha, raw_version_metadata = version_commit
    final_version = bind_version_generation(
        {"commit_sha": commit_sha, **dict(raw_version_metadata)},
        allow_legacy=False,
    )
    version_metadata = {key: value for key, value in final_version.items() if key != "commit_sha"}
    _assert_json_payload_size(
        {
            "commit_sha": commit_sha,
            "last_synced_at": "9999-12-31T23:59:59.999999+00:00",
            "sync_timestamp": 253402300799.999999,
            **version_metadata,
        },
        maximum_bytes=MAX_GENERATION_VERSION_METADATA_BYTES,
        label="Generation version metadata",
    )

    aidefend_path = settings.DB_PATH / "aidefend.lance"
    backup_candidates = _existing_backup_artifacts()
    current_backup_path: Optional[Path] = None
    current_backup_metadata_path: Optional[Path] = None
    previous_version: Optional[Dict[str, Any]] = None
    restored_backup_metadata_path: Optional[Path] = None
    activated_new = False
    activation_marker: Optional[Dict[str, Any]] = None

    if not new_sync_path.exists():
        raise RuntimeError(f"Staged database table is missing: {new_sync_path}")
    staged_generation = _assert_table_path_generation(
        new_sync_path,
        final_version,
    )
    if staged_generation != final_version[GENERATION_ID_FIELD]:
        raise GenerationIdentityError("Staged table generation does not match its version metadata")

    from app.core import query_engine

    async with query_engine.database_write_guard() as guarded_engine:
        guarded_engine._reset_database_handles_locked()
        logger.info("Query engine paused for database swap")

        try:
            if aidefend_path.exists():
                current_version = _load_version_info_strict()
                try:
                    if not isinstance(current_version, Mapping):
                        raise GenerationIdentityError(
                            "Existing active table has no usable version metadata"
                        )
                    previous_version = _bind_existing_active_generation(
                        aidefend_path,
                        current_version,
                    )
                except GenerationIdentityError as legacy_error:
                    # An old installation without enough provenance cannot be
                    # promoted to a rollback candidate.  The already-verified
                    # staged generation may still be activated safely; move the
                    # unprovable table out of service first and continue with a
                    # no-backup marker.  If the staged table then fails, startup
                    # sees no active table and performs a clean rebuild.
                    guarded_engine._reset_database_handles_locked()
                    failed_legacy = await _quarantine_generation_table(
                        aidefend_path,
                        "aidefend_failed_generation",
                    )
                    previous_version = None
                    current_backup_path = None
                    current_backup_metadata_path = None
                    logger.warning(
                        "Quarantined an unbindable legacy active table as %s; "
                        "continuing with verified staged generation: %s",
                        (failed_legacy.name if failed_legacy is not None else "unknown"),
                        legacy_error,
                    )
                else:
                    current_backup_path = _unique_table_artifact("aidefend_backup")
                    # Operational failures while preparing the sidecar (for
                    # example disk-full or permission errors) must abort before
                    # any rename and retain the proven active generation. They
                    # are not evidence that the active table itself is invalid.
                    current_backup_metadata_path = _write_backup_metadata(
                        current_backup_path,
                        previous_version,
                    )

            activation_marker = _write_generation_activation_marker(
                commit_sha=commit_sha,
                version_metadata=version_metadata,
                backup_table=(
                    current_backup_path.name if current_backup_path is not None else None
                ),
                backup_metadata=(
                    current_backup_metadata_path.name
                    if current_backup_metadata_path is not None
                    else None
                ),
                previous_generation_id=(
                    previous_version[GENERATION_ID_FIELD] if previous_version is not None else None
                ),
                staged_table=new_sync_path.name,
            )

            if aidefend_path.exists():
                _durable_rename(aidefend_path, current_backup_path)
                logger.info(f"Retained previous active table as {current_backup_path.name}")

            _durable_rename(new_sync_path, aidefend_path)
            activated_new = True
            logger.info("Atomic swap complete: aidefend_new_sync -> aidefend")

            if not await guarded_engine._do_initialize(expected_version_info=final_version):
                raise RuntimeError("QueryEngine rejected the newly swapped database")

            try:
                save_version_info(commit_sha, dict(version_metadata))
            except BaseException as metadata_error:
                # Atomic replacement can succeed even if a wrapper raises just
                # after os.replace().  Retain it only when both durable objects
                # independently prove the marker-bound generation.
                committed_version = _load_version_info_strict()
                try:
                    if not isinstance(committed_version, Mapping):
                        raise GenerationIdentityError("Committed version metadata is unavailable")
                    committed_bound = bind_version_generation(
                        committed_version,
                        allow_legacy=False,
                    )
                    if (
                        activation_marker is None
                        or committed_bound[GENERATION_ID_FIELD]
                        != activation_marker["generation_id"]
                        or _generation_fingerprint(committed_bound)
                        != activation_marker["expected_version"]
                    ):
                        raise GenerationIdentityError(
                            "Committed version does not match activation marker"
                        )
                    _assert_table_path_generation(
                        aidefend_path,
                        committed_bound,
                    )
                except GenerationIdentityError:
                    raise metadata_error
                logger.warning(
                    "Version writer raised after the expected table/version pair "
                    "was durably visible; retaining generation %s: %s",
                    activation_marker["generation_id"][:12],
                    metadata_error,
                )
            else:
                committed_version = _load_version_info_strict()
                if not isinstance(committed_version, Mapping):
                    raise GenerationIdentityError("Committed version metadata is unavailable")
                committed_bound = bind_version_generation(
                    committed_version,
                    allow_legacy=False,
                )
                if (
                    committed_bound[GENERATION_ID_FIELD] != activation_marker["generation_id"]
                    or _generation_fingerprint(committed_bound)
                    != activation_marker["expected_version"]
                ):
                    raise GenerationIdentityError(
                        "Committed version does not match activation marker"
                    )
                _assert_table_path_generation(aidefend_path, committed_bound)

            logger.info(
                "Committed database and version metadata as generation %s",
                activation_marker["generation_id"][:12],
            )
            try:
                _remove_generation_activation_marker()
            except OSError as marker_error:
                # Both durable objects already agree. Startup re-verifies the
                # table ID and metadata before removing a retained marker.
                logger.warning(
                    "Committed generation marker could not be removed: %s",
                    marker_error,
                )

        except BaseException as swap_error:
            logger.error(f"Database swap failed: {swap_error}. Attempting rollback...")
            guarded_engine._reset_database_handles_locked()

            # Nothing was renamed when preparation failed before the durable
            # marker was created.  Keep the existing active bytes in place;
            # transient legacy-metadata or sidecar I/O failures are not proof
            # that the last-known-good table is invalid.
            if (
                activation_marker is None
                and not _generation_activation_marker_path().exists()
                and aidefend_path.exists()
            ):
                await guarded_engine._do_initialize()
                _unlink_transaction_artifact_best_effort(current_backup_metadata_path)
                raise

            rollback_error: Optional[BaseException] = None
            rollback_cancellation: Optional[asyncio.CancelledError] = None
            try:
                restored = False

                async def quarantine_active() -> None:
                    await _quarantine_generation_table(
                        aidefend_path,
                        "aidefend_failed_sync",
                    )

                if activated_new:
                    await quarantine_active()
                elif aidefend_path.exists():
                    # If active->backup itself failed, retain it only when the
                    # table and durable metadata still prove the same ID.
                    durable_version = _load_version_info_strict()
                    active_pair_proven = False
                    try:
                        if not isinstance(durable_version, Mapping):
                            raise GenerationIdentityError("Active rollback metadata is unavailable")
                        # A pre-3.3 table can be left table-bound but with its
                        # legacy metadata unchanged when the one-time metadata
                        # augmentation hits a transient I/O failure.  It is
                        # still independently provable and must remain the LKG.
                        durable_bound = bind_version_generation(
                            durable_version,
                            allow_legacy=True,
                        )
                        _assert_table_path_generation(
                            aidefend_path,
                            durable_bound,
                            allow_legacy_unbound=True,
                        )
                        active_pair_proven = True
                        restored = await guarded_engine._do_initialize(
                            expected_version_info=(
                                durable_bound if GENERATION_ID_FIELD in durable_version else None
                            )
                        )
                    except GenerationIdentityError:
                        active_pair_proven = False
                        restored = False
                    except asyncio.CancelledError as cancellation:
                        if active_pair_proven:
                            restored = True
                            rollback_cancellation = cancellation
                        else:
                            raise
                    except BaseException:
                        # Operational initialization failure is not evidence
                        # that a generation-consistent LKG should be moved.
                        if active_pair_proven:
                            restored = True
                        else:
                            raise
                    if active_pair_proven and not restored:
                        # _do_initialize reports operational/model failures as
                        # False. Preserve the proven pair and leave the engine
                        # offline; a later startup can retry without data loss.
                        logger.warning(
                            "The previous active generation remains proven, "
                            "but QueryEngine reinitialization failed"
                        )
                        restored = True
                    if not active_pair_proven:
                        guarded_engine._reset_database_handles_locked()
                        await quarantine_active()

                if not restored:
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
                        try:
                            if aidefend_path.exists():
                                await quarantine_active()
                            await _restore_backup_generation(
                                candidate,
                                aidefend_path,
                                guarded_engine,
                                expected_generation_id=(
                                    activation_marker.get("previous_generation_id")
                                    if (
                                        activation_marker is not None
                                        and current_backup_path is not None
                                        and candidate == current_backup_path
                                    )
                                    else None
                                ),
                            )
                            restored_backup_metadata_path = _backup_metadata_path(candidate)
                            restored = True
                        except (
                            GenerationIdentityError,
                            GenerationRestoreRetryableError,
                        ) as candidate_error:
                            guarded_engine._reset_database_handles_locked()
                            logger.error(
                                "Rollback candidate %s remains retained but was "
                                "not selected: %s",
                                candidate.name,
                                candidate_error,
                            )
                            restored = False
                        except BaseException:
                            # The candidate could not even be returned to its
                            # verified backup path. Stop before touching any
                            # older generation.
                            raise
                        if restored:
                            logger.info(f"Rollback successful using {candidate.name}")
                            break

                if (
                    aidefend_path.exists() or current_backup_path is not None or backup_candidates
                ) and not restored:
                    raise RuntimeError(
                        "no retained table/version generation could be verified and initialized"
                    )
            except BaseException as exc:
                rollback_error = exc
                logger.error(
                    f"Rollback also failed: {exc}. Manual intervention required.",
                    exc_info=True,
                )

            if rollback_error is None:
                marker_removed = False
                try:
                    _remove_generation_activation_marker()
                    marker_removed = True
                except OSError as marker_error:
                    logger.warning(
                        "Rolled-back generation marker could not be removed: %s",
                        marker_error,
                    )
                if marker_removed:
                    if restored_backup_metadata_path is not None:
                        _unlink_transaction_artifact_best_effort(restored_backup_metadata_path)
                    elif (
                        current_backup_metadata_path is not None
                        and current_backup_path is not None
                        and not current_backup_path.exists()
                    ):
                        _unlink_transaction_artifact_best_effort(current_backup_metadata_path)

            if rollback_error is not None:
                if isinstance(rollback_error, asyncio.CancelledError):
                    raise rollback_error from swap_error
                if isinstance(swap_error, asyncio.CancelledError):
                    raise swap_error from rollback_error
                raise RuntimeError(
                    f"Database swap failed ({swap_error}); rollback also "
                    f"failed ({rollback_error})"
                ) from rollback_error
            if rollback_cancellation is not None:
                raise rollback_cancellation from swap_error
            raise


async def _recover_incomplete_generation_activation_locked() -> bool:
    """Recover or take offline a DB generation interrupted by process death.

    The caller must hold the cross-process sync lock for the complete call.
    Returns ``True`` when a pending marker was handled. A committed generation
    is retained only when its atomic version snapshot exactly matches the marker
    fingerprint. Otherwise the marker-named previous table is restored; if that
    proof is unavailable, the uncertain active table is quarantined so startup
    performs a clean rebuild instead of serving a split DB/registry generation.
    """
    marker: Optional[Dict[str, Any]] = None
    marker_error: Optional[BaseException] = None
    try:
        marker = _load_generation_activation_marker()
    except (asyncio.CancelledError, OSError):
        # Operational reads are retryable. Do not mutate any table, sidecar, or
        # marker when the transaction record cannot be read conclusively.
        raise
    except Exception as exc:
        marker_error = exc
        logger.error(
            "Generation activation marker is invalid; active data will fail closed: %s",
            exc,
        )

    # A marker can disappear between the cheap existence check and the read
    # (for example, manual cleanup outside this process).  Absence is not an
    # invalid transaction and must never fall through to quarantine the active
    # generation.  Legitimate writers cannot cause this race because the
    # caller holds the shared cross-process sync lock.
    if marker is None and marker_error is None:
        return False

    active_path = settings.DB_PATH / "aidefend.lance"
    backup_path: Optional[Path] = None
    if marker is not None and marker.get("backup_table"):
        backup_path = settings.DB_PATH / marker["backup_table"]

    if marker is not None:
        version_info = _load_version_info_strict()
        try:
            if not isinstance(version_info, Mapping):
                raise GenerationIdentityError("Active version metadata is unavailable")
            bound_version = bind_version_generation(
                version_info,
                allow_legacy=False,
            )
            if (
                bound_version[GENERATION_ID_FIELD] != marker["generation_id"]
                or _generation_fingerprint(bound_version) != marker["expected_version"]
            ):
                raise GenerationIdentityError(
                    "Active version metadata does not match the pending generation"
                )
            _assert_table_path_generation(active_path, bound_version)
        except GenerationIdentityError as proof_error:
            logger.warning(
                "Pending committed-generation proof failed; evaluating rollback: %s",
                proof_error,
            )
        else:
            logger.warning(
                "Recovered fully committed table/version generation %s after "
                "an interrupted marker cleanup",
                marker["generation_id"][:12],
            )
            try:
                _remove_generation_activation_marker()
            except OSError as exc:
                logger.warning(
                    "Committed generation marker remains and will be retried: %s",
                    exc,
                )
            return True

        # Compatibility recovery for an interruption from an older transaction
        # order: backup->active completed, its sidecar remains, but VERSION_FILE
        # still names the new generation. The sidecar can independently prove
        # that the active table is the marker-bound previous generation.
        if (
            active_path.exists()
            and backup_path is not None
            and not backup_path.exists()
            and (
                not isinstance(version_info, Mapping)
                or version_info.get(GENERATION_ID_FIELD) != marker["previous_generation_id"]
            )
        ):
            try:
                sidecar_version = _load_backup_metadata(backup_path)
                if sidecar_version[GENERATION_ID_FIELD] != marker["previous_generation_id"]:
                    raise GenerationIdentityError("Consumed backup sidecar is not marker-bound")
                _assert_table_path_generation(active_path, sidecar_version)
            except GenerationIdentityError as proof_error:
                logger.warning(
                    "Consumed-backup active proof failed; evaluating other "
                    "rollback evidence: %s",
                    proof_error,
                )
            else:
                from app.core import query_engine

                async with query_engine.database_write_guard() as guarded_engine:
                    guarded_engine._reset_database_handles_locked()
                    _write_generation_version_snapshot(sidecar_version)
                    if not await guarded_engine._do_initialize(
                        expected_version_info=sidecar_version
                    ):
                        raise GenerationRestoreRetryableError(
                            "Marker-bound active LKG could not be initialized"
                        )
                try:
                    _remove_generation_activation_marker()
                except OSError as cleanup_error:
                    logger.warning(
                        "Recovered previous generation but its marker remains: %s",
                        cleanup_error,
                    )
                else:
                    _unlink_transaction_artifact_best_effort(_backup_metadata_path(backup_path))
                logger.warning(
                    "Recovered the marker-bound previous generation from its "
                    "consumed backup sidecar"
                )
                return True

        # A crash can occur before active->backup, or after a successful
        # rollback but before marker cleanup. In both cases the active table and
        # durable version independently prove the marker-bound previous ID.
        # The sidecar may already have been consumed by the rename, so it is not
        # required for this active-pair proof.
        if active_path.exists():
            try:
                current_version = _load_version_info_strict()
                if not isinstance(current_version, Mapping):
                    raise GenerationIdentityError("Previous active version metadata is unavailable")
                current_bound = _bind_declared_backup_version(current_version)
                if current_bound[GENERATION_ID_FIELD] != marker["previous_generation_id"]:
                    raise GenerationIdentityError(
                        "Current metadata is not the marker-bound previous generation"
                    )
                _assert_table_path_generation(active_path, current_bound)
            except GenerationIdentityError as proof_error:
                logger.warning(
                    "Pending pre-swap proof failed; evaluating rollback: %s",
                    proof_error,
                )
            else:
                marker_removed = False
                try:
                    _remove_generation_activation_marker()
                    marker_removed = True
                except OSError as cleanup_error:
                    logger.warning(
                        "Previous generation remains proven, but its pending marker "
                        "could not be removed: %s",
                        cleanup_error,
                    )
                if marker_removed and backup_path is not None:
                    _unlink_transaction_artifact_best_effort(_backup_metadata_path(backup_path))
                logger.warning(
                    "Recovered the marker-bound previous table/version pair; it " "remains active"
                )
                return True

    # A malformed marker cannot identify a rollback target. Preserve an active
    # table only when its own persisted ID and version fingerprint still agree;
    # otherwise quarantine it below. If the bad marker cannot be deleted, the
    # pair may remain queryable but core_sync refuses to start another activation.
    if marker is None and marker_error is not None and active_path.exists():
        try:
            current_version = _load_version_info_strict()
            if not isinstance(current_version, Mapping):
                raise GenerationIdentityError("Active version metadata is unavailable")
            current_bound = _bind_declared_backup_version(current_version)
            _assert_table_path_generation(active_path, current_bound)
        except GenerationIdentityError as proof_error:
            logger.error(
                "Invalid marker and unprovable active generation require " "quarantine: %s",
                proof_error,
            )
        else:
            try:
                _remove_generation_activation_marker()
            except OSError as cleanup_error:
                logger.error(
                    "Preserved a proven active generation, but the invalid marker "
                    "could not be removed: %s",
                    cleanup_error,
                )
            else:
                logger.warning(
                    "Removed an invalid transaction marker while retaining the "
                    "independently proven active generation"
                )
            return True

    from app.core import query_engine

    async with query_engine.database_write_guard() as guarded_engine:
        guarded_engine._reset_database_handles_locked()

        if active_path.exists():
            failed_path = await _quarantine_generation_table(
                active_path,
                "aidefend_failed_generation",
            )
            logger.error(
                "Quarantined an uncommitted or unverifiable active generation as %s",
                failed_path.name if failed_path is not None else "unknown",
            )

        restored = False
        restored_backup_metadata_path: Optional[Path] = None
        if backup_path is not None and backup_path.exists():
            try:
                await _restore_backup_generation(
                    backup_path,
                    active_path,
                    guarded_engine,
                    expected_generation_id=marker["previous_generation_id"],
                )
            except (asyncio.CancelledError, GenerationRestoreRetryableError):
                # The verified backup and marker remain intact for the next
                # attempt; never turn a transient model/I/O/cancellation event
                # into an orphaned LKG that forces a rebuild.
                raise
            except GenerationIdentityError as recovery_error:
                logger.error(
                    "Marker-bound rollback generation was rejected: %s",
                    recovery_error,
                    exc_info=True,
                )
            else:
                restored = True
                restored_backup_metadata_path = _backup_metadata_path(backup_path)
                logger.warning(
                    "Restored the marker-bound table/version generation %s",
                    marker["previous_generation_id"][:12],
                )
        elif marker_error is None:
            logger.error(
                "No marker-bound, metadata-paired rollback generation exists; "
                "a clean sync is required"
            )

        if not restored:
            guarded_engine._reset_database_handles_locked()

    marker_removed = False
    try:
        _remove_generation_activation_marker()
        marker_removed = True
    except OSError as exc:
        logger.error(
            "Could not remove handled generation marker; recovery will be retried: %s",
            exc,
        )
    if marker_removed and restored_backup_metadata_path is not None:
        _unlink_transaction_artifact_best_effort(restored_backup_metadata_path)
    return True


async def recover_incomplete_generation_activation() -> bool:
    """Recover an interrupted activation under the cross-process sync lock.

    Startup and other external callers must use this wrapper.  ``core_sync``
    already owns the same non-reentrant lock and therefore calls the private
    locked helper directly.
    """
    if not await _acquire_sync_lock():
        raise RuntimeError(
            "Cannot inspect or recover a pending database generation while "
            "another process is synchronizing"
        )
    with _lease_state_lock:
        temporary_data_path_lease = not _operation_borrows_lifetime_lease
    try:
        recovered = await _await_operation_to_completion(
            _recover_incomplete_generation_activation_locked(),
            task_name="aidefend-generation-recovery",
        )
        _cleanup_durable_tombstones_best_effort()
        return recovered
    finally:
        try:
            if temporary_data_path_lease:
                # A direct recovery call can initialize LanceDB while
                # restoring the last-known-good generation.  Keep DATA_PATH
                # ownership until every resulting handle is closed.
                await _close_query_engine_to_completion(
                    task_name="aidefend-standalone-recovery-close",
                )
        finally:
            _release_sync_lock()


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
            raise ValueError(f"{document.get('source_id', 'Unknown')}: searchable text is missing")
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
            raise ValueError(f"{document.get('source_id', 'Unknown')}: searchable text is missing")
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


async def embed_and_index(
    documents: List[Dict[str, Any]],
    *,
    framework_labels: Optional[Mapping[str, str]] = None,
    version_metadata_builder: Optional[
        Callable[[Dict[str, Any]], Tuple[str, Mapping[str, Any]]]
    ] = None,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
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
        if version_metadata_builder is None:
            raise RuntimeError("embed_and_index requires an atomic version metadata builder")

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
                timeout=300,  # 5 minute timeout for model download
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
            dimension=settings.EMBEDDING_DIMENSION,
        )

        # Auto-cleanup: remove cache entries for deleted documents
        current_doc_ids = {doc["source_id"] for doc in documents}
        cache.auto_cleanup(current_doc_ids)

        # Check cache and generate embeddings (with progress indicators)
        logger.info(
            f"🔄 Generating embeddings for {len(documents)} documents (using cache when possible)..."
        )

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

            records.append(
                {
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
                    "defends_against": json.dumps(parse_json_list(doc.get("defends_against", []))),
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
                    "warnings": json.dumps(parse_json_list(doc.get("warnings", []))),
                }
            )

        # Pre-compute statistics from records (optimization for get_statistics tool)
        logger.info("📊 Pre-computing statistics from records...")
        statistics = _calculate_statistics_from_records(
            records,
            framework_labels=framework_labels,
        )
        logger.info(
            f"✅ Statistics pre-computed: {statistics['overview']['total_documents']} documents"
        )

        # Build threat mappings reverse index (optimization for defenses_for_threat tool)
        logger.info("🔗 Building threat mappings reverse index...")
        threat_mappings = _build_threat_mappings(
            records,
            framework_labels=framework_labels,
        )
        statistics["threat_mappings"] = threat_mappings
        logger.info(f"✅ Threat mappings built: {len(threat_mappings)} unique threat IDs")

        # Bind the staged table and version/provenance snapshot before writing
        # any Lance bytes. Every row carries the same independently verifiable
        # generation ID.
        version_commit = version_metadata_builder(statistics)
        commit_sha, raw_version_metadata = version_commit
        bound_version = bind_version_generation(
            {"commit_sha": commit_sha, **dict(raw_version_metadata)},
            allow_legacy=False,
        )
        table_generation_id = bound_version[GENERATION_ID_FIELD]
        for record in records:
            record[GENERATION_ID_FIELD] = table_generation_id
        version_commit = (
            commit_sha,
            {key: value for key, value in bound_version.items() if key != "commit_sha"},
        )

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
                logger.info(
                    f"Cleaned up orphaned '{temp_table_name}' table from previous failed sync"
                )
        except Exception as cleanup_err:
            logger.warning(f"Could not clean up temp table '{temp_table_name}': {cleanup_err}")

        # Declare every field explicitly. Schema inference can silently choose
        # a null/incorrect type when an additive framework field is empty in a
        # particular release.
        record_schema = pa.schema(
            [
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
                pa.field(GENERATION_ID_FIELD, pa.string()),
            ]
        )
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
        await _activate_staged_database(
            new_sync_path,
            version_commit=version_commit,
        )

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
            error_detail += "Check the full stack trace in the logs for diagnostic information.\n"

        logger.error(error_detail, exc_info=True)
        return (False, None)


async def _cleanup_successful_sync_artifacts() -> bool:
    """Remove rollback/staging tables only after a successful committed sync."""
    artifact_paths = {
        settings.DB_PATH / "aidefend_new_sync.lance",
        *settings.DB_PATH.glob("aidefend_backup*.lance"),
        *settings.DB_PATH.glob("aidefend_backup*.version.json"),
        *settings.DB_PATH.glob("aidefend_failed_sync*.lance"),
        *settings.DB_PATH.glob("aidefend_failed_metadata*.lance"),
        *settings.DB_PATH.glob("aidefend_failed_generation*.lance"),
    }
    failures = []
    for artifact_path in sorted(artifact_paths, key=lambda path: path.name):
        artifact_name = artifact_path.name
        if not artifact_path.exists():
            continue
        try:
            if artifact_path.is_dir():
                await asyncio.to_thread(shutil.rmtree, artifact_path)
            else:
                await asyncio.to_thread(artifact_path.unlink)
            logger.info(f"Removed successful-sync artifact: {artifact_name}")
        except Exception as exc:
            failures.append(f"{artifact_name}: {exc}")
            logger.error(
                f"Could not remove successful-sync artifact {artifact_name}: {exc}",
                exc_info=True,
            )
    if failures:
        _set_last_sync_error(
            "The new index is active, but sync artifact cleanup failed: " + "; ".join(failures)
        )
        return False
    _cleanup_durable_tombstones_best_effort()
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
    # Every entry point (REST, STDIO MCP, CLI, background loop, tests) must
    # settle a prior interrupted generation before it can stage another one.
    await _recover_incomplete_generation_activation_locked()
    if _generation_activation_marker_path().exists():
        raise RuntimeError(
            "A pending generation marker could not be cleared; refusing to "
            "start another database activation"
        )
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
        except Exception as manifest_error:
            error_msg = (
                "Framework main.js manifest validation failed; sync aborted and "
                f"the last-known-good index was retained: {manifest_error}"
            )
            logger.error(error_msg, exc_info=True)
            _set_last_sync_error(error_msg)
            return False

        # Edition-migration metadata is versioned with the same local source
        # tree or immutable GitHub revision. Missing metadata is accepted only
        # for the legacy 2025 corpus; corpus coherence is checked after parsing.
        try:
            framework_migrations_path = await download_framework_migrations_file(latest_sha)
            framework_migrations = await asyncio.to_thread(
                load_and_validate_framework_migrations,
                framework_migrations_path,
            )
            framework_migrations_sha256 = (
                await asyncio.to_thread(
                    compute_framework_migrations_sha256,
                    framework_migrations_path,
                )
                if framework_migrations_path is not None
                else None
            )
            source_files = _framework_source_files(
                tactic_files,
                include_framework_migrations=framework_migrations is not None,
            )
        except Exception as migration_error:
            error_msg = (
                "Framework edition migration registry validation failed; sync "
                "was aborted and the last-known-good index was retained: "
                f"{migration_error}"
            )
            logger.error(error_msg, exc_info=True)
            _set_last_sync_error(error_msg)
            return False

        # Rebuild not only when framework content changes, but also when the
        # MCP extraction/index contract or embedding configuration changes.
        local_sha = get_local_commit_sha()
        version_info = load_version_info() or {}
        expected_source_kind = "local" if _using_local_framework_source() else "github"
        public_data_keep_revisions: List[str] = []
        if expected_source_kind == "github":
            public_data_keep_revisions.append(latest_sha)
            stored_revision = _stored_source_revision(version_info)
            if (
                version_info.get("source_kind") == "github"
                and version_info.get("source_revision_kind") == "git_commit_sha"
                and str(version_info.get("source_repository", "")).strip().lower()
                == settings.github_repo_path.strip().lower()
                and re.fullmatch(r"[0-9a-f]{40}", stored_revision) is not None
            ):
                public_data_keep_revisions.append(stored_revision)
        _cleanup_staged_framework_public_data_revisions(
            keep_revisions=public_data_keep_revisions,
        )

        # The derived public export is metadata-only: it is neither indexed nor
        # included in the authored source digest. Discover its root schema version
        # from the same local root or exact immutable GitHub revision as tactics.
        public_data_result = await download_framework_public_data_file(
            latest_sha,
            previous_source_revision=_stored_source_revision(version_info) or None,
        )
        discovered_public_schema_version = await asyncio.to_thread(
            extract_framework_public_schema_version,
            public_data_result.path,
            base_dir=settings.RAW_PATH,
        )
        framework_public_schema_version = resolve_effective_framework_public_schema_version(
            discovered_public_schema_version,
            version_info=version_info,
            current_source_revision=latest_sha,
            source_kind=expected_source_kind,
            current_source_repository=(
                "local-working-tree"
                if _using_local_framework_source()
                else settings.github_repo_path
            ),
            discovery_status=public_data_result.status,
        )
        if (
            framework_public_schema_version == UNKNOWN_FRAMEWORK_SCHEMA_VERSION
            and public_data_result.retained_previous
        ):
            _discard_staged_framework_public_data_file(
                latest_sha if expected_source_kind == "github" else None
            )
        framework_public_schema_source = (
            FRAMEWORK_PUBLIC_DATA_SOURCE_PATH
            if framework_public_schema_version != UNKNOWN_FRAMEWORK_SCHEMA_VERSION
            else None
        )
        logger.info(
            "Framework public schema version: %s%s",
            framework_public_schema_version,
            (
                f" (source: {FRAMEWORK_PUBLIC_DATA_SOURCE_PATH})"
                if framework_public_schema_source is not None
                else ""
            ),
        )

        rebuild_reasons: List[str] = []
        if not (settings.DB_PATH / "aidefend.lance").is_dir():
            rebuild_reasons.append("active database table missing")
        if version_info.get("framework_public_schema_version") != framework_public_schema_version:
            rebuild_reasons.append(
                "framework public schema version "
                f"{version_info.get('framework_public_schema_version', 'missing')} -> "
                f"{framework_public_schema_version}"
            )
        if version_info.get("framework_public_schema_source") != framework_public_schema_source:
            rebuild_reasons.append("framework public schema source provenance changed or missing")
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
            "local-working-tree" if _using_local_framework_source() else settings.github_repo_path
        )
        expected_source_ref = (
            "working-tree" if _using_local_framework_source() else settings.GITHUB_BRANCH
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
        migration_metadata_keys = (
            "framework_migrations",
            "framework_migrations_schema_version",
            "framework_migrations_registry_version",
            "framework_migrations_sha256",
        )
        if framework_migrations is not None:
            expected_migration_metadata = {
                "framework_migrations": framework_migrations,
                "framework_migrations_schema_version": framework_migrations["schemaVersion"],
                "framework_migrations_registry_version": framework_migrations["registryVersion"],
                "framework_migrations_sha256": framework_migrations_sha256,
            }
            for key, expected_value in expected_migration_metadata.items():
                if version_info.get(key) != expected_value:
                    rebuild_reasons.append(f"{key} changed or missing")
        elif any(key in version_info for key in migration_metadata_keys):
            rebuild_reasons.append("stale framework migration metadata must be removed")

        if local_sha == latest_sha and rebuild_reasons and not force_rebuild:
            logger.info(
                "Rebuilding unchanged framework source because MCP index metadata changed: "
                + "; ".join(rebuild_reasons)
            )
            force_rebuild = True

        if _using_local_framework_source() and local_sha == latest_sha:
            current_local_signature = _compute_local_framework_signature(tactic_files)
            if current_local_signature != latest_sha:
                error_msg = (
                    "Local framework changed during the no-op sync check; retry "
                    "once the working tree is stable."
                )
                logger.error(error_msg)
                _set_last_sync_error(error_msg)
                return False

        if local_sha == latest_sha and not force_rebuild:
            logger.info(f"Already up-to-date (commit: {local_sha[:8]})")

            # A process interruption after a prior successful version write can
            # leave a backup/staging table behind. A no-op sync repairs that
            # residue before reporting a clean current state.
            if not await _cleanup_successful_sync_artifacts():
                return False
            _cleanup_staged_framework_public_data_revisions(
                keep_revisions=([latest_sha] if expected_source_kind == "github" else []),
            )

            # Update timestamp to indicate sync check completed
            # This shows users that the service checked for updates even if none were available
            save_sync_timestamp()

            return True

        if force_rebuild:
            logger.info(
                f"Force rebuild requested (current: {local_sha[:8] if local_sha else 'None'})"
            )
        else:
            logger.info(
                f"Update available: {local_sha[:8] if local_sha else 'None'} -> {latest_sha[:8]}"
            )

        # Download all files in parallel (faster than serial downloads)
        if _using_local_framework_source():
            logger.info(f"📥 Staging {len(source_files)} files from local framework...")
        else:
            logger.info(f"📥 Downloading {len(source_files)} files in parallel...")

        required_download_sources = [FRAMEWORK_INTRO_FILENAME, *tactic_files]
        download_tasks = []
        for filename in required_download_sources:
            if filename == FRAMEWORK_INTRO_FILENAME:
                # Special handling for intro file (in root directory)
                download_tasks.append(download_intro_file(latest_sha))
            else:
                download_tasks.append(download_file(filename, latest_sha))

        # Execute all downloads concurrently
        download_results = await asyncio.gather(*download_tasks, return_exceptions=True)

        # Process results
        downloaded_files: List[Path] = (
            [framework_migrations_path] if framework_migrations_path is not None else []
        )
        failed_required = []

        for i, result in enumerate(download_results):
            filename = required_download_sources[i]

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
                    f"Failed files:\n" + "\n".join([f"  - {f}" for f in failed_required]) + "\n\n"
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
                    f"Failed files:\n" + "\n".join([f"  - {f}" for f in failed_required]) + "\n\n"
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
        required_files = {_staged_framework_filename(name) for name in source_files}
        downloaded_names = {path.name for path in downloaded_files}
        missing_required_files = sorted(required_files - downloaded_names)
        if missing_required_files:
            error_msg = (
                "Required tactic files are missing from the staged framework source\n\n"
                "Missing files:\n"
                + "\n".join(f"  - {filename}" for filename in missing_required_files)
                + "\n\n"
                f"This usually indicates network issues or incomplete downloads.\n\n"
                "Check the download errors in the logs above for specific failure reasons."
            )
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False

        logger.info(f"✅ Staged {len(downloaded_files)}/{len(source_files)} files")

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
                    extract_framework_version, intro_file_path
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
        logger.info(f"📄 Parsing {len(tactic_files)} tactic files...")

        all_documents = []
        parsed_tactics: List[Mapping[str, Any]] = []
        failed_files = []
        seen_control_ids: set[str] = set()
        seen_guidance_ids: set[str] = set()
        scope_references: List[Tuple[str, str]] = []
        total_files = len(tactic_files)
        parsed_count = 0

        for file_path in downloaded_files:
            # Release and migration files are metadata only, never JavaScript tactics.
            if file_path.name in {
                FRAMEWORK_INTRO_FILENAME,
                FRAMEWORK_MIGRATIONS_FILENAME,
            }:
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

                    parsed_tactics.append(tactic_data)

                    # Use asyncio.to_thread for extract_documents_from_tactic as well
                    # (involves CPU-intensive data transformation)
                    documents = await asyncio.to_thread(extract_documents_from_tactic, tactic_data)
                    all_documents.extend(documents)

                    # Show progress every 10 files or at completion
                    if parsed_count % 10 == 0 or parsed_count == total_files:
                        progress_pct = (parsed_count / total_files) * 100
                        logger.info(
                            f"📄 Parsing progress: {parsed_count}/{total_files} ({progress_pct:.1f}%) - {len(documents)} docs from {file_path.name}"
                        )
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

        logger.info(
            f"✅ Parsing complete: {len(all_documents)} documents extracted from {parsed_count} files"
        )

        if not failed_files:
            try:
                validate_framework_migrations_corpus_contract(
                    framework_migrations,
                    parsed_tactics,
                )
            except FrameworkMigrationRegistryError as migration_error:
                logger.error(
                    "Framework migration registry and tactic corpus disagree: %s",
                    migration_error,
                )
                failed_files.append("framework migration corpus contract")

        missing_scope_targets = sorted(
            {
                (owner_id, target_id)
                for owner_id, target_id in scope_references
                if target_id not in seen_control_ids
            }
        )
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
                f"Failed files:\n" + "\n".join([f"  - {f}" for f in failed_files]) + "\n\n"
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
        effective_framework_labels = framework_labels_from_registry(framework_migrations)
        version_commit_prepared = False
        # A semantic source fingerprint can be identical across a forced repair
        # rebuild. Bind each physical table build to a fresh nonce so recovery
        # can distinguish pre-swap old bytes from fully committed new bytes.
        generation_build_id = secrets.token_hex(32)

        def build_version_commit(
            staged_statistics: Dict[str, Any],
        ) -> Tuple[str, Mapping[str, Any]]:
            """Build the metadata snapshot committed inside the DB writer lock."""
            nonlocal version_commit_prepared
            staged_total = staged_statistics.get("overview", {}).get("total_documents", 0)
            if staged_total != len(all_documents) or staged_total < 1:
                raise RuntimeError(
                    "Staged index statistics do not match the extracted document "
                    f"population ({staged_total!r} != {len(all_documents)!r})"
                )
            version_metadata: Dict[str, Any] = {
                GENERATION_BUILD_ID_FIELD: generation_build_id,
                "framework_version": framework_version,
                "framework_public_schema_version": framework_public_schema_version,
                "total_documents": len(all_documents),
                "total_actionable_items": staged_statistics.get("overview", {}).get(
                    "total_actionable_items"
                ),
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
                "statistics": staged_statistics,
            }
            if framework_public_schema_source is not None:
                version_metadata["framework_public_schema_source"] = framework_public_schema_source
            if framework_migrations is not None:
                version_metadata.update(
                    {
                        "framework_migrations": framework_migrations,
                        "framework_migrations_schema_version": framework_migrations[
                            "schemaVersion"
                        ],
                        "framework_migrations_registry_version": framework_migrations[
                            "registryVersion"
                        ],
                        "framework_migrations_sha256": framework_migrations_sha256,
                    }
                )
            version_commit_prepared = True
            return latest_sha, version_metadata

        success, statistics = await embed_and_index(
            all_documents,
            framework_labels=effective_framework_labels,
            version_metadata_builder=build_version_commit,
        )
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

        if not version_commit_prepared:
            error_msg = (
                "Embedding completed without preparing the atomic database/version "
                "generation commit"
            )
            logger.error(error_msg)
            _set_last_sync_error(error_msg)
            return False

        # The backup is retained through initialization and the durable metadata
        # write inside _activate_staged_database(). Only now is it obsolete.
        if not await _cleanup_successful_sync_artifacts():
            return False
        _cleanup_staged_framework_public_data_revisions(
            keep_revisions=([latest_sha] if expected_source_kind == "github" else []),
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


async def _await_operation_to_completion(operation, *, task_name: str):
    """Drain a write-capable task before propagating caller cancellation.

    ``asyncio.to_thread`` work cannot be stopped by cancelling the coroutine
    that awaits it. A shielded child task guarantees that operation and
    DATA_PATH leases remain held until every worker and rollback path has
    actually finished.
    """
    return await _await_cancellation_safe(operation, task_name=task_name)


async def _run_core_sync_to_completion(force_rebuild: bool) -> bool:
    """Run the complete sync transaction through the safe drain boundary."""
    return await _await_operation_to_completion(
        core_sync(force_rebuild=force_rebuild),
        task_name="aidefend-core-sync",
    )


async def _close_query_engine_to_completion(*, task_name: str) -> None:
    """Close LanceDB handles before their DATA_PATH ownership is released."""
    from app.core import query_engine

    await _await_operation_to_completion(
        query_engine.close(),
        task_name=task_name,
    )


async def _run_cli_sync_to_completion(force_rebuild: bool) -> bool:
    """Run a CLI sync and close all DB handles in one cancellation boundary.

    Keeping both phases inside the same ``asyncio.run`` invocation ensures
    repeated SIGINT/task cancellation cannot return control to the synchronous
    CLI lease-release path while either sync or close is still active.
    """
    try:
        return await _run_core_sync_to_completion(force_rebuild)
    finally:
        await _close_query_engine_to_completion(
            task_name="aidefend-cli-sync-close",
        )


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

    with _lease_state_lock:
        temporary_data_path_lease = not _operation_borrows_lifetime_lease

    try:
        return await _run_core_sync_to_completion(force_rebuild)
    finally:
        try:
            if temporary_data_path_lease:
                # Standalone callers do not have a service lifespan that will
                # close LanceDB. Release every handle before giving another
                # process ownership of this DATA_PATH.
                await _close_query_engine_to_completion(
                    task_name="aidefend-standalone-sync-close",
                )
        finally:
            # Always release only after the shielded worker and standalone DB
            # handle cleanup have completed.
            _release_sync_lock()


async def _create_vector_index_if_needed() -> bool:
    """
    Create a LanceDB vector index when the dataset is large enough to benefit.

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
                logger.info(
                    f"✅ Vector index already exists ({len(indices)} indices found), skipping creation"
                )
                return True
        except Exception:
            # list_indices() might not be available or might error - proceed with creation
            logger.debug(
                "Could not inspect existing LanceDB indices; continuing with creation",
                exc_info=True,
            )

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
            num_partitions = max(8, int(row_count**0.5))
        else:
            num_partitions = max(256, int(row_count**0.5))

        dimension = settings.EMBEDDING_DIMENSION
        num_sub_vectors = dimension // 16

        logger.info("=" * 60)
        logger.info("CREATING VECTOR INDEX (this may take several minutes)")
        logger.info("=" * 60)
        logger.info(f"Database rows: {row_count}")
        logger.info(f"Index partitions: {num_partitions}")
        logger.info(f"Sub-vectors: {num_sub_vectors}")
        logger.info(
            "This is a one-time operation; measure query latency on your "
            "deployment to quantify the benefit."
        )

        # Create index
        await asyncio.to_thread(
            table.create_index,
            metric="cosine",
            num_partitions=num_partitions,
            num_sub_vectors=num_sub_vectors,
        )

        logger.info("=" * 60)
        logger.info("✅ Vector index created successfully!")
        logger.info(
            "Index performance depends on the dataset, hardware, and query workload"
        )
        logger.info("=" * 60)

        return True

    except Exception as e:
        # Non-critical failure - service still works without index
        logger.warning(f"Failed to create vector index (non-critical): {e}", exc_info=True)
        logger.info("Service will continue to work (queries may be slower without index)")
        return False


async def sync_loop(stop_event: Optional[asyncio.Event] = None):
    """Run update checks until cooperatively asked to stop.

    Shutdown deliberately does not cancel an active ``run_sync``: cancellation
    cannot stop workers already executing through ``asyncio.to_thread``. The
    service must retain its DATA_PATH lease until those workers and the sync
    coroutine finish normally.
    """
    logger.info(f"Starting sync loop (interval: {settings.SYNC_INTERVAL_SECONDS}s)")

    consecutive_failures = 0
    max_backoff = 3600 * 4  # Cap at 4 hours
    first_check = True

    async def wait_or_stop(delay: float) -> bool:
        if stop_event is None:
            await asyncio.sleep(delay)
            return False
        if stop_event.is_set():
            return True
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
            return True
        except TimeoutError:
            return False

    while True:
        try:
            if stop_event is not None and stop_event.is_set():
                break
            # Warm services check immediately. Subsequent checks wait for the
            # configured interval or exponential failure backoff.
            if first_check:
                first_check = False
            elif consecutive_failures > 0:
                backoff = min(
                    settings.SYNC_INTERVAL_SECONDS * (2**consecutive_failures), max_backoff
                )
                logger.warning(
                    f"Sync backoff: waiting {backoff:.0f}s after {consecutive_failures} consecutive failure(s)"
                )
                if await wait_or_stop(backoff):
                    break
            else:
                if await wait_or_stop(settings.SYNC_INTERVAL_SECONDS):
                    break

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
            if stop_event is not None and stop_event.is_set():
                break
        except asyncio.CancelledError:
            logger.error(
                "Unsafe cancellation requested while the sync loop may own "
                "non-cancellable worker threads; waiting for process teardown"
            )
            raise
        except Exception as e:
            consecutive_failures += 1
            logger.error(f"Error in sync loop: {e}", exc_info=True)

    logger.info("Sync loop stopped")
