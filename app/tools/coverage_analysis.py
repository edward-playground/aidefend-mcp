"""
Coverage Analysis Tool for AIDEFEND MCP Service

Analyzes defense coverage based on implemented techniques and identifies gaps.
"""

import json
import asyncio
import lancedb
from typing import Dict, Any, List, Optional
from collections import defaultdict

from app.logger import get_logger
from app.config import settings
from app.security import InputValidationError

logger = get_logger(__name__)


def _query_techniques_from_table(table) -> List[Dict[str, Any]]:
    """
    Helper function to query all techniques from LanceDB table.

    This function is used with asyncio.to_thread to avoid lambda expressions.

    Args:
        table: LanceDB table instance

    Returns:
        List of technique records
    """
    return table.search().where("type = 'technique'").to_pandas().to_dict('records')


async def analyze_coverage(
    implemented_techniques: List[str],
    system_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze defense coverage and identify gaps.

    Provides:
    - Coverage percentage by tactic, pillar, phase
    - Threat framework coverage (OWASP, ATLAS, MAESTRO)
    - Critical gaps identification
    - Recommended next techniques to implement

    Args:
        implemented_techniques: List of technique IDs already implemented
        system_type: Optional system type for context-aware analysis
                     (chatbot, rag, agent, classifier, generative, multimodal)

    Returns:
        Dict containing coverage analysis with gaps and recommendations

    Raises:
        InputValidationError: If inputs are invalid
        Exception: If database query fails

    Example:
        >>> result = await analyze_coverage(
        ...     implemented_techniques=["AID-H-001", "AID-D-001", "AID-I-002"],
        ...     system_type="rag"
        ... )
        >>> print(f"Overall coverage: {result['overall_coverage']['percentage']}%")
    """
    import lancedb

    # Input validation
    if not implemented_techniques:
        raise InputValidationError("implemented_techniques cannot be empty")

    if len(implemented_techniques) > 200:
        raise InputValidationError("Too many techniques (max 200)")

    # Normalize IDs
    implemented_techniques = [tid.strip().upper() for tid in implemented_techniques]

    # Remove duplicates
    implemented_techniques = list(set(implemented_techniques))

    logger.info(f"Analyzing coverage for {len(implemented_techniques)} implemented techniques")

    try:
        # Connect to LanceDB
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

        # Get all techniques (not subtechniques or strategies)
        all_techniques = await asyncio.to_thread(
            _query_techniques_from_table, table
        )

        logger.info(f"Total techniques in KB: {len(all_techniques)}")

        # Calculate coverage by tactic
        coverage_by_tactic = _calculate_tactic_coverage(
            implemented_techniques,
            all_techniques
        )

        # Calculate coverage by pillar
        coverage_by_pillar = _calculate_pillar_coverage(
            implemented_techniques,
            all_techniques
        )

        # Calculate coverage by phase
        coverage_by_phase = _calculate_phase_coverage(
            implemented_techniques,
            all_techniques
        )

        # Analyze threat framework coverage
        threat_coverage = _analyze_threat_coverage(
            implemented_techniques,
            all_techniques
        )

        # Identify gaps
        gaps = _identify_gaps(
            implemented_techniques,
            all_techniques,
            coverage_by_tactic,
            system_type
        )

        # Generate recommendations
        recommendations = _generate_recommendations(
            implemented_techniques,
            all_techniques,
            gaps,
            system_type
        )

        # Calculate overall coverage
        total_techniques = len(all_techniques)
        implemented_count = len([t for t in implemented_techniques if any(
            tech['source_id'] == t for tech in all_techniques
        )])

        overall_percentage = round((implemented_count / total_techniques) * 100, 1) if total_techniques > 0 else 0

        # Determine coverage level
        if overall_percentage >= 80:
            coverage_level = "Comprehensive"
        elif overall_percentage >= 50:
            coverage_level = "Moderate"
        elif overall_percentage >= 25:
            coverage_level = "Basic"
        else:
            coverage_level = "Minimal"

        result = {
            "analysis_summary": {
                "total_techniques_available": total_techniques,
                "techniques_implemented": implemented_count,
                "coverage_percentage": overall_percentage,
                "coverage_level": coverage_level,
                "system_type": system_type
            },
            "coverage_by_tactic": coverage_by_tactic,
            "coverage_by_pillar": coverage_by_pillar,
            "coverage_by_phase": coverage_by_phase,
            "threat_framework_coverage": threat_coverage,
            "critical_gaps": gaps,
            "recommendations": recommendations,
            "next_steps": _generate_next_steps(gaps, recommendations)
        }

        logger.info(
            f"Coverage analysis complete: {overall_percentage}% coverage",
            extra={"implemented": implemented_count, "total": total_techniques}
        )

        return result

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to analyze coverage: {e}", exc_info=True)
        raise


def _calculate_tactic_coverage(
    implemented: List[str],
    all_techniques: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """Calculate coverage percentage by tactic."""
    tactic_total = defaultdict(int)
    tactic_implemented = defaultdict(int)

    # Count total by tactic
    for tech in all_techniques:
        tactic = tech.get('tactic', 'Unknown')
        tactic_total[tactic] += 1

    # Count implemented by tactic
    for tech in all_techniques:
        if tech['source_id'] in implemented:
            tactic = tech.get('tactic', 'Unknown')
            tactic_implemented[tactic] += 1

    # Calculate percentages
    coverage = {}
    for tactic in tactic_total:
        total = tactic_total[tactic]
        impl = tactic_implemented.get(tactic, 0)
        percentage = round((impl / total) * 100, 1) if total > 0 else 0

        # Determine status
        if percentage == 0:
            status = "not_covered"
        elif percentage < 25:
            status = "minimal"
        elif percentage < 50:
            status = "partial"
        elif percentage < 80:
            status = "good"
        else:
            status = "comprehensive"

        coverage[tactic] = {
            "implemented": impl,
            "total": total,
            "percentage": percentage,
            "status": status
        }

    return dict(sorted(coverage.items()))


def _calculate_pillar_coverage(
    implemented: List[str],
    all_techniques: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """Calculate coverage by pillar (for subtechniques)."""
    pillar_total = defaultdict(int)
    pillar_implemented = defaultdict(int)

    # Count total by pillar (only count items with non-empty pillar)
    for tech in all_techniques:
        pillar = tech.get('pillar', '').strip()
        if pillar:  # Only count if pillar is defined
            pillar_total[pillar] += 1

    # Count implemented by pillar
    for tech in all_techniques:
        if tech['source_id'] in implemented:
            pillar = tech.get('pillar', '').strip()
            if pillar:  # Only count if pillar is defined
                pillar_implemented[pillar] += 1

    # Calculate percentages
    coverage = {}
    for pillar in pillar_total:
        total = pillar_total[pillar]
        impl = pillar_implemented.get(pillar, 0)
        percentage = round((impl / total) * 100, 1) if total > 0 else 0

        # Determine status
        if percentage == 0:
            status = "not_covered"
        elif percentage < 25:
            status = "minimal"
        elif percentage < 50:
            status = "partial"
        elif percentage < 80:
            status = "good"
        else:
            status = "comprehensive"

        coverage[pillar] = {
            "implemented": impl,
            "total": total,
            "percentage": percentage,
            "status": status
        }

    return dict(sorted(coverage.items()))


def _calculate_phase_coverage(
    implemented: List[str],
    all_techniques: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """Calculate coverage by phase."""
    phase_total = defaultdict(int)
    phase_implemented = defaultdict(int)

    # Count total by phase (only count items with non-empty phase)
    for tech in all_techniques:
        phase = tech.get('phase', '').strip()
        if phase:  # Only count if phase is defined
            phase_total[phase] += 1

    # Count implemented by phase
    for tech in all_techniques:
        if tech['source_id'] in implemented:
            phase = tech.get('phase', '').strip()
            if phase:  # Only count if phase is defined
                phase_implemented[phase] += 1

    # Calculate percentages
    coverage = {}
    for phase in phase_total:
        total = phase_total[phase]
        impl = phase_implemented.get(phase, 0)
        percentage = round((impl / total) * 100, 1) if total > 0 else 0

        # Determine status
        if percentage == 0:
            status = "not_covered"
        elif percentage < 25:
            status = "minimal"
        elif percentage < 50:
            status = "partial"
        elif percentage < 80:
            status = "good"
        else:
            status = "comprehensive"

        coverage[phase] = {
            "implemented": impl,
            "total": total,
            "percentage": percentage,
            "status": status
        }

    return dict(sorted(coverage.items()))


def _analyze_threat_coverage(
    implemented: List[str],
    all_techniques: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Analyze threat framework coverage."""
    owasp_covered = set()
    atlas_covered = set()
    maestro_covered = set()

    for tech in all_techniques:
        if tech['source_id'] not in implemented:
            continue

        defends_against_str = tech.get('defends_against', '[]')
        try:
            defends_against = json.loads(defends_against_str) if isinstance(defends_against_str, str) else defends_against_str

            for framework_data in defends_against:
                framework_name = framework_data.get('framework', '')
                items = framework_data.get('items', [])

                if 'OWASP' in framework_name:
                    owasp_covered.update(items)
                elif 'ATLAS' in framework_name or 'MITRE' in framework_name:
                    atlas_covered.update(items)
                elif 'MAESTRO' in framework_name:
                    maestro_covered.update(items)

        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "owasp_llm_covered": len(owasp_covered),
        "mitre_atlas_covered": len(atlas_covered),
        "maestro_covered": len(maestro_covered),
        "coverage_details": {
            "owasp_items": sorted(list(owasp_covered))[:10],  # Top 10
            "atlas_items": sorted(list(atlas_covered))[:10],
            "maestro_items": sorted(list(maestro_covered))[:10]
        }
    }


