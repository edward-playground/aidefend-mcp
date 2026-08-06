"""Lightweight, read-only probes for the cross-process DATA_PATH lease."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_lock_file_held_by_other_process(lock_file: Path) -> bool:
    """Return whether another process holds ``lock_file`` without modifying it.

    This module intentionally has no database, embedding, or web-framework imports.
    CLI contention checks must be able to reject a second process promptly even on
    a cold machine before the heavier service runtime is imported.
    """
    lock_path = Path(lock_file)
    if not lock_path.exists():
        return False

    try:
        descriptor = os.open(
            str(lock_path),
            os.O_RDWR if sys.platform == "win32" else os.O_RDONLY,
        )
    except OSError:
        # Preserve the existing advisory-probe behavior: the atomic service-lock
        # acquisition remains authoritative when a path cannot be inspected.
        return False

    try:
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            try:
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            except OSError:
                # Closing the descriptor still releases this process's probe lock.
                pass
            return False

        import fcntl

        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            return True
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except (OSError, IOError):
            # Closing the descriptor still releases this process's probe lock.
            pass
        return False
    finally:
        os.close(descriptor)
