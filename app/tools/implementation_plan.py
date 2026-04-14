"""
Implementation Plan Tool for AIDEFEND MCP Service

Recommends next defense techniques to implement based on heuristic scoring.
Uses existing database fields only - NO LLM inference.

Scoring dimensions:
1. Threat importance (defends_against contains high-risk threats)
2. Ease of implementation (tools_opensource availability)
3. Phase weight (earlier phases = lower cost)
4. Pillar weight (prevention > detection > response)
5. Tool ecosystem maturity (tools_commercial availability)
"""

import asyncio
import html  # For HTML entity unescaping
import json
import re    # For fallback HTML parsing
import lancedb

from app.security import sanitize_technique_id


def _safe_json_loads(value, default=None):
    """Safely parse a JSON string or return the value if already parsed."""
    if default is None:
        default = []
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return default
    return default
from typing import Dict, Any, List, Set, Optional
from collections import defaultdict
from bs4 import BeautifulSoup  # Robust HTML parsing for Compound Tool optimization

from app.logger import get_logger
from app.config import settings
from app.security import InputValidationError
from app.framework_utils import is_actionable_record

logger = get_logger(__name__)

# High-risk threat patterns (for threat importance scoring)
HIGH_RISK_PATTERNS = [
    'LLM01', 'LLM03',  # Prompt injection, Training data poisoning
    'POISON', 'EXFIL',  # Poisoning, Exfiltration
    'T0020', 'T0043',   # ATLAS poisoning, adversarial examples
    'BACKDOOR', 'JAILBREAK'
]


# ============================================================================
# HTML Parsing Helpers (for Compound Tool optimization)
# ============================================================================

def _strip_html(text: str) -> str:
    """
    Fallback regex-based HTML tag stripper.

    Used when BeautifulSoup parsing fails to provide a basic text extraction.

    Args:
        text: HTML text to strip

    Returns:
        Plain text with HTML tags removed and whitespace normalized
    """
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', ' ', str(text))
    # Normalize whitespace
    return ' '.join(clean.split())


def _extract_strategy_details(
    html_text: str,
    include_code: bool = False,
    summary_length: Optional[int] = None
) -> Dict[str, Any]:
    """
    Robustly extract summary and code snippets from HTML using BeautifulSoup.

    Implements defense-in-depth error handling:
    1. Try BeautifulSoup parsing (removes script/style tags)
    2. Fallback to regex stripper (_strip_html)
    3. Final fallback to error message

    This function is designed to handle AIDEFEND's diverse HTML/Markdown content,
    including various tag structures, nested elements, and code blocks.

    Args:
        html_text: Raw HTML content from database (may include markdown-style tags)
        include_code: Whether to extract code blocks (False for "standard", True for "detailed")
        summary_length: Custom summary length (defaults: 500 with code, 200 without)

    Returns:
        Dictionary containing:
            - 'summary' (str): Clean text summary, length-limited
            - 'code_snippets' (List[Dict], optional): Code blocks with 'language' and 'code'
            - 'code_snippet_count' (int, optional): Number of code blocks found

    Example:
        >>> details = _extract_strategy_details("<p>Validate inputs</p>", include_code=False)
        >>> print(details['summary'])
        'Validate inputs'
    """
    if not html_text:
        return {"summary": "", "code_snippets": []}

    try:
        soup = BeautifulSoup(html_text, 'html.parser')

        # Security: Remove script and style elements that might add noise
        for tag in soup(['script', 'style']):
            tag.decompose()

        # Extract clean text with separator to prevent word merging
        text_content = soup.get_text(separator=' ', strip=True)

        # Determine summary length based on mode
        if summary_length is None:
            summary_length = 500 if include_code else 200

        summary = text_content[:summary_length] + "..." if len(text_content) > summary_length else text_content
        result = {"summary": summary}

        # Extract code blocks if requested (only in "detailed" mode)
        if include_code:
            code_blocks = []
            for pre in soup.find_all('pre'):
                code_tag = pre.find('code')
                if code_tag:
                    # Extract language from class attribute (e.g., class="language-python")
                    lang = "plaintext"
                    classes = code_tag.get('class', [])
                    for cls in classes:
                        if isinstance(cls, str) and cls.startswith('language-'):
                            lang = cls.replace('language-', '')
                            break

                    # BeautifulSoup's get_text() automatically handles HTML entity unescaping
                    code_content = code_tag.get_text().strip()

                    if code_content:
                        code_blocks.append({
                            "language": lang,
                            "code": code_content
                        })

            if code_blocks:
                result["code_snippets"] = code_blocks
                result["code_snippet_count"] = len(code_blocks)

        return result

    except Exception as e:
        # Level 1 Fallback: Regex stripper
        logger.warning(f"BeautifulSoup parsing failed: {e}. Using regex fallback.")
        try:
            fallback_text = _strip_html(html_text)
            limit = summary_length if summary_length else 200
            return {"summary": fallback_text[:limit] + "..." if len(fallback_text) > limit else fallback_text}
        except Exception:
            # Level 2 Fallback: Ultimate safety net
            return {"summary": "[Error: Unable to parse content]"}


