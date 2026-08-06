"""Queries keep using the live table while a new index is staged."""

import asyncio
from contextlib import asynccontextmanager
import gc
import json

import numpy as np
import pytest
import lancedb

import app.core as core_module
import app.sync as sync_module
from app.core import QueryEngine
from app.generation_identity import (
    GENERATION_ID_FIELD,
    bind_version_generation,
)
from app.schemas import QueryRequest


@pytest.fixture(autouse=True)
def _isolate_cross_process_sync_lock(tmp_path, monkeypatch):
    """Keep every recovery lock acquisition inside this test's temp tree."""
    lock_path = tmp_path / "locks" / "sync.lock"
    monkeypatch.setattr(sync_module.settings, "DATA_PATH", lock_path.parent)
    monkeypatch.setattr(
        sync_module,
        "_file_lock",
        sync_module.SyncFileLock(lock_path),
    )


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
        self.close_calls = 0
        self.in_write_guard = False

    @asynccontextmanager
    async def database_write_guard(self):
        assert self.in_write_guard is False
        self.in_write_guard = True
        try:
            yield self
        finally:
            self.in_write_guard = False

    def _reset_database_handles_locked(self):
        self.reset_calls += 1

    async def _do_initialize(self, *, expected_version_info=None):
        self.initialize_calls += 1
        return self.initialize_results.pop(0)

    async def close(self):
        self.close_calls += 1


class _FaultInjectingSwapEngine(_SwapEngine):
    async def _do_initialize(self, *, expected_version_info=None):
        self.initialize_calls += 1
        result = self.initialize_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def _table_marker(database_path, table_name="aidefend"):
    db = lancedb.connect(str(database_path))
    table = db.open_table(table_name)
    value = table.search().select(["marker"]).limit(1).to_list()[0]["marker"]
    del table, db
    gc.collect()
    return value


def _version_commit(
    commit_sha="a" * 40,
    *,
    total_documents=1,
    generation_build_id=None,
):
    return commit_sha, {
        "generation_build_id": generation_build_id or (commit_sha * 2)[:64],
        "framework_version": "1.20260805",
        "framework_public_schema_version": "2.4",
        "framework_public_schema_source": "data/data.json",
        "framework_migrations_schema_version": "1.0",
        "framework_migrations_registry_version": "2026-08-05",
        "framework_migrations_sha256": "c" * 64,
        "total_documents": total_documents,
        "total_actionable_items": 300,
        "embedding_model": "test-model",
        "embedding_dimension": 768,
        "index_schema_version": "3.3",
        "source_kind": "github",
        "source_revision_kind": "git_commit",
        "source_revision": commit_sha,
        "source_repository": "edward-playground/aidefense-framework",
        "source_ref": commit_sha,
        "source_content_sha256": "d" * 64,
        "source_files": ["main.js", "data/framework-migrations.json"],
    }


def _bound_version(commit):
    commit_sha, metadata = commit
    return bind_version_generation(
        {"commit_sha": commit_sha, **metadata},
        allow_legacy=False,
    )


def _create_lance_table(database_path, name, marker, version_info=None, ids=None):
    database_path.mkdir(parents=True, exist_ok=True)
    rows = []
    generation_ids = ids
    if generation_ids is None and version_info is not None:
        generation_ids = [version_info[GENERATION_ID_FIELD]]
    for generation_id in generation_ids or [None]:
        row = {"marker": marker}
        if generation_id is not None:
            row[GENERATION_ID_FIELD] = generation_id
        rows.append(row)
    db = lancedb.connect(str(database_path))
    table = db.create_table(name, data=rows)
    del table, db
    gc.collect()


def _save_bound_version(version_file, version_info):
    sync_module._atomic_write_json(version_file, dict(version_info))


def _write_backup_pair(database_path, name, marker, version_info):
    path = database_path / f"{name}.lance"
    _create_lance_table(database_path, name, marker, version_info)
    sync_module._write_backup_metadata(path, version_info)
    return path


