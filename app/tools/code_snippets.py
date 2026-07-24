"""
Secure Code Snippet Tool for AIDEFEND MCP Service

Extracts executable code snippets from implementation strategies.
"""

import json
import re
import asyncio
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup

from app.logger import get_logger
from app.core import decode_framework_record
from app.security import (
    InputValidationError,
    sanitize_technique_id,
    validate_bounded_integer,
)

logger = get_logger(__name__)


async def get_secure_code_snippet(
    technique_id: Optional[str] = None,
    topic: Optional[str] = None,
    language: Optional[str] = None,
    max_snippets: int = 5
) -> Dict[str, Any]:
    """
    Get secure code implementation snippets from AIDEFEND strategies.

    Can search by:
    - Specific technique ID (returns all code from that technique)
    - Topic keyword (e.g., "RAG validation", "prompt guard")
    - Programming language filter

    Args:
        technique_id: Specific technique/subtechnique ID (optional)
        topic: Natural language topic (e.g., "input validation", "RAG security")
        language: Programming language filter (e.g., "python", "javascript")
        max_snippets: Maximum number of snippets to return (1-20, default: 5)

    Returns:
        Dict containing code snippets with context and metadata

    Raises:
        InputValidationError: If inputs are invalid
        Exception: If database query fails

    Example:
        >>> # Get code for specific technique
        >>> result = await get_secure_code_snippet(technique_id="AID-H-002.002")

        >>> # Search by topic
        >>> result = await get_secure_code_snippet(topic="prompt injection defense")
    """
    from app.core import query_engine
    from app.exceptions import QueryEngineNotInitializedError

    # Input validation
    if not technique_id and not topic:
        raise InputValidationError("Either technique_id or topic must be provided")

    if topic and len(topic) < 3:
        raise InputValidationError("topic must be at least 3 characters")

    max_snippets = validate_bounded_integer(
        max_snippets, "max_snippets", 1, 20
    )

    # Pre-flight check: ensure query engine is ready
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please run 'sync_aidefend' first to download the knowledge base."
        )

    # Support hybrid search: if both technique_id and topic provided, combine results
    search_mode = "hybrid" if (technique_id and topic) else "technique_id" if technique_id else "topic"
    logger.info(f"Searching code snippets [mode={search_mode}] technique_id={technique_id}, topic={topic}")

    try:
        code_snippets = []

        # Hybrid search: if both technique_id and topic provided, get both and merge
        if technique_id and topic:
            technique_id = technique_id.strip().upper()
            topic = topic.strip()

            if len(topic) < 3:
                raise InputValidationError("topic must be at least 3 characters")

            # Sanitize technique_id to prevent OR-clause injection (CRITICAL)
            sanitized_id = sanitize_technique_id(technique_id)

            # First, get code from specific technique (using sanitized ID)
            docs = await query_engine.read_table(
                lambda table: table.search().where(
                    f"source_id = '{sanitized_id}' OR parent_technique_id = '{sanitized_id}'"
                ).to_pandas().to_dict('records')
            )

            logger.info(f"[Hybrid] Found {len(docs)} documents for technique {technique_id}")

            for doc in docs:
                snippets = _extract_code_from_doc(doc)
                code_snippets.extend(snippets)

            # Then, supplement with topic-based semantic search
            from fastembed import TextEmbedding
            model_name = query_engine.active_embedding_model
            model = await asyncio.to_thread(TextEmbedding, model_name=model_name)
            query_embedding = list(await asyncio.to_thread(model.embed, [topic]))[0]

            search_results = await query_engine.read_table(
                lambda table: table.search(query_embedding.tolist()).where(
                    "has_code_snippets = true"
                ).limit(max_snippets).to_pandas().to_dict('records')
            )

            logger.info(f"[Hybrid] Found {len(search_results)} additional documents for topic: {topic}")

            # Add topic results, avoiding duplicates
            existing_ids = {s.get('source_document_id') for s in code_snippets}
            for doc in search_results:
                if doc.get('source_id') not in existing_ids:
                    snippets = _extract_code_from_doc(doc)
                    code_snippets.extend(snippets)

        # Case 1: Specific technique ID only
        elif technique_id:
            technique_id = technique_id.strip().upper()

            # Sanitize technique_id to prevent OR-clause injection (CRITICAL)
            sanitized_id = sanitize_technique_id(technique_id)

            # Get the technique and all related documents (using sanitized ID)
            docs = await query_engine.read_table(
                lambda table: table.search().where(
                    f"source_id = '{sanitized_id}' OR parent_technique_id = '{sanitized_id}'"
                ).to_pandas().to_dict('records')
            )

            logger.info(f"Found {len(docs)} documents for technique {technique_id}")

            for doc in docs:
                snippets = _extract_code_from_doc(doc)
                code_snippets.extend(snippets)

        # Case 2: Topic-based semantic search only
        elif topic:
            topic = topic.strip()

            if len(topic) < 3:
                raise InputValidationError("topic must be at least 3 characters")

            # Search for strategies with code
            from fastembed import TextEmbedding
            model_name = query_engine.active_embedding_model
            model = await asyncio.to_thread(TextEmbedding, model_name=model_name)
            query_embedding = list(await asyncio.to_thread(model.embed, [topic]))[0]

            # Search strategies with code
            search_results = await query_engine.read_table(
                lambda table: table.search(query_embedding.tolist()).where(
                    "has_code_snippets = true"
                ).limit(max_snippets * 2).to_pandas().to_dict('records')
            )

            logger.info(f"Found {len(search_results)} documents with code for topic: {topic}")

            for doc in search_results:
                snippets = _extract_code_from_doc(doc)
                code_snippets.extend(snippets)

        code_snippets = _deduplicate_snippets(code_snippets)

        # Filter by language if specified
        if language:
            language_lower = language.lower()
            code_snippets = [
                s for s in code_snippets
                if language_lower in s.get('language', '').lower()
            ]

        # Limit results
        code_snippets = code_snippets[:max_snippets]

        logger.info(f"Returning {len(code_snippets)} code snippets")

        return {
            "query": {
                "technique_id": technique_id,
                "topic": topic,
                "language_filter": language
            },
            "code_snippets": code_snippets,
            "total_snippets": len(code_snippets),
            "usage_notes": {
                "security_warning": "Review and test all code before using in production",
                "adaptation_required": "Code snippets may need adaptation to your specific environment",
                "dependencies": "Check code comments for required libraries and dependencies"
            }
        }

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Failed to get code snippets: {e}", exc_info=True)
        raise


