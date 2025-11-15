"""
Core query engine for AIDEFEND MCP Service.
Handles vector search and context retrieval.
"""

import asyncio
import lancedb
from typing import List, Optional
from pathlib import Path
from fastembed import TextEmbedding
from aiorwlock import RWLock

from app.config import settings
from app.logger import get_logger
from app.schemas import QueryRequest, ContextChunk
from app.utils import load_version_info
from app.sync import is_sync_in_progress

logger = get_logger(__name__)


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
        self._id_cache: Optional[List] = None  # ID cache for validation tool

        logger.info("QueryEngine instance created (lazy initialization)")

    async def _do_initialize(self) -> bool:
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
                    extra={"db_path": str(settings.DB_PATH)}
                )
                return False

            # Load embedding model (fastembed uses ONNX Runtime)
            logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
            self._model = await asyncio.to_thread(
                TextEmbedding,
                model_name=settings.EMBEDDING_MODEL
            )
            logger.info("Embedding model loaded")

            # Connect to database
            logger.info(f"Connecting to LanceDB: {settings.DB_PATH}")
            self._db = await asyncio.to_thread(
                lancedb.connect,
                str(settings.DB_PATH)
            )

            # Open table
            try:
                self._table = await asyncio.to_thread(
                    self._db.open_table,
                    "aidefend"
                )
                logger.info("Opened 'aidefend' table")

                # Get table stats
                count = await asyncio.to_thread(self._table.count_rows)

                # Load ID cache for validation tool (optimization)
                logger.info("Loading ID cache for validation tool...")
                self._id_cache = await asyncio.to_thread(
                    lambda: self._table.to_pandas()[['source_id', 'name', 'type', 'tactic']].to_dict('records')
                )
                logger.info(f"ID cache loaded: {len(self._id_cache)} entries")

                logger.info(
                    f"QueryEngine initialized successfully",
                    extra={"document_count": count}
                )

                self._initialized = True
                return True

            except Exception as e:
                logger.error(f"Failed to open 'aidefend' table: {e}")
                return False

        except Exception as e:
            logger.error(f"Failed to initialize QueryEngine: {e}", exc_info=True)
            self._initialized = False
            return False

    async def initialize(self) -> bool:
        """
        Initialize database connection and embedding model.

        Returns:
            True if successful, False otherwise
        """
        async with self._rw_lock.writer:
            return await self._do_initialize()

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
        # Check if sync is in progress (read-write lock protection)
        if is_sync_in_progress():
            logger.warning(
                "Query attempted while sync is in progress",
                extra={"query_preview": request.query_text[:50]}
            )
            raise QueryEngineNotInitializedError(
                "Database sync in progress. Please try again in a few moments."
            )

        # Ensure initialized (acquire writer lock if needed)
        if not self._initialized:
            initialized = await self.initialize()
            if not initialized:
                raise QueryEngineNotInitializedError(
                    "Query engine not initialized. Database may not exist. "
                    "Run initial sync first."
                )

        # Acquire reader lock for search operation (allows concurrent reads)
        async with self._rw_lock.reader:
            # Double-check state after acquiring lock
            if not self._initialized or self._model is None or self._table is None:
                raise QueryEngineNotInitializedError(
                    "Query engine components not available"
                )

            try:
                logger.info(
                    f"Processing query",
                    extra={
                        "query_length": len(request.query_text),
                        "top_k": request.top_k
                    }
                )

                # Embed query (fastembed returns generator, get first result)
                query_embeddings = await asyncio.to_thread(
                    lambda: list(self._model.embed([request.query_text]))
                )
                query_vector = query_embeddings[0]

                # Perform vector search
                results = await asyncio.to_thread(
                    self._perform_search,
                    query_vector,
                    request.top_k
                )

                # Convert to ContextChunk objects
                chunks = []
                for result in results:
                    chunk = ContextChunk(
                        source_id=result.get("source_id", "N/A"),
                        tactic=result.get("tactic", "N/A"),
                        text=result.get("text", ""),
                        metadata={
                            "type": result.get("type", "N/A"),
                            "name": result.get("name", "N/A"),
                            "pillar": result.get("pillar", ""),
                            "phase": result.get("phase", "")
                        },
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

    async def get_stats(self) -> dict:
        """
        Get query engine statistics.

        Returns:
            Dict with engine stats
        """
        if not self._initialized:
            return {
                "initialized": False,
                "document_count": 0,
                "model_loaded": False
            }

        # Acquire reader lock for stats operation
        async with self._rw_lock.reader:
            try:
                doc_count = 0
                if self._table:
                    doc_count = await asyncio.to_thread(self._table.count_rows)

                # Load framework version from version file
                version_info = load_version_info()
                framework_version = version_info.get("framework_version") if version_info else None

                return {
                    "initialized": self._initialized,
                    "document_count": doc_count,
                    "model_loaded": self._model is not None,
                    "embedding_model": settings.EMBEDDING_MODEL,
                    "embedding_dimension": settings.EMBEDDING_DIMENSION,
                    "framework_version": framework_version
                }
            except Exception as e:
                logger.error(f"Failed to get stats: {e}")
                return {
                    "initialized": self._initialized,
                    "document_count": 0,
                    "model_loaded": self._model is not None,
                    "error": str(e)
                }

    async def health_check(self) -> bool:
        """
        Check if query engine is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Ensure initialized (acquire writer lock if needed)
            if not self._initialized:
                await self.initialize()

            if not self._initialized:
                return False

            # Acquire reader lock for health check operation
            async with self._rw_lock.reader:
                # Try a simple count operation
                if self._table:
                    await asyncio.to_thread(self._table.count_rows)
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
        async with self._rw_lock.writer:
            logger.info("Reloading QueryEngine...")

            # Reset state
            self._initialized = False
            self._db = None
            self._table = None
            self._id_cache = None
            # Keep model loaded for performance

            # Re-initialize (we already have writer lock, so call _do_initialize directly)
            return await self._do_initialize()

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
    def is_ready(self) -> bool:
        """
        Check if query engine is initialized and ready to serve queries.

        Returns:
            True if initialized with valid database connection, False otherwise
        """
        return self._initialized and self._table is not None


# Create singleton instance
query_engine = QueryEngine()