@pytest.mark.asyncio
async def test_search_remains_available_while_sync_stages_new_table(monkeypatch):
    active_version = _bound_version(_version_commit())
    engine = QueryEngine()
    engine._initialized = True
    engine._model = _EmbeddingModel()
    engine._table = _SearchTable()
    engine._active_generation_id = active_version[GENERATION_ID_FIELD]
    monkeypatch.setattr(
        core_module,
        "load_version_info",
        lambda: dict(active_version),
    )
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
async def test_successful_swap_commits_one_generation_and_retains_paired_backup(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    old_version = _bound_version(_version_commit("b" * 40))
    new_commit = _version_commit("a" * 40)
    new_version = _bound_version(new_commit)
    _create_lance_table(database_path, "aidefend", "old-active", old_version)
    _save_bound_version(version_file, old_version)
    _create_lance_table(
        database_path,
        "aidefend_new_sync",
        "new-active",
        new_version,
    )
    staged = database_path / "aidefend_new_sync.lance"

    engine = _SwapEngine([True])
    original_save = sync_module.save_version_info

    def guarded_save(commit_sha, metadata):
        assert engine.in_write_guard is True
        original_save(commit_sha, metadata)

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(sync_module, "save_version_info", guarded_save)

    await sync_module._activate_staged_database(
        staged,
        version_commit=new_commit,
    )

    assert engine.in_write_guard is False
    assert _table_marker(database_path) == "new-active"
    assert sync_module.load_version_info()[GENERATION_ID_FIELD] == new_version[
        GENERATION_ID_FIELD
    ]
    assert not sync_module._generation_activation_marker_path().exists()
    backup_paths = list(database_path.glob("aidefend_backup*.lance"))
    assert len(backup_paths) == 1
    assert _table_marker(database_path, backup_paths[0].stem) == "old-active"
    backup_version = sync_module._load_backup_metadata(backup_paths[0])
    assert backup_version[GENERATION_ID_FIELD] == old_version[GENERATION_ID_FIELD]

    assert await sync_module._cleanup_successful_sync_artifacts() is True
    assert _table_marker(database_path) == "new-active"
    assert not list(database_path.glob("aidefend_backup*.lance"))
    assert not list(database_path.glob("aidefend_backup*.version.json"))


@pytest.mark.asyncio
async def test_generation_metadata_failure_rolls_back_before_releasing_writer(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    old_version = _bound_version(_version_commit("b" * 40))
    new_commit = _version_commit("a" * 40)
    new_version = _bound_version(new_commit)
    _create_lance_table(database_path, "aidefend", "old-active", old_version)
    _save_bound_version(version_file, old_version)
    _create_lance_table(
        database_path,
        "aidefend_new_sync",
        "new-active",
        new_version,
    )
    staged = database_path / "aidefend_new_sync.lance"

    engine = _SwapEngine([True, True])

    def failing_save(_commit_sha, _metadata):
        assert engine.in_write_guard is True
        raise OSError("synthetic durable metadata failure")

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(sync_module, "save_version_info", failing_save)

    with pytest.raises(OSError, match="durable metadata failure"):
        await sync_module._activate_staged_database(
            staged,
            version_commit=new_commit,
        )

    assert engine.in_write_guard is False
    assert _table_marker(database_path) == "old-active"
    assert sync_module.load_version_info()[GENERATION_ID_FIELD] == old_version[
        GENERATION_ID_FIELD
    ]
    assert not sync_module._generation_activation_marker_path().exists()
    failed = list(database_path.glob("aidefend_failed_sync*.lance"))
    assert len(failed) == 1
    assert _table_marker(database_path, failed[0].stem) == "new-active"


@pytest.mark.asyncio
async def test_post_replace_metadata_error_keeps_proven_committed_generation(
    tmp_path, monkeypatch
):
    """Do not roll the table back after the expected metadata is durable."""
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    old_version = _bound_version(_version_commit("b" * 40))
    new_commit = _version_commit("a" * 40)
    new_version = _bound_version(new_commit)
    _create_lance_table(database_path, "aidefend", "old-active", old_version)
    _save_bound_version(version_file, old_version)
    _create_lance_table(
        database_path,
        "aidefend_new_sync",
        "new-active",
        new_version,
    )
    staged = database_path / "aidefend_new_sync.lance"

    engine = _SwapEngine([True])
    original_save = sync_module.save_version_info

    def save_then_raise(commit_sha, metadata):
        assert engine.in_write_guard is True
        original_save(commit_sha, metadata)
        raise OSError("synthetic error after atomic replace")

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(sync_module, "save_version_info", save_then_raise)

    await sync_module._activate_staged_database(
        staged,
        version_commit=new_commit,
    )

    assert engine.in_write_guard is False
    assert _table_marker(database_path) == "new-active"
    assert sync_module.load_version_info()[GENERATION_ID_FIELD] == new_version[
        GENERATION_ID_FIELD
    ]
    assert not sync_module._generation_activation_marker_path().exists()
    backup_paths = list(database_path.glob("aidefend_backup*.lance"))
    assert len(backup_paths) == 1
    assert _table_marker(database_path, backup_paths[0].stem) == "old-active"
    assert sync_module._load_backup_metadata(backup_paths[0])[
        GENERATION_ID_FIELD
    ] == old_version[GENERATION_ID_FIELD]


@pytest.mark.asyncio
async def test_failed_new_and_previous_generations_restore_older_paired_metadata(
    tmp_path, monkeypatch
):
    """Regression: never activate generation A while leaving metadata B."""
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    older_version = _bound_version(_version_commit("c" * 40))
    previous_version = _bound_version(_version_commit("b" * 40))
    new_commit = _version_commit("a" * 40)
    new_version = _bound_version(new_commit)

    _write_backup_pair(
        database_path,
        "aidefend_backup",
        "older-generation",
        older_version,
    )
    _create_lance_table(
        database_path,
        "aidefend",
        "previous-generation",
        previous_version,
    )
    _save_bound_version(version_file, previous_version)
    _create_lance_table(
        database_path,
        "aidefend_new_sync",
        "new-generation",
        new_version,
    )

    engine = _SwapEngine([False, False, True])
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)

    with pytest.raises(RuntimeError, match="newly swapped database"):
        await sync_module._activate_staged_database(
            database_path / "aidefend_new_sync.lance",
            version_commit=new_commit,
        )

    assert _table_marker(database_path) == "older-generation"
    restored_version = sync_module.load_version_info()
    assert restored_version[GENERATION_ID_FIELD] == older_version[
        GENERATION_ID_FIELD
    ]
    assert restored_version[GENERATION_ID_FIELD] != previous_version[
        GENERATION_ID_FIELD
    ]
    assert engine.initialize_calls == 3


@pytest.mark.asyncio
async def test_sidecar_write_failure_retains_proven_active_generation(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    old_version = _bound_version(_version_commit("b" * 40))
    new_commit = _version_commit("a" * 40)
    new_version = _bound_version(new_commit)
    _create_lance_table(database_path, "aidefend", "old-active", old_version)
    _save_bound_version(version_file, old_version)
    _create_lance_table(
        database_path,
        "aidefend_new_sync",
        "new-active",
        new_version,
    )

    engine = _SwapEngine([True])
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        sync_module,
        "_write_backup_metadata",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("synthetic sidecar write failure")
        ),
    )

    with pytest.raises(OSError, match="sidecar write failure"):
        await sync_module._activate_staged_database(
            database_path / "aidefend_new_sync.lance",
            version_commit=new_commit,
        )

    assert _table_marker(database_path) == "old-active"
    assert sync_module.load_version_info()[GENERATION_ID_FIELD] == old_version[
        GENERATION_ID_FIELD
    ]
    assert engine.initialize_calls == 1
    assert not list(database_path.glob("aidefend_failed_generation*.lance"))


