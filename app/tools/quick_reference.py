"""
Quick Reference Tool for AIDEFEND MCP Service

Generates quick reference guides for specific security topics.
"""

import asyncio
from typing import Dict, Any, List, Optional
from fastembed import TextEmbedding

from app.logger import get_logger
from app.config import settings
from app.security import InputValidationError

logger = get_logger(__name__)


async def get_quick_reference(
    topic: str,
    format: str = "checklist",
    max_items: int = 10
) -> Dict[str, Any]:
    """
    Generate a quick reference guide for a specific security topic.

    Provides a concise, actionable list of defense techniques organized by
    priority (quick wins, must-haves, nice-to-haves).

    Args:
        topic: Security topic (e.g., 'prompt injection', 'RAG security', 'model hardening')
        format: Output format ('checklist', 'table', 'markdown') - default: 'checklist'
        max_items: Maximum number of items to include (5-20, default: 10)

    Returns:
        Dict containing quick reference guide organized by priority

    Raises:
        InputValidationError: If inputs are invalid
        Exception: If generation fails

    Example:
        >>> ref = await get_quick_reference(
        ...     topic="prompt injection defense",
        ...     format="checklist",
        ...     max_items=10
        ... )
        >>> print(f"Quick wins: {len(ref['quick_wins'])}")
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
    if not topic or not isinstance(topic, str):
        raise InputValidationError("topic must be a non-empty string")

    topic = topic.strip()

    if len(topic) < 3:
        raise InputValidationError("topic must be at least 3 characters")

    if len(topic) > 200:
        raise InputValidationError("topic too long (max 200 characters)")

    if format not in ["checklist", "table", "markdown"]:
        raise InputValidationError("format must be 'checklist', 'table', or 'markdown'")

    if max_items < 5 or max_items > 20:
        raise InputValidationError("max_items must be between 5 and 20")

    logger.info(f"Generating quick reference for topic: {topic}")

    try:
        # Connect to LanceDB
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

        # Semantic search for relevant techniques
        logger.info("Performing semantic search...")
        model = await asyncio.to_thread(TextEmbedding, model_name=settings.EMBEDDING_MODEL)
        query_embedding = list(await asyncio.to_thread(model.embed, [topic]))[0]

        # Search for relevant techniques
        search_results = await asyncio.to_thread(
            lambda: table.search(query_embedding.tolist()).where(
                "type = 'technique'"
            ).limit(max_items * 2).to_pandas().to_dict('records')
        )

        logger.info(f"Found {len(search_results)} relevant techniques")

        # Categorize by priority
        categorized = _categorize_techniques(search_results, topic)

        # Format output
        if format == "checklist":
            output = _format_as_checklist(categorized)
        elif format == "table":
            output = _format_as_table(categorized)
        else:  # markdown
            output = _format_as_markdown(categorized)

        result = {
            "topic": topic,
            "format": format,
            "generated_at": _get_timestamp(),
            "quick_wins": categorized["quick_wins"],
            "must_haves": categorized["must_haves"],
            "nice_to_haves": categorized["nice_to_haves"],
            "formatted_output": output,
            "total_items": len(categorized["quick_wins"]) + len(categorized["must_haves"]) + len(categorized["nice_to_haves"]),
            "usage_notes": {
                "quick_wins": "Low effort, high impact - implement first",
                "must_haves": "Essential defenses - prioritize after quick wins",
                "nice_to_haves": "Additional depth - implement when foundational defenses are in place"
            }
        }

        logger.info(
            f"Quick reference generated: {result['total_items']} items",
            extra={
                "quick_wins": len(categorized["quick_wins"]),
                "must_haves": len(categorized["must_haves"]),
                "nice_to_haves": len(categorized["nice_to_haves"])
            }
        )

        return result

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to generate quick reference: {e}", exc_info=True)
        raise


def _categorize_techniques(
    techniques: List[Dict[str, Any]],
    topic: str
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Categorize techniques into quick wins, must-haves, and nice-to-haves.

    Uses heuristics based on:
    - Tactic (Detect/Harden are higher priority)
    - Name patterns (validation, baseline are low effort)
    - Relevance score
    """
    quick_wins = []
    must_haves = []
    nice_to_haves = []

    for i, tech in enumerate(techniques[:15]):  # Limit to top 15
        tech_info = {
            "priority": i + 1,
            "technique_id": tech.get('source_id'),
            "name": tech.get('name'),
            "tactic": tech.get('tactic'),
            "description": tech.get('text', '')[:200],  # Truncate
            "estimated_effort": _estimate_effort(tech),
            "estimated_impact": _estimate_impact(tech, topic)
        }

        # Categorization logic
        effort = tech_info["estimated_effort"]
        impact = tech_info["estimated_impact"]

        if effort == "Low" and impact in ["High", "Critical"]:
            quick_wins.append(tech_info)
        elif impact in ["High", "Critical"]:
            must_haves.append(tech_info)
        else:
            nice_to_haves.append(tech_info)

    # Limit each category
    return {
        "quick_wins": quick_wins[:3],
        "must_haves": must_haves[:5],
        "nice_to_haves": nice_to_haves[:2]
    }


