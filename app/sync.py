"""
Synchronization service for AIDEFEND framework content.
Handles GitHub sync, parsing, embedding, and indexing with security.
"""

import asyncio
import httpx
import lancedb
import time
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from fastembed import TextEmbedding
from bs4 import BeautifulSoup

from app.config import settings
from app.logger import get_logger
from app.security import (
    validate_commit_sha,
    validate_github_url,
    validate_file_path,
    sanitize_filename,
    set_secure_file_permissions,
    compute_file_checksum
)
from app.utils import (
    parse_js_file_with_node,
    save_version_info,
    get_local_commit_sha,
    format_bytes
)

logger = get_logger(__name__)

# Sync lock using asyncio.Lock (non-blocking, in-memory)
# Since API_WORKERS=1, we run in single process, so asyncio.Lock is sufficient
_sync_lock = asyncio.Lock()

# Global state for last sync error
_last_sync_error: Optional[str] = None


async def _acquire_sync_lock() -> bool:
    """
    Acquire sync lock using asyncio.Lock (non-blocking).

    Returns:
        True if lock acquired, False if another coroutine holds the lock
    """
    if _sync_lock.locked():
        logger.info("Sync already in progress (asyncio.Lock is held)")
        return False

    await _sync_lock.acquire()
    logger.info("Acquired async sync lock")
    return True


def _release_sync_lock() -> None:
    """Release async sync lock."""
    try:
        _sync_lock.release()
        logger.info("Released async sync lock")
    except RuntimeError:
        logger.warning("Attempted to release a lock that was not held.")


def is_sync_in_progress() -> bool:
    """
    Check if sync is currently running (non-blocking).

    Returns:
        True if asyncio.Lock is currently held
    """
    return _sync_lock.locked()


def get_last_sync_error() -> Optional[str]:
    """Get last sync error message."""
    return _last_sync_error


