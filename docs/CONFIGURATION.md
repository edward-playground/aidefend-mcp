# AIDEFEND MCP Service - Configuration Guide

Complete configuration reference for the AIDEFEND MCP Service.

## Environment Variables

All configuration is done via environment variables. Copy `.env.example` to `.env` and customize as needed.

```bash
cp .env.example .env
```

## Key Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_MODE` | `no_auth` | Authentication mode: `no_auth` (dev) or `api_key` (prod) |
| `AIDEFEND_API_KEY` | `None` | API key for authentication (required when `AUTH_MODE=api_key`) |
| `SYNC_INTERVAL_SECONDS` | `3600` | How often to check for updates (1 hour) |
| `API_HOST` | `127.0.0.1` | Host to bind the API server (use `0.0.0.0` for external access) |
| `API_PORT` | `8000` | Port to run the API server on |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `ENABLE_RATE_LIMITING` | `true` | Enable rate limiting on API endpoints |
| `RATE_LIMIT_PER_MINUTE` | `60` | Max requests per minute per IP |
| `MAX_QUERY_LENGTH` | `1500` | Maximum query text length (aligned with embedding model limit) |
| `MAX_TOTAL_QUERY_LENGTH` | `5000` | Maximum total query length for chunked search |
| `MAX_CHUNKS` | `5` | Maximum number of chunks per query |
| `MAX_CHUNKS_PROCESSING_TIME` | `15` | Timeout for chunked queries in seconds |
| `CHUNK_SIZE` | `1200` | Target size for each chunk in characters |
| `CHUNK_OVERLAP` | `200` | Overlap between chunks to preserve context |
| `EMBEDDING_MODEL` | `Xenova/multilingual-e5-base` | ONNX embedding model via FastEmbed |
| `EMBEDDING_DIMENSION` | `768` | Must match model dimension |
| `API_WORKERS` | `1` | ⚠️ **Must be 1** - Multi-worker mode not supported |
| `ENABLE_FUZZY_MATCHING` | `true` | Enable Tier 2 fuzzy matching for typo tolerance (100% local) |
| `FUZZY_MATCH_CUTOFF` | `0.70` | Minimum similarity score for fuzzy matches (0.0-1.0) |
| `LOCAL_FRAMEWORK_PATH` | `None` | Optional local framework checkout path. Leave unset to sync from GitHub. |

### Storage Paths

A source checkout keeps the historical repository-local data directory. An
installed wheel uses a per-user writable location instead of site-packages:

- Windows: %LOCALAPPDATA%\AIDEFEND\aidefend-mcp
- macOS: ~/Library/Application Support/aidefend-mcp
- Linux: $XDG_DATA_HOME/aidefend-mcp, or ~/.local/share/aidefend-mcp
- Docker: /app/data

Setting DATA_PATH also derives DB_PATH, RAW_PATH, VERSION_FILE, and LOG_PATH
unless those fields are explicitly set. In a source checkout, relative storage
overrides resolve from the repository root. In an installed wheel, they resolve
under the per-user AIDEFEND data directory and never under site-packages.

### Runtime Storage Ownership

A configured `DATA_PATH` is a single-process ownership boundary. At most one
REST service, stdio MCP server, `--resync` command, or maintenance process may
open that runtime storage at a time. The process keeps an operating-system lock
on `DATA_PATH/sync.lock` while it owns the data directory; lock contention must
be resolved by stopping the current owner, not by removing the file.

The `sync.lock` file is a stable rendezvous file. Its presence does **not** mean
that a process still owns the lock, and an old timestamp does not prove that it
is safe to delete. The operating-system lock is authoritative. Never manually
delete or replace `sync.lock` to force a service or resync to start.

If REST and MCP must run at the same time, give them different `DATA_PATH`
values and independent storage. Keep each instance's `DB_PATH`, `RAW_PATH`, and
`VERSION_FILE` aligned with its own data directory; do not point two otherwise
separate instances at any of the same runtime paths.

## Critical: Single Data Owner and Worker

**⚠️ This service requires `API_WORKERS=1`**

The local LanceDB architecture combines a lifetime data-directory lease with
in-memory query state, so one configured data directory supports one process
and one API worker. Running with `API_WORKERS > 1`, starting REST and MCP over
the same paths, or mounting one writable data volume into several replicas is
unsupported because it can cause:

- Sync conflicts and race conditions
- Stale data served by some workers after sync
- Inconsistent query results

### Production Horizontal Scaling

If you need horizontal scaling for production:

