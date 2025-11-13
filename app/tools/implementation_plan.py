"""
Implementation Plan Tool for AIDEFEND MCP Service

Recommends next defense techniques to implement based on heuristic scoring.
Uses existing database fields only - NO LLM inference.

Scoring dimensions:
1. Threat importance (defends_against contains high-risk threats)
2. Ease of implementation (tools_opensource availability)
3. Phase weight (earlier phases = lower cost)
4. Pillar weight (prevention > detection > response)
5. Tool ecosystem maturity (tools_commercial availability)
"""

import json
import asyncio
import lancedb
from typing import Dict, Any, List, Set, Optional
from collections import defaultdict

from app.logger import get_logger
from app.config import settings
from app.security import InputValidationError

logger = get_logger(__name__)

# High-risk threat patterns (for threat importance scoring)
HIGH_RISK_PATTERNS = [
    'LLM01', 'LLM03',  # Prompt injection, Training data poisoning
    'POISON', 'EXFIL',  # Poisoning, Exfiltration
    'T0020', 'T0043',   # ATLAS poisoning, adversarial examples
    'BACKDOOR', 'JAILBREAK'
]


async def get_implementation_plan(
    implemented_techniques: Optional[List[str]] = None,
    exclude_tactics: Optional[List[str]] = None,
    top_k: int = 10
) -> Dict[str, Any]:
    """
    Recommend next techniques to implement based on heuristic scoring.

    This function uses ONLY existing database fields for scoring:
    - defends_against: High-risk threat coverage
    - tools_opensource/tools_commercial: Implementation ease
    - phase: Development stage (Design = easier than Runtime)
    - pillar: Defense layer (Prevent > Detect > Respond)

    NO LLM inference is used. All scoring is heuristic.

    Args:
        implemented_techniques: List of already implemented technique IDs
        exclude_tactics: List of tactics to exclude (e.g., ["Model", "Harden"])
        top_k: Number of recommendations to return (1-20)

    Returns:
        Dict containing:
        - input: Summary of input parameters
        - recommendations: List of recommended techniques with scores
        - categories: Bucketed recommendations (quick_wins, high_priority, standard)

    Raises:
        InputValidationError: If input validation fails
        Exception: If database query fails

    Example:
        >>> result = await get_implementation_plan(
        ...     implemented_techniques=["AID-D-001"],
        ...     top_k=10
        ... )
        >>> print(result['recommendations'][0]['technique_id'])
        'AID-D-014'
    """
    # Input validation
    if implemented_techniques is None:
        implemented_techniques = []

    if exclude_tactics is None:
        exclude_tactics = []

    if not isinstance(implemented_techniques, list):
        raise InputValidationError("implemented_techniques must be a list")

    if not isinstance(exclude_tactics, list):
        raise InputValidationError("exclude_tactics must be a list")

    if top_k < 1 or top_k > 20:
        raise InputValidationError("top_k must be between 1 and 20")

    # Normalize inputs
    implemented_set = set(tid.strip().upper() for tid in implemented_techniques)
    exclude_tactics_set = set(tactic.strip().title() for tactic in exclude_tactics)

    logger.info(
        f"Generating implementation plan: "
        f"{len(implemented_set)} implemented, "
        f"{len(exclude_tactics_set)} tactics excluded, "
        f"top_k={top_k}"
    )

    try:
        # Connect to LanceDB
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

        # Get all techniques (excluding subtechniques and strategies)
        all_techniques = await asyncio.to_thread(
            lambda: table.search().where("type = 'technique'").to_pandas().to_dict('records')
        )

        logger.info(f"Retrieved {len(all_techniques)} total techniques")

        # Filter: exclude already implemented and excluded tactics
        candidate_techniques = []
        for tech in all_techniques:
            tech_id = tech.get('source_id', '')
            tactic = tech.get('tactic', '')

            # Skip if already implemented
            if tech_id in implemented_set:
                continue

            # Skip if tactic is excluded
            if tactic in exclude_tactics_set:
                continue

            candidate_techniques.append(tech)

        logger.info(f"Filtered to {len(candidate_techniques)} candidate techniques")

        # Score each candidate technique
        scored_techniques = []
        for tech in candidate_techniques:
            score, breakdown = _calculate_recommendation_score(tech)

            scored_techniques.append({
                "technique": tech,
                "score": score,
                "score_breakdown": breakdown
            })

        # Sort by score (descending)
        scored_techniques.sort(key=lambda x: x["score"], reverse=True)

        # Take top_k
        top_recommendations = scored_techniques[:top_k]

        # Build recommendations list
        recommendations = []
        for i, item in enumerate(top_recommendations, 1):
            tech = item["technique"]
            score = item["score"]
            breakdown = item["score_breakdown"]

            # Generate reasoning text
            reasoning = _generate_reasoning(tech, breakdown)

            # Check if has opensource tools
            tools_opensource = json.loads(tech.get('tools_opensource', '[]'))
            has_opensource_tools = bool(tools_opensource)

            recommendations.append({
                "rank": i,
                "technique_id": tech.get('source_id'),
                "technique_name": tech.get('name'),
                "tactic": tech.get('tactic'),
                "score": round(score, 2),
                "score_breakdown": breakdown,
                "reasoning": reasoning,
                "has_opensource_tools": has_opensource_tools,
                "pillar": tech.get('pillar', ''),
                "phase": tech.get('phase', '')
            })

        # Categorize recommendations
        categories = _categorize_recommendations(scored_techniques[:top_k])

        result = {
            "input": {
                "implemented_count": len(implemented_set),
                "exclude_tactics": list(exclude_tactics_set),
                "top_k": top_k
            },
            "recommendations": recommendations,
            "categories": categories
        }

        logger.info(
            f"Implementation plan generated: {len(recommendations)} recommendations, "
            f"{len(categories['quick_wins'])} quick wins, "
            f"{len(categories['high_priority'])} high priority"
        )

        return result

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to generate implementation plan: {e}", exc_info=True)
        raise