@pytest.mark.asyncio
async def test_unbindable_legacy_active_does_not_block_verified_new_generation(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    new_commit = _version_commit("a" * 40)
    new_version = _bound_version(new_commit)
    _create_lance_table(database_path, "aidefend", "unbound-legacy")
    sync_module._atomic_write_json(
        version_file,
        {"commit_sha": "legacy", "framework_version": "legacy"},
    )
    _create_lance_table(
        database_path,
        "aidefend_new_sync",
        "new-active",
        new_version,
    )

    engine = _SwapEngine([True])
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)

    await sync_module._activate_staged_database(
        database_path / "aidefend_new_sync.lance",
        version_commit=new_commit,
    )

    assert _table_marker(database_path) == "new-active"
    assert sync_module.load_version_info()[GENERATION_ID_FIELD] == new_version[
        GENERATION_ID_FIELD
    ]
    failed = list(database_path.glob("aidefend_failed_generation*.lance"))
    assert len(failed) == 1
    assert _table_marker(database_path, failed[0].stem) == "unbound-legacy"


@pytest.mark.asyncio
async def test_startup_keeps_generation_when_atomic_metadata_matches_marker(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    previous_version = _bound_version(_version_commit("b" * 40))
    current_commit = _version_commit("a" * 40)
    current_version = _bound_version(current_commit)
    _create_lance_table(
        database_path,
        "aidefend",
        "committed-active",
        current_version,
    )
    backup_path = _write_backup_pair(
        database_path,
        "aidefend_backup",
        "old-active",
        previous_version,
    )
    engine = _SwapEngine([])

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    commit_sha, metadata = current_commit
    sync_module._write_generation_activation_marker(
        commit_sha=commit_sha,
        version_metadata=metadata,
        backup_table="aidefend_backup.lance",
        backup_metadata=sync_module._backup_metadata_path(backup_path).name,
        previous_generation_id=previous_version[GENERATION_ID_FIELD],
        staged_table="aidefend_new_sync.lance",
    )
    _save_bound_version(version_file, current_version)

    assert await sync_module.recover_incomplete_generation_activation() is True
    assert _table_marker(database_path) == "committed-active"
    assert engine.reset_calls == 0
    assert not sync_module._generation_activation_marker_path().exists()


@pytest.mark.asyncio
async def test_startup_restores_marker_bound_backup_when_metadata_is_old(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    previous_version = _bound_version(_version_commit("b" * 40))
    current_commit = _version_commit("a" * 40)
    current_version = _bound_version(current_commit)
    _create_lance_table(
        database_path,
        "aidefend",
        "uncommitted-new",
        current_version,
    )
    backup_path = _write_backup_pair(
        database_path,
        "aidefend_backup",
        "old-active",
        previous_version,
    )
    engine = _SwapEngine([True])

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    _save_bound_version(version_file, previous_version)
    commit_sha, metadata = current_commit
    sync_module._write_generation_activation_marker(
        commit_sha=commit_sha,
        version_metadata=metadata,
        backup_table="aidefend_backup.lance",
        backup_metadata=sync_module._backup_metadata_path(backup_path).name,
        previous_generation_id=previous_version[GENERATION_ID_FIELD],
        staged_table="aidefend_new_sync.lance",
    )

    assert await sync_module.recover_incomplete_generation_activation() is True
    assert _table_marker(database_path) == "old-active"
    assert sync_module.load_version_info()[GENERATION_ID_FIELD] == previous_version[
        GENERATION_ID_FIELD
    ]
    failed = list(database_path.glob("aidefend_failed_generation*.lance"))
    assert len(failed) == 1
    assert _table_marker(database_path, failed[0].stem) == "uncommitted-new"
    assert not sync_module._generation_activation_marker_path().exists()


@pytest.mark.parametrize(
    ("failure_kind", "expected_exception"),
    [
        pytest.param(
            "initialize-false",
            sync_module.GenerationRestoreRetryableError,
            id="initialization-rejected",
        ),
        pytest.param(
            "cancelled",
            asyncio.CancelledError,
            id="initialization-cancelled",
        ),
    ],
)
@pytest.mark.asyncio
async def test_startup_retryable_restore_retains_evidence_then_recovers(
    tmp_path,
    monkeypatch,
    failure_kind,
    expected_exception,
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    previous_version = _bound_version(_version_commit("b" * 40))
    current_commit = _version_commit("a" * 40)
    current_version = _bound_version(current_commit)
    _create_lance_table(
        database_path,
        "aidefend",
        "uncommitted-new",
        current_version,
    )
    backup_path = _write_backup_pair(
        database_path,
        "aidefend_backup",
        "old-active",
        previous_version,
    )
    first_result = (
        asyncio.CancelledError() if failure_kind == "cancelled" else False
    )
    engine = _FaultInjectingSwapEngine([first_result])

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    _save_bound_version(version_file, previous_version)
    commit_sha, metadata = current_commit
    sync_module._write_generation_activation_marker(
        commit_sha=commit_sha,
        version_metadata=metadata,
        backup_table=backup_path.name,
        backup_metadata=sync_module._backup_metadata_path(backup_path).name,
        previous_generation_id=previous_version[GENERATION_ID_FIELD],
        staged_table="aidefend_new_sync.lance",
    )

    with pytest.raises(expected_exception):
        await sync_module.recover_incomplete_generation_activation()

    marker_path = sync_module._generation_activation_marker_path()
    backup_metadata_path = sync_module._backup_metadata_path(backup_path)
    assert marker_path.is_file()
    assert backup_path.is_dir()
    assert backup_metadata_path.is_file()
    retained_marker = sync_module._load_generation_activation_marker()
    assert retained_marker["generation_id"] == current_version[GENERATION_ID_FIELD]
    assert retained_marker["previous_generation_id"] == previous_version[
        GENERATION_ID_FIELD
    ]
    assert retained_marker["backup_table"] == backup_path.name
    assert retained_marker["backup_metadata"] == backup_metadata_path.name
    retained_backup_version = sync_module._load_backup_metadata(backup_path)
    assert retained_backup_version[GENERATION_ID_FIELD] == previous_version[
        GENERATION_ID_FIELD
    ]
    assert sync_module._assert_table_path_generation(
        backup_path,
        retained_backup_version,
    ) == previous_version[GENERATION_ID_FIELD]
    assert not (database_path / "aidefend.lance").exists()
    assert sync_module.load_version_info()[GENERATION_ID_FIELD] == previous_version[
        GENERATION_ID_FIELD
    ]
    failed = list(database_path.glob("aidefend_failed_generation*.lance"))
    assert len(failed) == 1
    assert _table_marker(database_path, failed[0].stem) == "uncommitted-new"

    engine.initialize_results.append(True)
    assert await sync_module.recover_incomplete_generation_activation() is True

    assert _table_marker(database_path) == "old-active"
    assert sync_module.load_version_info()[GENERATION_ID_FIELD] == previous_version[
        GENERATION_ID_FIELD
    ]
    assert not marker_path.exists()
    assert not backup_path.exists()
    assert not backup_metadata_path.exists()
    assert len(list(database_path.glob("aidefend_failed_generation*.lance"))) == 1


@pytest.mark.asyncio
async def test_startup_aborts_pre_swap_marker_without_crossing_generations(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    previous_version = _bound_version(_version_commit("b" * 40))
    current_commit = _version_commit("a" * 40)
    _create_lance_table(
        database_path,
        "aidefend",
        "old-active",
        previous_version,
    )
    _save_bound_version(version_file, previous_version)
    backup_path = database_path / "aidefend_backup.lance"
    sidecar = sync_module._write_backup_metadata(backup_path, previous_version)
    engine = _SwapEngine([])

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    commit_sha, metadata = current_commit
    sync_module._write_generation_activation_marker(
        commit_sha=commit_sha,
        version_metadata=metadata,
        backup_table=backup_path.name,
        backup_metadata=sidecar.name,
        previous_generation_id=previous_version[GENERATION_ID_FIELD],
        staged_table="aidefend_new_sync.lance",
    )

    assert await sync_module.recover_incomplete_generation_activation() is True
    assert _table_marker(database_path) == "old-active"
    assert sync_module.load_version_info()[GENERATION_ID_FIELD] == previous_version[
        GENERATION_ID_FIELD
    ]
    assert engine.reset_calls == 0
    assert not sidecar.exists()
    assert not sync_module._generation_activation_marker_path().exists()


@pytest.mark.asyncio
async def test_pre_swap_rebuild_with_same_source_uses_physical_build_identity(
    tmp_path, monkeypatch
):
    """A forced same-source rebuild must not make old bytes look committed-new."""
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    same_commit = "a" * 40
    previous_version = _bound_version(
        _version_commit(same_commit, generation_build_id="b" * 64)
    )
    current_commit = _version_commit(
        same_commit,
        generation_build_id="c" * 64,
    )
    _create_lance_table(
        database_path,
        "aidefend",
        "old-physical-build",
        previous_version,
    )
    _save_bound_version(version_file, previous_version)
    backup_path = database_path / "aidefend_backup.lance"
    sidecar = sync_module._write_backup_metadata(backup_path, previous_version)
    engine = _SwapEngine([])

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    commit_sha, metadata = current_commit
    sync_module._write_generation_activation_marker(
        commit_sha=commit_sha,
        version_metadata=metadata,
        backup_table=backup_path.name,
        backup_metadata=sidecar.name,
        previous_generation_id=previous_version[GENERATION_ID_FIELD],
        staged_table="aidefend_new_sync.lance",
    )

    assert await sync_module.recover_incomplete_generation_activation() is True
    assert _table_marker(database_path) == "old-physical-build"
    assert sync_module.load_version_info()[GENERATION_ID_FIELD] == previous_version[
        GENERATION_ID_FIELD
    ]
    assert not sync_module._generation_activation_marker_path().exists()


@pytest.mark.asyncio
async def test_startup_takes_unprovable_first_generation_offline(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    current_commit = _version_commit("a" * 40)
    current_version = _bound_version(current_commit)
    _create_lance_table(
        database_path,
        "aidefend",
        "uncommitted-first",
        current_version,
    )
    engine = _SwapEngine([])

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    commit_sha, metadata = current_commit
    sync_module._write_generation_activation_marker(
        commit_sha=commit_sha,
        version_metadata=metadata,
        backup_table=None,
        staged_table="aidefend_new_sync.lance",
    )

    assert await sync_module.recover_incomplete_generation_activation() is True
    assert not (database_path / "aidefend.lance").exists()
    failed = list(database_path.glob("aidefend_failed_generation*.lance"))
    assert len(failed) == 1
    assert _table_marker(database_path, failed[0].stem) == "uncommitted-first"
    assert not sync_module._generation_activation_marker_path().exists()


@pytest.mark.asyncio
async def test_rollback_marker_cleanup_failure_remains_recoverable(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    old_version = _bound_version(_version_commit("b" * 40))
    new_commit = _version_commit("a" * 40)
    new_version = _bound_version(new_commit)
    _create_lance_table(database_path, "aidefend", "old-active", old_version)
    _save_bound_version(version_file, old_version)
    _create_lance_table(
        database_path,
        "aidefend_new_sync",
        "new-active",
        new_version,
    )
    engine = _SwapEngine([True, True])

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        sync_module,
        "save_version_info",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("synthetic metadata failure")
        ),
    )
    original_remove = sync_module._remove_generation_activation_marker
    monkeypatch.setattr(
        sync_module,
        "_remove_generation_activation_marker",
        lambda: (_ for _ in ()).throw(OSError("synthetic marker lock")),
    )

    with pytest.raises(OSError, match="metadata failure"):
        await sync_module._activate_staged_database(
            database_path / "aidefend_new_sync.lance",
            version_commit=new_commit,
        )

    assert _table_marker(database_path) == "old-active"
    assert sync_module._generation_activation_marker_path().exists()
    assert list(database_path.glob("aidefend_backup*.version.json"))

    monkeypatch.setattr(
        sync_module,
        "_remove_generation_activation_marker",
        original_remove,
    )
    assert await sync_module.recover_incomplete_generation_activation() is True
    assert _table_marker(database_path) == "old-active"
    assert sync_module.load_version_info()[GENERATION_ID_FIELD] == old_version[
        GENERATION_ID_FIELD
    ]
    assert not sync_module._generation_activation_marker_path().exists()
    assert not list(database_path.glob("aidefend_backup*.version.json"))


@pytest.mark.asyncio
async def test_rollback_metadata_write_failure_retains_verified_backup_offline(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    old_version = _bound_version(_version_commit("b" * 40))
    new_commit = _version_commit("a" * 40)
    new_version = _bound_version(new_commit)
    _create_lance_table(database_path, "aidefend", "old-active", old_version)
    _save_bound_version(version_file, old_version)
    _create_lance_table(
        database_path,
        "aidefend_new_sync",
        "new-active",
        new_version,
    )
    engine = _SwapEngine([True])

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        sync_module,
        "save_version_info",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("synthetic new metadata failure")
        ),
    )
    original_atomic_write = sync_module._atomic_write_json

    def fail_old_version_restore(path, payload):
        if (
            path == version_file
            and payload.get(GENERATION_ID_FIELD)
            == old_version[GENERATION_ID_FIELD]
        ):
            raise OSError("synthetic rollback metadata failure")
        return original_atomic_write(path, payload)

    monkeypatch.setattr(
        sync_module,
        "_atomic_write_json",
        fail_old_version_restore,
    )

    with pytest.raises(RuntimeError, match="rollback also failed"):
        await sync_module._activate_staged_database(
            database_path / "aidefend_new_sync.lance",
            version_commit=new_commit,
        )

    assert not (database_path / "aidefend.lance").exists()
    assert sync_module._generation_activation_marker_path().exists()
    retained_backups = list(database_path.glob("aidefend_backup*.lance"))
    assert len(retained_backups) == 1
    assert _table_marker(database_path, retained_backups[0].stem) == "old-active"
    assert sync_module._backup_metadata_path(retained_backups[0]).is_file()
    assert engine.in_write_guard is False


@pytest.mark.asyncio
async def test_invalid_unremovable_marker_preserves_proven_active_pair(
    tmp_path, monkeypatch
):
    import app.core as core_module

    database_path = tmp_path / "aidefend_kb.lancedb"
    version_file = tmp_path / "local_version.json"
    version = _bound_version(_version_commit("b" * 40))
    _create_lance_table(database_path, "aidefend", "proven-active", version)
    _save_bound_version(version_file, version)
    marker_path = version_file.with_name(
        sync_module.GENERATION_ACTIVATION_MARKER_FILENAME
    )
    marker_path.mkdir()
    engine = _SwapEngine([])

    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)

    assert await sync_module.recover_incomplete_generation_activation() is True
    assert _table_marker(database_path) == "proven-active"
    assert marker_path.is_dir()
    assert engine.reset_calls == 0


@pytest.mark.asyncio
async def test_core_sync_refuses_new_activation_while_marker_persists(
    tmp_path, monkeypatch
):
    version_file = tmp_path / "local_version.json"
    marker_path = version_file.with_name(
        sync_module.GENERATION_ACTIVATION_MARKER_FILENAME
    )
    marker_path.write_text("still pending", encoding="utf-8")
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)

    async def leave_marker_pending():
        return True

    monkeypatch.setattr(
        sync_module,
        "_recover_incomplete_generation_activation_locked",
        leave_marker_pending,
    )

    with pytest.raises(RuntimeError, match="refusing to start another"):
        await sync_module.core_sync()


@pytest.mark.asyncio
async def test_external_recovery_refuses_cross_process_lock_contention(
    tmp_path, monkeypatch
):
    """A second process must not inspect or mutate an in-flight activation."""
    marker_path = tmp_path / "generation_activation.pending.json"
    marker_path.write_text("pending", encoding="utf-8")
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", tmp_path / "version.json")

    holder = sync_module.SyncFileLock(sync_module.settings.DATA_PATH / "sync.lock")
    assert holder.acquire(timeout=0) is True
    try:
        with pytest.raises(RuntimeError, match="another process is synchronizing"):
            await sync_module.recover_incomplete_generation_activation()
        assert marker_path.read_text(encoding="utf-8") == "pending"
    finally:
        holder.release()


@pytest.mark.asyncio
async def test_disappearing_marker_is_absence_not_quarantine(tmp_path, monkeypatch):
    """An exists/read TOCTOU must not take a valid active generation offline."""
    import app.core as core_module

    version_file = tmp_path / "local_version.json"
    marker_path = version_file.with_name(
        sync_module.GENERATION_ACTIVATION_MARKER_FILENAME
    )
    marker_path.write_text("pending", encoding="utf-8")
    engine = _SwapEngine([])
    monkeypatch.setattr(sync_module.settings, "VERSION_FILE", version_file)
    monkeypatch.setattr(core_module, "query_engine", engine)
    monkeypatch.setattr(
        sync_module,
        "_load_generation_activation_marker",
        lambda: None,
    )

    assert await sync_module.recover_incomplete_generation_activation() is False
    assert engine.reset_calls == 0


@pytest.mark.asyncio
async def test_external_recovery_releases_lock_after_failure(monkeypatch):
    async def fail_recovery():
        raise OSError("synthetic recovery failure")

    monkeypatch.setattr(
        sync_module,
        "_recover_incomplete_generation_activation_locked",
        fail_recovery,
    )
    with pytest.raises(OSError, match="synthetic recovery failure"):
        await sync_module.recover_incomplete_generation_activation()

    successor = sync_module.SyncFileLock(sync_module.settings.DATA_PATH / "sync.lock")
    assert successor.acquire(timeout=0) is True
    successor.release()


def test_backup_sidecar_tampering_and_absence_fail_closed(tmp_path, monkeypatch):
    database_path = tmp_path / "aidefend_kb.lancedb"
    version = _bound_version(_version_commit("b" * 40))
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)
    backup_path = _write_backup_pair(
        database_path,
        "aidefend_backup",
        "old-active",
        version,
    )
    sidecar = sync_module._backup_metadata_path(backup_path)
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["version_info"]["framework_version"] = "tampered"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="generation_id does not match"):
        sync_module._load_backup_metadata(backup_path)

    sidecar.unlink()
    with pytest.raises(RuntimeError, match="no safe paired version metadata"):
        sync_module._load_backup_metadata(backup_path)