def _estimate_effort(technique: Dict[str, Any]) -> str:
    """Estimate implementation effort: Low, Medium, High."""
    name_lower = technique.get('name', '').lower()
    tactic = technique.get('tactic', '')

    # Low effort indicators
    low_effort_keywords = ['validation', 'policy', 'baseline', 'documentation', 'logging']
    if any(kw in name_lower for kw in low_effort_keywords):
        return "Low"

    # High effort indicators
    high_effort_keywords = ['training', 'retraining', 'federated', 'cryptographic', 'formal']
    if any(kw in name_lower for kw in high_effort_keywords):
        return "High"

    # Tactic-based estimation
    if tactic in ['Model', 'Restore']:
        return "High"
    elif tactic in ['Harden', 'Detect']:
        return "Medium"

    return "Medium"


def _estimate_impact(technique: Dict[str, Any], topic: str) -> str:
    """Estimate security impact: Low, Medium, High, Critical."""
    name_lower = technique.get('name', '').lower()
    topic_lower = topic.lower()

    # Check relevance to topic
    if any(word in name_lower for word in topic_lower.split()):
        return "High"

    # Tactic-based impact
    tactic = technique.get('tactic', '')
    if tactic in ['Detect', 'Harden']:
        return "High"
    elif tactic in ['Model', 'Isolate']:
        return "Medium"

    return "Medium"


def _format_as_checklist(categorized: Dict[str, List[Dict[str, Any]]]) -> str:
    """Format as plain text checklist."""
    output = []

    output.append("# QUICK WINS (Low Effort, High Impact)")
    for item in categorized["quick_wins"]:
        output.append(f"[ ] {item['technique_id']}: {item['name']}")
        output.append(f"    Effort: {item['estimated_effort']} | Impact: {item['estimated_impact']}")
        output.append("")

    output.append("# MUST-HAVES (Essential Defenses)")
    for item in categorized["must_haves"]:
        output.append(f"[ ] {item['technique_id']}: {item['name']}")
        output.append(f"    Effort: {item['estimated_effort']} | Impact: {item['estimated_impact']}")
        output.append("")

    output.append("# NICE-TO-HAVES (Additional Depth)")
    for item in categorized["nice_to_haves"]:
        output.append(f"[ ] {item['technique_id']}: {item['name']}")
        output.append(f"    Effort: {item['estimated_effort']} | Impact: {item['estimated_impact']}")
        output.append("")

    return "\n".join(output)


def _format_as_table(categorized: Dict[str, List[Dict[str, Any]]]) -> str:
    """Format as markdown table."""
    output = []

    output.append("| Priority | ID | Name | Tactic | Effort | Impact |")
    output.append("|----------|-------|------|--------|--------|--------|")

    for item in categorized["quick_wins"]:
        output.append(
            f"| QUICK WIN | {item['technique_id']} | {item['name'][:30]} | "
            f"{item['tactic']} | {item['estimated_effort']} | {item['estimated_impact']} |"
        )

    for item in categorized["must_haves"]:
        output.append(
            f"| MUST-HAVE | {item['technique_id']} | {item['name'][:30]} | "
            f"{item['tactic']} | {item['estimated_effort']} | {item['estimated_impact']} |"
        )

    for item in categorized["nice_to_haves"]:
        output.append(
            f"| NICE-TO-HAVE | {item['technique_id']} | {item['name'][:30]} | "
            f"{item['tactic']} | {item['estimated_effort']} | {item['estimated_impact']} |"
        )

    return "\n".join(output)


def _format_as_markdown(categorized: Dict[str, List[Dict[str, Any]]]) -> str:
    """Format as markdown document."""
    output = []

    output.append("## Quick Wins (Implement First)")
    for item in categorized["quick_wins"]:
        output.append(f"### {item['technique_id']}: {item['name']}")
        output.append(f"- **Tactic:** {item['tactic']}")
        output.append(f"- **Effort:** {item['estimated_effort']}")
        output.append(f"- **Impact:** {item['estimated_impact']}")
        output.append("")

    output.append("## Must-Haves (Essential Defenses)")
    for item in categorized["must_haves"]:
        output.append(f"### {item['technique_id']}: {item['name']}")
        output.append(f"- **Tactic:** {item['tactic']}")
        output.append(f"- **Effort:** {item['estimated_effort']}")
        output.append(f"- **Impact:** {item['estimated_impact']}")
        output.append("")

    output.append("## Nice-to-Haves (Additional Depth)")
    for item in categorized["nice_to_haves"]:
        output.append(f"### {item['technique_id']}: {item['name']}")
        output.append(f"- **Tactic:** {item['tactic']}")
        output.append(f"- **Effort:** {item['estimated_effort']}")
        output.append(f"- **Impact:** {item['estimated_impact']}")
        output.append("")

    return "\n".join(output)


def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"