def _calculate_statistics_from_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Pre-compute statistics from LanceDB records (optimization).

    This avoids expensive full table scans when get_statistics is called.
    Called during sync after records are prepared but before writing to DB.

    Args:
        records: List of LanceDB records

    Returns:
        Dict with pre-computed statistics matching get_statistics format
    """
    import json
    from collections import defaultdict

    total_documents = len(records)
    type_counts = defaultdict(int)
    tactic_counts = defaultdict(int)
    pillar_counts = defaultdict(int)
    phase_counts = defaultdict(int)

    # Enhanced features
    techniques_with_defenses = 0
    techniques_with_opensource_tools = 0
    techniques_with_commercial_tools = 0
    documents_with_code = 0

    # Framework coverage
    owasp_items = set()
    atlas_items = set()
    maestro_items = set()

    for record in records:
        doc_type = record.get('type', 'unknown')
        tactic = record.get('tactic', 'Unknown')
        pillar = record.get('pillar', '')
        phase = record.get('phase', '')

        # Count by type
        type_counts[doc_type] += 1

        # Count by tactic
        tactic_counts[tactic] += 1

        # Count by pillar (only if not empty)
        if pillar:
            pillar_counts[pillar] += 1

        # Count by phase (only if not empty)
        if phase:
            phase_counts[phase] += 1

        # Enhanced features (only for techniques)
        if doc_type == 'technique':
            # Parse defends_against field
            defends_against_str = record.get('defends_against', '[]')
            try:
                defends_against = json.loads(defends_against_str) if isinstance(defends_against_str, str) else defends_against_str

                if defends_against:
                    techniques_with_defenses += 1

                    # Extract threat items by framework
                    for framework_data in defends_against:
                        framework_name = framework_data.get('framework', '')
                        items = framework_data.get('items', [])

                        if 'OWASP' in framework_name:
                            owasp_items.update(items)
                        elif 'ATLAS' in framework_name or 'MITRE' in framework_name:
                            atlas_items.update(items)
                        elif 'MAESTRO' in framework_name:
                            maestro_items.update(items)

            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse defends_against for {record.get('source_id')}")

            # Parse tools
            tools_opensource_str = record.get('tools_opensource', '[]')
            tools_commercial_str = record.get('tools_commercial', '[]')

            try:
                tools_opensource = json.loads(tools_opensource_str) if isinstance(tools_opensource_str, str) else tools_opensource_str
                tools_commercial = json.loads(tools_commercial_str) if isinstance(tools_commercial_str, str) else tools_commercial_str

                if tools_opensource:
                    techniques_with_opensource_tools += 1
                if tools_commercial:
                    techniques_with_commercial_tools += 1

            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse tools for {record.get('source_id')}")

        # Check for code snippets
        has_code = record.get('has_code_snippets', False)
        if has_code:
            documents_with_code += 1

    # Build statistics object (matching get_statistics format)
    statistics = {
        "overview": {
            "total_documents": total_documents,
            "total_techniques": type_counts.get('technique', 0),
            "total_subtechniques": type_counts.get('subtechnique', 0),
            "total_strategies": type_counts.get('strategy', 0),
            "last_synced": datetime.now(timezone.utc).isoformat(),
            "embedding_model": settings.EMBEDDING_MODEL,
            "database_path": str(settings.DB_PATH)
        },
        "by_tactic": dict(sorted(tactic_counts.items())),
        "by_pillar": dict(sorted(pillar_counts.items())),
        "by_phase": dict(sorted(phase_counts.items())),
        "threat_framework_coverage": {
            "owasp_llm_items_covered": len(owasp_items),
            "mitre_atlas_items_covered": len(atlas_items),
            "maestro_items_covered": len(maestro_items),
            "techniques_with_threat_mappings": techniques_with_defenses,
            "coverage_percentage": round(
                (techniques_with_defenses / type_counts.get('technique', 1)) * 100, 1
            ) if type_counts.get('technique', 0) > 0 else 0
        },
        "tools_availability": {
            "techniques_with_opensource_tools": techniques_with_opensource_tools,
            "techniques_with_commercial_tools": techniques_with_commercial_tools,
            "opensource_coverage_percentage": round(
                (techniques_with_opensource_tools / type_counts.get('technique', 1)) * 100, 1
            ) if type_counts.get('technique', 0) > 0 else 0
        },
        "implementation_resources": {
            "documents_with_code_snippets": documents_with_code,
            "strategies_total": type_counts.get('strategy', 0),
            "code_coverage_percentage": round(
                (documents_with_code / type_counts.get('strategy', 1)) * 100, 1
            ) if type_counts.get('strategy', 0) > 0 else 0
        }
    }

    return statistics


def _build_threat_mappings(records: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Build reverse index: threat_id -> [technique_ids] (optimization).

    This allows O(1) lookup in defenses_for_threat tool instead of O(n) scan.

    Args:
        records: List of LanceDB records

    Returns:
        Dict mapping threat IDs to lists of technique IDs
    """
    import json

    threat_mappings = {}

    for record in records:
        # Only process techniques (not subtechniques or strategies)
        if record.get('type') != 'technique':
            continue

        technique_id = record.get('source_id')
        defends_against_str = record.get('defends_against', '[]')

        try:
            defends_against = json.loads(defends_against_str) if isinstance(defends_against_str, str) else defends_against_str

            if not defends_against:
                continue

            # Extract all threat items
            for framework_data in defends_against:
                items = framework_data.get('items', [])

                for item in items:
                    # Extract normalized threat IDs from item text
                    # Example: "LLM01:2025 Prompt Injection" -> "LLM01"
                    # Example: "AML.T0015" -> "AML.T0015"

                    item_upper = item.upper()

                    # Extract LLM IDs
                    llm_match = re.search(r'LLM\d{2}', item_upper)
                    if llm_match:
                        threat_id = llm_match.group(0)
                        if threat_id not in threat_mappings:
                            threat_mappings[threat_id] = []
                        if technique_id not in threat_mappings[threat_id]:
                            threat_mappings[threat_id].append(technique_id)

                    # Extract ATLAS IDs (T####)
                    atlas_match = re.search(r'T\d{4}', item_upper)
                    if atlas_match:
                        t_id = atlas_match.group(0)
                        # Store both with and without AML. prefix
                        for threat_id in [t_id, f"AML.{t_id}"]:
                            if threat_id not in threat_mappings:
                                threat_mappings[threat_id] = []
                            if technique_id not in threat_mappings[threat_id]:
                                threat_mappings[threat_id].append(technique_id)

                    # Store full item text as well (for exact matches)
                    # Normalized: strip whitespace, uppercase
                    normalized_item = item.strip().upper()
                    if normalized_item:
                        if normalized_item not in threat_mappings:
                            threat_mappings[normalized_item] = []
                        if technique_id not in threat_mappings[normalized_item]:
                            threat_mappings[normalized_item].append(technique_id)

        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse defends_against for {technique_id}: {e}")

    logger.info(f"Built threat mappings index: {len(threat_mappings)} unique threat IDs")
    return threat_mappings


