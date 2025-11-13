"""
Classify Threat Tool for AIDEFEND MCP Service

Maps threat keywords from unstructured text to standard framework IDs
(OWASP LLM Top 10, MITRE ATLAS, MAESTRO) using simple keyword matching.

NOTE: This tool uses ONLY static keyword dictionary matching.
NO NLP, NO embedding, NO auto-chain.
LLM handles text understanding; this tool provides standardized mappings.
"""

from typing import Dict, Any, List, Optional
import difflib
from app.logger import get_logger
from app.security import InputValidationError
from app.threat_keywords import THREAT_KEYWORDS, normalize_threat_keyword
from app.config import settings

logger = get_logger(__name__)


async def classify_threat(text: str, top_k: int = 5) -> Dict[str, Any]:
    """
    Classify threats in text using keyword matching with static dictionary.

    This function:
    1. Normalizes input text (lowercase)
    2. Matches against predefined keyword dictionary
    3. Returns normalized threat IDs + recommended tool calls

    NO text understanding (let LLM do that).
    NO auto-chain (let LLM orchestrate).

    Args:
        text: Input text containing threat-related content
        top_k: Maximum number of keywords to return (1-10)

    Returns:
        Dict containing:
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

    if top_k < 1 or top_k > 10:
        raise InputValidationError("top_k must be between 1 and 10")

    logger.info(f"Classifying threats in text ({len(text)} chars)")

    # === TIER 1: Static Keyword Matching ===
    matches = _match_threats(text)
    match_source = "static_keyword"

    # If static match has high confidence, use it
    if matches and matches[0]["confidence"] >= settings.LLM_FALLBACK_THRESHOLD:
        logger.info(f"Static keyword match found (confidence: {matches[0]['confidence']:.2f})")

    # === TIER 2: Fuzzy Matching (if enabled and no high-confidence static match) ===
    elif settings.ENABLE_FUZZY_MATCHING and (not matches or matches[0]["confidence"] < settings.LLM_FALLBACK_THRESHOLD):
        logger.info("Attempting fuzzy matching for typo tolerance...")
        fuzzy_matches = _fuzzy_match_threats(text)
        if fuzzy_matches and fuzzy_matches[0]["confidence"] >= settings.FUZZY_MATCH_CUTOFF:
            matches = fuzzy_matches
            match_source = "fuzzy_match"
            logger.info(f"Fuzzy match found (confidence: {matches[0]['confidence']:.2f})")

    # === TIER 3: LLM Semantic Inference (if enabled and no high-confidence match) ===
    if settings.ENABLE_LLM_FALLBACK and (not matches or matches[0]["confidence"] < settings.LLM_FALLBACK_THRESHOLD):
        if settings.ANTHROPIC_API_KEY:
            logger.info("Attempting LLM semantic inference...")
            llm_matches = await _llm_semantic_inference(text)
            if llm_matches:
                matches = llm_matches
                match_source = "llm_inferred"
                logger.info(f"LLM semantic inference completed ({len(llm_matches)} threats found)")
        else:
            logger.warning("LLM fallback enabled but ANTHROPIC_API_KEY not configured")

    # If still no matches, set source to no_match
    if not matches:
        match_source = "no_match"
        logger.info("No threat matches found across all tiers")

    # Limit to top_k
    top_matches = matches[:top_k]

    # Aggregate normalized threat IDs
    normalized_threats = {"owasp": set(), "atlas": set(), "maestro": set()}
    threat_details = []

    for match in top_matches:
        keyword = match["keyword"]
        frameworks = match["frameworks"]
        confidence = match["confidence"]
        match_type = match.get("match_type", "unknown")

        # Add to normalized_threats
        for framework, threat_ids in frameworks.items():
            normalized_threats[framework].update(threat_ids)

        # Build threat_details
        for framework, threat_ids in frameworks.items():
            for threat_id in threat_ids:
                threat_details.append({
                    "threat_id": f"{framework.upper()}-{threat_id}",
                    "threat_name": keyword.title(),
                    "confidence": confidence,
                    "matched_keyword": keyword,
                    "match_type": match_type
                })

    # Convert sets to sorted lists
    normalized_threats = {
        k: sorted(list(v)) for k, v in normalized_threats.items()
    }

    # Generate recommended actions
    recommended_actions = _generate_recommended_actions(normalized_threats, top_matches)

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
        "recommended_actions": recommended_actions
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
                "match_type": "primary"
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
                    "matched_alias": alias
                })
                break

    # Sort by confidence (descending)
    matches.sort(key=lambda x: x["confidence"], reverse=True)

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
    Phase 1: Fuzzy string matching for typo tolerance.

    Uses difflib.get_close_matches() to find similar keywords.
    FREE - Zero cost, no API calls.

    Args:
        text: Input text

    Returns:
        List of matched keywords with fuzzy confidence scores

    Examples:
        "federrated learning attack" → matches "federated learning"
        "algo bias" → matches "algorithmic bias"
    """
    text_lower = text.lower()
    matches = []

    # Extract potential keywords from text (split by spaces and common separators)
    text_tokens = text_lower.replace(",", " ").replace(".", " ").split()

    # Get all keywords from dictionary
    all_keywords = list(THREAT_KEYWORDS.keys())

    # Try to match multi-word keywords first (more specific)
    for keyword in all_keywords:
        keyword_tokens = keyword.split()
        if len(keyword_tokens) > 1:
            # For multi-word keywords, use get_close_matches on the full phrase
            close_matches = difflib.get_close_matches(
                keyword,
                [text_lower],
                n=1,
                cutoff=settings.FUZZY_MATCH_CUTOFF
            )
            if close_matches:
                similarity = difflib.SequenceMatcher(None, keyword, text_lower).ratio()
                matches.append({
                    "keyword": keyword,
                    "frameworks": THREAT_KEYWORDS[keyword]["frameworks"],
                    "confidence": THREAT_KEYWORDS[keyword]["confidence"] * similarity,
                    "match_type": "fuzzy",
                    "similarity": similarity
                })

    # Try single-word keyword matching
    for token in text_tokens:
        if len(token) < 3:  # Skip very short tokens
            continue

        close_matches = difflib.get_close_matches(
            token,
            all_keywords,
            n=3,
            cutoff=settings.FUZZY_MATCH_CUTOFF
        )

        for matched_keyword in close_matches:
            # Calculate similarity score
            similarity = difflib.SequenceMatcher(None, token, matched_keyword).ratio()

            # Avoid duplicates
            if not any(m["keyword"] == matched_keyword for m in matches):
                matches.append({
                    "keyword": matched_keyword,
                    "frameworks": THREAT_KEYWORDS[matched_keyword]["frameworks"],
                    "confidence": THREAT_KEYWORDS[matched_keyword]["confidence"] * similarity,
                    "match_type": "fuzzy",
                    "similarity": similarity
                })

    # Sort by confidence (descending)
    matches.sort(key=lambda x: x["confidence"], reverse=True)

    logger.debug(f"Fuzzy matching found {len(matches)} potential matches")
    return matches


