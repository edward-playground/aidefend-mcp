"""
Validation Tool for AIDEFEND MCP Service

Validates technique IDs and provides suggestions for invalid or not-found IDs.
"""

import re
import asyncio
from typing import Dict, Any, List, Optional
from difflib import SequenceMatcher

from app.logger import get_logger
from app.security import InputValidationError, sanitize_technique_id
from app.utils import sanitize_for_json

logger = get_logger(__name__)

# Canonical AIDEFEND ID shape. Tactic codes are taxonomy data, not a closed
# application enum: future framework releases may add a code without requiring
# an MCP/REST release. Keep the segment deliberately narrow (uppercase ASCII,
# starts with a letter, followed by alphanumeric characters) while database
# membership remains the authority for whether a well-formed ID exists.
_TACTIC_CODE_PATTERN = r"[A-Z][A-Z0-9]*"
CONTROL_ID_PATTERN = re.compile(
    rf"^AID-{_TACTIC_CODE_PATTERN}-\d{{3}}(?:\.\d{{3}})?\Z"
)
GUIDANCE_ID_PATTERN = re.compile(
    rf"^AID-{_TACTIC_CODE_PATTERN}-\d{{3}}(?:\.\d{{3}})?-G\d{{3}}\Z"
)
TECHNIQUE_ID_PATTERN = re.compile(
    rf"^AID-{_TACTIC_CODE_PATTERN}-\d{{3}}(?:\.\d{{3}})?(?:-G\d{{3}})?\Z"
)

# Friendly labels for tactic codes known to this release. This mapping is
# intentionally informational and must not be used as an ID-validation enum.
VALID_TACTIC_CODES = {
    'M': 'Model',
    'H': 'Harden',
    'D': 'Detect',
    'I': 'Isolate',
    'DV': 'Deceive',
    'E': 'Evict',
    'R': 'Restore'
}


async def validate_technique_id(technique_id: str) -> Dict[str, Any]:
    """
    Validate if a technique ID exists and is correctly formatted.

    Performs:
    1. Format validation (checks against pattern)
    2. Database lookup (checks if ID exists)
    3. Fuzzy matching (provides suggestions if not found)

    Args:
        technique_id: The technique ID to validate (e.g., "AID-H-001")

    Returns:
        Dict containing validation result and suggestions:
        {
            "valid": bool,
            "technique": {...} or None,
            "reason": str,  # If invalid
            "suggestions": [...]  # If not found
        }

    Raises:
        InputValidationError: If input is malformed
        Exception: If database query fails

    Example:
        >>> result = await validate_technique_id("AID-H-001")
        >>> if result["valid"]:
        ...     print(f"Found: {result['technique']['name']}")
    """
    from app.core import decode_framework_record, query_engine
    from app.exceptions import QueryEngineNotInitializedError

    # Input sanitization (before database check — fail fast on bad input)
    if not technique_id or not isinstance(technique_id, str):
        raise InputValidationError("technique_id must be a non-empty string")

    technique_id = technique_id.strip().upper()

    if len(technique_id) > 50:  # Reasonable limit
        raise InputValidationError("technique_id too long (max 50 characters)")

    # Step 1: Format validation (before database check)
    if not TECHNIQUE_ID_PATTERN.match(technique_id):
        logger.warning(f"Invalid technique ID format: {technique_id}")
        return {
            "valid": False,
            "technique": None,
            "reason": "INVALID_FORMAT",
            "expected_format": "AID-{TACTIC}-###[.###][-G###]",
            "examples": [
                "AID-H-001 (Technique)",
                "AID-D-001.001 (Sub-technique)",
                "AID-DV-001 (Deceive technique)",
                "AID-D-001.001-G001 (Implementation guidance)"
            ],
            "message": (
                f"Invalid format: '{technique_id}'. "
                "Expected format: AID-{{TACTIC}}-###[.###][-G###] "
                "(e.g., AID-H-001, AID-D-001.001, AID-DV-001, "
                "AID-D-001.001-G001)"
            )
        }

    logger.info(f"Validating technique ID: {technique_id}")

    # Pre-flight check: ensure query engine is ready (after format validation)
    if not query_engine.is_ready:
        raise QueryEngineNotInitializedError(
            "Database not initialized. Please run 'sync_aidefend' first to download the knowledge base."
        )

    # Step 2: Database lookup
    try:
        # Sanitize technique_id to prevent filter injection
        # This is defense-in-depth: format validation + sanitization
        sanitized_id = sanitize_technique_id(technique_id)

        # Search for exact match (using sanitized ID)
        logger.info(f"Searching database for: {sanitized_id}")
        results = await query_engine.read_table(
            lambda table: table.search().where(
                f"source_id = '{sanitized_id}'"
            ).limit(1).to_pandas().to_dict('records')
        )

        if results:
            doc = decode_framework_record(results[0])
            logger.info(f"Found technique: {doc.get('name')}")

            # Scrub NaN/Inf from DB-sourced fields (e.g. a top-level technique's
            # parent_technique_id) so the REST JSONResponse (allow_nan=False) does not 500.
            return sanitize_for_json({
                "valid": True,
                "technique": {
                    "id": doc.get('source_id'),
                    "name": doc.get('name'),
                    "type": doc.get('type'),
                    "tactic": doc.get('tactic'),
                    "pillar": doc.get('pillar', ''),
                    "phase": doc.get('phase', ''),
                    "parent_technique_id": doc.get('parent_technique_id', ''),
                    "guidance_id": doc.get('guidance_id', ''),
                    "scope_boundary": doc.get('scope_boundary') or {},
                    "tools_opensource": doc['tools_opensource'],
                    "tools_source_available": doc['tools_source_available'],
                    "tools_commercial": doc['tools_commercial'],
                    "is_actionable": bool(doc.get('is_actionable', False)),
                    "is_parent_family": bool(doc.get('is_parent_family', False)),
                },
                "message": f"Valid AIDEFEND ID: {technique_id}"
            })

        # Step 3: Not found - provide fuzzy matching suggestions
        logger.info(f"Technique ID not found: {technique_id}. Searching for similar IDs...")

        # Get all IDs from query engine cache (optimization - avoids full table scan)
        from app.core import query_engine
        all_docs = query_engine.get_id_cache()

        # Fallback: if cache not available, query database directly
        if all_docs is None:
            logger.warning("ID cache not available, performing full table scan (slow)")
            all_docs = await query_engine.read_table(
                lambda table: table.to_pandas()[
                    ['source_id', 'name', 'type', 'tactic']
                ].to_dict('records')
            )
        else:
            logger.info(f"Using ID cache for fuzzy matching: {len(all_docs)} entries")

        # Find similar IDs using fuzzy matching
        suggestions = find_similar_ids(technique_id, all_docs, threshold=0.6, max_results=5)

        logger.info(f"Found {len(suggestions)} similar IDs")

        return {
            "valid": False,
            "technique": None,
            "reason": "NOT_FOUND",
            "queried_id": technique_id,
            "suggestions": suggestions,
            "message": (
                f"Technique ID '{technique_id}' not found in database. "
                f"{'Did you mean one of the suggested IDs?' if suggestions else 'No similar IDs found.'}"
            ),
            "help": "Use get_technique_detail with a suggested ID to view full information."
        }

    except FileNotFoundError:
        logger.error("Database not found")
        raise Exception("Database not initialized. Please run sync first.")

    except Exception as e:
        logger.error(f"Database query failed: {e}", exc_info=True)
        raise Exception(f"Failed to validate technique ID: {str(e)}")


