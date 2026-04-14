"""
Threat Coverage Tool for AIDEFEND MCP Service

Analyzes threat coverage for implemented defense techniques across
OWASP LLM Top 10, MITRE ATLAS, and MAESTRO frameworks.

This tool performs reverse mapping: given a list of implemented techniques,
it identifies which threats are covered and calculates coverage rates.
"""

import asyncio
import lancedb
from typing import Dict, Any, List
from collections import defaultdict

from app.logger import get_logger
from app.config import settings
from app.security import InputValidationError, sanitize_technique_id
from app.framework_utils import (
    coverage_lists_from_sets,
    extract_framework_coverage,
    is_actionable_record,
    merge_framework_coverage_sets,
    parse_json_list,
)

logger = get_logger(__name__)


async def get_threat_coverage(implemented_techniques: List[str]) -> Dict[str, Any]:
    """
    Analyze threat coverage for implemented defense techniques.

    Given a list of implemented technique IDs, this function:
    1. Validates each technique ID
    2. Retrieves defends_against data for each technique
    3. Aggregates all covered threats (deduplicated)
    4. Calculates coverage rates for each framework

    Args:
        implemented_techniques: List of implemented technique IDs
                               (e.g., ["AID-D-001", "AID-H-002"])

    Returns:
        Dict containing:
        - input_count: Number of techniques provided
        - valid_count: Number of valid techniques
        - invalid_techniques: List of invalid technique IDs
        - covered: Dict of {framework -> [threat_ids]}
        - coverage_rate: Dict of {framework -> percentage}
        - by_technique: Detailed mapping per technique

    Raises:
        InputValidationError: If input validation fails
        Exception: If database query fails

    Example:
        >>> result = await get_threat_coverage(["AID-D-001", "AID-H-002"])
        >>> print(f"OWASP coverage: {result['covered']['owasp']}")
        ['LLM01', 'LLM02']
    """
    from app.core import query_engine
    from app.exceptions import QueryEngineNotInitializedError

    # Input validation (check parameters BEFORE database check)
    # Note: Empty array is allowed for baseline threat coverage analysis (0% coverage)

    if not isinstance(implemented_techniques, list):
        raise InputValidationError("implemented_techniques must be a list")

    if len(implemented_techniques) > 100:
        raise InputValidationError("Too many techniques (max 100)")

    # Pre-flight check: ensure query engine is ready (AFTER parameter validation)
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please run 'sync_aidefend' first to download the knowledge base."
        )

    # Normalize technique IDs (uppercase, strip)
    normalized_techniques = [tid.strip().upper() for tid in implemented_techniques]

    logger.info(f"Analyzing threat coverage for {len(normalized_techniques)} techniques")

    try:
        # Connect to LanceDB
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

        # Load all technique-like records once. We filter in Python because the
        # latest framework distinguishes actionable sub-techniques from umbrella
        # parent techniques.
        all_records = await asyncio.to_thread(
            lambda: table.search().where(
                "type = 'technique' OR type = 'subtechnique'"
            ).to_pandas().to_dict('records')
        )

        records_by_id = {record.get("source_id"): record for record in all_records}
        actionable_records = {
            record.get("source_id"): record
            for record in all_records
            if is_actionable_record(record)
        }
        parent_to_children = defaultdict(list)
        total_threats = merge_framework_coverage_sets()

        for record in actionable_records.values():
            parent_id = record.get("parent_technique_id")
            if parent_id:
                parent_to_children[parent_id].append(record)

            total_threats = merge_framework_coverage_sets(
                total_threats,
                extract_framework_coverage(parse_json_list(record.get("defends_against", "[]"))),
            )

        covered_threats = merge_framework_coverage_sets()
        by_technique = []
        valid_techniques = []
        invalid_techniques = []

        for tech_id in normalized_techniques:
            sanitized_id = sanitize_technique_id(tech_id)

            docs_to_analyze = []
            coverage_scope = "actionable_item"

            if sanitized_id in actionable_records:
                docs_to_analyze = [actionable_records[sanitized_id]]
            elif sanitized_id in parent_to_children:
                docs_to_analyze = parent_to_children[sanitized_id]
                coverage_scope = "aggregated_subtechniques"
            else:
                logger.warning(f"Technique not found: {tech_id}")
                invalid_techniques.append(tech_id)
                continue

            valid_techniques.append(tech_id)
            technique_coverage = merge_framework_coverage_sets()

            for doc in docs_to_analyze:
                technique_coverage = merge_framework_coverage_sets(
                    technique_coverage,
                    extract_framework_coverage(parse_json_list(doc.get("defends_against", "[]"))),
                )

            covered_threats = merge_framework_coverage_sets(covered_threats, technique_coverage)
            doc_for_label = records_by_id.get(sanitized_id, docs_to_analyze[0])

            by_technique.append({
                "technique_id": tech_id,
                "technique_name": doc_for_label.get('name', 'Unknown'),
                "tactic": doc_for_label.get('tactic', 'Unknown'),
                "coverage_scope": coverage_scope,
                "threats_covered": coverage_lists_from_sets(technique_coverage)
            })

        coverage_rate = {}
        framework_totals = {}
        for key, total_set in total_threats.items():
            total = len(total_set)
            framework_totals[key] = total
            coverage_rate[key] = round(len(covered_threats.get(key, set())) / total, 3) if total else 0.0

        result = {
            "input_count": len(normalized_techniques),
            "valid_count": len(valid_techniques),
            "invalid_count": len(invalid_techniques),
            "invalid_techniques": invalid_techniques,
            "covered": coverage_lists_from_sets(covered_threats),
            "coverage_rate": coverage_rate,
            "framework_totals": framework_totals,
            "by_technique": by_technique
        }

        logger.info(
            f"Coverage analysis complete: {len(valid_techniques)} valid techniques, "
            f"OWASP(all): {len(covered_threats['owasp'])}, ATLAS: {len(covered_threats['atlas'])}"
        )

        return result

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to analyze threat coverage: {e}", exc_info=True)
        raise
