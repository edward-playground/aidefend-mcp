# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AIDEFEND MCP Service is a **local, decentralized RAG engine** for the AIDEFEND AI security framework. It provides secure, private access to AI defense knowledge without external API calls.

**Dual-mode architecture:**
- **REST API mode** (FastAPI): For system integration and HTTP clients
- **MCP mode** (stdio): For Claude Desktop and MCP-compatible AI assistants

**Key features:**
- 100% local processing - all queries processed on-machine, never sent to external services
- Multilingual support (100+ languages via `Xenova/multilingual-e5-base` Quantized Int8)
- Auto-sync from GitHub repository (hourly checks)
- Vector search with LanceDB + FastEmbed (ONNX-based, 75% smaller with quantization)
- 18 security tools (3 basic + 15 specialized P0 tools) for comprehensive AI security analysis

## Quick Reference

**Essential commands:**
```bash
python __main__.py              # Start REST API (http://127.0.0.1:8000)
python __main__.py --mcp        # Start MCP mode (for Claude Desktop)
python __main__.py --resync     # Force database rebuild
pytest                          # Run all tests
pytest -m "not slow"            # Fast test run
python scripts/install.py       # One-click installation
```

**Key files:**
- `__main__.py` - Entry point (mode selection via `--mcp` flag)
- `app/core.py` - QueryEngine (shared by both modes)
- `app/tools/` - All 18 security tools (framework-agnostic)
- `mcp_server.py` - MCP protocol implementation
- `app/main.py` - FastAPI REST API

## Architecture

### High-Level Flow

```
User Query → Entry Point (__main__.py)
                ↓
         Mode Selection
        /              \
   REST API        MCP Server
   (FastAPI)       (stdio)
        \              /
         QueryEngine (shared core)
              ↓
         LanceDB Vector Search
              ↓
    FastEmbed (ONNX embeddings)
              ↓
         Results
```

### Core Components

1. **`__main__.py`**: Unified entry point
   - Routes to REST API or MCP mode based on `--mcp` flag
   - Handles `--resync` for database cleanup

2. **`app/core.py`**: QueryEngine (shared by both modes)
   - Vector search with LanceDB
   - Embedding generation with FastEmbed
   - Read-write locking for concurrent access
   - Auto-detects embedding model from stored vectors

3. **`app/sync.py`**: Background sync service
   - Fetches latest AIDEFEND content from GitHub
   - Parses JavaScript files using Node.js subprocess
   - Embeds content and updates LanceDB
   - Uses asyncio.Lock for sync coordination

4. **`mcp_server.py`**: MCP protocol implementation
   - 18 security tools (3 basic + 15 specialized) for AI security analysis
   - Stdio transport for Claude Desktop integration
   - Shares QueryEngine with REST API for consistency

5. **`app/main.py`**: FastAPI REST API
   - HTTP endpoints mirroring MCP tools
   - Rate limiting, CORS, security headers
   - Auto-triggers sync on startup

6. **`app/tools/`**: P0 specialized tools (15 tools)
   - Each tool is a standalone module with framework-agnostic logic
   - Tools exposed via both REST API (`app/main.py`) and MCP (`mcp_server.py`)
   - See tool files for implementation details (e.g., `statistics.py`, `classify_threat.py`)

### Critical Architectural Constraints

**⚠️ MUST RUN WITH SINGLE WORKER (`API_WORKERS=1`)**

