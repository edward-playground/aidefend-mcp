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
   python __main__.py
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
         "command": "python",
         "args": [
           "/absolute/path/to/aidefend-mcp/__main__.py",
           "--mcp"
         ],
         "cwd": "/absolute/path/to/aidefend-mcp"
       }
     }
   }
   ```

   **Important:** Replace paths with **complete absolute paths**!
   - Replace `/absolute/path/to/aidefend-mcp/__main__.py` in the `args` field
   - Replace `/absolute/path/to/aidefend-mcp` in the `cwd` field

   **Note:** You must use full paths in both fields. The `cwd` field is necessary for Python to resolve relative imports within the project.
   - Windows example:
     - `"args": ["C:/Users/YourName/projects/aidefend-mcp/__main__.py", "--mcp"]`
     - `"cwd": "C:/Users/YourName/projects/aidefend-mcp"`
   - macOS/Linux example:
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

When running in MCP mode (`python __main__.py --mcp`), the service provides tools for AI assistants like Claude Desktop.

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

## P0 Tools - Practical Examples

The AIDEFEND MCP Service includes **8 specialized P0 tools** designed for AI security practitioners, security engineers, and developers. These tools provide targeted functionality beyond basic knowledge base search.

### Tool 1: Get Statistics

**Purpose**: Get a comprehensive overview of the AIDEFEND knowledge base - total documents, coverage by tactic/pillar/phase, and threat framework coverage.

**When to use**: Understanding the scope of the knowledge base, reporting, or checking data completeness.

#### MCP Mode Example (Claude Desktop):

```
You: "Can you show me statistics about the AIDEFEND knowledge base?"

Claude: [Uses get_statistics tool]
        The AIDEFEND knowledge base contains:
        - 156 total documents (45 techniques, 78 sub-techniques, 33 strategies)
        - Coverage across 7 tactics: Model, Harden, Detect, Isolate, Deceive, Evict, Restore
        - Threat framework coverage: 10 OWASP LLM threats, 28 MITRE ATLAS techniques
        - 34 techniques with open-source tools, 18 with commercial tools
        - 42 documents with code snippets
```

#### REST API Example:

```bash
curl http://localhost:8000/api/v1/statistics
```

**Response:**
```json
{
  "overview": {
    "total_documents": 156,
    "total_techniques": 45,
    "total_subtechniques": 78,
    "total_strategies": 33
  },
  "by_tactic": {
    "Harden": 18,
    "Detect": 12,
    "Isolate": 8,
    "Model": 7
  },
  "threat_framework_coverage": {
    "owasp_llm_items_covered": 10,
    "mitre_atlas_items_covered": 28,
    "maestro_items_covered": 15
  },
  "tools_availability": {
    "techniques_with_opensource_tools": 34,
    "techniques_with_commercial_tools": 18
  },
  "code_snippets": {
    "documents_with_code_snippets": 42
  }
}
```

---

### Tool 2: Validate Technique ID

**Purpose**: Validate if a technique ID exists and is correctly formatted. Provides fuzzy matching suggestions if ID is not found.

**When to use**: Before querying specific techniques, checking if an ID from documentation is valid, or finding similar techniques.

#### MCP Mode Example (Claude Desktop):

```
You: "Is AID-H-001 a valid technique ID?"

Claude: [Uses validate_technique_id tool]
        Yes, AID-H-001 is valid!
        - Name: Baseline Input Validation
        - Type: technique
        - Tactic: Harden
```

```
You: "What about AID-H-999?"

Claude: [Uses validate_technique_id tool]
        AID-H-999 is not found in the knowledge base.
        Did you mean:
        - AID-H-001 (Baseline Input Validation) - 85% match
        - AID-H-002 (Prompt Guard) - 78% match
