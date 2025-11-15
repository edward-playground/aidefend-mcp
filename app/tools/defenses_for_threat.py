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
from app.config import settings
from app.security import InputValidationError

logger = get_logger(__name__)


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
    import lancedb
    from app.core import query_engine
    from app.exceptions import QueryEngineNotInitializedError

    # Pre-flight check: ensure query engine is ready
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please run 'sync_aidefend' first to download the knowledge base."
        )

    # Input validation
    if not threat_id and not threat_keyword:
        raise InputValidationError("Either threat_id or threat_keyword must be provided")

    if top_k < 1 or top_k > 50:
        raise InputValidationError("top_k must be between 1 and 50")

    logger.info(f"Searching defenses for threat_id={threat_id}, threat_keyword={threat_keyword}")

    try:
        # Connect to LanceDB
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

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
                    tech_results = await asyncio.to_thread(
                        lambda tid=tech_id: table.search().where(f"source_id = '{tid}'").limit(1).to_pandas().to_dict('records')
                    )

                    if tech_results:
                        tech = tech_results[0]

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
                                    if _threat_id_matches(normalized_id, item):
                                        matched_items.append(item)
                                        matched_framework = framework_name

                        except (json.JSONDecodeError, TypeError):
                            pass

                        results.append({
                            "technique": {
                                "id": tech.get('source_id'),
                                "name": tech.get('name'),
                                "tactic": tech.get('tactic'),
                                "description": tech.get('text', ''),
                                "pillar": tech.get('pillar', ''),
                                "phase": tech.get('phase', '')
                            },
                            "relevance_score": 1.0,  # Exact match
                            "match_type": "exact_threat_id",
                            "matched_threats": matched_items,
                            "framework": matched_framework
                        })

            else:
                # Fallback: full table scan (slow path - O(n) scan)
                logger.warning(f"Threat mappings index not available or no match, performing full table scan (slow path)")

                all_techniques = await asyncio.to_thread(
                    lambda: table.search().where("type = 'technique'").to_pandas().to_dict('records')
                )

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
                                if _threat_id_matches(normalized_id, item):
                                    matched_items.append(item)
                                    matched_framework = framework_name

                        if matched_items:
                            results.append({
                                "technique": {
                                    "id": tech.get('source_id'),
                                    "name": tech.get('name'),
                                    "tactic": tech.get('tactic'),
                                    "description": tech.get('text', ''),
                                    "pillar": tech.get('pillar', ''),
                                    "phase": tech.get('phase', '')
                                },
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

            # Load embedding model
            model = await asyncio.to_thread(TextEmbedding, model_name=settings.EMBEDDING_MODEL)

            # Embed query
            query_embedding = list(await asyncio.to_thread(model.embed, [keyword]))[0]

            # Vector search
            search_results = await asyncio.to_thread(
                lambda: table.search(query_embedding.tolist()).where("type = 'technique'").limit(top_k).to_pandas().to_dict('records')
            )

            logger.info(f"Found {len(search_results)} results from semantic search")

            for doc in search_results:
                # Calculate relevance score (0.0-1.0)
                # LanceDB returns distance, lower is better, we need to convert
                # Assuming cosine similarity: score = 1 - distance
                distance = doc.get('_distance', 0.5)
                relevance_score = max(0.0, 1.0 - distance)

                results.append({
                    "technique": {
                        "id": doc.get('source_id'),
                        "name": doc.get('name'),
                        "tactic": doc.get('tactic'),
                        "description": doc.get('text', ''),
                        "pillar": doc.get('pillar', ''),
                        "phase": doc.get('phase', '')
                    },
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
    threat_id = threat_id.upper().strip()

    # Extract core ID from OWASP format
    if 'OWASP' in threat_id or 'LLM' in threat_id:
        # Extract LLM## pattern
        match = re.search(r'LLM\d{2}', threat_id)
        if match:
            return match.group(0)

    # MITRE ATLAS format
    if threat_id.startswith('T') and re.match(r'^T\d{4}', threat_id):
        if not threat_id.startswith('AML.'):
            return f"AML.{threat_id}"

    return threat_id


def _threat_id_matches(normalized_query: str, item_text: str) -> bool:
    """
    Check if normalized threat ID matches an item from defends_against.

    Args:
        normalized_query: Normalized threat ID query
        item_text: Item text from defends_against (e.g., "LLM01:2025 Prompt Injection")

    Returns:
        True if matches
    """
    item_text_upper = item_text.upper()

    # Exact substring match
    if normalized_query in item_text_upper:
        return True

    # For LLM IDs, match regardless of year
    if normalized_query.startswith('LLM'):
        # Match "LLM01" in "LLM01:2025" or "LLM01:2023"
        pattern = normalized_query + r'[:\s]'
        if re.search(pattern, item_text_upper):
            return True

    # For ATLAS IDs, match variations
    if 'AML.T' in normalized_query:
        # Extract T#### part
        t_part = re.search(r'T\d{4}', normalized_query)
        if t_part and t_part.group(0) in item_text_upper:
            return True

    return False


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