async def get_implementation_plan(
    implemented_techniques: Optional[List[str]] = None,
    exclude_tactics: Optional[List[str]] = None,
    top_k: int = 10,
    detail_level: str = "basic"
) -> Dict[str, Any]:
    """
    Recommend next techniques to implement based on heuristic scoring.

    This function uses ONLY existing database fields for scoring:
    - defends_against: High-risk threat coverage
    - tools_opensource/tools_commercial: Implementation ease
    - phase: Development stage (Design = easier than Runtime)
    - pillar: Defense layer (Prevent > Detect > Respond)

    NO LLM inference is used. All scoring is heuristic.

    Compound Tool Pattern (detail_level parameter):
    - "basic": Returns technique IDs and scores only (fastest, original behavior)
    - "standard": Returns brief summaries (200 chars) for top 5 techniques (recommended)
    - "detailed": Returns full summaries (500 chars) for top 5 techniques

    Strategy Querying:
    - Uses union logic to query BOTH parent-level and sub-technique-level strategies
    - Adds context_source field for strategies from sub-techniques
    - NEVER includes code snippets automatically (use get_secure_code_snippet separately)

    Args:
        implemented_techniques: List of already implemented technique IDs
        exclude_tactics: List of tactics to exclude (e.g., ["Model", "Harden"])
        top_k: Number of recommendations to return (1-20)
        detail_level: Level of detail ("basic", "standard", "detailed")

    Returns:
        Dict containing:
        - input: Summary of input parameters
        - recommendations: List of recommended techniques with scores
        - categories: Bucketed recommendations (quick_wins, high_priority, standard)
        - actionable_strategies (optional): Strategy summaries for top 5 (if detail_level != "basic")
          Each strategy may include context_source field if from sub-technique

    Raises:
        InputValidationError: If input validation fails
        Exception: If database query fails

    Example:
        >>> # Basic mode (original behavior)
        >>> result = await get_implementation_plan(
        ...     implemented_techniques=["AID-D-001"],
        ...     top_k=10
        ... )
        >>> print(result['recommendations'][0]['technique_id'])
        'AID-D-014'

        >>> # Standard mode (recommended - fast with summaries)
        >>> result = await get_implementation_plan(
        ...     implemented_techniques=["AID-D-001"],
        ...     top_k=10,
        ...     detail_level="standard"
        ... )
        >>> print(result['actionable_strategies'][0]['strategies'][0]['summary'])
        'Implement input validation...'
        >>> # For code examples, use get_secure_code_snippet() separately
    """
    from app.core import query_engine
    from app.exceptions import QueryEngineNotInitializedError

    # Pre-flight check: ensure query engine is ready
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please run 'sync_aidefend' first to download the knowledge base."
        )

    # Input validation
    if implemented_techniques is None:
        implemented_techniques = []

    if exclude_tactics is None:
        exclude_tactics = []

    if not isinstance(implemented_techniques, list):
        raise InputValidationError("implemented_techniques must be a list")

    if not isinstance(exclude_tactics, list):
        raise InputValidationError("exclude_tactics must be a list")

    if top_k < 1 or top_k > 20:
        raise InputValidationError("top_k must be between 1 and 20")

    if detail_level not in ["basic", "standard", "detailed"]:
        raise InputValidationError("detail_level must be 'basic', 'standard', or 'detailed'")

    # Normalize inputs
    implemented_set = set(tid.strip().upper() for tid in implemented_techniques)
    exclude_tactics_set = set(tactic.strip().title() for tactic in exclude_tactics)

    logger.info(
        f"Generating implementation plan: "
        f"{len(implemented_set)} implemented, "
        f"{len(exclude_tactics_set)} tactics excluded, "
        f"top_k={top_k}"
    )

    try:
        # Connect to LanceDB
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

        # Get all technique-like records, then keep directly implementable items
        # only (standalone techniques + sub-techniques).
        all_techniques = await asyncio.to_thread(
            lambda: table.search().where(
                "type = 'technique' OR type = 'subtechnique'"
            ).to_pandas().to_dict('records')
        )
        all_techniques = [tech for tech in all_techniques if is_actionable_record(tech)]

        logger.info(f"Retrieved {len(all_techniques)} actionable techniques")

        # Filter: exclude already implemented and excluded tactics
        candidate_techniques = []
        for tech in all_techniques:
            tech_id = tech.get('source_id', '')
            tactic = tech.get('tactic', '')

            # Skip if already implemented
            if tech_id in implemented_set:
                continue

            # Skip if tactic is excluded
            if tactic in exclude_tactics_set:
                continue

            candidate_techniques.append(tech)

        logger.info(f"Filtered to {len(candidate_techniques)} candidate techniques")

        # Score each candidate technique
        scored_techniques = []
        for tech in candidate_techniques:
            score, breakdown = _calculate_recommendation_score(tech)

            scored_techniques.append({
                "technique": tech,
                "score": score,
                "score_breakdown": breakdown
            })

        # Sort by score (descending)
        scored_techniques.sort(key=lambda x: x["score"], reverse=True)

        # Take top_k
        top_recommendations = scored_techniques[:top_k]

        # Build recommendations list
        recommendations = []
        for i, item in enumerate(top_recommendations, 1):
            tech = item["technique"]
            score = item["score"]
            breakdown = item["score_breakdown"]

            # Generate reasoning text
            reasoning = _generate_reasoning(tech, breakdown)

            # Check if has opensource tools
            tools_opensource = _safe_json_loads(tech.get('tools_opensource', '[]'))
            has_opensource_tools = bool(tools_opensource)

            recommendations.append({
                "rank": i,
                "technique_id": tech.get('source_id'),
                "technique_name": tech.get('name'),
                "tactic": tech.get('tactic'),
                "score": round(score, 2),
                "score_breakdown": breakdown,
                "reasoning": reasoning,
                "has_opensource_tools": has_opensource_tools,
                "pillar": tech.get('pillar', ''),
                "phase": tech.get('phase', '')
            })

        # Categorize recommendations
        categories = _categorize_recommendations(scored_techniques[:top_k])

        # Compound Tool Pattern: Proactively fetch detailed implementation guidance
        # This eliminates N+1 query problem by returning actionable strategies upfront
        actionable_strategies = None
        if detail_level in ["standard", "detailed"]:
            actionable_strategies = []

            # Process top 5 recommendations only (balance between detail and performance)
            top_5_items = top_recommendations[:min(5, len(top_recommendations))]

            for item in top_5_items:
                tech = item["technique"]
                tech_id = tech.get('source_id')
                tech_name = tech.get('name')

                try:
                    # Strategy Storage Model:
                    # - Strategies are stored in the 'implementation_guidance' field (JSON string)
                    # - Parent techniques: strategies in technique.implementation_guidance
                    # - Techniques with subtechniques: strategies in subtechnique.implementation_guidance

                    strategy_details = []

                    # Defense-in-depth: sanitize tech_id even though it comes from DB
                    sanitized_tid = sanitize_technique_id(tech_id) if tech_id else None

                    if not sanitized_tid:
                        logger.warning(f"Skipping strategy fetch for invalid technique ID: {tech_id}")
                        continue

                    # Step 1: Check for subtechniques
                    sub_techniques = await asyncio.to_thread(
                        lambda tid=sanitized_tid: table.search()
                        .where(f"type = 'subtechnique' AND parent_technique_id = '{tid}'")
                        .limit(5)  # Get up to 5 subtechniques
                        .to_pandas()
                        .to_dict('records')
                    )

                    if sub_techniques:
                        # Technique has subtechniques - extract strategies from each subtechnique
                        for sub_tech in sub_techniques:
                            sub_tech_name = sub_tech.get('name', '')
                            impl_strat_raw = sub_tech.get('implementation_guidance', '')

                            # Parse embedded strategies (stored as JSON string)
                            if isinstance(impl_strat_raw, str) and impl_strat_raw:
                                try:
                                    strategies = json.loads(impl_strat_raw)
                                    if isinstance(strategies, list):
                                        for strat in strategies:
                                            strategy_name = strat.get('implementation', '')
                                            how_to_html = strat.get('howTo', '')

                                            # NEVER include code automatically
                                            include_code = False

                                            # Set summary length based on detail_level
                                            summary_length = 200 if detail_level == "standard" else 500

                                            # Extract summary from howTo HTML
                                            extracted = _extract_strategy_details(
                                                how_to_html,
                                                include_code=include_code,
                                                summary_length=summary_length
                                            )

                                            strategy_entry = {
                                                "strategy_name": strategy_name,
                                                "summary": extracted.get("summary", ""),
                                                "context_source": sub_tech_name  # Label which subtechnique this came from
                                            }

                                            strategy_details.append(strategy_entry)

                                except json.JSONDecodeError as e:
                                    logger.warning(f"Failed to parse strategies for {sub_tech.get('source_id')}: {e}")
                    else:
                        # No subtechniques - try to get strategies from parent technique
                        impl_strat_raw = tech.get('implementation_guidance', '')

                        if isinstance(impl_strat_raw, str) and impl_strat_raw:
                            try:
                                strategies = json.loads(impl_strat_raw)
                                if isinstance(strategies, list):
                                    for strat in strategies:
                                        strategy_name = strat.get('implementation', '')
                                        how_to_html = strat.get('howTo', '')

                                        # NEVER include code automatically
                                        include_code = False

                                        # Set summary length based on detail_level
                                        summary_length = 200 if detail_level == "standard" else 500

                                        # Extract summary from howTo HTML
                                        extracted = _extract_strategy_details(
                                            how_to_html,
                                            include_code=include_code,
                                            summary_length=summary_length
                                        )

                                        strategy_entry = {
                                            "strategy_name": strategy_name,
                                            "summary": extracted.get("summary", "")
                                        }

                                        strategy_details.append(strategy_entry)

                            except json.JSONDecodeError as e:
                                logger.warning(f"Failed to parse strategies for {tech_id}: {e}")

                    actionable_strategies.append({
                        "technique_id": tech_id,
                        "technique_name": tech_name,
                        "strategies": strategy_details,
                        "strategy_count": len(strategy_details)
                    })

                except Exception as e:
                    # Graceful degradation: log error but continue processing other techniques
                    logger.warning(f"Failed to fetch strategies for {tech_id}: {e}")
                    actionable_strategies.append({
                        "technique_id": tech_id,
                        "technique_name": tech_name,
                        "strategies": [],
                        "strategy_count": 0,
                        "error": "Failed to fetch strategies"
                    })

        result = {
            "input": {
                "implemented_count": len(implemented_set),
                "exclude_tactics": list(exclude_tactics_set),
                "top_k": top_k,
                "detail_level": detail_level
            },
            "recommendations": recommendations,
            "categories": categories
        }

        # Add actionable_strategies only when detail_level != "basic"
        if actionable_strategies is not None:
            result["actionable_strategies"] = actionable_strategies
            result["metadata"] = {
                "compound_tool_enabled": True,
                "detail_level": detail_level,
                "strategies_fetched": len(actionable_strategies)
            }

        logger.info(
            f"Implementation plan generated: {len(recommendations)} recommendations, "
            f"{len(categories['quick_wins'])} quick wins, "
            f"{len(categories['high_priority'])} high priority"
            + (f", {len(actionable_strategies)} actionable strategies (detail_level={detail_level})" if actionable_strategies else "")
        )

        return result

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to generate implementation plan: {e}", exc_info=True)
        raise


