"""
Technique Comparison Matrix Tool for AIDEFEND MCP Service

Provides side-by-side comparison of multiple AIDEFEND techniques with
heuristic-based scoring for effectiveness, complexity, and cost.

All scoring is 100% local using metadata analysis - no ML inference required.
"""

import asyncio
import json
import lancedb
from typing import Dict, Any, List, Optional

from app.logger import get_logger
from app.config import settings
from app.security import InputValidationError, sanitize_technique_id
from app.core import query_engine
from app.exceptions import QueryEngineNotInitializedError
from app.framework_utils import (
    FRAMEWORK_LABELS,
    extract_framework_coverage,
    merge_framework_coverage_sets,
)

logger = get_logger(__name__)


def _parse_json_field(field_value: Any) -> Any:
    """Parse JSON string field, return parsed value or empty list."""
    if not field_value:
        return []

    if isinstance(field_value, str):
        try:
            return json.loads(field_value)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON field: {field_value[:100]}")
            return []

    return field_value


def _detect_defense_type(tactic: str, description: str) -> str:
    """
    Detect the type of defense based on keywords.
    Returns: 'prevention', 'detection', 'response', or 'unknown'
    """
    text = (tactic + " " + description).lower()
    if any(k in text for k in ["harden", "prevent", "filter", "block", "sanitize", "output validation", "input validation", "firewall"]):
        return "prevention"
    if any(k in text for k in ["detect", "monitor", "log", "audit", "alert", "scan", "identif"]):
        return "detection"
    if any(k in text for k in ["respond", "isolate", "recover", "mitigate", "incident", "investigat"]):
        return "response"
    return "unknown"


def _has_keywords(text: str, keywords: List[str]) -> bool:
    """Check if text contains any of the keywords."""
    text_lower = text.lower()
    return any(k in text_lower for k in keywords)


def _calculate_effectiveness_score(technique_doc: Dict[str, Any]) -> int:
    """
    Calculate effectiveness score using Quality > Quantity heuristic.
    
    New Scoring (0-100):
    - Base: 20 points
    - Defense Type: Prevention (+25), Detection (+15), Response (+10)
    - Asset Criticality: Model/Training Data related (+15)
    - Validation Ready: Mentions verify/test (+10)
    - Threat Coverage: +5 per threat (Max 20)
    - Implementation Ready: Strategies/Code (+10)
    """
    score = 20  # Lower base score to allow quality factors to dominate
    
    description = technique_doc.get('text', '')
    tactic = technique_doc.get('tactic', '')
    pillars = _parse_json_field(technique_doc.get('pillar', ''))
    pillar_lower = [p.lower() for p in pillars] if isinstance(pillars, list) else []

    # 1. Defense Type Weighting
    defense_type = _detect_defense_type(tactic, description)
    if defense_type == "prevention":
        score += 25
    elif defense_type == "detection":
        score += 15
    elif defense_type == "response":
        score += 10
        
    # 2. Asset Criticality (Model-centric is critical for specialized AI security)
    if 'model' in pillar_lower:
        score += 15
        
    # 3. Validation Bonus
    if _has_keywords(description, ["verify", "test", "validation", "evaluat", "assess"]):
        score += 10

    # 4. Threat Coverage (Capped count)
    defends_against = _parse_json_field(technique_doc.get('defends_against', '[]'))
    threat_count = 0
    if isinstance(defends_against, list):
        for item in defends_against:
            if isinstance(item, dict) and 'items' in item:
                threat_count += len(item.get('items', []))
    score += min(threat_count * 5, 20)  # Max 20 points

    # 5. Implementation Readiness
    impl_strategies = _parse_json_field(technique_doc.get('implementation_guidance', '[]'))
    has_code = technique_doc.get('has_code_snippets', False)

    if (impl_strategies and len(impl_strategies) > 0) or has_code:
        score += 10

    return min(score, 100)


