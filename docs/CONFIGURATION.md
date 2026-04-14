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

## Critical: Single Worker Limitation

**⚠️ This service requires `API_WORKERS=1`**

The sync architecture uses file-based locking and in-memory state management that requires a single worker process. Running with `API_WORKERS > 1` will cause:

- Sync conflicts and race conditions
- Stale data served by some workers after sync
- Inconsistent query results

### Production Horizontal Scaling

If you need horizontal scaling for production:

1. **Deploy multiple independent instances** behind a load balancer
2. **Use a separate sync service/cron job** to update a shared database
3. **Each API instance runs with `API_WORKERS=1`**

**Example architecture:**
```
Load Balancer
   ├─ Instance 1 (API_WORKERS=1)
   ├─ Instance 2 (API_WORKERS=1)
   └─ Instance 3 (API_WORKERS=1)
         ↓
   Shared LanceDB
         ↑
   Separate Sync Service
```

## Authentication Configuration

### Development Mode (`AUTH_MODE=no_auth`)

**Default mode for local development:**

- No authentication required
- Suitable for local development on `127.0.0.1`
- **Safety**: Service refuses to start if `API_HOST=0.0.0.0` with `no_auth`

```bash
AUTH_MODE=no_auth
API_HOST=127.0.0.1  # Required for no_auth mode
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

## 100% Local Processing - Privacy Guaranteed

**This service is COMPLETELY LOCAL and PRIVATE:**

✅ **Zero External API Calls**
- All threat classification happens locally using 2-tier matching (static + RapidFuzz)
- All knowledge base queries processed on your machine
- Embedding generation uses local ONNX models (FastEmbed)
- No data ever leaves your infrastructure

✅ **FREE - No API Costs**
- No API keys required for any functionality
- No token consumption
- Zero ongoing costs

✅ **Works 100% Offline**
- After initial sync from GitHub, works completely offline
- No internet connection needed for queries
- Perfect for air-gapped/restricted environments

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
- **Performance**: Fast on CPU (~500-1000ms per query)
- **Accuracy**: High semantic matching quality
- **License**: MIT (commercial-friendly)

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

### GPU Acceleration (Optional)

For faster embedding generation, see [GPU Acceleration Guide](advanced/GPU_ACCELERATION.md).

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
SYNC_INTERVAL_SECONDS=0  # Manual sync only via API/MCP
```

**Force sync on startup:**
```bash
python __main__.py --resync
```

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
SYNC_INTERVAL_SECONDS=0  # No auto-sync
```

## Troubleshooting

### Config not loading

1. Check `.env` file exists in project root
2. Verify no syntax errors in `.env`
3. Restart service after changes

### Worker conflicts

**Error:** `Sync conflicts detected`

**Solution:** Ensure `API_WORKERS=1` in `.env`

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