```

#### REST API Example:

```bash
# Valid ID
curl -X POST "http://localhost:8000/api/v1/validate-technique-id?technique_id=AID-H-001"
```

**Response:**
```json
{
  "valid": true,
  "technique": {
    "id": "AID-H-001",
    "name": "Baseline Input Validation",
    "type": "technique",
    "tactic": "Harden"
  }
}
```

```bash
# Invalid ID with suggestions
curl -X POST "http://localhost:8000/api/v1/validate-technique-id?technique_id=AID-H-999"
```

**Response:**
```json
{
  "valid": false,
  "reason": "NOT_FOUND",
  "suggestions": [
    {
      "id": "AID-H-001",
      "name": "Baseline Input Validation",
      "similarity_score": 0.85
    }
  ]
}
```

---

### Tool 3: Get Technique Detail

**Purpose**: Get complete details for a specific technique including all sub-techniques, implementation strategies with code examples, tool recommendations, and threat mappings.

**When to use**: Deep-diving into a specific defense technique, implementing a defense control, or understanding what threats a technique defends against.

#### MCP Mode Example (Claude Desktop):

```
You: "Show me all details for technique AID-H-001"

Claude: [Uses get_technique_detail tool]
        Here's the complete breakdown of AID-H-001 (Baseline Input Validation):

        Main Technique:
        - Tactic: Harden
        - Defends against: OWASP LLM01, LLM03, MITRE ATLAS AML.T0043

        Sub-Techniques (3):
        1. AID-H-001.001: Schema Validation
           - 2 implementation strategies with Python/JavaScript code
        2. AID-H-001.002: Content Filtering
           - 3 implementation strategies
        3. AID-H-001.003: Rate Limiting
           - 2 implementation strategies

        Tools Available:
        - Open-source: prompt-toolkit, guardrails-ai, nemo-guardrails
        - Commercial: Microsoft Prompt Shield, AWS Bedrock Guardrails
```

#### REST API Example:

```bash
curl "http://localhost:8000/api/v1/technique/AID-H-001?include_code=true&include_tools=true"
```

**Response** (abbreviated):
```json
{
  "technique": {
    "id": "AID-H-001",
    "name": "Baseline Input Validation",
    "type": "technique",
    "tactic": "Harden",
    "description": "Implement baseline input validation...",
    "defends_against": [
      {
        "framework": "OWASP LLM Top 10",
        "items": ["LLM01", "LLM03"]
      }
    ],
    "tools": {
      "opensource": ["guardrails-ai", "nemo-guardrails"],
      "commercial": ["Microsoft Prompt Shield"]
    }
  },
  "subtechniques": [
    {
      "id": "AID-H-001.001",
      "name": "Schema Validation",
      "strategies": [
        {
          "strategy": "Pydantic-based validation",
          "how_to": "Use Pydantic models to validate input schema...",
          "code_blocks": [
            {
              "language": "python",
              "code": "from pydantic import BaseModel..."
            }
          ]
        }
      ]
    }
  ],
  "metadata": {
    "total_subtechniques": 3,
    "total_strategies": 7
  }
}
```

---

### Tool 4: Get Defenses for Threat

**Purpose**: Find AIDEFEND defense techniques for a specific threat. Supports threat IDs from OWASP LLM Top 10, MITRE ATLAS, MAESTRO, or natural language keywords.

**When to use**: Threat-driven defense planning, responding to specific vulnerabilities, or building defense roadmaps.

#### MCP Mode Example (Claude Desktop):

```
You: "What defenses does AIDEFEND have for OWASP LLM01?"

Claude: [Uses get_defenses_for_threat tool]
        For OWASP LLM01 (Prompt Injection), AIDEFEND recommends 8 defense techniques:

        Top Defenses:
        1. AID-H-001: Baseline Input Validation (100% match)
        2. AID-H-002: Prompt Guard (100% match)
        3. AID-D-001: Semantic Anomaly Detection (95% match)
        4. AID-I-002: Prompt Isolation (90% match)
```

```
You: "How do I defend against model poisoning attacks?"

