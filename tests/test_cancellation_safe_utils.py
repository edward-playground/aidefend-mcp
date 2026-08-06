import asyncio

import anyio
import pytest

from app.utils import _await_cancellation_safe


@pytest.mark.asyncio
async def test_anyio_level_cancellation_drains_without_busy_spin(monkeypatch):
    release_worker = asyncio.Event()
    worker_completed = asyncio.Event()
    real_shield = asyncio.shield
    shield_calls = 0
    busy_spin_tripwire = 10

    async def blocked_operation():
        await release_worker.wait()
        worker_completed.set()

    def counting_shield(awaitable):
        nonlocal shield_calls
        shield_calls += 1
        # Make the old level-cancellation loop terminate deterministically
        # instead of consuming a full test timeout.
        if shield_calls == busy_spin_tripwire:
            release_worker.set()
        return real_shield(awaitable)

    monkeypatch.setattr(asyncio, "shield", counting_shield)
    fallback_release = asyncio.get_running_loop().call_later(
        0.05,
        release_worker.set,
    )
    try:
        with anyio.CancelScope() as cancel_scope:
            cancel_scope.cancel()
            await _await_cancellation_safe(
                blocked_operation(),
                task_name="level-cancel-drain-test",
            )
    finally:
        fallback_release.cancel()
        release_worker.set()

    assert worker_completed.is_set()
    assert shield_calls == 2


@pytest.mark.asyncio
async def test_repeated_direct_task_cancellation_still_drains_worker():
    worker_started = asyncio.Event()
    release_worker = asyncio.Event()
    worker_completed = asyncio.Event()

    async def blocked_operation():
        worker_started.set()
        await release_worker.wait()
        worker_completed.set()

    caller = asyncio.create_task(
        _await_cancellation_safe(
            blocked_operation(),
            task_name="repeated-direct-cancel-drain-test",
        )
    )
    await worker_started.wait()

    caller.cancel()
    await asyncio.sleep(0)
    assert not caller.done()

    caller.cancel()
    await asyncio.sleep(0)
    assert not caller.done()
    assert not worker_completed.is_set()

    release_worker.set()
    with pytest.raises(asyncio.CancelledError):
        await caller

    assert worker_completed.is_set()
