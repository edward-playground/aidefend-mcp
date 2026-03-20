"""
Compliance Mapping Tool for AIDEFEND MCP Service

Maps AIDEFEND techniques to compliance frameworks using heuristic-based analysis.

100% LOCAL - No external API calls, all processing happens locally.
"""

import asyncio
from typing import Dict, Any, List

from app.logger import get_logger
from app.config import settings
from app.security import InputValidationError, sanitize_technique_id

logger = get_logger(__name__)

# Supported compliance frameworks with version information
# Last updated: 2025-12-05
FRAMEWORK_VERSIONS = {
    "nist_ai_rmf": "NIST AI RMF 2.0 (2024-02) + GenAI Profile (2024-07-26)",
    "eu_ai_act": "Regulation (EU) 2024/1689 (2024-07-12, effective 2024-08-01)",
    "iso_42001": "ISO/IEC 42001:2023",
    "csa_ai_controls": "CSA AI Controls Matrix (AICM) 2025 (2025-07-10)",
    "owasp_asvs": "OWASP ASVS 5.0.0 (2025-05)"
}

SUPPORTED_FRAMEWORKS = {
    "nist_ai_rmf": "NIST AI Risk Management Framework",
    "eu_ai_act": "EU AI Act",
    "iso_42001": "ISO/IEC 42001 (AI Management System)",
    "csa_ai_controls": "CSA AI Control Matrix",
    "owasp_asvs": "OWASP Application Security Verification Standard"
}

# Control descriptions for production-grade compliance mapping
# Subset of controls mapped by AIDEFEND techniques (full descriptions available on request)
CONTROL_DESCRIPTIONS = {
    "nist_ai_rmf": {
        "GOVERN-1.1": "Policies and procedures address AI systems' purposes, capabilities, and limitations",
        "GOVERN-1.2": "Legal and regulatory requirements involving AI are understood and managed",
        "GOVERN-4.1": "AI risk management process is established and documented",
        "MAP-2.3": "Scientific integrity and TEVV considerations are documented",
        "MAP-5.1": "Model, data, and system-level impacts are understood",
        "MANAGE-2.1": "Strategies to maximize benefits and minimize negative impacts are implemented",
        "MANAGE-3.1": "AI risks are prioritized based on likelihood and impact",
        "MANAGE-3.2": "Risk response and mitigation is assigned and actioned",
        "MANAGE-4.1": "AI systems are monitored for intended operation",
        "MANAGE-4.2": "Mechanisms enable alteration or decommissioning of deployed systems",
        "MANAGE-4.3": "AI incidents and errors are tracked and analyzed",
        "MANAGE-4.4": "AI system impacts are assessed and monitored",
        "MEASURE-2.1": "Test sets, metrics, and TEVV tools are documented",
        "MEASURE-2.11": "Fairness and bias are evaluated and documented"
    },
    "eu_ai_act": {
        "Art. 9 (Risk Management)": "Risk management system throughout AI system lifecycle",
        "Art. 10 (Data Governance)": "Appropriate data governance and management practices",
        "Art. 13 (Transparency)": "Sufficient transparency for users to interpret output",
        "Art. 14 (Human Oversight)": "Effective oversight by natural persons during use",
        "Art. 15 (Accuracy)": "Appropriate accuracy, robustness, and cybersecurity levels",
        "Art. 16 (Record-keeping)": "Automatic event logging throughout lifecycle",
        "Art. 52 (Transparency Obligations)": "Transparency when interacting with humans or generating content",
        "Art. 72 (Monitoring)": "Post-market monitoring systems proportionate to AI technologies",
        "Art. 72 (Post-market Monitoring)": "Continuous monitoring after deployment"
    },
    "iso_42001": {
        "5.3 (AI Policy)": "AI management system policies established and maintained",
        "6.1 (Risk Assessment)": "AI-related risks identified, analyzed, and evaluated",
        "7.2 (Competence)": "Personnel have appropriate AI system competence",
        "7.4 (Communication)": "Internal and external communications processes established",
        "8.2 (AI System Controls)": "Controls specific to AI system operations implemented",
        "8.3 (Security)": "Security controls for AI systems and data implemented",
        "8.3 (Security Controls)": "Technical and organizational security measures",
        "8.32 (Incident Management)": "Incident response for AI failures or breaches",
        "8.5 (Monitoring)": "AI system performance and control effectiveness monitored",
        "9.1 (Performance Evaluation)": "Management system performance evaluated at intervals",
        "9.2 (Internal Audit)": "Internal audits conducted at planned intervals",
        "10.2 (Continual Improvement)": "Continual improvement of management system",
        "A.2.9 (Incident Response)": "Procedures for detecting, reporting, and responding to AI incidents",
        "A.2.10 (Business Continuity)": "Continued operation or recovery of critical AI systems"
    },
    "csa_ai_controls": {
        "GRC-01 (Governance)": "AI governance framework with oversight mechanisms",
        "GRC-02 (Risk Management)": "Comprehensive AI risk management processes",
        "MDS-01 (Model Risk Assessment)": "AI model risk assessment including bias and security",
        "MDS-02 (Model Security)": "Security controls to prevent model tampering or poisoning",
        "IAM-01 (Identity & Access)": "Identity and access management for AI systems",
        "IAM-02 (Access Control)": "Least privilege and role-based access control",
        "DSP-02 (Data Protection)": "Protection of sensitive AI training and operational data",
        "TVM-01 (Threat Detection)": "Monitoring and detection of AI-specific threats",
        "TVM-02 (Vulnerability Management)": "AI vulnerability identification and remediation",
        "TVM-03 (Deception Technologies)": "Deception to detect adversarial AI attacks",
        "TVM-04 (Threat Remediation)": "AI threat and vulnerability remediation processes",
        "SEF-01 (Logging & Monitoring)": "Comprehensive AI activity logging and monitoring",
        "BCR-01 (Incident Containment)": "AI security incident containment procedures",
        "BCR-02 (Incident Response)": "AI-specific incident response plans",
        "BCR-03 (Business Continuity)": "Business continuity for AI dependencies",
        "BCR-04 (Disaster Recovery)": "Disaster recovery for AI systems and training data"
    },
    "owasp_asvs": {
        "V1 (Encoding & Sanitization)": "Data validation, sanitization, and encoding",
        "V2 (Validation)": "Input validation throughout application",
        "V2.1 (Business Logic)": "Business logic flow protections",
        "V3 (Web Frontend Security)": "Web frontend security controls",
        "V4.3 (API Error Handling)": "Secure API error handling",
        "V5.4 (Backup & Recovery)": "Documented and tested backup procedures",
        "V6 (Authentication)": "Secure authentication mechanisms",
        "V7 (Session Management)": "Secure session management",
        "V7.3 (Session Termination)": "Proper session termination on security events",
        "V8 (Authorization)": "Authorization controls enforcement",
        "V13 (Configuration)": "Hardened security configurations",
        "V14 (Data Protection)": "Cryptography and data protection mechanisms",
        "V15.1 (Secure Design)": "Secure design principles applied",
        "V15.2 (Threat Modeling)": "Threat modeling performed",
        "V16 (Security Logging)": "Security event logging and detection",
        "V16.2 (Attack Detection)": "Attack detection mechanisms monitored",
        "V16.3 (Incident Response)": "Documented incident response procedures",
        "V16.4 (Recovery)": "Security incident and data loss recovery"
    }
}