def _identify_gaps(
    implemented: List[str],
    all_techniques: List[Dict[str, Any]],
    tactic_coverage: Dict[str, Dict[str, Any]],
    system_type: Optional[str]
) -> List[Dict[str, Any]]:
    """Identify critical coverage gaps."""
    gaps = []

    # Tactic gaps (no coverage)
    for tactic, data in tactic_coverage.items():
        if data['implemented'] == 0:
            gaps.append({
                "gap_type": "tactic",
                "tactic": tactic,
                "severity": "HIGH",
                "reason": f"No {tactic} techniques implemented",
                "risk": f"Complete lack of {tactic} capability"
            })

    return gaps


def _generate_recommendations(
    implemented: List[str],
    all_techniques: List[Dict[str, Any]],
    gaps: List[Dict[str, Any]],
    system_type: Optional[str]
) -> List[Dict[str, Any]]:
    """Generate technique recommendations."""
    recommendations = []

    # Recommend techniques for gaps
    for gap in gaps[:5]:  # Top 5 gaps
        if gap['gap_type'] == 'tactic':
            tactic = gap['tactic']

            # Find techniques in this tactic
            tactic_techniques = [
                t for t in all_techniques
                if t.get('tactic') == tactic and t['source_id'] not in implemented
            ]

            if tactic_techniques:
                # Recommend first one
                tech = tactic_techniques[0]
                recommendations.append({
                    "rank": len(recommendations) + 1,
                    "technique_id": tech['source_id'],
                    "name": tech['name'],
                    "tactic": tech['tactic'],
                    "priority": "HIGH",
                    "reason": f"Fills {tactic} tactic gap",
                    "impact": "High - Establishes defensive capability"
                })

    return recommendations[:10]  # Top 10


def _generate_next_steps(
    gaps: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]]
) -> Dict[str, List[str]]:
    """Generate actionable next steps."""
    immediate = []
    short_term = []
    long_term = []

    # Immediate: Address critical gaps
    for rec in recommendations[:3]:
        immediate.append(
            f"Implement {rec['technique_id']} ({rec['name']}) - {rec['reason']}"
        )

    # Short-term: Fill remaining gaps
    short_term.append("Achieve 50%+ coverage in all tactics")
    short_term.append("Cover top 5 OWASP LLM threats")

    # Long-term
    long_term.append("Achieve 80%+ overall coverage")
    long_term.append("Implement defense-in-depth across all pillars")

    return {
        "immediate": immediate,
        "short_term": short_term,
        "long_term": long_term
    }
