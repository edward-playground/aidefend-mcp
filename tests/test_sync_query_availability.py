"""Queries keep using the live table while a new index is staged."""

from contextlib import asynccontextmanager

import numpy as np
import pytest

import app.sync as sync_module
from app.core import QueryEngine
from app.schemas import QueryRequest


class _EmbeddingModel:
    def embed(self, texts):
        return [np.zeros(768, dtype=np.float32) for _text in texts]


class _SearchTable:
    def search(self, _vector):
        return self

    def limit(self, _top_k):
        return self

    def to_list(self):
        return [
            {
                "source_id": "AID-H-001",
                "tactic": "Harden",
                "type": "technique",
                "name": "Live control",
                "text": "The existing index remains queryable during staging.",
                "pillar": "[]",
                "phase": "[]",
                "defends_against": "[]",
                "tools_opensource": "[]",
                "tools_source_available": "[]",
                "tools_commercial": "[]",
                "implementation_guidance": "[]",
                "scope_boundary": "{}",
                "warnings": "[]",
                "is_actionable": True,
                "is_parent_family": False,
                "has_code_snippets": False,
                "_distance": 0.0,
            }
        ]


class _SwapEngine:
    def __init__(self, initialize_results):
        self.initialize_results = list(initialize_results)
        self.initialize_calls = 0
        self.reset_calls = 0

    @asynccontextmanager
    async def database_write_guard(self):
        yield self

    def _reset_database_handles_locked(self):
        self.reset_calls += 1

    async def _do_initialize(self):
        self.initialize_calls += 1
        return self.initialize_results.pop(0)


def _table_marker(path, value):
    path.mkdir(parents=True)
    (path / "marker").write_text(value, encoding="utf-8")


def _active_marker(database_path):
    return (database_path / "aidefend.lance" / "marker").read_text(
        encoding="utf-8"
    )


@pytest.mark.asyncio
async def test_search_remains_available_while_sync_stages_new_table(monkeypatch):
    engine = QueryEngine()
    engine._initialized = True
    engine._model = _EmbeddingModel()
    engine._table = _SearchTable()
    monkeypatch.setattr(sync_module, "is_sync_in_progress", lambda: True)

    results = await engine.search(QueryRequest(query_text="live query", top_k=1))

    assert [result.source_id for result in results] == ["AID-H-001"]


@pytest.mark.asyncio
async def test_successful_sync_artifact_cleanup_keeps_only_active_table(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "aidefend_kb.lancedb"
    active = database_path / "aidefend.lance"
    active.mkdir(parents=True)
    for artifact_name in (
        "aidefend_backup.lance",
        "aidefend_backup_123.lance",
        "aidefend_failed_sync.lance",
        "aidefend_failed_sync_123.lance",
        "aidefend_failed_metadata.lance",
        "aidefend_new_sync.lance",
    ):
        artifact = database_path / artifact_name
        artifact.mkdir()
        (artifact / "marker").write_text("stale", encoding="utf-8")

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)

    assert await sync_module._cleanup_successful_sync_artifacts() is True
    assert active.is_dir()
    assert sorted(path.name for path in database_path.iterdir()) == [
        "aidefend.lance"
    ]