def _calculate_recommendation_score(technique: Dict) -> tuple[float, Dict[str, float]]:
    """
    Calculate heuristic recommendation score (0-10) using only existing fields.

    Scoring dimensions (total 10 points):
    1. Threat importance (3 points): High-risk threats in defends_against
    2. Ease of implementation (2 points): tools_opensource availability
    3. Phase weight (2 points): Design > Development > Deployment > Runtime
    4. Pillar weight (2 points): Prevent > Detect > Respond
    5. Tool ecosystem (1 point): tools_commercial availability

    Args:
        technique: Technique dict from database

    Returns:
        Tuple of (total_score, breakdown_dict)
    """
    score = 0.0
    breakdown = {}

    # 1. Threat importance (0-3 points)
    defends_against = _safe_json_loads(technique.get('defends_against', '[]'))
    threat_score = 0.0

    for framework_data in defends_against:
        for item in framework_data.get('items', []):
            item_upper = item.upper()
            if any(pattern in item_upper for pattern in HIGH_RISK_PATTERNS):
                threat_score = 3.0
                break
        if threat_score > 0:
            break

    score += threat_score
    breakdown["threat_importance"] = threat_score

    # 2. Ease of implementation (0-2 points)
    tools_opensource = _safe_json_loads(technique.get('tools_opensource', '[]'))
    ease_score = 2.0 if tools_opensource else 0.0

    score += ease_score
    breakdown["ease_of_implementation"] = ease_score

    # 3. Phase weight (0-2 points)
    # Note: phase is stored as JSON array in database (e.g., ["scoping", "building"])
    phase_raw = technique.get('phase', '[]')
    if isinstance(phase_raw, str):
        try:
            phases = json.loads(phase_raw) if phase_raw.strip() else []
        except json.JSONDecodeError:
            phases = []
    elif isinstance(phase_raw, list):
        phases = phase_raw
    else:
        phases = []

    # Map actual database phase values to scores (earlier phases = higher priority)
    phase_scores = {
        'scoping': 2.0,       # Early design/planning phase
        'building': 1.5,      # Development phase
        'validation': 1.0,    # Testing/deployment phase
        'operation': 0.5,     # Runtime/production phase
        'improvement': 0.8    # Ongoing improvement
    }

    # Take the highest score from all phases this technique applies to
    phase_score = 0.0
    if isinstance(phases, list) and phases:
        phase_score = max([phase_scores.get(p, 0.0) for p in phases])

    score += phase_score
    breakdown["phase_weight"] = phase_score

    # 4. Pillar weight (0-2 points)
    # Note: pillar is stored as JSON array in database (e.g., ["data", "model", "app"])
    pillar_raw = technique.get('pillar', '[]')
    if isinstance(pillar_raw, str):
        try:
            pillars = json.loads(pillar_raw) if pillar_raw.strip() else []
        except json.JSONDecodeError:
            pillars = []
    elif isinstance(pillar_raw, list):
        pillars = pillar_raw
    else:
        pillars = []

    # Map actual database pillar values to scores (security-critical pillars = higher priority)
    pillar_scores = {
        'model': 2.0,    # Model security (highest risk)
        'data': 2.0,     # Data protection (highest risk)
        'app': 1.5,      # Application security
        'infra': 1.0     # Infrastructure security
    }

    # Take the highest score from all pillars this technique applies to
    pillar_score = 0.0
    if isinstance(pillars, list) and pillars:
        pillar_score = max([pillar_scores.get(p, 0.0) for p in pillars])

    score += pillar_score
    breakdown["pillar_weight"] = pillar_score

    # 5. Tool ecosystem maturity (0-1 point)
    tools_commercial = _safe_json_loads(technique.get('tools_commercial', '[]'))
    ecosystem_score = 1.0 if tools_commercial else 0.0

    score += ecosystem_score
    breakdown["tool_ecosystem"] = ecosystem_score

    return (score, breakdown)


