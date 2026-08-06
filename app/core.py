"""
Core query engine for AIDEFEND MCP Service.
Handles vector search and context retrieval.
"""

import asyncio
import gc
import json
import math
import re
import lancedb
from contextlib import asynccontextmanager
from typing import Any, List, Mapping, Optional, Dict
from pathlib import Path
from fastembed import TextEmbedding
from aiorwlock import RWLock

from app.config import settings
from app.logger import get_logger
from app.schemas import QueryRequest, ContextChunk
from app.utils import _await_cancellation_safe, load_version_info
from app.generation_identity import (
    GENERATION_ID_FIELD,
    GenerationIdentityError,
    assert_table_generation,
    bind_version_generation,
)

logger = get_logger(__name__)

_FRAMEWORK_LIST_FIELDS = (
    'pillar',
    'phase',
    "defends_against",
    "tools_opensource",
    "tools_source_available",
    "tools_commercial",
    "implementation_guidance",
    "warnings",
)
_CANONICAL_GUIDANCE_ID = re.compile(
    r"^AID-[A-Z][A-Z0-9]*-\d{3}(?:\.\d{3})?-G\d{3}\Z"
)


def _is_missing_metadata_value(value: Any) -> bool:
    """Return True for database null-like scalar values, including pandas NaN."""
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value) or math.isinf(value)
    try:
        unequal_to_self = value != value
        if hasattr(unequal_to_self, "item"):
            unequal_to_self = unequal_to_self.item()
        return isinstance(unequal_to_self, bool) and unequal_to_self
    except (TypeError, ValueError):
        return False


def _decode_json_list(value: Any) -> List[Any]:
    """Decode a LanceDB JSON-array field without leaking its storage encoding."""
    if _is_missing_metadata_value(value):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        if not value.strip():
            return []
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
        if isinstance(decoded, list):
            return decoded
        # Older index builders could JSON-encode a scalar where the public
        # contract requires an array. Preserve a meaningful scalar while
        # treating an encoded empty string as the empty array.
        if isinstance(decoded, str):
            normalized = decoded.strip()
            return [normalized] if normalized else []
        return []
    return []


def _decode_json_object(value: Any) -> Dict[str, Any]:
    """Decode a LanceDB JSON-object field, returning an object in all cases."""
    if _is_missing_metadata_value(value):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        if not value.strip():
            return {}
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _decode_bool(value: Any, default: bool) -> bool:
    """Decode bool values returned by Arrow, pandas, or an older string schema."""
    if _is_missing_metadata_value(value):
        return default
    if isinstance(value, bool):
        return value
    if hasattr(value, "item"):
        scalar_value = value.item()
        if isinstance(scalar_value, bool):
            return scalar_value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no", ""}:
            return False
    return default


def _metadata_string(value: Any) -> str:
    """Normalize nullable scalar metadata to a JSON-safe string."""
    return "" if _is_missing_metadata_value(value) else str(value)


