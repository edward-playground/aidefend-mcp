"""
Defenses for Threat Tool for AIDEFEND MCP Service

Maps threats (OWASP, MITRE ATLAS, MAESTRO) to AIDEFEND defense techniques.
"""

import json
import re
import asyncio
from typing import Dict, Any, List, Optional
from fastembed import TextEmbedding

from app.logger import get_logger
from app.security import (
    InputValidationError,
    sanitize_technique_id,
    validate_bounded_integer,
)
from app.framework_utils import (
    canonicalize_maestro_identifier,
    framework_key,
    is_actionable_record,
    normalize_framework_item,
)

logger = get_logger(__name__)


def _public_technique_payload(technique: Dict[str, Any]) -> Dict[str, Any]:
    """Return one stable schema-2.3 technique object for every search path."""
    return {
        "id": technique.get('source_id'),
        "name": technique.get('name'),
        "type": technique.get('type'),
        "tactic": technique.get('tactic'),
        "description": technique.get('text', ''),
        "pillar": technique.get('pillar', []),
        "phase": technique.get('phase', []),
        "parent_technique_id": technique.get('parent_technique_id', ''),
        "guidance_id": technique.get('guidance_id', ''),
        "scope_boundary": technique.get('scope_boundary') or {},
        "tools_opensource": technique.get('tools_opensource', []),
        "tools_source_available": technique.get('tools_source_available', []),
        "tools_commercial": technique.get('tools_commercial', []),
        "is_actionable": bool(technique.get('is_actionable', False)),
        "is_parent_family": bool(technique.get('is_parent_family', False)),
    }


