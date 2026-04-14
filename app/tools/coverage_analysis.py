"""
Coverage Analysis Tool for AIDEFEND MCP Service

Analyzes defense coverage based on implemented techniques and identifies gaps.
"""

import asyncio
import lancedb
from typing import Dict, Any, List, Optional
from collections import defaultdict

from app.logger import get_logger
from app.config import settings
from app.security import InputValidationError
from app.framework_utils import (
    coverage_lists_from_sets,
    extract_framework_coverage,
    is_actionable_record,
    merge_framework_coverage_sets,
    parse_json_list,
)

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
    return table.search().where(
        "type = 'technique' OR type = 'subtechnique'"
    ).to_pandas().to_dict('records')


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
    from app.core import query_engine
    from app.exceptions import QueryEngineNotInitializedError

    # Input validation (check parameters BEFORE database check)
    # Note: Empty array is allowed for baseline coverage analysis (0% implementation)

    if len(implemented_techniques) > 200:
        raise InputValidationError("Too many techniques (max 200)")

    # Pre-flight check: ensure query engine is ready (AFTER parameter validation)
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please run 'sync_aidefend' first to download the knowledge base."
        )

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

        all_techniques = [tech for tech in all_techniques if is_actionable_record(tech)]

        logger.info(f"Total actionable techniques in KB: {len(all_techniques)}")

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

    # Count total by pillar (parse JSON arrays, count each element)
    for tech in all_techniques:
        pillar_raw = tech.get('pillar', '')
        # Parse JSON array (or handle already-parsed list)
        if isinstance(pillar_raw, str) and pillar_raw.strip():
            pillars = parse_json_list(pillar_raw)
        elif isinstance(pillar_raw, list):
            pillars = pillar_raw
        else:
            pillars = []

        # Count each pillar in the array
        for pillar in pillars:
            if pillar:
                pillar_total[pillar] += 1

    # Count implemented by pillar
    for tech in all_techniques:
        if tech['source_id'] in implemented:
            pillar_raw = tech.get('pillar', '')
            if isinstance(pillar_raw, str) and pillar_raw.strip():
                pillars = parse_json_list(pillar_raw)
            elif isinstance(pillar_raw, list):
                pillars = pillar_raw
            else:
                pillars = []

            for pillar in pillars:
                if pillar:
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

    # Count total by phase (parse JSON arrays, count each element)
    for tech in all_techniques:
        phase_raw = tech.get('phase', '')
        # Parse JSON array (or handle already-parsed list)
        if isinstance(phase_raw, str) and phase_raw.strip():
            phases = parse_json_list(phase_raw)
        elif isinstance(phase_raw, list):
            phases = phase_raw
        else:
            phases = []

        # Count each phase in the array
        for phase in phases:
            if phase:
                phase_total[phase] += 1

    # Count implemented by phase
    for tech in all_techniques:
        if tech['source_id'] in implemented:
            phase_raw = tech.get('phase', '')
            if isinstance(phase_raw, str) and phase_raw.strip():
                phases = parse_json_list(phase_raw)
            elif isinstance(phase_raw, list):
                phases = phase_raw
            else:
                phases = []

            for phase in phases:
                if phase:
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
    covered_sets = merge_framework_coverage_sets()
    total_sets = merge_framework_coverage_sets()

    for tech in all_techniques:
        total_sets = merge_framework_coverage_sets(
            total_sets,
            extract_framework_coverage(parse_json_list(tech.get('defends_against', '[]'))),
        )

    for tech in all_techniques:
        if tech['source_id'] not in implemented:
            continue

        covered_sets = merge_framework_coverage_sets(
            covered_sets,
            extract_framework_coverage(parse_json_list(tech.get('defends_against', '[]'))),
        )

    coverage_rate = {}
    framework_totals = {}
    for key, total in total_sets.items():
        total_count = len(total)
        framework_totals[key] = total_count
        coverage_rate[key] = round(len(covered_sets.get(key, set())) / total_count, 3) if total_count else 0.0

    return {
        "owasp_llm_covered": len(covered_sets["owasp_llm"]),
        "owasp_ml_covered": len(covered_sets["owasp_ml"]),
        "owasp_agentic_covered": len(covered_sets["owasp_agentic"]),
        "mitre_atlas_covered": len(covered_sets["atlas"]),
        "maestro_covered": len(covered_sets["maestro"]),
        "nist_aml_covered": len(covered_sets["nist_aml"]),
        "cisco_covered": len(covered_sets["cisco"]),
        "google_saif_covered": len(covered_sets["google_saif"]),
        "databricks_covered": len(covered_sets["databricks"]),
        "coverage_rate": coverage_rate,
        "framework_totals": framework_totals,
        "coverage_details": {
            key: values[:10]
            for key, values in coverage_lists_from_sets(covered_sets).items()
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
    short_term.append("Improve coverage across the lowest-covered threat frameworks")

    # Long-term
    long_term.append("Achieve 80%+ overall coverage")
    long_term.append("Implement defense-in-depth across all pillars")

    return {
        "immediate": immediate,
        "short_term": short_term,
        "long_term": long_term
    }
