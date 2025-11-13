"""
Threat Coverage Tool for AIDEFEND MCP Service

Analyzes threat coverage for implemented defense techniques across
OWASP LLM Top 10, MITRE ATLAS, and MAESTRO frameworks.

This tool performs reverse mapping: given a list of implemented techniques,
it identifies which threats are covered and calculates coverage rates.
"""

import json
import asyncio
import lancedb
from typing import Dict, Any, List, Set
from collections import defaultdict

from app.logger import get_logger
from app.config import settings
from app.security import InputValidationError

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
    # Input validation
    if not implemented_techniques:
        raise InputValidationError("implemented_techniques cannot be empty")

    if not isinstance(implemented_techniques, list):
        raise InputValidationError("implemented_techniques must be a list")

    if len(implemented_techniques) > 100:
        raise InputValidationError("Too many techniques (max 100)")

    # Normalize technique IDs (uppercase, strip)
    normalized_techniques = [tid.strip().upper() for tid in implemented_techniques]

    logger.info(f"Analyzing threat coverage for {len(normalized_techniques)} techniques")

    try:
        # Connect to LanceDB
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

        # Initialize result structures
        covered_threats = {"owasp": set(), "atlas": set(), "maestro": set()}
        by_technique = []
        valid_techniques = []
        invalid_techniques = []

        # Process each technique
        for tech_id in normalized_techniques:
            # Query technique from database
            results = await asyncio.to_thread(
                lambda tid=tech_id: table.search().where(
                    f"source_id = '{tid}' AND type = 'technique'"
                ).limit(1).to_pandas().to_dict('records')
            )

            if not results:
                logger.warning(f"Technique not found: {tech_id}")
                invalid_techniques.append(tech_id)
                continue

            tech = results[0]
            valid_techniques.append(tech_id)

            # Parse defends_against field
            defends_against_str = tech.get('defends_against', '[]')
            try:
                defends_against = json.loads(defends_against_str) if isinstance(defends_against_str, str) else defends_against_str
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse defends_against for {tech_id}")
                defends_against = []

            # Extract threats per technique
            technique_threats = {"owasp": [], "atlas": [], "maestro": []}

            if defends_against:
                for framework_data in defends_against:
                    framework_name = framework_data.get('framework', '').upper()
                    items = framework_data.get('items', [])

                    for item in items:
                        # Extract normalized threat IDs from item text
                        extracted_ids = _extract_threat_ids(item)

                        for framework_key, threat_ids in extracted_ids.items():
                            technique_threats[framework_key].extend(threat_ids)
                            covered_threats[framework_key].update(threat_ids)

            # Add to by_technique list
            by_technique.append({
                "technique_id": tech_id,
                "technique_name": tech.get('name', 'Unknown'),
                "tactic": tech.get('tactic', 'Unknown'),
                "threats_covered": {
                    "owasp": list(set(technique_threats["owasp"])),
                    "atlas": list(set(technique_threats["atlas"])),
                    "maestro": list(set(technique_threats["maestro"]))
                }
            })

        # Calculate coverage rates
        # OWASP LLM Top 10: 10 items
        # MITRE ATLAS: ~43 techniques (approximate)
        # MAESTRO: TBD
        coverage_rate = {
            "owasp": round(len(covered_threats["owasp"]) / 10, 3) if covered_threats["owasp"] else 0.0,
            "atlas": round(len(covered_threats["atlas"]) / 43, 3) if covered_threats["atlas"] else 0.0,
            "maestro": round(len(covered_threats["maestro"]) / 1, 3) if covered_threats["maestro"] else 0.0
        }

        result = {
            "input_count": len(normalized_techniques),
            "valid_count": len(valid_techniques),
            "invalid_count": len(invalid_techniques),
            "invalid_techniques": invalid_techniques,
            "covered": {
                "owasp": sorted(list(covered_threats["owasp"])),
                "atlas": sorted(list(covered_threats["atlas"])),
                "maestro": sorted(list(covered_threats["maestro"]))
            },
            "coverage_rate": coverage_rate,
            "by_technique": by_technique
        }

        logger.info(
            f"Coverage analysis complete: {len(valid_techniques)} valid techniques, "
            f"OWASP: {len(covered_threats['owasp'])}, ATLAS: {len(covered_threats['atlas'])}"
        )

        return result

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to analyze threat coverage: {e}", exc_info=True)
        raise


def _extract_threat_ids(item_text: str) -> Dict[str, List[str]]:
    """
    Extract normalized threat IDs from defends_against item text.

    Examples:
        "LLM01:2025 Prompt Injection" -> {"owasp": ["LLM01"]}
        "AML.T0043 Adversarial Examples" -> {"atlas": ["AML.T0043"]}
        "T0020 Data Poisoning" -> {"atlas": ["AML.T0020"]}

    Args:
        item_text: Item text from defends_against field

    Returns:
        Dict with {framework -> [threat_ids]}
    """
    import re

    result = {"owasp": [], "atlas": [], "maestro": []}
    item_upper = item_text.upper()

    # Extract OWASP LLM IDs (LLM##)
    llm_match = re.search(r'LLM\d{2}', item_upper)
    if llm_match:
        result["owasp"].append(llm_match.group(0))

    # Extract MITRE ATLAS IDs (T#### or AML.T####)
    # First try AML.T#### format
    atlas_match = re.search(r'AML\.T\d{4}', item_upper)
    if atlas_match:
        result["atlas"].append(atlas_match.group(0))
    else:
        # Try T#### format and add AML. prefix
        t_match = re.search(r'T\d{4}', item_upper)
        if t_match:
            t_id = t_match.group(0)
            result["atlas"].append(f"AML.{t_id}")

    # MAESTRO: Add logic when available
    # (Currently AIDEFEND framework doesn't have MAESTRO mappings)

    return result