Claude: [Uses get_defenses_for_threat with keyword search]
        For "model poisoning", here are the relevant defenses:

        1. AID-M-001: Training Data Validation (semantic match: 0.89)
        2. AID-D-003: Model Behavior Monitoring (semantic match: 0.85)
        3. AID-H-004: Model Integrity Checks (semantic match: 0.82)
```

#### REST API Example:

```bash
# Search by threat ID
curl -X POST "http://localhost:8000/api/v1/defenses-for-threat?threat_id=LLM01&top_k=5"
```

**Response:**
```json
{
  "threat_query": {
    "threat_id": "LLM01",
    "normalized_id": "LLM01",
    "threat_keyword": null
  },
  "defense_techniques": [
    {
      "technique": {
        "id": "AID-H-001",
        "name": "Baseline Input Validation",
        "tactic": "Harden"
      },
      "relevance_score": 1.0,
      "match_type": "exact_threat_id",
      "matched_threats": ["LLM01"]
    }
  ],
  "total_results": 5
}
```

```bash
# Search by keyword
curl -X POST "http://localhost:8000/api/v1/defenses-for-threat?threat_keyword=prompt%20injection&top_k=10"
```

---

### Tool 5: Get Secure Code Snippet

**Purpose**: Extract executable secure code snippets from AIDEFEND implementation strategies. Search by technique ID or topic keyword to get copy-paste ready code examples.

**When to use**: Implementing specific security controls, looking for code examples, or rapid prototyping.

#### MCP Mode Example (Claude Desktop):

```
You: "Show me code examples for input validation"

Claude: [Uses get_secure_code_snippet tool]
        I found 5 code snippets for input validation:

        Snippet 1 (Python):
        from pydantic import BaseModel, Field

        class UserPrompt(BaseModel):
            text: str = Field(max_length=500)

        def validate_input(prompt: str):
            return UserPrompt(text=prompt)

        Snippet 2 (JavaScript):
        const Joi = require('joi');
        const schema = Joi.string().max(500).required();
        ...
```

#### REST API Example:

```bash
# Get code for specific technique
curl -X POST "http://localhost:8000/api/v1/code-snippets?technique_id=AID-H-001.001&max_snippets=5"
```

**Response:**
```json
{
  "query": {
    "technique_id": "AID-H-001.001",
    "topic": null,
    "language_filter": null
  },
  "code_snippets": [
    {
      "technique_id": "AID-H-001.001",
      "technique_name": "Schema Validation",
      "tactic": "Harden",
      "code": "from pydantic import BaseModel, Field\n\nclass UserPrompt(BaseModel):\n    text: str = Field(max_length=500)",
      "language": "python",
      "description": "Use Pydantic for input validation",
      "usage_context": "Validate user prompts before sending to LLM"
    }
  ],
  "total_snippets": 5,
  "usage_notes": {
    "security_warning": "Review and test all code before using in production",
    "adaptation_required": "Code snippets may need adaptation to your specific environment"
  }
}
```

```bash
# Search by topic with language filter
curl -X POST "http://localhost:8000/api/v1/code-snippets?topic=RAG%20security&language=python&max_snippets=3"
```

---

### Tool 6: Analyze Coverage

**Purpose**: Analyze defense coverage based on implemented techniques and identify gaps. Provides coverage percentage by tactic/pillar/phase, threat framework coverage, and prioritized recommendations.

**When to use**: Security program management, gap analysis, prioritizing security investments, or reporting to leadership.

#### MCP Mode Example (Claude Desktop):

```
You: "I've implemented AID-H-001, AID-H-002, and AID-D-001. What's my coverage?"

