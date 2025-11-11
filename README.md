[English Readme](README.md) | [繁體中文 Readme](README-繁體中文.md)

---

# AIDEFEND MCP / REST API Service

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%20|%203.13-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121.1-009688.svg)](https://fastapi.tiangolo.com)
[![Security: Multiple Layers](https://img.shields.io/badge/security-multi--layer-success.svg)](./SECURITY.md)

A **local, decentralized RAG (Retrieval-Augmented Generation) engine** for the [AIDEFEND framework](https://github.com/edward-playground/aidefense-framework).
This service provides secure, private access to the AIDEFEND knowledge base without sending sensitive queries to external services. Two modes are supported:

- **REST API**: For custom applications and system integration.

- **MCP Server**: For native integration with AI assistants like Claude Desktop.

## Features

- **100% Private & Local**: All queries processed locally - your prompts never leave your infrastructure, works completely offline
- **Cost Efficient**: 25x token reduction vs sending full framework - drastically lower LLM API costs
- **Auto-Sync**: Automatically pulls latest AIDEFEND content from GitHub (hourly checks)
- **Fast Vector Search**: Powered by LanceDB for efficient semantic search (millisecond response times)
- **Security-First**: Comprehensive input validation, sanitization, and security headers
- **Docker Ready**: Easy deployment with Docker and docker-compose
- **Production Ready**: Health checks, rate limiting, structured logging, and monitoring
- **Defense in Depth**: Multiple security layers (see [SECURITY.md](./SECURITY.md))

## Why Use This MCP / REST API Service?

AIDEFEND is open source, so you *could* retrieve the framework content and build the query function yourself. But there's a huge gap between "possible" and "practical."

### The Problems This Solves

#### **Problem 1: Privacy Concerns with Cloud Services**

Most RAG services send your queries to cloud servers. Your sensitive prompts (security questions, proprietary info) leave your control.

**This MCP / REST API Service:**
- ✅ **100% local processing** - queries never leave your machine
- ✅ **Works offline** after initial sync
- ✅ **Zero tracking** - no telemetry, no external API calls

#### **Problem 2: LLMs Can't Handle the Full Framework**

AIDEFEND has thousands of lines. LLMs have token limits (~8K-128K). There are cases that you can't paste everything into ChatGPT.

**This MCP / REST API Service:**
- ✅ **Smart search** - finds the 3-5 most relevant sections in milliseconds
- ✅ **Only sends what you need** - no manual copy-pasting

#### **Problem 3: Building RAG is Complex**

To build this yourself, you'd need to:
- Write JavaScript parsers
- Set up vector databases (LanceDB, ChromaDB, Pinecone)
- Configure embedding models
- Handle updates manually (`git pull` → re-parse → re-embed)

**This MCP / REST API Service:**
- ✅ **One command**: `docker-compose up -d`
- ✅ **Auto-updates** every hour
- ✅ **Zero maintenance** required

#### **Problem 4: Token Costs Add Up Fast**

Sending the full framework = 50K+ tokens per query. Paid LLM APIs charge per token.

**This MCP / REST API Service:**
- ✅ **500-2K tokens per query** (25x reduction)
- ✅ **25x lower API costs** for paid LLMs (GPT-4, Claude)
- ✅ **Faster responses** - smaller context = quicker processing

### Quick Comparison

| Feature | DIY Build | Cloud RAG | This Service |
|---------|-----------|-----------|--------------|
| **Privacy** | Local (if you build it) | ❌ Cloud-based | ✅ 100% local |
| **Works Offline** | ❌ No | ❌ No | ✅ Yes |
| **Token Usage/Query** | 50K+ (wasteful) | High | ✅ 500-2K (25x less) |
| **Setup Time** | Days | Minutes | ✅ 5 minutes |
| **Auto-Updates** | ❌ Manual | ✅ Yes (cloud) | ✅ Yes (local) |
| **Maintenance** | High effort | Vendor-managed | ✅ Zero |
| **Cost** | Your time | $$/month | ✅ $0 |

### Bottom Line

Get a production-ready RAG system that:
- **Protects privacy** - 100% local processing
- **Saves money** - 25x less tokens = 25x lower API costs
- **Works offline** - no internet needed after setup
- **Auto-updates** - always current with latest research
- **Costs nothing** - free and open source

> **The AIDEFEND framework is the knowledge base. This service helps you to leverage AIDEFEND privately and efficiently.**

## Architecture

### Dual-Mode Design

This service supports **two modes** to fit different use cases:

1. **REST API Mode** - For system integration (existing applications, custom tools)
2. **MCP Mode** - For AI assistants (Claude Desktop, other MCP-compatible clients)

Both modes share the same core logic, ensuring consistent results.

```
┌─────────────────────────────────────────────────────────────┐
│                    AIDEFEND MCP Service                     │
│                      (Dual-Mode Support)                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐         ┌──────────────┐                  │
│  │              │         │              │                  │
│  │  Sync        │────────▶│  LanceDB     │                 │
│  │  Service     │  Index  │  Vector DB   │                  │
│  │              │         │              │                  │
│  └──────┬───────┘         └───────▲──────┘                  │
│         │                         │                         │
│         │ GitHub                  │ Query                   │
│         │ API                     │                         │
│         ▼                         │                         │
│  ┌──────────────┐         ┌──────┴──────┐                   │
│  │  AIDEFEND    │         │  Query      │                   │
│  │  Framework   │         │  Engine     │◀────┐            │
│  │  (GitHub)    │         │ (Shared)    │     │             │
│  └──────────────┘         └──────┬──────┘     │             │
│                                   │           │             │
│                          ┌────────┴────────┐  │             │
│                          │                 │  │             │
│                    ┌─────▼──────┐   ┌──────▼─────┐          │
│                    │  FastAPI   │   │ MCP Server │          │
│                    │  REST API  │   │  (stdio)   │          │
│                    └─────┬──────┘   └──────┬─────┘          │
│                          │                 │                │
└──────────────────────────┼─────────────────┼────────────────┘
                           │                 │
                  ┌────────┴────────┐ ┌──────┴──────┐
                  │  Your LLM       │ │   Claude    │
                  │  Application    │ │   Desktop   │
                  │  (HTTP Client)  │ │  (MCP)      │
                  └─────────────────┘ └─────────────┘
```

### When to Use Each Mode

| Use Case | Recommended Mode | Why |
|----------|------------------|-----|
| **Claude Desktop integration** | MCP Mode | Native tool support, no HTTP needed |
| **Custom scripts/automation** | REST API Mode | Standard HTTP, easy to integrate |
| **System integration** | REST API Mode | Works with any HTTP client |
| **AI assistant conversations** | MCP Mode | Optimized for AI assistant workflows |
| **Both simultaneously** | Run both! | They can coexist on the same machine |

## Prerequisites

- **Python 3.9 - 3.13** (tested on 3.13.6)
- **Node.js 18+** (required for parsing JavaScript files)
  - Download: https://nodejs.org/
  - Verify: `node --version`
- **Docker** (optional, for containerized deployment)
- **2GB RAM** minimum (4GB recommended)
- **500MB disk space** for models and data

## Quick Start

### Step 1: Installation (Common for Both Modes)

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd aidefend-mcp
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env if needed (optional)
   ```

### Step 2: Choose Your Mode

#### Option A: REST API Mode (For HTTP Integration)

**When to use:** You want to integrate with custom applications, scripts, or any HTTP client.

1. **Start the service**

   **Using the convenience script:**
   ```bash
   # On macOS/Linux:
   ./scripts/start.sh

   # On Windows:
   scripts\start.bat
   ```

   **Or start directly with Python:**
   ```bash
   python -m aidefend_mcp
   # Or equivalently:
   # python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

2. **Verify it's running**
   ```bash
   curl http://localhost:8000/health
   ```

3. **Access API docs**

   Open your browser: http://localhost:8000/docs

The service will automatically sync with GitHub and index the AIDEFEND framework on first run.

#### Option B: MCP Mode (For Claude Desktop)

**When to use:** You want Claude Desktop to access AIDEFEND knowledge directly as a tool.

1. **Configure Claude Desktop**

   Edit Claude Desktop's config file:
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

   Add this configuration:
   ```json
   {
     "mcpServers": {
       "aidefend": {
         "command": "python",
         "args": [
           "-m",
           "aidefend_mcp",
           "--mcp"
         ],
         "cwd": "/absolute/path/to/aidefend-mcp"
       }
     }
   }
   ```

   **Important:** Replace `/absolute/path/to/aidefend-mcp` with your actual directory path!

2. **Restart Claude Desktop**

   Close and reopen Claude Desktop completely.

3. **Verify connection**

   In Claude Desktop, you should see "aidefend" in the MCP tools list (look for the 🔌 icon). Try asking:
   ```
   "Can you search AIDEFEND for prompt injection defenses?"
   ```

   Claude will automatically use the `query_aidefend` tool to search the knowledge base.

**For detailed MCP setup instructions, see [INSTALL.md](INSTALL.md).**

#### Option C: Docker Deployment (REST API Mode)

1. **Build and run with docker-compose**
   ```bash
   docker-compose up -d
   ```

2. **Check logs**
   ```bash
   docker-compose logs -f
   ```

3. **Check status**
   ```bash
   curl http://localhost:8000/health
   ```

**Note:** MCP mode requires direct Python execution and cannot run in Docker (Claude Desktop needs direct stdio access).

## Usage Guide

### REST API Mode Usage

The REST API provides HTTP endpoints for integration with any application.

#### Query Endpoint

```bash
POST /api/v1/query
Content-Type: application/json

{
  "query_text": "How do I protect against prompt injection attacks?",
  "top_k": 5
}
```

**Example with curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "What are best practices for AI model hardening?",
    "top_k": 5
  }'
```

**Example Response:**
```json
{
  "query_text": "What are best practices for AI model hardening?",
  "context_chunks": [
    {
      "source_id": "AID-H-001.001",
      "tactic": "Harden",
      "text": "Sub-Technique: Input Validation\nDescription: Implement robust input validation...",
      "metadata": {
        "type": "subtechnique",
        "name": "Input Validation",
        "pillar": "app",
        "phase": "building"
      },
      "score": 0.234
    }
  ],
  "total_results": 5,
  "timestamp": "2025-11-09T10:30:00Z"
}
```

### Status Endpoint

```bash
GET /api/v1/status
```

Returns service status, sync information, and version details.

### Health Check

```bash
GET /health
```

Returns health status of all components (database, embedding model, sync service).

### Manual Sync Trigger

```bash
POST /api/v1/sync
```

Manually triggers a sync operation (rate limited to 5/minute).

---

### MCP Mode Usage

When running in MCP mode (`python -m aidefend_mcp --mcp`), the service provides tools for AI assistants like Claude Desktop.

#### Available MCP Tools

1. **query_aidefend** - Search the AIDEFEND knowledge base
2. **get_aidefend_status** - Check service status and sync info
3. **sync_aidefend** - Manually trigger knowledge base sync

#### How to Use in Claude Desktop

Once configured, Claude Desktop can automatically use these tools when you ask AIDEFEND-related questions.

**Example Conversations:**

```
You: "How do I defend against prompt injection attacks?"

Claude: [Uses query_aidefend tool automatically]
       Based on the AIDEFEND framework, here are the key defenses...
```

```
You: "What's the status of the AIDEFEND knowledge base?"

Claude: [Uses get_aidefend_status tool]
       The AIDEFEND service has 42 indexed documents...
```

```
You: "Can you sync the latest AIDEFEND tactics?"

Claude: [Uses sync_aidefend tool]
       Syncing with GitHub... The knowledge base has been updated successfully!
```

#### Using Tools Explicitly

You can also ask Claude to use specific tools:

```
You: "Use the query_aidefend tool to search for 'model poisoning defenses'"

Claude: [Calls query_aidefend with your exact query]
```

#### MCP Tool Schemas

For developers integrating with other MCP clients, here are the tool schemas:

**query_aidefend:**
```json
{
  "name": "query_aidefend",
  "description": "Search the AIDEFEND AI security defense knowledge base...",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Your search query in natural language"
      },
      "top_k": {
        "type": "number",
        "description": "Number of results to return (default: 5, max: 20)",
        "default": 5
      }
    },
    "required": ["query"]
  }
}
```

**get_aidefend_status:**
```json
{
  "name": "get_aidefend_status",
  "description": "Get the current status of the AIDEFEND knowledge base...",
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

**sync_aidefend:**
```json
{
  "name": "sync_aidefend",
  "description": "Manually trigger synchronization with the AIDEFEND GitHub repository...",
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": []
  }
}
```

## Configuration

All configuration is done via environment variables. See [.env.example](./.env.example) for all options.

### Key Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNC_INTERVAL_SECONDS` | `3600` | How often to check for updates (1 hour) |
| `API_PORT` | `8000` | Port to run the API server on |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `ENABLE_RATE_LIMITING` | `true` | Enable rate limiting on API endpoints |
| `RATE_LIMIT_PER_MINUTE` | `60` | Max requests per minute per IP |
| `MAX_QUERY_LENGTH` | `2000` | Maximum query text length |
| `API_WORKERS` | `1` | ⚠️ **Must be 1** - Multi-worker mode not supported |

### Important: Single Worker Limitation

**⚠️ This service requires `API_WORKERS=1`**

The sync architecture uses file-based locking and in-memory state management that requires a single worker process. Running with `API_WORKERS > 1` will cause:

- Sync conflicts and race conditions
- Stale data served by some workers after sync
- Inconsistent query results

**For production deployments**, if you need horizontal scaling:
- Deploy multiple independent instances behind a load balancer
- Use a separate sync service/cron job to update a shared database
- Each API instance runs with `API_WORKERS=1`

## Security

As an MCP service for an AI security framework, this service itself implements multiple security layers:

- **Local-First Processing**: All queries processed locally - your data never leaves your infrastructure
- **Input Validation**: Comprehensive validation and sanitization of all inputs
- **Rate Limiting**: Protection against abuse and DoS attacks
- **Secure Operations**: Path traversal prevention, file security, and permission controls
- **Network Security**: SSRF protection, URL validation, and security headers
- **Container Hardening**: Non-root user, minimal privileges, and secure defaults
- **Audit Logging**: Structured logs with automatic sensitive data filtering

**For security issues, vulnerability reporting, and deployment best practices, see [SECURITY.md](./SECURITY.md).**

## Monitoring & Logs

### Health Check Endpoint

The `/health` endpoint provides comprehensive service health status:

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",  // or "degraded", "unhealthy"
  "checks": {
    "database": true,
    "embedding_model": true,
    "sync_service": true
  },
  "timestamp": "2025-11-11T00:00:00Z"
}
```

**Health Status Levels:**
- `healthy` - All systems operational, data is fresh
- `degraded` - System operational but data is stale (last sync > 2x sync interval)
- `unhealthy` - Critical component failure (database, embedding model)

**Stale Data Detection:**
The health check automatically detects if sync has failed for an extended period. If data age exceeds `2 × SYNC_INTERVAL_SECONDS`, status becomes `degraded` to alert monitoring systems.

### Structured Logging

Logs are written in JSON format to `./data/logs/aidefend_mcp.log`:

```json
{
  "timestamp": "2025-11-09T10:30:00Z",
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

### Health Monitoring

The `/health` endpoint provides component-level health checks:

```bash
curl http://localhost:8000/health
```

## Development

### Setup Development Environment

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Check code quality
black app/
flake8 app/
mypy app/

# Security scan
safety check
bandit -r app/
```

### Automated Security Scanning

This repository includes automated security scanning via GitHub Actions:

**🔒 Security Workflows (`.github/workflows/security.yml`)**
- **Bandit**: Static security analysis for Python code
- **Safety**: Dependency vulnerability scanning
- **CodeQL**: Advanced semantic code analysis

**Runs automatically on:**
- Every push to `main` or `develop` branches
- All pull requests
- Weekly schedule (Mondays at 00:00 UTC)
- Manual trigger via GitHub Actions UI

**📦 Dependabot (`.github/dependabot.yml`)**
- Automated dependency updates
- Weekly scans for Python packages and GitHub Actions
- Automatic pull requests for security patches
- Grouped updates for dev dependencies

**View security reports:** Check the "Security" tab in your GitHub repository.


### Project Structure

```
aidefend-mcp/
├── __main__.py          # Unified entry point (mode selection)
├── mcp_server.py        # MCP protocol server implementation
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application (REST API mode)
│   ├── config.py        # Configuration management
│   ├── core.py          # Query engine (shared by both modes)
│   ├── sync.py          # GitHub sync service
│   ├── schemas.py       # Pydantic models
│   ├── security.py      # Security validations
│   ├── logger.py        # Structured logging
│   └── utils.py         # Utility functions
├── scripts/             # Convenience scripts
│   ├── start.sh         # Quick start script (Unix)
│   └── start.bat        # Quick start script (Windows)
├── data/                # Auto-generated data directory
│   ├── raw_content/     # Downloaded .js files
│   ├── aidefend_kb.lancedb/  # Vector database
│   ├── local_version.json    # Sync version info
│   └── logs/            # Log files
├── tests/               # Test suite
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml       # Project configuration
├── .env.example
├── README.md
├── INSTALL.md           # Installation guide
└── SECURITY.md
```


## Troubleshooting

### Service won't start

1. **Check logs**
   ```bash
   tail -f data/logs/aidefend_mcp.log
   ```

2. **Verify network access to GitHub**
   ```bash
   curl https://api.github.com/repos/edward-playground/aidefense-framework/commits/main
   ```

### Queries return "Service not ready"

- The initial sync is still in progress. Check `/api/v1/status` for sync status.
- The database may be corrupted. Delete `data/` and restart the service.

### Rate limiting issues

Adjust `RATE_LIMIT_PER_MINUTE` in `.env` or disable with `ENABLE_RATE_LIMITING=false`.

### MCP Mode Issues

#### Claude Desktop doesn't show the tools

1. **Verify config file path**
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

2. **Check config syntax**
   - Must be valid JSON (use a JSON validator)
   - Use absolute paths, not relative paths
   - Ensure `cwd` points to the correct directory

3. **Restart Claude Desktop**
   - Completely quit and reopen the application
   - Check for error messages in Claude's console

4. **Test MCP server manually**
   ```bash
   python -m aidefend_mcp --mcp
   ```
   - You should see "Waiting for MCP client connections..." in stderr
   - If it crashes, check the error message

#### MCP tools are slow or timeout

- The first query triggers initial sync (1-3 minutes)
- Check if sync is complete: `python -m aidefend_mcp` then visit http://localhost:8000/api/v1/status
- After initial sync, queries should be fast (< 1 second)

#### "Database sync in progress" error

- Wait a few moments and retry
- This protects against race conditions during sync
- Check logs for sync errors: `tail -f data/logs/aidefend_mcp.log`

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Run tests and security checks
4. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Copyright (c) 2025 Edward Lee (edward-playground)

## Acknowledgments

- [AIDEFEND Framework](https://github.com/edward-playground/aidefense-framework) - The AI security knowledge base
- [LanceDB](https://lancedb.com/) - Fast vector database
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [FastEmbed](https://qdrant.github.io/fastembed/) - Lightweight ONNX-based embedding models

## Author

**Edward Lee**
- GitHub: [@edward-playground](https://github.com/edward-playground)
- LinkedIn: [Edward Lee](https://www.linkedin.com/in/go-edwardlee/)

## Support

For issues and questions:
- GitHub Issues: [Create an issue](https://github.com/edward-playground/aidefend-mcp/issues)
- Security Issues: See [SECURITY.md](./SECURITY.md)

---

**Built with ❤️ for the AI security community**
