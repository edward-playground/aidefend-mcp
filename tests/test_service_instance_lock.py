"""Cross-process DATA_PATH lifetime-lease regressions."""

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

import app.sync as sync_module


@pytest.fixture
def isolated_lease(tmp_path, monkeypatch):
    lock_path = tmp_path / "data" / "sync.lock"
    monkeypatch.setattr(sync_module.settings, "DATA_PATH", lock_path.parent)
    monkeypatch.setattr(
        sync_module,
        "_file_lock",
        sync_module.SyncFileLock(lock_path),
    )
    monkeypatch.setattr(sync_module, "_sync_operation_lock", threading.Lock())
    monkeypatch.setattr(sync_module, "_lease_state_lock", threading.Lock())
    monkeypatch.setattr(sync_module, "_lifetime_lease_owned", False)
    monkeypatch.setattr(
        sync_module,
        "_operation_borrows_lifetime_lease",
        False,
    )
    yield lock_path
    sync_module._release_sync_lock()
    sync_module.release_service_instance_lock()


@pytest.mark.asyncio
async def test_lifetime_lease_is_exclusive_and_operations_borrow_it(isolated_lease):
    assert sync_module.acquire_service_instance_lock() is True
    assert sync_module.acquire_service_instance_lock() is False

    assert await sync_module._acquire_sync_lock() is True
    assert sync_module.is_sync_in_progress() is True
    assert sync_module._file_lock.is_locked is True
    sync_module._release_sync_lock()

    assert sync_module.is_sync_in_progress() is False
    assert sync_module._file_lock.is_locked is True
    sync_module.release_service_instance_lock()
    assert sync_module._file_lock.is_locked is False
    assert isolated_lease.is_file()

    successor = sync_module.SyncFileLock(isolated_lease)
    assert successor.acquire(timeout=0) is True
    successor.release()


@pytest.mark.asyncio
async def test_service_guard_releases_after_exception_and_cancellation(isolated_lease):
    with pytest.raises(RuntimeError, match="synthetic startup failure"):
        async with sync_module.service_instance_guard("test service"):
            raise RuntimeError("synthetic startup failure")

    with pytest.raises(asyncio.CancelledError):
        async with sync_module.service_instance_guard("test service"):
            raise asyncio.CancelledError()

    successor = sync_module.SyncFileLock(isolated_lease)
    assert successor.acquire(timeout=0) is True
    successor.release()


@pytest.mark.asyncio
async def test_standalone_run_sync_temporarily_owns_data_path(
    isolated_lease, monkeypatch
):
    observations = []

    async def fake_core_sync(*, force_rebuild=False):
        observations.append(
            (
                force_rebuild,
                sync_module._file_lock.is_locked,
                sync_module.is_sync_in_progress(),
            )
        )
        return True

    monkeypatch.setattr(sync_module, "core_sync", fake_core_sync)

    assert await sync_module.run_sync(force_rebuild=True) is True
    assert observations == [(True, True, True)]
    assert sync_module._file_lock.is_locked is False
    assert sync_module.is_sync_in_progress() is False


@pytest.mark.asyncio
async def test_cancelled_run_sync_drains_worker_before_releasing_lease(
    isolated_lease, monkeypatch
):
    started = asyncio.Event()
    finish = asyncio.Event()

    async def fake_core_sync(*, force_rebuild=False):
        started.set()
        await finish.wait()
        return True

    monkeypatch.setattr(sync_module, "core_sync", fake_core_sync)

    task = asyncio.create_task(sync_module.run_sync())
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)

    assert task.done() is False
    assert sync_module._file_lock.is_locked is True
    assert sync_module.is_sync_in_progress() is True

    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert sync_module._file_lock.is_locked is False
    assert sync_module.is_sync_in_progress() is False


@pytest.mark.asyncio
async def test_repeated_cancel_during_standalone_close_retains_lease(
    isolated_lease, monkeypatch
):
    from app.core import query_engine

    sync_started = asyncio.Event()
    finish_sync = asyncio.Event()
    close_started = asyncio.Event()
    finish_close = asyncio.Event()

    async def fake_core_sync(*, force_rebuild=False):
        sync_started.set()
        await finish_sync.wait()
        return True

    async def fake_close():
        close_started.set()
        await finish_close.wait()

    monkeypatch.setattr(sync_module, "core_sync", fake_core_sync)
    monkeypatch.setattr(query_engine, "close", fake_close)

    task = asyncio.create_task(sync_module.run_sync())
    await sync_started.wait()
    task.cancel()
    finish_sync.set()
    await close_started.wait()

    # A second cancellation must not cut through the close drain and release
    # either the process-local operation guard or the DATA_PATH lease.
    task.cancel()
    await asyncio.sleep(0)
    assert task.done() is False
    assert sync_module._file_lock.is_locked is True
    assert sync_module.is_sync_in_progress() is True

    successor = sync_module.SyncFileLock(isolated_lease)
    assert successor.acquire(timeout=0) is False

    finish_close.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert sync_module._file_lock.is_locked is False
    assert sync_module.is_sync_in_progress() is False
    assert successor.acquire(timeout=0) is True
    successor.release()