Claude: [Uses analyze_coverage tool]
        Your defense coverage analysis:

        Overall Coverage: 18% (3 of 156 techniques implemented)
        Coverage Level: Minimal

        Coverage by Tactic:
        - Harden: 11% (2 of 18 techniques)
        - Detect: 8% (1 of 12 techniques)
        - Isolate: 0% ⚠️ CRITICAL GAP
        - Model: 0% ⚠️ CRITICAL GAP

        Critical Gaps:
        1. No Isolate techniques - Complete lack of isolation capability
        2. No Model techniques - No model hardening defenses

        Recommended Next Steps:
        1. Implement AID-I-001 (Prompt Isolation) - HIGH PRIORITY
        2. Implement AID-M-001 (Training Data Validation) - HIGH PRIORITY
        3. Achieve 50%+ coverage in Harden tactic
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/analyze-coverage" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": ["AID-H-001", "AID-H-002", "AID-D-001"],
    "system_type": "rag"
  }'
```

**Response:**
```json
{
  "analysis_summary": {
    "total_techniques_available": 156,
    "techniques_implemented": 3,
    "coverage_percentage": 18.0,
    "coverage_level": "Minimal",
    "system_type": "rag"
  },
  "coverage_by_tactic": {
    "Harden": {
      "implemented": 2,
      "total": 18,
      "percentage": 11.1,
      "status": "minimal"
    },
    "Detect": {
      "implemented": 1,
      "total": 12,
      "percentage": 8.3,
      "status": "minimal"
    },
    "Isolate": {
      "implemented": 0,
      "total": 8,
      "percentage": 0.0,
      "status": "not_covered"
    }
  },
  "critical_gaps": [
    {
      "gap_type": "tactic",
      "tactic": "Isolate",
      "severity": "HIGH",
      "reason": "No Isolate techniques implemented",
      "risk": "Complete lack of Isolate capability"
    }
  ],
  "recommendations": [
    {
      "rank": 1,
      "technique_id": "AID-I-001",
      "name": "Prompt Isolation",
      "tactic": "Isolate",
      "priority": "HIGH",
      "reason": "Fills Isolate tactic gap",
      "impact": "High - Establishes defensive capability"
    }
  ],
  "next_steps": {
    "immediate": [
      "Implement AID-I-001 (Prompt Isolation) - Fills Isolate tactic gap"
    ],
    "short_term": [
      "Achieve 50%+ coverage in all tactics",
      "Cover top 5 OWASP LLM threats"
    ],
    "long_term": [
      "Achieve 80%+ overall coverage",
      "Implement defense-in-depth across all pillars"
    ]
  }
}
```

---

### Tool 7: Map to Compliance Framework

**Purpose**: Map AIDEFEND techniques to compliance framework requirements (NIST AI RMF, EU AI Act, ISO 42001, CSA AI Controls, OWASP ASVS) using heuristic-based analysis.

**100% LOCAL** - Uses local heuristic matching based on tactic alignment, no external API calls.

**When to use**: Compliance reporting, audit preparation, governance documentation, or demonstrating regulatory alignment.

#### MCP Mode Example (Claude Desktop):

```
You: "Map AID-H-001 and AID-D-001 to NIST AI RMF"

Claude: [Uses map_to_compliance_framework tool]
        Compliance mapping to NIST AI RMF:

        AID-H-001 (Baseline Input Validation):
        - Maps to: GOVERN-1.2, MANAGE-2.1
        - Confidence: Medium
        - Rationale: Input validation aligns with risk management and governance controls

        AID-D-001 (Semantic Anomaly Detection):
        - Maps to: MEASURE-2.1, MANAGE-4.1
        - Confidence: Medium
        - Rationale: Detection techniques align with measurement and incident management

        ⚠️ Note: Mappings should be reviewed by compliance experts
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/compliance-mapping" \
  -H "Content-Type: application/json" \
  -d '{
    "technique_ids": ["AID-H-001", "AID-D-001"],
    "framework": "nist_ai_rmf"
  }'