async def get_defenses_for_threat(
    threat_id: Optional[str] = None,
    threat_keyword: Optional[str] = None,
    top_k: int = 10
) -> Dict[str, Any]:
    """
    Find AIDEFEND defense techniques for a specific threat.

    Supports:
    - Threat IDs from OWASP LLM Top 10 (e.g., 'LLM01', 'OWASP-LLM01:2025')
    - Threat IDs from MITRE ATLAS (e.g., 'T0015', 'AML.T0043')
    - Threat IDs from MAESTRO (e.g., 'Adversarial Examples')
    - Natural language threat keywords (e.g., 'prompt injection')

    Args:
        threat_id: Threat ID from OWASP/ATLAS/MAESTRO (optional)
        threat_keyword: Threat keyword in natural language (optional)
        top_k: Number of defense techniques to return (1-50, default: 10)

    Returns:
        Dict containing matched defense techniques with relevance scores

    Raises:
        InputValidationError: If inputs are invalid
        Exception: If database query fails

    Example:
        >>> # By threat ID
        >>> result = await get_defenses_for_threat(threat_id="LLM01")
        >>> print(f"Found {len(result['defense_techniques'])} defenses")

        >>> # By keyword
        >>> result = await get_defenses_for_threat(threat_keyword="prompt injection")
    """
    from app.core import decode_framework_record, query_engine

    # Input validation (check parameters BEFORE database check)
    if not threat_id and not threat_keyword:
        raise InputValidationError("Either threat_id or threat_keyword must be provided")

    if threat_keyword and len(threat_keyword) < 3:
        raise InputValidationError("threat_keyword must be at least 3 characters")

    if threat_keyword and len(threat_keyword) > 200:
        raise InputValidationError("threat_keyword must not exceed 200 characters")

    top_k = validate_bounded_integer(top_k, "top_k", 1, 50)

    logger.info(f"Searching defenses for threat_id={threat_id}, threat_keyword={threat_keyword}")

    try:
        results = []

        # Case 1: Threat ID provided - exact matching in defends_against field
        if threat_id:
            normalized_id = normalize_threat_id(threat_id)
            logger.info(f"Normalized threat ID: {threat_id} -> {normalized_id}")

            # Try to use pre-computed threat mappings index (fast path - O(1) lookup)
            from app.utils import load_version_info
            version_info = load_version_info()
            threat_mappings = version_info.get('statistics', {}).get('threat_mappings', {}) if version_info else {}

            technique_ids = threat_mappings.get(normalized_id, [])

            if technique_ids:
                logger.info(f"Using threat mappings index: found {len(technique_ids)} techniques (fast path)")

                # Fetch only the specific techniques (targeted query)
                for tech_id in technique_ids:
                    # Sanitize technique_id to prevent filter injection
                    sanitized_id = sanitize_technique_id(tech_id)

                    tech_results = await query_engine.read_table(
                        lambda table, tid=sanitized_id: table.search().where(
                            f"source_id = '{tid}'"
                        ).limit(1).to_pandas().to_dict('records')
                    )

                    if tech_results:
                        tech = decode_framework_record(tech_results[0])

                        # Extract matched threats from defends_against
                        defends_against_str = tech.get('defends_against', '[]')
                        matched_items = []
                        matched_framework = None

                        try:
                            defends_against = json.loads(defends_against_str) if isinstance(defends_against_str, str) else defends_against_str

                            for framework_data in defends_against:
                                framework_name = framework_data.get('framework', '')
                                items = framework_data.get('items', [])

                                for item in items:
                                    if _threat_id_matches(
                                        normalized_id,
                                        item,
                                        framework_name,
                                    ):
                                        matched_items.append(item)
                                        matched_framework = framework_name

                        except (json.JSONDecodeError, TypeError):
                            pass

                        results.append({
                            "technique": _public_technique_payload(tech),
                            "relevance_score": 1.0,  # Exact match
                            "match_type": "exact_threat_id",
                            "matched_threats": matched_items,
                            "framework": matched_framework
                        })

            else:
                # Fallback: full table scan (slow path - O(n) scan)
                logger.warning(f"Threat mappings index not available or no match, performing full table scan (slow path)")

                all_techniques = await query_engine.read_table(
                    lambda table: table.search().where(
                        "type = 'technique' OR type = 'subtechnique'"
                    ).to_pandas().to_dict('records')
                )
                all_techniques = [
                    decode_framework_record(tech) for tech in all_techniques
                ]
                all_techniques = [tech for tech in all_techniques if is_actionable_record(tech)]

                logger.info(f"Scanning {len(all_techniques)} techniques for threat mappings...")

                for tech in all_techniques:
                    defends_against_str = tech.get('defends_against', '[]')

                    try:
                        defends_against = json.loads(defends_against_str) if isinstance(defends_against_str, str) else defends_against_str

                        if not defends_against:
                            continue

                        # Check if this technique defends against the threat
                        matched_items = []
                        matched_framework = None

                        for framework_data in defends_against:
                            framework_name = framework_data.get('framework', '')
                            items = framework_data.get('items', [])

                            for item in items:
                                if _threat_id_matches(
                                    normalized_id,
                                    item,
                                    framework_name,
                                ):
                                    matched_items.append(item)
                                    matched_framework = framework_name

                        if matched_items:
                            results.append({
                                "technique": _public_technique_payload(tech),
                                "relevance_score": 1.0,  # Exact match
                                "match_type": "exact_threat_id",
                                "matched_threats": matched_items,
                                "framework": matched_framework
                            })

                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse defends_against for {tech.get('source_id')}: {e}")

            logger.info(f"Found {len(results)} exact matches for threat ID")

        # Case 2: Threat keyword provided - semantic search
        if threat_keyword:
            keyword = threat_keyword.strip()

            if len(keyword) < 3:
                raise InputValidationError("threat_keyword must be at least 3 characters")

            if len(keyword) > 200:
                raise InputValidationError("threat_keyword too long (max 200 characters)")

            logger.info(f"Performing semantic search for: {keyword}")

            # Load embedding model that matches the active LanceDB vectors
            model_name = query_engine.active_embedding_model
            model = await asyncio.to_thread(TextEmbedding, model_name=model_name)

            # Embed query
            query_embedding = list(await asyncio.to_thread(model.embed, [keyword]))[0]

            # Vector search
            search_results = await query_engine.read_table(
                lambda table: table.search(query_embedding.tolist()).where(
                    "type = 'technique' OR type = 'subtechnique'"
                ).limit(top_k * 2).to_pandas().to_dict('records')
            )
            search_results = [
                decode_framework_record(doc) for doc in search_results
            ]
            search_results = [doc for doc in search_results if is_actionable_record(doc)]

            logger.info(f"Found {len(search_results)} results from semantic search")

            for doc in search_results:
                # Calculate relevance score (0.0-1.0)
                # LanceDB returns L2 distance (lower is better, no upper bound)
                # Convert to similarity score using: score = 1 / (1 + distance)
                # This ensures: distance=0 → score=1.0, distance=∞ → score=0.0
                distance = doc.get('_distance', 1.0)
                relevance_score = 1.0 / (1.0 + distance)

                results.append({
                    "technique": _public_technique_payload(doc),
                    "relevance_score": round(relevance_score, 3),
                    "match_type": "semantic_search",
                    "matched_threats": [],
                    "framework": "semantic"
                })

        # Deduplicate and sort by relevance
        unique_results = _deduplicate_results(results)
        sorted_results = sorted(unique_results, key=lambda x: x['relevance_score'], reverse=True)

        # Limit to top_k
        final_results = sorted_results[:top_k]

        logger.info(f"Returning {len(final_results)} defense techniques")

        return {
            "threat_query": {
                "threat_id": threat_id,
                "threat_keyword": threat_keyword,
                "normalized_threat_id": normalize_threat_id(threat_id) if threat_id else None
            },
            "defense_techniques": final_results,
            "total_results": len(final_results),
            "search_method": "hybrid" if (threat_id and threat_keyword) else ("exact" if threat_id else "semantic")
        }

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to get defenses for threat: {e}", exc_info=True)
        raise


