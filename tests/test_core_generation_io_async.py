"""Non-blocking and cancellation-safe generation assertion regressions."""

import asyncio
import threading

import pytest

import app.core as core_module
from app.core import QueryEngine
from app.generation_identity import GenerationIdentityError


def _ready_engine(monkeypatch, *, generation_id="a" * 64):
    version_info = {
        "framework_version": "1.20260805",
        "total_documents": 1,
    }
    monkeypatch.setattr(
        core_module,
        "load_version_info",
        lambda: dict(version_info),
    )
    monkeypatch.setattr(
        core_module,
        "bind_version_generation",
        lambda *_args, **_kwargs: {"generation_id": generation_id},
    )

    engine = QueryEngine()
    engine._initialized = True
    engine._model = object()
    engine._table = object()
    engine._active_generation_id = generation_id
    return engine


@pytest.mark.asyncio
async def test_health_generation_io_does_not_block_event_loop(monkeypatch):
    """A blocking LanceDB generation read must run outside the event loop."""
    engine = _ready_engine(monkeypatch)
    assertion_started = threading.Event()
    release_assertion = threading.Event()
    event_loop_thread = threading.get_ident()
    assertion_thread = []

    def blocking_assertion(*_args, **_kwargs):
        assertion_thread.append(threading.get_ident())
        assertion_started.set()
        if not release_assertion.wait(timeout=5):
            raise TimeoutError("test did not release generation assertion")
        return "a" * 64

    monkeypatch.setattr(
        core_module,
        "assert_table_generation",
        blocking_assertion,
    )

    # The timer prevents a regressed synchronous implementation from hanging
    # the suite. In the correct implementation the heartbeat fires first while
    # the generation worker is still blocked.
    fallback_release = threading.Timer(0.3, release_assertion.set)
    fallback_release.start()
    heartbeat = asyncio.Event()
    asyncio.get_running_loop().call_later(0.02, heartbeat.set)
    health_task = asyncio.create_task(engine.health_check())

    try:
        await asyncio.wait_for(heartbeat.wait(), timeout=1)
        assert assertion_started.is_set()
        assert health_task.done() is False
        assert len(assertion_thread) == 1
        assert assertion_thread[0] != event_loop_thread

        release_assertion.set()
        assert await asyncio.wait_for(health_task, timeout=1) is True
    finally:
        release_assertion.set()
        fallback_release.cancel()
        if not health_task.done():
            await health_task


@pytest.mark.asyncio
async def test_cancelled_generation_io_holds_reader_until_worker_exits(
    monkeypatch,
):
    """Cancellation cannot let a writer swap a table still read by a worker."""
    engine = _ready_engine(monkeypatch, generation_id="b" * 64)
    assertion_started = threading.Event()
    release_assertion = threading.Event()
    writer_entered = asyncio.Event()

    def blocking_assertion(*_args, **_kwargs):
        assertion_started.set()
        if not release_assertion.wait(timeout=5):
            raise TimeoutError("test did not release generation assertion")
        return "b" * 64

    monkeypatch.setattr(
        core_module,
        "assert_table_generation",
        blocking_assertion,
    )

    def operation(_table):
        return "unreachable"

    read_task = asyncio.create_task(engine.read_table_snapshot(operation))
    assert await asyncio.to_thread(assertion_started.wait, 5)
    read_task.cancel()
    await asyncio.sleep(0)

    async def take_writer():
        async with engine.database_write_guard():
            writer_entered.set()

    writer_task = asyncio.create_task(take_writer())
    await asyncio.sleep(0)

    assert read_task.done() is False
    assert writer_entered.is_set() is False

    release_assertion.set()
    with pytest.raises(asyncio.CancelledError):
        await read_task
    await asyncio.wait_for(writer_task, timeout=1)
    assert writer_entered.is_set() is True


@pytest.mark.asyncio
async def test_generation_assertion_failures_remain_fail_closed(monkeypatch):
    engine = _ready_engine(monkeypatch)

    def reject_generation(*_args, **_kwargs):
        raise GenerationIdentityError("table generation mismatch")

    monkeypatch.setattr(
        core_module,
        "assert_table_generation",
        reject_generation,
    )

    stats = await engine.get_stats()

    assert stats["initialized"] is False
    assert stats["document_count"] == 0
    assert "table generation mismatch" in stats["error"]
    assert await engine.health_check() is False
