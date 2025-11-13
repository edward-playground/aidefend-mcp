"""
Compliance Mapping Tool for AIDEFEND MCP Service

Maps AIDEFEND techniques to compliance frameworks using LLM-based analysis.
"""

import asyncio
from typing import Dict, Any, List, Optional

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
    framework: str = "nist_ai_rmf",
    use_llm: bool = True
) -> Dict[str, Any]:
    """
    Map AIDEFEND techniques to compliance framework requirements.

    Uses LLM (Claude API) to dynamically generate mappings based on
    technique descriptions and framework requirements.

    Args:
        technique_ids: List of AIDEFEND technique IDs to map
        framework: Compliance framework to map to (default: nist_ai_rmf)
        use_llm: Whether to use LLM for mapping (default: True)

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

            if use_llm:
                # Use LLM to generate mapping
                mapping = await _generate_llm_mapping(doc, framework)
            else:
                # Use heuristic-based mapping (fallback)
                mapping = _generate_heuristic_mapping(doc, framework)

            mappings.append(mapping)

        result = {
            "framework": {
                "id": framework,
                "name": SUPPORTED_FRAMEWORKS[framework]
            },
            "mappings": mappings,
            "total_mapped": len(mappings),
            "mapping_method": "llm" if use_llm else "heuristic",
            "disclaimer": (
                "Compliance mappings are generated automatically and should be "
                "reviewed by compliance experts. Mappings may not cover all "
                "requirements and should be used as guidance only."
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


async def _generate_llm_mapping(
    technique: Dict[str, Any],
    framework: str
) -> Dict[str, Any]:
    """
    Generate compliance mapping using Claude LLM.

    Uses Claude API to analyze the technique and map it to compliance framework
    controls. Falls back to heuristic mapping if API is unavailable or fails.
    """
    tech_id = technique.get('source_id')
    tech_name = technique.get('name')
    tactic = technique.get('tactic', '')
    description = technique.get('text', '')[:1000]  # First 1000 chars for context

    logger.info(f"Generating LLM mapping for {tech_id} to {framework}")

    # Check if API key is available
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured. Falling back to heuristic mapping.")
        return _generate_heuristic_mapping(technique, framework)

    try:
        # Import Anthropic SDK
        try:
            from anthropic import Anthropic
        except ImportError:
            logger.warning("anthropic package not installed. Falling back to heuristic mapping.")
            return _generate_heuristic_mapping(technique, framework)

        # Initialize Claude client
        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Build prompt for compliance mapping
        framework_name = SUPPORTED_FRAMEWORKS[framework]

        prompt = f"""You are a compliance expert specializing in AI security frameworks.

I need you to map an AI security defense technique to specific controls in the {framework_name} framework.

**Technique Information:**
- ID: {tech_id}
- Name: {tech_name}
- Tactic: {tactic}
- Description: {description}

**Task:**
Map this technique to specific {framework_name} controls or requirements. Consider:
1. Which controls/requirements does this technique help satisfy?
2. How confident is this mapping? (high/medium/low)
3. What is the rationale for this mapping?
4. Are there any additional considerations for implementation?

**Output Format (JSON):**
{{
    "framework_controls": ["control-id-1", "control-id-2", ...],
    "mapping_confidence": "high|medium|low",
    "mapping_rationale": "Brief explanation of why these controls apply",
    "additional_considerations": ["consideration-1", "consideration-2", ...]
}}

Provide only the JSON object, no additional text."""

        # Call Claude API
        response = await asyncio.to_thread(
            lambda: client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=settings.CLAUDE_MAX_TOKENS,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
        )

        # Parse response
        import json
        response_text = response.content[0].text.strip()

        # Extract JSON from response (in case there's extra text)
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        if start_idx >= 0 and end_idx > start_idx:
            json_text = response_text[start_idx:end_idx]
            llm_result = json.loads(json_text)
        else:
            raise ValueError("No JSON found in response")

        # Build result
        result = {
            "technique_id": tech_id,
            "technique_name": tech_name,
            "technique_tactic": tactic,
            "framework": framework,
            "framework_name": framework_name,
            "framework_controls": llm_result.get("framework_controls", []),
            "mapping_confidence": llm_result.get("mapping_confidence", "medium"),
            "mapping_rationale": llm_result.get("mapping_rationale", ""),
            "additional_considerations": llm_result.get("additional_considerations", [])
        }

        logger.info(
            f"LLM mapping completed for {tech_id}: {len(result['framework_controls'])} controls",
            extra={"confidence": result["mapping_confidence"]}
        )

        return result

    except Exception as e:
        logger.warning(
            f"LLM mapping failed for {tech_id}: {e}. Falling back to heuristic mapping.",
            exc_info=True
        )
        return _generate_heuristic_mapping(technique, framework)


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