def _calculate_complexity_score(technique_doc: Dict[str, Any]) -> int:
    """
    Calculate complexity score reflecting implementation friction.
    
    New Scoring (0-100):
    - Base: 20 points
    - Cross-Domain Friction: Infra+Model (+25), App+Model (+15)
    - Human Dependency: Policy/Process/Training (+15)
    - Code Complexity: No snippets but specific tools (+15)
    - Tactic/Phase: Building phase (+10)
    """
    score = 20
    
    description = technique_doc.get('text', '')
    pillars = _parse_json_field(technique_doc.get('pillar', ''))
    pillar_lower = [p.lower() for p in pillars] if isinstance(pillars, list) else []
    
    # 1. Cross-Domain Friction
    has_infra = 'infra' in pillar_lower or 'infrastructure' in pillar_lower
    has_model = 'model' in pillar_lower
    has_app = 'app' in pillar_lower or 'application' in pillar_lower
    
    if has_infra and has_model:
        score += 25  # Hardest: Data Scientist + DevOps coordination
    elif has_app and has_model:
        score += 15  # Hard: Data Scientist + App Dev coordination
        
    # 2. Human Dependency (Process is harder to maintain than tech)
    if _has_keywords(description, ["policy", "process", "review", "training", "governance", "manual"]):
        score += 15
        
    # 3. Hidden Complexity (Tools without code samples)
    has_code = technique_doc.get('has_code_snippets', False)
    opensource_tools = _parse_json_field(technique_doc.get('tools_opensource', '[]'))
    has_tools = opensource_tools and len(opensource_tools) > 0
    
    if has_tools and not has_code:
        score += 15  # Implies configuration/setup effort without copy-paste help

    # 4. Phase and Scale
    phase_raw = technique_doc.get('phase', '')
    phases = _parse_json_field(phase_raw)
    phase_lower = [p.lower() for p in phases] if isinstance(phases, list) else []
    
    if 'building' in phase_lower:
        score += 10 # Design-time integration
        
    # Sub-technique check (depth implies complexity)
    source_id = technique_doc.get('source_id', '')
    if '.' in source_id: 
         score += 5 # Sub-techniques are specific but often detailed

    return min(score, 100)


def _calculate_cost_score(technique_doc: Dict[str, Any]) -> int:
    """
    Calculate cost score based on OpEx (Operations) and CapEx (Tooling).
    
    New Scoring (0-100):
    - Base: 30 points
    - Operational Overhead (OpEx): Detection/Logging (+15), Prevention (+5)
    - Cloud/Infrastructure: Cloud keywords/Infra pillar (+15)
    - Enterprise Tooling (CapEx): Commercial tools (+20)
    - Mitigation: Open source only (-10)
    """
    score = 30
    
    description = technique_doc.get('text', '')
    tactic = technique_doc.get('tactic', '')
    
    # 1. Operational Overhead (OpEx)
    defense_type = _detect_defense_type(tactic, description)
    if defense_type == "detection":
        score += 15  # High OpEx: Storage, Analysis, Alert Triage
    elif defense_type == "prevention":
        score += 5   # Low OpEx: Set and forget (mostly)
        
    # 2. Cloud/Infrastructure Costs
    pillars = _parse_json_field(technique_doc.get('pillar', ''))
    pillar_lower = [p.lower() for p in pillars] if isinstance(pillars, list) else []
    
    if 'infra' in pillar_lower or 'infrastructure' in pillar_lower or \
       _has_keywords(description, ["aws", "azure", "gcp", "cloud", "kubernetes", "cluster"]):
        score += 15
        
    # 3. Enterprise Tooling (CapEx)
    commercial_tools = _parse_json_field(technique_doc.get('tools_commercial', '[]'))
    if commercial_tools and len(commercial_tools) > 0:
        score += 20
        
    # 4. Mitigation (Open Source)
    opensource_tools = _parse_json_field(technique_doc.get('tools_opensource', '[]'))
    if opensource_tools and len(opensource_tools) > 0 and not commercial_tools:
        score -= 10
        
    return max(0, min(score, 100))