1. **Give every instance its own complete data directory or persistent volume**
2. **Keep `DB_PATH`, `RAW_PATH`, and `VERSION_FILE` private to that instance**
3. **Run every API instance with `API_WORKERS=1`**
4. **Or replace local storage with an external data layer designed and tested
   for concurrent clients** before sharing state

Do not place the current local LanceDB directory on one shared writable volume
and attach it to several service replicas. A separate sync process also cannot
update a local database while another process is serving it.

**Example architecture:**
```
Load Balancer
   ├─ Instance 1 (API_WORKERS=1) → Data copy / volume 1
   ├─ Instance 2 (API_WORKERS=1) → Data copy / volume 2
   └─ Instance 3 (API_WORKERS=1) → Data copy / volume 3
```

An external database or retrieval service may be used for a different scaling
architecture, but that is a separate deployment design; the bundled local
LanceDB files are not a shared multi-replica storage layer.

## Authentication Configuration

### Development Mode (`AUTH_MODE=no_auth`)

**Default mode for local development:**

- No authentication required
- Suitable only for local development on `localhost`, `127.0.0.0/8`, or `::1`
- **Safety**: Wildcard, LAN/public IP, empty, and unknown hostname bindings are
  rejected when `AUTH_MODE=no_auth`

```bash
AUTH_MODE=no_auth
API_HOST=127.0.0.1  # Any explicit loopback IP, or localhost
```

### Production Mode (`AUTH_MODE=api_key`)

**Required for production deployments:**

1. **Generate API key:**
   ```bash
   python scripts/generate_api_key.py
   ```

2. **Configure in `.env`:**
   ```bash
   AUTH_MODE=api_key
   AIDEFEND_API_KEY=your-generated-key-here
   API_HOST=0.0.0.0  # Allow external access
   ```

3. **Use in API requests:**
   ```bash
   curl -H "X-API-Key: your-api-key" \
        -H "Content-Type: application/json" \
        -d '{"query_text": "prompt injection"}' \
        http://localhost:8000/api/v1/query
   ```

**See [SECURITY.md](../SECURITY.md) for best practices.**

## Local Query Processing and Network Boundaries

**User query processing stays on the configured host:**

✅ **No External Inference API Calls**
- All threat classification happens locally using 2-tier matching (static + RapidFuzz)
- All knowledge base queries processed on your machine
- Embedding generation uses local ONNX models (FastEmbed)
- Query content is not sent to GitHub or Hugging Face
- Initial framework synchronization uses GitHub, and initial model acquisition may use Hugging Face

✅ **No Third-Party Inference API Costs**
- No third-party inference API key is required; REST authentication can still require your locally configured `API_KEY`
- No token consumption
- No usage-based fee from this project

✅ **Offline Query Operation After Setup**
- After framework data and the model are present locally, queries work offline
- No internet connection needed for queries
- Air-gapped environments must pre-stage all required framework and model assets

✅ **Privacy First**
- Your queries, data, and threat intelligence stay on your machine
- No telemetry, no tracking, no external logging
- Compliance-friendly for regulated industries (healthcare, finance, government)

**Architecture Flow:**
```
Your Query → Local Matching Engine (Tier 1: Static, Tier 2: RapidFuzz)
           ↓
Local Vector DB (LanceDB) → Local Embedding Model (FastEmbed/ONNX)
           ↓
Results (100% processed on your machine) ✅
```

## Embedding Models

### Default Model

```bash
EMBEDDING_MODEL=Xenova/multilingual-e5-base
EMBEDDING_DIMENSION=768
```

For advanced usage (changing models, custom ONNX models), see [Advanced Configuration](ADVANCED_CONFIGURATION.md).

**Features:**
- **Multilingual**: Supports 100+ languages
- **Performance**: Runs locally on CPU; measure representative queries on the
  target host because latency depends on hardware, cache state, and workload
- **Accuracy**: High semantic matching quality
- **Service code license**: MIT; synchronized framework content remains CC BY 4.0

### Changing Models

**⚠️ Changing the embedding model requires database rebuild:**

1. Update `.env`:
   ```bash
   EMBEDDING_MODEL=your-new-model
   EMBEDDING_DIMENSION=your-new-dimension
   ```

2. Force resync:
   ```bash
   python __main__.py --resync
   ```

3. Wait for re-embedding (may take several minutes)

### GPU Acceleration Status

AIDEFEND MCP 1.3.0 supports `fastembed==0.8.0` with the project's declared CPU
`onnxruntime` dependency. GPU and accelerator-specific package substitutions
are not supported or release-tested. Do not replace the declared CPU packages
with GPU variants. See [GPU Acceleration Status](advanced/GPU_ACCELERATION.md)
for the dependency boundary and future support requirements.

