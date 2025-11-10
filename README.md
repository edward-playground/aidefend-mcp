[English](README.md) | [繁體中文](README-繁體中文.md)

---

# AIDEFEND MCP Service

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.2-009688.svg)](https://fastapi.tiangolo.com)
[![Security: Multiple Layers](https://img.shields.io/badge/security-multi--layer-success.svg)](./SECURITY.md)

A **local, decentralized RAG (Retrieval-Augmented Generation) engine** for the [AIDEFEND framework](https://github.com/edward-playground/aidefend-framework). This service provides secure, private access to AIDEFEND's AI security knowledge base without sending sensitive queries to external services.

## Features

- **100% Private & Local**: All queries processed locally - your prompts never leave your infrastructure, works completely offline
- **Cost Efficient**: 25x token reduction vs sending full framework - drastically lower LLM API costs
- **Auto-Sync**: Automatically pulls latest AIDEFEND content from GitHub (hourly checks)
- **Fast Vector Search**: Powered by LanceDB for efficient semantic search (millisecond response times)
- **Security-First**: Comprehensive input validation, sanitization, and security headers
- **Docker Ready**: Easy deployment with Docker and docker-compose
- **Production Ready**: Health checks, rate limiting, structured logging, and monitoring
- **Defense in Depth**: Multiple security layers (see [SECURITY.md](./SECURITY.md))

## Why Use This MCP Service?

AIDEFEND is open source, so you *could* build this yourself. But there's a huge gap between "possible" and "practical."

### The Problems This Solves

#### **Problem 1: Privacy Concerns with Cloud Services**

Most RAG services send your queries to cloud servers. Your sensitive prompts (security questions, proprietary info) leave your control.

**This MCP Service:**
- ✅ **100% local processing** - queries never leave your machine
- ✅ **Works offline** after initial sync
- ✅ **Zero tracking** - no telemetry, no external API calls

#### **Problem 2: LLMs Can't Handle the Full Framework**

AIDEFEND has thousands of lines. LLMs have token limits (~8K-128K). You can't paste everything into ChatGPT.

**This MCP Service:**
- ✅ **Smart search** - finds the 3-5 most relevant sections in milliseconds
- ✅ **Only sends what you need** - no manual copy-pasting

#### **Problem 3: Building RAG is Complex**

To build this yourself, you'd need to:
- Write JavaScript parsers
- Set up vector databases (LanceDB, ChromaDB, Pinecone)
- Configure embedding models
- Handle updates manually (`git pull` → re-parse → re-embed)

**This MCP Service:**
- ✅ **One command**: `docker-compose up -d`
- ✅ **Auto-updates** every hour
- ✅ **Zero maintenance** required

#### **Problem 4: Token Costs Add Up Fast**

Sending the full framework = 50K+ tokens per query. Paid LLM APIs charge per token.

**This MCP Service:**
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

> **The AIDEFEND framework is the knowledge base. This service delivers it privately and efficiently.**

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AIDEFEND MCP Service                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐         ┌──────────────┐                │
│  │              │         │              │                 │
│  │  Sync        │────────▶│  LanceDB     │                 │
│  │  Service     │  Index  │  Vector DB   │                 │
│  │              │         │              │                 │
│  └──────┬───────┘         └───────▲──────┘                 │
│         │                         │                         │
│         │ GitHub                  │ Query                   │
│         │ API                     │                         │
│         ▼                         │                         │
│  ┌──────────────┐         ┌──────┴──────┐                 │
│  │  AIDEFEND    │         │  Query      │                  │
│  │  Framework   │         │  Engine     │                  │
│  │  (GitHub)    │         │             │                  │
│  └──────────────┘         └──────▲──────┘                  │
│                                   │                         │
│                           ┌───────┴────────┐               │
│                           │   FastAPI      │               │
│                           │   REST API     │               │
│                           └───────▲────────┘               │
│                                   │                         │
└───────────────────────────────────┼─────────────────────────┘
                                    │
                            ┌───────┴────────┐
                            │  Your LLM      │
                            │  Application   │
                            └────────────────┘
```

## Prerequisites

- **Python 3.9+**
- **Node.js** (for parsing AIDEFEND JavaScript files)
- **Docker** (optional, for containerized deployment)
- **4GB RAM** minimum (8GB recommended)
- **2GB disk space** for models and data

## Quick Start

### Option 1: Local Installation

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
   # Edit .env if needed
   ```

4. **Verify Node.js is installed**
   ```bash
   node --version
   ```

5. **Run the service**
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

6. **Check status**
   ```bash
   curl http://localhost:8000/health
   ```

The service will automatically:
- Download AIDEFEND framework files from GitHub
- Parse and index the content
- Start the API server

Access the API documentation at: http://localhost:8000/docs

### Option 2: Docker Deployment

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

## API Usage

### Query Endpoint

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
| `NODE_EXECUTABLE` | `node` | Path to Node.js executable |

## Security

As an MCP service for an AI security framework, this service implements multiple security layers:

- **Local-First Processing**: All queries processed locally - your data never leaves your infrastructure
- **Input Validation**: Comprehensive validation and sanitization of all inputs
- **Rate Limiting**: Protection against abuse and DoS attacks
- **Secure Operations**: Path traversal prevention, file security, and permission controls
- **Network Security**: SSRF protection, URL validation, and security headers
- **Container Hardening**: Non-root user, minimal privileges, and secure defaults
- **Audit Logging**: Structured logs with automatic sensitive data filtering

**For security issues, vulnerability reporting, and deployment best practices, see [SECURITY.md](./SECURITY.md).**

## Monitoring & Logs

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

### Project Structure

```
aidefend-mcp/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application
│   ├── config.py        # Configuration management
│   ├── core.py          # Query engine
│   ├── sync.py          # GitHub sync service
│   ├── schemas.py       # Pydantic models
│   ├── security.py      # Security validations
│   ├── logger.py        # Structured logging
│   └── utils.py         # Utility functions
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
├── .env.example
├── README.md
└── SECURITY.md
```

## Troubleshooting

### Service won't start

1. **Check Node.js is installed**
   ```bash
   node --version
   ```

2. **Check logs**
   ```bash
   tail -f data/logs/aidefend_mcp.log
   ```

3. **Verify network access to GitHub**
   ```bash
   curl https://api.github.com/repos/edward-playground/aidefend-framework/commits/main
   ```

### Queries return "Service not ready"

- The initial sync is still in progress. Check `/api/v1/status` for sync status.
- The database may be corrupted. Delete `data/` and restart the service.

### Rate limiting issues

Adjust `RATE_LIMIT_PER_MINUTE` in `.env` or disable with `ENABLE_RATE_LIMITING=false`.

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

- [AIDEFEND Framework](https://github.com/edward-playground/aidefend-framework) - The AI security knowledge base
- [LanceDB](https://lancedb.com/) - Fast vector database
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Sentence Transformers](https://www.sbert.net/) - Embedding models

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
