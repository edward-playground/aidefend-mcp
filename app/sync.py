"""
Synchronization service for AIDEFEND framework content.
Handles GitHub sync, parsing, embedding, and indexing with security.
"""

import asyncio
import httpx
import lancedb
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from fastembed import TextEmbedding

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
    parse_js_file_with_regex,
    save_version_info,
    get_local_commit_sha,
    format_bytes
)

logger = get_logger(__name__)

# Sync lock configuration
LOCK_FILE = settings.DATA_PATH / ".sync.lock"
LOCK_TIMEOUT_SECONDS = 1800  # 30 minutes

# Global state for last sync error
_last_sync_error: Optional[str] = None


def _acquire_sync_lock() -> bool:
    """
    Acquire sync lock using atomic file creation.

    Returns:
        True if lock acquired, False if another process holds the lock
    """
    try:
        # Check if stale lock exists (older than timeout)
        if LOCK_FILE.exists():
            lock_age = time.time() - LOCK_FILE.stat().st_mtime
            if lock_age > LOCK_TIMEOUT_SECONDS:
                logger.warning(
                    f"Removing stale lock file (age: {lock_age:.0f}s)",
                    extra={"lock_age_seconds": lock_age, "timeout": LOCK_TIMEOUT_SECONDS}
                )
                LOCK_FILE.unlink(missing_ok=True)
            else:
                logger.info("Sync already in progress (lock file exists)")
                return False

        # Try to create lock file atomically
        # Using 'x' mode fails if file exists, making this atomic
        with open(LOCK_FILE, 'x') as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()}\n")

        logger.info("Acquired sync lock")
        return True

    except FileExistsError:
        # Another process created the lock between our check and creation
        logger.info("Sync already in progress (lock acquired by another process)")
        return False
    except Exception as e:
        logger.error(f"Error acquiring sync lock: {e}")
        return False


def _release_sync_lock() -> None:
    """Release sync lock by removing lock file."""
    try:
        LOCK_FILE.unlink(missing_ok=True)
        logger.info("Released sync lock")
    except Exception as e:
        logger.warning(f"Error releasing sync lock: {e}")


def is_sync_in_progress() -> bool:
    """
    Check if sync is currently running by checking lock file existence.

    Returns:
        True if lock file exists and is not stale
    """
    if not LOCK_FILE.exists():
        return False

    # Check if lock is stale
    try:
        lock_age = time.time() - LOCK_FILE.stat().st_mtime
        if lock_age > LOCK_TIMEOUT_SECONDS:
            logger.warning(f"Stale lock detected (age: {lock_age:.0f}s)")
            return False
        return True
    except Exception as e:
        logger.error(f"Error checking lock file: {e}")
        return False


def get_last_sync_error() -> Optional[str]:
    """Get last sync error message."""
    return _last_sync_error


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
        parsed_data = parse_js_file_with_regex(file_path)

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

        # Document for technique
        tech_text = f"Technique: {tech_name}\nID: {tech_id}\nDescription: {tech_desc}"
        documents.append({
            "text": tech_text,
            "source_id": tech_id,
            "tactic": tactic_name,
            "type": "technique",
            "name": tech_name,
            "pillar": technique.get("pillar", ""),
            "phase": technique.get("phase", "")
        })

        # Documents for sub-techniques
        for sub_tech in technique.get("subTechniques", []):
            sub_id = sub_tech.get("id", "Unknown")
            sub_name = sub_tech.get("name", "Unknown")
            sub_desc = sub_tech.get("description", "")
            sub_pillar = sub_tech.get("pillar", "")
            sub_phase = sub_tech.get("phase", "")

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
                "phase": sub_phase
            })

            # Documents for implementation strategies
            for i, strategy in enumerate(sub_tech.get("implementationStrategies", []), 1):
                strategy_name = strategy.get("strategy", "Strategy")
                how_to = strategy.get("howTo", "")

                # Remove HTML tags from howTo for better embedding
                import re
                clean_how_to = re.sub(r'<[^>]+>', ' ', how_to)
                clean_how_to = ' '.join(clean_how_to.split())  # Normalize whitespace

                strategy_id = f"{sub_id}.S{i}"
                strategy_text = (
                    f"Implementation Strategy for {sub_name}\n"
                    f"Strategy: {strategy_name}\n"
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
                    "phase": sub_phase
                })

    logger.info(
        f"Extracted {len(documents)} documents from {tactic_name}",
        extra={"tactic": tactic_name, "doc_count": len(documents)}
    )

    return documents


async def embed_and_index(documents: List[Dict[str, Any]]) -> bool:
    """
    Embed documents and store in LanceDB.

    Args:
        documents: List of document dicts

    Returns:
        True if successful, False otherwise
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

        # Prepare LanceDB records
        records = []
        for i, doc in enumerate(documents):
            records.append({
                "vector": embeddings[i].tolist(),
                "text": doc["text"],
                "source_id": doc["source_id"],
                "tactic": doc["tactic"],
                "type": doc["type"],
                "name": doc["name"],
                "pillar": doc.get("pillar", ""),
                "phase": doc.get("phase", "")
            })

        # Connect to LanceDB
        logger.info(f"Connecting to LanceDB: {settings.DB_PATH}")
        db = await asyncio.to_thread(lancedb.connect, str(settings.DB_PATH))

        # Drop existing table if exists
        try:
            await asyncio.to_thread(db.drop_table, "aidefend")
            logger.info("Dropped existing 'aidefend' table")
        except Exception:
            logger.info("No existing 'aidefend' table to drop")

        # Create new table with explicit schema
        logger.info(f"Creating 'aidefend' table with {len(records)} records...")

        await asyncio.to_thread(
            db.create_table,
            "aidefend",
            data=records
        )

        logger.info("Successfully indexed all documents in LanceDB")

        # Set secure permissions on database directory
        db_dir = settings.DB_PATH
        if db_dir.exists():
            for file in db_dir.rglob("*"):
                if file.is_file():
                    set_secure_file_permissions(file)

        return True

    except Exception as e:
        logger.error(f"Failed to embed and index documents: {e}", exc_info=True)
        return False


async def run_sync() -> bool:
    """
    Execute complete sync process with file-based locking.

    Returns:
        True if sync successful, False otherwise
    """
    global _last_sync_error

    # Try to acquire lock
    if not _acquire_sync_lock():
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

        # Parse all files
        all_documents = []
        for file_path in downloaded_files:
            # Use asyncio.to_thread to avoid blocking the event loop
            # (parse_tactic_file involves file I/O and CPU-intensive regex operations)
            tactic_data = await asyncio.to_thread(parse_tactic_file, file_path)
            if tactic_data:
                # Use asyncio.to_thread for extract_documents_from_tactic as well
                # (involves CPU-intensive data transformation)
                documents = await asyncio.to_thread(extract_documents_from_tactic, tactic_data)
                all_documents.extend(documents)
            else:
                error_msg = f"Failed to parse {file_path.name}"
                logger.error(error_msg)
                _last_sync_error = error_msg
                return False

        logger.info(f"Total documents extracted: {len(all_documents)}")

        if not all_documents:
            error_msg = "No documents extracted from files"
            logger.error(error_msg)
            _last_sync_error = error_msg
            return False

        # Embed and index
        success = await embed_and_index(all_documents)
        if not success:
            error_msg = "Failed to embed and index documents"
            _last_sync_error = error_msg
            return False

        # Save version info
        save_version_info(
            latest_sha,
            {"total_documents": len(all_documents)}
        )

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
