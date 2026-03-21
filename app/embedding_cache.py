"""
Embedding cache system for AIDEFEND MCP Service.

Provides persistent caching of document embeddings to speed up subsequent syncs.
Cache entries are permanent and only cleaned up when documents are deleted from
the framework (no time-based expiration).
"""

import hashlib
import json
from pathlib import Path
from typing import Optional, Set, Dict, Any, List
from datetime import datetime
import numpy as np

from app.logger import get_logger
from app.config import settings

logger = get_logger(__name__)


def compute_content_hash(text: str, model_name: str) -> str:
    """
    Compute a unique hash for document content and model combination.

    Args:
        text: Document text content
        model_name: Embedding model name (e.g., "Xenova/multilingual-e5-base")

    Returns:
        SHA-256 hash string

    Note:
        The hash includes model_name so that changing models invalidates old cache.
    """
    content = f"{text}|{model_name}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


class EmbeddingCache:
    """
    Persistent cache for document embeddings.

    Cache strategy:
    - Permanent retention (no time-based expiration)
    - Content-hash based lookup (auto-invalidates when content changes)
    - Model-aware (different models produce different hashes)
    - Auto-cleanup of deleted documents before each sync
    """

    def __init__(self, cache_file: Path, model_name: str, dimension: int):
        """
        Initialize embedding cache.

        Args:
            cache_file: Path to cache JSON file
            model_name: Current embedding model name
            dimension: Embedding dimension (e.g., 768)
        """
        self.cache_file = cache_file
        self.model_name = model_name
        self.dimension = dimension
        self.cache = self._load_cache()
        self._hits = 0
        self._misses = 0

    def _load_cache(self) -> Dict[str, Any]:
        """Load cache from disk or create new cache structure."""
        if not self.cache_file.exists():
            logger.info(f"No existing cache found at {self.cache_file}, creating new cache")
            return self._create_empty_cache()

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            # Validate cache structure
            if not isinstance(cache, dict) or "embeddings" not in cache:
                logger.warning(f"Invalid cache structure, creating new cache")
                return self._create_empty_cache()

            # Check if schema version changed
            cached_schema = cache.get("schema_version", "1.0")
            if cached_schema != settings.CACHE_SCHEMA_VERSION:
                logger.warning(
                    f"🔄 Cache schema changed from '{cached_schema}' to '{settings.CACHE_SCHEMA_VERSION}'. "
                    f"Invalidating {len(cache.get('embeddings', {}))} cached entries for safety. "
                    f"This ensures data consistency after metadata format changes."
                )
                return self._create_empty_cache()

            # Check if model changed
            cached_model = cache.get("model_name", "unknown")
            if cached_model != self.model_name:
                logger.warning(
                    f"Embedding model changed from '{cached_model}' to '{self.model_name}'. "
                    f"Old cache entries will be ignored (but not deleted)."
                )

            logger.info(
                f"✅ Loaded cache: {len(cache['embeddings'])} entries, "
                f"schema={cached_schema}, model={cached_model}"
            )
            return cache

        except Exception as e:
            logger.error(f"Failed to load cache: {e}. Creating new cache.")
            return self._create_empty_cache()

    def _create_empty_cache(self) -> Dict[str, Any]:
        """Create an empty cache structure."""
        return {
            "cache_version": "1.0",
            "schema_version": settings.CACHE_SCHEMA_VERSION,
            "model_name": self.model_name,
            "model_dimension": self.dimension,
            "embeddings": {},
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            }
        }

    def get(self, content_hash: str) -> Optional[np.ndarray]:
        """
        Retrieve embedding from cache by content hash.

        Args:
            content_hash: SHA-256 hash of (text + model_name)

        Returns:
            Numpy array of embedding vector, or None if not in cache
        """
        entry = self.cache["embeddings"].get(content_hash)

        if entry is None:
            self._misses += 1
            return None

        # Check if model matches (model change invalidates cache)
        if entry.get("model_name") != self.model_name:
            self._misses += 1
            return None

        self._hits += 1

        try:
            embedding = np.array(entry["embedding"], dtype=np.float32)
            return embedding
        except Exception as e:
            logger.error(f"Failed to deserialize cached embedding: {e}")
            self._misses += 1
            return None

    def set(self, content_hash: str, source_id: str, embedding: np.ndarray):
        """
        Store embedding in cache.

        Args:
            content_hash: SHA-256 hash of (text + model_name)
            source_id: Document source ID (e.g., "AID-H-001")
            embedding: Numpy array of embedding vector
        """
        self.cache["embeddings"][content_hash] = {
            "source_id": source_id,
            "content_hash": content_hash,
            "model_name": self.model_name,
            "embedding": embedding.tolist(),
            "created_at": datetime.now().isoformat()
        }

    def auto_cleanup(self, current_doc_ids: Set[str]):
        """
        Automatically clean up cache entries for deleted documents.

        This is the ONLY cleanup strategy - no time-based or size-based expiration.
        Old cache entries remain valid as long as:
        1. The document still exists in the framework
        2. The content hasn't changed (hash mismatch auto-invalidates)

        Uses copy-on-write to avoid corrupting the cache dict if interrupted.

        Args:
            current_doc_ids: Set of document IDs currently in the framework
        """
        before_count = len(self.cache["embeddings"])

        if before_count == 0:
            logger.info("🧹 Cache is empty, nothing to clean")
            return

        logger.info(f"🧹 Running cache cleanup (checking {before_count} entries)...")

        # Build new dict first (copy-on-write), then swap atomically
        # This prevents corruption if the process is interrupted mid-cleanup
        cleaned = {
            hash_key: entry
            for hash_key, entry in self.cache["embeddings"].items()
            if entry.get("source_id") in current_doc_ids
        }

        removed = before_count - len(cleaned)

        # Atomic swap of the embeddings dict
        self.cache["embeddings"] = cleaned

        if removed > 0:
            logger.info(f"✅ Cache cleanup: removed {removed} entries for deleted documents, kept {len(cleaned)} entries")
        else:
            logger.info(f"✅ Cache is healthy: all {len(cleaned)} entries are valid")

    def save(self):
        """Save cache to disk."""
        try:
            # Update metadata
            self.cache["metadata"]["last_updated"] = datetime.now().isoformat()
            self.cache["model_name"] = self.model_name
            self.cache["model_dimension"] = self.dimension
            self.cache["schema_version"] = settings.CACHE_SCHEMA_VERSION

            # Ensure directory exists
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Write to temp file first, then atomic rename (safer)
            temp_file = self.cache_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2)

            # Atomic rename
            temp_file.replace(self.cache_file)

            cache_size_mb = self.cache_file.stat().st_size / (1024 * 1024)
            logger.info(
                f"✅ Cache saved: {len(self.cache['embeddings'])} entries, "
                f"{cache_size_mb:.1f}MB, schema={settings.CACHE_SCHEMA_VERSION}"
            )

        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        cache_size_bytes = self.cache_file.stat().st_size if self.cache_file.exists() else 0
        cache_size_mb = cache_size_bytes / (1024 * 1024)

        return {
            "total_entries": len(self.cache["embeddings"]),
            "cache_size_mb": cache_size_mb,
            "model": self.model_name,
            "dimension": self.dimension,
            "hit_rate": self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0.0,
            "hits": self._hits,
            "misses": self._misses
        }
