"""Test schema version cache invalidation."""

import pytest
import json
from pathlib import Path
from app.embedding_cache import EmbeddingCache
from app.config import settings
import numpy as np


def test_schema_version_mismatch_invalidates_cache(tmp_path):
    """Test that cache is invalidated when schema version changes."""

    cache_file = tmp_path / "test_cache.json"

    # Create cache with old schema version
    old_cache = {
        "cache_version": "1.0",
        "schema_version": "0.9",  # Old version (different from current)
        "model_name": "Xenova/multilingual-e5-base",
        "model_dimension": 768,
        "embeddings": {
            "abc123": {
                "source_id": "AID-TEST-001",
                "content_hash": "abc123",
                "model_name": "Xenova/multilingual-e5-base",
                "embedding": [0.1] * 768,
                "created_at": "2024-01-01T00:00:00"
            }
        },
        "metadata": {
            "created_at": "2024-01-01T00:00:00",
            "last_updated": "2024-01-01T00:00:00"
        }
    }

    with open(cache_file, 'w') as f:
        json.dump(old_cache, f)

    # Load cache with current schema version
    cache = EmbeddingCache(
        cache_file=cache_file,
        model_name="Xenova/multilingual-e5-base",
        dimension=768
    )

    # Cache should be invalidated (empty)
    assert len(cache.cache["embeddings"]) == 0
    assert cache.cache["schema_version"] == settings.CACHE_SCHEMA_VERSION

    print("✅ Schema version mismatch correctly invalidated cache")


def test_schema_version_match_preserves_cache(tmp_path):
    """Test that cache is preserved when schema version matches."""

    cache_file = tmp_path / "test_cache.json"

    # Create cache with CURRENT schema version
    current_cache = {
        "cache_version": "1.0",
        "schema_version": settings.CACHE_SCHEMA_VERSION,  # Current version
        "model_name": "Xenova/multilingual-e5-base",
        "model_dimension": 768,
        "embeddings": {
            "abc123": {
                "source_id": "AID-TEST-001",
                "content_hash": "abc123",
                "model_name": "Xenova/multilingual-e5-base",
                "embedding": [0.1] * 768,
                "created_at": "2024-01-01T00:00:00"
            }
        },
        "metadata": {
            "created_at": "2024-01-01T00:00:00",
            "last_updated": "2024-01-01T00:00:00"
        }
    }

    with open(cache_file, 'w') as f:
        json.dump(current_cache, f)

    # Load cache
    cache = EmbeddingCache(
        cache_file=cache_file,
        model_name="Xenova/multilingual-e5-base",
        dimension=768
    )

    # Cache should be preserved
    assert len(cache.cache["embeddings"]) == 1
    assert "abc123" in cache.cache["embeddings"]
    assert cache.cache["schema_version"] == settings.CACHE_SCHEMA_VERSION

    print("✅ Matching schema version preserved cache")


def test_cache_save_includes_schema_version(tmp_path):
    """Test that saving cache persists schema version."""

    cache_file = tmp_path / "test_cache.json"

    # Create new cache
    cache = EmbeddingCache(
        cache_file=cache_file,
        model_name="Xenova/multilingual-e5-base",
        dimension=768
    )

    # Add an embedding
    test_embedding = np.array([0.1] * 768, dtype=np.float32)
    cache.set("test_hash", "AID-TEST-001", test_embedding)

    # Save cache
    cache.save()

    # Load cache file and verify schema version
    with open(cache_file, 'r') as f:
        saved_cache = json.load(f)

    assert "schema_version" in saved_cache
    assert saved_cache["schema_version"] == settings.CACHE_SCHEMA_VERSION
    assert len(saved_cache["embeddings"]) == 1

    print("✅ Cache save correctly persists schema version")


def test_new_cache_has_schema_version(tmp_path):
    """Test that newly created cache includes schema version."""

    cache_file = tmp_path / "test_cache.json"

    # Create new cache (file doesn't exist)
    cache = EmbeddingCache(
        cache_file=cache_file,
        model_name="Xenova/multilingual-e5-base",
        dimension=768
    )

    # Check that schema version is set
    assert "schema_version" in cache.cache
    assert cache.cache["schema_version"] == settings.CACHE_SCHEMA_VERSION

    print("✅ New cache has schema version")


if __name__ == "__main__":
    import tempfile

    print("=" * 70)
    print("SCHEMA VERSIONING TESTS")
    print("=" * 70)
    print()

    with tempfile.TemporaryDirectory() as tmpdir:
        test_schema_version_mismatch_invalidates_cache(Path(tmpdir) / "test1")
        test_schema_version_match_preserves_cache(Path(tmpdir) / "test2")
        test_cache_save_includes_schema_version(Path(tmpdir) / "test3")
        test_new_cache_has_schema_version(Path(tmpdir) / "test4")

    print()
    print("=" * 70)
    print("✅ ALL SCHEMA VERSIONING TESTS PASSED!")
    print("=" * 70)