# Total controls in each framework (for coverage percentage calculation)
FRAMEWORK_CONTROL_TOTALS = {
    "nist_ai_rmf": 47,      # NIST AI RMF 2.0 + GenAI Profile
    "eu_ai_act": 85,        # EU AI Act high-risk requirements
    "iso_42001": 39,        # ISO/IEC 42001:2023 control objectives
    "csa_ai_controls": 243, # CSA AICM 2025 (18 domains)
    "owasp_asvs": 350       # OWASP ASVS 5.0.0 (approximate)
}


async def map_to_compliance_framework(
    technique_ids: List[str],
    framework: str = "nist_ai_rmf"
) -> Dict[str, Any]:
    """
    Map AIDEFEND techniques to compliance framework requirements.

    Uses heuristic-based analysis to map techniques to framework controls
    based on tactic alignment.

    100% LOCAL - No external API calls, all processing happens locally.

    Args:
        technique_ids: List of AIDEFEND technique IDs to map
        framework: Compliance framework to map to (default: nist_ai_rmf)

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
    from app.core import query_engine
    from app.exceptions import QueryEngineNotInitializedError

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

    # Pre-flight check: ensure query engine is ready
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please run 'sync_aidefend' first to download the knowledge base."
        )

    logger.info(f"Mapping {len(technique_ids)} techniques to {framework}")

    try:
        # Get technique details from database
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

        mappings = []

        for tech_id in technique_ids:
            tech_id = tech_id.strip().upper()

            # Sanitize technique_id to prevent filter injection
            sanitized_id = sanitize_technique_id(tech_id)

            # Get technique (using sanitized ID)
            docs = await asyncio.to_thread(
                lambda sid=sanitized_id: table.search().where(f"source_id = '{sid}'").limit(1).to_pandas().to_dict('records')
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

            # Use heuristic-based mapping (100% local)
            mapping = _generate_heuristic_mapping(doc, framework)

            mappings.append(mapping)

        # PRODUCTION-GRADE ENHANCEMENT: Calculate coverage summary
        covered_controls = set()
        for mapping in mappings:
            for control in mapping.get("framework_controls", []):
                control_id = control.get("id") if isinstance(control, dict) else control
                if control_id:
                    covered_controls.add(control_id)

        total_controls_in_framework = FRAMEWORK_CONTROL_TOTALS.get(framework, 100)
        coverage_percentage = round((len(covered_controls) / total_controls_in_framework) * 100, 1)

        # Identify high-priority uncovered controls (domain-specific recommendations)
        uncovered_critical_controls = _get_uncovered_critical_controls(
            framework,
            covered_controls
        )

        result = {
            "framework": {
                "id": framework,
                "name": SUPPORTED_FRAMEWORKS[framework],
                "version": FRAMEWORK_VERSIONS[framework]
            },
            "mappings": mappings,
            "total_mapped": len(mappings),
            "mapping_method": "heuristic",
            "summary": {
                "total_controls_in_framework": total_controls_in_framework,
                "covered_controls": len(covered_controls),
                "coverage_percentage": f"{coverage_percentage}%",
                "uncovered_critical_controls": uncovered_critical_controls[:10]  # Top 10 critical gaps
            },
            "disclaimer": (
                f"Compliance mappings are generated automatically using heuristic analysis "
                f"based on {FRAMEWORK_VERSIONS[framework]} and should be reviewed by compliance experts. "
                f"Mappings may not cover all requirements and should be used as guidance only."
            )
        }

        logger.info(
            f"Generated {len(mappings)} compliance mappings with {coverage_percentage}% coverage",
            extra={"framework": framework, "covered_controls": len(covered_controls)}
        )

        return result

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to map to compliance framework: {e}", exc_info=True)
        raise


def _get_uncovered_critical_controls(
    framework: str,
    covered_controls: set
) -> List[str]:
    """
    Identify high-priority uncovered controls in the framework.

    Returns list of critical control IDs that are not yet covered by implemented techniques.
    This helps users prioritize which additional techniques to implement.

    Args:
        framework: Framework ID
        covered_controls: Set of control IDs already covered

    Returns:
        List of uncovered critical control IDs with high priority
    """
    # Define critical controls per framework (high-priority for security)
    critical_controls_by_framework = {
        "nist_ai_rmf": [
            "GOVERN-1.1", "GOVERN-4.1", "MANAGE-2.1", "MANAGE-4.1",
            "MEASURE-2.1", "MEASURE-2.11", "MAP-5.1", "MANAGE-3.1"
        ],
        "eu_ai_act": [
            "Art. 9 (Risk Management)", "Art. 15 (Accuracy)", "Art. 14 (Human Oversight)",
            "Art. 72 (Monitoring)", "Art. 13 (Transparency)", "Art. 10 (Data Governance)"
        ],
        "iso_42001": [
            "6.1 (Risk Assessment)", "8.2 (AI System Controls)", "8.3 (Security)",
            "8.5 (Monitoring)", "9.1 (Performance Evaluation)", "8.32 (Incident Management)"
        ],
        "csa_ai_controls": [
            "GRC-02 (Risk Management)", "MDS-01 (Model Risk Assessment)", "MDS-02 (Model Security)",
            "TVM-01 (Threat Detection)", "TVM-02 (Vulnerability Management)", "SEF-01 (Logging & Monitoring)",
            "BCR-02 (Incident Response)", "IAM-01 (Identity & Access)"
        ],
        "owasp_asvs": [
            "V6 (Authentication)", "V8 (Authorization)", "V2 (Validation)",
            "V15.2 (Threat Modeling)", "V16 (Security Logging)", "V14 (Data Protection)",
            "V13 (Configuration)", "V16.3 (Incident Response)"
        ]
    }

    critical_controls = critical_controls_by_framework.get(framework, [])
    uncovered = [ctrl for ctrl in critical_controls if ctrl not in covered_controls]

    return uncovered


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
    # Updated: 2025-12-05 to reflect latest framework versions
    framework_mappings = {
        # NIST AI RMF 2.0 + Generative AI Profile (2024-07-26)
        "nist_ai_rmf": {
            "Model": ["GOVERN-1.1", "MAP-2.3", "MAP-5.1"],
            "Harden": ["GOVERN-1.2", "MANAGE-2.1", "GOVERN-4.1"],
            "Detect": ["MEASURE-2.1", "MEASURE-2.11", "MANAGE-4.1"],
            "Isolate": ["MANAGE-3.1", "MANAGE-3.2"],
            "Deceive": ["MANAGE-4.2"],
            "Evict": ["MANAGE-4.3"],
            "Restore": ["MANAGE-4.4"]
        },
        # EU AI Act - Regulation (EU) 2024/1689
        "eu_ai_act": {
            "Model": ["Art. 9 (Risk Management)", "Art. 15 (Accuracy)", "Art. 10 (Data Governance)"],
            "Harden": ["Art. 9 (Risk Management)", "Art. 13 (Transparency)", "Art. 14 (Human Oversight)"],
            "Detect": ["Art. 9 (Risk Management)", "Art. 16 (Record-keeping)", "Art. 72 (Monitoring)"],
            "Isolate": ["Art. 9 (Risk Management)", "Art. 14 (Human Oversight)"],
            "Deceive": ["Art. 9 (Risk Management)", "Art. 52 (Transparency Obligations)"],
            "Evict": ["Art. 9 (Risk Management)", "Art. 14 (Human Oversight)"],
            "Restore": ["Art. 9 (Risk Management)", "Art. 16 (Record-keeping)", "Art. 72 (Post-market Monitoring)"]
        },
        # ISO/IEC 42001:2023
        "iso_42001": {
            "Model": ["6.1 (Risk Assessment)", "7.4 (Communication)", "5.3 (AI Policy)"],
            "Harden": ["8.2 (AI System Controls)", "8.3 (Security)", "7.2 (Competence)"],
            "Detect": ["8.5 (Monitoring)", "9.1 (Performance Evaluation)", "9.2 (Internal Audit)"],
            "Isolate": ["8.3 (Security Controls)", "8.32 (Incident Management)"],
            "Deceive": ["8.3 (Security Controls)"],
            "Evict": ["8.32 (Incident Management)", "A.2.9 (Incident Response)"],
            "Restore": ["8.32 (Incident Management)", "10.2 (Continual Improvement)", "A.2.10 (Business Continuity)"]
        },
        # CSA AI Controls Matrix (AICM) 2025
        # 18 domains, 243 control objectives
        "csa_ai_controls": {
            "Model": ["GRC-01 (Governance)", "GRC-02 (Risk Management)", "MDS-01 (Model Risk Assessment)"],
            "Harden": ["IAM-01 (Identity & Access)", "DSP-02 (Data Protection)", "MDS-02 (Model Security)"],
            "Detect": ["TVM-01 (Threat Detection)", "TVM-02 (Vulnerability Management)", "SEF-01 (Logging & Monitoring)"],
            "Isolate": ["IAM-02 (Access Control)", "BCR-01 (Incident Containment)"],
            "Deceive": ["TVM-03 (Deception Technologies)"],
            "Evict": ["BCR-02 (Incident Response)", "TVM-04 (Threat Remediation)"],
            "Restore": ["BCR-03 (Business Continuity)", "BCR-04 (Disaster Recovery)"]
        },
        # OWASP ASVS 5.0.0 (2025-05)
        # 17 chapters, ~350 requirements
        "owasp_asvs": {
            "Model": ["V15.1 (Secure Design)", "V15.2 (Threat Modeling)", "V2.1 (Business Logic)"],
            "Harden": ["V1 (Encoding & Sanitization)", "V6 (Authentication)", "V8 (Authorization)", "V13 (Configuration)"],
            "Detect": ["V16 (Security Logging)", "V2 (Validation)", "V4.3 (API Error Handling)"],
            "Isolate": ["V8 (Authorization)", "V7 (Session Management)"],
            "Deceive": ["V3 (Web Frontend Security)", "V16.2 (Attack Detection)"],
            "Evict": ["V16.3 (Incident Response)", "V7.3 (Session Termination)"],
            "Restore": ["V16.4 (Recovery)", "V14 (Data Protection)", "V5.4 (Backup & Recovery)"]
        }
    }

    control_ids = framework_mappings.get(framework, {}).get(tactic, [])

    # Convert control IDs to objects with descriptions (PRODUCTION-GRADE ENHANCEMENT)
    control_objects = []
    control_descriptions_map = CONTROL_DESCRIPTIONS.get(framework, {})

    for control_id in control_ids:
        control_obj = {
            "id": control_id,
            "description": control_descriptions_map.get(control_id, "Description not available"),
            "confidence": "high" if control_descriptions_map.get(control_id) else "medium"
        }
        control_objects.append(control_obj)

    return {
        "technique_id": tech_id,
        "technique_name": tech_name,
        "technique_tactic": tactic,
        "framework": framework,
        "framework_name": SUPPORTED_FRAMEWORKS[framework],
        "framework_controls": control_objects,  # Now objects with id, description, confidence
        "mapping_confidence": "medium" if control_objects else "low",
        "mapping_rationale": f"Mapped based on tactic '{tactic}' alignment with framework requirements",
        "additional_considerations": [
            "Review with compliance team for completeness",
            "May require additional controls depending on specific use case",
            "Consider combination with other techniques for full compliance"
        ]
    }
