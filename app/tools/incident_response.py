"""
Incident Response Playbook Generator for AIDEFEND MCP Service

Generates structured incident response playbooks based on threat classification.
Provides timeline-based action plans following industry-standard NIST phases.

100% local implementation - integrates with existing classify_threat and
get_defenses_for_threat tools.
"""

import asyncio
import re
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


_OWASP_LLM_2026_ID_PATTERN = re.compile(r"LLM(?:0[1-9]|10):2026")


def _classified_framework_ids(
    threat_classification: Optional[Dict[str, Any]],
    framework: str,
) -> set[str]:
    """Return exact classified IDs for one framework.

    ``normalized_threats`` is the canonical classifier contract. The detail
    fallback keeps the playbook helper usable with stored classifier responses
    that contain only the prefixed ``threat_id`` representation.
    """
    if not threat_classification:
        return set()

    framework_key = framework.casefold()
    ids = {
        str(threat_id).strip()
        for threat_id in (
            threat_classification.get("normalized_threats", {}).get(
                framework_key, []
            )
            or []
        )
        if str(threat_id).strip()
    }

    detail_prefix = f"{framework.upper()}-"
    for detail in threat_classification.get("threat_details", []) or []:
        raw_threat_id = str(detail.get("threat_id", "")).strip()
        if raw_threat_id.upper().startswith(detail_prefix):
            ids.add(raw_threat_id[len(detail_prefix):])

    return ids


