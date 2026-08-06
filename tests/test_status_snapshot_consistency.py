"""Generation-consistency regressions for MCP and REST status reporting."""

import asyncio
import threading

import pytest

import app.core as core_module
import app.main as main_module
import mcp_server
from app.core import QueryEngine, QueryEngineError
from app.schemas import QueryRequest


class _BlockingTable:
    def __init__(self, row_count, started, release):
        self._row_count = row_count
        self._started = started
        self._release = release

    def count_rows(self):
        self._started.set()
        if not self._release.wait(timeout=5):
            raise TimeoutError("test did not release the table count")
        return self._row_count


class _StaticTable:
    def __init__(self, row_count):
        self._row_count = row_count

    def count_rows(self):
        return self._row_count


@pytest.mark.asyncio
async def test_get_stats_pairs_table_and_version_during_concurrent_activation(
    monkeypatch,
):
    """A writer cannot split the table count from its version metadata."""
    old_version = {"framework_version": "1.20260805", "source_revision": "old"}
    new_version = {"framework_version": "1.20260806", "source_revision": "new"}
    active = {"version_info": old_version}
    count_started = threading.Event()
    release_count = threading.Event()

    monkeypatch.setattr(
        core_module,
        "load_version_info",
        lambda: dict(active["version_info"]),
    )
    monkeypatch.setattr(
        core_module,
        "assert_table_generation",
        lambda *_args, **_kwargs: "test-generation",
    )

    engine = QueryEngine()
    engine._initialized = True
    engine._model = object()
    engine._table = _BlockingTable(1208, count_started, release_count)

    stats_task = asyncio.create_task(engine.get_stats())
    assert await asyncio.to_thread(count_started.wait, 5)

    async def activate_new_generation():
        async with engine.database_write_guard():
            engine._table = _StaticTable(1210)
            active["version_info"] = new_version

    writer_task = asyncio.create_task(activate_new_generation())
    await asyncio.sleep(0)
    assert not writer_task.done()

    release_count.set()
    old_stats = await stats_task
    await writer_task

    assert old_stats["document_count"] == 1208
    assert old_stats["framework_version"] == "1.20260805"
    assert old_stats["version_info"] == old_version

    new_stats = await engine.get_stats()
    assert new_stats["document_count"] == 1210
    assert new_stats["framework_version"] == "1.20260806"
    assert new_stats["version_info"] == new_version


@pytest.mark.asyncio
async def test_get_stats_waits_for_uninitialized_engine_activation(monkeypatch):
    """Initialization state is sampled only after an in-flight writer exits."""
    old_version = {"framework_version": "1.20260805", "source_revision": "old"}
    new_version = {"framework_version": "1.20260806", "source_revision": "new"}
    active = {"version_info": old_version}
    writer_started = asyncio.Event()
    allow_activation = asyncio.Event()

    monkeypatch.setattr(
        core_module,
        "load_version_info",
        lambda: dict(active["version_info"]),
    )
    monkeypatch.setattr(
        core_module,
        "assert_table_generation",
        lambda *_args, **_kwargs: "test-generation",
    )

    engine = QueryEngine()

    async def activate_new_generation():
        async with engine.database_write_guard():
            writer_started.set()
            await allow_activation.wait()
            engine._table = _StaticTable(1210)
            engine._model = object()
            engine._initialized = True
            active["version_info"] = new_version

    writer_task = asyncio.create_task(activate_new_generation())
    await writer_started.wait()
    stats_task = asyncio.create_task(engine.get_stats())
    await asyncio.sleep(0)

    assert not stats_task.done()
    allow_activation.set()
    await writer_task
    stats = await stats_task

    assert stats["initialized"] is True
    assert stats["document_count"] == 1210
    assert stats["framework_version"] == "1.20260806"
    assert stats["version_info"] == new_version


@pytest.mark.asyncio
async def test_ready_status_and_health_fail_closed_without_generation_metadata(
    monkeypatch,
):
    engine = QueryEngine()
    engine._initialized = True
    engine._model = object()
    engine._table = _StaticTable(1)
    monkeypatch.setattr(core_module, "load_version_info", lambda: None)

    stats = await engine.get_stats()

    assert stats["initialized"] is False
    assert stats["document_count"] == 0
    assert "usable version metadata" in stats["error"]
    assert await engine.health_check() is False


@pytest.mark.asyncio
async def test_vector_searches_fail_closed_without_generation_metadata(monkeypatch):
    engine = QueryEngine()
    engine._initialized = True
    engine._model = object()
    engine._table = _StaticTable(1)
    engine._active_generation_id = "a" * 64
    monkeypatch.setattr(core_module, "load_version_info", lambda: None)

    request = QueryRequest(query_text="prompt injection defense", top_k=1)

    with pytest.raises(QueryEngineError, match="usable version metadata"):
        await engine.search(request)
    with pytest.raises(QueryEngineError, match="usable version metadata"):
        await engine.search_batch([request])


@pytest.mark.asyncio
async def test_cancelled_table_read_keeps_reader_lock_until_worker_exits(
    monkeypatch,
):
    generation_id = "a" * 64
    worker_started = threading.Event()
    release_worker = threading.Event()
    writer_entered = asyncio.Event()

    monkeypatch.setattr(core_module, "load_version_info", lambda: {"legacy": True})
    monkeypatch.setattr(
        core_module,
        "bind_version_generation",
        lambda *_args, **_kwargs: {"generation_id": generation_id},
    )

    engine = QueryEngine()
    engine._initialized = True
    engine._table = object()
    engine._active_generation_id = generation_id

    def blocking_read(_table):
        worker_started.set()
        if not release_worker.wait(timeout=5):
            raise TimeoutError("test did not release blocking table read")
        return "complete"

    read_task = asyncio.create_task(engine.read_table(blocking_read))
    assert await asyncio.to_thread(worker_started.wait, 5)
    read_task.cancel()
    await asyncio.sleep(0)

    async def take_writer():
        async with engine.database_write_guard():
            writer_entered.set()

    writer_task = asyncio.create_task(take_writer())
    await asyncio.sleep(0)

    assert read_task.done() is False
    assert writer_entered.is_set() is False

    release_worker.set()
    with pytest.raises(asyncio.CancelledError):
        await read_task
    await asyncio.wait_for(writer_task, timeout=1)
    assert writer_entered.is_set() is True


