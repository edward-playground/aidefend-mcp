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

    # Try to load pre-computed statistics from version file (optimization)
    from app.utils import load_version_info
    version_info = load_version_info()

    if version_info and "statistics" in version_info:
        logger.info("Using pre-computed statistics from version file (fast path)")
        return version_info["statistics"]

    # Fallback: Calculate statistics from database (slow path)
    logger.warning("Pre-computed statistics not found, performing full table scan (slow)")
    import lancedb
    from app.core import query_engine
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

        # Framework coverage tracking
        owasp_items = set()
        atlas_items = set()
        maestro_items = set()

        # Scan documents
        for doc in all_docs:
            doc_type = doc.get('type', 'unknown')
            tactic = doc.get('tactic', 'Unknown')
            pillar = doc.get('pillar', '')
            phase = doc.get('phase', '')

            # Count by type
            type_counts[doc_type] += 1

            # Count by tactic (all documents)
            tactic_counts[tactic] += 1

            # Count by pillar (only if not empty)
            if pillar:
                pillar_counts[pillar] += 1

            # Count by phase (only if not empty)
            if phase:
                phase_counts[phase] += 1

            # Enhanced features (only for techniques)
            if doc_type == 'technique':
                # Parse defends_against field
                defends_against_str = doc.get('defends_against', '[]')
                try:
                    defends_against = json.loads(defends_against_str) if isinstance(defends_against_str, str) else defends_against_str

                    if defends_against:
                        techniques_with_defenses += 1

                        # Extract threat items by framework
                        for framework_data in defends_against:
                            framework_name = framework_data.get('framework', '')
                            items = framework_data.get('items', [])

                            if 'OWASP' in framework_name:
                                owasp_items.update(items)
                            elif 'ATLAS' in framework_name or 'MITRE' in framework_name:
                                atlas_items.update(items)
                            elif 'MAESTRO' in framework_name:
                                maestro_items.update(items)

                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Failed to parse defends_against for {doc.get('source_id')}")

                # Parse tools
                tools_opensource_str = doc.get('tools_opensource', '[]')
                tools_commercial_str = doc.get('tools_commercial', '[]')

                try:
                    tools_opensource = json.loads(tools_opensource_str) if isinstance(tools_opensource_str, str) else tools_opensource_str
                    tools_commercial = json.loads(tools_commercial_str) if isinstance(tools_commercial_str, str) else tools_commercial_str

                    if tools_opensource:
                        techniques_with_opensource_tools += 1
                    if tools_commercial:
                        techniques_with_commercial_tools += 1

                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Failed to parse tools for {doc.get('source_id')}")

            # Check for code snippets
            has_code = doc.get('has_code_snippets', False)
            if has_code:
                documents_with_code += 1

        # Get last sync time from version file
        from app.utils import load_version_info
        version_info = load_version_info()
        last_synced = version_info.get("last_sync", "Unknown")

        # Build response
        statistics = {
            "overview": {
                "total_documents": total_documents,
                "total_techniques": type_counts.get('technique', 0),
                "total_subtechniques": type_counts.get('subtechnique', 0),
                "total_strategies": type_counts.get('strategy', 0),
                "last_synced": last_synced,
                "embedding_model": settings.EMBEDDING_MODEL,
                "database_path": str(settings.DB_PATH)
            },
            "by_tactic": dict(sorted(tactic_counts.items())),
            "by_pillar": dict(sorted(pillar_counts.items())),
            "by_phase": dict(sorted(phase_counts.items())),
            "threat_framework_coverage": {
                "owasp_llm_items_covered": len(owasp_items),
                "mitre_atlas_items_covered": len(atlas_items),
                "maestro_items_covered": len(maestro_items),
                "techniques_with_threat_mappings": techniques_with_defenses,
                "coverage_percentage": round(
                    (techniques_with_defenses / type_counts.get('technique', 1)) * 100, 1
                ) if type_counts.get('technique', 0) > 0 else 0
            },
            "tools_availability": {
                "techniques_with_opensource_tools": techniques_with_opensource_tools,
                "techniques_with_commercial_tools": techniques_with_commercial_tools,
                "opensource_coverage_percentage": round(
                    (techniques_with_opensource_tools / type_counts.get('technique', 1)) * 100, 1
                ) if type_counts.get('technique', 0) > 0 else 0
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