async def fetch_latest_commit_sha() -> Optional[str]:
    """
    Fetch the latest commit SHA from GitHub repository.

    Returns:
        Commit SHA string or None if failed
    """
    url = f"{settings.github_repo_api_url}/commits/{settings.GITHUB_BRANCH}"

    try:
        # Validate URL before making request
        validate_github_url(url, settings.github_repo_path)

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AIDEFEND-MCP-Service/1.0"
            }

            response = await client.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            sha = data.get("sha")

            if not sha:
                logger.error("No SHA in GitHub response")
                return None

            # Validate SHA format
            validated_sha = validate_commit_sha(sha)
            logger.info(f"Latest GitHub commit: {validated_sha[:8]}")
            return validated_sha

    except httpx.HTTPStatusError as e:
        logger.error(f"GitHub API HTTP error: {e.response.status_code}")
        return None
    except httpx.RequestError as e:
        logger.error(f"GitHub API request error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching commit: {e}")
        return None


async def download_file(filename: str, commit_sha: str) -> Optional[Path]:
    """
    Download a single file from GitHub.

    Args:
        filename: Name of file to download
        commit_sha: Git commit SHA

    Returns:
        Path to downloaded file or None if failed
    """
    try:
        # Sanitize filename
        safe_filename = sanitize_filename(filename)

        # Construct URL
        url = settings.get_raw_file_url(safe_filename, commit_sha)

        # Validate URL
        validate_github_url(url, settings.github_repo_path)

        logger.info(f"Downloading {safe_filename}...")

        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {"User-Agent": "AIDEFEND-MCP-Service/1.0"}
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            content = response.text

            # Save to raw content directory
            file_path = settings.RAW_PATH / safe_filename

            # Validate path
            validated_path = validate_file_path(file_path, settings.RAW_PATH)

            # Write file
            validated_path.write_text(content, encoding='utf-8')

            # Set secure permissions
            set_secure_file_permissions(validated_path)

            # Log file info
            file_size = validated_path.stat().st_size
            logger.info(
                f"Downloaded {safe_filename} ({format_bytes(file_size)})",
                extra={"filename": safe_filename, "size": file_size}
            )

            return validated_path

    except httpx.HTTPStatusError as e:
        logger.error(
            f"Failed to download {filename}: HTTP {e.response.status_code}",
            extra={"filename": filename, "status_code": e.response.status_code}
        )
        return None
    except Exception as e:
        logger.error(f"Error downloading {filename}: {e}")
        return None


def parse_tactic_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """
    Parse a tactic .js file using regex.

    Args:
        file_path: Path to .js file

    Returns:
        Parsed tactic data or None if failed
    """
    try:
        parsed_data = parse_js_file_with_node(file_path)

        # Validate expected structure
        if not isinstance(parsed_data, dict):
            logger.error(f"Parsed data is not a dict: {file_path.name}")
            return None

        required_keys = {"name", "techniques"}
        if not all(key in parsed_data for key in required_keys):
            logger.error(
                f"Missing required keys in {file_path.name}",
                extra={"required": list(required_keys), "found": list(parsed_data.keys())}
            )
            return None

        logger.info(
            f"Parsed {file_path.name}",
            extra={
                "tactic": parsed_data.get("name"),
                "techniques": len(parsed_data.get("techniques", []))
            }
        )

        return parsed_data

    except Exception as e:
        logger.error(f"Failed to parse {file_path.name}: {e}")
        return None


