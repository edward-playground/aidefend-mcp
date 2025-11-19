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
from app.security import InputValidationError
from app.core import query_engine
from app.exceptions import QueryEngineNotInitializedError

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


def _calculate_effectiveness_score(technique_doc: Dict[str, Any]) -> int:
    """
    Calculate effectiveness score based on threat coverage and implementation support.

    Scoring algorithm (0-100):
    - Base: 50 points
    - +10 for each OWASP threat defended
    - +5 for each ATLAS threat defended
    - +5 for each MAESTRO threat defended
    - +10 if has implementation strategies
    - +10 if has code snippets

    Args:
        technique_doc: Technique document from LanceDB

    Returns:
        Effectiveness score (0-100)
    """
    score = 50  # Base score

    # Parse defends_against field
    defends_against = _parse_json_field(technique_doc.get('defends_against', '[]'))

    # Count threats by framework
    owasp_count = 0
    atlas_count = 0
    maestro_count = 0

    if isinstance(defends_against, list):
        for defense_item in defends_against:
            if isinstance(defense_item, dict):
                framework = defense_item.get('framework', '').lower()
                items = defense_item.get('items', [])

                if 'owasp' in framework:
                    owasp_count += len(items) if isinstance(items, list) else 0
                elif 'atlas' in framework:
                    atlas_count += len(items) if isinstance(items, list) else 0
                elif 'maestro' in framework:
                    maestro_count += len(items) if isinstance(items, list) else 0

    # Add points based on threat coverage
    score += min(owasp_count * 10, 30)  # Max 30 points from OWASP
    score += min(atlas_count * 5, 15)   # Max 15 points from ATLAS
    score += min(maestro_count * 5, 15) # Max 15 points from MAESTRO

    # Check for implementation strategies
    impl_strategies = _parse_json_field(technique_doc.get('implementation_strategies', '[]'))
    if impl_strategies and len(impl_strategies) > 0:
        score += 10

    # Check for code snippets
    has_code_snippets = technique_doc.get('has_code_snippets', False)
    if has_code_snippets:
        score += 10

    # Normalize to 0-100
    return min(score, 100)


def _calculate_complexity_score(technique_doc: Dict[str, Any]) -> int:
    """
    Calculate complexity score based on implementation requirements.

    Scoring algorithm (0-100):
    - Base: 30 points (low complexity)
    - +20 if has sub-techniques (indicates depth)
    - +15 if pillar = "infrastructure" (harder than app/model)
    - +10 if phase = "building" (design-time harder)
    - +5 per implementation strategy (more options = more complex)

    Args:
        technique_doc: Technique document from LanceDB

    Returns:
        Complexity score (0-100, higher = more complex)
    """
    score = 30  # Base score (low complexity)

    # Check for sub-techniques
    source_id = technique_doc.get('source_id', '')
    technique_type = technique_doc.get('type', '')

    # If this is a parent technique (not a subtechnique), it likely has subtechniques
    if technique_type == 'technique' and '.' not in source_id:
        score += 20

    # Pillar complexity
    pillar = technique_doc.get('pillar', '').lower()
    if 'infrastructure' in pillar:
        score += 15
    elif 'model' in pillar:
        score += 5

    # Phase complexity
    phase = technique_doc.get('phase', '').lower()
    if 'building' in phase:
        score += 10
    elif 'deployment' in phase:
        score += 5

    # Implementation strategies count
    impl_strategies = _parse_json_field(technique_doc.get('implementation_strategies', '[]'))
    if impl_strategies:
        strategy_count = len(impl_strategies) if isinstance(impl_strategies, list) else 0
        score += min(strategy_count * 5, 25)  # Max 25 points from strategies

    # Normalize to 0-100
    return min(score, 100)


def _calculate_cost_score(technique_doc: Dict[str, Any]) -> int:
    """
    Calculate cost score based on tooling and implementation requirements.

    Scoring algorithm (0-100):
    - Base: 40 points (medium cost)
    - +20 if requires commercial tools
    - +10 if phase = "building" (upfront investment)
    - +15 if pillar = "infrastructure" (expensive)
    - -10 if has opensource tools only

    Args:
        technique_doc: Technique document from LanceDB

    Returns:
        Cost score (0-100, higher = more expensive)
    """
    score = 40  # Base score (medium cost)

    # Check for commercial tools
    commercial_tools = _parse_json_field(technique_doc.get('tools_commercial', '[]'))
    if commercial_tools and len(commercial_tools) > 0:
        score += 20

    # Check for opensource tools
    opensource_tools = _parse_json_field(technique_doc.get('tools_opensource', '[]'))
    if opensource_tools and len(opensource_tools) > 0 and not commercial_tools:
        score -= 10  # Opensource only = lower cost

    # Phase cost
    phase = technique_doc.get('phase', '').lower()
    if 'building' in phase:
        score += 10  # Upfront design investment

    # Pillar cost
    pillar = technique_doc.get('pillar', '').lower()
    if 'infrastructure' in pillar:
        score += 15  # Infrastructure is expensive
    elif 'model' in pillar:
        score += 5

    # Normalize to 0-100
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
    impl_strategies = _parse_json_field(technique_doc.get('implementation_strategies', '[]'))
    opensource_tools = _parse_json_field(technique_doc.get('tools_opensource', '[]'))
    commercial_tools = _parse_json_field(technique_doc.get('tools_commercial', '[]'))

    # Count threats by framework
    threat_summary = {"owasp": 0, "atlas": 0, "maestro": 0}

    if isinstance(defends_against, list):
        for defense_item in defends_against:
            if isinstance(defense_item, dict):
                framework = defense_item.get('framework', '').lower()
                items = defense_item.get('items', [])
                item_count = len(items) if isinstance(items, list) else 0

                if 'owasp' in framework:
                    threat_summary['owasp'] += item_count
                elif 'atlas' in framework:
                    threat_summary['atlas'] += item_count
                elif 'maestro' in framework:
                    threat_summary['maestro'] += item_count

    return {
        "source_id": technique_doc.get('source_id', ''),
        "name": technique_doc.get('name', ''),
        "tactic": technique_doc.get('tactic', ''),
        "pillar": technique_doc.get('pillar', ''),
        "phase": technique_doc.get('phase', ''),
        "type": technique_doc.get('type', ''),
        "description": technique_doc.get('text', '')[:200] + "..." if len(technique_doc.get('text', '')) > 200 else technique_doc.get('text', ''),
        "threat_coverage": threat_summary,
        "has_implementation_strategies": len(impl_strategies) > 0 if isinstance(impl_strategies, list) else False,
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

            docs = await asyncio.to_thread(
                lambda tid=technique_id: table.search()
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
