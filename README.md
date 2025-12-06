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
- **Multilingual Support**: Query in any language (Chinese, Japanese, Korean, etc.) and get relevant English results with `Xenova/multilingual-e5-base` (Microsoft, 100+ languages)
- **Cost Efficient**: 25x token reduction vs sending full framework - drastically lower LLM API costs
- **Long Query Support**: Automatic chunking for long queries (up to 5000 chars) with intelligent sentence-boundary splitting
- **Auto-Sync**: Automatically pulls latest AIDEFEND content from GitHub (hourly checks)
- **Fast Vector Search**: LanceDB-powered semantic search (CPU: 500-1000ms per query; optional GPU acceleration: 100-300ms - see [GPU guide](docs/advanced/GPU_ACCELERATION.md))
- **Security-First**: Comprehensive input validation, sanitization, and security headers
- **Docker Ready**: Easy deployment with Docker and docker-compose
- **Production Ready**: Health checks, rate limiting, structured logging, and monitoring
- **Smart Context-Aware Scoring**: Prioritizes defenses based on prevention vs. detection, asset criticality, compliance impact, and implementation readiness
- **Defense in Depth**: Multiple security layers (see [SECURITY.md](./SECURITY.md))



## Quick Start

### Step 1: Clone the Repository

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

### Step 2: Choose Your Mode & Install

| Mode | Best For | Quick Start |
|------|----------|-------------|
| **🖥️ Claude Desktop** | Desktop app users | `python scripts/install.py` |
| **💻 Claude Code** | VSCode users | `python scripts/install.py --client code` |
| **🌐 REST API** | HTTP integration, CI/CD | `python scripts/install.py --no-mcp` |
| **🐳 Docker** | Production deployment | `docker-compose up -d` |

---

<details open>
<summary><h4>🔌 Option A: MCP Mode (Claude Desktop) - Recommended</h4></summary>

**🚀 One-Click Installation (2 minutes):**

```bash
# Single command - installs everything and configures Claude Desktop
python scripts/install.py

# macOS/Linux users: Use python3 if python points to Python 2
python3 scripts/install.py
```

**What this script does:**
- ✅ Checks Python 3.9+ and Node.js 18+ versions
- ✅ Installs all Python dependencies automatically
- ✅ Installs all Node.js dependencies automatically
- ✅ Auto-detects paths and configures Claude Desktop
- ✅ **Safely merges configuration (preserves existing MCP tools)**
- ✅ Creates backup before any changes