def decode_framework_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Decode one LanceDB record into the public framework schema contract."""
    decoded = dict(record)
    for field in _FRAMEWORK_LIST_FIELDS:
        raw_value = record.get(field)
        decoded[field] = _decode_json_list(raw_value)
        if (
            field in {"pillar", "phase"}
            and not decoded[field]
            and isinstance(raw_value, str)
            and raw_value.strip()
            and raw_value.strip() not in {"[]", "null"}
            and not raw_value.lstrip().startswith(("[", '"'))
        ):
            # Very old fixtures/indexes used a single scalar for these fields.
            decoded[field] = [raw_value.strip()]

    decoded["scope_boundary"] = _decode_json_object(record.get("scope_boundary"))
    decoded["parent_technique_id"] = _metadata_string(
        record.get("parent_technique_id")
    )

    source_id = _metadata_string(record.get("source_id"))
    guidance_id = _metadata_string(record.get("guidance_id"))
    if guidance_id and not _CANONICAL_GUIDANCE_ID.fullmatch(guidance_id):
        guidance_id = ""
    if not guidance_id and _CANONICAL_GUIDANCE_ID.fullmatch(source_id):
        guidance_id = source_id
    decoded["guidance_id"] = guidance_id

    doc_type = _metadata_string(record.get("type"))
    inferred_parent = (
        doc_type == "technique"
        and not decoded["pillar"]
        and not decoded["phase"]
        and not decoded["implementation_guidance"]
    )
    is_parent_family = _decode_bool(
        record.get("is_parent_family"), inferred_parent
    )
    inferred_actionable = (
        doc_type == "subtechnique"
        or (doc_type == "technique" and not is_parent_family)
    )
    decoded["is_parent_family"] = is_parent_family
    decoded["is_actionable"] = _decode_bool(
        record.get("is_actionable"), inferred_actionable
    )
    decoded["has_code_snippets"] = _decode_bool(
        record.get("has_code_snippets"), False
    )
    return decoded


def framework_public_metadata(record: Dict[str, Any]) -> Dict[str, Any]:
    """Select normalized framework fields safe for MCP and REST responses."""
    decoded = decode_framework_record(record)
    return {
        "type": _metadata_string(decoded.get("type")),
        "name": _metadata_string(decoded.get("name")),
        "pillar": decoded["pillar"],
        "phase": decoded["phase"],
        "defends_against": decoded["defends_against"],
        "tools_opensource": decoded["tools_opensource"],
        "tools_source_available": decoded["tools_source_available"],
        "tools_commercial": decoded["tools_commercial"],
        "parent_technique_id": decoded["parent_technique_id"],
        "guidance_id": decoded["guidance_id"],
        "scope_boundary": decoded["scope_boundary"],
        "is_actionable": decoded["is_actionable"],
        "is_parent_family": decoded["is_parent_family"],
        "has_code_snippets": decoded["has_code_snippets"],
        "warnings": decoded["warnings"],
    }


def _register_custom_embedding_models():
    """
    Register custom embedding models that are not natively supported by FastEmbed.
    This allows using models like Xenova/multilingual-e5-base and intfloat/multilingual-e5-small.
    """
    try:
        from fastembed.common.model_description import PoolingType, ModelSource

        # Check if Xenova/multilingual-e5-base is already registered
        supported = [m["model"] for m in TextEmbedding.list_supported_models()]
        if "Xenova/multilingual-e5-base" in supported:
            logger.debug("Xenova/multilingual-e5-base already supported natively")
            return

        # Register Xenova/multilingual-e5-base (768-dim, 512 tokens, 100+ languages)
        # Using Xenova's pre-quantized Int8 version for 75% size reduction (1.1GB → 280MB)
        logger.info("Registering custom model: Xenova/multilingual-e5-base (Quantized Int8)")
        TextEmbedding.add_custom_model(
            model="Xenova/multilingual-e5-base",
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf="Xenova/multilingual-e5-base"),
            dim=768,
            model_file="onnx/model_quantized.onnx",
            description="Multilingual E5 Base (Quantized Int8 version) - 768 dimensions, 512 tokens, 100+ languages",
            license="MIT",
            size_in_gb=0.28,
            additional_files=[]
        )



        logger.info("Custom embedding models registered successfully")

    except Exception as e:
        logger.warning(f"Failed to register custom embedding models: {e}. Will try direct loading.", exc_info=True)


# Register custom models on module import
_register_custom_embedding_models()


# Mapping of known embedding models to their vector dimensions.
# This allows us to automatically match the correct embedding model to the
# stored LanceDB vectors even if the configured model has changed.
KNOWN_EMBEDDING_MODELS: Dict[str, int] = {
    "Xenova/multilingual-e5-base": 768,
    "intfloat/multilingual-e5-small": 384,
}


class QueryEngineError(Exception):
    """Base exception for query engine errors."""
    pass


class QueryEngineNotInitializedError(QueryEngineError):
    """Raised when query engine is not properly initialized."""
    pass


class QueryEngine:
    """
    RAG query engine for AIDEFEND knowledge base.
    Handles embedding queries and vector search.
    """

    def __init__(self):
        """Initialize query engine (lazy loading)."""
        self._db: Optional[lancedb.DBConnection] = None
        self._table: Optional[lancedb.Table] = None
        self._model: Optional[TextEmbedding] = None
        self._initialized = False
        self._rw_lock = RWLock()  # Read-write lock for concurrent access
        self._rw_lock_loop_id = None  # Track which event loop the lock is bound to
        self._id_cache: Optional[List] = None  # ID cache for validation tool
        self._active_embedding_model: str = settings.EMBEDDING_MODEL
        self._active_embedding_dimension: int = settings.EMBEDDING_DIMENSION
        self._active_generation_id: Optional[str] = None

        logger.info("QueryEngine instance created (lazy initialization)")

    def _ensure_rwlock_for_current_loop(self):
        """
        Ensure RWLock is bound to the current event loop.

        aiorwlock.RWLock() binds to the event loop active when first used.
        If the event loop changes (e.g., FastAPI worker restart, tests),
        we must recreate the lock to avoid "bound to a different event loop" errors.
        """
        try:
            current_loop = asyncio.get_running_loop()
            current_loop_id = id(current_loop)

            # If lock is bound to a different loop, recreate it
            if self._rw_lock_loop_id != current_loop_id:
                logger.debug(f"Recreating RWLock for new event loop (old: {self._rw_lock_loop_id}, new: {current_loop_id})")
                self._rw_lock = RWLock()
                self._rw_lock_loop_id = current_loop_id
        except RuntimeError:
            # No event loop running - this is OK, lock will be created when needed
            pass

    def _detect_table_vector_dimension(self, table: lancedb.Table) -> Optional[int]:
        """
        Attempt to detect the vector dimension stored in LanceDB.

        Args:
            table: LanceDB table to inspect

        Returns:
            Detected dimension, or None if unable to detect
        """
        try:
            schema = table.schema
            if schema:
                for field in schema:
                    if field.name == "vector":
                        list_size = getattr(field.type, "list_size", None)
                        if isinstance(list_size, int):
                            return list_size
        except Exception as e:
            logger.debug(f"Failed to inspect LanceDB schema for vector dimension: {e}")

        try:
            batch = table.take([0])
            if batch and batch.num_rows > 0:
                vector_column = batch.column("vector")
                if vector_column:
                    vector_list = vector_column.to_pylist()[0]
                    if hasattr(vector_list, "__len__"):
                        return len(vector_list)
        except Exception as e:
            logger.debug(f"Failed to sample LanceDB vector dimension: {e}")

        return None

    def _resolve_embedding_model(self, detected_dimension: Optional[int]) -> str:
        """
        Determine which embedding model should be used based on LanceDB vectors.
        Includes upgrade detection to prevent silent model switches.

        Args:
            detected_dimension: Detected vector dimension from database

        Returns:
            Resolved model name

        Raises:
            QueryEngineError: If intentional model upgrade detected without rebuild
        """
        configured_model = settings.EMBEDDING_MODEL
        configured_dimension = settings.EMBEDDING_DIMENSION

        resolved_model = configured_model
        resolved_dimension = configured_dimension

        if detected_dimension is not None:
            resolved_dimension = detected_dimension

            configured_model_dim = KNOWN_EMBEDDING_MODELS.get(configured_model, configured_dimension)

            if detected_dimension not in (configured_dimension, configured_model_dim):
                # Check if this is an intentional upgrade
                version_info = load_version_info()
                stored_model = version_info.get("embedding_model") if version_info else None

                if stored_model and stored_model != configured_model:
                    # This is an INTENTIONAL model upgrade/change
                    logger.error(
                        "❌ Embedding model upgrade detected!\n"
                        f"   Database model: {stored_model} ({detected_dimension}d)\n"
                        f"   Configured model: {configured_model} ({configured_model_dim}d)\n"
                        "\n"
                        "To upgrade the embedding model, you must rebuild the database:\n"
                        "  1. Delete: data/aidefend_kb.lancedb and data/local_version.json\n"
                        "  2. Restart the service to trigger fresh sync\n"
                        "\n"
                        "Or run: python __main__.py --resync"
                    )
                    raise QueryEngineError(
                        f"Database model mismatch. Database uses {stored_model} ({detected_dimension}d) "
                        f"but config specifies {configured_model} ({configured_model_dim}d). "
                        "Rebuild required for model upgrade."
                    )

                # Not an intentional upgrade - auto-correct dimension mismatch
                override_model = next(
                    (name for name, dim in KNOWN_EMBEDDING_MODELS.items() if dim == detected_dimension),
                    None
                )

                if override_model:
                    logger.warning(
                        "LanceDB vectors are %sd but configured model '%s' is %sd. "
                        "Automatically switching to '%s' to prevent dimension mismatch.",
                        detected_dimension,
                        configured_model,
                        configured_dimension,
                        override_model
                    )
                    resolved_model = override_model
                else:
                    logger.warning(
                        "Detected LanceDB vector dimension %s, but no known embedding model matches. "
                        "Continuing with configured model '%s' (%sd).",
                        detected_dimension,
                        configured_model,
                        configured_dimension
                    )
                    resolved_dimension = configured_dimension

        self._active_embedding_model = resolved_model
        self._active_embedding_dimension = resolved_dimension

        return resolved_model

    async def _do_initialize(
        self,
        *,
        expected_version_info: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        """
        Initialize database connection and embedding model.
        Must be called with writer lock held.

        Returns:
            True if successful, False otherwise
        """
        if self._initialized:
            return True

        try:
            logger.info("Initializing QueryEngine...")

            # Check if database exists
            if not settings.DB_PATH.exists():
                logger.warning(
                    "LanceDB not found. Initial sync required.",
                    extra={"db_path": settings.DB_PATH.name}
                )
                return False

            # Connect to database before loading embedding model so we can detect
            # which vector dimension is stored in LanceDB.
            logger.info(f"Connecting to LanceDB: {settings.DB_PATH.name}")
            self._db = await _await_cancellation_safe(
                asyncio.to_thread(lancedb.connect, str(settings.DB_PATH)),
                task_name="aidefend-lancedb-connect",
            )

            # Open table
            try:
                self._table = await _await_cancellation_safe(
                    asyncio.to_thread(self._db.open_table, "aidefend"),
                    task_name="aidefend-lancedb-open-table",
                )
                logger.info("Opened 'aidefend' table")
            except Exception as e:
                logger.error(f"Failed to open 'aidefend' table: {e}")
                return False

            # Startup accepts a fully legacy pre-3.3 pair long enough for the
            # schema-version sync to rebuild it. Transactional activation and
            # rollback always pass expected metadata and therefore require a
            # persisted table ID before the engine can become ready.
            identity_version = (
                expected_version_info
                if expected_version_info is not None
                else load_version_info()
            )
            if not isinstance(identity_version, Mapping):
                raise GenerationIdentityError(
                    "Active LanceDB table has no usable version metadata"
                )
            await self._assert_table_generation_locked(
                self._table,
                identity_version,
                allow_legacy_unbound=expected_version_info is None,
                task_name="aidefend-lancedb-initialize-generation-assert",
            )
            self._active_generation_id = bind_version_generation(
                identity_version,
                allow_legacy=True,
            )[GENERATION_ID_FIELD]

            # Detect stored vector dimension (if possible) and resolve model.
            detected_dimension = await _await_cancellation_safe(
                asyncio.to_thread(
                    self._detect_table_vector_dimension,
                    self._table,
                ),
                task_name="aidefend-lancedb-detect-vector-dimension",
            )

            if detected_dimension:
                logger.info(f"Detected LanceDB vector dimension: {detected_dimension}")
            else:
                logger.warning(
                    "Unable to detect LanceDB vector dimension. Using configured dimension: %s",
                    settings.EMBEDDING_DIMENSION
                )

            previous_model_name = self._active_embedding_model
            resolved_model_name = self._resolve_embedding_model(detected_dimension)

            # Load embedding model only if we don't already have the correct one cached
            if self._model is None or previous_model_name != resolved_model_name:
                if resolved_model_name == "Xenova/multilingual-e5-base":
                    logger.info("Loading embedding model: Xenova/multilingual-e5-base (Quantized Int8)")
                else:
                    logger.info(f"Loading embedding model: {resolved_model_name}")

                # AIDEFEND MCP 1.3.0 ships one supported inference runtime:
                # the CPU packages declared by its distribution metadata.
                # Optional persisted cache dir (None = FastEmbed default).
                model_cache_dir = (
                    str(settings.MODEL_CACHE_DIR)
                    if settings.MODEL_CACHE_DIR
                    else None
                )
                self._model = await _await_cancellation_safe(
                    asyncio.to_thread(
                        TextEmbedding,
                        model_name=resolved_model_name,
                        cache_dir=model_cache_dir,
                    ),
                    task_name="aidefend-embedding-model-load-cpu",
                )
                logger.info("Embedding model loaded (CPU runtime)")
            else:
                logger.info(f"Reusing loaded embedding model: {resolved_model_name}")

            # Get table stats
            count = await _await_cancellation_safe(
                asyncio.to_thread(self._table.count_rows),
                task_name="aidefend-lancedb-initialize-count",
            )

            # Load ID cache for validation tool (optimization)
            logger.info("Loading ID cache for validation tool...")
            self._id_cache = await _await_cancellation_safe(
                asyncio.to_thread(
                    lambda: self._table.to_pandas()[
                        ['source_id', 'name', 'type', 'tactic']
                    ].to_dict('records')
                ),
                task_name="aidefend-lancedb-id-cache",
            )
            logger.info(f"ID cache loaded: {len(self._id_cache)} entries")

            logger.info(
                f"QueryEngine initialized successfully",
                extra={"document_count": count, "embedding_model": self._active_embedding_model}
            )

            self._initialized = True
            return True

        except asyncio.CancelledError:
            self._reset_database_handles_locked()
            raise
        except Exception as e:
            logger.error(f"Failed to initialize QueryEngine: {e}", exc_info=True)
            self._reset_database_handles_locked()
            return False

    async def initialize(self) -> bool:
        """
        Initialize database connection and embedding model.

        Returns:
            True if successful, False otherwise
        """
        self._ensure_rwlock_for_current_loop()
        async with self._rw_lock.writer:
            return await self._do_initialize()

    async def _assert_table_generation_locked(
        self,
        table: lancedb.Table,
        version_info: Mapping[str, Any],
        *,
        allow_legacy_unbound: bool,
        task_name: str,
    ) -> Optional[str]:
        """Verify table identity without blocking the event loop.

        ``assert_table_generation`` reads the LanceDB schema and row counts.
        Those are synchronous storage operations, so callers must hold the
        appropriate database reader or writer lock while this method drains
        the worker to completion, including when the caller is cancelled.
        """
        return await _await_cancellation_safe(
            asyncio.to_thread(
                assert_table_generation,
                table,
                version_info,
                allow_legacy_unbound=allow_legacy_unbound,
            ),
            task_name=task_name,
        )

    def _assert_durable_generation_locked(self) -> None:
        """Fail closed unless the initialized table matches durable metadata.

        The caller must hold the database reader or writer guard.
        """
        if not self._initialized or self._table is None:
            raise QueryEngineNotInitializedError(
                "Query engine database is not available"
            )
        version_info = load_version_info()
        if not isinstance(version_info, Mapping):
            raise GenerationIdentityError(
                "Active LanceDB table has no usable version metadata"
            )
        durable_generation = bind_version_generation(
            version_info,
            allow_legacy=True,
        )[GENERATION_ID_FIELD]
        if durable_generation != self._active_generation_id:
            raise GenerationIdentityError(
                "Active version metadata drifted from the initialized table"
            )

    @asynccontextmanager
    async def database_read_guard(self):
        """Yield the active table while preventing a concurrent physical swap."""
        self._ensure_rwlock_for_current_loop()
        async with self._rw_lock.reader:
            self._assert_durable_generation_locked()
            yield self._table

    async def read_table(self, operation):
        """Run one synchronous LanceDB read under the shared reader lock."""
        async with self.database_read_guard() as table:
            return await _await_cancellation_safe(
                asyncio.to_thread(operation, table),
                task_name="aidefend-lancedb-read",
            )

    @asynccontextmanager
    async def database_snapshot_guard(self):
        """Yield the active table and its version metadata as one generation.

        Sync activates the physical table and VERSION_FILE while holding the
        writer side of this same lock.  Loading metadata only after acquiring
        the reader lock therefore gives callers a generation-consistent view
        for compound reads that cannot be expressed as one synchronous table
        callback.
        """
        from app.utils import load_version_info

        async with self.database_read_guard() as table:
            version_info = load_version_info()
            if not isinstance(version_info, Mapping):
                raise GenerationIdentityError(
                    "Active LanceDB table has no usable version metadata"
                )
            await self._assert_table_generation_locked(
                table,
                version_info,
                allow_legacy_unbound=True,
                task_name="aidefend-lancedb-snapshot-generation-assert",
            )
            yield table, version_info

    async def read_table_snapshot(self, operation):
        """Read the active table and its version/registry as one generation.

        Sync commits the physical table and atomic version file while holding
        the writer side of this same lock. Loading metadata after acquiring the
        reader therefore prevents a caller from pairing an old registry with a
        newly activated table (or the reverse).
        """
        async with self.database_snapshot_guard() as (table, version_info):
            result = await _await_cancellation_safe(
                asyncio.to_thread(operation, table),
                task_name="aidefend-lancedb-snapshot-read",
            )
            return result, version_info

    @asynccontextmanager
    async def database_write_guard(self):
        """Hold the exclusive database lock across a physical table swap."""
        self._ensure_rwlock_for_current_loop()
        async with self._rw_lock.writer:
            yield self

    def _reset_database_handles_locked(self) -> None:
        """Drop DB handles while the caller holds database_write_guard()."""
        self._initialized = False
        self._table = None
        self._db = None
        self._id_cache = None
        self._active_generation_id = None
        # LanceDB has no stable cross-version close API. Releasing references and
        # collecting here prevents Windows file handles from surviving the swap.
        gc.collect()

    async def search(self, request: QueryRequest) -> List[ContextChunk]:
        """
        Perform vector search on knowledge base.

        Args:
            request: Query request with text and parameters

        Returns:
            List of context chunks

        Raises:
            QueryEngineNotInitializedError: If engine not initialized
        """
        # Ensure initialized (acquire writer lock if needed)
        if not self._initialized:
            initialized = await self.initialize()
            if not initialized:
                raise QueryEngineNotInitializedError(
                    "Query engine not initialized. Database may not exist. "
                    "Run initial sync first."
                )

        # Acquire reader lock for search operation (allows concurrent reads)
        self._ensure_rwlock_for_current_loop()
        async with self._rw_lock.reader:
            # Double-check state after acquiring lock
            if not self._initialized or self._model is None or self._table is None:
                raise QueryEngineNotInitializedError(
                    "Query engine components not available"
                )

            try:
                self._assert_durable_generation_locked()
                logger.info(
                    f"Processing query",
                    extra={
                        "query_length": len(request.query_text),
                        "top_k": request.top_k
                    }
                )

                # Embed query (fastembed returns generator, get first result)
                query_embeddings = await _await_cancellation_safe(
                    asyncio.to_thread(
                        lambda: list(self._model.embed([request.query_text]))
                    ),
                    task_name="aidefend-query-embedding",
                )
                query_vector = query_embeddings[0]

                # Perform vector search
                results = await _await_cancellation_safe(
                    asyncio.to_thread(
                        self._perform_search,
                        query_vector,
                        request.top_k,
                    ),
                    task_name="aidefend-lancedb-vector-search",
                )

                # Convert to ContextChunk objects
                chunks = []
                for result in results:
                    decoded = decode_framework_record(result)
                    chunk = ContextChunk(
                        source_id=decoded.get("source_id", "N/A"),
                        tactic=decoded.get("tactic", "N/A"),
                        text=decoded.get("text", ""),
                        metadata=framework_public_metadata(decoded),
                        score=result.get("_distance", 0.0)
                    )
                    chunks.append(chunk)

                logger.info(
                    f"Query completed",
                    extra={
                        "results_returned": len(chunks),
                        "top_score": chunks[0].score if chunks else None
                    }
                )

                return chunks

            except Exception as e:
                logger.error(f"Query failed: {e}", exc_info=True)
                raise QueryEngineError(f"Search failed: {e}")

    def _perform_search(self, query_vector, top_k: int):
        """
        Perform synchronous vector search.
        (Separated for easier thread execution)

        Args:
            query_vector: Query embedding vector
            top_k: Number of results

        Returns:
            List of search results
        """
        if self._table is None:
            raise QueryEngineNotInitializedError("Table not available")

        return (
            self._table
            .search(query_vector)
            .limit(top_k)
            .to_list()
        )

    async def search_batch(self, requests: List[QueryRequest]) -> List[List[ContextChunk]]:
        """
        Perform batch search with optimized batch embedding generation.

        This is more efficient than calling search() multiple times because:
        - Embeddings are generated in a single batch call
        - Reduces overhead from multiple model invocations

        Args:
            requests: List of query requests

        Returns:
            List of result lists (one per request)

        Raises:
            QueryEngineNotInitializedError: If engine not initialized
        """
        if not requests:
            return []

        # Ensure initialized
        if not self._initialized:
            initialized = await self.initialize()
            if not initialized:
                raise QueryEngineNotInitializedError(
                    "Query engine not initialized. Database may not exist."
                )

        # Acquire reader lock for search operation
        self._ensure_rwlock_for_current_loop()
        async with self._rw_lock.reader:
            if not self._initialized or self._model is None or self._table is None:
                raise QueryEngineNotInitializedError("Query engine components not available")

            try:
                self._assert_durable_generation_locked()
                logger.info(
                    f"Processing batch search: {len(requests)} queries",
                    extra={"batch_size": len(requests)}
                )

                # Extract query texts
                query_texts = [req.query_text for req in requests]

                # Batch embed (one model call for all queries).
                query_embeddings = await _await_cancellation_safe(
                    asyncio.to_thread(lambda: list(self._model.embed(query_texts))),
                    task_name="aidefend-batch-query-embedding",
                )

                logger.debug(f"Generated {len(query_embeddings)} embeddings in batch")

                # Parallel search with pre-generated embeddings
                search_tasks = [
                    asyncio.to_thread(self._perform_search, embedding, req.top_k)
                    for embedding, req in zip(query_embeddings, requests)
                ]

                results_list = await _await_cancellation_safe(
                    asyncio.gather(*search_tasks, return_exceptions=True),
                    task_name="aidefend-lancedb-batch-vector-search",
                )

                # Convert results to ContextChunk objects
                all_chunks = []
                for i, results in enumerate(results_list):
                    if isinstance(results, Exception):
                        logger.warning(
                            f"Search failed for query {i}: {results}",
                            extra={"query_index": i, "error": str(results)}
                        )
                        all_chunks.append([])  # Empty results for failed query
                        continue

                    chunks = []
                    for result in results:
                        decoded = decode_framework_record(result)
                        chunk = ContextChunk(
                            source_id=decoded.get("source_id", "N/A"),
                            tactic=decoded.get("tactic", "N/A"),
                            text=decoded.get("text", ""),
                            metadata=framework_public_metadata(decoded),
                            score=result.get("_distance", 0.0)
                        )
                        chunks.append(chunk)

                    all_chunks.append(chunks)

                logger.info(
                    f"Batch search completed: {len(all_chunks)} result sets",
                    extra={"total_results": sum(len(c) for c in all_chunks)}
                )

                return all_chunks

            except Exception as e:
                logger.error(f"Batch search failed: {e}", exc_info=True)
                raise QueryEngineError(f"Batch search failed: {e}")

    async def get_stats(self) -> dict:
        """
        Get query engine statistics and their generation metadata snapshot.

        ``version_info`` is read while holding the same reader lock as the
        active table count. Callers that report both values must consume this
        returned snapshot instead of re-reading VERSION_FILE after the lock is
        released, because a sync may activate a new generation in between.

        Returns:
            Dict with engine stats
        """
        # Acquire the reader lock before inspecting initialization state. A
        # writer may be activating both the table and version file; checking
        # state first could pair an unlocked zero count with new metadata.
        self._ensure_rwlock_for_current_loop()
        async with self._rw_lock.reader:
            version_info = None
            try:
                # Sync activates the table and atomic version file under this
                # lock's writer side, so these values describe one generation.
                version_info = load_version_info()
                if not self._initialized:
                    return {
                        "initialized": False,
                        "document_count": 0,
                        "model_loaded": False,
                        "framework_version": (
                            version_info.get("framework_version")
                            if version_info
                            else None
                        ),
                        "version_info": version_info,
                    }

                if not isinstance(version_info, Mapping):
                    raise GenerationIdentityError(
                        "Active LanceDB table has no usable version metadata"
                    )
                await self._assert_table_generation_locked(
                    self._table,
                    version_info,
                    allow_legacy_unbound=True,
                    task_name="aidefend-lancedb-stats-generation-assert",
                )

                doc_count = 0
                if self._table:
                    doc_count = await _await_cancellation_safe(
                        asyncio.to_thread(self._table.count_rows),
                        task_name="aidefend-lancedb-stats-count",
                    )

                framework_version = version_info.get("framework_version") if version_info else None

                return {
                    "initialized": self._initialized,
                    "document_count": doc_count,
                    "model_loaded": self._model is not None,
                    "embedding_model": self.active_embedding_model,
                    "embedding_dimension": self.active_embedding_dimension,
                    "framework_version": framework_version,
                    "version_info": version_info,
                }
            except Exception as e:
                logger.error(f"Failed to get stats: {e}")
                return {
                    "initialized": False,
                    "document_count": 0,
                    "model_loaded": self._model is not None,
                    "framework_version": (
                        version_info.get("framework_version")
                        if version_info
                        else None
                    ),
                    "version_info": version_info,
                    "error": str(e)
                }

    async def health_check(self) -> bool:
        """
        Check if query engine is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # A probe must not open the DB or download/load an embedding model.
            if not self._initialized:
                return False

            # Acquire reader lock for health check operation
            self._ensure_rwlock_for_current_loop()
            async with self._rw_lock.reader:
                if self._table:
                    version_info = load_version_info()
                    if not isinstance(version_info, Mapping):
                        raise GenerationIdentityError(
                            "Active LanceDB table has no usable version metadata"
                        )
                    await self._assert_table_generation_locked(
                        self._table,
                        version_info,
                        allow_legacy_unbound=True,
                        task_name="aidefend-lancedb-health-generation-assert",
                    )
                    return True

                return False

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def reload(self) -> bool:
        """
        Reload database connection (e.g., after sync).

        Returns:
            True if successful, False otherwise
        """
        # Acquire writer lock for reload operation (exclusive access)
        self._ensure_rwlock_for_current_loop()
        async with self._rw_lock.writer:
            logger.info("Reloading QueryEngine...")

            self._reset_database_handles_locked()

            # Re-initialize (we already have writer lock, so call _do_initialize directly)
            return await self._do_initialize()

    async def close(self) -> None:
        """Release all database handles under the exclusive reader/writer guard."""
        self._ensure_rwlock_for_current_loop()
        async with self._rw_lock.writer:
            self._reset_database_handles_locked()

    def get_id_cache(self) -> Optional[List]:
        """
        Get the cached ID list for validation (optimization).

        This cache is loaded during initialization and avoids full table scans
        in the validation tool for fuzzy matching.

        Returns:
            List of dicts with 'source_id', 'name', 'type', 'tactic' fields,
            or None if not initialized
        """
        return self._id_cache

    @property
    def active_embedding_model(self) -> str:
        """Return the embedding model currently aligned with the database."""
        return self._active_embedding_model or settings.EMBEDDING_MODEL

    @property
    def active_embedding_dimension(self) -> int:
        """Return the vector dimension currently aligned with the database."""
        return self._active_embedding_dimension or settings.EMBEDDING_DIMENSION

    @property
    def is_ready(self) -> bool:
        """
        Check if query engine is initialized and ready to serve queries.

        Returns:
            True if initialized with valid database connection, False otherwise
        """
        return self._initialized and self._table is not None


# Create singleton instance
query_engine = QueryEngine()
