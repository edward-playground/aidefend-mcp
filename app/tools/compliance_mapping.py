"""
Compliance Mapping Tool for AIDEFEND MCP Service

Maps AIDEFEND techniques to compliance frameworks using heuristic-based analysis.

100% LOCAL - No external API calls, all processing happens locally.
"""

import asyncio
from typing import Dict, Any, List

from app.logger import get_logger
from app.config import settings
from app.security import InputValidationError

logger = get_logger(__name__)

# Supported compliance frameworks
SUPPORTED_FRAMEWORKS = {
    "nist_ai_rmf": "NIST AI Risk Management Framework",
    "eu_ai_act": "EU AI Act",
    "iso_42001": "ISO/IEC 42001 (AI Management System)",
    "csa_ai_controls": "CSA AI Control Matrix",
    "owasp_asvs": "OWASP Application Security Verification Standard"
}


async def map_to_compliance_framework(
    technique_ids: List[str],
    framework: str = "nist_ai_rmf"
) -> Dict[str, Any]:
    """
    Map AIDEFEND techniques to compliance framework requirements.

    Uses heuristic-based analysis to map techniques to framework controls
    based on tactic alignment.

    100% LOCAL - No external API calls, all processing happens locally.

    Args:
        technique_ids: List of AIDEFEND technique IDs to map
        framework: Compliance framework to map to (default: nist_ai_rmf)

    Returns:
        Dict containing compliance mappings for each technique

    Raises:
        InputValidationError: If inputs are invalid
        Exception: If mapping fails

    Example:
        >>> result = await map_to_compliance_framework(
        ...     technique_ids=["AID-H-001", "AID-D-001"],
        ...     framework="nist_ai_rmf"
        ... )
        >>> for mapping in result['mappings']:
        ...     print(f"{mapping['technique_id']} -> {mapping['framework_controls']}")
    """
    import lancedb
    from app.core import query_engine
    from app.exceptions import QueryEngineNotInitializedError

    # Pre-flight check: ensure query engine is ready
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please run 'sync_aidefend' first to download the knowledge base."
        )


    # Input validation
    if not technique_ids:
        raise InputValidationError("technique_ids cannot be empty")

    if len(technique_ids) > 50:
        raise InputValidationError("Too many techniques (max 50)")

    if framework not in SUPPORTED_FRAMEWORKS:
        raise InputValidationError(
            f"Unsupported framework: {framework}. "
            f"Supported: {', '.join(SUPPORTED_FRAMEWORKS.keys())}"
        )

    logger.info(f"Mapping {len(technique_ids)} techniques to {framework}")

    try:
        # Get technique details from database
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

        mappings = []

        for tech_id in technique_ids:
            tech_id = tech_id.strip().upper()

            # Get technique
            docs = await asyncio.to_thread(
                lambda: table.search().where(f"source_id = '{tech_id}'").limit(1).to_pandas().to_dict('records')
            )

            if not docs:
                logger.warning(f"Technique not found: {tech_id}")
                mappings.append({
                    "technique_id": tech_id,
                    "technique_name": "Not Found",
                    "framework": framework,
                    "framework_controls": [],
                    "mapping_confidence": "none",
                    "error": "Technique not found in database"
                })
                continue

            doc = docs[0]

            # Use heuristic-based mapping (100% local)
            mapping = _generate_heuristic_mapping(doc, framework)

            mappings.append(mapping)

        result = {
            "framework": {
                "id": framework,
                "name": SUPPORTED_FRAMEWORKS[framework]
            },
            "mappings": mappings,
            "total_mapped": len(mappings),
            "mapping_method": "heuristic",
            "disclaimer": (
                "Compliance mappings are generated automatically using heuristic "
                "analysis and should be reviewed by compliance experts. Mappings "
                "may not cover all requirements and should be used as guidance only."
            )
        }

        logger.info(f"Generated {len(mappings)} compliance mappings")

        return result

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to map to compliance framework: {e}", exc_info=True)
        raise


def _generate_heuristic_mapping(
    technique: Dict[str, Any],
    framework: str
) -> Dict[str, Any]:
    """
    Generate compliance mapping using heuristics.

    This is a fallback when LLM is not available.
    """
    tech_id = technique.get('source_id')
    tech_name = technique.get('name')
    tactic = technique.get('tactic', '')

    # Framework-specific mappings based on tactic
    framework_mappings = {
        "nist_ai_rmf": {
            "Model": ["GOVERN-1.1", "MAP-2.3"],
            "Harden": ["GOVERN-1.2", "MANAGE-2.1"],
            "Detect": ["MEASURE-2.1", "MANAGE-4.1"],
            "Isolate": ["MANAGE-3.1"],
            "Deceive": ["MANAGE-4.2"],
            "Evict": ["MANAGE-4.3"],
            "Restore": ["MANAGE-4.4"]
        },
        "eu_ai_act": {
            "Model": ["Art. 9 (Risk Management)", "Art. 15 (Accuracy)"],
            "Harden": ["Art. 9 (Risk Management)", "Art. 13 (Transparency)"],
            "Detect": ["Art. 9 (Risk Management)", "Art. 16 (Logs)"],
            "Isolate": ["Art. 9 (Risk Management)"],
            "Deceive": ["Art. 9 (Risk Management)"],
            "Evict": ["Art. 9 (Risk Management)"],
            "Restore": ["Art. 9 (Risk Management)", "Art. 16 (Logs)"]
        },
        "iso_42001": {
            "Model": ["6.1 (Risk Assessment)", "7.4 (Communication)"],
            "Harden": ["8.2 (AI System Controls)", "8.3 (Security)"],
            "Detect": ["8.5 (Monitoring)", "9.1 (Performance Evaluation)"],
            "Isolate": ["8.3 (Security Controls)"],
            "Deceive": ["8.3 (Security Controls)"],
            "Evict": ["8.5 (Incident Response)"],
            "Restore": ["8.5 (Incident Response)", "10.2 (Continual Improvement)"]
        }
    }

    controls = framework_mappings.get(framework, {}).get(tactic, [])

    return {
        "technique_id": tech_id,
        "technique_name": tech_name,
        "technique_tactic": tactic,
        "framework": framework,
        "framework_name": SUPPORTED_FRAMEWORKS[framework],
        "framework_controls": controls,
        "mapping_confidence": "medium" if controls else "low",
        "mapping_rationale": f"Mapped based on tactic '{tactic}' alignment with framework requirements",
        "additional_considerations": [
            "Review with compliance team for completeness",
            "May require additional controls depending on specific use case",
            "Consider combination with other techniques for full compliance"
        ]
    }
