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

### 1. Python 3.10 - 3.14

**Purpose**: Core programming language for the service
**Minimum Version**: 3.10
**Recommended Version**: Latest Python 3.14 patch release, after the current
hosted Python/OS release matrix passes
**Installation**: https://www.python.org/downloads/
**License**: PSF License (BSD-style, permissive)
**Why this version range**:
- 3.10+: Required by the declared MCP SDK and development dependency set
- Up to 3.14: Configured support range; every release requires the complete
  hosted Python/OS matrix to pass
- Uses features: `asyncio`, `pathlib`, `typing` with modern syntax

**Auto-install**: Not available (requires manual installation as prerequisite)

---

### 2. Node.js 18+

**Purpose**: Parse AIDEFEND JavaScript files with ES6 template literals
**Minimum Version**: 18.0.0
**Recommended Version**: Node.js 24 LTS
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

Application runtime dependencies are listed in
[`requirements.txt`](requirements.txt). Development and release verification
dependencies are listed in [`requirements-dev.txt`](requirements-dev.txt).
The installed runtime dependency set is approximately 500MB-1GB.

### Web Framework & Server

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **fastapi** | 0.141.1 | Modern async web framework for REST API | MIT |
| **starlette** | 1.4.1 | ASGI framework used by FastAPI | BSD-3-Clause |
| **uvicorn[standard]** | 0.52.1 | ASGI server for FastAPI | BSD-3-Clause |
| **python-multipart** | 0.0.32 | Form data parsing for FastAPI | Apache-2.0 |

**Why these versions**: The FastAPI/Starlette and multipart versions are pinned to the release-audited compatible set; uvicorn[standard] includes performance optimizations.

---

### Data Validation & Settings

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **pydantic** | 2.13.4 | Data validation and settings management | MIT |
| **pydantic-settings** | 2.14.2 | Settings management from env vars | MIT |

**Why these versions**: Pydantic v2 required for modern type validation and performance improvements.

---

