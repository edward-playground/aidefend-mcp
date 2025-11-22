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
- **Multilingual Support**: Query in any language (Chinese, Japanese, Korean, etc.) and get relevant English results with `intfloat/multilingual-e5-base` (Microsoft, 100+ languages)
- **Cost Efficient**: 25x token reduction vs sending full framework - drastically lower LLM API costs
- **Long Query Support**: Automatic chunking for long queries (up to 5000 chars) with intelligent sentence-boundary splitting
- **Auto-Sync**: Automatically pulls latest AIDEFEND content from GitHub (hourly checks)
- **Fast Vector Search**: LanceDB-powered semantic search (CPU: 500-1000ms per query; optional GPU acceleration: 100-300ms - see [GPU guide](docs/advanced/GPU_ACCELERATION.md))
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
   git clone https://github.com/edward-playground/aidefend-mcp.git
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
   # Default (REST API mode)
   C:/Python313/python.exe __main__.py

   # Or explicitly specify REST API mode
   C:/Python313/python.exe __main__.py --api
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

      - (On most modern Windows machine, this path is C:\Users\\[Your User Name]\AppData\Roaming\Claude\\)

   Add this configuration:
   ```json
   {
     "mcpServers": {
       "aidefend": {
         "command": "C:/Python313/python.exe",
         "args": [
           "/absolute/path/to/aidefend-mcp/__main__.py",
           "--mcp"
         ],
         "cwd": "/absolute/path/to/aidefend-mcp"
       }
     }
   }
   ```

   **⚠️ IMPORTANT:** Replace ALL paths with **your actual absolute paths**!

   1. **Python executable path** in the `command` field:
      - Replace `C:/Python313/python.exe` with your actual Python installation path
      - To find your Python path:
        - Windows: Run `where python` in Command Prompt
        - macOS/Linux: Run `which python` or `which python3` in Terminal
      - Common locations:
        - Windows: `C:/Python313/python.exe`, `C:/Python312/python.exe`, `C:/Users/YourName/AppData/Local/Programs/Python/Python313/python.exe`
        - macOS: `/usr/local/bin/python3`, `/opt/homebrew/bin/python3`
        - Linux: `/usr/bin/python3`, `/usr/local/bin/python3`

   2. **Project paths** in the `args` and `cwd` fields:
      - Replace `/absolute/path/to/aidefend-mcp/__main__.py` in the `args` field
      - Replace `/absolute/path/to/aidefend-mcp` in the `cwd` field
      - The `cwd` field is necessary for Python to resolve relative imports within the project

   **Complete examples:**
   - Windows:
     - `"command": "C:/Python313/python.exe"`
     - `"args": ["C:/Users/YourName/projects/aidefend-mcp/__main__.py", "--mcp"]`
     - `"cwd": "C:/Users/YourName/projects/aidefend-mcp"`
   - macOS/Linux:
     - `"command": "/usr/local/bin/python3"`
     - `"args": ["/Users/yourname/projects/aidefend-mcp/__main__.py", "--mcp"]`
     - `"cwd": "/Users/yourname/projects/aidefend-mcp"`

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

