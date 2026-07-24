"""
Classify Threat Tool for AIDEFEND MCP Service

Maps threat keywords from unstructured text to standard framework IDs
(OWASP LLM Top 10, MITRE ATLAS, MAESTRO) using 2-tier matching strategy:

Tier 1: Static keyword matching (exact matches)
Tier 2: Enhanced fuzzy matching with RapidFuzz (typo-tolerant, 10-100x faster)

100% LOCAL - No external API calls, all processing happens locally.
FREE - Zero cost, no tokens consumed.

LLM handles text understanding; this tool provides standardized threat ID mappings.
"""

from typing import Dict, Any, List, Optional
from rapidfuzz import fuzz, process
from app.logger import get_logger
from app.security import InputValidationError, validate_bounded_integer
from app.threat_keywords import (
    THREAT_KEYWORDS,
    canonicalize_classifier_frameworks,
)
from app.config import settings
from app.utils import load_version_info

logger = get_logger(__name__)


def _current_index_threat_ids() -> Optional[set[str]]:
    """Return threat IDs that resolve to at least one control in the live index."""
    version_info = load_version_info() or {}
    statistics = version_info.get("statistics")
    mappings = statistics.get("threat_mappings") if isinstance(statistics, dict) else None
    if not isinstance(mappings, dict):
        return None

    return {
        str(threat_id).strip().casefold()
        for threat_id, control_ids in mappings.items()
        if str(threat_id).strip()
        and isinstance(control_ids, list)
        and bool(control_ids)
    }


async def classify_threat(text: str, top_k: int = 5) -> Dict[str, Any]:
    """
    Classify threats in text using 2-tier local matching strategy.

    Tier 1: Static keyword matching (exact string matches)
    Tier 2: Enhanced fuzzy matching with RapidFuzz (typo-tolerant, 10-100x faster than difflib)

    100% LOCAL - No external API calls, all processing happens locally.
    FREE - Zero cost, no tokens consumed.

    This function:
    1. Normalizes input text (lowercase)
    2. Tier 1: Matches against predefined keyword dictionary
    3. Tier 2 (if no static match): Advanced fuzzy matching with multiple strategies
    4. Returns normalized threat IDs + recommended tool calls

    Args:
        text: Input text containing threat-related content
        top_k: Maximum number of keywords to return (1-10)

    Returns:
        Dict containing:
        - source: 'static_keyword', 'fuzzy_match', or 'no_match'
        - input_text_preview: First 100 chars of input
        - keywords_found: List of matched keywords with confidence
        - normalized_threats: Dict of {framework -> [threat_ids]}
        - threat_details: Detailed threat information
        - recommended_actions: Suggested followup tool calls

    Raises:
        InputValidationError: If input validation fails

    Example:
        >>> result = await classify_threat(
        ...     text="Recent prompt injection attack detected"
        ... )
        >>> print(result['source'])
        'static_keyword'
        >>> print(result['normalized_threats']['owasp'])
        ['LLM01']
    """
    # Input validation
    if not text:
        raise InputValidationError("text cannot be empty")

    if not isinstance(text, str):
        raise InputValidationError("text must be a string")

    if len(text) > 10000:
        raise InputValidationError("text too long (max 10000 characters)")

    top_k = validate_bounded_integer(top_k, "top_k", 1, 10)

    logger.info(f"Classifying threats in text ({len(text)} chars)")

    # === TIER 1: Static Keyword Matching ===
    matches = _match_threats(text)
    match_source = "static_keyword"

    if matches:
        logger.info(f"Static keyword match found (confidence: {matches[0]['confidence']:.2f})")

    # === TIER 2: Fuzzy Matching (if enabled and no static match found) ===
    if settings.ENABLE_FUZZY_MATCHING and not matches:
        logger.info("No static match found. Attempting fuzzy matching for typo tolerance...")
        fuzzy_matches = _fuzzy_match_threats(text)
        if fuzzy_matches and fuzzy_matches[0]["confidence"] >= settings.FUZZY_MATCH_CUTOFF:
            matches = fuzzy_matches
            match_source = "fuzzy_match"
            logger.info(f"Fuzzy match found (confidence: {matches[0]['confidence']:.2f})")

    # If still no matches, set source to no_match
    if not matches:
        match_source = "no_match"
        logger.info("No threat matches found across all tiers")

    # Limit to top_k
    top_matches = matches[:top_k]

    # Aggregate normalized threat IDs
    normalized_threats = {"owasp": set(), "atlas": set(), "maestro": set()}
    threat_details = []
    unmapped_keywords = []
    live_threat_ids = _current_index_threat_ids()
    unresolved_claims: List[str] = []

    for match in top_matches:
        keyword = match["keyword"]
        # Defense in depth: THREAT_KEYWORDS is normalized at import, but keep
        # the public classifier boundary fail-closed if a caller or test
        # replaces an entry with a legacy/stale mapping.
        frameworks = canonicalize_classifier_frameworks(match["frameworks"])
        confidence = match["confidence"]
        match_type = match.get("match_type", "unknown")

        if not frameworks:
            unmapped_keywords.append(keyword)

        # Add to normalized_threats
        for framework, threat_ids in frameworks.items():
            if framework not in normalized_threats:
                normalized_threats[framework] = set()
            normalized_threats[framework].update(threat_ids)

        # Build threat_details
        for framework, threat_ids in frameworks.items():
            for threat_id in threat_ids:
                resolvable = (
                    live_threat_ids is not None
                    and threat_id.strip().casefold() in live_threat_ids
                )
                if not resolvable:
                    unresolved_claims.append(f"{framework}:{threat_id}")
                threat_details.append({
                    "threat_id": f"{framework.upper()}-{threat_id}",
                    "threat_name": keyword.title(),
                    "confidence": confidence,
                    "matched_keyword": keyword,
                    "match_type": match_type,
                    "resolvable": resolvable,
                })

    # Convert sets to sorted lists
    normalized_threats = {
        k: sorted(list(v)) for k, v in normalized_threats.items()
    }

    # Only recommend ID-based followups that the current index can answer.
    # The complete static classification remains visible above for callers that
    # use it independently of AIDEFEND's current defense mappings.
    resolvable_threats = {
        framework: [
            threat_id
            for threat_id in threat_ids
            if live_threat_ids is not None
            and threat_id.strip().casefold() in live_threat_ids
        ]
        for framework, threat_ids in normalized_threats.items()
    }
    recommended_actions = _generate_recommended_actions(
        resolvable_threats,
        top_matches,
    )

    result = {
        "source": match_source,  # NEW: Indicate which tier produced the result
        "input_text_preview": text[:100] + ("..." if len(text) > 100 else ""),
        "keywords_found": [
            {
                "keyword": m["keyword"],
                "match_type": m.get("match_type", "unknown"),
                "confidence": m["confidence"]
            }
            for m in top_matches
        ],
        "normalized_threats": normalized_threats,
        "threat_details": threat_details,
        "recommended_actions": recommended_actions,
        "mapping_status": {
            "all_emitted_claims_resolvable": not unresolved_claims,
            "corpus_mapping_available": live_threat_ids is not None,
            "unresolved_claims": list(dict.fromkeys(unresolved_claims)),
            "unmapped_keywords": list(dict.fromkeys(unmapped_keywords)),
        },
    }

    logger.info(
        f"Threat classification complete (source: {match_source}): "
        f"{len(top_matches)} keywords matched, "
        f"OWASP: {len(normalized_threats['owasp'])}, "
        f"ATLAS: {len(normalized_threats['atlas'])}"
    )

    return result