def find_similar_ids(
    query_id: str,
    all_docs: List[Dict[str, Any]],
    threshold: float = 0.6,
    max_results: int = 5
) -> List[Dict[str, Any]]:
    """
    Find similar technique IDs using fuzzy string matching.

    Args:
        query_id: The query technique ID
        all_docs: List of all documents with IDs
        threshold: Minimum similarity ratio (0.0-1.0)
        max_results: Maximum number of suggestions to return

    Returns:
        List of similar IDs with metadata
    """
    similarities = []

    for doc in all_docs:
        doc_id = doc['source_id']

        # Calculate similarity ratio
        ratio = SequenceMatcher(None, query_id.upper(), doc_id.upper()).ratio()

        # Also check if query is a substring (higher weight)
        if query_id.upper() in doc_id.upper():
            ratio = max(ratio, 0.8)  # Boost substring matches

        if ratio >= threshold:
            similarities.append({
                "id": doc_id,
                "name": doc['name'],
                "type": doc['type'],
                "tactic": doc['tactic'],
                "similarity_score": round(ratio, 2),
                "match_reason": "substring" if query_id.upper() in doc_id.upper() else "fuzzy"
            })

    # Sort by similarity score (descending)
    similarities.sort(key=lambda x: x['similarity_score'], reverse=True)

    return similarities[:max_results]


async def batch_validate_technique_ids(technique_ids: List[str]) -> Dict[str, Any]:
    """
    Validate multiple technique IDs in batch.

    Args:
        technique_ids: List of technique IDs to validate

    Returns:
        Dict with validation results for each ID:
        {
            "total": int,
            "valid_count": int,
            "invalid_count": int,
            "results": [...]
        }

    Example:
        >>> ids = ["AID-H-001", "AID-H-002", "AID-INVALID"]
        >>> results = await batch_validate_technique_ids(ids)
        >>> print(f"Valid: {results['valid_count']}/{results['total']}")
    """
    if not technique_ids:
        raise InputValidationError("technique_ids cannot be empty")

    if len(technique_ids) > 100:  # Reasonable batch limit
        raise InputValidationError("Too many IDs in batch (max 100)")

    logger.info(f"Batch validating {len(technique_ids)} technique IDs")

    results = []
    valid_count = 0
    invalid_count = 0

    for tech_id in technique_ids:
        try:
            result = await validate_technique_id(tech_id)
            results.append(result)

            if result["valid"]:
                valid_count += 1
            else:
                invalid_count += 1

        except Exception as e:
            logger.warning(f"Failed to validate {tech_id}: {e}")
            results.append({
                "valid": False,
                "technique": None,
                "queried_id": tech_id,
                "reason": "VALIDATION_ERROR",
                "message": str(e)
            })
            invalid_count += 1

    return {
        "total": len(technique_ids),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "results": results
    }