> **💡 Tip:** For troubleshooting and maintenance commands (including database resync), see the [Troubleshooting section in INSTALL.md](INSTALL.md#troubleshooting).

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

#### Other Key Endpoints

```bash
# Service status
GET /api/v1/status

# Health check
GET /health

# Manual sync
POST /api/v1/sync
```

> **📖 Full API documentation:** http://localhost:8000/docs (when service is running)

### MCP Mode Usage

When running in MCP mode (`python __main__.py --mcp`), the service provides tools for AI assistants like Claude Desktop.

**Example conversation:**

```
You: "How do I defend against prompt injection attacks?"

Claude: [Automatically uses query_aidefend tool]
       Based on AIDEFEND, here are the key defense techniques...
```

> **📖 Complete MCP tool reference:** [docs/TOOLS.md](docs/TOOLS.md)

## Available Tools (19 Tools)

The AIDEFEND MCP Service provides **19 specialized tools** for AI security analysis:

### Basic Query Tools (4 tools)
- 🔍 **query_aidefend** - Search AIDEFEND knowledge base
- ✅ **get_aidefend_status** - Check service status
- 🔄 **sync_aidefend** - Manually trigger sync
- 📦 **get_framework_version** - Get framework version

### Technique Analysis Tools (4 tools)
- 📊 **get_statistics** - Knowledge base statistics
- ✅ **validate_technique_id** - Validate technique IDs
- 📖 **get_technique_detail** - Deep-dive into techniques
- 💻 **get_secure_code_snippet** - Get code examples

### Threat Analysis Tools (3 tools)
- 🛡️ **get_defenses_for_threat** - Find defenses for threats
- 🎯 **classify_threat** - Classify threats (100% local)
- 📋 **get_threat_coverage** - Analyze threat coverage

### Planning & Analysis Tools (5 tools)
- 📈 **analyze_coverage** - Identify defense gaps
- 🗺️ **map_to_compliance_framework** - Map to compliance (NIST, EU AI Act, etc.)
- ⚖️ **compare_techniques** - Compare techniques side-by-side
- 🎯 **get_implementation_plan** - Get prioritized recommendations
- 🛡️ **analyze_security_posture** - Comprehensive posture analysis

### Advanced Tools (3 tools)
- 🔎 **comprehensive_search** - Multi-query aggregated search
- 📝 **get_quick_reference** - Generate checklists
- 🚨 **generate_incident_playbook** - Incident response playbooks

> **📖 Complete tool documentation with examples:** [docs/TOOLS.md](docs/TOOLS.md)

## Configuration

All configuration is done via environment variables. Copy `.env.example` to `.env` and customize as needed.

### Key Configuration Options

```bash
# Authentication
AUTH_MODE=no_auth                    # or "api_key" for production
AIDEFEND_API_KEY=<your-key>          # Required when AUTH_MODE=api_key

# Server
API_HOST=127.0.0.1                   # Use 0.0.0.0 for external access
API_PORT=8000
API_WORKERS=1                        # ⚠️ Must be 1 (multi-worker not supported)

# Sync
SYNC_INTERVAL_SECONDS=3600           # Auto-sync frequency (1 hour)

# Embedding
EMBEDDING_MODEL=intfloat/multilingual-e5-base
EMBEDDING_DIMENSION=768

# Rate Limiting
ENABLE_RATE_LIMITING=true
RATE_LIMIT_PER_MINUTE=60
```

> **📖 Complete configuration guide:** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## Security

As an MCP service for an AI security framework, this service implements multiple security layers:

- **Local-First Processing**: All queries processed locally
- **Input Validation**: Comprehensive sanitization
- **Rate Limiting**: DoS protection
- **Authentication**: Optional API key authentication
- **Container Hardening**: Non-root user, minimal privileges
- **Audit Logging**: Structured logs with sensitive data filtering

> **📖 Security policy and best practices:** [SECURITY.md](./SECURITY.md)

## Troubleshooting

**Common issues:**

- **Service won't start:** Check logs at `data/logs/aidefend_mcp.log`
- **Database errors:** Run `python __main__.py --resync`
- **MCP tools not showing:** Verify absolute paths in Claude Desktop config
- **Slow queries:** Initial sync in progress, wait for completion

> **📖 Complete troubleshooting guide:** [INSTALL.md#troubleshooting](INSTALL.md#troubleshooting)

## Development

Want to contribute? Great!

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Check code quality
black app/
flake8 app/
mypy app/
```

> **📖 Development guide:** [CONTRIBUTING.md](CONTRIBUTING.md)

## Project Structure

```
aidefend-mcp/
├── __main__.py              # Entry point (mode selection)
├── mcp_server.py            # MCP protocol server
├── app/
│   ├── main.py              # FastAPI REST API
│   ├── core.py              # QueryEngine (shared)
│   ├── sync.py              # Background sync
│   └── tools/               # 19 specialized tools
├── docs/                    # Documentation
│   ├── TOOLS.md             # Complete tool reference
│   └── CONFIGURATION.md     # Configuration guide
├── tests/                   # Test suite
└── data/                    # Runtime data
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **AIDEFEND Framework**: [edward-playground/aidefense-framework](https://github.com/edward-playground/aidefense-framework)
- **FastAPI**: Modern Python web framework
- **LanceDB**: Vector database for semantic search
- **FastEmbed**: ONNX-based embedding models
- **Anthropic MCP**: Model Context Protocol

---

**Questions or issues?** Please open an issue on [GitHub](https://github.com/edward-playground/aidefend-mcp/issues).