def _extract_technique_info(technique_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and format technique information for comparison.

    Args:
        technique_doc: Technique document from LanceDB

    Returns:
        Formatted technique info dict
    """
    defends_against = _parse_json_field(technique_doc.get('defends_against', '[]'))
    impl_strategies = _parse_json_field(technique_doc.get('implementation_guidance', '[]'))
    opensource_tools = _parse_json_field(technique_doc.get('tools_opensource', '[]'))
    commercial_tools = _parse_json_field(technique_doc.get('tools_commercial', '[]'))

    coverage_sets = merge_framework_coverage_sets(
        extract_framework_coverage(defends_against)
    )
    threat_summary = {
        "owasp": len(coverage_sets["owasp"]),
        "atlas": len(coverage_sets["atlas"]),
        "maestro": len(coverage_sets["maestro"]),
        "by_framework": {
            key: len(coverage_sets.get(key, set()))
            for key in FRAMEWORK_LABELS
        }
    }

    return {
        "source_id": technique_doc.get('source_id', ''),
        "name": technique_doc.get('name', ''),
        "tactic": technique_doc.get('tactic', ''),
        "pillar": technique_doc.get('pillar', ''),
        "phase": technique_doc.get('phase', ''),
        "type": technique_doc.get('type', ''),
        "description": technique_doc.get('text', '')[:200] + "..." if len(technique_doc.get('text', '')) > 200 else technique_doc.get('text', ''),
        "threat_coverage": threat_summary,
        "has_implementation_guidance": len(impl_strategies) > 0 if isinstance(impl_strategies, list) else False,
        "has_code_snippets": technique_doc.get('has_code_snippets', False),
        "has_opensource_tools": len(opensource_tools) > 0 if isinstance(opensource_tools, list) else False,
        "has_commercial_tools": len(commercial_tools) > 0 if isinstance(commercial_tools, list) else False,
        "effectiveness_score": _calculate_effectiveness_score(technique_doc),
        "complexity_score": _calculate_complexity_score(technique_doc),
        "cost_score": _calculate_cost_score(technique_doc)
    }


async def compare_techniques(
    technique_ids: List[str],
    include_recommendations: bool = True
) -> Dict[str, Any]:
    """
    Compare multiple AIDEFEND techniques side-by-side with heuristic scoring.

    Provides a comparison matrix showing effectiveness, complexity, and cost scores
    for each technique, along with recommendations for prioritization.

    All scoring is 100% local using metadata analysis - no external API calls.

    Args:
        technique_ids: List of technique IDs to compare (2-10 techniques)
                      e.g., ["AID-H-001", "AID-D-002", "AID-I-003"]
        include_recommendations: Include prioritization recommendations (default: True)

    Returns:
        Dict containing:
            - input_techniques: List of requested technique IDs
            - comparison_matrix: List of technique comparison data
            - summary: Overall comparison summary
            - recommendations: Prioritization recommendations (if requested)

    Raises:
        InputValidationError: If inputs are invalid
        QueryEngineNotInitializedError: If database is not ready
        Exception: If comparison fails

    Example:
        >>> result = await compare_techniques(["AID-H-001", "AID-D-002"])
        >>> print(f"Comparing {len(result['comparison_matrix'])} techniques")
        >>> for tech in result['comparison_matrix']:
        ...     print(f"{tech['source_id']}: Effectiveness={tech['effectiveness_score']}")
    """
    # Input validation (check parameters BEFORE database check)
    if not technique_ids or not isinstance(technique_ids, list):
        raise InputValidationError("technique_ids must be a non-empty list")

    if len(technique_ids) < 2:
        raise InputValidationError("At least 2 techniques required for comparison (got {})".format(len(technique_ids)))

    if len(technique_ids) > 10:
        raise InputValidationError("Maximum 10 techniques allowed for comparison (got {})".format(len(technique_ids)))

    # Normalize technique IDs
    technique_ids = [tid.strip().upper() for tid in technique_ids]

    # Remove duplicates while preserving order
    seen = set()
    unique_ids = []
    for tid in technique_ids:
        if tid not in seen:
            seen.add(tid)
            unique_ids.append(tid)

    technique_ids = unique_ids

    # Pre-flight check (AFTER parameter validation)
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please wait for initial sync to complete."
        )

    logger.info(
        f"Comparing {len(technique_ids)} techniques",
        extra={"technique_count": len(technique_ids), "technique_ids": technique_ids}
    )

    try:
        # Connect to LanceDB
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

        # Fetch all requested techniques
        comparison_matrix = []
        not_found = []

        for technique_id in technique_ids:
            logger.debug(f"Fetching technique: {technique_id}")

            # Sanitize technique_id to prevent filter injection
            sanitized_id = sanitize_technique_id(technique_id)

            docs = await asyncio.to_thread(
                lambda tid=sanitized_id: table.search()
                .where(f"source_id = '{tid}'")
                .limit(1)
                .to_pandas()
                .to_dict('records')
            )

            if not docs:
                logger.warning(f"Technique not found: {technique_id}")
                not_found.append(technique_id)
                continue

            # Extract and score technique
            technique_info = _extract_technique_info(docs[0])
            comparison_matrix.append(technique_info)

        if len(comparison_matrix) < 2:
            raise InputValidationError(
                f"Insufficient valid techniques for comparison. Found: {len(comparison_matrix)}, Required: 2"
            )

        # Generate summary
        avg_effectiveness = sum(t['effectiveness_score'] for t in comparison_matrix) / len(comparison_matrix)
        avg_complexity = sum(t['complexity_score'] for t in comparison_matrix) / len(comparison_matrix)
        avg_cost = sum(t['cost_score'] for t in comparison_matrix) / len(comparison_matrix)

        summary = {
            "techniques_compared": len(comparison_matrix),
            "techniques_not_found": not_found,
            "average_effectiveness": round(avg_effectiveness, 1),
            "average_complexity": round(avg_complexity, 1),
            "average_cost": round(avg_cost, 1),
            "tactics_covered": list(set(t['tactic'] for t in comparison_matrix if t['tactic'])),
            "pillars_covered": list(set(t['pillar'] for t in comparison_matrix if t['pillar']))
        }

        # Generate recommendations
        recommendations = []

        if include_recommendations:
            # Sort by effectiveness (descending)
            by_effectiveness = sorted(comparison_matrix, key=lambda x: x['effectiveness_score'], reverse=True)

            # Quick wins: High effectiveness, low complexity, low cost
            quick_wins = [
                t for t in comparison_matrix
                if t['effectiveness_score'] >= 70 and t['complexity_score'] <= 50 and t['cost_score'] <= 50
            ]

            if quick_wins:
                recommendations.append({
                    "category": "Quick Wins",
                    "description": "High effectiveness, low complexity, low cost",
                    "techniques": [{"id": t['source_id'], "name": t['name']} for t in quick_wins[:3]]
                })

            # Strategic investments: High effectiveness, high complexity/cost
            strategic = [
                t for t in comparison_matrix
                if t['effectiveness_score'] >= 70 and (t['complexity_score'] > 70 or t['cost_score'] > 70)
            ]

            if strategic:
                recommendations.append({
                    "category": "Strategic Investments",
                    "description": "High effectiveness, but requires significant resources",
                    "techniques": [{"id": t['source_id'], "name": t['name']} for t in strategic[:3]]
                })

            # Implementation priority: Overall best effectiveness/complexity ratio
            priority_list = sorted(
                comparison_matrix,
                key=lambda x: x['effectiveness_score'] / max(x['complexity_score'], 10),  # Avoid div by zero
                reverse=True
            )

            recommendations.append({
                "category": "Implementation Priority",
                "description": "Ordered by effectiveness-to-complexity ratio",
                "techniques": [{"id": t['source_id'], "name": t['name']} for t in priority_list]
            })

        result = {
            "input_techniques": technique_ids,
            "comparison_matrix": comparison_matrix,
            "summary": summary,
            "recommendations": recommendations if include_recommendations else []
        }

        logger.info(
            f"Technique comparison completed: {len(comparison_matrix)} techniques",
            extra={
                "techniques_compared": len(comparison_matrix),
                "not_found": len(not_found),
                "avg_effectiveness": round(avg_effectiveness, 1)
            }
        )

        return result

    except InputValidationError:
        raise
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        logger.error(
            f"Technique comparison failed: {e}",
            exc_info=True,
            extra={"technique_ids": technique_ids}
        )
        raise Exception(f"Technique comparison failed: {str(e)}")
