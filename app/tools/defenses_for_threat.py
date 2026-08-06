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
    framework_labels_from_version_info,
    is_actionable_record,
    normalize_framework_item,
)
from app.framework_migrations import (
    canonical_lookup_id,
    resolve_framework_reference,
)

logger = get_logger(__name__)


_NON_OWASP_ID_PATTERN = re.compile(
    r"(?:\bAML\.T\d|\bT\d{4}|\bNISTAML\.|\bASI\d|\bML\d{2}:2023|"
    r"\bAITECH-|\bAISUBTECH-)",
    re.IGNORECASE,
)
_OWASP_LLM_REFERENCE_PATTERN = re.compile(
    r"\bLLM\d|\bOWASP\s+(?:LLM|TOP\s+10\s+FOR\s+(?:LLM|LARGE\s+LANGUAGE\s+MODEL))",
    re.IGNORECASE,
)


def _contains_owasp_llm_reference(raw_reference: str) -> bool:
    return bool(_OWASP_LLM_REFERENCE_PATTERN.search(raw_reference))


def _contains_mixed_framework_reference(raw_reference: str) -> bool:
    return bool(
        _contains_owasp_llm_reference(raw_reference)
        and _NON_OWASP_ID_PATTERN.search(raw_reference)
    )


def _is_explicit_non_owasp_llm_reference(raw_reference: str) -> bool:
    """Protect other framework identifiers from OWASP-registry failures."""
    if _contains_owasp_llm_reference(raw_reference):
        return False
    if canonicalize_maestro_identifier(raw_reference):
        return True
    return bool(_NON_OWASP_ID_PATTERN.match(raw_reference.strip()))


def _registryless_owasp_llm_resolution(
    raw_reference: str,
) -> Optional[Dict[str, Any]]:
    """Fail closed for edition claims an old registry-less index cannot prove.

    A bare rank or an explicit 2025 ID retains the historical lookup behavior
    needed by existing indexes. Current/latest, malformed, mixed-framework, and
    multi-concept references return structured metadata and never fall through
    to the permissive legacy regex normalizer.
    """
    value = raw_reference.strip()
    if not _contains_owasp_llm_reference(value):
        return None

    def invalid(reason: str) -> Dict[str, Any]:
        return {
            "status": "invalid",
            "input": value,
            "frameworkKey": "owasp_llm",
            "reason": reason,
            "availableEdition": "2025",
        }

    if _contains_mixed_framework_reference(value):
        return invalid(
            "The threat_id mixes OWASP LLM and another framework reference; "
            "submit one framework risk per ID query."
        )

    reference_pattern = (
        r"\bLLM(\d+)(?::([a-z0-9_-]+))?"
        r"(?=$|[\s/(),;\[\]{}&?]|\.(?=$|\s|LLM))"
    )
    tokens = list(re.finditer(reference_pattern, value, re.IGNORECASE))
    llm_starts = {
        match.start() for match in re.finditer(r"\bLLM\d+", value, re.IGNORECASE)
    }
    if llm_starts - {match.start() for match in tokens}:
        return invalid(
            "The OWASP LLM identifier is malformed; the registry-less legacy "
            "index accepts only LLMdd or LLMdd:2025."
        )
    if not tokens:
        return invalid(
            "The query names OWASP LLM but does not contain a supported legacy risk ID."
        )

    normalized_tokens = []
    for token in tokens:
        rank_text = token.group(1)
        suffix = token.group(2).lower() if token.group(2) else None
        if not re.fullmatch(r"(?:0[1-9]|10)", rank_text):
            return invalid(
                f"OWASP LLM rank {rank_text!r} is malformed or outside the Top 10."
            )
        if suffix not in {None, "2025"}:
            return invalid(
                "The active index has no validated migration registry and cannot "
                f"resolve OWASP LLM edition {suffix!r}; complete a successful sync."
            )
        normalized_tokens.append(f"LLM{int(rank_text):02d}:2025")

    context_editions = set(re.findall(r"\b20\d{2}\b", value))
    if context_editions - {"2025"} or re.search(r"\blatest\b", value, re.IGNORECASE):
        return invalid(
            "The registry-less legacy index cannot satisfy a current/latest or "
            "non-2025 OWASP LLM edition request; complete a successful sync."
        )

    unique_tokens = list(dict.fromkeys(normalized_tokens))
    if len(unique_tokens) > 1:
        return {
            "status": "ambiguous",
            "input": value,
            "frameworkKey": "owasp_llm",
            "candidates": [
                {
                    "edition": "2025",
                    "id": identifier,
                    "label": identifier,
                }
                for identifier in unique_tokens
            ],
            "reason": (
                "The query contains multiple OWASP LLM concepts. Specify one risk; "
                "the registry-less legacy index will not choose by position."
            ),
        }
    return None