def _generate_reasoning(technique: Dict, breakdown: Dict[str, float]) -> str:
    """
    Generate human-readable reasoning for recommendation.

    Args:
        technique: Technique dict
        breakdown: Score breakdown dict

    Returns:
        Reasoning text
    """
    reasons = []

    # Threat importance
    if breakdown.get("threat_importance", 0) >= 3.0:
        reasons.append("Covers high-risk threats")

    # Ease of implementation
    if breakdown.get("ease_of_implementation", 0) >= 2.0:
        reasons.append("Has open-source tools available")

    # Pillar (parse JSON array)
    pillar_raw = technique.get('pillar', '')
    try:
        pillars = json.loads(pillar_raw) if isinstance(pillar_raw, str) and pillar_raw.strip() else []
    except json.JSONDecodeError:
        pillars = []

    if isinstance(pillars, list):
        if 'model' in pillars or 'data' in pillars:
            reasons.append("Addresses critical security pillars (model/data)")
        elif 'app' in pillars:
            reasons.append("Strengthens application layer security")

    # Phase (parse JSON array)
    phase_raw = technique.get('phase', '')
    try:
        phases = json.loads(phase_raw) if isinstance(phase_raw, str) and phase_raw.strip() else []
    except json.JSONDecodeError:
        phases = []

    if isinstance(phases, list):
        if 'scoping' in phases or 'building' in phases:
            phase_str = 'scoping' if 'scoping' in phases else 'building'
            reasons.append(f"Early-stage implementation ({phase_str})")

    if not reasons:
        reasons.append("Standard priority technique")

    return "; ".join(reasons)


def _categorize_recommendations(scored_techniques: List[Dict]) -> Dict[str, List[str]]:
    """
    Categorize recommendations into quick_wins, high_priority, standard.

    Categories:
    - quick_wins: Has opensource tools AND score >= 6.0
    - high_priority: Score >= 7.0 (regardless of tools)
    - standard: Everything else

    Args:
        scored_techniques: List of scored technique dicts

    Returns:
        Dict with {category -> [technique_ids]}
    """
    quick_wins = []
    high_priority = []
    standard = []

    for item in scored_techniques:
        tech = item["technique"]
        score = item["score"]
        tech_id = tech.get('source_id')

        tools_opensource = _safe_json_loads(tech.get('tools_opensource', '[]'))
        has_tools = bool(tools_opensource)

        # Categorize
        if has_tools and score >= 6.0:
            quick_wins.append(tech_id)

        if score >= 7.0:
            high_priority.append(tech_id)
        else:
            standard.append(tech_id)

    return {
        "quick_wins": quick_wins,
        "high_priority": high_priority,
        "standard": standard
    }
