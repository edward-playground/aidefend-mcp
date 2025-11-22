"""
Performance Benchmark Tool for AIDEFEND MCP Service

Measures search latency to identify performance bottlenecks.
"""

import asyncio
import time
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core import query_engine
from app.schemas import QueryRequest
from app.logger import get_logger

logger = get_logger(__name__)


async def benchmark_single_search(query_text: str, top_k: int = 10, warmup: bool = True):
    """
    Benchmark a single search query.

    Args:
        query_text: Query to test
        top_k: Number of results to retrieve
        warmup: Whether to do a warmup query first (recommended)

    Returns:
        Dict with timing breakdown
    """
    # Initialize query engine
    logger.info("Initializing query engine...")
    initialized = await query_engine.initialize()

    if not initialized:
        logger.error("Failed to initialize query engine")
        return None

    logger.info(f"Query engine ready. Model: {query_engine.active_embedding_model}")

    # Warmup query (loads model into memory, warms up GPU if available)
    if warmup:
        logger.info("Running warmup query...")
        warmup_request = QueryRequest(query_text="test warmup", top_k=5)
        await query_engine.search(warmup_request)
        logger.info("Warmup complete")

    # Benchmark query
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmarking query: '{query_text}'")
    logger.info(f"Top-K: {top_k}")
    logger.info(f"{'='*60}\n")

    request = QueryRequest(query_text=query_text, top_k=top_k)

    # Measure total time
    start_total = time.perf_counter()
    results = await query_engine.search(request)
    end_total = time.perf_counter()

    total_time = end_total - start_total

    # Print results
    logger.info(f"\n{'='*60}")
    logger.info(f"BENCHMARK RESULTS")
    logger.info(f"{'='*60}")
    logger.info(f"Query: '{query_text}'")
    logger.info(f"Top-K: {top_k}")
    logger.info(f"Results returned: {len(results)}")
    logger.info(f"\nTotal search time: {total_time*1000:.2f} ms ({total_time:.4f} s)")

    # Performance evaluation
    if total_time < 0.5:
        status = "✅ EXCELLENT (< 500ms)"
    elif total_time < 1.0:
        status = "✓ GOOD (< 1s)"
    elif total_time < 2.0:
        status = "⚠ ACCEPTABLE (< 2s)"
    else:
        status = "❌ SLOW (> 2s) - Optimization recommended"

    logger.info(f"Performance: {status}")

    # Show top 3 results
    if results:
        logger.info(f"\nTop 3 results:")
        for i, chunk in enumerate(results[:3], 1):
            logger.info(f"  {i}. {chunk.source_id}: {chunk.metadata.get('name', 'N/A')} (score: {chunk.score:.4f})")

    logger.info(f"{'='*60}\n")

    return {
        "query_text": query_text,
        "top_k": top_k,
        "total_time_ms": total_time * 1000,
        "total_time_s": total_time,
        "results_count": len(results),
        "status": status
    }


async def benchmark_multiple_queries(queries: list, top_k: int = 10):
    """
    Benchmark multiple queries and show statistics.

    Args:
        queries: List of query strings
        top_k: Number of results per query
    """
    logger.info(f"\n{'#'*60}")
    logger.info(f"MULTI-QUERY BENCHMARK")
    logger.info(f"{'#'*60}")
    logger.info(f"Total queries: {len(queries)}")
    logger.info(f"Top-K: {top_k}")
    logger.info(f"{'#'*60}\n")

    results = []

    # Run warmup once
    logger.info("Initializing and warming up...")
    initialized = await query_engine.initialize()
    if not initialized:
        logger.error("Failed to initialize query engine")
        return

    warmup_request = QueryRequest(query_text="test warmup", top_k=5)
    await query_engine.search(warmup_request)
    logger.info("Warmup complete\n")

    # Benchmark each query
    for i, query_text in enumerate(queries, 1):
        logger.info(f"[{i}/{len(queries)}] Benchmarking: '{query_text}'")

        request = QueryRequest(query_text=query_text, top_k=top_k)

        start = time.perf_counter()
        search_results = await query_engine.search(request)
        end = time.perf_counter()

        elapsed_ms = (end - start) * 1000

        logger.info(f"    Time: {elapsed_ms:.2f} ms | Results: {len(search_results)}")

        results.append({
            "query": query_text,
            "time_ms": elapsed_ms,
            "results_count": len(search_results)
        })

    # Calculate statistics
    times = [r["time_ms"] for r in results]
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    logger.info(f"\n{'='*60}")
    logger.info(f"STATISTICS")
    logger.info(f"{'='*60}")
    logger.info(f"Queries executed: {len(queries)}")
    logger.info(f"Average time: {avg_time:.2f} ms")
    logger.info(f"Min time: {min_time:.2f} ms")
    logger.info(f"Max time: {max_time:.2f} ms")
    logger.info(f"Total time: {sum(times):.2f} ms")

    # Performance classification
    if avg_time < 500:
        status = "✅ EXCELLENT"
    elif avg_time < 1000:
        status = "✓ GOOD"
    elif avg_time < 2000:
        status = "⚠ ACCEPTABLE"
    else:
        status = "❌ NEEDS OPTIMIZATION"

    logger.info(f"Overall performance: {status}")
    logger.info(f"{'='*60}\n")


async def comprehensive_search_benchmark():
    """
    Benchmark the comprehensive_search tool with parallel queries.
    """
    from app.tools.comprehensive_search import comprehensive_search

    logger.info(f"\n{'#'*60}")
    logger.info(f"COMPREHENSIVE SEARCH BENCHMARK")
    logger.info(f"{'#'*60}\n")

    topic = "prompt injection"

    logger.info(f"Topic: '{topic}'")
    logger.info(f"This will execute 5 parallel searches internally...")

    start = time.perf_counter()
    result = await comprehensive_search(topic, max_results=20)
    end = time.perf_counter()

    elapsed = end - start

    logger.info(f"\n{'='*60}")
    logger.info(f"RESULTS")
    logger.info(f"{'='*60}")
    logger.info(f"Total time: {elapsed*1000:.2f} ms ({elapsed:.2f} s)")
    logger.info(f"Queries executed: {len(result['queries_executed'])}")
    logger.info(f"Results before dedup: {result['total_results_before_dedup']}")
    logger.info(f"Results after dedup: {result['total_results_after_dedup']}")
    logger.info(f"Final results returned: {len(result['results'])}")

    # Calculate time per query
    time_per_query = (elapsed / len(result['queries_executed'])) * 1000
    logger.info(f"\nAverage time per query: {time_per_query:.2f} ms")

    if elapsed < 2.0:
        status = "✅ EXCELLENT (< 2s)"
    elif elapsed < 5.0:
        status = "✓ GOOD (< 5s)"
    elif elapsed < 10.0:
        status = "⚠ ACCEPTABLE (< 10s)"
    else:
        status = "❌ SLOW (> 10s)"

    logger.info(f"Performance: {status}")
    logger.info(f"{'='*60}\n")


async def main():
    """Run all benchmarks."""
    # Single query benchmark
    await benchmark_single_search("prompt injection attacks", top_k=10)

    # Multiple queries benchmark
    test_queries = [
        "prompt injection",
        "jailbreak attacks",
        "deepfakes detection",
        "model poisoning",
        "adversarial examples"
    ]

    await benchmark_multiple_queries(test_queries, top_k=10)

    # Comprehensive search benchmark
    await comprehensive_search_benchmark()


if __name__ == "__main__":
    asyncio.run(main())