def _resolve_requested_threat_id(
    threat_id: str,
    version_info: Optional[Dict[str, Any]],
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Resolve one ID against the registry from the same data generation."""
    legacy_normalized_id = normalize_threat_id(threat_id)
    registry = (
        version_info.get("framework_migrations")
        if isinstance(version_info, dict)
        else None
    )

    if _contains_mixed_framework_reference(threat_id):
        resolution = {
            "status": "invalid",
            "input": threat_id.strip(),
            "frameworkKey": "owasp_llm",
            "reason": (
                "The threat_id mixes OWASP LLM and another framework "
                "reference; submit one framework risk per ID query."
            ),
        }
    elif registry is None:
        resolution = _registryless_owasp_llm_resolution(threat_id)
    elif _is_explicit_non_owasp_llm_reference(threat_id):
        resolution = None
    else:
        # A present registry is generation-integrity metadata, not optional
        # OWASP-only decoration. Invalid metadata must fail closed for every
        # query so callers cannot combine a table with untrusted labels/indexes.
        resolution = resolve_framework_reference(threat_id, registry)

    if resolution and resolution.get("canonical"):
        return resolution, canonical_lookup_id(resolution)
    if resolution and resolution.get("status") in {"ambiguous", "invalid"}:
        return resolution, None
    return resolution, legacy_normalized_id


def _resolution_only_payload(
    *,
    threat_id: str,
    threat_keyword: Optional[str],
    resolution: Dict[str, Any],
    framework_labels: Dict[str, str],
) -> Dict[str, Any]:
    return {
        "threat_query": {
            "threat_id": threat_id,
            "threat_keyword": threat_keyword,
            "normalized_threat_id": None,
            "lookup_threat_id": None,
            "canonical_threat_id": None,
            "resolution": resolution,
        },
        "defense_techniques": [],
        "total_results": 0,
        "search_method": "resolution_only",
        "framework_labels": framework_labels,
    }


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
    - Current or superseded OWASP LLM Top 10 IDs (e.g., 'LLM01',
      'LLM04:2026', or legacy 'LLM03:2025')
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

    if threat_id is not None and not isinstance(threat_id, str):
        raise InputValidationError("threat_id must be a string")
    if threat_id is not None and len(threat_id) > 500:
        raise InputValidationError("threat_id must not exceed 500 characters")

    if threat_keyword and len(threat_keyword) < 3:
        raise InputValidationError("threat_keyword must be at least 3 characters")

    if threat_keyword and len(threat_keyword) > 200:
        raise InputValidationError("threat_keyword must not exceed 200 characters")

    top_k = validate_bounded_integer(top_k, "top_k", 1, 50)

    logger.info(f"Searching defenses for threat_id={threat_id}, threat_keyword={threat_keyword}")

    try:
        results = []
        normalized_id = None
        resolution = None
        keyword = threat_keyword.strip() if threat_keyword else None
        query_embedding = None
        embedding_model_name = None

        # In hybrid mode, resolve the structured ID before loading an embedding
        # model. Invalid or ambiguous IDs are authoritative and must block the
        # keyword fallback without downloading a model or running vector search.
        # A valid hybrid query is resolved again against the final paired
        # table/metadata snapshot after the embedding is prepared.
        if threat_id and keyword:
            _, preflight_version_info = await query_engine.read_table_snapshot(
                lambda _table: None
            )
            preflight_framework_labels = framework_labels_from_version_info(
                preflight_version_info
            )
            preflight_resolution, _ = _resolve_requested_threat_id(
                threat_id,
                preflight_version_info,
            )
            if preflight_resolution and preflight_resolution.get("status") in {
                "ambiguous",
                "invalid",
            }:
                return _resolution_only_payload(
                    threat_id=threat_id,
                    threat_keyword=threat_keyword,
                    resolution=preflight_resolution,
                    framework_labels=preflight_framework_labels,
                )

        # Prepare a semantic vector outside the database reader lock. If a sync
        # activates a different embedding model before the snapshot begins, the
        # guarded operation reports the drift and we recompute against the new
        # model rather than querying a table with a mismatched vector shape.
        snapshot_payload = None
        version_info = None
        for _snapshot_attempt in range(3):
            if keyword:
                embedding_model_name = query_engine.active_embedding_model
                model = await asyncio.to_thread(
                    TextEmbedding,
                    model_name=embedding_model_name,
                )
                query_embedding = await asyncio.to_thread(
                    lambda: list(model.embed([keyword]))[0]
                )

            def read_generation(table):
                if (
                    query_embedding is not None
                    and query_engine.active_embedding_model
                    != embedding_model_name
                ):
                    return {"embedding_model_changed": True}

                documents = table.search().where(
                    "type = 'technique' OR type = 'subtechnique'"
                ).to_pandas().to_dict('records')
                semantic_documents = []
                if query_embedding is not None:
                    semantic_documents = table.search(
                        query_embedding.tolist()
                    ).where(
                        "type = 'technique' OR type = 'subtechnique'"
                    ).limit(top_k * 2).to_pandas().to_dict('records')
                return {
                    "embedding_model_changed": False,
                    "documents": documents,
                    "semantic_documents": semantic_documents,
                }

            snapshot_payload, version_info = (
                await query_engine.read_table_snapshot(read_generation)
            )
            if not snapshot_payload.get("embedding_model_changed"):
                break
        else:
            raise RuntimeError(
                "The active embedding generation changed repeatedly during the query; retry."
            )

        effective_framework_labels = framework_labels_from_version_info(
            version_info
        )
        all_techniques = [
            decode_framework_record(tech)
            for tech in snapshot_payload.get("documents", [])
        ]
        all_techniques = [
            tech for tech in all_techniques if is_actionable_record(tech)
        ]
        records_by_id = {
            tech.get("source_id"): tech
            for tech in all_techniques
            if tech.get("source_id")
        }

        # Case 1: Threat ID provided - exact matching in defends_against field
        if threat_id:
            resolution, normalized_id = _resolve_requested_threat_id(
                threat_id,
                version_info,
            )

            if resolution and resolution.get("status") in {"ambiguous", "invalid"}:
                return _resolution_only_payload(
                    threat_id=threat_id,
                    threat_keyword=threat_keyword,
                    resolution=resolution,
                    framework_labels=effective_framework_labels,
                )

            logger.info(
                "Normalized threat ID: %s -> %s (resolution=%s)",
                threat_id,
                normalized_id,
                resolution.get("status") if resolution else "legacy_or_non_owasp",
            )

        if threat_id and normalized_id:
            # Try to use pre-computed threat mappings index (fast path - O(1) lookup)
            threat_mappings = version_info.get('statistics', {}).get('threat_mappings', {}) if version_info else {}

            technique_ids = threat_mappings.get(normalized_id, [])

            index_mismatch = False
            if technique_ids:
                logger.info(f"Using threat mappings index: found {len(technique_ids)} techniques (fast path)")

                # Fetch only the specific techniques (targeted query)
                for tech_id in technique_ids:
                    # Sanitize technique_id to prevent filter injection
                    try:
                        sanitized_id = sanitize_technique_id(tech_id)
                    except InputValidationError:
                        index_mismatch = True
                        logger.error(
                            "Threat reverse index contains invalid technique ID %r",
                            tech_id,
                        )
                        continue

                    tech = records_by_id.get(sanitized_id)
                    if tech is not None:

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
                                        framework_labels=effective_framework_labels,
                                    ):
                                        matched_items.append(item)
                                        matched_framework = framework_name

                        except (json.JSONDecodeError, TypeError):
                            pass

                        if matched_items:
                            results.append({
                                "technique": _public_technique_payload(tech),
                                "relevance_score": 1.0,  # Exact match
                                "match_type": "exact_threat_id",
                                "matched_threats": matched_items,
                                "framework": matched_framework
                            })
                        else:
                            index_mismatch = True
                            logger.error(
                                "Threat reverse index candidate %s does not contain %s",
                                sanitized_id,
                                normalized_id,
                            )
                    else:
                        index_mismatch = True
                        logger.error(
                            "Threat reverse index candidate %s is absent from the active table",
                            sanitized_id,
                        )

            if not technique_ids or index_mismatch:
                # Fallback: full table scan (slow path - O(n) scan)
                logger.warning(
                    "Threat mappings index unavailable or inconsistent; "
                    "performing full table scan (slow path)"
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
                                if _threat_id_matches(
                                    normalized_id,
                                    item,
                                    framework_name,
                                    framework_labels=effective_framework_labels,
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
        if keyword:
            logger.info(f"Performing semantic search for: {keyword}")
            search_results = [
                decode_framework_record(doc)
                for doc in snapshot_payload.get("semantic_documents", [])
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

        if threat_id and normalized_id is None and not threat_keyword:
            search_method = "resolution_only"
        elif threat_id and threat_keyword:
            search_method = "hybrid"
        elif threat_id:
            search_method = "exact"
        else:
            search_method = "semantic"

        canonical_threat_id = None
        if isinstance(resolution, dict) and isinstance(
            resolution.get("canonical"), dict
        ):
            canonical_threat_id = resolution["canonical"].get("id")

        return {
            "threat_query": {
                "threat_id": threat_id,
                "threat_keyword": threat_keyword,
                "normalized_threat_id": normalized_id,
                "lookup_threat_id": normalized_id,
                "canonical_threat_id": canonical_threat_id,
                "resolution": resolution,
            },
            "defense_techniques": final_results,
            "total_results": len(final_results),
            "search_method": search_method,
            "framework_labels": effective_framework_labels,
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
        OWASP-LLM01:2026 -> LLM01
        OWASP-LLM03:2025 -> LLM03  # legacy fallback without a registry

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
    *,
    framework_labels: Optional[Dict[str, str]] = None,
) -> bool:
    """
    Check if normalized threat ID matches an item from defends_against.

    Args:
        normalized_query: Normalized threat ID query
        item_text: Item text from defends_against (e.g., "LLM01:2026 Prompt Injection")

    Returns:
        True if matches
    """
    if not framework_name:
        query_upper = normalized_query.upper()
        if query_upper.startswith("LLM"):
            framework_name = "OWASP LLM Top 10 2026"
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

    item_id = normalize_framework_item(
        framework_name,
        item_text,
        framework_labels=framework_labels,
    )
    if not item_id:
        return False

    resolved_framework_key = framework_key(
        framework_name,
        framework_labels=framework_labels,
    )
    if resolved_framework_key is None:
        query_id = normalize_framework_item(
            framework_name,
            normalized_query,
            framework_labels=framework_labels,
        )
        return bool(query_id and query_id.casefold() == item_id.casefold())

    if resolved_framework_key == "maestro":
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
