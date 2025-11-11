[English Installation Guide](INSTALL.md) | [繁體中文安裝指南](INSTALL-繁體中文.md)

---

# Installation Guide

**Complete step-by-step installation guide for AIDEFEND MCP Service.**

This guide is designed for beginners. Every step is explained in detail. If you get stuck, check the [Troubleshooting](#troubleshooting) section.

---

## 📋 Table of Contents

1. [What You'll Need (Prerequisites)](#what-youll-need-prerequisites)
2. [Method 1: Quick Start with Scripts (Easiest)](#method-1-quick-start-with-scripts-easiest)
3. [Method 2: Docker Installation (Recommended for Production)](#method-2-docker-installation-recommended-for-production)
4. [Method 3: Manual Installation (Most Control)](#method-3-manual-installation-most-control)
5. [Verify Everything is Working](#verify-everything-is-working)
6. [Troubleshooting Common Issues](#troubleshooting-common-issues)
7. [Next Steps](#next-steps)

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

**Don't have it?** Download from: https://nodejs.org/

**Installation tips:**
- **Windows**: Use the installer from nodejs.org
- **macOS**: Use the installer or `brew install node`
- **Linux**: `sudo apt install nodejs` or `sudo yum install nodejs`

**Why is this needed?** AIDEFEND framework uses JavaScript ES6 template literals (backticks) which cannot be parsed with Python alone. The service uses Node.js subprocess to natively parse these files.

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
- **Disk Space**: 500MB free (for ML models and AIDEFEND content)
- **Internet**: Required for initial download (service works offline after setup)

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

### Step 2: Run the Start Script

**On Windows:**
```cmd
scripts\start.bat
```

**On macOS/Linux:**
```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

**What this script does automatically:**
1. ✅ Checks Python is installed
2. ✅ Creates a virtual environment (isolated Python environment)
3. ✅ Installs all required Python packages
4. ✅ Creates configuration file (`.env`)
5. ✅ Starts the service

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

**For most users, the defaults work fine. You can skip this step.**

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
Collecting fastapi==0.109.2
Downloading fastapi-0.109.2-py3-none-any.whl (92 kB)
...
Installing collected packages: ...
Successfully installed fastapi-0.109.2 ...
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
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**What this command means:**
- `python -m uvicorn` - Run the Uvicorn web server
- `app.main:app` - Load the app from `app/main.py`
- `--host 127.0.0.1` - Only accept local connections (secure)
- `--port 8000` - Run on port 8000

**Expected output:**
```
INFO - Starting AIDEFEND sync process
INFO - Downloading tactics/harden.js...
INFO - Downloading tactics/protect.js...
INFO - Parsing JavaScript files...
INFO - Embedding 1250 documents...
INFO - Indexing in LanceDB...
INFO - Sync complete! Updated to commit abc1234
INFO - QueryEngine initialized successfully
INFO - Started server process [12345]
INFO - Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
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
      "command": "python",
      "args": [
        "-m",
        "aidefend_mcp",
        "--mcp"
      ],
      "cwd": "/REPLACE/WITH/YOUR/PATH/TO/aidefend-mcp"
    }
  }
}
```

**⚠️ IMPORTANT:** Replace `/REPLACE/WITH/YOUR/PATH/TO/aidefend-mcp` with the **absolute path** where you installed AIDEFEND.

**How to find your path:**

**macOS/Linux:**
```bash
cd /path/to/aidefend-mcp
pwd
```
Copy the output (e.g., `/Users/yourname/projects/aidefend-mcp`)

**Windows:**
```cmd
cd C:\path\to\aidefend-mcp
cd
```
Copy the output, but **use forward slashes** in the JSON file:
- ✅ Good: `"cwd": "C:/Users/YourName/projects/aidefend-mcp"`
- ❌ Wrong: `"cwd": "C:\\Users\\YourName\\projects\\aidefend-mcp"`

---

### Step 3: Example Configurations

**Example 1: macOS Installation**
```json
{
  "mcpServers": {
    "aidefend": {
      "command": "python",
      "args": ["-m", "aidefend_mcp", "--mcp"],
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
      "command": "python",
      "args": ["-m", "aidefend_mcp", "--mcp"],
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
      "command": "python",
      "args": ["-m", "aidefend_mcp", "--mcp"],
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
   python -m aidefend_mcp --mcp
   ```

   You should see: `Waiting for MCP client connections...`

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
python -m aidefend_mcp  # Start in API mode
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
python -m aidefend_mcp          # REST API on http://localhost:8000
```

Terminal 2:
```bash
# Configure Claude Desktop with MCP mode (as shown above)
# MCP runs automatically when Claude Desktop connects
```

Both modes share the same knowledge base and sync service - they stay in sync automatically.

---

## Troubleshooting Common Issues

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

Or run with a different port:
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

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

**For start.sh:**
```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

**For data directory:**
```bash
chmod -R 755 data/
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

**Questions? Issues? Feature requests?**

Open an issue: https://github.com/edward-playground/aidefend-mcp/issues

**Happy deploying! 🚀**