@pytest.mark.asyncio
async def test_standalone_recovery_closes_handles_before_releasing_lease(
    isolated_lease, monkeypatch
):
    from app.core import query_engine

    observations = []

    async def fake_recovery():
        observations.append(
            ("recover", sync_module._file_lock.is_locked, sync_module.is_sync_in_progress())
        )
        return True

    async def fake_close():
        observations.append(
            ("close", sync_module._file_lock.is_locked, sync_module.is_sync_in_progress())
        )

    monkeypatch.setattr(
        sync_module,
        "_recover_incomplete_generation_activation_locked",
        fake_recovery,
    )
    monkeypatch.setattr(
        sync_module,
        "_cleanup_durable_tombstones_best_effort",
        lambda: None,
    )
    monkeypatch.setattr(query_engine, "close", fake_close)

    assert await sync_module.recover_incomplete_generation_activation() is True
    assert observations == [
        ("recover", True, True),
        ("close", True, True),
    ]
    assert sync_module._file_lock.is_locked is False
    assert sync_module.is_sync_in_progress() is False


@pytest.mark.asyncio
async def test_cli_sync_repeated_cancel_drains_close_before_return(monkeypatch):
    from app.core import query_engine

    sync_started = asyncio.Event()
    finish_sync = asyncio.Event()
    close_started = asyncio.Event()
    finish_close = asyncio.Event()

    async def fake_core_sync(*, force_rebuild=False):
        sync_started.set()
        await finish_sync.wait()
        return True

    async def fake_close():
        close_started.set()
        await finish_close.wait()

    monkeypatch.setattr(sync_module, "core_sync", fake_core_sync)
    monkeypatch.setattr(query_engine, "close", fake_close)

    task = asyncio.create_task(
        sync_module._run_cli_sync_to_completion(force_rebuild=True)
    )
    await sync_started.wait()
    task.cancel()
    finish_sync.set()
    await close_started.wait()
    task.cancel()
    await asyncio.sleep(0)

    assert task.done() is False
    finish_close.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_cancelled_index_maintenance_drains_before_releasing_lease(
    isolated_lease, monkeypatch
):
    import scripts.create_lancedb_index as index_script

    started = asyncio.Event()
    finish = asyncio.Event()

    async def fake_create_index():
        started.set()
        await finish.wait()
        return True

    monkeypatch.setattr(index_script, "create_index", fake_create_index)

    task = asyncio.create_task(index_script.main())
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)

    assert task.done() is False
    assert sync_module._file_lock.is_locked is True
    assert sync_module.is_sync_in_progress() is True

    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert sync_module._file_lock.is_locked is False
    assert sync_module.is_sync_in_progress() is False


def _start_child_lock_holder(lock_path: Path):
    code = r'''
import os
import sys
from pathlib import Path
from app.sync import SyncFileLock
lock = SyncFileLock(Path(sys.argv[1]))
if not lock.acquire(timeout=0):
    raise SystemExit(2)
print(f"READY {os.getpid()}", flush=True)
sys.stdin.readline()
lock.release()
'''
    process = subprocess.Popen(  # nosec B603
        [sys.executable, "-c", code, str(lock_path)],
        cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    ready_line = process.stdout.readline().strip()
    assert ready_line.startswith("READY ")
    return process, ready_line.removeprefix("READY ") + "\n"


@pytest.mark.asyncio
async def test_real_child_lease_blocks_service_and_standalone_sync(isolated_lease):
    process, _holder_pid = _start_child_lock_holder(isolated_lease)
    try:
        assert sync_module.acquire_service_instance_lock() is False
        assert await sync_module._acquire_sync_lock() is False
    finally:
        assert process.stdin is not None
        process.stdin.write("stop\n")
        process.stdin.flush()
        process.wait(timeout=20)
        if process.returncode != 0:
            assert process.stderr is not None
            pytest.fail(process.stderr.read())

    assert sync_module.acquire_service_instance_lock() is True
    sync_module.release_service_instance_lock()


def test_cli_force_never_replaces_or_deletes_live_lock_inode(tmp_path):
    lock_path = tmp_path / "cli-data" / "sync.lock"
    process, expected_holder_pid = _start_child_lock_holder(lock_path)
    try:
        before_stat = lock_path.stat()
        before = (before_stat.st_ino, before_stat.st_mtime_ns, before_stat.st_size)
        environment = os.environ.copy()
        environment["DATA_PATH"] = str(lock_path.parent)
        result = subprocess.run(  # nosec B603
            [sys.executable, "__main__.py", "--resync", "--force"],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        after_stat = lock_path.stat()
        after = (after_stat.st_ino, after_stat.st_mtime_ns, after_stat.st_size)
        assert result.returncode != 0
        assert "deprecated" in result.stderr.lower()
        assert "currently running" in result.stderr.lower()
        assert after == before
    finally:
        assert process.stdin is not None
        process.stdin.write("stop\n")
        process.stdin.flush()
        process.wait(timeout=20)
        # A Windows venv launcher can spawn the real interpreter under a PID
        # different from Popen.pid. Compare against the value written by the
        # lock-holding interpreter before the CLI contender started.
        assert lock_path.read_text(encoding="utf-8") == expected_holder_pid