def normalize_threat_id(threat_id: str) -> str:
    """
    Normalize threat ID to standard format.

    Examples:
        LLM01 -> LLM01
        T0015 -> AML.T0015
        AML.T0043 -> AML.T0043
        OWASP-LLM01:2025 -> LLM01

    Args:
        threat_id: Raw threat ID

    Returns:
        Normalized threat ID
    """
    raw_threat_id = threat_id.strip()

    # MAESTRO uses canonical labels rather than machine IDs. Resolve both the
    # current labels and legacy L#-/Cross- classifier slugs before uppercasing.
    maestro_id = canonicalize_maestro_identifier(raw_threat_id)
    if maestro_id:
        return maestro_id

    threat_id = raw_threat_id.upper()

    # Extract core IDs from OWASP formats
    if 'OWASP' in threat_id or 'LLM' in threat_id:
        # Extract LLM## pattern
        match = re.search(r'LLM\d{2}', threat_id)
        if match:
            return match.group(0)
    if 'ML' in threat_id:
        match = re.search(r'ML\d{2}:2023', threat_id)
        if match:
            return match.group(0)
    if 'ASI' in threat_id:
        match = re.search(r'ASI\d{2}:2026', threat_id)
        if match:
            return match.group(0)

    # MITRE ATLAS format
    if threat_id.startswith('T') and re.match(r'^T\d{4}', threat_id):
        if not threat_id.startswith('AML.'):
            return f"AML.{threat_id}"

    if threat_id.startswith('NISTAML.'):
        return threat_id

    cisco_match = re.search(r'AI(?:SUBTECH|TECH)-[\d\.]+', threat_id)
    if cisco_match:
        return cisco_match.group(0)

    return threat_id


def _threat_id_matches(
    normalized_query: str,
    item_text: str,
    framework_name: Optional[str] = None,
) -> bool:
    """
    Check if normalized threat ID matches an item from defends_against.

    Args:
        normalized_query: Normalized threat ID query
        item_text: Item text from defends_against (e.g., "LLM01:2025 Prompt Injection")

    Returns:
        True if matches
    """
    if not framework_name:
        query_upper = normalized_query.upper()
        if query_upper.startswith("LLM"):
            framework_name = "OWASP LLM Top 10 2025"
        elif re.match(r"^ML\d{2}:2023$", query_upper):
            framework_name = "OWASP ML Top 10 2023"
        elif query_upper.startswith("ASI"):
            framework_name = "OWASP Top 10 for Agentic Applications 2026"
        elif query_upper.startswith(("AML.T", "T")):
            framework_name = "MITRE ATLAS"
        elif query_upper.startswith("NISTAML."):
            framework_name = "NIST Adversarial Machine Learning 2025"
        elif query_upper.startswith(("AITECH-", "AISUBTECH-")):
            framework_name = "Cisco Integrated AI Security and Safety Framework"
        else:
            framework_name = "MAESTRO"

    item_id = normalize_framework_item(framework_name, item_text)
    if not item_id:
        return False

    if framework_key(framework_name) is None:
        query_id = normalize_framework_item(framework_name, normalized_query)
        return bool(query_id and query_id.casefold() == item_id.casefold())

    if framework_name.upper().strip() == "MAESTRO":
        query_id = canonicalize_maestro_identifier(normalized_query)
        return bool(query_id and query_id.casefold() == item_id.casefold())

    query_id = normalize_threat_id(normalized_query)
    return query_id.casefold() == item_id.casefold()


def _deduplicate_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate techniques, keeping the one with highest relevance.

    Args:
        results: List of result dicts

    Returns:
        Deduplicated list
    """
    seen = {}

    for result in results:
        tech_id = result['technique']['id']

        if tech_id not in seen or result['relevance_score'] > seen[tech_id]['relevance_score']:
            seen[tech_id] = result

    return list(seen.values())
