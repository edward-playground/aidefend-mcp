"""
Comprehensive Search Tool for AIDEFEND MCP Service

Performs multi-query aggregated semantic search to provide comprehensive
coverage of broad topics in a single tool call, preventing timeout issues.
"""

import asyncio
import lancedb
from typing import Dict, Any, List, Optional
from collections import Counter

from app.logger import get_logger
from app.config import settings
from app.security import (
    InputValidationError,
    validate_bounded_integer,
    validate_query_text,
)
from app.schemas import QueryRequest
from app.core import decode_framework_record, query_engine
from app.exceptions import QueryEngineNotInitializedError

logger = get_logger(__name__)


def _available_tactic_names(records: Any) -> List[str]:
    """Return unique tactic names in index order from cached framework records."""
    if not isinstance(records, list):
        return []

    names: List[str] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        tactic = record.get("tactic")
        if not isinstance(tactic, str) or not tactic.strip():
            continue
        tactic = tactic.strip()
        key = tactic.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(tactic)
    return names


def generate_related_queries(topic: str, max_queries: int = 5) -> List[str]:
    """
    Generate related search queries from a broad topic using heuristics.

    This function uses keyword expansion and domain knowledge to generate
    semantically related queries that provide comprehensive coverage.

    Args:
        topic: Broad topic (e.g., "deepfakes", "prompt injection")
        max_queries: Maximum number of queries to generate (default: 5)

    Returns:
        List of related query strings

    Example:
        >>> generate_related_queries("deepfakes")
        ['deepfakes', 'synthetic media', 'deepfake detection', 'video forgery']
    """
    topic_lower = topic.lower().strip()
    queries = [topic]  # Always include the original topic

    # Heuristic-based query expansion
    # Maps common topics to related search terms
    expansion_map = {
        # Deepfakes and synthetic media
        "deepfake": ["synthetic media", "deepfake detection", "media manipulation", "audio cloning"],
        "synthetic media": ["deepfakes", "video forgery", "media authentication", "detection techniques"],

        # Prompt injection and jailbreaking
        "prompt injection": ["jailbreak", "prompt attacks", "input validation", "prompt defense"],
        "jailbreak": ["prompt injection", "bypass", "safety alignment", "guardrails"],

        # Model security
        "model poisoning": ["data poisoning", "backdoor attacks", "training security", "model integrity"],
        "adversarial": ["adversarial examples", "adversarial attacks", "robustness", "defense"],

        # Data security
        "data poisoning": ["training data", "model poisoning", "data validation", "data integrity"],
        "privacy": ["data leakage", "membership inference", "differential privacy", "PII protection"],

        # Supply chain
        "supply chain": ["third-party models", "dependency", "model provenance", "vendor security"],

        # RAG and retrieval
        "rag": ["retrieval", "context injection", "document poisoning", "knowledge base security"],
        "retrieval": ["rag security", "context manipulation", "vector database"],

        # General ML security
        "model theft": ["model extraction", "model stealing", "API abuse", "intellectual property"],
        "evasion": ["adversarial evasion", "detection bypass", "obfuscation"],
    }

    # Find matching expansion rules
    for keyword, related_terms in expansion_map.items():
        if keyword in topic_lower:
            queries.extend(related_terms[:max_queries - 1])
            break

    # If no specific expansion found, add general defense/detection/mitigation queries
    if len(queries) == 1:
        queries.append(f"{topic} detection")
        queries.append(f"{topic} defense")
        queries.append(f"{topic} mitigation")

    # Deduplicate and limit
    seen = set()
    unique_queries = []
    for q in queries:
        q_lower = q.lower().strip()
        if q_lower not in seen:
            seen.add(q_lower)
            unique_queries.append(q)

    return unique_queries[:max_queries]


def deduplicate_results(
    results: List[Dict[str, Any]],
    score_key: str = "_distance"
) -> List[Dict[str, Any]]:
    """
    Remove duplicate results by source_id, keeping the one with best score.

    Args:
        results: List of search result dicts
        score_key: Key containing the relevance score (lower is better for L2 distance)

    Returns:
        Deduplicated list sorted by relevance
    """
    seen = {}

    for result in results:
        source_id = result.get("source_id")
        if not source_id:
            continue

        score = result.get(score_key, float('inf'))

        # Keep result with lower distance score (better match)
        if source_id not in seen or score < seen[source_id][score_key]:
            seen[source_id] = result

    # Sort by relevance score (lower distance = better)
    deduplicated = list(seen.values())
    deduplicated.sort(key=lambda x: x.get(score_key, float('inf')))

    return deduplicated