async def _llm_semantic_inference(text: str) -> List[Dict]:
    """
    Phase 2: LLM semantic inference fallback using Anthropic Claude.

    When static + fuzzy matching fails, use Claude to understand
    the semantic meaning and map to threat frameworks.

    USER-PAYS: Requires user's ANTHROPIC_API_KEY.
    Cost: ~$0.0001-0.0003 per classification.

    Args:
        text: Input text describing potential threat

    Returns:
        List of inferred threat keywords with confidence scores

    Example:
        Input: "Users are tricking the AI into ignoring safety rules"
        Output: [{"keyword": "prompt injection", "confidence": 0.85, ...}]
    """
    try:
        # Import here to make it optional (only needed if LLM fallback enabled)
        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Build prompt for Claude
        prompt = f"""You are an AI security expert. Analyze the following text and identify which AI/ML security threats it describes.

Text to analyze:
"{text}"

Available threat keywords (choose from these):
{', '.join(list(THREAT_KEYWORDS.keys())[:30])}...

Instructions:
1. Identify 1-3 most relevant threat keywords from the list above
2. Provide confidence score (0.0-1.0) for each
3. Return ONLY valid JSON array format:

[
  {{"keyword": "threat_keyword", "confidence": 0.85}},
  ...
]

If no threats detected, return empty array: []"""

        # Call Claude API
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=settings.CLAUDE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse response
        response_text = response.content[0].text.strip()

        # Extract JSON (handle potential markdown formatting)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        # Parse JSON
        import json
        inferred_threats = json.loads(response_text)

        # Validate and build matches
        matches = []
        for threat in inferred_threats:
            keyword = threat.get("keyword", "").lower()
            confidence = threat.get("confidence", 0.5)

            # Validate keyword exists in our dictionary
            if keyword in THREAT_KEYWORDS:
                matches.append({
                    "keyword": keyword,
                    "frameworks": THREAT_KEYWORDS[keyword]["frameworks"],
                    "confidence": min(confidence, 0.90),  # Cap LLM confidence at 0.90
                    "match_type": "llm_inferred"
                })
            else:
                logger.warning(f"LLM suggested unknown keyword: {keyword}")

        logger.info(f"LLM semantic inference returned {len(matches)} threats")
        return matches

    except ImportError:
        logger.error("anthropic package not installed. Install with: pip install anthropic")
        return []
    except Exception as e:
        logger.error(f"LLM semantic inference failed: {str(e)}")
        return []
