"""
Security Posture Analysis Tool for AIDEFEND MCP Service

Comprehensive security posture analysis combining:
1. Technical coverage (tactics/pillars/phases)
2. Threat framework coverage (OWASP/ATLAS/MAESTRO)
3. Gap analysis and recommendations

This tool merges functionality from analyze_coverage and get_threat_coverage
into a unified interface for holistic security assessment.
"""

from typing import Dict, Any, List, Optional

from app.logger import get_logger
from app.security import InputValidationError
from app.tools.coverage_analysis import analyze_coverage
from app.tools.threat_coverage import get_threat_coverage

logger = get_logger(__name__)


async def analyze_security_posture(
    implemented_techniques: List[str],
    view: str = "both",
    system_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Comprehensive security posture analysis.

    Provides unified view of security coverage from both technical and threat perspectives:
    - Technical view: Coverage by tactic/pillar/phase, gap analysis, recommendations
    - Threat view: Coverage of OWASP LLM Top 10, MITRE ATLAS, MAESTRO frameworks
    - Both views: Combined analysis (default)

    Args:
        implemented_techniques: List of technique IDs already implemented
                               (e.g., ["AID-D-001", "AID-H-002"])
        view: Analysis view to return:
              - "both" (default): Technical + Threat coverage
              - "technical": Only tactic/pillar/phase coverage
              - "threat": Only threat framework coverage
        system_type: Optional system type for context-aware analysis
                     (chatbot, rag, agent, classifier, generative, multimodal)

    Returns:
        Dict containing:
        - view: Which view was requested
        - implemented_count: Number of techniques analyzed
        - technical_coverage: (if view="both" or "technical")
            - overall_coverage: Percentage and counts
            - by_tactic: Coverage breakdown by tactic
            - by_pillar: Coverage breakdown by pillar
            - by_phase: Coverage breakdown by phase
            - critical_gaps: High-priority missing techniques
            - recommendations: Suggested next techniques
        - threat_coverage: (if view="both" or "threat")
            - covered_threats: Dict of {framework -> [threat_ids]}
            - coverage_rate: Dict of {framework -> percentage}
            - by_technique: Detailed mapping per technique
            - uncovered_threats: Threats not yet addressed
        - summary: High-level summary combining both views

    Raises:
        InputValidationError: If inputs are invalid
        Exception: If database query fails

    Example:
        >>> result = await analyze_security_posture(
        ...     implemented_techniques=["AID-H-001", "AID-D-001"],
        ...     view="both",
        ...     system_type="rag"
        ... )
        >>> print(f"Overall coverage: {result['technical_coverage']['overall_coverage']['percentage']}%")
        >>> print(f"OWASP threats covered: {result['threat_coverage']['covered_threats']['owasp']}")
    """
    # Input validation
    if not implemented_techniques:
        raise InputValidationError("implemented_techniques cannot be empty")

    if not isinstance(implemented_techniques, list):
        raise InputValidationError("implemented_techniques must be a list")

    if view not in ["both", "technical", "threat"]:
        raise InputValidationError(
            f"Invalid view '{view}'. Must be one of: both, technical, threat"
        )

    # Normalize and deduplicate
    implemented_techniques = list(set([tid.strip().upper() for tid in implemented_techniques]))

    logger.info(
        f"Analyzing security posture for {len(implemented_techniques)} techniques (view={view})",
        extra={"count": len(implemented_techniques), "view": view, "system_type": system_type}
    )

    result = {
        "view": view,
        "implemented_count": len(implemented_techniques),
        "system_type": system_type
    }

    try:
        # Execute analysis based on requested view
        if view in ["both", "technical"]:
            logger.debug("Running technical coverage analysis...")
            technical_result = await analyze_coverage(
                implemented_techniques=implemented_techniques,
                system_type=system_type
            )
            result["technical_coverage"] = technical_result

        if view in ["both", "threat"]:
            logger.debug("Running threat coverage analysis...")
            threat_result = await get_threat_coverage(
                implemented_techniques=implemented_techniques
            )
            result["threat_coverage"] = threat_result

        # Generate unified summary
        if view == "both":
            result["summary"] = _generate_unified_summary(
                result.get("technical_coverage"),
                result.get("threat_coverage"),
                len(implemented_techniques)
            )

        logger.info(
            f"Security posture analysis completed for {len(implemented_techniques)} techniques",
            extra={"view": view, "techniques_count": len(implemented_techniques)}
        )

        return result

    except InputValidationError:
        raise
    except Exception as e:
        logger.error(
            f"Security posture analysis failed: {e}",
            exc_info=True,
            extra={"view": view, "techniques_count": len(implemented_techniques)}
        )
        raise Exception(f"Security posture analysis failed: {str(e)}")


def _generate_unified_summary(
    technical_cov: Optional[Dict[str, Any]],
    threat_cov: Optional[Dict[str, Any]],
    technique_count: int
) -> Dict[str, Any]:
    """
    Generate unified summary combining technical and threat perspectives.

    Args:
        technical_cov: Results from analyze_coverage
        threat_cov: Results from get_threat_coverage
        technique_count: Number of techniques analyzed

    Returns:
        Dict containing unified summary with key insights
    """
    summary = {
        "techniques_implemented": technique_count,
        "overall_posture": "unknown",
        "key_insights": [],
        "top_priorities": []
    }

    if not technical_cov or not threat_cov:
        return summary

    # Extract key metrics
    tech_coverage_pct = technical_cov.get("overall_coverage", {}).get("percentage", 0)
    owasp_cov_pct = threat_cov.get("coverage_rate", {}).get("owasp", 0)
    atlas_cov_pct = threat_cov.get("coverage_rate", {}).get("atlas", 0)
    maestro_cov_pct = threat_cov.get("coverage_rate", {}).get("maestro", 0)

    # Determine overall posture
    avg_coverage = (tech_coverage_pct + owasp_cov_pct + atlas_cov_pct + maestro_cov_pct) / 4

    if avg_coverage >= 80:
        summary["overall_posture"] = "strong"
    elif avg_coverage >= 60:
        summary["overall_posture"] = "moderate"
    elif avg_coverage >= 40:
        summary["overall_posture"] = "developing"
    else:
        summary["overall_posture"] = "early"

    # Generate insights
    summary["key_insights"].append(
        f"Technical coverage: {tech_coverage_pct:.1f}% of AIDEFEND techniques"
    )
    summary["key_insights"].append(
        f"OWASP LLM Top 10: {owasp_cov_pct:.1f}% threat coverage"
    )
    summary["key_insights"].append(
        f"MITRE ATLAS: {atlas_cov_pct:.1f}% threat coverage"
    )
    summary["key_insights"].append(
        f"MAESTRO: {maestro_cov_pct:.1f}% threat coverage"
    )

    # Identify top priorities from technical gaps
    critical_gaps = technical_cov.get("critical_gaps", [])
    if critical_gaps:
        summary["top_priorities"].extend([
            f"{gap['technique_id']}: {gap['name']}"
            for gap in critical_gaps[:3]
        ])

    # Identify uncovered high-priority threats
    uncovered = threat_cov.get("uncovered_threats", {})
    if uncovered.get("owasp"):
        summary["top_priorities"].append(
            f"OWASP threats not covered: {', '.join(uncovered['owasp'][:3])}"
        )

    return summary