def _classified_owasp_llm_2026_ids(
    threat_classification: Optional[Dict[str, Any]],
) -> set[str]:
    """Return only exact OWASP LLM Top 10 2026 classifier claims."""
    return {
        threat_id.upper()
        for threat_id in _classified_framework_ids(
            threat_classification, "owasp"
        )
        if _OWASP_LLM_2026_ID_PATTERN.fullmatch(threat_id.upper())
    }


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

    # Route threat-specific actions by exact 2026 risk semantics. Keyword
    # fragments are too broad here: for example, "training" is not itself
    # evidence of poisoning, and rate limiting alone does not bound agent loops.
    owasp_llm_ids = _classified_owasp_llm_2026_ids(threat_classification)

    if "LLM01:2026" in owasp_llm_ids:
        actions.append({
            "action": "Isolate Affected LLM Interaction Path",
            "priority": "CRITICAL",
            "description": (
                "Fail closed or disable the affected prompt, retrieval, tool, "
                "memory, or multimodal ingestion path; preserve the triggering "
                "content and resulting model/tool traces for replay."
            ),
            "estimated_time": "5 minutes"
        })

    if "LLM05:2026" in owasp_llm_ids:
        actions.append({
            "action": "Freeze Mutable Learning Sources",
            "priority": "CRITICAL",
            "description": (
                "Stop writes and promotion from affected training, fine-tuning, "
                "RAG-corpus, long-term-memory, and feedback sources; snapshot "
                "their versions, lineage, and hashes before remediation."
            ),
            "estimated_time": "2-5 minutes"
        })

    if "LLM06:2026" in owasp_llm_ids:
        actions.append({
            "action": "Trip Consumption Circuit Breakers",
            "priority": "HIGH",
            "description": (
                "Enforce emergency request, input/output/reasoning-token, "
                "concurrency, session, tool-iteration, and cost ceilings; stop "
                "runaway work while retaining usage and billing evidence."
            ),
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

    # Add containment steps tied to the actual 2026 risk mechanisms.
    owasp_llm_ids = _classified_owasp_llm_2026_ids(threat_classification)

    if "LLM01:2026" in owasp_llm_ids:
        actions.append({
            "action": "Enforce Instruction and Data Boundaries",
            "priority": "HIGH",
            "description": (
                "Treat external content as untrusted data, validate structured "
                "tool calls, constrain tool permissions, add approval gates for "
                "consequential actions, and replay the captured payload as a "
                "regression test."
            ),
            "estimated_time": "2-4 hours"
        })

    if "LLM05:2026" in owasp_llm_ids:
        actions.append({
            "action": "Quarantine and Rebuild Poisoned State",
            "priority": "CRITICAL",
            "description": (
                "Identify the last known-good dataset, model, retrieval index, "
                "memory, or feedback artifact; quarantine suspect versions, "
                "verify lineage and integrity, then rebuild or retrain the "
                "affected state before promotion."
            ),
            "estimated_time": "4-8 hours"
        })

    if "LLM06:2026" in owasp_llm_ids:
        actions.append({
            "action": "Deploy End-to-End Consumption Budgets",
            "priority": "HIGH",
            "description": (
                "Apply tenant and workload budgets across inference, reasoning, "
                "queues, sessions, multimodal processing, and tool calls with "
                "timeouts, bounded iterations, backpressure, and cost alerts."
            ),
            "estimated_time": "2-4 hours"
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


def _classified_threat_ids(
    threat_classification: Optional[Dict[str, Any]]
) -> List[str]:
    """Return canonical classified IDs in confidence order without duplicates."""
    if not threat_classification:
        return []

    ordered: List[str] = []
    seen = set()
    for detail in threat_classification.get("threat_details", []):
        if detail.get("resolvable") is False:
            continue
        raw_threat_id = detail.get("threat_id", "")
        threat_id = (
            raw_threat_id.split("-", 1)[1]
            if "-" in raw_threat_id
            else raw_threat_id
        )
        if threat_id and threat_id not in seen:
            seen.add(threat_id)
            ordered.append(threat_id)
    return ordered


def _merge_defense_results(
    lookups: List[tuple[str, Dict[str, Any]]],
    unresolved_threat_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Merge per-threat defense results by AIDEFEND control ID."""
    merged: Dict[str, Dict[str, Any]] = {}
    resolved_threat_ids: List[str] = []

    for threat_id, lookup in lookups:
        entries = lookup.get("defense_techniques", [])
        if entries:
            resolved_threat_ids.append(threat_id)

        for entry in entries:
            technique = entry.get("technique", {})
            technique_id = technique.get("id")
            if not technique_id:
                continue

            existing = merged.get(technique_id)
            if existing is None:
                existing = {
                    **entry,
                    "technique": dict(technique),
                    "matched_threats": list(entry.get("matched_threats", [])),
                    "matched_classified_threat_ids": [threat_id],
                }
                merged[technique_id] = existing
                continue

            existing["relevance_score"] = max(
                existing.get("relevance_score", 0),
                entry.get("relevance_score", 0),
            )
            for matched_item in entry.get("matched_threats", []):
                if matched_item not in existing["matched_threats"]:
                    existing["matched_threats"].append(matched_item)
            if threat_id not in existing["matched_classified_threat_ids"]:
                existing["matched_classified_threat_ids"].append(threat_id)

    defenses = sorted(
        merged.values(),
        key=lambda entry: entry.get("relevance_score", 0),
        reverse=True,
    )[:10]
    return {
        "threat_query": {
            "classified_threat_ids": [threat_id for threat_id, _ in lookups],
        },
        "defense_techniques": defenses,
        "total_results": len(defenses),
        "search_method": "multi_exact",
        "resolved_threat_ids": resolved_threat_ids,
        "unresolved_threat_ids": unresolved_threat_ids or [],
    }


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
            threat_ids = _classified_threat_ids(threat_classification)

            async def fetch_defenses(threat_id: str):
                try:
                    result = await get_defenses_for_threat(
                        threat_id=threat_id,
                        top_k=10,
                    )
                    return threat_id, result, None
                except Exception as exc:
                    return threat_id, None, exc

            lookup_results = await asyncio.gather(
                *(fetch_defenses(threat_id) for threat_id in threat_ids)
            )
            successful_lookups: List[tuple[str, Dict[str, Any]]] = []
            unresolved_threat_ids: List[str] = []

            for threat_id, lookup, error in lookup_results:
                if error is not None:
                    logger.warning(
                        f"Failed to fetch defense techniques for {threat_id}: {error}"
                    )
                    unresolved_threat_ids.append(threat_id)
                    continue
                if lookup and lookup.get("defense_techniques"):
                    successful_lookups.append((threat_id, lookup))
                else:
                    unresolved_threat_ids.append(threat_id)

            if successful_lookups:
                defense_techniques = _merge_defense_results(
                    successful_lookups,
                    unresolved_threat_ids,
                )
            else:
                # A recognized keyword may intentionally have no current
                # framework mapping. In that case, use its human-readable
                # keyword for semantic retrieval rather than fabricating an ID.
                keywords_found = threat_classification.get("keywords_found", [])
                fallback_keyword = (
                    keywords_found[0].get("keyword")
                    if keywords_found
                    else None
                ) or incident_description[:200]
                if fallback_keyword:
                    try:
                        defense_techniques = await get_defenses_for_threat(
                            threat_keyword=fallback_keyword,
                            top_k=10,
                        )
                        defense_techniques["search_method"] = "semantic_fallback"
                        defense_techniques["resolved_threat_ids"] = []
                        defense_techniques["unresolved_threat_ids"] = (
                            unresolved_threat_ids
                        )
                    except Exception as exc:
                        logger.warning(
                            f"Semantic defense fallback failed: {exc}"
                        )

            if defense_techniques:
                logger.info(
                    "Merged incident defense techniques",
                    extra={
                        "classified_threat_count": len(threat_ids),
                        "technique_count": len(
                            defense_techniques.get("defense_techniques", [])
                        ),
                    },
                )

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
