"""
Threat Coverage Tool for AIDEFEND MCP Service

Analyzes threat coverage for implemented defense techniques across
OWASP LLM Top 10, MITRE ATLAS, and MAESTRO frameworks.

This tool performs reverse mapping: given a list of implemented techniques,
it identifies which threats are covered and calculates coverage rates.
"""

from typing import Dict, Any, List

from app.logger import get_logger
from app.core import decode_framework_record
from app.security import InputValidationError, sanitize_technique_id
from app.framework_utils import (
    coverage_lists_from_sets,
    extract_framework_coverage,
    is_actionable_record,
    merge_framework_coverage_sets,
    parse_json_list,
    public_framework_coverage_mapping,
    resolve_control_ids,
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
    if not all(isinstance(technique_id, str) for technique_id in implemented_techniques):
        raise InputValidationError("implemented_techniques must contain only strings")

    if len(implemented_techniques) > 200:
        raise InputValidationError("Too many techniques (max 200)")

    # Pre-flight check: ensure query engine is ready (AFTER parameter validation)
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please run 'sync_aidefend' first to download the knowledge base."
        )

    # Normalize technique IDs (uppercase, strip)
    normalized_techniques = list(dict.fromkeys(
        tid.strip().upper() for tid in implemented_techniques
    ))

    logger.info(f"Analyzing threat coverage for {len(normalized_techniques)} techniques")

    try:
        # Load all technique-like records once. We filter in Python because the
        # latest framework distinguishes actionable sub-techniques from umbrella
        # parent techniques.
        all_records = await query_engine.read_table(
            lambda table: table.search().where(
                "type = 'technique' OR type = 'subtechnique'"
            ).to_pandas().to_dict('records')
        )
        all_records = [decode_framework_record(record) for record in all_records]

        records_by_id = {record.get("source_id"): record for record in all_records}
        actionable_records = {
            record.get("source_id"): record
            for record in all_records
            if is_actionable_record(record)
        }
        total_threats = merge_framework_coverage_sets()

        for record in actionable_records.values():
            total_threats = merge_framework_coverage_sets(
                total_threats,
                extract_framework_coverage(record['defends_against']),
            )

        resolution = resolve_control_ids(normalized_techniques, all_records)
        expanded_parent_families = resolution["expanded_parent_families"]
        invalid_techniques = resolution["unrecognized_ids"]
        invalid_set = set(invalid_techniques)

        covered_threats = merge_framework_coverage_sets()
        by_technique = []
        valid_techniques = []

        for tech_id in normalized_techniques:
            sanitized_id = sanitize_technique_id(tech_id)

            if sanitized_id in invalid_set:
                logger.warning(f"Technique not found: {tech_id}")
                continue

            docs_to_analyze = []
            coverage_scope = "actionable_item"

            if sanitized_id in actionable_records:
                docs_to_analyze = [actionable_records[sanitized_id]]
            elif sanitized_id in expanded_parent_families:
                docs_to_analyze = [
                    actionable_records[child_id]
                    for child_id in expanded_parent_families[sanitized_id]
                ]
                coverage_scope = "aggregated_subtechniques"
            else:
                logger.warning(f"Technique not found: {tech_id}")
                continue

            valid_techniques.append(tech_id)
            technique_coverage = merge_framework_coverage_sets()

            for doc in docs_to_analyze:
                technique_coverage = merge_framework_coverage_sets(
                    technique_coverage,
                    extract_framework_coverage(doc['defends_against']),
                )

            covered_threats = merge_framework_coverage_sets(covered_threats, technique_coverage)
            doc_for_label = records_by_id.get(sanitized_id, docs_to_analyze[0])

            by_technique.append({
                "technique_id": tech_id,
                "technique_name": doc_for_label.get('name', 'Unknown'),
                "tactic": doc_for_label.get('tactic', 'Unknown'),
                "coverage_scope": coverage_scope,
                "pillar": doc_for_label['pillar'],
                "phase": doc_for_label['phase'],
                "scope_boundary": doc_for_label['scope_boundary'],
                "is_actionable": doc_for_label['is_actionable'],
                "is_parent_family": doc_for_label['is_parent_family'],
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
            "resolved_actionable_count": len(resolution["actionable_ids"]),
            "expanded_parent_families": expanded_parent_families,
            "covered": coverage_lists_from_sets(covered_threats),
            "coverage_rate": public_framework_coverage_mapping(coverage_rate),
            "framework_totals": public_framework_coverage_mapping(framework_totals),
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