def _extract_code_from_doc(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract all code snippets from a document.

    Args:
        doc: Document dict from LanceDB

    Returns:
        List of code snippet dicts
    """
    snippets = []
    doc = decode_framework_record(doc)
    impl_strategies = doc['implementation_guidance']

    try:
        for i, strategy in enumerate(impl_strategies, 1):
            how_to_html = strategy.get('howTo', '')

            if not how_to_html:
                continue

            # Extract code blocks
            code_blocks = _extract_code_blocks(how_to_html)

            if not code_blocks:
                continue

            # Build context
            source_document_id = doc.get('source_id', '')
            control_id = (
                doc['parent_technique_id']
                if doc.get('type') == 'strategy'
                else source_document_id
            )
            context = {
                "technique_id": control_id,
                "control_id": control_id,
                "source_document_id": source_document_id,
                "guidance_id": strategy.get('id') or doc['guidance_id'],
                "technique_name": doc.get('name'),
                "tactic": doc.get('tactic'),
                "pillar": doc['pillar'],
                "phase": doc['phase'],
                "scope_boundary": doc['scope_boundary'],
                "tools_opensource": doc['tools_opensource'],
                "tools_source_available": doc['tools_source_available'],
                "tools_commercial": doc['tools_commercial'],
                "warnings": doc['warnings'],
                "implementation": strategy.get('implementation', 'Implementation Guidance')
            }

            for block in code_blocks:
                snippets.append({
                    **context,
                    "code": block['code'],
                    "language": block['language'],
                    "description": _extract_description(how_to_html),
                    "usage_context": _extract_usage_context(how_to_html)
                })

    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse strategies for {doc.get('source_id')}: {e}")

    return snippets


def _deduplicate_snippets(snippets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicated embedded/strategy-document code without losing order."""
    unique = []
    seen = set()
    for snippet in snippets:
        key = (
            snippet.get('guidance_id'),
            snippet.get('language'),
            snippet.get('code'),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(snippet)
    return unique


def _extract_code_blocks(html_text: str) -> List[Dict[str, str]]:
    """
    Extract code blocks from HTML with language detection using BeautifulSoup.

    First tries to extract language from class attribute (e.g., class="language-python"),
    then falls back to pattern-based heuristic detection.

    Returns:
        List of dicts with 'language' and 'code' keys
    """
    code_blocks = []

    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html_text, 'html.parser')

    # Find all <pre><code>...</code></pre> structures
    for pre_tag in soup.find_all('pre'):
        code_tag = pre_tag.find('code')
        if not code_tag:
            continue

        # Extract language from class attribute
        language = 'unknown'
        if code_tag.get('class'):
            # Look for 'language-python', 'python', etc.
            for class_name in code_tag['class']:
                class_name_lower = class_name.lower()
                # Remove 'language-' prefix if present
                if class_name_lower.startswith('language-'):
                    lang = class_name_lower.replace('language-', '')
                else:
                    lang = class_name_lower

                # Normalize common language names
                lang_map = {
                    'js': 'javascript',
                    'ts': 'typescript',
                    'py': 'python',
                    'sh': 'shell',
                    'bash': 'shell',
                    'golang': 'go'
                }
                language = lang_map.get(lang, lang)
                break  # Use first class

        # Get clean code text (BeautifulSoup handles HTML entities automatically)
        clean_code = code_tag.get_text().strip()

        if not clean_code:
            continue

        # Fall back to heuristic detection if language not found
        if language == 'unknown':
            language = _detect_language(clean_code)

        code_blocks.append({
            "language": language,
            "code": clean_code
        })

    return code_blocks


def _detect_language(code: str) -> str:
    """
    Simple language detection based on code patterns.

    Args:
        code: Code string

    Returns:
        Detected language name
    """
    code_lower = code.lower()

    # Python indicators
    if any(keyword in code_lower for keyword in ['import ', 'def ', 'class ', 'from ', 'asyncio', '__init__']):
        return "python"

    # JavaScript/TypeScript indicators
    if any(keyword in code_lower for keyword in ['const ', 'let ', 'var ', 'function ', 'async ', '=>', 'require(']):
        return "javascript"

    # Go indicators
    if any(keyword in code_lower for keyword in ['package ', 'func ', 'import "', 'go ']):
        return "go"

    # Java indicators
    if any(keyword in code_lower for keyword in ['public class', 'private ', 'protected ', 'import java']):
        return "java"

    # Shell/Bash indicators
    if code.startswith('#!') or any(keyword in code_lower for keyword in ['#!/bin/', 'echo ', 'export ']):
        return "shell"

    return "unknown"


def _extract_description(html_text: str) -> str:
    """
    Extract description text from HTML (before first code block).

    Args:
        html_text: HTML content

    Returns:
        Description text
    """
    # Get text before first <pre> tag
    match = re.search(r'(.*?)<pre>', html_text, re.DOTALL)

    if match:
        desc = match.group(1)
        # Strip HTML tags
        desc = re.sub(r'<[^>]+>', ' ', desc)
        desc = ' '.join(desc.split())
        return desc[:300]  # Limit length

    return ""


def _extract_usage_context(html_text: str) -> str:
    """
    Extract usage context (steps, action items) from HTML.

    Args:
        html_text: HTML content

    Returns:
        Usage context text
    """
    # Look for "Action:", "Step:", etc.
    patterns = [
        r'<p><strong>Action:</strong>(.*?)</p>',
        r'<h5>Step \d+:(.*?)</h5>',
        r'<p><strong>Step \d+:</strong>(.*?)</p>'
    ]

    context_parts = []

    for pattern in patterns:
        matches = re.findall(pattern, html_text, re.DOTALL)
        for match in matches:
            clean = re.sub(r'<[^>]+>', ' ', match)
            clean = ' '.join(clean.split())
            if clean:
                context_parts.append(clean)

    return ' '.join(context_parts[:2])  # First 2 items