def test_mixed_or_truncated_table_generation_is_rejected(tmp_path, monkeypatch):
    database_path = tmp_path / "aidefend_kb.lancedb"
    expected = _bound_version(_version_commit("a" * 40, total_documents=2))
    other = _bound_version(_version_commit("b" * 40, total_documents=2))
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_path)

    _create_lance_table(
        database_path,
        "aidefend_new_sync",
        "mixed",
        ids=[
            expected[GENERATION_ID_FIELD],
            other[GENERATION_ID_FIELD],
        ],
    )
    with pytest.raises(RuntimeError, match="mixed, or mismatched"):
        sync_module._assert_table_path_generation(
            database_path / "aidefend_new_sync.lance",
            expected,
        )

    lancedb.connect(str(database_path)).drop_table("aidefend_new_sync")
    _create_lance_table(
        database_path,
        "aidefend_new_sync",
        "truncated",
        expected,
    )
    with pytest.raises(RuntimeError, match="row count"):
        sync_module._assert_table_path_generation(
            database_path / "aidefend_new_sync.lance",
            expected,
        )


def test_generation_version_writer_and_reader_share_exact_size_boundary():
    empty_size = len(json.dumps({"payload": ""}, indent=2).encode("utf-8"))
    filler_size = sync_module.MAX_GENERATION_VERSION_METADATA_BYTES - empty_size
    exact = {"payload": "x" * filler_size}

    assert sync_module._assert_json_payload_size(
        exact,
        maximum_bytes=sync_module.MAX_GENERATION_VERSION_METADATA_BYTES,
        label="test version metadata",
    ) == sync_module.MAX_GENERATION_VERSION_METADATA_BYTES

    with pytest.raises(RuntimeError, match="exceeds"):
        sync_module._assert_json_payload_size(
            {"payload": "x" * (filler_size + 1)},
            maximum_bytes=sync_module.MAX_GENERATION_VERSION_METADATA_BYTES,
            label="test version metadata",
        )