def _calculate_recommendation_score(technique: Dict) -> tuple[float, Dict[str, float]]:
    """
    Calculate heuristic recommendation score (0-10) using only existing fields.

    Scoring dimensions (total 10 points):
    1. Threat importance (3 points): High-risk threats in defends_against
    2. Ease of implementation (2 points): tools_opensource availability
    3. Phase weight (2 points): Design > Development > Deployment > Runtime
    4. Pillar weight (2 points): Prevent > Detect > Respond
    5. Tool ecosystem (1 point): tools_commercial availability

    Args:
        technique: Technique dict from database

    Returns:
        Tuple of (total_score, breakdown_dict)
    """
    score = 0.0
    breakdown = {}

    # 1. Threat importance (0-3 points)
    defends_against = json.loads(technique.get('defends_against', '[]'))
    threat_score = 0.0

    for framework_data in defends_against:
        for item in framework_data.get('items', []):
            item_upper = item.upper()
            if any(pattern in item_upper for pattern in HIGH_RISK_PATTERNS):
                threat_score = 3.0
                break
        if threat_score > 0:
            break

    score += threat_score
    breakdown["threat_importance"] = threat_score

    # 2. Ease of implementation (0-2 points)
    tools_opensource = json.loads(technique.get('tools_opensource', '[]'))
    ease_score = 2.0 if tools_opensource else 0.0

    score += ease_score
    breakdown["ease_of_implementation"] = ease_score

    # 3. Phase weight (0-2 points)
    phase = technique.get('phase', '')
    phase_scores = {
        'Design': 2.0,
        'Development': 1.5,
        'Deployment': 1.0,
        'Runtime': 0.5
    }
    phase_score = phase_scores.get(phase, 0.0)

    score += phase_score
    breakdown["phase_weight"] = phase_score

    # 4. Pillar weight (0-2 points)
    pillar = technique.get('pillar', '')
    pillar_scores = {
        'Prevent': 2.0,
        'Detect': 1.5,
        'Respond': 1.0
    }
    pillar_score = pillar_scores.get(pillar, 0.0)

    score += pillar_score
    breakdown["pillar_weight"] = pillar_score

    # 5. Tool ecosystem maturity (0-1 point)
    tools_commercial = json.loads(technique.get('tools_commercial', '[]'))
    ecosystem_score = 1.0 if tools_commercial else 0.0

    score += ecosystem_score
    breakdown["tool_ecosystem"] = ecosystem_score

    return (score, breakdown)


def _generate_reasoning(technique: Dict, breakdown: Dict[str, float]) -> str:
    """
    Generate human-readable reasoning for recommendation.

    Args:
        technique: Technique dict
        breakdown: Score breakdown dict

    Returns:
        Reasoning text
    """
    reasons = []

    # Threat importance
    if breakdown.get("threat_importance", 0) >= 3.0:
        reasons.append("Covers high-risk threats")

    # Ease of implementation
    if breakdown.get("ease_of_implementation", 0) >= 2.0:
        reasons.append("Has open-source tools available")

    # Pillar
    pillar = technique.get('pillar', '')
    if pillar == 'Prevent':
        reasons.append("Prevention is most cost-effective")
    elif pillar == 'Detect':
        reasons.append("Detection adds defense-in-depth")

    # Phase
    phase = technique.get('phase', '')
    if phase in ['Design', 'Development']:
        reasons.append(f"Early-stage implementation ({phase})")

    if not reasons:
        reasons.append("Standard priority technique")

    return "; ".join(reasons)


def _categorize_recommendations(scored_techniques: List[Dict]) -> Dict[str, List[str]]:
    """
    Categorize recommendations into quick_wins, high_priority, standard.

    Categories:
    - quick_wins: Has opensource tools AND score >= 6.0
    - high_priority: Score >= 7.0 (regardless of tools)
    - standard: Everything else

    Args:
        scored_techniques: List of scored technique dicts

    Returns:
        Dict with {category -> [technique_ids]}
    """
    quick_wins = []
    high_priority = []
    standard = []

    for item in scored_techniques:
        tech = item["technique"]
        score = item["score"]
        tech_id = tech.get('source_id')

        tools_opensource = json.loads(tech.get('tools_opensource', '[]'))
        has_tools = bool(tools_opensource)

        # Categorize
        if has_tools and score >= 6.0:
            quick_wins.append(tech_id)

        if score >= 7.0:
            high_priority.append(tech_id)
        else:
            standard.append(tech_id)

    return {
        "quick_wins": quick_wins,
        "high_priority": high_priority,
        "standard": standard
    }