```

**Response:**
```json
{
  "framework": {
    "id": "nist_ai_rmf",
    "name": "NIST AI Risk Management Framework"
  },
  "mappings": [
    {
      "technique_id": "AID-H-001",
      "technique_name": "Baseline Input Validation",
      "technique_tactic": "Harden",
      "framework": "nist_ai_rmf",
      "framework_name": "NIST AI Risk Management Framework",
      "framework_controls": ["GOVERN-1.2", "MANAGE-2.1"],
      "mapping_confidence": "medium",
      "mapping_rationale": "Mapped based on tactic 'Harden' alignment with framework requirements",
      "additional_considerations": [
        "Review with compliance team for completeness",
        "May require additional controls depending on specific use case",
        "Consider combination with other techniques for full compliance"
      ]
    }
  ],
  "total_mapped": 2,
  "mapping_method": "heuristic",
  "disclaimer": "Compliance mappings are generated automatically using heuristic analysis and should be reviewed by compliance experts. Mappings may not cover all requirements and should be used as guidance only."
}
```

```bash
# Map to EU AI Act
curl -X POST "http://localhost:8000/api/v1/compliance-mapping" \
  -H "Content-Type: application/json" \
  -d '{
    "technique_ids": ["AID-H-001"],
    "framework": "eu_ai_act"
  }'
```

---

### Tool 8: Get Quick Reference

**Purpose**: Generate a quick reference guide for a specific security topic. Provides actionable checklist organized by priority (quick wins, must-haves, nice-to-haves).

**When to use**: Fast decision-making, presentations to leadership, onboarding new team members, or creating security checklists.

#### MCP Mode Example (Claude Desktop):

```
You: "Give me a quick reference for prompt injection defense"

Claude: [Uses get_quick_reference tool]
        Quick Reference: Prompt Injection Defense

        🚀 QUICK WINS (Low Effort, High Impact):
        [ ] AID-H-001: Baseline Input Validation
            Effort: Low | Impact: High
        [ ] AID-H-002: Prompt Guard
            Effort: Low | Impact: Critical

        ⚡ MUST-HAVES (Essential Defenses):
        [ ] AID-D-001: Semantic Anomaly Detection
            Effort: Medium | Impact: High
        [ ] AID-I-001: Prompt Isolation
            Effort: Medium | Impact: High
        [ ] AID-H-003: Context-Aware Filtering
            Effort: Medium | Impact: High

        ✨ NICE-TO-HAVES (Additional Depth):
        [ ] AID-D-002: Behavioral Monitoring
            Effort: High | Impact: Medium
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/quick-reference?topic=RAG%20security&format=checklist&max_items=10"
```

**Response:**
```json
{
  "topic": "RAG security",
  "format": "checklist",
  "generated_at": "2025-11-11T12:00:00Z",
  "quick_wins": [
    {
      "priority": 1,
      "technique_id": "AID-H-001",
      "name": "Baseline Input Validation",
      "tactic": "Harden",
      "description": "Implement baseline input validation for RAG queries...",
      "estimated_effort": "Low",
      "estimated_impact": "High"
    }
  ],
  "must_haves": [
    {
      "priority": 1,
      "technique_id": "AID-H-003",
      "name": "Document Validation",
      "tactic": "Harden",
      "description": "Validate retrieved documents before sending to LLM...",
      "estimated_effort": "Medium",
      "estimated_impact": "High"
    }
  ],
  "nice_to_haves": [
    {
      "priority": 1,
      "technique_id": "AID-D-004",
      "name": "Retrieval Monitoring",
      "tactic": "Detect",
      "description": "Monitor retrieval patterns for anomalies...",
      "estimated_effort": "High",
      "estimated_impact": "Medium"
    }
  ],
  "formatted_output": "# QUICK WINS (Low Effort, High Impact)\n[ ] AID-H-001: Baseline Input Validation\n    Effort: Low | Impact: High\n\n# MUST-HAVES (Essential Defenses)\n[ ] AID-H-003: Document Validation\n    Effort: Medium | Impact: High\n...",
  "total_items": 10,
  "usage_notes": {
    "quick_wins": "Low effort, high impact - implement first",
    "must_haves": "Essential defenses - prioritize after quick wins",
    "nice_to_haves": "Additional depth - implement when foundational defenses are in place"
  }
}
```

```bash
# Get as markdown table
curl -X POST "http://localhost:8000/api/v1/quick-reference?topic=model%20hardening&format=table"
```

---

### Tool 9: Get Threat Coverage

**Purpose**: Analyze threat coverage for implemented defense techniques. Given a list of AIDEFEND technique IDs, calculates which threats are covered (OWASP LLM Top 10, MITRE ATLAS, MAESTRO) and provides coverage rates.

**When to use**: Track which threats your implemented defenses cover, identify coverage gaps, report security posture to stakeholders, validate defense investments.

#### MCP Mode Example (Claude Desktop):

```
You: "Analyze threat coverage for techniques AID-D-001, AID-H-002, AID-I-003"