@pytest.mark.asyncio
async def test_swap_failure_falls_back_past_uncommitted_active_to_lkg_backup(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    _table_marker(database_path / "aidefend.lance", "uncommitted-active")
    _table_marker(database_path / "aidefend_backup.lance", "last-known-good")
    staged = database_path / "aidefend_new_sync.lance"
    _table_marker(staged, "new-invalid")

    # New candidate fails, interrupted active fails, older retained backup works.
    engine = _SwapEngine([False, False, True])
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(core_module, "query_engine", engine)

    with pytest.raises(RuntimeError, match="newly swapped database"):
        await sync_module._activate_staged_database(staged)

    assert _active_marker(database_path) == "last-known-good"
    failed_markers = sorted(
        (path / "marker").read_text(encoding="utf-8")
        for path in database_path.glob("aidefend_failed_sync*.lance")
    )
    assert failed_markers == ["new-invalid", "uncommitted-active"]
    assert engine.initialize_calls == 3


@pytest.mark.asyncio
async def test_swap_recovers_backup_when_active_was_missing(tmp_path, monkeypatch):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    _table_marker(database_path / "aidefend_backup.lance", "last-known-good")
    staged = database_path / "aidefend_new_sync.lance"
    _table_marker(staged, "new-invalid")

    engine = _SwapEngine([False, True])
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(core_module, "query_engine", engine)

    with pytest.raises(RuntimeError, match="newly swapped database"):
        await sync_module._activate_staged_database(staged)

    assert _active_marker(database_path) == "last-known-good"
    assert engine.initialize_calls == 2


@pytest.mark.asyncio
async def test_successful_swap_keeps_backup_until_commit_cleanup(tmp_path, monkeypatch):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    _table_marker(database_path / "aidefend.lance", "old-active")
    staged = database_path / "aidefend_new_sync.lance"
    _table_marker(staged, "new-active")

    engine = _SwapEngine([True])
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(core_module, "query_engine", engine)

    await sync_module._activate_staged_database(staged)

    assert _active_marker(database_path) == "new-active"
    backup_paths = list(database_path.glob("aidefend_backup*.lance"))
    assert len(backup_paths) == 1
    assert (backup_paths[0] / "marker").read_text(encoding="utf-8") == "old-active"

    assert await sync_module._cleanup_successful_sync_artifacts() is True
    assert _active_marker(database_path) == "new-active"
    assert not list(database_path.glob("aidefend_backup*.lance"))


@pytest.mark.asyncio
async def test_metadata_failure_restores_last_known_good_table(tmp_path, monkeypatch):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    _table_marker(database_path / "aidefend.lance", "uncommitted-new")
    _table_marker(database_path / "aidefend_backup.lance", "last-known-good")

    engine = _SwapEngine([True])
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(core_module, "query_engine", engine)

    restored = await sync_module._rollback_active_database_after_metadata_failure()

    assert restored is True
    assert _active_marker(database_path) == "last-known-good"
    failed = list(database_path.glob("aidefend_failed_metadata*.lance"))
    assert len(failed) == 1
    assert (failed[0] / "marker").read_text(encoding="utf-8") == "uncommitted-new"
    assert engine.initialize_calls == 1


@pytest.mark.asyncio
async def test_metadata_failure_takes_fresh_uncommitted_table_offline(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    _table_marker(database_path / "aidefend.lance", "uncommitted-first-sync")

    engine = _SwapEngine([])
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(core_module, "query_engine", engine)

    restored = await sync_module._rollback_active_database_after_metadata_failure()

    assert restored is False
    assert not (database_path / "aidefend.lance").exists()
    failed = list(database_path.glob("aidefend_failed_metadata*.lance"))
    assert len(failed) == 1
    assert (failed[0] / "marker").read_text(encoding="utf-8") == "uncommitted-first-sync"
    assert engine.reset_calls == 1


@pytest.mark.asyncio
async def test_metadata_failure_enumeration_error_still_takes_active_offline(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    _table_marker(database_path / "aidefend.lance", "uncommitted-new")

    engine = _SwapEngine([])
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(core_module, "query_engine", engine)

    def fail_backup_enumeration():
        raise OSError("simulated Windows artifact enumeration failure")

    monkeypatch.setattr(
        sync_module,
        "_existing_backup_artifacts",
        fail_backup_enumeration,
    )

    restored = await sync_module._rollback_active_database_after_metadata_failure()

    assert restored is False
    assert not (database_path / "aidefend.lance").exists()
    failed = list(database_path.glob("aidefend_failed_metadata*.lance"))
    assert len(failed) == 1
    assert (failed[0] / "marker").read_text(encoding="utf-8") == "uncommitted-new"
    assert engine.reset_calls == 1
