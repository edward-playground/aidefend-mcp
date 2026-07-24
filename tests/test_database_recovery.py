"""Isolated tests for database recovery and sync locking.

These tests must never move, delete, rebuild, or otherwise mutate the service's
configured database.  Every filesystem assertion is scoped to ``tmp_path``.
"""

from pathlib import Path

import pytest


def test_imports():
    """Recovery entry points remain importable."""
    from app.config import settings
    from app.sync import SyncFileLock, check_database_corruption, ensure_database_ready

    assert settings is not None
    assert callable(check_database_corruption)
    assert callable(ensure_database_ready)
    assert SyncFileLock is not None


def test_missing_database_is_not_reported_as_corrupt(tmp_path, monkeypatch):
    """A database that has not been initialized is missing, not corrupt."""
    from app.config import settings
    from app.sync import check_database_corruption

    database_path = tmp_path / "missing-db"
    monkeypatch.setattr(settings, "DB_PATH", database_path)

    assert not database_path.exists()
    assert check_database_corruption() is False


def test_incomplete_database_is_reported_as_corrupt(tmp_path, monkeypatch):
    """An incomplete LanceDB layout fails the structural health checks."""
    from app.config import settings
    from app.sync import check_database_corruption

    database_path = tmp_path / "incomplete-db"
    (database_path / "aidefend.lance" / "data").mkdir(parents=True)
    monkeypatch.setattr(settings, "DB_PATH", database_path)

    assert check_database_corruption() is True


@pytest.mark.asyncio
async def test_ensure_ready_healthy_database_does_not_rebuild(tmp_path, monkeypatch):
    """The healthy fast path must not invoke the destructive rebuild path."""
    import app.sync as sync_module
    from app.config import settings

    database_path = tmp_path / "healthy-db"
    database_path.mkdir()
    monkeypatch.setattr(settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module, "check_database_corruption", lambda: False)

    async def unexpected_rebuild(*, force_rebuild=False):
        pytest.fail(f"healthy database unexpectedly rebuilt (force={force_rebuild})")

    monkeypatch.setattr(sync_module, "run_sync", unexpected_rebuild)

    assert await sync_module.ensure_database_ready() is True


@pytest.mark.asyncio
async def test_ensure_ready_missing_database_uses_isolated_rebuild(tmp_path, monkeypatch):
    """The missing-database path requests one forced sync without touching real data."""
    import app.sync as sync_module
    from app.config import settings

    database_path = tmp_path / "new-db"
    monkeypatch.setattr(settings, "DB_PATH", database_path)
    calls = []

    async def successful_rebuild(*, force_rebuild=False):
        calls.append(force_rebuild)
        return True

    monkeypatch.setattr(sync_module, "run_sync", successful_rebuild)

    assert await sync_module.ensure_database_ready() is True
    assert calls == [True]


def test_sync_file_lock_is_exclusive_and_reusable(tmp_path):
    """Both same-instance and cross-instance concurrent acquisition must fail."""
    from app.sync import SyncFileLock

    lock_path = Path(tmp_path) / "sync.lock"
    first = SyncFileLock(lock_path)
    contender = SyncFileLock(lock_path)

    assert first.acquire(timeout=0) is True
    try:
        assert first.acquire(timeout=0) is False
        assert contender.acquire(timeout=0) is False
    finally:
        contender.release()
        first.release()

    successor = SyncFileLock(lock_path)
    assert successor.acquire(timeout=0) is True
    successor.release()