This is enforced in [app/config.py:155-160](app/config.py#L155-L160) (field definition) and [app/config.py:275-285](app/config.py#L275-L285) (validator). Running with multiple workers causes:
- Sync lock conflicts (file-based lock only works within single instance)
- LanceDB write conflicts (concurrent writes corrupt database)
- Stale data served by workers after sync

For horizontal scaling in production:
- Deploy multiple independent instances behind a load balancer
- Each instance runs with `API_WORKERS=1`
- Use separate sync service/cron job for shared database

**⚠️ PATH RESOLUTION MUST USE PROJECT_ROOT**

All file paths in [app/config.py:17-83](app/config.py#L17-L83) are resolved relative to `PROJECT_ROOT` (not current working directory).

**Why this is critical:**
- When launched from command line: `cwd = project root` ✅
- When launched by Claude Desktop/Code: `cwd ≠ project root` ❌

**Implementation:**
```python
# app/config.py
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# All paths use PROJECT_ROOT
DB_PATH: Path = Field(
    default=PROJECT_ROOT / "data" / "aidefend_kb.lancedb",
    description="LanceDB database path"
)
```

**Impact:**
- Ensures database is found regardless of launch method
- Critical for MCP mode (Claude Desktop/Code integration)
- Prevents "LanceDB not found" errors on cold start

## Development Commands

### Running the Service

**REST API mode** (default):
```bash
python __main__.py
```
- Access at: http://127.0.0.1:8000
- API docs: http://127.0.0.1:8000/docs

**MCP mode** (for Claude Desktop):
```bash
# One-click installation (recommended)
python scripts/install.py

# Then restart Claude Desktop
```
- Checks Python/Node.js versions
- Installs all dependencies automatically
- Auto-detects paths and safely merges configuration
- Preserves existing MCP tools
- See [INSTALL.md](INSTALL.md) for details

**Manual MCP mode** (for testing):
```bash
python __main__.py --mcp
```

**Force resync** (cleanup and fresh sync):
```bash
python __main__.py --resync
```
- Deletes `data/aidefend_kb.lancedb` and `data/local_version.json`
- Use when upgrading embedding models or fixing database corruption

### Testing

**Run all tests:**
```bash
pytest
```

**Run specific test file:**
```bash
pytest tests/test_parser.py
```

**Run with coverage:**
```bash
pytest --cov=app --cov-report=html
```

**Test markers:**
```bash
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m "not slow"    # Skip slow tests
```

### Code Quality

**Format code:**
```bash
black app/
isort app/
```

**Lint:**
```bash
flake8 app/
mypy app/
```

**Security scanning:**
```bash
bandit -r app/         # Static security analysis
safety check           # Dependency vulnerability scanning
```

### Node.js Dependency

**Required for JavaScript parsing:**
```bash
node --version  # Verify Node.js installed (v18+)
npm install     # Install acorn parser
```

The service uses Node.js subprocess to parse AIDEFEND `.js` files via [parse_js_module.mjs](parse_js_module.mjs).

### Installation and MCP Setup

**One-click installation** (v2.0):
```bash
python scripts/install.py                      # Interactive (Claude Desktop, recommended)
python scripts/install.py --client desktop     # Configure Claude Desktop only
python scripts/install.py --client code        # Configure Claude Code (VSCode) only
python scripts/install.py --client both        # Configure both clients
python scripts/install.py --auto               # Non-interactive
python scripts/install.py --no-mcp             # Skip MCP, only install dependencies
python scripts/install.py --dry-run            # Preview without making changes
python scripts/install.py --check              # Check prerequisites only (no install)
```

This script:
- Checks system requirements (Python 3.9+, Node.js 18+)
- Installs Python dependencies (pip install -r requirements.txt)
- Installs Node.js dependencies (npm install)
- Configures MCP clients (Claude Desktop and/or Claude Code)

**Uninstall MCP configuration:**
```bash
python scripts/uninstall_mcp.py
```

**Other useful scripts:**
```bash
python scripts/generate_api_key.py      # Generate API key for REST API auth
python scripts/benchmark_search.py      # Performance benchmarking
python scripts/create_lancedb_index.py  # Create IVF_PQ index (2-5x speedup)
```

## Key Implementation Patterns

### 1. Dual-Mode Tool Implementation

All P0 tools follow this pattern:
- **Core logic** in `app/tools/{tool_name}.py` (framework-agnostic)
- **REST API endpoint** in `app/main.py` (FastAPI decorator)
- **MCP handler** in `mcp_server.py` (MCP protocol wrapper)

Example: [app/tools/statistics.py](app/tools/statistics.py) provides `get_statistics()` function, exposed via:
- REST: `GET /api/v1/statistics` in [app/main.py](app/main.py)
- MCP: `get_statistics` tool in [mcp_server.py](mcp_server.py)

### 2. QueryEngine Lazy Initialization

[app/core.py:360](app/core.py#L360) implements lazy loading via `initialize()` method:
- QueryEngine created on module import
- Database/model loaded on first `initialize()` call
- Handles cold start (no database) vs warm start (existing database)
- Auto-detects embedding model from stored vectors

### 3. Sync Locking Pattern

[app/sync.py:42-175](app/sync.py#L42-L175) uses `SyncFileLock` (file-based cross-process locking):
- OS-level locking (Windows: `msvcrt.locking`, Unix: `fcntl.flock`)
- Prevents concurrent syncs across processes and instances
- `is_sync_in_progress()` used by QueryEngine to block queries during sync

### 4. Security-First Input Validation

All user inputs validated via [app/security.py](app/security.py):
- `validate_query_text()`: Length, sanitization, injection prevention
- `validate_commit_sha()`: Prevent path traversal via malicious SHAs
- `validate_github_url()`: Whitelist GitHub domains only
- `validate_file_path()`: Prevent directory traversal attacks

### 5. Audit Logging

[app/audit.py](app/audit.py) provides tool-call auditing:
- `audit_tool_call()`: Log tool invocations with parameters (redacted)
- `audit_tool_completion()`: Log success/failure and result summary
- Used by all MCP tool handlers for observability

## Configuration

Environment variables loaded via [app/config.py](app/config.py) using Pydantic Settings.

**Key settings:**

| Variable | Default | Notes |
|----------|---------|-------|
| `AUTH_MODE` | `no_auth` | `no_auth` (dev) or `api_key` (prod) |
| `AIDEFEND_API_KEY` | `None` | Required when `AUTH_MODE=api_key` |
| `EMBEDDING_MODEL` | `Xenova/multilingual-e5-base` | ONNX model via FastEmbed (Quantized Int8, 280MB) |
| `EMBEDDING_DIMENSION` | `768` | Must match model dimension |
| `SYNC_INTERVAL_SECONDS` | `3600` | Auto-sync frequency (1 hour) |
| `API_WORKERS` | `1` | **MUST BE 1** - enforced by validator |
| `MAX_QUERY_LENGTH` | `1500` | Aligned with model's 512 token limit |
| `ENABLE_FUZZY_MATCHING` | `true` | Tier 2 typo-tolerant matching (free) |
| `FUZZY_MATCH_CUTOFF` | `0.70` | Minimum similarity score (0.0-1.0) |

**Configuration file:** Copy `.env.example` to `.env` and customize.

### Authentication Configuration

**REST API Mode** supports two authentication modes:

1. **`AUTH_MODE=no_auth`** (Default):
   - No authentication required
   - Suitable for local development on `127.0.0.1`
   - **Safety**: Service refuses to start if `API_HOST=0.0.0.0` with `no_auth`

2. **`AUTH_MODE=api_key`** (Production):
   - Requires API key in `X-API-Key` header
   - Generate key: `python scripts/generate_api_key.py`
   - Configure in `.env`: `AIDEFEND_API_KEY=<generated-key>`
   - See [SECURITY.md](SECURITY.md) for best practices

**MCP Mode** does not use HTTP authentication (secured via file permissions).

**Example API request with authentication:**
```bash
curl -H "X-API-Key: your-api-key" \
     -H "Content-Type: application/json" \
     -d '{"query_text": "prompt injection", "top_k": 5}' \
     http://localhost:8000/api/v1/query
```

## Database Schema (LanceDB)

**Table: `aidefend_kb`**

| Column | Type | Description |
|--------|------|-------------|
| `source_id` | String | Technique ID (e.g., `AID-H-001`) |
| `tactic` | String | Defense tactic (Model, Harden, Detect, etc.) |
| `type` | String | Document type (technique, subtechnique, strategy) |
| `name` | String | Human-readable name |
| `description` | String | Full text content |
| `text` | String | Searchable text (indexed) |
| `vector` | FixedSizeList[768] | Embedding vector |
| `pillar` | String | Defense pillar (prevent, detect, respond) |
| `phase` | String | SDLC phase (design, development, deployment) |
| `defends_against` | String | JSON string of threat mappings |
| Additional metadata fields | Various | Code blocks, tools, strategies, etc. |

**Accessing the database:**
```python
from app.core import query_engine
await query_engine.initialize()
table = query_engine._table  # LanceDB table instance
```

## Cache Schema Versioning

AIDEFEND MCP uses semantic versioning for cache schema to ensure data consistency and automatic invalidation when metadata formats change.

### Overview

The cache schema version (`CACHE_SCHEMA_VERSION` in [app/config.py](app/config.py)) tracks the structure of metadata stored in embeddings cache. When the version changes, the cache is automatically invalidated to prevent stale data issues.

**Key Benefits:**
- ✅ Zero manual intervention for users
- ✅ Automatic cache rebuild on metadata format changes
- ✅ Clear contract for breaking changes
- ✅ Production-grade reliability

### When to Increment Schema Version

Update `CACHE_SCHEMA_VERSION` in [app/config.py](app/config.py) when making these changes:

**MAJOR version** (e.g., 1.0 → 2.0): Breaking metadata changes
- Changing data types (string → array, array → object)
- Renaming metadata fields
- Removing fields
- Changing parsing logic that affects cached data
- Examples: pillar/phase string→array migration (v1.0)

**MINOR version** (e.g., 1.0 → 1.1): Additive changes (optional)
- Adding new optional metadata fields
- Adding new document types
- Non-breaking enhancements

### What Happens on Version Mismatch

When cache schema version ≠ code schema version:
1. ✅ Cache automatically invalidated (ignored, not deleted)
2. ✅ Fresh embeddings generated from GitHub
3. ✅ New cache created with current schema version
4. ✅ User sees log: `"Cache schema changed from 'X' to 'Y'. Invalidating cached entries."`

**No user action required** - the system handles everything automatically.

### Schema Version History

- **1.0** (2025-11): Initial versioned release
  - JSON arrays for pillar/phase (not comma-separated strings)
  - Strategies extracted from parent techniques (techniques without subtechniques)
  - Added `has_code_snippets` field

### Developer Guidelines

**✅ DO: Increment version for breaking changes**
```python
# Before changing metadata format in app/sync.py:
# 1. Update version in app/config.py
CACHE_SCHEMA_VERSION = "1.0"  # → "2.0"

# 2. Document the change in version history comments
# 2.0 (2025-12): Added threat severity scores to all techniques

# 3. Make your metadata changes
# Users will automatically get fresh cache on next sync
```

**❌ DON'T: Change metadata without incrementing version**
```python
# This causes users to get stale cached data!
# Always increment version when changing:
# - Field types or structure
# - Parsing logic
# - Required fields
```

**Example Workflow:**
```bash
# Developer makes breaking change to metadata format
# 1. Edit app/config.py
CACHE_SCHEMA_VERSION = "2.0"  # Increment

# 2. Make metadata changes in app/sync.py
# (e.g., change pillar from array to nested object)

# 3. User runs resync
python __main__.py --resync

# Output shows:
# "Cache schema changed from '1.0' to '2.0'"
# "Invalidating 549 cached entries"
# Fresh data loaded automatically ✅
```

### Testing Schema Changes

Run schema versioning tests:
```bash
pytest tests/test_schema_versioning.py -v
```

Tests verify:
- ✅ Version mismatch invalidates cache
- ✅ Version match preserves cache
- ✅ New cache includes schema version
- ✅ Save/load cycle persists version

### Implementation Details

**Files involved:**
- [app/config.py](app/config.py): `CACHE_SCHEMA_VERSION` constant
- [app/embedding_cache.py](app/embedding_cache.py): Version checking logic
- [app/sync.py](app/sync.py): Logs schema version at startup
- [tests/test_schema_versioning.py](tests/test_schema_versioning.py): Test suite

**Cache structure with schema version:**
```json
{
  "cache_version": "1.0",
  "schema_version": "1.0",
  "model_name": "Xenova/multilingual-e5-base",
  "model_dimension": 768,
  "embeddings": { ... },
  "metadata": { ... }
}
```

## Documentation Structure

**README.md** uses a compact, scannable format:
- Quick comparison table for mode selection (MCP/REST API/Docker)
- Collapsible `<details>` sections to minimize scrolling
- MCP mode prioritized with automated setup instructions
- Detailed manual setup instructions link to INSTALL.md

**When updating documentation:**
- Keep README.md concise (quick start focused)
- Put detailed instructions in INSTALL.md
- Maintain both English and Traditional Chinese versions
- Use tables and collapsible sections for better scannability

## Common Development Tasks

### Adding a New P0 Tool

1. **Create tool function** in `app/tools/{tool_name}.py`:
   ```python
   async def my_new_tool(param1: str, param2: int = 5) -> Dict[str, Any]:
       """Tool logic here."""
       # Access QueryEngine
       from app.core import query_engine
       await query_engine.initialize()

       # Perform operations
       results = await query_engine.search(...)

       # Return structured data
       return {"results": results, "total": len(results)}
   ```

2. **Add REST API endpoint** in [app/main.py](app/main.py):
   ```python
   @app.post("/api/v1/my-tool")
   async def my_tool_endpoint(param1: str, param2: int = 5):
       result = await my_new_tool(param1, param2)
       return result
   ```

3. **Add MCP tool handler** in [mcp_server.py](mcp_server.py):
   - Add tool definition in `list_tools()` (lines 68-625)
   - Add handler in `call_tool()` (lines 627-711)
   - Create `handle_my_new_tool()` async function

4. **Add tests** in `tests/test_my_tool.py`

5. **Update README.md** with tool documentation

### Modifying the Embedding Model

**⚠️ Changing the embedding model requires database rebuild:**

1. Update `EMBEDDING_MODEL` and `EMBEDDING_DIMENSION` in `.env`
2. Run force resync:
   ```bash
   python __main__.py --resync
   ```
3. Wait for re-embedding (may take several minutes)

**Note:** QueryEngine auto-detects model from stored vectors, so mismatched config will trigger warnings. Always resync after model changes.

### Debugging Sync Issues

**Check sync status:**
```bash
curl http://localhost:8000/api/v1/status
```

**View logs:**
```bash
tail -f data/logs/aidefend_mcp.log
```

**Common sync failures:**
1. **Missing Node.js:** Install Node.js v18+ and run `npm install`
2. **Network issues:** Check GitHub API access and HuggingFace model download
3. **Database locked:** Another process running - stop all instances
4. **Embedding model download failed:** Usually temporary HuggingFace outage - retry

**Manual sync trigger:**
```bash
curl -X POST http://localhost:8000/api/v1/sync
```

### Working with Git Commits

**Pre-commit security scanning:** GitHub Actions runs Bandit, Safety, and CodeQL on every commit. See [.github/workflows/security.yml](.github/workflows/security.yml).

**Commit message style:** Based on recent commits in `git log`:
- `Added tools and corresponding tests`
- `Minor bug fix on comprehensive search`
- `Fix - bug fixes`

Use imperative mood and keep concise.

## Testing Strategy

**Test structure** (see [pyproject.toml:122-141](pyproject.toml#L122-L141)):
- `tests/test_*.py` - individual tool tests
- Coverage target: 80%+ (`--cov=app`)
- Markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`

**Running tests in development:**
```bash
# Fast iteration - skip slow tests
pytest -m "not slow"

# Full test suite
pytest

# Debug specific test
pytest tests/test_parser.py -v -s
```

## Privacy & Security Notes

**100% Local Processing:**
- All threat classification uses local matching (static keywords + RapidFuzz fuzzy matching)
- No external API calls for any functionality
- Embedding generation uses local ONNX models (FastEmbed)
- Data never leaves your machine

**Security Layers:**
1. **Input validation:** All inputs sanitized and length-limited
2. **Rate limiting:** Configurable per-minute limits
3. **Audit logging:** All tool calls logged (sensitive data redacted)
4. **Path traversal protection:** Whitelist-based file access
5. **SSRF protection:** GitHub URLs only
6. **Security headers:** CSP, X-Frame-Options, HSTS

**See [SECURITY.md](SECURITY.md) for vulnerability reporting and deployment best practices.**

## Integration with AIDEFEND Framework

**Source repository:** https://github.com/edward-playground/aidefense-framework

**Sync process:**
1. Fetch latest commit SHA from GitHub API
2. Download `.js` files from `tactics/` directory
3. Parse JavaScript modules using Node.js subprocess ([parse_js_module.mjs](parse_js_module.mjs))
4. Extract techniques, sub-techniques, and strategies
5. Generate embeddings using FastEmbed
6. Store in LanceDB with metadata

**Framework version extraction:** Parsed from `aidefend-intro.js` (format: `1.YYYYMMDD`)

## Troubleshooting

**Service won't start:**
- Check `python __main__.py` output for errors
- Verify Node.js installed: `node --version`
- Check logs: `tail -f data/logs/aidefend_mcp.log`

**Queries return "Service not ready":**
- Initial sync in progress - wait for completion
- Check status: `curl http://localhost:8000/api/v1/status`
- Database corrupted - run `python __main__.py --resync`

**MCP tools not visible in Claude Desktop:**
- Verify `claude_desktop_config.json` paths are absolute (not relative)
- Check Python path: `where python` (Windows) or `which python3` (Unix)
- Restart Claude Desktop completely
- Test MCP manually: `python __main__.py --mcp`

**Slow queries:**
- Cold start triggers blocking sync (30-60 seconds)
- After warm start, queries should be <1 second
- Check database size: Large databases may need indexing optimization

## References

- **README.md**: User-facing documentation with full tool examples
- **INSTALL.md**: Detailed installation and MCP configuration guide
- **SECURITY.md**: Security best practices and vulnerability reporting
- **pyproject.toml**: Python project configuration and tool settings
