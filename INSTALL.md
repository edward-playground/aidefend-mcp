[English Installation Guide](INSTALL.md) | [繁體中文安裝指南](INSTALL-繁體中文.md)

---

# Installation Guide

**Complete step-by-step installation guide for AIDEFEND MCP Service.**

This guide is designed for beginners. Every step is explained in detail. If you get stuck, check the [Troubleshooting](#troubleshooting) section.

---

## 📋 Table of Contents

1. [What You'll Need (Prerequisites)](#what-youll-need-prerequisites)
2. [🚀 MCP Mode Setup (Claude Desktop) - Automated](#-mcp-mode-setup-claude-desktop---automated)
3. [Method 1: Quick Start with Scripts (Easiest)](#method-1-quick-start-with-scripts-easiest)
4. [Method 2: Docker Installation (Recommended for Production)](#method-2-docker-installation-recommended-for-production)
5. [Method 3: Manual Installation (Most Control)](#method-3-manual-installation-most-control)
6. [Verify Everything is Working](#verify-everything-is-working)
7. [Troubleshooting Common Issues](#troubleshooting-common-issues)
8. [Next Steps](#next-steps)

---

## What You'll Need (Prerequisites)

Before installing, make sure you have these programs installed on your computer.

### ✅ Required Software

#### 1. **Python 3.9 - 3.13**

**What is Python?** A programming language. This service is written in Python.

**Check if you have it:**
```bash
python --version
```

**Expected output:** `Python 3.9.x` or higher (e.g., `Python 3.11.5`, `Python 3.13.6`)

**Don't have it?** Download from: https://www.python.org/downloads/

**Installation tips:**
- **Windows**: Check "Add Python to PATH" during installation
- **macOS**: Use the installer or `brew install python`
- **Linux**: Usually pre-installed, or `sudo apt install python3`

---

#### 2. **Git** (for downloading the code)

**What is Git?** A tool for downloading code from GitHub.

**Check if you have it:**
```bash
git --version
```

**Expected output:** `git version 2.x.x`

**Don't have it?** Download from: https://git-scm.com/

---

#### 3. **Node.js 18+** (required for parsing JavaScript files)

**What is Node.js?** A JavaScript runtime required to parse AIDEFEND framework files that use JavaScript template literals.

**Check if you have it:**
```bash
node --version
```

**Expected output:** `v18.x.x` or higher (e.g., `v22.18.0`)

**Don't have it?**

✨ **NEW: Semi-Automated Installation!** The installation script can now automatically download and install Node.js LTS for you:
- Detects if Node.js >= 18 is installed
- Fetches latest LTS version info from nodejs.org API
- Downloads installer from Node.js official site (~30-35MB)
- Offers automatic installation with standard installer UI
- **Windows/macOS**: Launches installer, waits for completion, verifies installation
- **Linux**: Provides distro-specific package manager commands
- Fallback to manual instructions if needed

**How it works:**
1. Run `python scripts/install.py`
2. If Node.js is missing or version < 18, you'll see installation options:
   - **[1] Automatic installation** (recommended for Windows/macOS) - downloads and installs for you
   - **[2] Show manual instructions** - if you prefer manual control or on Linux
   - **[3] Skip** - proceed without installing (will fail later)
3. Choose option 1 for hassle-free installation!

**Manual installation (if you prefer):**
- **Windows**: Download from https://nodejs.org/ (use LTS version)
- **macOS**: Download from https://nodejs.org/ or `brew install node`
- **Linux**: Use your package manager (commands shown in auto-installer)

**Why is this needed?** AIDEFEND framework uses JavaScript ES6 template literals (backticks) which cannot be parsed with Python alone. The service uses Node.js subprocess to natively parse these files.

---

#### 4. **Microsoft Visual C++ Redistributable** (Windows Only)

**What is this?** A set of runtime libraries required by AI/ML libraries on Windows.

**Who needs it?** Windows users only (macOS and Linux users can skip this)

**When is it needed?** ONNX Runtime (used for embeddings) requires Visual C++ runtime DLLs on Windows.

**Check if you have it:**
- Open "Apps & features" in Windows Settings
- Search for "Microsoft Visual C++ 2015-2022 Redistributable"

**Don't have it?**

✨ **NEW: Semi-Automated Installation!** The installation script can now automatically download and install Visual C++ Redistributable for you:
- Detects if already installed (checks Windows registry)
- Downloads installer from Microsoft official site (~14MB)
- Offers automatic installation with minimal user interaction
- Shows UAC prompt for admin privileges (one-click approval)
- Fallback to manual instructions if needed

**How it works:**
1. Run `python scripts/install.py`
2. If Visual C++ is missing, you'll see installation options:
   - **[1] Automatic installation** (recommended) - downloads and installs for you
   - **[2] Show manual instructions** - if you prefer manual control
   - **[3] Skip** - proceed without installing (will fail later)
3. Choose option 1 for hassle-free installation!

**Manual installation (if you prefer):**
- **Latest version:** https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
- **Direct download:** https://aka.ms/vs/17/release/vc_redist.x64.exe

**Why is this needed?** Python AI/ML libraries like ONNX Runtime use native C++ code for performance. These libraries require Visual C++ runtime DLLs to function on Windows.

---

#### 5. **macOS Native Dependencies** (macOS Only, Recommended for Apple Silicon)

**What is this?** OpenMP library and Xcode Command Line Tools required for optimal ONNX Runtime performance on macOS.

**Who needs it?** macOS users, especially those with Apple Silicon (M1/M2/M3/M4) Macs.

**When is it needed?** ONNX Runtime uses OpenMP for parallel processing. While pre-built Python wheels often include bundled dependencies, some configurations may require system-level libomp for best performance.

**Check if you have Xcode Command Line Tools:**
```bash
xcode-select -p
```

**Expected output:** `/Library/Developer/CommandLineTools` or similar path

**Check if you have libomp (via Homebrew):**
```bash
brew list libomp
```

**Don't have them?**

**Install Xcode Command Line Tools:**
```bash
xcode-select --install
```

**Install Homebrew (if not installed):**
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Install libomp:**
```bash
brew install libomp
```

**Automatic Detection:** The installation script (`python scripts/install.py --check`) will detect macOS and check for these dependencies, providing warnings and instructions if they're missing.

**Note:** Installation may succeed without libomp if the pre-built Python wheels include bundled OpenMP. If you encounter ONNX-related errors after installation, install libomp as shown above.

---

### 🐳 Optional: Docker (for containerized deployment)

**What is Docker?** A tool that packages the service and all its dependencies into a "container" - think of it like a portable, isolated environment.

**When to use Docker:**
- You want the easiest installation (no Python setup needed)
- You're deploying to production
- You want to avoid "it works on my machine" issues

**Check if you have it:**
```bash
docker --version
docker-compose --version
```

**Don't have it?** Download **Docker Desktop** from: https://www.docker.com/products/docker-desktop/

---

### 💻 System Requirements

- **RAM**: 2GB minimum, 4GB recommended
- **Disk Space**: **2-2.5GB free** (breakdown below)

  **AIDEFEND Service itself (~200-700MB):**
  - Source code: ~10MB
  - Vector database (knowledge base): ~100-500MB (grows as AIDEFEND framework updates)
  - Raw content cache: ~50-100MB
  - Logs: ~10-50MB

  **Dependencies (~1.5GB):**
  - ONNX embedding model (Int8 Quantized): ~280MB
  - Python packages (pip): ~500MB-1GB (FastAPI, LanceDB, NumPy, etc.)
  - Node.js packages (npm): ~100-200MB (Acorn parser)

  **Total: 2GB minimum, up to 3GB with database growth**

- **Internet**: Required for initial download (service works offline after setup)

---

## 🚀 MCP Mode Setup (Claude Desktop) - One-Click Installation

**For users who want to use AIDEFEND with Claude Desktop**

This one-click installation installs all dependencies and configures Claude Desktop in just 5 - 8 minutes.

### Prerequisites

1. **Claude Desktop installed** - Download from: https://claude.ai/download
2. **Python 3.9+** - Check: `python --version`
3. **Node.js 18+** - Check: `node --version` (Download from: https://nodejs.org/)
4. **Git** - Check: `git --version`

### Step 1: Download AIDEFEND

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

**💡 Tip:** For macOS/Linux users, use `python3` if `python` points to Python 2:
```bash
python3 --version  # Check if you need python3 instead of python
```

### Step 2: (Optional but Recommended) Create Virtual Environment

Using a virtual environment prevents dependency conflicts with other Python projects:

```bash
# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# You should see (venv) in your terminal prompt
```

**Why use venv?**
- Isolates AIDEFEND dependencies from other Python projects
- Prevents version conflicts (e.g., if another project uses different Pydantic version)
- Easy to remove (just delete the `venv` folder)

**Note:** If you use venv, remember to activate it every time you run AIDEFEND.

### Step 3: One-Click Installation

**Check prerequisites first (recommended):**
```bash
python scripts/install.py --check
```

**Then install:**
```bash
python scripts/install.py
```

**Linux/macOS users:** Use `python3` if needed:
```bash
python3 scripts/install.py --check
python3 scripts/install.py
```

**What this script does:**
- ✅ Checks Python 3.9+ and Node.js 18+ versions
- ✅ Installs all Python dependencies (pip install -r requirements.txt)
- ✅ Installs all Node.js dependencies (npm install)
- ✅ Auto-detects your Python path and project path
- ✅ Auto-detects Claude Desktop config location
- ✅ **Safely merges** configuration (preserves all existing MCP tools)
- ✅ Creates backup of existing config
- ✅ Validates all paths before writing

**Example output:**
```
======================================================================
  AIDEFEND MCP - One-Click Installation
======================================================================

[Step 1/5] Checking Python version
----------------------------------------------------------------------
   Python version: 3.13.1
✅ Python version OK

[Step 2/5] Checking Node.js version
----------------------------------------------------------------------
   Node.js version: v20.11.0
✅ Node.js version OK

[Step 3/5] Installing Python dependencies
----------------------------------------------------------------------
Installing Python dependencies...
   Using: c:\Users\you\aidefend-mcp\requirements.txt
✅ Python dependencies installed successfully

[Step 4/5] Installing Node.js dependencies
----------------------------------------------------------------------
Installing Node.js dependencies...
   Using: c:\Users\you\aidefend-mcp\package.json
✅ Node.js dependencies installed successfully

[Step 5/5] Configuring Claude Desktop (MCP mode)
----------------------------------------------------------------------
Configuring Claude Desktop for MCP mode...
   Config file: C:\Users\you\AppData\Roaming\Claude\claude_desktop_config.json
   Python: C:/Python313/python.exe
   Project: c:/Users/you/aidefend-mcp

✅ Backup created: claude_desktop_config.json.backup.20250126_143022
✅ Preserving 2 existing MCP tool(s):
   • filesystem
   • git
✅ Configuration saved to: C:\Users\you\AppData\Roaming\Claude\claude_desktop_config.json

✅ MCP configuration completed successfully!

⚠️  IMPORTANT: Restart Claude Desktop to apply changes
   1. Completely close Claude Desktop
   2. Reopen Claude Desktop
   3. Look for 'aidefend' in MCP tools list (Search and tools icon 🔍/⚙️)

======================================================================
  ✅ Installation Complete!
======================================================================

Next steps:
  1. Restart Claude Desktop (close completely and reopen)
  2. Look for 'aidefend' in MCP tools (Search and tools icon ⚙️)
  3. Try: 'Search AIDEFEND for prompt injection defenses'
```

### Step 4: Restart Claude Desktop

**IMPORTANT:** You must **completely quit** Claude Desktop (not just close the window) and restart it.

**Windows:**
- Right-click Claude icon in system tray → Exit

**macOS:**
- Press `Cmd+Q` (or Claude menu → Quit)

**Verify tools loaded:**
- Open Claude Desktop
- Tools should appear in the available tools panel
- Ask Claude: "What AIDEFEND tools are available?"

### Step 5: First Use - Model Download

⚠️ **IMPORTANT:** On **first use**, AIDEFEND will automatically download a ~1.1GB embedding model (`multilingual-e5-base`).

**What to expect:**
- **Download time:** 5-8 minutes (depending on internet speed)
- **Storage:** ~3-4GB total (model + dependencies + knowledge base - see System Requirements above for breakdown)
- **Location:** `~/.cache/fastembed/` (macOS/Linux) or `%USERPROFILE%\.cache\fastembed\` (Windows)
- **One-time only:** Subsequent uses are instant

**If Claude seems slow on first query:**
- It's downloading the model in the background
- Check the MCP server logs if needed
- Wait a few minutes and try again

**For offline use:**
- After first download, AIDEFEND works completely offline
- No external API calls are ever made
- All processing is 100% local

### Alternative: Installation Options

The installation script supports several modes:

```bash
# Check prerequisites only (no installation)
python scripts/install.py --check

# Interactive mode (default) - asks for confirmation
python scripts/install.py

# Automatic mode - no confirmations
python scripts/install.py --auto

# Skip MCP configuration - only install dependencies
python scripts/install.py --no-mcp

# Dry run - preview without making changes
python scripts/install.py --dry-run

# Show help
python scripts/install.py --help
```

**Recommended workflow:**
```bash
# 1. Check prerequisites first
python scripts/install.py --check

# 2. If all OK, install
python scripts/install.py
```

### Uninstalling MCP Mode

To remove AIDEFEND from Claude Desktop (while keeping the project files):

```bash
python scripts/uninstall_mcp.py
```

This will:
- ✅ Remove AIDEFEND from Claude config
- ✅ Preserve all other MCP tools
- ✅ Create backup before removal
- ✅ Keep your local project files untouched

---

## 🔌 Claude Code Setup (VSCode Extension)

**For users who want to use AIDEFEND with Claude Code (VSCode extension)**

Claude Code uses a different configuration format (`.mcp.json`) than Claude Desktop.

### Quick Setup

```bash
# Install for Claude Code only
python scripts/install.py --client code

# Or install for BOTH Claude Desktop and Claude Code
python scripts/install.py --client both
```

**What this does:**
- ✅ Installs all dependencies (same as Claude Desktop)
- ✅ Creates `.mcp.json` in project root
- ✅ **Safely merges** with existing `.mcp.json` (preserves other servers)
- ✅ Ready to commit to git (shareable with team)

### After Installation

1. **Reload VSCode window**:
   - Press `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (macOS)
   - Type "Reload Window" and press Enter

2. **Verify AIDEFEND is available**:
   - Look for `aidefend` in MCP tools panel
   - Try using AIDEFEND tools via `/` slash commands

### Claude Code vs Claude Desktop

| Aspect | Claude Desktop | Claude Code |
|--------|----------------|-------------|
| **Config file** | `claude_desktop_config.json` | `.mcp.json` (project root) |
| **Location** | User config directory | Project directory |
| **Version control** | Not shared | Can be committed to git |
| **Team sharing** | Manual setup per user | Automatic (via git) |
| **Client access** | Desktop app only | VSCode only |

### Example .mcp.json

```json
{
  "mcpServers": {
    "aidefend": {
  "mcpServers": {
    "aidefend": {
      "command": "C:/path/to/python.exe",
      "args": [
        "C:/Users/you/aidefend-mcp/__main__.py",
        "--mcp"
      ],
      "env": {}
    }
  }
}
```

> **Note:** The installation script automatically detects your actual Python path and fills this in correctly. The example above uses a placeholder.

---

### Troubleshooting Installation Issues

#### Python/Node.js version errors

**Problem:** `python --version` shows Python 2.x or command not found

**Solution for macOS/Linux:**
```bash
# Use python3 instead
python3 --version
python3 scripts/install.py
```

**Solution for Windows:**
```bash
# Install Python 3.9+ from https://www.python.org/downloads/
# Make sure "Add Python to PATH" is checked during installation
```

#### `pip install` fails or times out

**Problem:** Network issues, firewall, or slow downloads

**Solution 1 - Check internet:**
```bash
python scripts/install.py --check  # Verify connectivity
```

**Solution 2 - For China users:**
```bash
# Use Tsinghua mirror
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
npm install --registry=https://registry.npmmirror.com
```

**Solution 3 - Behind corporate proxy:**
```bash
pip install -r requirements.txt --proxy YOUR_PROXY_URL
```

**Solution 4 - Upgrade pip:**
```bash
python -m pip install --upgrade pip
```

#### `npm install` fails

**Problem:** npm errors or permission issues

**Solution 1 - Clear cache:**
```bash
npm cache clean --force
npm install
```

**Solution 2 - Use different registry:**
```bash
npm install --registry=https://registry.npmjs.org/
```

#### Claude Desktop not detected

**Problem:** Warning that Claude Desktop not found

**Solution:**
- Install Claude Desktop from https://claude.ai/download
- The config will still be created for when you install it
- Not needed if you only want REST API mode

#### Dependencies conflict with other projects

**Problem:** "Version conflict" or "Cannot install pydantic 2.x"

**Solution - Use virtual environment:**
```bash
# Create isolated environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Then install
python scripts/install.py
```

#### First query is very slow

**Problem:** Claude hangs for 2-5 minutes on first AIDEFEND query

**Cause:** Downloading ~400MB embedding model (one-time only)

**Solution:**
- Wait for model download to complete (check internet connection)
- Subsequent queries will be instant
- Model stored at: `~/.cache/fastembed/` (macOS/Linux) or `%USERPROFILE%\.cache\fastembed\` (Windows)

#### MCP tools not showing in Claude Desktop

**Problem:** AIDEFEND not visible after restart

**Checklist:**
1. Did you completely quit Claude Desktop? (not just close window)
   - Windows: Right-click tray icon → Exit
   - macOS: Cmd+Q
2. Check config file exists:
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
3. Check config format is valid JSON (no trailing commas)
4. Try restarting Claude Desktop again
5. Check Claude Desktop logs for errors

#### Still having issues?

```bash
# Run diagnostic check
python scripts/install.py --check

# View detailed logs
cat data/logs/aidefend_mcp.log  # macOS/Linux
type data\logs\aidefend_mcp.log  # Windows
```

For more help, see the full troubleshooting guide below or open an issue on GitHub.

---

## Method 1: Quick Start with Scripts (Easiest)

**Recommended for:** First-time users, local development

This method uses our automated scripts to handle everything.

### Step 1: Download the Code

Open your terminal (Command Prompt on Windows, Terminal on macOS/Linux) and run:

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

**What this does:**
- Downloads all the code to a folder called `aidefend-mcp`
- Changes into that folder

**Verify you're in the right place:**
```bash
# You should see files like README.md, scripts/, app/
ls  # macOS/Linux
dir # Windows
```

---

### Step 2: Start the Service

**On any platform (Windows/macOS/Linux):**
```bash
python __main__.py
```

**What happens on first run:**
1. ✅ Automatically syncs AIDEFEND framework from GitHub (5-8 minutes)
2. ✅ Parses and indexes all security techniques
3. ✅ Starts the REST API server on http://localhost:8000
4. ✅ Service is ready for queries

**Expected output:**
```
==========================================
AIDEFEND MCP Service - Quick Start
==========================================

Checking Python version...
+ Python OK
Creating virtual environment...
+ Virtual environment created
Installing dependencies (this may take a few minutes)...
+ Dependencies installed

==========================================
Starting AIDEFEND MCP Service...
==========================================

The service will:
  1. Download AIDEFEND framework from GitHub
  2. Parse and index the content
  3. Start the API server on http://localhost:8000

This may take a few minutes on first run...

INFO - Starting AIDEFEND sync process
INFO - Downloading tactics files...
INFO - Parsing JavaScript files...
INFO - Embedding 1250 documents... (this is the slow part)
INFO - Indexing in vector database...
INFO - Sync complete!
INFO - QueryEngine initialized successfully
INFO - Application startup complete
INFO - Uvicorn running on http://127.0.0.1:8000
```

**First-time installation:** The "Embedding documents" step takes **1-3 minutes** (downloading lightweight ONNX models). This is normal!

---

### Step 3: Test the Service

**Open a new terminal** (keep the service running in the first one) and run:

```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "checks": {
    "database": true,
    "embedding_model": true,
    "sync_service": true
  }
}
```

**✅ Success!** Your service is running.

**Continue to:** [Verify Everything is Working](#verify-everything-is-working)

---

## Method 2: Docker Installation (Recommended for Production)

**Recommended for:** Production deployments, easy updates, reproducible environments

### Prerequisites for Docker Method

Make sure Docker Desktop is installed and running:
```bash
docker --version
docker-compose --version
```

---

### Step 1: Download the Code

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

---

### Step 2: (Optional) Customize Configuration

If you want to change settings (port number, sync frequency, etc.):

```bash
# Copy example config
cp .env.example .env

# Edit with your text editor
notepad .env      # Windows
nano .env         # Linux
open -e .env      # macOS
```

**⚠️ CRITICAL SECURITY REQUIREMENT:**

Docker deployments bind to `0.0.0.0` and **REQUIRE** an API Key to start.

1. **Generate a key:**
   ```bash
   python scripts/generate_api_key.py
   ```

2. **Add to `.env` file:**
   ```bash
   AUTH_MODE=api_key
   AIDEFEND_API_KEY=<your-generated-key>
   ```

> **Note:** The container will fail to start if this key is missing.

---

### Step 3: Start with Docker Compose

```bash
docker-compose up -d
```

**What this does:**
- `-d` means "detached" (runs in background)
- Builds a Docker image (first time only, takes 2-3 minutes)
- Downloads Python if needed
- Starts the service
- Creates a persistent data volume

**Expected output:**
```
Creating network "aidefend-mcp_default" ... done
Creating volume "aidefend-mcp_aidefend-data" ... done
Building aidefend-mcp
[+] Building 125.3s (18/18) FINISHED
Creating aidefend-mcp ... done
```

---

### Step 4: Watch the Logs

```bash
docker-compose logs -f
```

**What to look for:**
```
aidefend-mcp    | INFO - Starting AIDEFEND sync process
aidefend-mcp    | INFO - Downloading tactics files...
aidefend-mcp    | INFO - Embedding 1250 documents...
aidefend-mcp    | INFO - Sync complete!
aidefend-mcp    | INFO - QueryEngine initialized successfully
aidefend-mcp    | INFO - Uvicorn running on http://0.0.0.0:8000
```

**Press `Ctrl+C` to exit logs.** The container keeps running in the background.

---

### Step 5: Test the Service

```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{"status": "healthy", "checks": {"database": true, "embedding_model": true, "sync_service": true}}
```

---

### Useful Docker Commands

```bash
# View logs
docker-compose logs -f

# Stop service
docker-compose down

# Start service
docker-compose up -d

# Restart service
docker-compose restart

# Remove everything and start fresh
docker-compose down -v
docker-compose up -d
```

---

## Method 3: Manual Installation (Most Control)

**Recommended for:** Developers, customization, understanding how it works

### Step 1: Download the Code

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

---

### Step 2: Create a Virtual Environment

**What is a virtual environment?** An isolated Python environment for this project only. It prevents conflicts with other Python projects.

**On Windows:**
```cmd
python -m venv venv
venv\Scripts\activate
```

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**How to tell it worked:**
Your terminal prompt should now start with `(venv)`:
```
(venv) C:\Users\YourName\aidefend-mcp>
```

---

### Step 3: Install Python Dependencies

```bash
pip install -r requirements.txt
```

**What this installs:**
- FastAPI (web framework)
- LanceDB (vector database)
- FastEmbed (lightweight ONNX-based ML model for embeddings)
- 15+ other packages

**This will take 2-5 minutes on first run** (downloading ML models ~100MB).

**Expected output:**
```
Collecting fastapi==0.121.1
Downloading fastapi-0.121.1-py3-none-any.whl (92 kB)
...
Installing collected packages: ...
Successfully installed fastapi-0.121.1 ...
```

---

### Step 4: Create Configuration File

```bash
cp .env.example .env
```

**What's in `.env`?** Settings like:
- Port number (default: 8000)
- Sync frequency (default: every hour)
- Rate limits (default: 60 requests/minute)

**For first-time setup, you don't need to edit this file.**

---

### Step 5: Start the Service

```bash
# Default (REST API mode)
C:/Python313/python.exe __main__.py

# Or explicitly specify REST API mode
C:/Python313/python.exe __main__.py --api
```

**What this command means:**
- Runs the AIDEFEND service main program
- Starts in REST API mode by default (or use `--api` flag explicitly)
- Service will run on `127.0.0.1:8000`
- All configuration loaded from `.env` file
- Use `--mcp` flag for MCP mode, `--resync` for database rebuild, `--help` for help

**Expected output:**
```
Starting AIDEFEND REST API Server...
API will be available at: http://127.0.0.1:8000
API documentation: http://127.0.0.1:8000/docs
------------------------------------------------------------
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

**⏳ First run takes 1-3 minutes** for downloading and embedding AIDEFEND content.

---

## Verify Everything is Working

Once the service is running, test it with these commands.

### Test 1: Health Check

```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "checks": {
    "database": true,
    "embedding_model": true,
    "sync_service": true
  }
}
```

**❌ If you get an error:** The service might still be starting. Wait 1 minute and try again.

---

### Test 2: Check Sync Status

```bash
curl http://localhost:8000/api/v1/status
```

**Expected response:**
```json
{
  "status": "online",
  "sync_info": {
    "last_synced_at": "2025-11-09T10:00:00Z",
    "current_commit_sha": "abc123...",
    "total_documents": 1250,
    "is_syncing": false
  },
  "message": "Service is online and synchronized",
  "version": "1.0.0"
}
```

**What to check:**
- ✅ `"status": "online"`
- ✅ `"is_syncing": false`
- ✅ `"total_documents": 1250` (or similar number)

---

### Test 3: Try a Real Query

**Using curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "How to protect against prompt injection?",
    "top_k": 3
  }'
```

**Expected response:** JSON with AIDEFEND techniques related to prompt injection.

**Don't have curl?** Open your browser and go to:

**http://localhost:8000/docs**

This opens **Swagger UI** - an interactive API playground where you can test queries with a nice GUI.

---

### Test 4: Interactive API Documentation

**Open in your browser:**
```
http://localhost:8000/docs
```

**What you'll see:**
- All API endpoints listed
- "Try it out" buttons to test queries
- Auto-generated documentation

**Try this:**
1. Click on `POST /api/v1/query`
2. Click "Try it out"
3. Edit the request body:
   ```json
   {
     "query_text": "How to defend against model poisoning?",
     "top_k": 5
   }
   ```
4. Click "Execute"
5. See the results!

---

## Setting Up MCP Mode for Claude Desktop

**What is MCP Mode?** MCP (Model Context Protocol) allows Claude Desktop to use AIDEFEND as a tool. Instead of copying/pasting defense tactics, Claude can search the knowledge base directly during conversations.

**When to use MCP Mode:**
- You want Claude Desktop to access AIDEFEND knowledge automatically
- You're having AI-assisted security conversations
- You prefer tool-based integration over HTTP API

**When to use REST API Mode instead:**
- You're integrating with custom applications
- You need HTTP endpoints
- You're building automation scripts

---

### Prerequisites for MCP Mode

✅ You've completed one of the installation methods above
✅ You have [Claude Desktop](https://claude.ai/download) installed
✅ The AIDEFEND service is installed (doesn't need to be running for config)

---

### Step 1: Locate Claude Desktop Configuration File

Claude Desktop stores its MCP server configuration in a JSON file:

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```
On most modern Windows machine, this path is C:\Users\\[Your User Name]\AppData\Roaming\Claude\

**How to open it:**

#### macOS:
```bash
# Open in default text editor
open ~/Library/Application\ Support/Claude/claude_desktop_config.json

# Or use nano in terminal
nano ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

#### Windows:
```cmd
# Open in Notepad
notepad %APPDATA%\Claude\claude_desktop_config.json
```

**File doesn't exist?** Create it manually - it's normal if this is your first MCP server.

---

### Step 2: Add AIDEFEND Configuration

Add this configuration to the file. If the file is empty, copy everything below. If you already have other MCP servers configured, add just the `"aidefend"` section inside the existing `"mcpServers"` object.

**Template:**
```json
{
  "mcpServers": {
    "aidefend": {
      "command": "C:/Python313/python.exe",
      "args": [
        "/REPLACE/WITH/ABSOLUTE/PATH/TO/aidefend-mcp/__main__.py",
        "--mcp"
      ],
      "cwd": "/REPLACE/WITH/ABSOLUTE/PATH/TO/aidefend-mcp"
    }
  }
}
```

**⚠️ IMPORTANT:** Replace ALL paths with your actual absolute paths!

1. **Python executable path** in the `command` field:
   - Replace `C:/Python313/python.exe` with your actual Python installation path
   - To find your Python path:
     - **Windows:** Run `where python` in Command Prompt
     - **macOS/Linux:** Run `which python` or `which python3` in Terminal
   - Common locations:
     - Windows: `C:/Python313/python.exe`, `C:/Python312/python.exe`, `C:/Users/YourName/AppData/Local/Programs/Python/Python313/python.exe`
     - macOS: `/usr/local/bin/python3`, `/opt/homebrew/bin/python3`
     - Linux: `/usr/bin/python3`, `/usr/local/bin/python3`

2. **Project paths** in the `args` and `cwd` fields:
   - Replace `/REPLACE/WITH/ABSOLUTE/PATH/TO/aidefend-mcp/__main__.py` with the **complete absolute path** to the `__main__.py` file in the `args` field
   - Replace `/REPLACE/WITH/ABSOLUTE/PATH/TO/aidefend-mcp` with the **complete absolute path** to the project root directory in the `cwd` field
   - The `cwd` field is necessary for Python to resolve relative imports within the project

**How to find your path:**

**macOS/Linux:**
```bash
cd /path/to/aidefend-mcp
path=$(pwd)
echo "args: [\"$path/__main__.py\", \"--mcp\"]"
echo "cwd: \"$path\""
```
Copy both outputs for use in the configuration.

**Windows:**
```powershell
cd C:\path\to\aidefend-mcp
$path = (Get-Location).Path -replace '\\', '/'
Write-Host "args: [`"$path/__main__.py`", `"--mcp`"]"
Write-Host "cwd: `"$path`""
```
This outputs both the `args` and `cwd` values with forward slashes (e.g., `C:/Users/YourName/projects/aidefend-mcp`)

**Important tips:**
- ✅ Good: Use **forward slashes** `/` in JSON
  - `"args": ["C:/Users/YourName/projects/aidefend-mcp/__main__.py", "--mcp"]`
  - `"cwd": "C:/Users/YourName/projects/aidefend-mcp"`
- ❌ Wrong: Using backslashes `\` (will cause parsing errors)

---

### Step 3: Example Configurations

**Example 1: macOS Installation**
```json
{
  "mcpServers": {
    "aidefend": {
      "command": "C:/Python313/python.exe",
      "args": ["/Users/alice/projects/aidefend-mcp/__main__.py", "--mcp"],
      "cwd": "/Users/alice/projects/aidefend-mcp"
    }
  }
}
```

**Example 2: Windows Installation**
```json
{
  "mcpServers": {
    "aidefend": {
      "command": "C:/Python313/python.exe",
      "args": ["C:/Users/Bob/Documents/aidefend-mcp/__main__.py", "--mcp"],
      "cwd": "C:/Users/Bob/Documents/aidefend-mcp"
    }
  }
}
```

**Example 3: Multiple MCP Servers**

If you already have other MCP servers (like filesystem or git), add AIDEFEND alongside them:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/alice/Documents"]
    },
    "aidefend": {
      "command": "C:/Python313/python.exe",
      "args": ["/Users/alice/projects/aidefend-mcp/__main__.py", "--mcp"],
      "cwd": "/Users/alice/projects/aidefend-mcp"
    }
  }
}
```

---

### Step 4: Restart Claude Desktop

1. **Completely quit Claude Desktop** (not just close the window)
   - macOS: `Cmd+Q` or right-click icon → Quit
   - Windows: Right-click taskbar icon → Exit

2. **Reopen Claude Desktop**

3. **Look for the 🔌 icon** in the Claude interface
   - Click it to see available tools
   - You should see "aidefend" listed

---

### Step 5: Test the MCP Integration

Try these example prompts in Claude Desktop:

**Test 1: Basic Query**
```
Can you search AIDEFEND for prompt injection defenses?
```

Claude should automatically use the `query_aidefend` tool and return relevant defense tactics.

**Test 2: Check Status**
```
What's the status of the AIDEFEND knowledge base?
```

Claude should use `get_aidefend_status` and report document count and sync status.

**Test 3: Manual Sync**
```
Please sync the latest AIDEFEND tactics from GitHub.
```

Claude should use `sync_aidefend` to update the knowledge base.

---

### Step 6: Understanding the Tools

Claude Desktop now has access to three AIDEFEND tools:

| Tool Name | What It Does | Example Use |
|-----------|--------------|-------------|
| `query_aidefend` | Searches the AIDEFEND knowledge base | "Find defenses for model poisoning" |
| `get_aidefend_status` | Checks if service is ready and synced | "Is AIDEFEND up to date?" |
| `sync_aidefend` | Manually updates the knowledge base | "Sync latest AIDEFEND tactics" |

Claude will automatically choose which tool to use based on your question.

---

### Troubleshooting MCP Mode

#### ❌ Claude Desktop doesn't show the 🔌 icon

**Possible causes:**
1. Configuration file has syntax errors
2. Path to AIDEFEND is incorrect
3. Claude Desktop wasn't fully restarted

**Solutions:**
1. **Validate JSON syntax** - Use https://jsonlint.com/ to check your config file
2. **Check path is absolute** - Must start with `/` (macOS/Linux) or `C:/` (Windows)
3. **Use forward slashes** on Windows - Even though Windows uses `\`, JSON requires `/`
4. **Fully quit Claude** - Use Cmd+Q (macOS) or Exit from taskbar (Windows)

---

#### ❌ Tools appear but give "Connection failed" errors

**Cause:** The AIDEFEND service code has issues or dependencies are missing.

**Solutions:**
1. **Test the service manually:**
   ```bash
   cd /path/to/aidefend-mcp
   C:/Python313/python.exe __main__.py --mcp
   ```

   You should see: `Starting AIDEFEND MCP Server (stdio mode)...`

2. **Check for Python errors** - If you see error messages, the service needs fixing

3. **Verify dependencies are installed:**
   ```bash
   pip install -r requirements.txt
   ```

---

#### ❌ First query takes 2-3 minutes

**This is normal!** The first query triggers:
1. Initial sync with GitHub (downloads AIDEFEND tactics)
2. Parsing all JavaScript files
3. Generating embeddings
4. Building vector database

**After the first sync**, queries take less than 1 second.

**Tip:** Run a manual sync before using Claude:
```bash
C:/Python313/python.exe __main__.py  # Start in API mode
# Visit http://localhost:8000/api/v1/status to check sync status
```

---

#### ❌ "Database sync in progress" error

**Cause:** You're querying while the background sync is running.

**Solution:** Wait 30 seconds and try again. This protects against data corruption during sync.

---

### Using Both REST API and MCP Modes

**Can I use both?** Yes! They're completely independent:

- **MCP Mode**: For Claude Desktop conversations
- **REST API Mode**: For HTTP integrations, scripts, other applications

**Running both simultaneously:**

Terminal 1:
```bash
C:/Python313/python.exe __main__.py          # REST API on http://localhost:8000
```

Terminal 2:
```bash
# Configure Claude Desktop with MCP mode (as shown above)
# MCP runs automatically when Claude Desktop connects
```

Both modes share the same knowledge base and sync service - they stay in sync automatically.

---

## Troubleshooting Common Issues

### ℹ️ About Automatic Cache Management

**Good news:** You never need to manually delete cache files!

AIDEFEND MCP uses **automatic cache invalidation** to ensure data consistency:

**Automatic Updates:**
- ✅ **Content updates**: System checks GitHub hourly for new techniques and updates automatically
- ✅ **Schema updates**: Cache auto-invalidates when metadata format changes
- ✅ **Model changes**: Detected automatically and triggers rebuild

**When to use `--resync`:**
Only needed in special cases:
- Changing embedding model (e.g., from e5-base to embeddinggemma)
- Database corruption
- Development/testing with clean state

**What happens during auto-update:**
```
System detects change → Downloads new data → Updates embeddings → Ready to use
```
No user intervention required!

---

### ❌ Issue: "Python not found" or "python: command not found"

**Possible causes:**
1. Python is not installed
2. Python is not in your system PATH

**Solutions:**

**Windows:**
1. Reinstall Python from https://www.python.org/downloads/
2. **Important:** Check "Add Python to PATH" during installation
3. Restart your Command Prompt

**macOS/Linux:**
```bash
# Try python3 instead of python
python3 --version

# If that works, use python3 for all commands
python3 -m venv venv
```

---

### ❌ Issue: "pip: command not found"

**macOS/Linux solution:**
```bash
# Use pip3 instead
pip3 install -r requirements.txt
```

**Windows solution:**
```cmd
# Use python -m pip
python -m pip install -r requirements.txt
```

---

### ❌ Issue: "Address already in use" or "Port 8000 is already allocated"

**Meaning:** Another program is using port 8000.

**Solution 1: Find and stop the other program**

**Windows:**
```cmd
netstat -ano | findstr :8000
taskkill /PID <PID_from_above> /F
```

**macOS/Linux:**
```bash
lsof -i :8000
kill -9 <PID_from_above>
```

**Solution 2: Use a different port**

Edit `.env`:
```env
API_PORT=8001
```

Then restart the service normally with `C:/Python313/python.exe __main__.py` (it will read the new port from `.env`)

---

### ❌ Issue: Service starts but queries return "503 Service Not Ready"

**Meaning:** The initial sync is still running.

**Solution:** Wait 1-3 minutes for the embedding process to complete.

**Check sync status:**
```bash
curl http://localhost:8000/api/v1/status
```

**Look for:**
```json
{
  "sync_info": {
    "is_syncing": true  ← Still syncing, wait
  }
}
```

**If `is_syncing` is stuck on `true` for more than 10 minutes:**

1. Check logs: `tail -f data/logs/aidefend_mcp.log`
2. Check internet connection: `curl https://api.github.com`
3. Restart the service

---

### ❌ Issue: "ModuleNotFoundError: No module named 'fastapi'"

**Meaning:** Dependencies not installed, or virtual environment not activated.

**Solution:**

1. **Activate virtual environment:**
   ```bash
   # Windows
   venv\Scripts\activate

   # macOS/Linux
   source venv/bin/activate
   ```

2. **Reinstall dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

### ❌ Issue: Docker container keeps restarting

**Check logs:**
```bash
docker-compose logs aidefend-mcp
```

**Common causes:**

1. **Out of memory:**
   - Open Docker Desktop → Settings → Resources
   - Increase memory to at least 2GB

2. **Network issues:**
   - Check internet connection
   - Verify GitHub is accessible: `curl https://api.github.com`

3. **Port conflict:**
   - Another service using port 8000
   - Change in `docker-compose.yml`: `"8001:8000"`

---

### ❌ Issue: Embedding process is very slow (>10 minutes)

**Normal on first run:** 1-3 minutes for ~1250 documents

**If it takes longer:**

**Possible causes:**
1. **Slow internet** - downloading ML models (~100MB)
2. **Slow CPU** - embedding is CPU-intensive
3. **Low RAM** - system is swapping to disk

**Solutions:**
1. **Check download speed:** Visit https://fast.com
2. **Close other programs** to free up CPU/RAM
3. **Be patient** - it only happens on first run
4. **For very slow machines:** Consider using a cloud server

---

### ❌ Issue: "Permission denied" (Linux/macOS)

**For data directory:**
```bash
chmod -R 755 data/
```

**For main script:**
```bash
chmod +x __main__.py
```

---

### ❌ Issue: curl commands don't work on Windows

**Solution 1: Use PowerShell instead of Command Prompt**

PowerShell has curl built-in.

**Solution 2: Use the browser**

Go to http://localhost:8000/docs and use the interactive UI.

**Solution 3: Install curl for Windows**

Download from: https://curl.se/windows/

---

## Next Steps

### 🎉 Congratulations! Your service is running.

**What to do next:**

1. **Read the API Documentation**
   - Open http://localhost:8000/docs
   - Try different queries
   - See what data is returned

2. **Integrate with Your LLM**
   - Use the `/api/v1/query` endpoint
   - Send user questions
   - Get relevant AIDEFEND context
   - Pass context to your LLM (GPT-4, Claude, etc.)

3. **Customize Configuration**
   - Edit `.env` to change settings
   - Adjust rate limits
   - Change sync frequency

4. **Learn More**
   - Read [README.md](README.md) for API usage examples
   - Review [SECURITY.md](SECURITY.md) for deployment best practices

---

## Getting Help

**If you're still stuck:**

1. **Check existing issues:** https://github.com/edward-playground/aidefend-mcp/issues
2. **Search discussions:** https://github.com/edward-playground/aidefend-mcp/discussions
3. **Create a new issue** with:
   - Your operating system (Windows 11, macOS 14, Ubuntu 22.04, etc.)
   - Python version: `python --version`
   - Full error message (copy-paste)
   - What you tried
   - Relevant log files

---

## Uninstalling

**Local Installation:**
```bash
# Stop the service (Ctrl+C)

# Deactivate virtual environment
deactivate

# Remove everything
cd ..
rm -rf aidefend-mcp  # macOS/Linux
rd /s aidefend-mcp   # Windows
```

**Docker Installation:**
```bash
# Stop and remove everything
docker-compose down -v

# Remove directory
cd ..
rm -rf aidefend-mcp
```

---

## Troubleshooting

### Resync Database

If you encounter database issues or need to upgrade the embedding model, use the resync command:

```bash
python __main__.py --resync
```

**When to use:**
- ✅ Upgrading to a different embedding model
- ✅ Database corruption or errors
- ✅ Starting fresh with clean data
- ✅ After changing `EMBEDDING_MODEL` in `.env`

**What it does:**
1. Deletes existing database (`data/aidefend_kb.lancedb`)
2. Deletes version tracking (`data/local_version.json`)
3. Re-downloads content from GitHub
4. Rebuilds database with current configuration
5. Recreates embedding cache

**Note:** This is a safe operation - all data is recoverable from the source repository.

**After resync, start your preferred mode:**
```bash
# Start MCP mode
python __main__.py --mcp

# Or start REST API
python __main__.py --api
```

### Common Issues

**Database model mismatch:**
```
❌ Embedding model upgrade detected!
   Database model: intfloat/multilingual-e5-small (384d)
   Configured model: Xenova/multilingual-e5-base (768d)
```
**Solution:** Run `python __main__.py --resync`

**Database corruption:**
```
Error: Failed to load database
```
**Solution:** Run `python __main__.py --resync`

**Service not responding:**
- Check if service is running: `ps aux | grep python` (Unix) or Task Manager (Windows)
- Check logs: `tail -f data/logs/aidefend_mcp.log`
- Restart the service

**MCP tools not showing in Claude Desktop:**
- Verify `claude_desktop_config.json` paths are absolute (not relative)
- Restart Claude Desktop completely
- Check Python path: `which python3` (Unix) or `where python` (Windows)

---

**Questions? Issues? Feature requests?**

Open an issue: https://github.com/edward-playground/aidefend-mcp/issues

**Happy deploying! 🚀**