## Rate Limiting

Configure rate limiting to protect against abuse:

```bash
ENABLE_RATE_LIMITING=true
RATE_LIMIT_PER_MINUTE=60  # Max 60 requests per minute per IP
```

**Bypass rate limiting (not recommended):**
```bash
ENABLE_RATE_LIMITING=false
```

## Logging

```bash
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

**Log file location:** `./data/logs/aidefend_mcp.log`

**Log format:** Structured JSON for easy parsing

Example log entry:
```json
{
  "timestamp": "2025-11-20T10:30:00Z",
  "level": "INFO",
  "logger": "aidefend_mcp",
  "message": "Query completed",
  "module": "core",
  "function": "search",
  "extra": {
    "results_returned": 5,
    "top_score": 0.234
  }
}
```

## Sync Configuration

```bash
SYNC_INTERVAL_SECONDS=3600  # Auto-sync every hour
```

**Disable auto-sync:**
```bash
ENABLE_AUTO_SYNC=false  # Manual sync only via API/MCP
```

**Force sync on startup:**
```bash
python __main__.py --resync
```

Run `--resync` only when no REST server, MCP server, or other maintenance
command owns the same `DATA_PATH`. For a running service, use its MCP sync tool
or REST sync endpoint instead of starting a second process against its files.

### Upgrading to the Lifetime-Lock Release

Before upgrading an installation from a version that did not hold the data-path
lock for the complete service lifetime:

1. Stop the REST service.
2. Close every MCP client that can launch the AIDEFEND stdio server.
3. Wait for any resync or maintenance command to finish.
4. Upgrade the service, then start only one process for that `DATA_PATH`.

An older running service cannot be assumed to participate in the new lifetime
lock contract. Stopping all old processes is therefore a required upgrade step,
not an optional stale-lock cleanup.

## Advanced Configuration

### Chunked Search

For long queries, the service automatically chunks text while preserving sentence boundaries:

```bash
MAX_TOTAL_QUERY_LENGTH=5000  # Maximum total query length
MAX_CHUNKS=5                 # Maximum chunks per query
MAX_CHUNKS_PROCESSING_TIME=15  # Timeout in seconds
CHUNK_SIZE=1200              # Target chunk size
CHUNK_OVERLAP=200            # Overlap to preserve context
```

### Fuzzy Matching

Enable typo-tolerant matching using RapidFuzz (100% local):

```bash
ENABLE_FUZZY_MATCHING=true
FUZZY_MATCH_CUTOFF=0.70  # Minimum similarity score (0.0-1.0)
```

## Environment-Specific Configurations

### Development

`.env.development`:
```bash
AUTH_MODE=no_auth
API_HOST=127.0.0.1
API_PORT=8000
LOG_LEVEL=DEBUG
SYNC_INTERVAL_SECONDS=3600
```

### Production

`.env.production`:
```bash
AUTH_MODE=api_key
AIDEFEND_API_KEY=<generated-key>
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
SYNC_INTERVAL_SECONDS=3600
ENABLE_RATE_LIMITING=true
```

### Air-Gapped

`.env.airgapped`:
```bash
AUTH_MODE=no_auth
API_HOST=127.0.0.1
API_PORT=8000
LOG_LEVEL=INFO
ENABLE_AUTO_SYNC=false  # No auto-sync
```

## Troubleshooting

### Config not loading

1. Check `.env` file exists in project root
2. Verify no syntax errors in `.env`
3. Restart service after changes

### Worker conflicts

**Error:** `Sync conflicts detected`

**Solution:** Ensure `API_WORKERS=1` in `.env`

### Data directory already owned

**Error:** Startup or resync reports that another process owns the configured
data directory.

**Solution:** Stop the REST service, MCP server, resync, or maintenance process
that uses the same `DATA_PATH`. If both REST and MCP must remain active, assign
independent `DATA_PATH`, `DB_PATH`, `RAW_PATH`, and `VERSION_FILE` values. Do
not delete `sync.lock`; an unheld rendezvous file is harmless and reusable.

### Authentication failures

**Error:** `Invalid API key`

**Solution:**
1. Regenerate API key: `python scripts/generate_api_key.py`
2. Update `.env` with new key
3. Restart service

## Additional Resources

- **Main README**: [README.md](../README.md)
- **Installation Guide**: [INSTALL.md](../INSTALL.md)
- **Security Policy**: [SECURITY.md](../SECURITY.md)
- **Environment Example**: [.env.example](../.env.example)