Claude: [Uses get_threat_coverage tool]
        Threat Coverage Analysis

        Techniques Analyzed: 3
        Valid Techniques: 3
        Invalid Techniques: 0

        ## Threat Coverage by Framework

        ### OWASP LLM Top 10
        Coverage: 30.0% (3/10)
        Threats Covered: LLM01, LLM02, LLM03

        ### MITRE ATLAS
        Coverage: 4.7% (2/43)
        Threats Covered: AML.T0020, AML.T0043

        ## Coverage by Technique

        ### AID-D-001: Input Validation
        - OWASP: LLM01
        - ATLAS:

        ### AID-H-002: Prompt Guard
        - OWASP: LLM01, LLM02
        - ATLAS: AML.T0043

        ### AID-I-003: Context Isolation
        - OWASP: LLM03
        - ATLAS: AML.T0020
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/threat-coverage" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": ["AID-D-001", "AID-H-002", "AID-I-003"]
  }'
```

**Response:**
```json
{
  "input_count": 3,
  "valid_count": 3,
  "invalid_count": 0,
  "invalid_techniques": [],
  "covered": {
    "owasp": ["LLM01", "LLM02", "LLM03"],
    "atlas": ["AML.T0020", "AML.T0043"],
    "maestro": []
  },
  "coverage_rate": {
    "owasp": 0.3,
    "atlas": 0.047,
    "maestro": 0.0
  },
  "by_technique": [
    {
      "technique_id": "AID-D-001",
      "technique_name": "Input Validation",
      "tactic": "Detect",
      "threats_covered": {
        "owasp": ["LLM01"],
        "atlas": [],
        "maestro": []
      }
    }
  ],
  "timestamp": "2025-11-12T10:30:00Z"
}
```

---

### Tool 10: Get Implementation Plan

**Purpose**: Get ranked recommendations for next defense techniques to implement based on heuristic scoring (threat importance, ease of implementation, phase weight, pillar weight). Helps prioritize security investments.

**When to use**: Plan security roadmap, prioritize technique implementation, find quick wins, justify security budget, optimize defense-in-depth strategy.

**Note**: This tool provides ONLY heuristic scores. LLM should use these scores to make final recommendations via RAG.

#### MCP Mode Example (Claude Desktop):

```
You: "Give me an implementation plan, excluding techniques AID-D-001 and AID-H-002"

Claude: [Uses get_implementation_plan tool]
        Defense Implementation Plan

        Implemented Techniques: 2
        Recommendations Generated: 10

        ## Priority Categories

        - ⚡ Quick Wins (3 techniques): High score + open-source tools available
        - 🎯 High Priority (5 techniques): Score ≥ 7.0
        - 📋 Standard (2 techniques): Score < 7.0

        ## Top Recommendations

        🥇 AID-D-014: Prompt Injection Detection
           - Score: 8.5/10
           - Tactic: Detect
           - Pillar: Detect | Phase: Development
           - Score Breakdown:
             - Threat Importance: 3.0/3
             - Ease of Implementation: 2.0/2
             - Phase Weight: 1.5/2
             - Pillar Weight: 1.5/2
             - Tool Ecosystem: 0.5/1
           - Reasoning: Covers high-risk threats; Has open-source tools available; Detection adds defense-in-depth
           - ✅ Open-source tools available

        🥈 AID-H-010: Model Input Sanitization
           - Score: 7.5/10
           - Tactic: Harden
           - Pillar: Prevent | Phase: Design
           - Reasoning: Covers high-risk threats; Early-stage implementation (Design)

        🥉 AID-I-005: Prompt Isolation
           - Score: 7.0/10
           - Tactic: Isolate
           - Pillar: Prevent | Phase: Development
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/implementation-plan" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": ["AID-D-001", "AID-H-002"],
    "exclude_tactics": ["Model"],
    "top_k": 10
  }'
