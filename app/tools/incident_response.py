"""
Incident Response Playbook Generator for AIDEFEND MCP Service

Generates structured incident response playbooks based on threat classification.
Provides timeline-based action plans following industry-standard NIST phases.

100% local implementation - integrates with existing classify_threat and
get_defenses_for_threat tools.
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.logger import get_logger
from app.security import InputValidationError, validate_query_text
from app.core import query_engine
from app.exceptions import QueryEngineNotInitializedError
from app.framework_utils import FRAMEWORK_LABELS
from app.tools.classify_threat import classify_threat
from app.tools.defenses_for_threat import get_defenses_for_threat

logger = get_logger(__name__)


def _framework_label_from_threat_id(threat_id: str) -> str:
    """Convert prefixed threat detail IDs into human-friendly framework labels."""
    prefix = threat_id.split("-", 1)[0].lower()
    legacy_labels = {
        "owasp": "OWASP",
        "atlas": "MITRE ATLAS",
        "maestro": "MAESTRO",
    }
    return legacy_labels.get(prefix, FRAMEWORK_LABELS.get(prefix, prefix.upper()))


def _generate_immediate_actions(
    incident_description: str,
    threat_classification: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Generate immediate actions (0-15 minutes).

    Args:
        incident_description: Description of the incident
        threat_classification: Results from classify_threat_simple

    Returns:
        List of immediate action items
    """
    actions = [
        {
            "action": "Activate Incident Response Team",
            "priority": "CRITICAL",
            "description": "Notify designated IR team members and establish communication channel",
            "estimated_time": "2-5 minutes"
        },
        {
            "action": "Assess Initial Severity",
            "priority": "CRITICAL",
            "description": "Determine severity level (Low/Medium/High/Critical) based on initial observations",
            "estimated_time": "5-10 minutes"
        },
        {
            "action": "Preserve Evidence",
            "priority": "HIGH",
            "description": "Capture logs, screenshots, system state before any modifications. Document timeline.",
            "estimated_time": "5-10 minutes"
        }
    ]

    # Add threat-specific immediate actions
    if threat_classification and threat_classification.get('threat_details'):
        threat_details = threat_classification['threat_details']

        # Check for specific high-risk threats
        threat_keywords = ' '.join([t.get('matched_keyword', '') for t in threat_details]).lower()

        if 'prompt injection' in threat_keywords or 'jailbreak' in threat_keywords:
            actions.append({
                "action": "Isolate Affected LLM Endpoints",
                "priority": "CRITICAL",
                "description": "Temporarily disable or rate-limit affected LLM API endpoints to prevent exploitation",
                "estimated_time": "5 minutes"
            })

        if 'data poisoning' in threat_keywords or 'training' in threat_keywords:
            actions.append({
                "action": "Halt Training Pipelines",
                "priority": "CRITICAL",
                "description": "Immediately stop any active model training to prevent poisoned data propagation",
                "estimated_time": "2-5 minutes"
            })

        if 'denial of service' in threat_keywords or 'resource' in threat_keywords:
            actions.append({
                "action": "Implement Rate Limiting",
                "priority": "HIGH",
                "description": "Apply emergency rate limits and resource quotas to mitigate service degradation",
                "estimated_time": "5-10 minutes"
            })

    return actions


