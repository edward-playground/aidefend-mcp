"""
Technique Detail Tool for AIDEFEND MCP Service

Retrieves complete information about a specific technique including all
sub-techniques, implementation strategies with code, tools, and threat mappings.
"""

import json
import asyncio
from typing import Dict, Any, List, Optional

from app.logger import get_logger
from app.config import settings
from app.security import InputValidationError

logger = get_logger(__name__)


async def get_technique_detail(
    technique_id: str,
    include_code: bool = True,
    include_tools: bool = True
) -> Dict[str, Any]:
    """
    Get complete details for a specific AIDEFEND technique ID.

    Retrieves:
    - Technique metadata and description
    - All sub-techniques
    - Implementation strategies with code examples (if requested)
    - Tool recommendations (if requested)
    - Threat framework mappings

    Args:
        technique_id: AIDEFEND technique ID (e.g., 'AID-H-001', 'AID-D-001.001')
        include_code: Include full code examples from strategies (default: True)
        include_tools: Include tool recommendations (default: True)

    Returns:
        Dict containing complete technique information with hierarchical structure

    Raises:
        InputValidationError: If technique_id is invalid
        Exception: If technique not found or database error

    Example:
        >>> detail = await get_technique_detail("AID-H-001", include_code=True)
        >>> print(f"Technique: {detail['technique']['name']}")
        >>> print(f"Sub-techniques: {len(detail['subtechniques'])}")
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
    if not technique_id or not isinstance(technique_id, str):
        raise InputValidationError("technique_id must be a non-empty string")

    technique_id = technique_id.strip().upper()

    if len(technique_id) > 50:
        raise InputValidationError("technique_id too long")

    logger.info(f"Fetching technique detail for: {technique_id}")

    try:
        # Connect to LanceDB
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))
        table = await asyncio.to_thread(db.open_table, "aidefend")

        # Step 1: Get the main technique/subtechnique
        main_doc = await asyncio.to_thread(
            lambda: table.search().where(f"source_id = '{technique_id}'").limit(1).to_pandas().to_dict('records')
        )

        if not main_doc:
            raise Exception(f"Technique ID '{technique_id}' not found in database")

        main_doc = main_doc[0]
        doc_type = main_doc.get('type')

        logger.info(f"Found {doc_type}: {main_doc.get('name')}")

        # Parse JSON fields
        defends_against = _parse_json_field(main_doc.get('defends_against', '[]'))
        tools_opensource = _parse_json_field(main_doc.get('tools_opensource', '[]'))
        tools_commercial = _parse_json_field(main_doc.get('tools_commercial', '[]'))
        impl_strategies = _parse_json_field(main_doc.get('implementation_strategies', '[]'))

        # Build main technique info
        technique_info = {
            "id": main_doc.get('source_id'),
            "name": main_doc.get('name'),
            "type": doc_type,
            "tactic": main_doc.get('tactic'),
            "pillar": main_doc.get('pillar', ''),
            "phase": main_doc.get('phase', ''),
            "description": main_doc.get('text', ''),
            "parent_technique_id": main_doc.get('parent_technique_id', '')
        }

        # Add threat mappings
        if defends_against:
            technique_info["defends_against"] = defends_against

        # Add tools if requested
        if include_tools and (tools_opensource or tools_commercial):
            technique_info["tools"] = {
                "opensource": tools_opensource,
                "commercial": tools_commercial
            }

        # Step 2: Find child elements based on type
        subtechniques = []
        strategies = []

        if doc_type == 'technique':
            # This is a parent technique - find all subtechniques
            logger.info(f"Searching for subtechniques of {technique_id}...")

            subtechniques_docs = await asyncio.to_thread(
                lambda: table.search().where(
                    f"parent_technique_id = '{technique_id}' AND type = 'subtechnique'"
                ).to_pandas().to_dict('records')
            )

            logger.info(f"Found {len(subtechniques_docs)} subtechniques")

            for sub_doc in subtechniques_docs:
                sub_id = sub_doc.get('source_id')
                sub_impl_strategies = _parse_json_field(sub_doc.get('implementation_strategies', '[]'))

                subtechnique_info = {
                    "id": sub_id,
                    "name": sub_doc.get('name'),
                    "description": sub_doc.get('text', ''),
                    "pillar": sub_doc.get('pillar', ''),
                    "phase": sub_doc.get('phase', ''),
                    "has_code_snippets": sub_doc.get('has_code_snippets', False)
                }

                # Add strategies for this subtechnique
                if include_code and sub_impl_strategies:
                    subtechnique_info["strategies"] = _format_strategies(
                        sub_impl_strategies,
                        include_code=include_code
                    )

                subtechniques.append(subtechnique_info)

        elif doc_type == 'subtechnique':
            # This is a subtechnique - include its strategies
            if include_code and impl_strategies:
                strategies = _format_strategies(impl_strategies, include_code=include_code)

        # Step 3: Build response
        response = {
            "technique": technique_info,
            "subtechniques": subtechniques,
            "strategies": strategies,
            "metadata": {
                "total_subtechniques": len(subtechniques),
                "total_strategies": len(strategies),
                "has_implementation_guidance": len(strategies) > 0 or any(
                    "strategies" in st for st in subtechniques
                )
            }
        }

        logger.info(
            f"Technique detail retrieved successfully",
            extra={
                "technique_id": technique_id,
                "subtechniques": len(subtechniques),
                "strategies": len(strategies)
            }
        )

        return response

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to get technique detail: {e}", exc_info=True)
        raise


def _parse_json_field(field_value: Any) -> Any:
    """Parse JSON string field, return parsed value or empty list/dict."""
    if not field_value:
        return []

    if isinstance(field_value, str):
        try:
            return json.loads(field_value)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON field: {field_value[:100]}")
            return []

    return field_value


def _format_strategies(
    strategies: List[Dict[str, Any]],
    include_code: bool = True
) -> List[Dict[str, Any]]:
    """
    Format implementation strategies, optionally extracting code snippets.

    Args:
        strategies: List of strategy dicts with 'strategy' and 'howTo' fields
        include_code: Whether to include full HTML/code

    Returns:
        List of formatted strategy dicts
    """
    formatted = []

    for strat in strategies:
        strategy_info = {
            "strategy": strat.get('strategy', ''),
            "how_to": strat.get('howTo', '') if include_code else _strip_html(strat.get('howTo', ''))
        }

        # Extract code blocks if present
        if include_code:
            code_blocks = _extract_code_blocks(strat.get('howTo', ''))
            if code_blocks:
                strategy_info["code_examples"] = code_blocks

        formatted.append(strategy_info)

    return formatted


def _strip_html(html_text: str) -> str:
    """Strip HTML tags from text."""
    import re
    clean = re.sub(r'<[^>]+>', ' ', html_text)
    clean = ' '.join(clean.split())
    return clean


def _extract_code_blocks(html_text: str) -> List[Dict[str, str]]:
    """
    Extract code blocks from HTML.

    Returns:
        List of dicts with 'language' and 'code' keys
    """
    import re

    # Match <pre><code>...</code></pre> blocks
    pattern = r'<pre><code[^>]*>(.*?)</code></pre>'
    matches = re.findall(pattern, html_text, re.DOTALL)

    code_blocks = []
    for i, code in enumerate(matches, 1):
        # Clean up HTML entities and extra whitespace
        clean_code = code.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        clean_code = clean_code.strip()

        code_blocks.append({
            "block_number": i,
            "language": "python",  # Default assumption
            "code": clean_code
        })

    return code_blocks
