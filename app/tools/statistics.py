"""
Statistics Tool for AIDEFEND MCP Service

Provides comprehensive statistics about the AIDEFEND knowledge base including
total documents, breakdown by type, tactic, pillar, and phase.
"""

import json
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from collections import defaultdict

from app.logger import get_logger
from app.config import settings
from app.framework_utils import (
    build_framework_metrics,
    extract_framework_coverage,
    is_actionable_record,
    merge_framework_coverage_sets,
    parse_json_list,
)

logger = get_logger(__name__)


async def get_statistics() -> Dict[str, Any]:
    """
    Get comprehensive statistics about the AIDEFEND knowledge base.

    Returns statistics including:
    - Total documents by type (technique, subtechnique, strategy)
    - Breakdown by tactic, pillar, and phase
    - Threat framework coverage
    - Tools availability
    - Last sync information

    Returns:
        Dict containing all statistics

    Raises:
        Exception: If database not initialized or query fails

    Example:
        >>> stats = await get_statistics()
        >>> print(f"Total techniques: {stats['total_techniques']}")
    """
    logger.info("Fetching AIDEFEND knowledge base statistics")

    from app.core import query_engine

    # Try to load pre-computed statistics from version file (optimization)
    from app.utils import load_version_info
    version_info = load_version_info()

    if version_info and "statistics" in version_info:
        logger.info("Using pre-computed statistics from version file (fast path)")
        statistics = version_info["statistics"]
        model_name = query_engine.active_embedding_model
        if model_name == "Xenova/multilingual-e5-base":
            model_name = "Xenova/multilingual-e5-base (Quantized Int8)"
        statistics.setdefault("overview", {})["embedding_model"] = model_name
        return statistics

    # Fallback: Calculate statistics from database (slow path)
    logger.warning("Pre-computed statistics not found, performing full table scan (slow)")
    import lancedb
    from app.exceptions import QueryEngineNotInitializedError

    # Pre-flight check: ensure query engine is ready
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please run 'sync_aidefend' first to download the knowledge base."
        )


    try:
        # Connect to LanceDB
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))

        # Open table
        table = await asyncio.to_thread(db.open_table, "aidefend")

        # Get all documents (we need to scan to get accurate stats)
        # Note: This is a full table scan, but for ~500 documents it's acceptable
        logger.info("Scanning all documents for statistics...")
        all_docs = await asyncio.to_thread(
            lambda: table.to_pandas().to_dict('records')
        )

        logger.info(f"Retrieved {len(all_docs)} documents")

        # Initialize counters
        total_documents = len(all_docs)
        type_counts = defaultdict(int)
        tactic_counts = defaultdict(int)
        pillar_counts = defaultdict(int)
        phase_counts = defaultdict(int)

        # Counters for enhanced features
        techniques_with_defenses = 0
        techniques_with_opensource_tools = 0
        techniques_with_commercial_tools = 0
        documents_with_code = 0

        covered_framework_sets = merge_framework_coverage_sets()
        total_framework_sets = merge_framework_coverage_sets()
        actionable_total = 0

        # Scan documents
        for doc in all_docs:
            doc_type = doc.get('type', 'unknown')
            tactic = doc.get('tactic', 'Unknown')
            pillar_raw = doc.get('pillar', '')
            phase_raw = doc.get('phase', '')

            # Parse pillar and phase (stored as JSON arrays)
            pillars = parse_json_list(pillar_raw)
            phases = parse_json_list(phase_raw)

            # Count by type
            type_counts[doc_type] += 1

            # Count by tactic (all documents)
            tactic_counts[tactic] += 1

            # Count by pillar (iterate over array elements)
            if isinstance(pillars, list):
                for pillar in pillars:
                    if pillar:
                        pillar_counts[pillar] += 1

            # Count by phase (iterate over array elements)
            if isinstance(phases, list):
                for phase in phases:
                    if phase:
                        phase_counts[phase] += 1

            # Enhanced features (standalone techniques + sub-techniques)
            if is_actionable_record(doc):
                actionable_total += 1

                defends_against = parse_json_list(doc.get('defends_against', '[]'))
                tools_opensource = parse_json_list(doc.get('tools_opensource', '[]'))
                tools_commercial = parse_json_list(doc.get('tools_commercial', '[]'))

                if defends_against:
                    techniques_with_defenses += 1
                    coverage = extract_framework_coverage(defends_against)
                    covered_framework_sets = merge_framework_coverage_sets(covered_framework_sets, coverage)
                    total_framework_sets = merge_framework_coverage_sets(total_framework_sets, coverage)

                if tools_opensource:
                    techniques_with_opensource_tools += 1
                if tools_commercial:
                    techniques_with_commercial_tools += 1

            # Check for code snippets
            has_code = doc.get('has_code_snippets', False)
            if has_code:
                documents_with_code += 1

        # Get last sync time from version file
        from app.utils import load_version_info
        version_info = load_version_info()
        last_synced = version_info.get("last_sync", "Unknown") if version_info else "Unknown"

        threat_framework_coverage = build_framework_metrics(
            covered_sets=covered_framework_sets,
            total_sets=total_framework_sets,
        )
        threat_framework_coverage["techniques_with_threat_mappings"] = techniques_with_defenses
        threat_framework_coverage["techniques_mapped_percentage"] = round(
            (techniques_with_defenses / actionable_total) * 100, 1
        ) if actionable_total > 0 else 0.0

        # Build response
        statistics = {
            "overview": {
                "total_documents": total_documents,
                "total_techniques": type_counts.get('technique', 0),
                "total_subtechniques": type_counts.get('subtechnique', 0),
                "total_strategies": type_counts.get('strategy', 0),
                "total_actionable_items": actionable_total,
                "last_synced": last_synced,
                "embedding_model": "Xenova/multilingual-e5-base (Quantized Int8)" if query_engine.active_embedding_model == "Xenova/multilingual-e5-base" else query_engine.active_embedding_model,
                "database_path": str(settings.DB_PATH)
            },
            "by_tactic": dict(sorted(tactic_counts.items())),
            "by_pillar": dict(sorted(pillar_counts.items())),
            "by_phase": dict(sorted(phase_counts.items())),
            "threat_framework_coverage": threat_framework_coverage,
            "tools_availability": {
                "techniques_with_opensource_tools": techniques_with_opensource_tools,
                "techniques_with_commercial_tools": techniques_with_commercial_tools,
                "opensource_coverage_percentage": round(
                    (techniques_with_opensource_tools / actionable_total) * 100, 1
                ) if actionable_total > 0 else 0
            },
            "implementation_resources": {
                "documents_with_code_snippets": documents_with_code,
                "strategies_total": type_counts.get('strategy', 0),
                "code_coverage_percentage": round(
                    (documents_with_code / type_counts.get('strategy', 1)) * 100, 1
                ) if type_counts.get('strategy', 0) > 0 else 0
            }
        }

        logger.info(
            "Statistics generated successfully",
            extra={
                "total_documents": total_documents,
                "techniques": type_counts.get('technique', 0),
                "subtechniques": type_counts.get('subtechnique', 0)
            }
        )

        return statistics

    except FileNotFoundError:
        logger.error("Database not found. Please run initial sync.")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to generate statistics: {e}", exc_info=True)
        raise Exception(f"Failed to generate statistics: {str(e)}")
