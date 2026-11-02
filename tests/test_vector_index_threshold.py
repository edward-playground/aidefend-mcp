"""Small tables keep exact vector search instead of an approximate index."""

import lancedb
import pytest

import app.sync as sync_module
import scripts.create_lancedb_index as index_script
from app.config import settings


class FakeTable:
    def __init__(self, rows):
        self.rows = rows
        self.created = []

    def list_indices(self):
        return []

    def count_rows(self):
        return self.rows

    def create_index(self, **kwargs):
        self.created.append(kwargs)


@pytest.fixture
def fake_table(tmp_path, monkeypatch):
    table = FakeTable(0)

    class FakeDatabase:
        def open_table(self, name):
            assert name == "aidefend"
            return table

    monkeypatch.setattr(settings, "DB_PATH", tmp_path)
    monkeypatch.setattr(settings, "AUTO_CREATE_INDEX", True)
    monkeypatch.setattr(lancedb, "connect", lambda _path: FakeDatabase())
    return table


def test_default_threshold_keeps_the_current_corpus_on_exact_search():
    assert settings.VECTOR_INDEX_MIN_ROWS == 10_000


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [1_267, 9_999])
async def test_sync_skips_index_below_threshold(fake_table, rows):
    fake_table.rows = rows
    assert await sync_module._create_vector_index_if_needed() is True
    assert fake_table.created == []


@pytest.mark.asyncio
async def test_sync_indexes_a_table_at_the_threshold(fake_table):
    fake_table.rows = settings.VECTOR_INDEX_MIN_ROWS
    assert await sync_module._create_vector_index_if_needed() is True
    assert fake_table.created == [
        {
            "metric": "cosine",
            "num_partitions": 256,
            "num_sub_vectors": settings.EMBEDDING_DIMENSION // 16,
        }
    ]


@pytest.mark.asyncio
async def test_threshold_is_configurable(fake_table, monkeypatch):
    monkeypatch.setattr(settings, "VECTOR_INDEX_MIN_ROWS", 1_000)
    fake_table.rows = 1_267
    assert await sync_module._create_vector_index_if_needed() is True
    assert len(fake_table.created) == 1


@pytest.mark.asyncio
async def test_maintenance_script_never_indexes_or_prompts_below_threshold(
    fake_table, monkeypatch
):
    def no_prompt(_message):
        raise AssertionError("index maintenance must not prompt")

    monkeypatch.setattr("builtins.input", no_prompt)
    fake_table.rows = 1_267
    assert await index_script.create_index() is True
    assert fake_table.created == []

    fake_table.rows = settings.VECTOR_INDEX_MIN_ROWS
    assert await index_script.create_index() is True
    assert len(fake_table.created) == 1