```

**Response:**
```json
{
  "input": {
    "implemented_count": 2,
    "exclude_tactics": ["Model"],
    "top_k": 10
  },
  "recommendations": [
    {
      "rank": 1,
      "technique_id": "AID-D-014",
      "technique_name": "Prompt Injection Detection",
      "tactic": "Detect",
      "score": 8.5,
      "score_breakdown": {
        "threat_importance": 3.0,
        "ease_of_implementation": 2.0,
        "phase_weight": 1.5,
        "pillar_weight": 1.5,
        "tool_ecosystem": 0.5
      },
      "reasoning": "Covers high-risk threats; Has open-source tools available; Detection adds defense-in-depth",
      "has_opensource_tools": true,
      "pillar": "Detect",
      "phase": "Development"
    }
  ],
  "categories": {
    "quick_wins": ["AID-D-014", "AID-D-015"],
    "high_priority": ["AID-D-014", "AID-H-010"],
    "standard": ["AID-I-005", "AID-R-001"]
  },
  "timestamp": "2025-11-12T10:30:00Z"
}
```

---

### Tool 11: Classify Threat (2-Tier Local Matching)

**Purpose**: Classify threats in text using a fast, local 2-tier matching system:
1. **Tier 1 (Static Keyword)**: Direct keyword matching (instant)
2. **Tier 2 (RapidFuzz Fuzzy Matching)**: Typo-tolerant matching (10-100x faster than difflib)

Maps common threat terms (prompt injection, model poisoning, etc.) to standard framework IDs (OWASP LLM, MITRE ATLAS, MAESTRO).

**When to use**: Normalize threat keywords from incident reports, security alerts, vulnerability descriptions, or threat intelligence to standard framework IDs. Quick triage of security events.

**How it works**:
- 100% LOCAL - No external API calls, all processing happens locally
- Tier 1: Tries static keyword matching first (instant exact matches)
- Tier 2: If no static match, uses RapidFuzz for typo-tolerant fuzzy matching
- Always indicates which tier produced the result (static_keyword, fuzzy_match, or no_match)

**Key Features**:
- **100% Local & Private**: Zero external API calls, all processing on your machine
- **FREE**: No API costs, no tokens consumed
- **Fast**: Millisecond response times with RapidFuzz (10-100x faster than difflib)
- **Offline-Ready**: Works completely offline after initial setup

#### MCP Mode Example (Claude Desktop):

```
You: "Classify the following threat: 'We detected a prompt injection attack that bypassed our input validation'"

Claude: [Uses classify_threat tool]
        Threat Classification Results

        Classification Source: 🔍 Static Keyword Match (Tier 1)
        Input Text: We detected a prompt injection attack that bypassed our input validation
        Keywords Matched: 2

        ## Matched Keywords

        🟢 Prompt Injection (Primary, confidence: 0.9)
        🟡 Insecure Output (Alias, confidence: 0.77)

        ## Normalized Threat IDs

        OWASP LLM Top 10: LLM01, LLM02
        MITRE ATLAS:

        ## Threat Details

        - OWASP-LLM01: Prompt Injection
          - Confidence: 0.9
          - Matched Keyword: prompt injection
          - Match Type: primary

        - OWASP-LLM02: Insecure Output
          - Confidence: 0.77
          - Matched Keyword: insecure output
          - Match Type: alias

        ## Recommended Next Steps

        - get_defenses_for_threat
          - Args: {'threat_id': 'LLM01'}
          - Reason: Find defense techniques for LLM01

        - get_quick_reference
          - Args: {'topic': 'prompt injection', 'max_items': 10}
          - Reason: Get actionable mitigation steps for prompt injection
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/classify-threat" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Recent training data poisoning attack detected in our ML pipeline",
    "top_k": 5
  }'
