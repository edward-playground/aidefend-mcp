[English README](README.md) | [繁體中文 README](README-繁體中文.md)

---

# AIDEFEND MCP / REST API Service

[![CI](https://github.com/edward-playground/aidefend-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/edward-playground/aidefend-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%20|%203.13-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.121.1-009688.svg)](https://fastapi.tiangolo.com)

Local retrieval service for the [AIDEFEND framework](https://github.com/edward-playground/aidefense-framework).

This repository safely parses the framework's JavaScript tactics, builds a local LanceDB knowledge base, and exposes the result through:

- a REST API for applications and automation
- an MCP server for AI assistants such as Claude Desktop

This repository is **not** the framework itself. It is the service layer on top of the framework.

## What You Get

- Local semantic search over AIDEFEND content
- REST API and MCP access from the same indexed knowledge base
- Automatic sync from the upstream GitHub repository by default
- Optional local framework override for contributors working on both repos
- Multilingual embedding search with `Xenova/multilingual-e5-base`
- Automated tests and Bandit security scanning in GitHub Actions

## How It Works

1. Sync AIDEFEND tactic files from GitHub.
2. Parse the JavaScript files with a Node.js AST parser. The service does not execute upstream framework code.
3. Expand tactics into techniques, sub-techniques, and strategies.
4. Generate embeddings and store the documents in LanceDB.
5. Serve the indexed data over REST or MCP.

## Requirements

- Python 3.9 to 3.13
- Node.js 18+
- Git
- About 2 to 3 GB free disk space for dependencies, embedding model, and local database

Normal users do **not** need to configure any personal local path. The default setup syncs from GitHub.

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

### 2. Pick an installation path

| Use case | Recommended command |
| --- | --- |
| Claude Desktop MCP | `python scripts/install.py` |
| Claude Code MCP | `python scripts/install.py --client code` |
| REST API only | `python scripts/install.py --no-mcp` |
| Manual setup | Follow [INSTALL.md](INSTALL.md) |

### 3. Build the local knowledge base

```bash
python __main__.py --resync
```

The first sync downloads the framework, embedding model, and creates the local database. Expect several minutes on a clean machine.

### 4. Run the service

REST API:

```bash
python __main__.py
```

MCP server:

```bash
python __main__.py --mcp
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Manual Setup From a Fresh Clone

If you want a clean, explicit install path instead of the helper script:

```bash
python -m venv .venv
```

Activate the virtual environment.

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm ci
```

Create local config:

macOS/Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Then run:

```bash
python __main__.py --resync
python __main__.py
```

## Optional Local Framework Override

By default the service syncs from GitHub. If you are developing this repo alongside a local checkout of `aidefense-framework`, you can point the sync to your local source:

```env
LOCAL_FRAMEWORK_PATH=/path/to/aidefense-framework
```

This is optional and should stay unset for normal open-source users.

## Common Commands

```bash
# Rebuild the local database from the configured source
python __main__.py --resync

# Run the REST API
python __main__.py

# Run the MCP server
python __main__.py --mcp

# Run tests
python -m pytest -q

# Run static security scan
python -m bandit -q -r app
```

## Docker

```bash
docker-compose up -d
```

When binding externally, authentication is required. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Documentation

- Installation: [INSTALL.md](INSTALL.md)
- Configuration: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- Advanced configuration: [docs/ADVANCED_CONFIGURATION.md](docs/ADVANCED_CONFIGURATION.md)
- Tool reference: [docs/TOOLS.md](docs/TOOLS.md)
- Security notes: [SECURITY.md](SECURITY.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)

## Repository Notes

- `data/`, local caches, coverage output, and `.env` are ignored by git and are not required in the repository.
- CI runs `pytest` and `bandit` automatically on pushes and pull requests.
- The service has been validated against the updated AIDEFEND framework structure as of April 14, 2026.

## License

MIT. See [LICENSE](LICENSE).
