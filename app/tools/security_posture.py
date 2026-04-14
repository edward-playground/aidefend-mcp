"""
Security Posture Analysis Tool for AIDEFEND MCP Service

Comprehensive security posture analysis combining:
1. Technical coverage (tactics/pillars/phases)
2. Threat framework coverage across all mapped external frameworks
3. Gap analysis and recommendations

This tool merges functionality from analyze_coverage and get_threat_coverage
into a unified interface for holistic security assessment.
"""

from typing import Dict, Any, List, Optional

from app.logger import get_logger
from app.security import InputValidationError
from app.framework_utils import FRAMEWORK_LABELS
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
    - Threat view: Coverage across all mapped threat frameworks
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
        >>> print(result['threat_coverage']['coverage_rate'])
    """
    # Input validation
    if not isinstance(implemented_techniques, list):
        raise InputValidationError("implemented_techniques must be a list")

    # Allow empty array for baseline analysis (0% coverage, all gaps)
    # This enables users to generate initial security plans without any existing implementations

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
    # analyze_coverage returns analysis_summary.coverage_percentage (0-100)
    tech_coverage_pct = technical_cov.get("analysis_summary", {}).get("coverage_percentage", 0)
    # get_threat_coverage returns coverage_rate as fractions (0.0-1.0), convert to percentage
    framework_percentages = {
        key: threat_cov.get("coverage_rate", {}).get(key, 0) * 100
        for key in FRAMEWORK_LABELS
    }

    # Determine overall posture
    avg_coverage = (
        tech_coverage_pct
        + sum(framework_percentages.values())
    ) / (len(framework_percentages) + 1)

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
    for key, label in FRAMEWORK_LABELS.items():
        summary["key_insights"].append(
            f"{label}: {framework_percentages[key]:.1f}% threat coverage"
        )

    # Identify top priorities from technical gaps and recommendations
    # Note: critical_gaps contains gap analysis (tactic/pillar/phase gaps)
    # recommendations contains specific technique suggestions with IDs
    critical_gaps = technical_cov.get("critical_gaps", [])
    recommendations = technical_cov.get("recommendations", [])

    if critical_gaps:
        # Add gap descriptions (gaps have 'reason' not 'technique_id')
        for gap in critical_gaps[:3]:
            gap_desc = gap.get('reason', gap.get('tactic', 'Unknown gap'))
            summary["top_priorities"].append(f"Gap: {gap_desc}")

    # Add specific technique recommendations
    if recommendations:
        summary["top_priorities"].extend([
            f"{rec['technique_id']}: {rec['name']}"
            for rec in recommendations[:5]
        ])

    low_coverage_frameworks = [
        (FRAMEWORK_LABELS[key], pct)
        for key, pct in framework_percentages.items()
        if pct < 50
    ]
    low_coverage_frameworks.sort(key=lambda item: item[1])
    for label, pct in low_coverage_frameworks[:3]:
        summary["top_priorities"].append(
            f"Increase {label} coverage ({pct:.1f}%)"
        )

    # Identify uncovered OWASP threats from threat coverage data
    # get_threat_coverage returns "covered" dict, compute uncovered from known OWASP list
    covered_owasp = threat_cov.get("covered", {}).get("owasp_llm", [])
    all_owasp = ["LLM01", "LLM02", "LLM03", "LLM04", "LLM05",
                 "LLM06", "LLM07", "LLM08", "LLM09", "LLM10"]
    uncovered_owasp = [t for t in all_owasp if t not in covered_owasp]
    if uncovered_owasp:
        summary["top_priorities"].append(
            f"OWASP threats not covered: {', '.join(uncovered_owasp[:3])}"
        )

    return summary
