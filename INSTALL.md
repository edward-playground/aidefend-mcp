[English Installation Guide](INSTALL.md) | [繁體中文安裝指南](INSTALL-繁體中文.md)

---

# Installation Guide

This guide is written for someone starting from a fresh GitHub clone.

If you only need the shortest path:

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
python scripts/install.py --no-mcp
python __main__.py --resync
python __main__.py
```

If you want Claude Desktop integration, run `python scripts/install.py` instead.

## Choose One Path

| Goal | Recommended path |
| --- | --- |
| Claude Desktop MCP | `python scripts/install.py` |
| Claude Code MCP | `python scripts/install.py --client code` |
| REST API only | `python scripts/install.py --no-mcp` |
| Full manual control | Follow the manual setup section below |
| Container deployment | Use Docker Compose |

## Prerequisites

- Python 3.9 to 3.13
- Node.js 18+
- Git
- 2 to 3 GB free disk space

Check versions:

```bash
python --version
node --version
git --version
```

## Recommended Path: Install Script

Clone the repository:

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

Then choose one:

```bash
# Claude Desktop
python scripts/install.py

# Claude Code
python scripts/install.py --client code

# REST API only
python scripts/install.py --no-mcp
```

After the installer finishes, build the local database:

```bash
python __main__.py --resync
```

Then run:

```bash
# REST API
python __main__.py

# MCP server
python __main__.py --mcp
```

## Manual Setup

### 1. Clone the repository

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it.

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### 3. Install Python and Node dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm ci
```

### 4. Create a local config file

macOS/Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Normal users can keep the defaults. The service syncs from GitHub by default.

### 5. Build the knowledge base

```bash
python __main__.py --resync
```

The first run downloads the framework and embedding model, then builds LanceDB locally. This can take several minutes.

### 6. Start the service

REST API:

```bash
python __main__.py
```

MCP:

```bash
python __main__.py --mcp
```

### 7. Verify the service

REST health check:

```bash
curl http://127.0.0.1:8000/health
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Docker Compose

```bash
docker-compose up -d
```

If you expose the service on `0.0.0.0`, authentication is required. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Optional Local Framework Source

By default sync uses the upstream GitHub repository.

If you are actively developing `aidefense-framework` locally and want this service to index your local checkout instead, set:

```env
LOCAL_FRAMEWORK_PATH=/path/to/aidefense-framework
```

Leave this unset for standard open-source installs.

## Common Commands

```bash
# Rebuild database from the configured source
python __main__.py --resync

# Run tests
python -m pytest -q

# Run Bandit
python -m bandit -q -r app
```

## Troubleshooting

- `node` not found: install Node.js 18+ and confirm `node --version` works.
- ONNX or Windows runtime errors: install Microsoft Visual C++ Redistributable.
- First sync is slow: this is normal on a clean machine because models and framework data are being downloaded.
- Binding to external interfaces without auth fails by design. This is a security check, not a bug.

## More Docs

- Overview: [README.md](README.md)
- Configuration: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- Advanced configuration: [docs/ADVANCED_CONFIGURATION.md](docs/ADVANCED_CONFIGURATION.md)
- Security: [SECURITY.md](SECURITY.md)