def _match_threats(text: str) -> List[Dict]:
    """
    Match threats using predefined keyword dictionary.

    Simple string matching (no NLP):
    1. Lowercase text
    2. Check primary keywords
    3. Check aliases
    4. Return matches with confidence

    Args:
        text: Input text

    Returns:
        List of matched keywords with metadata
    """
    text_lower = text.lower()
    matches = []

    for keyword, threat_data in THREAT_KEYWORDS.items():
        # Check primary keyword
        if keyword in text_lower:
            matches.append({
                "keyword": keyword,
                "frameworks": threat_data["frameworks"],
                "confidence": threat_data["confidence"],
                "match_type": "primary",
                "match_specificity": len(keyword.split()),
            })
            continue

        # Check aliases
        for alias in threat_data.get("aliases", []):
            if alias.lower() in text_lower:
                matches.append({
                    "keyword": keyword,
                    "frameworks": threat_data["frameworks"],
                    "confidence": threat_data["confidence"] * 0.9,  # Reduce confidence for alias matches
                    "match_type": "alias",
                    "matched_alias": alias,
                    "match_specificity": len(alias.split()),
                })
                break

    # Prefer the most specific matched phrase. Without this, a shorter, broad
    # phrase such as "compromised agent" can hide the canonical
    # "compromised agent registry" classification when top_k is small.
    matches.sort(
        key=lambda x: (x.get("match_specificity", 0), x["confidence"]),
        reverse=True,
    )

    return matches