@pytest.mark.asyncio
async def test_cancelled_batch_search_drains_all_workers_before_writer_enters(
    monkeypatch,
):
    generation_id = "b" * 64
    workers_started = threading.Event()
    release_workers = threading.Event()
    writer_entered = asyncio.Event()
    count_lock = threading.Lock()
    started_count = 0

    monkeypatch.setattr(core_module, "load_version_info", lambda: {"legacy": True})
    monkeypatch.setattr(
        core_module,
        "bind_version_generation",
        lambda *_args, **_kwargs: {"generation_id": generation_id},
    )

    class _Model:
        def embed(self, texts):
            return [[float(index)] for index, _text in enumerate(texts)]

    engine = QueryEngine()
    engine._initialized = True
    engine._model = _Model()
    engine._table = object()
    engine._active_generation_id = generation_id

    def blocking_search(_embedding, _top_k):
        nonlocal started_count
        with count_lock:
            started_count += 1
            if started_count == 2:
                workers_started.set()
        if not release_workers.wait(timeout=5):
            raise TimeoutError("test did not release batch search workers")
        return []

    monkeypatch.setattr(engine, "_perform_search", blocking_search)
    requests = [
        QueryRequest(query_text="prompt injection defense", top_k=1),
        QueryRequest(query_text="model supply chain defense", top_k=1),
    ]

    search_task = asyncio.create_task(engine.search_batch(requests))
    assert await asyncio.to_thread(workers_started.wait, 5)
    search_task.cancel()
    await asyncio.sleep(0)

    async def take_writer():
        async with engine.database_write_guard():
            writer_entered.set()

    writer_task = asyncio.create_task(take_writer())
    await asyncio.sleep(0)

    assert search_task.done() is False
    assert writer_entered.is_set() is False

    release_workers.set()
    with pytest.raises(asyncio.CancelledError):
        await search_task
    await asyncio.wait_for(writer_task, timeout=1)
    assert writer_entered.is_set() is True


@pytest.mark.asyncio
async def test_mcp_status_keeps_stats_snapshot_when_generation_switches(
    monkeypatch,
):
    """MCP rendering must not re-read metadata after get_stats returns."""
    old_version = {
        "framework_version": "1.20260805",
        "source_revision": "old-generation",
        "source_kind": "github",
        "last_synced_at": "2026-08-05T00:00:00+00:00",
        "framework_public_schema_version": "2.3",
        "index_schema_version": "3.3",
        "framework_migrations_schema_version": "1.0",
    }
    new_version = {
        "framework_version": "1.20260806",
        "source_revision": "new-generation",
        "source_kind": "github",
        "last_synced_at": "2026-08-06T00:00:00+00:00",
    }
    active = {"version_info": old_version}
    snapshot_captured = asyncio.Event()
    generation_switched = asyncio.Event()

    async def get_stats():
        snapshot = dict(active["version_info"])
        snapshot_captured.set()
        await generation_switched.wait()
        return {
            "initialized": True,
            "document_count": 1208,
            "model_loaded": True,
            "embedding_model": "test-model",
            "framework_version": snapshot["framework_version"],
            "version_info": snapshot,
        }

    async def switch_generation():
        await snapshot_captured.wait()
        active["version_info"] = new_version
        generation_switched.set()

    late_reads = []
    monkeypatch.setattr(mcp_server.query_engine, "get_stats", get_stats)
    monkeypatch.setattr(mcp_server, "get_last_sync_error", lambda: None)
    monkeypatch.setattr(
        mcp_server,
        "load_version_info",
        lambda: late_reads.append(True) or dict(active["version_info"]),
    )

    status_task = asyncio.create_task(mcp_server.handle_status())
    await asyncio.gather(status_task, switch_generation())
    rendered = status_task.result()[0].text

    assert "Framework Version:** 1.20260805" in rendered
    assert "Framework Source Revision:** old-gene" in rendered
    assert "Framework Public Schema:** 2.3" in rendered
    assert "MCP Index Schema:** 3.3" in rendered
    assert "Framework Migration Registry Schema:** 1.0" in rendered
    assert "old-gene" in rendered
    assert "1.20260806" not in rendered
    assert "new-gene" not in rendered
    assert late_reads == []


@pytest.mark.asyncio
async def test_health_uses_version_metadata_from_stats_snapshot(monkeypatch):
    """Health staleness must use the generation paired with its DB stats."""
    engine = type("Engine", (), {})()
    engine.is_ready = True

    async def get_stats():
        return {
            "initialized": True,
            "document_count": 1208,
            "model_loaded": True,
            "version_info": {"last_synced_at": "2000-01-01T00:00:00+00:00"},
        }

    engine.get_stats = get_stats
    monkeypatch.setattr(main_module, "query_engine", engine)
    monkeypatch.setattr(
        main_module,
        "load_version_info",
        lambda: (_ for _ in ()).throw(
            AssertionError("health must not perform a late version-file read")
        ),
    )

    response = await main_module.health_check()

    assert response.status_code == 200
    assert b'"status":"degraded"' in response.body