def extract_documents_from_tactic(tactic_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Transform tactic data into flat document list for embedding.

    Args:
        tactic_data: Parsed tactic data

    Returns:
        List of document dicts
    """
    documents = []
    tactic_name = tactic_data.get("name", "Unknown")

    for technique in tactic_data.get("techniques", []):
        tech_id = technique.get("id", "Unknown")
        tech_name = technique.get("name", "Unknown")
        tech_desc = technique.get("description", "")

        # Extract threat framework mappings
        defends_against = technique.get("defendsAgainst", [])

        # Extract tool lists
        tools_opensource = technique.get("toolsOpenSource", [])
        tools_commercial = technique.get("toolsCommercial", [])

        # Document for technique
        tech_text = f"Technique: {tech_name}\nID: {tech_id}\nDescription: {tech_desc}"

        # Add defends-against info to text for better semantic search
        if defends_against:
            frameworks_text = []
            for fw in defends_against:
                fw_name = fw.get("framework", "")
                items = fw.get("items", [])
                if items:
                    frameworks_text.append(f"{fw_name}: {', '.join(items)}")
            if frameworks_text:
                tech_text += "\nDefends Against: " + "; ".join(frameworks_text)

        documents.append({
            "text": tech_text,
            "source_id": tech_id,
            "tactic": tactic_name,
            "type": "technique",
            "name": tech_name,
            "pillar": technique.get("pillar", ""),
            "phase": technique.get("phase", ""),
            "defends_against": defends_against,
            "tools_opensource": tools_opensource,
            "tools_commercial": tools_commercial,
            "parent_technique_id": "",  # Techniques have no parent
            "implementation_strategies": [],  # Techniques don't have strategies directly
            "has_code_snippets": False
        })

        # Documents for sub-techniques
        for sub_tech in technique.get("subTechniques", []):
            sub_id = sub_tech.get("id", "Unknown")
            sub_name = sub_tech.get("name", "Unknown")
            sub_desc = sub_tech.get("description", "")
            sub_pillar = sub_tech.get("pillar", "")
            sub_phase = sub_tech.get("phase", "")

            # Extract implementation strategies (preserve full HTML for code extraction)
            implementation_strategies = sub_tech.get("implementationStrategies", [])

            # Check if any strategy has code snippets (using BeautifulSoup for robustness)
            # This ensures consistency with code_snippets.py extraction logic
            has_code = False
            for strat in implementation_strategies:
                how_to = strat.get("howTo", "")
                if how_to:
                    soup_check = BeautifulSoup(how_to, 'html.parser')
                    if soup_check.find_all(['pre', 'code']):
                        has_code = True
                        break

            sub_text = (
                f"Sub-Technique: {sub_name}\n"
                f"ID: {sub_id}\n"
                f"Parent: {tech_name}\n"
                f"Pillar: {sub_pillar}\n"
                f"Phase: {sub_phase}\n"
                f"Description: {sub_desc}"
            )

            documents.append({
                "text": sub_text,
                "source_id": sub_id,
                "tactic": tactic_name,
                "type": "subtechnique",
                "name": sub_name,
                "pillar": sub_pillar,
                "phase": sub_phase,
                "defends_against": [],  # Sub-techniques inherit from parent
                "tools_opensource": [],
                "tools_commercial": [],
                "parent_technique_id": tech_id,
                "implementation_strategies": implementation_strategies,
                "has_code_snippets": has_code
            })

            # Documents for implementation strategies
            for i, strategy in enumerate(sub_tech.get("implementationStrategies", []), 1):
                strategy_name = strategy.get("strategy", "Strategy")
                how_to_html = strategy.get("howTo", "")

                # For embedding text: Use BeautifulSoup to safely remove HTML
                soup = BeautifulSoup(how_to_html, 'html.parser')

                # Check if this strategy has code (before removing tags)
                has_code = bool(soup.find_all(['pre', 'code']))

                # Remove code tags - we don't want code in the embedding text
                for code_tag in soup.find_all(['pre', 'code']):
                    code_tag.decompose()

                # Get clean text
                clean_how_to = soup.get_text(separator=' ', strip=True)

                strategy_id = f"{sub_id}.S{i}"
                strategy_text = (
                    f"Tactic: {tactic_name}. Technique: {tech_name}. Sub-Technique: {sub_name}\n"
                    f"Implementation Strategy: {strategy_name}\n"
                    f"ID: {strategy_id}\n"
                    f"How-To: {clean_how_to}"
                )

                documents.append({
                    "text": strategy_text,
                    "source_id": strategy_id,
                    "tactic": tactic_name,
                    "type": "strategy",
                    "name": f"{sub_name} - {strategy_name}",
                    "pillar": sub_pillar,
                    "phase": sub_phase,
                    "defends_against": [],
                    "tools_opensource": [],
                    "tools_commercial": [],
                    "parent_technique_id": sub_id,
                    "implementation_strategies": [{
                        "strategy": strategy_name,
                        "howTo": how_to_html  # Preserve full HTML
                    }],
                    "has_code_snippets": has_code
                })

    logger.info(
        f"Extracted {len(documents)} documents from {tactic_name}",
        extra={"tactic": tactic_name, "doc_count": len(documents)}
    )

    return documents


async def embed_and_index(documents: List[Dict[str, Any]]) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Embed documents and store in LanceDB.

    Args:
        documents: List of document dicts

    Returns:
        Tuple of (success: bool, statistics: Optional[Dict])
        - success: True if successful, False otherwise
        - statistics: Pre-computed statistics dict, or None if failed
    """
    try:
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")

        # Load embedding model in thread pool (fastembed uses ONNX Runtime)
        model = await asyncio.to_thread(
            TextEmbedding,
            model_name=settings.EMBEDDING_MODEL
        )

        logger.info(f"Embedding {len(documents)} documents...")

        # Extract texts for batch embedding
        texts = [doc["text"] for doc in documents]

        # Embed in batches (fastembed returns generator, convert to list)
        embeddings_generator = await asyncio.to_thread(
            model.embed,
            texts,
            batch_size=32
        )

        # Convert generator to list and ensure numpy arrays
        embeddings = list(embeddings_generator)

        logger.info("Creating LanceDB records...")

        # Prepare LanceDB records with extended schema
        records = []
        for i, doc in enumerate(documents):
            # Convert complex types to JSON strings for LanceDB storage
            import json

            records.append({
                "vector": embeddings[i].tolist(),
                "text": doc["text"],
                "source_id": doc["source_id"],
                "tactic": doc["tactic"],
                "type": doc["type"],
                "name": doc["name"],
                "pillar": doc.get("pillar", ""),
                "phase": doc.get("phase", ""),
                # New fields for enhanced functionality
                "defends_against": json.dumps(doc.get("defends_against", [])),
                "tools_opensource": json.dumps(doc.get("tools_opensource", [])),
                "tools_commercial": json.dumps(doc.get("tools_commercial", [])),
                "parent_technique_id": doc.get("parent_technique_id", ""),
                "implementation_strategies": json.dumps(doc.get("implementation_strategies", [])),
                "has_code_snippets": doc.get("has_code_snippets", False)
            })

        # Pre-compute statistics from records (optimization for get_statistics tool)
        logger.info("Pre-computing statistics from records...")
        statistics = _calculate_statistics_from_records(records)
        logger.info(f"Statistics pre-computed: {statistics['overview']['total_documents']} documents")

        # Build threat mappings reverse index (optimization for defenses_for_threat tool)
        logger.info("Building threat mappings reverse index...")
        threat_mappings = _build_threat_mappings(records)
        statistics['threat_mappings'] = threat_mappings
        logger.info(f"Threat mappings built: {len(threat_mappings)} unique threat IDs")

        # Connect to LanceDB
        logger.info(f"Connecting to LanceDB: {settings.DB_PATH}")
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))

        # Blue-Green Deployment: Write to temporary table first
        temp_table_name = "aidefend_new_sync"

        # Drop temporary table if exists (from previous failed sync)
        try:
            await asyncio.to_thread(db.drop_table, temp_table_name)
            logger.info(f"Dropped existing '{temp_table_name}' table")
        except Exception:
            pass  # Table doesn't exist, that's fine

        # Create new table with explicit schema
        logger.info(f"Creating '{temp_table_name}' table with {len(records)} records...")

        await asyncio.to_thread(
            db.create_table,
            temp_table_name,
            data=records
        )

        # Verify new table was created successfully
        table_names = await asyncio.to_thread(db.table_names)
        if temp_table_name not in table_names:
            raise Exception(f"Failed to create {temp_table_name} table")

        logger.info(f"Successfully created {temp_table_name} table. Performing atomic swap...")

        # Atomic swap: Rename tables for zero-downtime deployment
        # 1. Delete old backup if exists
        try:
            await asyncio.to_thread(db.drop_table, "aidefend_backup")
            logger.info("Deleted old backup table")
        except Exception:
            pass  # No backup exists

        # 2. Rename current aidefend to aidefend_backup (if exists)
        try:
            table_names = await asyncio.to_thread(db.table_names)
            if "aidefend" in table_names:
                # LanceDB doesn't have native rename, so we need to use underlying filesystem
                aidefend_path = settings.DB_PATH / "aidefend.lance"
                backup_path = settings.DB_PATH / "aidefend_backup.lance"

                if aidefend_path.exists():
                    await asyncio.to_thread(
                        aidefend_path.rename,
                        backup_path
                    )
                    logger.info("Renamed aidefend -> aidefend_backup")
        except Exception as e:
            logger.warning(f"Could not backup old table: {e}")

        # 3. Rename new_sync to aidefend (atomic operation)
        new_sync_path = settings.DB_PATH / f"{temp_table_name}.lance"
        aidefend_path = settings.DB_PATH / "aidefend.lance"

        await asyncio.to_thread(
            new_sync_path.rename,
            aidefend_path
        )

        logger.info("Atomic swap complete: aidefend_new_sync -> aidefend")

        # 4. Reload query engine to use new table
        from app.core import query_engine
        reload_success = await query_engine.reload()
        if reload_success:
            logger.info("Query engine reloaded successfully")
        else:
            logger.warning("Query engine reload reported failure (may still work)")

        logger.info("Zero-downtime sync complete!")

        # Set secure permissions on database directory
        db_dir = settings.DB_PATH
        if db_dir.exists():
            for file in db_dir.rglob("*"):
                if file.is_file():
                    set_secure_file_permissions(file)

        # Return success with pre-computed statistics
        return (True, statistics)

    except Exception as e:
        logger.error(f"Failed to embed and index documents: {e}", exc_info=True)
        return (False, None)