def _generate_recommended_actions(
    normalized_threats: Dict[str, List[str]],
    top_matches: List[Dict]
) -> List[Dict]:
    """
    Generate recommended followup tool calls.

    Suggests:
    1. get_defenses_for_threat for each normalized threat
    2. get_quick_reference for primary keywords

    Args:
        normalized_threats: Dict of {framework -> [threat_ids]}
        top_matches: List of matched keywords

    Returns:
        List of recommended tool calls
    """
    actions = []

    # Recommend get_defenses_for_threat for each threat
    all_threat_ids = []
    for framework, threat_ids in normalized_threats.items():
        all_threat_ids.extend(threat_ids)

    # Deduplicate and limit to top 3 threats
    unique_threats = list(dict.fromkeys(all_threat_ids))[:3]

    for threat_id in unique_threats:
        actions.append({
            "tool": "get_defenses_for_threat",
            "args": {"threat_id": threat_id},
            "reason": f"Find defense techniques for {threat_id}"
        })

    # Recommend get_quick_reference for top matched keyword
    if top_matches:
        top_keyword = top_matches[0]["keyword"]
        actions.append({
            "tool": "get_quick_reference",
            "args": {"topic": top_keyword, "max_items": 10},
            "reason": f"Get actionable mitigation steps for {top_keyword}"
        })

    return actions


def _fuzzy_match_threats(text: str) -> List[Dict]:
    """
    Enhanced Tier 2: Fuzzy string matching with RapidFuzz (10-100x faster than difflib).

    Uses multiple fuzzy matching strategies:
    - Token set ratio: Word order doesn't matter
    - Partial ratio: Handles partial matches
    - Full text ratio: Complete text similarity

    FREE - Zero cost, no API calls, 100% local.

    Args:
        text: Input text

    Returns:
        List of matched keywords with fuzzy confidence scores

    Examples:
        "federrated learning attack" → matches "federated learning" (typo)
        "algo bias detected" → matches "algorithmic bias" (abbreviation)
        "jailbreak attempt" → matches "prompt injection" (via alias)
    """
    text_lower = text.lower()
    matches = []
    cutoff_score = settings.FUZZY_MATCH_CUTOFF * 100  # RapidFuzz uses 0-100 scale

    # Get all keywords from dictionary
    all_keywords = list(THREAT_KEYWORDS.keys())

    # Strategy 1: Full text matching against all keywords (good for multi-word)
    # Uses token_set_ratio which ignores word order
    full_text_matches = process.extract(
        text_lower,
        all_keywords,
        scorer=fuzz.token_set_ratio,
        limit=5,
        score_cutoff=cutoff_score
    )

    for matched_keyword, score, _ in full_text_matches:
        similarity = score / 100.0  # Convert back to 0-1 scale
        matches.append({
            "keyword": matched_keyword,
            "frameworks": THREAT_KEYWORDS[matched_keyword]["frameworks"],
            "confidence": THREAT_KEYWORDS[matched_keyword]["confidence"] * similarity,
            "match_type": "fuzzy_full",
            "similarity": similarity
        })

    # Strategy 2: Token-level matching (good for single words and abbreviations)
    text_tokens = text_lower.replace(",", " ").replace(".", " ").split()

    for token in text_tokens:
        if len(token) < 3:  # Skip very short tokens
            continue

        # Use process.extract for efficient batch matching
        token_matches = process.extract(
            token,
            all_keywords,
            scorer=fuzz.ratio,
            limit=3,
            score_cutoff=cutoff_score
        )

        for matched_keyword, score, _ in token_matches:
            similarity = score / 100.0

            # Avoid duplicates
            if not any(m["keyword"] == matched_keyword for m in matches):
                matches.append({
                    "keyword": matched_keyword,
                    "frameworks": THREAT_KEYWORDS[matched_keyword]["frameworks"],
                    "confidence": THREAT_KEYWORDS[matched_keyword]["confidence"] * similarity,
                    "match_type": "fuzzy_token",
                    "similarity": similarity
                })

    # Strategy 3: Partial matching for phrases (good for "X in Y" patterns)
    partial_matches = process.extract(
        text_lower,
        all_keywords,
        scorer=fuzz.partial_ratio,
        limit=3,
        score_cutoff=cutoff_score
    )

    for matched_keyword, score, _ in partial_matches:
        similarity = score / 100.0

        # Avoid duplicates
        if not any(m["keyword"] == matched_keyword for m in matches):
            matches.append({
                "keyword": matched_keyword,
                "frameworks": THREAT_KEYWORDS[matched_keyword]["frameworks"],
                "confidence": THREAT_KEYWORDS[matched_keyword]["confidence"] * similarity,
                "match_type": "fuzzy_partial",
                "similarity": similarity
            })

    # Sort by confidence (descending)
    matches.sort(key=lambda x: x["confidence"], reverse=True)

    logger.debug(f"Enhanced fuzzy matching found {len(matches)} potential matches (RapidFuzz)")
    return matches
