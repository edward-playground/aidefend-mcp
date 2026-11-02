"""Embedding vectors are reused and served only with the runtime that produced them."""

import json

import numpy as np
import pytest

import mcp_server
from app.embedding_cache import (
    EmbeddingCache,
    embedding_runtime_identity,
    embedding_runtime_status,
)
from app.config import settings
from app.generation_identity import generation_fingerprint, generation_id

MODEL = "Xenova/multilingual-e5-base"
OLD_RUNTIME = {"fastembed": "0.9.1", "onnxruntime": "1.28.0"}


def _write_cache(path, runtime):
    cache = {
        "cache_version": "1.0",
        "schema_version": settings.EMBEDDING_CACHE_SCHEMA_VERSION,
        "model_name": MODEL,
        "model_dimension": 768,
        "embeddings": {
            "abc123": {
                "source_id": "AID-H-001",
                "content_hash": "abc123",
                "model_name": MODEL,
                "embedding": [0.1] * 768,
                "created_at": "2026-10-01T00:00:00",
            }
        },
        "metadata": {"created_at": "2026-10-01T00:00:00", "last_updated": "2026-10-01T00:00:00"},
    }
    if runtime is not None:
        cache["embedding_runtime"] = runtime
    path.write_text(json.dumps(cache), encoding="utf-8")


def test_runtime_identity_names_the_installed_inference_stack():
    import fastembed
    import onnxruntime

    assert embedding_runtime_identity() == {
        "fastembed": fastembed.__version__,
        "onnxruntime": onnxruntime.__version__,
    }


def test_cache_from_the_same_runtime_is_reused(tmp_path):
    path = tmp_path / "cache.json"
    _write_cache(path, embedding_runtime_identity())
    cache = EmbeddingCache(path, MODEL, 768)
    assert cache.get("abc123") is not None


@pytest.mark.parametrize("recorded", [OLD_RUNTIME, None], ids=["other-runtime", "unrecorded"])
def test_cache_from_another_or_unrecorded_runtime_is_discarded(tmp_path, recorded):
    path = tmp_path / "cache.json"
    _write_cache(path, recorded)
    cache = EmbeddingCache(path, MODEL, 768)
    assert cache.cache["embeddings"] == {}
    assert cache.get("abc123") is None
    assert cache.cache["embedding_runtime"] == embedding_runtime_identity()


def test_saved_cache_records_the_runtime_that_produced_it(tmp_path):
    path = tmp_path / "cache.json"
    cache = EmbeddingCache(path, MODEL, 768, runtime=OLD_RUNTIME)
    cache.set("abc123", "AID-H-001", np.zeros(768, dtype=np.float32))
    cache.save()
    assert json.loads(path.read_text(encoding="utf-8"))["embedding_runtime"] == OLD_RUNTIME
    assert EmbeddingCache(path, MODEL, 768, runtime=OLD_RUNTIME).get("abc123") is not None
    assert EmbeddingCache(path, MODEL, 768).get("abc123") is None


def test_status_compares_indexed_and_current_runtime():
    current = embedding_runtime_identity()
    assert embedding_runtime_status({"embedding_runtime": current})[
        "embedding_runtime_matches_index"
    ] is True
    assert embedding_runtime_status({"embedding_runtime": OLD_RUNTIME})[
        "embedding_runtime_matches_index"
    ] is False
    for legacy in [None, {}, {"embedding_runtime": "1.28.0"}]:
        status = embedding_runtime_status(legacy)
        assert status["embedding_runtime"] is None
        assert status["embedding_runtime_matches_index"] is None
        assert status["current_embedding_runtime"] == current


def test_runtime_binds_new_generations_without_changing_legacy_identity():
    legacy = {"commit_sha": "a" * 40, "framework_version": "1.20261101", "total_documents": 1}
    assert "embedding_runtime" not in generation_fingerprint(legacy)
    first = generation_id(generation_fingerprint({**legacy, "embedding_runtime": OLD_RUNTIME}))
    second = generation_id(
        generation_fingerprint({**legacy, "embedding_runtime": embedding_runtime_identity()})
    )
    assert first != second
    assert generation_id(generation_fingerprint(legacy)) not in {first, second}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "recorded,expected",
    [
        ("current", None),
        (OLD_RUNTIME, "queries use a different runtime"),
        (None, "Not recorded"),
    ],
)
async def test_mcp_status_reports_runtime_mismatch(monkeypatch, recorded, expected):
    version_info = {"framework_version": "1.20261101"}
    if recorded == "current":
        version_info["embedding_runtime"] = embedding_runtime_identity()
    elif recorded is not None:
        version_info["embedding_runtime"] = recorded

    async def stats():
        return {
            "initialized": True,
            "document_count": 1267,
            "model_loaded": True,
            "embedding_model": MODEL,
            "version_info": version_info,
        }

    monkeypatch.setattr(mcp_server.query_engine, "get_stats", stats)
    monkeypatch.setattr(mcp_server, "get_last_sync_error", lambda: None)
    text = (await mcp_server.handle_status())[0].text
    assert "**Embedding Runtime:** fastembed " in text
    if expected is None:
        assert "Index Embedding Runtime" not in text
    else:
        assert expected in text
