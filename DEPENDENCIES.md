# DEPENDENCIES.md

**AIDEFEND MCP Service - Complete Dependency Documentation**

This document provides comprehensive information about all dependencies used by AIDEFEND MCP Service, including purposes, licenses, and security considerations.

---

## Table of Contents

1. [Runtime Dependencies](#runtime-dependencies)
2. [Python Dependencies](#python-dependencies)
3. [Node.js Dependencies](#nodejs-dependencies)
4. [System Requirements](#system-requirements)
5. [Optional Dependencies](#optional-dependencies)
6. [Security & Licenses](#security--licenses)
7. [Dependency Update Policy](#dependency-update-policy)

---

## Runtime Dependencies

### 1. Python 3.9 - 3.13

**Purpose**: Core programming language for the service
**Minimum Version**: 3.9
**Recommended Version**: 3.13.6 (latest tested)
**Installation**: https://www.python.org/downloads/
**License**: PSF License (BSD-style, permissive)
**Why this version range**:
- 3.9+: Required for modern type hints and async features
- Up to 3.13: Latest tested and supported version
- Uses features: `asyncio`, `pathlib`, `typing` with modern syntax

**Auto-install**: Not available (requires manual installation as prerequisite)

---

### 2. Node.js 18+

**Purpose**: Parse AIDEFEND JavaScript files with ES6 template literals
**Minimum Version**: 18.0.0
**Recommended Version**: Latest LTS (20.x)
**Installation**: https://nodejs.org/
**License**: MIT License
**Why needed**:
- AIDEFEND framework uses JavaScript ES6 template literals (backticks)
- Python cannot parse these natively
- Node.js subprocess used via `parse_js_module.mjs`

**Auto-install**: ✅ **Semi-automated** (Windows/macOS: downloads and launches installer, Linux: provides package manager commands)

---

### 3. Microsoft Visual C++ Redistributable 2015-2022 (Windows Only)

**Purpose**: Runtime libraries required by ONNX Runtime on Windows
**Version**: Latest (2015-2022 unified package)
**Installation**: https://aka.ms/vs/17/release/vc_redist.x64.exe
**License**: Microsoft Software License Terms
**Why needed**:
- ONNX Runtime uses native C++ code for performance
- Requires MSVC runtime DLLs (msvcp140.dll, vcruntime140.dll, etc.)
- Only needed on Windows (macOS/Linux have native equivalents)

**Auto-install**: ✅ **Semi-automated** (detects via registry, downloads from Microsoft, installs with /passive mode)

---

## Python Dependencies

All Python dependencies are listed in [`requirements.txt`](requirements.txt). Total size: ~500MB-1GB.

### Web Framework & Server

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **fastapi** | 0.121.1 | Modern async web framework for REST API | MIT |
| **uvicorn[standard]** | 0.38.0 | ASGI server for FastAPI | BSD-3-Clause |
| **python-multipart** | 0.0.20 | Form data parsing for FastAPI | Apache-2.0 |

**Why these versions**: FastAPI 0.121.1 has stable async support, uvicorn[standard] includes performance optimizations.

---

### Data Validation & Settings

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **pydantic** | 2.12.4 | Data validation and settings management | MIT |
| **pydantic-settings** | 2.7.1 | Settings management from env vars | MIT |

**Why these versions**: Pydantic v2 required for modern type validation and performance improvements.

---

### Vector Database & Embeddings

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **lancedb** | 0.25.3 | Vector database for semantic search | Apache-2.0 |
| **fastembed** | 0.7.3 | ONNX-based embedding generation | Apache-2.0 |
| **pandas** | >=2.0.0 | Data manipulation (required by LanceDB's `.to_pandas()`) | BSD-3-Clause |

**Why these**:
- LanceDB: Lightweight, serverless vector DB (no external database needed)
- FastEmbed: Uses ONNX Runtime for CPU-based embeddings (no GPU required)
- pandas: Implicit dependency of LanceDB for data conversion

**Downloaded Models**:
- `Xenova/multilingual-e5-base` (Quantized Int8): ~280MB ONNX model (stored in `~/.cache/fastembed/`)
- Qdrant pre-quantized version for 75% size reduction vs original (1.1GB → 280MB)
- Supports 100+ languages for multilingual semantic search

---

### MCP Protocol

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **mcp** | 1.21.0 | Model Context Protocol SDK for Claude Desktop integration | MIT |
| **pywin32** | 311 | Windows platform APIs (Windows only, required by MCP SDK) | PSF License |

**Why needed**:
- **mcp**: Enables native integration with Claude Desktop as an MCP server
- **pywin32**: Windows-only implicit dependency of MCP SDK for accessing Windows platform APIs (COM, registry, etc.)

**Platform-specific**: pywin32 is only installed on Windows (`sys_platform == 'win32'`)

---

### HTTP & Networking

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **httpx** | 0.28.1 | Modern async HTTP client for GitHub API calls | BSD-3-Clause |

**Why httpx over requests**: Full async support, HTTP/2, better connection pooling.

---

### Rate Limiting & Security

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **slowapi** | 0.1.9 | Rate limiting middleware for FastAPI | MIT |

**Why needed**: Prevents API abuse, implements token bucket rate limiting.

---

### Utilities & Performance

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **typing-extensions** | 4.15.0 | Backports for modern type hints | PSF License |
| **beautifulsoup4** | 4.12.3 | HTML parsing (for web content) | MIT |
| **rapidfuzz** | 3.10.1 | Fast fuzzy string matching (10-100x faster than difflib) | MIT |
| **aiorwlock** | 1.4.0 | Async read-write locks for QueryEngine | Apache-2.0 |

**Why these**:
- rapidfuzz: Used for typo-tolerant threat classification (Tier 2 fuzzy matching)
- aiorwlock: Prevents race conditions during database reads/writes

---

## Node.js Dependencies

All Node.js dependencies are listed in [`package.json`](package.json). Total size: ~100-200MB.

### JavaScript Parsing

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **acorn** | ^8.11.3 | Fast, standards-compliant ECMAScript parser | MIT |

**Why acorn**:
- Fast AST-based parsing (safer than `eval()`)
- Supports ES6+ syntax including template literals
- Used in Webpack, ESLint, and other trusted tools
- Sandboxed execution via Node.js subprocess

**Usage**: Called via `parse_js_module.mjs` to extract AIDEFEND technique definitions from JavaScript files.

---

## System Requirements

### Minimum Requirements

| Component | Minimum | Recommended | Notes |
|-----------|---------|-------------|-------|
| **CPU** | 2 cores | 4+ cores | CPU-based ONNX inference |
| **RAM** | 2GB | 4GB | Embedding model loaded in memory |
| **Disk Space** | 3GB | 4-5GB | See breakdown below |
| **Network** | Required for initial setup | Offline after setup | GitHub API, model download |

### Disk Space Breakdown

**Total: 2-2.5GB** (reduced from 3-4GB with Int8 quantized model)

1. **AIDEFEND Service** (~200-700MB):
   - Source code: ~10MB
   - Vector database (LanceDB): ~100-500MB (grows with AIDEFEND updates)
   - Raw content cache: ~50-100MB
   - Logs: ~10-50MB

2. **External Dependencies** (~880MB-1.48GB):
   - ONNX embedding model (HuggingFace cache): ~280MB (Quantized Int8)
   - Python packages (pip): ~500MB-1GB
   - Node.js packages (npm): ~100-200MB

3. **Visual C++ Redistributable** (Windows only):
   - Installer download: ~14MB (deleted after install)
   - Installed size: ~50-100MB

4. **Node.js Installation**:
   - Installer download: ~30-35MB (deleted after install)
   - Installed size: ~200-300MB (if not already installed)

---

## Optional Dependencies

### Docker (for containerized deployment)

**Purpose**: Run service in isolated container
**Installation**: https://www.docker.com/
**License**: Apache-2.0
**Note**: MCP mode not available in Docker (requires stdio access)

---

### GPU Acceleration (optional, for faster embeddings)

**Not currently implemented** - Service uses CPU-based ONNX Runtime.

Future consideration:
- CUDA Toolkit (NVIDIA GPUs)
- ROCm (AMD GPUs)
- Would reduce embedding time from ~1-2s to ~0.1-0.3s per document

---

## Security & Licenses

### License Summary

All dependencies use permissive open-source licenses:
- **MIT**: Most packages (FastAPI, FastEmbed, acorn, etc.)
- **Apache-2.0**: LanceDB, aiorwlock
- **BSD-3-Clause**: uvicorn, httpx, pandas
- **PSF License**: Python, typing-extensions

**No proprietary or copyleft (GPL) licenses used.**

---

### Security Considerations

#### Dependency Scanning

We use GitHub Dependabot and manual security audits:
- **Python**: `safety check` (scans for known vulnerabilities)
- **Node.js**: `npm audit` (scans for known vulnerabilities)
- **GitHub Actions**: Automated CodeQL scanning

#### Known Security Practices

1. **Pinned Versions**: Most packages use exact versions (e.g., `fastapi==0.121.1`)
2. **Exception**: pandas uses `>=2.0.0` to allow security patches
3. **Regular Updates**: Dependencies reviewed monthly for security updates

#### Input Validation

All user inputs sanitized via:
- `app/security.py`: Validates queries, file paths, URLs
- Prevents: SQL injection, path traversal, SSRF, XSS
- Rate limiting: Configurable per-minute limits

#### Model Security

- **ONNX models**: Downloaded from HuggingFace (trusted source)
- **Checksum verification**: FastEmbed validates model integrity
- **Sandboxed execution**: ONNX Runtime runs in isolated process

---

## Dependency Update Policy

### Python Dependencies

**Update Frequency**: Monthly security review, quarterly feature updates

**Critical Security Updates**: Applied immediately upon disclosure

**Testing**: All updates tested against:
- Python 3.9, 3.10, 3.11, 3.12, 3.13
- Windows, macOS, Linux
- Full test suite (pytest)

### Node.js Dependencies

**Update Frequency**: Quarterly reviews

**Acorn Updates**: Conservative approach (only security patches)
- Acorn is mature and stable
- Breaking changes rare but possible

### Breaking Change Policy

**Major version updates** (e.g., FastAPI 0.x → 1.x):
1. Evaluate breaking changes
2. Test in development environment
3. Update documentation
4. Create migration guide if needed
5. Announce in release notes

---

## Reporting Dependency Issues

### Security Vulnerabilities

If you discover a security vulnerability in any dependency:
1. **Do NOT open a public issue**
2. Email: [Security Contact - TBD]
3. Include: Package name, version, CVE ID (if available), proof of concept

### Dependency Conflicts

If you encounter dependency conflicts:
1. Open an issue: https://github.com/edward-playground/aidefend-mcp/issues
2. Include: Python version, OS, error message, `pip freeze` output

---

## Verification Commands

### Verify All Dependencies Installed

```bash
# Python dependencies
python -m pip list

# Node.js dependencies
npm list

# Check versions
python --version
node --version
npm --version
```

### Verify Specific Critical Dependencies

```bash
# Check ONNX Runtime (Windows: requires VC++ Redistributable)
python -c "import onnxruntime; print(onnxruntime.__version__)"

# Check LanceDB
python -c "import lancedb; print(lancedb.__version__)"

# Check pandas (implicit LanceDB dependency)
python -c "import pandas; print(pandas.__version__)"

# Check FastEmbed
python -c "import fastembed; print(fastembed.__version__)"

# Check MCP SDK
python -c "import mcp; print('MCP SDK OK')"
```

---

## Transparency Statement

**Why we document dependencies in detail:**

1. **Security**: Users can audit what code runs on their systems
2. **Privacy**: All processing is local - no external API calls except:
   - GitHub API (fetch AIDEFEND content)
   - HuggingFace (download embedding model once)
3. **Trust**: Open-source dependencies only, no black boxes
4. **Reproducibility**: Exact versions documented for bug reports
5. **Licensing**: Clear license information for compliance

**Data flows:**
- **Inbound**: GitHub (AIDEFEND content), HuggingFace (ONNX model)
- **Outbound**: None (all queries processed locally)
- **Storage**: Local only (vector database, cache, logs)

---

*Last updated: 2025-11-28*
*For the latest dependency information, see [`requirements.txt`](requirements.txt) and [`package.json`](package.json).*
