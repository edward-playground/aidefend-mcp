"""
Technique Detail Tool for AIDEFEND MCP Service

Retrieves complete information about a specific technique including all
sub-techniques, implementation strategies with code, tools, and threat mappings.
"""

import json
from typing import Dict, Any, List, Optional

from app.logger import get_logger
from app.security import InputValidationError, sanitize_technique_id
from app.utils import sanitize_for_json

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
    - Operational, performance, and scope warnings

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
    from app.core import decode_framework_record, query_engine
    from app.exceptions import QueryEngineNotInitializedError

    # Input validation
    if not technique_id or not isinstance(technique_id, str):
        raise InputValidationError("technique_id must be a non-empty string")

    technique_id = technique_id.strip().upper()

    if len(technique_id) > 50:
        raise InputValidationError("technique_id too long")

    # Pre-flight check: ensure query engine is ready
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please run 'sync_aidefend' first to download the knowledge base."
        )

    # Sanitize technique_id to prevent filter injection
    sanitized_id = sanitize_technique_id(technique_id)
    logger.info(f"Fetching technique detail for: {sanitized_id}")

    try:
        # Step 1: Get the main technique/subtechnique (using sanitized ID)
        main_doc = await query_engine.read_table(
            lambda table: table.search().where(
                f"source_id = '{sanitized_id}'"
            ).limit(1).to_pandas().to_dict('records')
        )

        if not main_doc:
            raise Exception(f"Technique ID '{technique_id}' not found in database")

        main_doc = decode_framework_record(main_doc[0])
        doc_type = main_doc.get('type')

        logger.info(f"Found {doc_type}: {main_doc.get('name')}")

        defends_against = main_doc['defends_against']
        tools_opensource = main_doc['tools_opensource']
        tools_source_available = main_doc['tools_source_available']
        tools_commercial = main_doc['tools_commercial']
        impl_strategies = main_doc['implementation_guidance']
        warnings = main_doc['warnings']

        # Build main technique info
        technique_info = {
            "id": main_doc.get('source_id'),
            "name": main_doc.get('name'),
            "type": doc_type,
            "tactic": main_doc.get('tactic'),
            "pillar": main_doc['pillar'],
            "phase": main_doc['phase'],
            "description": main_doc.get('text', ''),
            "parent_technique_id": main_doc['parent_technique_id'],
            "guidance_id": main_doc['guidance_id'],
            "scope_boundary": main_doc['scope_boundary'],
            "is_actionable": main_doc['is_actionable'],
            "is_parent_family": main_doc['is_parent_family'],
            "has_code_snippets": main_doc['has_code_snippets'],
            "warnings": warnings,
        }

        # Add threat mappings
        if defends_against:
            technique_info["defends_against"] = defends_against

        # Add tools if requested
        if include_tools:
            technique_info["tools"] = {
                "opensource": tools_opensource,
                "source_available": tools_source_available,
                "commercial": tools_commercial
            }

        # Step 2: Find child elements based on type
        subtechniques = []
        strategies = []

        if doc_type == 'technique':
            # This is a parent technique - find all subtechniques
            logger.info(f"Searching for subtechniques of {sanitized_id}...")

            # Use sanitized ID in where() clause to prevent injection
            subtechniques_docs = await query_engine.read_table(
                lambda table: table.search().where(
                    f"parent_technique_id = '{sanitized_id}' AND type = 'subtechnique'"
                ).to_pandas().to_dict('records')
            )

            logger.info(f"Found {len(subtechniques_docs)} subtechniques")

            for sub_doc in subtechniques_docs:
                sub_doc = decode_framework_record(sub_doc)
                sub_id = sub_doc.get('source_id')
                sub_defends_against = sub_doc['defends_against']
                sub_tools_opensource = sub_doc['tools_opensource']
                sub_tools_source_available = sub_doc['tools_source_available']
                sub_tools_commercial = sub_doc['tools_commercial']
                sub_impl_strategies = sub_doc['implementation_guidance']
                sub_warnings = sub_doc['warnings']

                subtechnique_info = {
                    "id": sub_id,
                    "name": sub_doc.get('name'),
                    "description": sub_doc.get('text', ''),
                    "pillar": sub_doc['pillar'],
                    "phase": sub_doc['phase'],
                    "parent_technique_id": sub_doc['parent_technique_id'],
                    "guidance_id": sub_doc['guidance_id'],
                    "scope_boundary": sub_doc['scope_boundary'],
                    "is_actionable": sub_doc['is_actionable'],
                    "is_parent_family": sub_doc['is_parent_family'],
                    "has_code_snippets": sub_doc['has_code_snippets'],
                    "warnings": sub_warnings,
                }

                if sub_defends_against:
                    subtechnique_info["defends_against"] = sub_defends_against

                if include_tools:
                    subtechnique_info["tools"] = {
                        "opensource": sub_tools_opensource,
                        "source_available": sub_tools_source_available,
                        "commercial": sub_tools_commercial
                    }

                # Add strategies for this subtechnique
                if sub_impl_strategies:
                    subtechnique_info["strategies"] = _format_strategies(
                        sub_impl_strategies,
                        include_code=include_code
                    )

                subtechniques.append(subtechnique_info)

            if not subtechniques_docs and impl_strategies:
                # Standalone techniques store implementation guidance on the
                # technique record itself.
                strategies = _format_strategies(impl_strategies, include_code=include_code)

        elif doc_type == 'subtechnique':
            # This is a subtechnique - include its strategies
            if impl_strategies:
                strategies = _format_strategies(impl_strategies, include_code=include_code)

        elif doc_type == 'strategy':
            # Guidance documents are first-class searchable records in schema 3.
            strategies = _format_strategies(impl_strategies, include_code=include_code)

        # Step 3: Build response
        response = {
            "technique": technique_info,
            "subtechniques": subtechniques,
            "strategies": strategies,
            "metadata": {
                "total_subtechniques": len(subtechniques),
                "total_strategies": len(strategies) + sum(
                    len(subtechnique.get("strategies", []))
                    for subtechnique in subtechniques
                ),
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

        # Scrub NaN/Inf from DB-sourced fields (e.g. a top-level technique's
        # parent_technique_id) so the REST JSONResponse (allow_nan=False) does not 500.
        return sanitize_for_json(response)

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
        strategies: List of guidance dicts with 'implementation' and 'howTo' fields
        include_code: Whether to include full HTML/code

    Returns:
        List of formatted strategy dicts
    """
    formatted = []

    for strat in strategies:
        strategy_info = {
            "guidance_id": strat.get('id', ''),
            "implementation": strat.get('implementation', ''),
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