def _generate_investigation_actions(
    incident_description: str,
    threat_classification: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Generate investigation actions (15 minutes - 2 hours).

    Args:
        incident_description: Description of the incident
        threat_classification: Results from classify_threat_simple

    Returns:
        List of investigation action items
    """
    actions = [
        {
            "action": "Perform Threat Classification",
            "priority": "HIGH",
            "description": "Map incident to OWASP LLM Top 10, MITRE ATLAS, or MAESTRO frameworks",
            "estimated_time": "10-15 minutes",
            "tools": ["classify_threat tool"]
        },
        {
            "action": "Collect Indicators of Compromise (IOCs)",
            "priority": "HIGH",
            "description": "Gather IP addresses, user IDs, timestamps, request patterns, model outputs",
            "estimated_time": "20-30 minutes"
        },
        {
            "action": "Scope Analysis",
            "priority": "HIGH",
            "description": "Determine which systems, models, and users are affected. Assess data exposure.",
            "estimated_time": "30-45 minutes"
        },
        {
            "action": "Root Cause Analysis",
            "priority": "MEDIUM",
            "description": "Identify vulnerability or misconfiguration that enabled the incident",
            "estimated_time": "45-90 minutes"
        }
    ]

    # Add threat-specific investigation actions
    if threat_classification and threat_classification.get('threat_details'):
        threat_details = threat_classification['threat_details']
        threat_ids = [t.get('threat_id', '') for t in threat_details]

        grouped_threats: Dict[str, List[str]] = {}
        for threat_id in threat_ids:
            grouped_threats.setdefault(_framework_label_from_threat_id(threat_id), []).append(threat_id)

        for framework_label, matched_ids in grouped_threats.items():
            actions.append({
                "action": f"Review {framework_label} Mapping",
                "priority": "MEDIUM",
                "description": f"Analyze incident against matched threats: {', '.join(matched_ids[:5])}",
                "estimated_time": "15-20 minutes"
            })

    return actions


def _generate_containment_actions(
    incident_description: str,
    threat_classification: Optional[Dict[str, Any]],
    defense_techniques: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Generate containment actions (2-8 hours).

    Args:
        incident_description: Description of the incident
        threat_classification: Results from classify_threat_simple
        defense_techniques: Results from get_defenses_for_threat

    Returns:
        List of containment action items
    """
    actions = [
        {
            "action": "Isolate Affected Systems",
            "priority": "CRITICAL",
            "description": "Network segmentation, API endpoint disabling, user account suspension as needed",
            "estimated_time": "30-60 minutes"
        },
        {
            "action": "Block Attack Vectors",
            "priority": "HIGH",
            "description": "Implement input validation, output filtering, or access controls to prevent continued exploitation",
            "estimated_time": "1-2 hours"
        },
        {
            "action": "Monitor for Persistence",
            "priority": "HIGH",
            "description": "Set up enhanced logging and monitoring to detect if attacker regains access",
            "estimated_time": "45-90 minutes"
        }
    ]

    # Add defense technique recommendations
    # get_defenses_for_threat returns {"defense_techniques": [{technique: {id, name, tactic, ...}, relevance_score}, ...]}
    if defense_techniques and defense_techniques.get('defense_techniques'):
        techniques = defense_techniques['defense_techniques'][:5]  # Top 5 techniques

        for tech_entry in techniques:
            tech = tech_entry.get('technique', {})
            actions.append({
                "action": f"Deploy Defense: {tech.get('name', '')}",
                "priority": "HIGH",
                "description": f"Implement {tech.get('id', '')} - {tech.get('description', '')[:150]}...",
                "estimated_time": "1-3 hours",
                "reference": tech.get('id', '')
            })

    # Add threat-specific containment
    if threat_classification and threat_classification.get('threat_details'):
        threat_keywords = ' '.join([t.get('matched_keyword', '') for t in threat_classification['threat_details']]).lower()

        if 'prompt injection' in threat_keywords:
            actions.append({
                "action": "Implement Prompt Validation",
                "priority": "HIGH",
                "description": "Deploy input sanitization and prompt injection detection mechanisms",
                "estimated_time": "2-4 hours"
            })

        if 'model theft' in threat_keywords or 'extraction' in threat_keywords:
            actions.append({
                "action": "Enhance API Protection",
                "priority": "HIGH",
                "description": "Implement rate limiting, query filtering, and response obfuscation",
                "estimated_time": "2-3 hours"
            })

    return actions


def _generate_recovery_actions(
    incident_description: str,
    threat_classification: Optional[Dict[str, Any]],
    defense_techniques: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Generate recovery and remediation actions (8+ hours).

    Args:
        incident_description: Description of the incident
        threat_classification: Results from classify_threat_simple
        defense_techniques: Results from get_defenses_for_threat

    Returns:
        List of recovery action items
    """
    actions = [
        {
            "action": "Implement Security Controls",
            "priority": "HIGH",
            "description": "Deploy recommended AIDEFEND defense techniques identified during investigation",
            "estimated_time": "4-8 hours",
            "reference": "See defense techniques in containment phase"
        },
        {
            "action": "Restore Services Safely",
            "priority": "MEDIUM",
            "description": "Gradually restore affected services with enhanced monitoring and controls",
            "estimated_time": "2-4 hours"
        },
        {
            "action": "Conduct Post-Incident Review",
            "priority": "MEDIUM",
            "description": "Document lessons learned, update runbooks, identify process improvements",
            "estimated_time": "2-3 hours"
        },
        {
            "action": "Update Security Documentation",
            "priority": "MEDIUM",
            "description": "Update threat models, security policies, and incident response procedures",
            "estimated_time": "2-4 hours"
        },
        {
            "action": "Communicate with Stakeholders",
            "priority": "MEDIUM",
            "description": "Brief leadership, affected users, and relevant parties on incident and remediation",
            "estimated_time": "1-2 hours"
        }
    ]

    # Add long-term preventive measures
    if defense_techniques and defense_techniques.get('defense_techniques'):
        technique_count = len(defense_techniques['defense_techniques'])

        actions.append({
            "action": "Implement Defense-in-Depth",
            "priority": "HIGH",
            "description": f"Deploy all {technique_count} recommended defense techniques across security lifecycle",
            "estimated_time": "1-2 weeks",
            "reference": "Use get_defenses_for_threat tool for complete list"
        })

    return actions


async def generate_incident_playbook(
    incident_description: str,
    include_defense_techniques: bool = True
) -> Dict[str, Any]:
    """
    Generate structured incident response playbook based on threat classification.

    Provides timeline-based action plan following NIST incident response phases:
    1. Immediate Actions (0-15 min)
    2. Investigation (15 min - 2 hours)
    3. Containment (2-8 hours)
    4. Recovery & Remediation (8+ hours)

    Integrates with classify_threat and get_defenses_for_threat for context-aware
    recommendations. 100% local implementation.

    Args:
        incident_description: Free-text description of the incident
                             (e.g., "Suspicious prompt injection attempts detected in production LLM")
        include_defense_techniques: Include specific AIDEFEND defense techniques (default: True)

    Returns:
        Dict containing:
            - incident_summary: Summary of the incident
            - threat_classification: Matched threats from OWASP/ATLAS/MAESTRO
            - timeline: Dict of {phase -> actions list}
            - defense_techniques: Recommended techniques (if requested)
            - generated_at: Timestamp

    Raises:
        InputValidationError: If inputs are invalid
        QueryEngineNotInitializedError: If database is not ready
        Exception: If playbook generation fails

    Example:
        >>> result = await generate_incident_playbook(
        ...     "Model outputs revealing training data in production"
        ... )
        >>> print(f"Threat: {result['threat_classification']['primary_threat']}")
        >>> for phase, actions in result['timeline'].items():
        ...     print(f"{phase}: {len(actions)} actions")
    """
    # Input validation (check parameters BEFORE database check)
    if not incident_description or not isinstance(incident_description, str):
        raise InputValidationError("incident_description must be a non-empty string")

    incident_description = validate_query_text(incident_description.strip())

    if len(incident_description) < 10:
        raise InputValidationError("incident_description must be at least 10 characters")

    if len(incident_description) > 1000:
        raise InputValidationError("incident_description must be less than 1000 characters")

    # Pre-flight check (AFTER parameter validation)
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please wait for initial sync to complete."
        )

    logger.info(
        "Generating incident response playbook",
        extra={"description_length": len(incident_description)}
    )

    try:
        # Step 1: Classify the threat
        logger.debug("Classifying threat...")
        threat_classification = None
        try:
            threat_classification = await classify_threat(incident_description)
            logger.info(
                f"Threat classified: {len(threat_classification.get('threat_details', []))} threats matched",
                extra={"threat_count": len(threat_classification.get('threat_details', []))}
            )
        except Exception as e:
            logger.warning(f"Threat classification failed (continuing with generic playbook): {e}")

        # Step 2: Get defense techniques if requested
        defense_techniques = None
        if include_defense_techniques and threat_classification:
            threat_details = threat_classification.get('threat_details', [])

            if threat_details:
                # Use the highest confidence threat for defense lookup
                primary_threat = threat_details[0]
                raw_threat_id = primary_threat.get('threat_id', '')
                # classify_threat returns IDs like "OWASP-LLM01" or "ATLAS-AML.T0043"
                # get_defenses_for_threat expects just "LLM01" or "AML.T0043"
                threat_id = raw_threat_id.split('-', 1)[1] if '-' in raw_threat_id else raw_threat_id

                if threat_id:
                    try:
                        logger.debug(f"Fetching defense techniques for threat: {threat_id}")
                        defense_techniques = await get_defenses_for_threat(
                            threat_id=threat_id,
                            top_k=10
                        )
                        logger.info(
                            f"Found {len(defense_techniques.get('defense_techniques', []))} defense techniques",
                            extra={"technique_count": len(defense_techniques.get('defense_techniques', []))}
                        )
                    except Exception as e:
                        logger.warning(f"Failed to fetch defense techniques: {e}")

        # Step 3: Generate timeline-based playbook
        timeline = {
            "immediate": {
                "phase": "Immediate Actions",
                "timeframe": "0-15 minutes",
                "objective": "Initial response, evidence preservation, and containment",
                "actions": _generate_immediate_actions(incident_description, threat_classification)
            },
            "investigation": {
                "phase": "Investigation",
                "timeframe": "15 minutes - 2 hours",
                "objective": "Threat analysis, scope determination, and root cause identification",
                "actions": _generate_investigation_actions(incident_description, threat_classification)
            },
            "containment": {
                "phase": "Containment",
                "timeframe": "2-8 hours",
                "objective": "Isolate threat, deploy defenses, and prevent further damage",
                "actions": _generate_containment_actions(incident_description, threat_classification, defense_techniques)
            },
            "recovery": {
                "phase": "Recovery & Remediation",
                "timeframe": "8+ hours",
                "objective": "Restore operations, implement long-term fixes, and document lessons learned",
                "actions": _generate_recovery_actions(incident_description, threat_classification, defense_techniques)
            }
        }

        # Step 4: Generate summary
        total_actions = sum(len(phase_data['actions']) for phase_data in timeline.values())

        incident_summary = {
            "description": incident_description,
            "total_action_items": total_actions,
            "phases": len(timeline),
            "estimated_total_time": "1-3 days (depending on severity and complexity)"
        }

        # Add primary threat if identified
        if threat_classification and threat_classification.get('threat_details'):
            primary_threat = threat_classification['threat_details'][0]
            incident_summary['primary_threat'] = {
                "threat_id": primary_threat.get('threat_id', ''),
                "framework": primary_threat.get('threat_id', '').split('-')[0] if primary_threat.get('threat_id') else '',
                "description": primary_threat.get('threat_name', ''),
                "confidence": primary_threat.get('confidence', 0) * 100  # Convert to percentage
            }

        result = {
            "incident_summary": incident_summary,
            "threat_classification": threat_classification,
            "timeline": timeline,
            "defense_techniques": defense_techniques if include_defense_techniques else None,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }

        logger.info(
            f"Incident playbook generated: {total_actions} actions across {len(timeline)} phases",
            extra={
                "total_actions": total_actions,
                "phases": len(timeline),
                "has_threat_classification": threat_classification is not None,
                "has_defense_techniques": defense_techniques is not None
            }
        )

        return result

    except InputValidationError:
        raise
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        logger.error(
            f"Incident playbook generation failed: {e}",
            exc_info=True,
            extra={"incident_description": incident_description[:100]}
        )
        raise Exception(f"Incident playbook generation failed: {str(e)}")