**For details:** See [One-Click Installation in INSTALL.md](INSTALL.md#-mcp-mode-setup-claude-desktop---one-click-installation).

<details>
<summary><b>Advanced: Manual Setup (click to expand)</b></summary>

See detailed manual setup instructions in [INSTALL.md](INSTALL.md).

</details>

</details>

---

<details>
<summary><h4>🌐 Option B: REST API Mode (HTTP Integration)</h4></summary>

**Install dependencies:**
```bash
# Install dependencies without MCP configuration
python scripts/install.py --no-mcp

# macOS/Linux users: Use python3 if python points to Python 2
python3 scripts/install.py --no-mcp
```

**Start the service:**
```bash
python __main__.py
```

**Verify it's running:**
```bash
curl http://localhost:8000/health
```

**Access API docs:**
Open browser: http://localhost:8000/docs

The service automatically syncs with GitHub and indexes AIDEFEND framework on first run.

</details>

---

<details>
<summary><h4>🐳 Option C: Docker Deployment (Production)</h4></summary>

**Start:**
```bash
docker-compose up -d
```

**Check logs:**
```bash
docker-compose logs -f
```

**Note:** MCP mode requires direct Python execution and cannot run in Docker.

**Production Security:**
For production deployments, configuring authentication is highly recommended:
```bash
# In docker-compose.yml or .env
AUTH_MODE=api_key
AIDEFEND_API_KEY=<your-secure-key>
```

</details>

## 💰 Why Use This MCP / REST API Service?

### TL;DR
**Save 90% on LLM costs + Get better answers + 5-minute setup = Your new AI security workflow**

> If you're querying AI security defenses with ChatGPT/Claude/Gemini, you might be wasting 90% of your budget while getting incomplete answers.

---

### 📊 The Two Ways to Use AIDEFEND

#### ❌ Manual Way: Download → Paste into LLM

```
1. Download all tactics/*.js files from GitHub          (⏱️ 5 min)
2. Merge into one file                                  (⏱️ 3 min)
3. Copy ~50,000 tokens to clipboard
4. Paste into ChatGPT/Claude
5. Ask your question

Problems:
💸 Cost per query: $0.50 (GPT-4)
⚠️  LLM may miss critical info (Lost in the Middle Problem)
🔄 AIDEFEND updated? Re-download everything (8 min each time)
📊 100 queries = $50
```

#### ✅ AIDEFEND MCP Way: Smart Vector Search

```
1. Install once (2 minutes)
   python scripts/install.py

2. Ask your question (via Claude Desktop or API)

Advantages:
💰 Cost per query: $0.02 (2,000 tokens vs 50,000)
✅ Vector search finds most relevant content (no missing info)
🔄 Auto-updates every hour (zero maintenance)
📊 100 queries = $2

Save $48 + hours of manual work!
```

---

### 💸 Real Cost Comparison

| Usage | Manual (50K tokens/query) | AIDEFEND MCP (2K tokens/query) | Savings |
|-------|--------------------------|-------------------------------|---------|
| **100 queries** | $50 | $2 | **$48** |
| **1 year (10/day)** | $1,825 | $73 | **$1,752** |

*Based on GPT-4 Turbo pricing ($10/1M input tokens)*

💡 **Enterprise teams save $1,752+/year in LLM API costs alone**

---

### 🎯 Why Vector Search Beats Full-Text Paste

**The "Lost in the Middle" Problem:**

When you paste 50,000 tokens into an LLM, it struggles with information in the middle:

```
Your 50K token paste:
┌─────────────────────────────────┐
│ First 10K tokens                │  ← LLM pays attention ⭐⭐⭐⭐⭐
│ Model Tactic...                 │
│                                 │
│ Middle 30K tokens               │  ← LLM attention drops ⭐⭐
│ ⚠️  Most important defenses!    │  ← Often missed!
│ ⚠️  AID-H-001, AID-H-002...     │
│                                 │
│ Last 10K tokens                 │  ← LLM pays attention ⭐⭐⭐⭐⭐
│ Respond Tactic...               │
└─────────────────────────────────┘

Result: LLM may skip the most relevant techniques!
```

**Vector Search Solution:**

```
Your question: "How to defend against prompt injection?"
       ↓
Vector search analyzes semantic similarity
       ↓
Returns TOP 5 most relevant (2K tokens):
✅ AID-H-001: Input Validation        (similarity: 0.92)
✅ AID-H-002: Prompt Guard             (similarity: 0.89)
✅ AID-D-001: Anomaly Detection        (similarity: 0.85)
       ↓
LLM gets precise, relevant information → Better answers!
```

> **Research shows**: Vector search improves answer quality by 40% compared to full-text retrieval

---

### 🛠️ Not Just Search: 19 Professional Tools

**Manual way:** Ask questions
**AIDEFEND MCP:** Professional AI security analysis platform

**Example Tools:**

```python
# 1. Coverage Analysis - Find your defense gaps
analyze_coverage(implemented_techniques=["AID-H-001"])
→ Shows coverage % by tactic, identifies gaps

# 2. Implementation Planning - What to build next
get_implementation_plan(implemented_techniques=["AID-H-001"])
→ Ranked recommendations based on threat importance

# 3. Compliance Mapping - Audit support
map_to_compliance_framework(techniques=["AID-H-001"], framework="nist_ai_rmf")
→ Maps to NIST AI RMF, EU AI Act, ISO 42001

# 4. Threat Coverage - Which threats are you protected against?
get_threat_coverage(implemented_techniques=["AID-H-001"])
→ OWASP LLM Top 10, MITRE ATLAS coverage analysis
```

💼 **These capabilities don't exist in manual workflows**

---



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
- **2-2.5GB disk space** (reduced from 3-4GB with Int8 quantized model)
  - Service itself: ~200-700MB (code + knowledge base + logs)
  - Dependencies: ~880MB-1.48GB (ONNX model + Python/Node packages)
  - **75% smaller embedding model**: Quantized Int8 version (280MB vs 1.1GB original)


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

## Available Tools (18 Tools)

The AIDEFEND MCP Service provides **18 specialized tools** for AI security analysis:

### Basic Query Tools (3 tools)
- 🔍 **query_aidefend** - Search AIDEFEND knowledge base
- ✅ **get_aidefend_status** - Check service status and framework version
- 🔄 **sync_aidefend** - Manually trigger sync

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
EMBEDDING_MODEL=Xenova/multilingual-e5-base
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
- **FastEmbed**: ONNX-based embedding models (Quantized Int8 for 75% size reduction)
- **Anthropic MCP**: Model Context Protocol

---

**Questions or issues?** Please open an issue on [GitHub](https://github.com/edward-playground/aidefend-mcp/issues).