### Vector Database & Embeddings

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **lancedb** | 0.25.3 | Vector database for semantic search | Apache-2.0 |
| **pyarrow** | >=16 | Arrow tables imported directly during index construction | Apache-2.0 |
| **fastembed** | 0.8.0 | CPU ONNX-based embedding generation | Apache-2.0 |
| **pillow** | 12.3.0 | Image support used by the embedding dependency chain | MIT-CMU |
| **onnxruntime** | FastEmbed 0.8-compatible, Python-marked ranges | Supported CPU ONNX inference backend imported by installer and container checks | MIT |
| **pandas** | >=2.0.0 | Data manipulation (required by LanceDB's `.to_pandas()`) | BSD-3-Clause |
| **numpy** | >=1.24,<3 | Numerical arrays used directly by the embedding cache | BSD-3-Clause |

**Why these**:
- LanceDB: Lightweight, serverless vector DB (no external database needed)
- pyarrow: Declared directly because synchronization code imports it
- FastEmbed: Provides the release-tested CPU embedding path
- onnxruntime: Declared directly as the supported CPU inference backend instead of relying on FastEmbed's transitive dependency
- pandas: Implicit dependency of LanceDB for data conversion
- numpy: Declared directly because runtime code imports it

**Downloaded Models**:
- `Xenova/multilingual-e5-base` (Quantized Int8): ~280MB ONNX model (stored in `~/.cache/fastembed/`)
- Qdrant pre-quantized version for 75% size reduction vs original (1.1GB → 280MB)
- Supports 100+ languages for multilingual semantic search

---

### MCP Protocol

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **mcp** | 1.29.0 | Model Context Protocol SDK for Claude Desktop integration | MIT |
| **pywin32** | 312 | Windows platform APIs (Windows only, required by MCP SDK) | PSF License |

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
| **slowapi** | 0.1.10 | Rate limiting middleware for FastAPI | MIT |

**Why needed**: Prevents API abuse, implements token bucket rate limiting.

---

### Utilities & Performance

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **typing-extensions** | 4.16.0 | Backports for modern type hints | PSF License |
| **beautifulsoup4** | 4.15.0 | HTML parsing (for web content) | MIT |
| **rapidfuzz** | 3.14.5 | Optimized fuzzy string matching with Python 3.14 wheels | MIT |
| **aiorwlock** | 1.5.1 | Async read-write locks for QueryEngine | Apache-2.0 |
| **anyio** | 4.14.2 | Structured cancellation shielding for safe asynchronous worker drains | MIT |

**Why these**:
- rapidfuzz: Used for typo-tolerant threat classification (Tier 2 fuzzy matching)
- aiorwlock: Prevents race conditions during database reads/writes
- anyio: Provides cancellation scopes used to drain background workers safely

---

### Development & Release Tooling

The following direct dependencies are installed through
[`requirements-dev.txt`](requirements-dev.txt) for development and release
verification only. They are not application runtime dependencies.

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **packaging** | 26.3 | Parse and compare artifact names and versions during wheel/sdist inventory verification | Apache-2.0 OR BSD-2-Clause |
| **httpx2** | 2.9.1 | Supported Starlette TestClient backend used by the integration suite | BSD-3-Clause |
| **tomli** | 2.4.1 (Python <3.11) | Read `pyproject.toml` in the Python 3.10 release verifier | MIT |
| **tokenizers** | >=0.15,<1.0 | Construct exact tokenizer fixtures in compatibility contract tests | Apache-2.0 |

---

## Node.js Parser Dependency

The release bundles the parser runtime under [`vendor/`](vendor/); production
and clean-wheel installs do not run `npm install`. The vendored Acorn module is
approximately 230 KB.

### JavaScript Parsing

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| **acorn** | 8.18.0 (exact manifest/lock pin; vendored) | Fast, standards-compliant ECMAScript parser | MIT |

**Why acorn**:
- Fast AST-based parsing (safer than `eval()`)
- Supports ES6+ syntax including template literals
- Used in Webpack, ESLint, and other trusted tools
- Source is evaluated only through the parser's closed, bounded static grammar;
  the Node.js subprocess itself is not a security sandbox

**Usage**: Called via `parse_js_module.mjs` to extract AIDEFEND technique
definitions without executing framework source code.

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

2. **External Python/model dependencies** (~780MB-1.28GB):
   - ONNX embedding model (HuggingFace cache): ~280MB (Quantized Int8)
   - Python packages (pip): ~500MB-1GB

   The approximately 230KB Acorn runtime is already included in the service
   source and Python distributions; it does not require an npm installation or
   a separate `node_modules` footprint.

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
**Note**: The default container entrypoint serves REST. MCP mode remains
available when the container is launched interactively with stdio and
`python __main__.py --mcp`; give simultaneous REST and MCP processes separate
writable `DATA_PATH` volumes.

---

### GPU Acceleration Status

AIDEFEND MCP 1.3.0 supports only the `fastembed==0.8.0` and CPU
`onnxruntime` dependency path declared by this project. It does not publish or
test a GPU installation extra. The CPU and GPU FastEmbed distributions cannot
coexist, and neither can the CPU and GPU ONNX Runtime distributions, so
replacing individual packages would create an unsupported dependency contract.

Do not substitute GPU variants in a 1.3.0 installation. A future accelerator
release would require a separate conflict-free dependency path and complete
installation, model, platform, fallback, and end-to-end validation. See
[GPU Acceleration Status](docs/advanced/GPU_ACCELERATION.md).

---

## Security & Licenses

### License Summary

All dependencies use permissive open-source licenses:
- **MIT**: FastAPI, MCP SDK, Acorn, AnyIO, ONNX Runtime, Tomli, and other MIT-licensed utilities
- **Apache-2.0**: LanceDB, PyArrow, FastEmbed, Tokenizers, python-multipart, aiorwlock
- **BSD-3-Clause**: Starlette, uvicorn, httpx, httpx2, pandas, NumPy
- **Apache-2.0 OR BSD-2-Clause**: packaging (development and release tooling only)
- **MIT-CMU**: Pillow
- **PSF License**: Python, typing-extensions

**No proprietary or copyleft (GPL) licenses used.**

---

### Security Considerations

#### Dependency Scanning

We use GitHub Dependabot and automated security audits:
- **Python**: fail-closed `pip-audit` on every CI run and in the scheduled security workflow
- **Node.js**: fail-closed `npm audit` on every CI run
- **GitHub Actions**: Automated CodeQL scanning

#### Known Security Practices

1. **Pinned Versions**: Most packages use exact versions (e.g., `fastapi==0.141.1`)
2. **Range pins**: PyArrow uses `>=16`, pandas uses `>=2.0.0`, NumPy uses `>=1.24,<3`, and ONNX Runtime follows FastEmbed's Python-specific compatibility ranges
3. **Regular Updates**: Dependencies reviewed monthly for security updates

#### Input Validation

All user inputs sanitized via:
- `app/security.py`: Validates queries, file paths, URLs
- Prevents: SQL injection, path traversal, SSRF, XSS
- Rate limiting: Configurable per-minute limits

#### Model Security

- **ONNX models**: Downloaded from HuggingFace (trusted source)
- **Checksum verification**: FastEmbed validates model integrity
- **Execution boundary**: ONNX Runtime executes in the AIDEFEND MCP Python
  process; it is not a separate process, sandbox, or isolation boundary

---

## Dependency Update Policy

### Python Dependencies

**Update Frequency**: Monthly security review, quarterly feature updates

**Critical Security Updates**: Applied immediately upon disclosure

**Release CI matrix** (must pass before publication):
- Python 3.10, 3.11, 3.12, 3.13, 3.14
- Windows, macOS, Linux
- Full test suite (pytest)

### Node.js Dependencies

**Update Frequency**: Quarterly reviews

**Acorn Updates**: Conservative same-major updates after package-integrity,
vendored-file, parser, installer, and release-artifact verification
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
2. Follow [SECURITY.md](SECURITY.md) and contact
   [Edward Lee on LinkedIn](https://www.linkedin.com/in/go-edwardlee/) privately
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

*Last updated: 2026-08-06*
*For the latest dependency information, see [`requirements.txt`](requirements.txt), [`requirements-dev.txt`](requirements-dev.txt), and [`package.json`](package.json).*