```

**Response:**
```json
{
  "source": "static_keyword",
  "input_text_preview": "Recent training data poisoning attack detected in our ML pipeline",
  "keywords_found": [
    {
      "keyword": "training data poisoning",
      "match_type": "primary",
      "confidence": 0.9
    }
  ],
  "normalized_threats": {
    "owasp": ["LLM03"],
    "atlas": ["AML.T0020"],
    "maestro": []
  },
  "threat_details": [
    {
      "threat_id": "OWASP-LLM03",
      "threat_name": "Training Data Poisoning",
      "confidence": 0.9,
      "matched_keyword": "training data poisoning",
      "match_type": "primary"
    },
    {
      "threat_id": "ATLAS-AML.T0020",
      "threat_name": "Training Data Poisoning",
      "confidence": 0.9,
      "matched_keyword": "training data poisoning",
      "match_type": "primary"
    }
  ],
  "recommended_actions": [
    {
      "tool": "get_defenses_for_threat",
      "args": {"threat_id": "LLM03"},
      "reason": "Find defense techniques for LLM03"
    },
    {
      "tool": "get_quick_reference",
      "args": {"topic": "training data poisoning", "max_items": 10},
      "reason": "Get actionable mitigation steps for training data poisoning"
    }
  ],
  "timestamp": "2025-11-12T10:30:00Z"
}
```

---

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
| `MAX_QUERY_LENGTH` | `1500` | Maximum query text length (aligned with embedding model limit) |
| `API_WORKERS` | `1` | ⚠️ **Must be 1** - Multi-worker mode not supported |
| `ENABLE_FUZZY_MATCHING` | `true` | Enable Tier 2 fuzzy matching for typo tolerance (100% local) |
| `FUZZY_MATCH_CUTOFF` | `0.70` | Minimum similarity score for fuzzy matches (0.0-1.0) |

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

### 100% Local Processing - Privacy Guaranteed

**This service is COMPLETELY LOCAL and PRIVATE:**

✅ **Zero External API Calls**
- All threat classification happens locally using 2-tier matching (static + RapidFuzz)
- All knowledge base queries processed on your machine
- Embedding generation uses local ONNX models (FastEmbed)
- No data ever leaves your infrastructure

✅ **FREE - No API Costs**
- No API keys required for any functionality
- No token consumption
- Zero ongoing costs

✅ **Works 100% Offline**
- After initial sync from GitHub, works completely offline
- No internet connection needed for queries
- Perfect for air-gapped/restricted environments

✅ **Privacy First**
- Your queries, data, and threat intelligence stay on your machine
- No telemetry, no tracking, no external logging
- Compliance-friendly for regulated industries (healthcare, finance, government)

**Architecture Flow:**
```
Your Query → Local Matching Engine (Tier 1: Static, Tier 2: RapidFuzz)
           ↓
Local Vector DB (LanceDB) → Local Embedding Model (FastEmbed/ONNX)
           ↓
Results (100% processed on your machine) ✅
```

**Future Enhancement (Optional):**
- Tier 3 local embedding semantic matching (using existing FastEmbed)
- Still 100% local, zero cost, no external API calls
- See GitHub issues for implementation timeline

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
   python __main__.py --mcp
   ```
   - You should see "Starting AIDEFEND MCP Server (stdio mode)..." in stderr
   - If it crashes, check the error message

#### MCP tools are slow or timeout

- The first query triggers initial sync (1-3 minutes)
- Check if sync is complete: `python __main__.py` then visit http://localhost:8000/api/v1/status
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