async def run_sync() -> bool:
    """
    Execute complete sync process with file-based locking.

    Returns:
        True if sync successful, False otherwise
    """
    global _last_sync_error

    # Try to acquire lock
    if not await _acquire_sync_lock():
        logger.warning("Sync already in progress, skipping")
        return False

    _last_sync_error = None

    try:
        logger.info("=" * 60)
        logger.info("Starting AIDEFEND sync process")
        logger.info("=" * 60)

        # Fetch latest commit
        latest_sha = await fetch_latest_commit_sha()
        if not latest_sha:
            error_msg = "Could not fetch latest commit from GitHub"
            logger.error(error_msg)
            _last_sync_error = error_msg
            return False

        # Check if update needed
        local_sha = get_local_commit_sha()
        if local_sha == latest_sha:
            logger.info(f"Already up-to-date (commit: {local_sha[:8]})")
            return True

        logger.info(f"Update available: {local_sha[:8] if local_sha else 'None'} -> {latest_sha[:8]}")

        # Download all files
        downloaded_files: List[Path] = []
        for filename in settings.AIDEFEND_FILES:
            file_path = await download_file(filename, latest_sha)
            if file_path:
                downloaded_files.append(file_path)
            else:
                error_msg = f"Failed to download {filename}"
                logger.error(error_msg)
                _last_sync_error = error_msg
                return False

        if len(downloaded_files) != len(settings.AIDEFEND_FILES):
            error_msg = "Not all files downloaded successfully"
            logger.error(error_msg)
            _last_sync_error = error_msg
            return False

        logger.info(f"Downloaded {len(downloaded_files)} files")

        # Parse all files with resilient error handling
        # Single file failure should not fail entire sync
        all_documents = []
        failed_files = []

        for file_path in downloaded_files:
            try:
                # Use asyncio.to_thread to avoid blocking the event loop
                # (parse_tactic_file involves file I/O and CPU-intensive regex operations)
                tactic_data = await asyncio.to_thread(parse_tactic_file, file_path)

                if tactic_data:
                    # Use asyncio.to_thread for extract_documents_from_tactic as well
                    # (involves CPU-intensive data transformation)
                    documents = await asyncio.to_thread(extract_documents_from_tactic, tactic_data)
                    all_documents.extend(documents)
                    logger.info(f"✓ Successfully parsed {file_path.name}: {len(documents)} documents")
                else:
                    # parse_tactic_file returned None
                    raise Exception("parse_tactic_file returned None")

            except Exception as e:
                error_msg = f"Failed to parse or extract from {file_path.name}: {e}"
                logger.error(error_msg, exc_info=True)
                _last_sync_error = error_msg  # Record last error
                failed_files.append(file_path.name)
                # Continue processing other files instead of returning False

        logger.info(f"Total documents extracted: {len(all_documents)}")

        # Only fail if ALL files failed to parse
        if not all_documents:
            error_msg = f"No documents extracted. All {len(failed_files)} file(s) failed to parse."
            logger.error(error_msg)
            _last_sync_error = error_msg
            return False

        # Warn if partial failure occurred
        if failed_files:
            warning_msg = (
                f"Sync proceeding with partial data. "
                f"{len(failed_files)} file(s) failed to parse: {', '.join(failed_files)}"
            )
            logger.warning(warning_msg)
            # Update _last_sync_error to show partial failure
            _last_sync_error = f"Partial sync: {len(failed_files)} file(s) failed ({failed_files[0]})"

        # Embed and index
        success, statistics = await embed_and_index(all_documents)
        if not success:
            error_msg = "Failed to embed and index documents"
            _last_sync_error = error_msg
            return False

        # Save version info with pre-computed statistics
        save_version_info(
            latest_sha,
            {
                "total_documents": len(all_documents),
                "statistics": statistics  # Pre-computed statistics for get_statistics tool
            }
        )

        # Reload query engine to use new database
        # (Use try-except to prevent reload failures from failing the entire sync)
        try:
            # Import here to avoid circular import issues
            from app.core import query_engine
            logger.info("Reloading query engine to use updated database...")
            reload_success = await query_engine.reload()
            if reload_success:
                logger.info("Query engine reloaded successfully")
            else:
                logger.warning("Query engine reload returned False - may not be initialized yet")
        except Exception as e:
            logger.warning(f"Failed to reload query engine after sync: {e}")
            logger.warning("Query engine will reload on next request or service restart")

        logger.info("=" * 60)
        logger.info(f"Sync complete! Updated to commit {latest_sha[:8]}")
        logger.info(f"Indexed {len(all_documents)} documents")
        logger.info("=" * 60)

        return True

    except Exception as e:
        error_msg = f"Unexpected error during sync: {e}"
        logger.error(error_msg, exc_info=True)
        _last_sync_error = error_msg
        return False

    finally:
        # Always release lock when done
        _release_sync_lock()


async def sync_loop():
    """Background task that runs sync periodically."""
    logger.info(
        f"Starting sync loop (interval: {settings.SYNC_INTERVAL_SECONDS}s)"
    )

    while True:
        try:
            await asyncio.sleep(settings.SYNC_INTERVAL_SECONDS)
            if settings.ENABLE_AUTO_SYNC:
                await run_sync()
        except asyncio.CancelledError:
            logger.info("Sync loop cancelled")
            break
        except Exception as e:
            logger.error(f"Error in sync loop: {e}", exc_info=True)
