"""
Chunked Search Tool for AIDEFEND MCP Service

Handles semantic search for long queries by intelligently chunking
the input text and combining results from multiple searches.
"""

import asyncio
from typing import List, Dict, Any
from collections import defaultdict

from app.logger import get_logger
from app.config import settings
from app.security import validate_query_text, validate_chunked_query
from app.chunking import smart_chunk_text
from app.core import query_engine
from app.schemas import QueryRequest

logger = get_logger(__name__)


async def search_with_chunking(
    query_text: str,
    top_k: int = 5,
    filters: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Perform semantic search with automatic chunking for long queries.

    For queries longer than MAX_QUERY_LENGTH, this function:
    1. Validates the query (security checks)
    2. Chunks the text intelligently (preserving sentence boundaries)
    3. Searches each chunk independently
    4. Deduplicates and ranks results
    5. Returns top-k combined results

    Args:
        query_text: User query (can be very long)
        top_k: Number of results to return
        filters: Optional filters (tactic, pillar, etc.)

    Returns:
        Dict with:
        - results: List of top-k technique matches
        - metadata: Chunking information and stats

    Raises:
        InputValidationError: If query is invalid or exceeds limits
        asyncio.TimeoutError: If processing exceeds timeout
        Exception: If query engine fails

    Security:
        - Validates total query length (MAX_TOTAL_QUERY_LENGTH)
        - Limits number of chunks (MAX_CHUNKS)
        - Enforces timeout (MAX_CHUNKS_PROCESSING_TIME)
        - Each chunk is independently validated

    Example:
        >>> result = await search_with_chunking("Very long report...", top_k=5)
        >>> print(f"Found {len(result['results'])} techniques")
        >>> print(f"Processed {result['metadata']['chunks_processed']} chunks")
    """
    start_time = asyncio.get_event_loop().time()

    try:
        # Step 1: Validate query with chunking-specific checks
        sanitized_text, validation_meta = validate_chunked_query(query_text)

        # Step 2: Determine if chunking is needed
        if not validation_meta['chunking_required']:
            # Query is short enough - use regular search
            logger.info("Query within single-chunk limit, using regular search")
            if filters:
                logger.debug("Search filters are not supported for chunked search; ignoring filters on short query path")
            results = await query_engine.search(
                QueryRequest(query_text=sanitized_text, top_k=top_k)
            )
            return {
                "results": [_normalize_search_result(result) for result in results],
                "metadata": {
                    "chunking_used": False,
                    "original_length": validation_meta['original_length'],
                    "chunks_processed": 1,
                    "processing_time_seconds": asyncio.get_event_loop().time() - start_time
                }
            }

        # Step 3: Chunk the text
        logger.info(
            f"Chunking long query for search",
            extra={
                "query_length": validation_meta['original_length'],
                "estimated_chunks": validation_meta['estimated_chunks']
            }
        )

        chunks = smart_chunk_text(
            sanitized_text,
            chunk_size=settings.CHUNK_SIZE,
            overlap=settings.CHUNK_OVERLAP
        )

        # Security check: Verify actual chunk count doesn't exceed limit
        if len(chunks) > settings.MAX_CHUNKS:
            logger.error(
                f"Chunk count exceeds limit after chunking",
                extra={
                    "actual_chunks": len(chunks),
                    "max_allowed": settings.MAX_CHUNKS
                }
            )
            raise ValueError(
                f"Query resulted in {len(chunks)} chunks, exceeding maximum of {settings.MAX_CHUNKS}"
            )

        # Step 4: Search each chunk with timeout protection
        try:
            results_list = await asyncio.wait_for(
                _search_all_chunks(chunks, top_k, filters),
                timeout=settings.MAX_CHUNKS_PROCESSING_TIME
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Chunked search timeout",
                extra={
                    "query_length": len(sanitized_text),
                    "num_chunks": len(chunks),
                    "timeout_seconds": settings.MAX_CHUNKS_PROCESSING_TIME
                }
            )
            raise asyncio.TimeoutError(
                f"Query processing exceeded {settings.MAX_CHUNKS_PROCESSING_TIME} second timeout. "
                "Please use a shorter query."
            )

        # Step 5: Combine and deduplicate results
        combined_results = _deduplicate_and_rank_results(results_list, top_k)

        processing_time = asyncio.get_event_loop().time() - start_time

        logger.info(
            f"Chunked search completed",
            extra={
                "chunks_processed": len(chunks),
                "total_matches_before_dedup": sum(len(r) for r in results_list),
                "unique_matches": len(combined_results),
                "top_k_returned": len(combined_results[:top_k]),
                "processing_time_seconds": processing_time
            }
        )

        # Build response
        return {
            "results": combined_results[:top_k],
            "metadata": {
                "chunking_used": True,
                "original_length": validation_meta['original_length'],
                "chunks_processed": len(chunks),
                "chunk_sizes": [len(c) for c in chunks],
                "total_matches_found": len(combined_results),
                "processing_time_seconds": round(processing_time, 2),
                "timeout_limit_seconds": settings.MAX_CHUNKS_PROCESSING_TIME
            }
        }

    except Exception as e:
        logger.error(
            f"Chunked search failed",
            exc_info=True,
            extra={
                "query_length": len(query_text),
                "error": str(e)
            }
        )
        raise


async def _search_all_chunks(
    chunks: List[str],
    top_k: int,
    filters: Dict[str, Any]
) -> List[List[Dict[str, Any]]]:
    """
    Search all chunks in parallel (with concurrency limit).

    Args:
        chunks: List of text chunks
        top_k: Results per chunk (will fetch top_k * 2 for better coverage)
        filters: Search filters

    Returns:
        List of result lists (one per chunk)
    """
    # Increase top_k per chunk to ensure good coverage
    # We'll deduplicate and re-rank later
    chunk_top_k = min(top_k * 2, settings.MAX_TOP_K)

    # Search each chunk
    tasks = []
    for i, chunk in enumerate(chunks):
        task = _search_single_chunk(chunk, i, chunk_top_k, filters)
        tasks.append(task)

    # Execute searches concurrently (FastAPI handles this efficiently)
    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and log them
    valid_results = []
    for i, result in enumerate(results_list):
        if isinstance(result, Exception):
            logger.warning(
                f"Chunk {i} search failed",
                extra={"chunk_index": i, "error": str(result)}
            )
            valid_results.append([])  # Empty results for failed chunk
        else:
            valid_results.append(result)

    return valid_results


async def _search_single_chunk(
    chunk: str,
    chunk_index: int,
    top_k: int,
    filters: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Search a single chunk.

    Args:
        chunk: Text chunk
        chunk_index: Index of this chunk (for logging)
        top_k: Number of results to fetch
        filters: Search filters

    Returns:
        List of search results
    """
    try:
        # Validate each chunk independently (defense in depth)
        sanitized_chunk = validate_query_text(chunk)

        logger.debug(
            f"Searching chunk {chunk_index}",
            extra={
                "chunk_index": chunk_index,
                "chunk_length": len(chunk),
                "chunk_preview": sanitized_chunk[:100]
            }
        )

        # Perform search
        if filters:
            logger.debug("Search filters are not supported for chunked search; ignoring filters on chunk search path")
        results = await query_engine.search(
            QueryRequest(query_text=sanitized_chunk, top_k=top_k)
        )

        logger.debug(
            f"Chunk {chunk_index} returned {len(results)} results",
            extra={"chunk_index": chunk_index, "result_count": len(results)}
        )

        return results

    except Exception as e:
        logger.warning(
            f"Failed to search chunk {chunk_index}: {e}",
            extra={"chunk_index": chunk_index, "error": str(e)}
        )
        # Return empty results instead of failing entire search
        return []


def _normalize_search_result(result: Any) -> Dict[str, Any]:
    """Convert query results into a consistent dict shape for deduplication and API output."""
    if hasattr(result, "model_dump"):
        normalized = result.model_dump()
    elif isinstance(result, dict):
        normalized = dict(result)
    else:
        raise TypeError(f"Unsupported search result type: {type(result)!r}")

    technique_id = normalized.get("technique_id") or normalized.get("source_id")
    if technique_id:
        normalized.setdefault("source_id", technique_id)

    if "similarity_score" not in normalized:
        distance = normalized.get("score", normalized.get("_distance"))
        if isinstance(distance, (int, float)):
            normalized["similarity_score"] = 1.0 / (1.0 + float(distance))
        else:
            normalized["similarity_score"] = 0.0

    return normalized


def _deduplicate_and_rank_results(
    results_list: List[List[Dict[str, Any]]],
    top_k: int
) -> List[Dict[str, Any]]:
    """
    Deduplicate results across chunks and re-rank by best score.

    For each unique technique:
    - Keep the result with the highest similarity score
    - Preserve all metadata from the best match

    Args:
        results_list: List of result lists (one per chunk)
        top_k: Desired number of final results

    Returns:
        Deduplicated and ranked results
    """
    # Group results by technique_id, keeping only the best score
    best_results = {}

    for chunk_results in results_list:
        for result in chunk_results:
            result = _normalize_search_result(result)
            technique_id = result.get('technique_id') or result.get('source_id')

            if not technique_id:
                logger.warning("Result missing technique_id, skipping", extra={"result": result})
                continue

            similarity_score = result.get('similarity_score', 0.0)

            # Keep result with highest similarity score
            if technique_id not in best_results:
                best_results[technique_id] = result
            elif similarity_score > best_results[technique_id].get('similarity_score', 0.0):
                best_results[technique_id] = result

    # Sort by similarity score (descending)
    sorted_results = sorted(
        best_results.values(),
        key=lambda x: x.get('similarity_score', 0.0),
        reverse=True
    )

    logger.debug(
        f"Deduplication complete",
        extra={
            "total_results_before": sum(len(r) for r in results_list),
            "unique_results": len(sorted_results),
            "top_k_requested": top_k
        }
    )

    return sorted_results