def compute_coverage_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute coverage statistics from search results.

    Args:
        results: List of deduplicated search results

    Returns:
        Dict containing coverage statistics
    """
    tactics_counter = Counter()
    types_counter = Counter()
    pillars_counter = Counter()
    phases_counter = Counter()

    technique_count = 0
    subtechnique_count = 0

    for result in results:
        result = decode_framework_record(result)
        result_type = result.get("type") or "unknown"
        tactic = result.get("tactic") or "unknown"
        pillars = result["pillar"] or ["unknown"]
        phases = result["phase"] or ["unknown"]

        if result_type == "technique":
            technique_count += 1
        elif result_type == "subtechnique":
            subtechnique_count += 1

        tactics_counter[tactic] += 1
        types_counter[result_type] += 1
        for pillar in pillars:
            pillars_counter[pillar] += 1
        for phase in phases:
            phases_counter[phase] += 1

    return {
        "total_results": len(results),
        "techniques": technique_count,
        "subtechniques": subtechnique_count,
        "by_tactic": dict(tactics_counter),
        "by_type": dict(types_counter),
        "by_pillar": dict(pillars_counter),
        "by_phase": dict(phases_counter),
        "tactics_covered": list(tactics_counter.keys()),
    }


async def comprehensive_search(
    topic: str,
    max_results: int = 20,
    include_subtechniques: bool = True,
    per_query_limit: int = 10
) -> Dict[str, Any]:
    """
    Perform comprehensive search across multiple related queries.

    Automatically generates related search queries from the input topic,
    performs parallel semantic searches, deduplicates results, and returns
    aggregated results with coverage summary.

    This tool is designed to handle broad questions that would normally require
    multiple sequential tool calls, preventing timeout issues in Claude Desktop.

    Args:
        topic: Broad topic to search (e.g., "deepfakes", "prompt injection")
        max_results: Maximum total results to return (5-50, default: 20)
        include_subtechniques: Include sub-techniques in results (default: True)
        per_query_limit: Results per individual query (default: 10)

    Returns:
        Dict containing:
            - input_topic: Original topic
            - search_strategy: "multi_query"
            - queries_executed: List of queries performed
            - total_results_before_dedup: Count before deduplication
            - total_results_after_dedup: Count after deduplication
            - results: List of deduplicated, ranked results
            - coverage_summary: Statistics about coverage
            - related_searches: Suggested additional searches

    Raises:
        InputValidationError: If inputs are invalid
        QueryEngineNotInitializedError: If database is not ready
        Exception: If search fails

    Example:
        >>> result = await comprehensive_search("deepfakes", max_results=20)
        >>> print(f"Found {len(result['results'])} unique techniques")
        >>> print(f"Tactics covered: {result['coverage_summary']['tactics_covered']}")
    """
    # Pre-flight check
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please wait for initial sync to complete."
        )

    # Input validation
    topic = validate_query_text(topic)

    if len(topic) < 3:
        raise InputValidationError("Topic must be at least 3 characters long")

    if len(topic) > 200:
        raise InputValidationError("Topic must be less than 200 characters")

    max_results = validate_bounded_integer(
        max_results, "max_results", 5, 50
    )

    if per_query_limit < 5 or per_query_limit > 20:
        per_query_limit = 10  # Use default if invalid

    logger.info(
        f"Starting comprehensive search for topic='{topic}', max_results={max_results}",
        extra={"topic": topic, "max_results": max_results}
    )

    try:
        # Step 1: Generate related queries
        related_queries = generate_related_queries(topic, max_queries=5)
        logger.info(
            f"Generated {len(related_queries)} related queries: {related_queries}",
            extra={"topic": topic, "queries": related_queries}
        )

        # Step 2: Perform batch semantic search (optimized with batch embedding)
        # Create all query requests
        query_requests = [
            QueryRequest(query_text=query_text, top_k=per_query_limit)
            for query_text in related_queries
        ]

        logger.info(f"Executing batch search for {len(query_requests)} queries (with batch embedding optimization)...")

        # Execute batch search (embeddings generated in one call, then parallel search).
        # Actual latency depends on the model, hardware, and query workload.
        search_results = await query_engine.search_batch(query_requests)

        logger.info(
            f"Search execution completed: {len(search_results)} results received",
            extra={"total_searches": len(search_results)}
        )

        # Step 3: Aggregate results from batch search
        all_results = []
        successful_queries = []

        # search_batch() returns List[List[ContextChunk]]
        for i, chunks in enumerate(search_results):
            if not chunks:
                # Empty result (query failed or no matches)
                logger.debug(
                    f"No results for query '{related_queries[i]}'",
                    extra={"query": related_queries[i]}
                )
                continue

            logger.debug(
                f"Search succeeded for query '{related_queries[i]}': {len(chunks)} chunks",
                extra={"query": related_queries[i], "chunks": len(chunks)}
            )

            # Process each ContextChunk
            for chunk in chunks:
                metadata = decode_framework_record(chunk.metadata)
                result_dict = {
                    "source_id": chunk.source_id,
                    "name": metadata.get("name", ""),
                    "tactic": chunk.tactic,
                    "type": metadata.get("type", ""),
                    "description": chunk.text,
                    "pillar": metadata["pillar"],
                    "phase": metadata["phase"],
                    "defends_against": metadata["defends_against"],
                    "tools_opensource": metadata["tools_opensource"],
                    "tools_source_available": metadata["tools_source_available"],
                    "tools_commercial": metadata["tools_commercial"],
                    "parent_technique_id": metadata["parent_technique_id"],
                    "guidance_id": metadata["guidance_id"],
                    "scope_boundary": metadata["scope_boundary"],
                    "is_actionable": metadata["is_actionable"],
                    "is_parent_family": metadata["is_parent_family"],
                    "_distance": chunk.score,
                    "matched_query": related_queries[i]
                }
                all_results.append(result_dict)

            successful_queries.append(related_queries[i])

        total_before_dedup = len(all_results)
        logger.info(f"Collected {total_before_dedup} results from {len(successful_queries)} queries")

        # Step 4: Deduplicate by source_id
        deduplicated_results = deduplicate_results(all_results)
        total_after_dedup = len(deduplicated_results)

        logger.info(
            f"Deduplication: {total_before_dedup} → {total_after_dedup} results",
            extra={"before": total_before_dedup, "after": total_after_dedup}
        )

        # Step 5: Filter by include_subtechniques if needed
        if not include_subtechniques:
            deduplicated_results = [
                r for r in deduplicated_results
                if r.get("type") != "subtechnique"
                and not (
                    r.get("type") == "strategy"
                    and "." in r.get("parent_technique_id", "")
                )
            ]
            logger.info(f"Filtered subtechniques: {len(deduplicated_results)} results remain")

        total_after_type_filter = len(deduplicated_results)

        # Step 6: Limit to max_results
        final_results = deduplicated_results[:max_results]

        # Step 7: Compute coverage summary
        coverage = compute_coverage_summary(final_results)

        # Step 8: Generate suggested related searches
        related_searches = []
        if coverage["total_results"] < 5:
            related_searches.append(f"Try more specific terms related to '{topic}'")

        # Suggest related topics based on what was found
        tactics_found = coverage.get("tactics_covered", [])
        get_id_cache = getattr(query_engine, "get_id_cache", None)
        cached_records = get_id_cache() if callable(get_id_cache) else None
        available_tactics = _available_tactic_names(cached_records)
        tactics_found_keys = {
            tactic.strip().casefold()
            for tactic in tactics_found
            if isinstance(tactic, str) and tactic.strip()
        }
        missing_tactics = [
            tactic
            for tactic in available_tactics
            if tactic.casefold() not in tactics_found_keys
        ]

        if missing_tactics:
            related_searches.append(
                f"Consider searching tactics not covered: {', '.join(missing_tactics[:3])}"
            )

        # Step 9: Build response
        response = {
            "input_topic": topic,
            "search_strategy": "multi_query",
            "queries_executed": successful_queries,
            "total_results_before_dedup": total_before_dedup,
            "total_results_after_dedup": total_after_dedup,
            "total_results_after_type_filter": total_after_type_filter,
            "results": final_results,
            "coverage_summary": coverage,
            "related_searches": related_searches,
        }

        logger.info(
            f"Comprehensive search completed: {len(final_results)} results",
            extra={
                "topic": topic,
                "queries": len(successful_queries),
                "results": len(final_results),
                "tactics": len(tactics_found)
            }
        )

        return response

    except InputValidationError:
        raise
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        logger.error(
            f"Comprehensive search failed for topic '{topic}': {e}",
            exc_info=True,
            extra={"topic": topic}
        )
        raise Exception(f"Comprehensive search failed: {str(e)}")
