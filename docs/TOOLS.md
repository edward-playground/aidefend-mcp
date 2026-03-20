# AIDEFEND MCP Tools - Complete Reference

This document provides detailed documentation for all **18 MCP tools** available in the AIDEFEND MCP Service.

## Tool Categories

### Basic Query Tools (3 tools)
Essential tools for interacting with the AIDEFEND knowledge base.

### Professional Analysis Tools (15 tools)
Specialized P0 tools for AI security practitioners, security engineers, and developers.

---

## Basic Query Tools

### Tool 1: Query AIDEFEND

**Purpose**: Search the AIDEFEND AI security defense knowledge base using natural language queries.

**When to use**: Finding defense strategies, techniques, and best practices for AI/ML security threats.

#### MCP Mode Example (Claude Desktop):

```
You: "How do I defend against prompt injection attacks?"

Claude: [Uses query_aidefend tool]
        Based on AIDEFEND, here are the key defense techniques:

        1. AID-H-001: Baseline Input Validation
        2. AID-H-002: Prompt Guard
        3. AID-D-001: Semantic Anomaly Detection
        ...
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query_text": "How to prevent prompt injection",
    "top_k": 5
  }'
```

---

### Tool 2: Get AIDEFEND Status

**Purpose**: Check the current status of the AIDEFEND knowledge base including framework version, total indexed documents, embedding model info, and sync status.

**When to use**: Verifying service readiness, checking framework version, checking sync status, troubleshooting.

#### MCP Mode Example (Claude Desktop):

```
You: "What's the status of the AIDEFEND service?"

Claude: [Uses get_aidefend_status tool]
        AIDEFEND Service Status:
        - Total documents: 156
        - Embedding model: Xenova/multilingual-e5-base
        - Last sync: 2 hours ago
        - Service ready: Yes
```

#### REST API Example:

```bash
curl http://localhost:8000/api/v1/status
```

**Response:**
```json
{
  "service_ready": true,
  "total_documents": 156,
  "embedding_model": "Xenova/multilingual-e5-base",
  "last_sync": "2025-01-18T10:30:00Z",
  "framework_version": "1.20251107"
}
```

---

### Tool 3: Sync AIDEFEND

**Purpose**: Manually trigger synchronization with the AIDEFEND GitHub repository to fetch the latest defense tactics and techniques.

**When to use**: Force update to latest framework version, troubleshooting outdated content.

**Note**: Auto-sync runs every hour by default. This may take a few minutes.

#### MCP Mode Example (Claude Desktop):

```
You: "Can you sync the AIDEFEND knowledge base to the latest version?"

Claude: [Uses sync_aidefend tool]
        Starting sync with GitHub...
        Downloading latest content...
        Parsing techniques...
        Generating embeddings...
        ✅ Sync complete! Knowledge base updated to version 1.20251118
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/sync"
```

**Response:**
```json
{
  "status": "success",
  "message": "Sync completed successfully",
  "framework_version": "1.20251118",
  "documents_synced": 158,
  "sync_duration_seconds": 42.3
}
```

---

## Professional Analysis Tools (P0 Tools)

### Tool 4: Get Statistics

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
    "owasp_llm_total_items": 10,
    "owasp_llm_coverage_percentage": 100.0,
    "mitre_atlas_items_covered": 28,
    "maestro_items_covered": 15,
    "techniques_with_threat_mappings": 40,
    "techniques_mapped_percentage": 88.9
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

### Tool 6: Validate Technique ID

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

### Tool 7: Get Technique Detail

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

#### ⚡ Performance Tip

If you need implementation strategies for **multiple techniques at once** (e.g., top 5-10 recommendations from an implementation plan), use **Tool 14: Get Implementation Plan** with `detail_level="standard"` or `"detailed"` instead. This eliminates the N+1 query problem and reduces latency by 85-90%.

**Example scenario:**
- ❌ Slow: Get implementation plan (basic) → Call get_technique_detail 5 times (2-3 minutes)
- ✅ Fast: Get implementation plan with `detail_level="standard"` (10-20 seconds)

Use get_technique_detail when you need:
- Details for a **single technique** outside the top recommendations
- Complete information for techniques ranked beyond top 5
- Direct technique ID queries

---

### Tool 8: Get Defenses for Threat

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

### Tool 9: Get Secure Code Snippet

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

#### 💡 Best Practice Workflow

When working with implementation plans, use this recommended workflow:

1. **Get overview**: Use **Tool 14: Get Implementation Plan** with `detail_level="standard"` to get technique recommendations with brief strategy summaries (10-20 seconds)
2. **Present to user**: Show the recommendations and summaries to help user select priorities
3. **Get code examples**: Use `get_secure_code_snippet` for specific techniques the user wants to implement

**Example scenario:**
- ❌ Old approach: Get plan (basic) → Call get_technique_detail 5 times → Call get_secure_code_snippet 5 times (2-4 minutes)
- ✅ Recommended: Get plan (standard) → Show summaries → Call get_secure_code_snippet only for selected techniques (10-30 seconds total)

Use get_secure_code_snippet when you need:
- Code for **specific techniques** outside the top recommendations
- Complete code collections with **language filtering**
- Code from techniques ranked beyond top 5

---

### Tool 10: Analyze Coverage

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

### Tool 11: Map to Compliance Framework

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

### Tool 12: Get Quick Reference

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

### Tool 13: Get Threat Coverage

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

### Tool 14: Get Implementation Plan

**Purpose**: Get ranked recommendations for next defense techniques to implement based on heuristic scoring (threat importance, ease of implementation, phase weight, pillar weight). Helps prioritize security investments.

**When to use**: Plan security roadmap, prioritize technique implementation, find quick wins, justify security budget, optimize defense-in-depth strategy.

**Note**: This tool provides ONLY heuristic scores. LLM should use these scores to make final recommendations via RAG.

**⚡ Compound Tool Pattern**: Use `detail_level="standard"` (recommended) or `detail_level="detailed"` to get actionable strategy summaries for the top 5 recommendations in a single call, eliminating the N+1 query problem (90-95% latency reduction).

**Strategy Querying**:
- Uses **union logic** to query BOTH parent-level and sub-technique-level strategies
- Adds `context_source` field for strategies from sub-techniques (helps identify which sub-technique a strategy relates to)
- **NEVER includes code snippets automatically** - use `get_secure_code_snippet` separately for specific techniques

**Parameters**:
- `implemented_techniques` (optional): List of already implemented technique IDs
- `exclude_tactics` (optional): List of tactics to exclude (e.g., ["Model", "Harden"])
- `top_k` (default: 10): Number of recommendations to return (1-20)
- `detail_level` (default: "basic"): Level of detail
  - **"basic"**: Returns technique IDs and scores only (fastest, original behavior)
  - **"standard"**: Returns brief summaries (200 chars) for top 5 techniques (recommended for most use cases)
  - **"detailed"**: Returns full summaries (500 chars) for top 5 techniques (for comprehensive planning)

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

#### REST API Example 1: Basic Mode (default)

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
    "top_k": 10,
    "detail_level": "basic"
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

#### REST API Example 2: Standard Mode (Recommended - Compound Tool)

```bash
curl -X POST "http://localhost:8000/api/v1/implementation-plan" \
  -H "Content-Type: application/json" \
  -d '{
    "implemented_techniques": [],
    "exclude_tactics": [],
    "top_k": 5,
    "detail_level": "standard"
  }'
```

**Response:**
```json
{
  "input": {
    "implemented_count": 0,
    "exclude_tactics": [],
    "top_k": 5,
    "detail_level": "standard"
  },
  "recommendations": [
    {
      "rank": 1,
      "technique_id": "AID-D-014",
      "technique_name": "Prompt Injection Detection",
      "score": 8.5,
      ...
    }
  ],
  "categories": {
    "quick_wins": ["AID-D-014"],
    "high_priority": ["AID-D-014", "AID-H-010"],
    "standard": []
  },
  "actionable_strategies": [
    {
      "technique_id": "AID-D-014",
      "technique_name": "Prompt Injection Detection",
      "strategy_count": 3,
      "strategies": [
        {
          "strategy_name": "Semantic Similarity Detection",
          "summary": "Use embeddings to detect prompt injections by measuring semantic similarity between user inputs and known attack patterns. This approach compares input text against a database of known..."
        },
        {
          "strategy_name": "Rule-Based Detection",
          "summary": "Implement pattern matching rules to identify common injection techniques. Rules check for suspicious patterns like system commands, SQL syntax, and script tags...",
          "context_source": "Direct Injection"
        }
      ]
    }
  ],
  "metadata": {
    "compound_tool_enabled": true,
    "detail_level": "standard",
    "strategies_fetched": 5
  },
  "timestamp": "2025-11-12T10:30:00Z"
}
```

**Note**: Strategies with `context_source` field indicate they come from a sub-technique. This helps you understand the specific context of the strategy.

**💡 Recommended Workflow**:
1. Use `detail_level="standard"` to get quick overview with 200-char summaries (~10-20 seconds)
2. Present recommendations to user
3. Use `get_secure_code_snippet(technique_id, strategy_name)` for specific techniques user selects

**Performance Comparison**:
- **Before** (basic mode + repeated get_technique_detail calls): 2-3 minutes for full details
- **After** (standard/detailed mode): 10-20 seconds for actionable summaries
- **Improvement**: 85-90% latency reduction

---

### Tool 15: Classify Threat (2-Tier Local Matching)

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

### Tool 16: Comprehensive Search (Multi-Query Aggregation)

**Purpose**: Execute multiple search queries in parallel and aggregate results intelligently. Auto-expands broad topics into specific queries for comprehensive coverage.

**When to use**: Broad security topics, research-oriented exploration, getting full picture of a security domain, or when you don't know exact keywords.

#### MCP Mode Example (Claude Desktop):

```
You: "Tell me everything about deepfake defenses in AIDEFEND"

Claude: [Uses comprehensive_search tool]
        Comprehensive Search Results for: deepfake defenses

        Queries Executed: 3 parallel searches
        Total Results: 15 unique techniques

        Query 1: "deepfake detection" (5 results)
        Query 2: "synthetic media defense" (5 results)
        Query 3: "media authenticity" (5 results)

        Top Techniques:
        1. AID-D-008: Deepfake Detection (Score: 0.92)
        2. AID-H-015: Media Validation (Score: 0.88)
        3. AID-D-009: Synthetic Content Analysis (Score: 0.85)
        ...
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/comprehensive-search" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "RAG security best practices",
    "max_results": 20
  }'
```

**Response:**
```json
{
  "topic": "RAG security best practices",
  "queries_executed": 4,
  "total_results": 18,
  "query_breakdown": [
    {
      "query": "retrieval augmented generation security",
      "results_count": 6
    },
    {
      "query": "vector database security",
      "results_count": 5
    },
    {
      "query": "document injection prevention",
      "results_count": 4
    },
    {
      "query": "RAG prompt safety",
      "results_count": 3
    }
  ],
  "aggregated_results": [
    {
      "technique_id": "AID-H-003",
      "name": "Document Validation",
      "tactic": "Harden",
      "relevance_score": 0.91,
      "matched_queries": ["retrieval augmented generation security", "document injection prevention"]
    }
  ]
}
```

---

### Tool 17: Analyze Security Posture

**Purpose**: Unified security posture analysis combining technical coverage, threat framework coverage, and actionable recommendations. One-stop shop for comprehensive security assessment.

**When to use**: Executive reporting, security program assessment, quarterly reviews, or establishing security baseline.

#### MCP Mode Example (Claude Desktop):

```
You: "Analyze my security posture. I've implemented: AID-H-001, AID-H-002, AID-D-001, AID-I-001"

Claude: [Uses analyze_security_posture tool]
        Security Posture Analysis

        Overall Assessment: DEVELOPING
        Techniques Implemented: 4

        ## Technical Coverage
        - Coverage: 25% (4/156 techniques)
        - By Tactic:
          • Harden: 11% (2/18) ⚠️
          • Detect: 8% (1/12) ⚠️
          • Isolate: 12.5% (1/8) ⚠️

        ## Threat Framework Coverage
        - OWASP LLM Top 10: 40% (4/10 threats covered)
        - MITRE ATLAS: 7% (3/43 threats covered)
        - MAESTRO: 15% (2/13 threats covered)

        ## Key Insights
        - ✅ Good foundation in Harden tactic
        - ⚠️ Limited detection capabilities
        - ❌ No Model hardening techniques
        - ⚠️ Low ATLAS coverage

        ## Top Priorities
        1. Implement AID-D-002 (Anomaly Detection) - Fills detection gap
        2. Implement AID-M-001 (Training Data Validation) - Addresses Model tactic gap
        3. Cover top ATLAS threats: AML.T0043, AML.T0020
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/analyze-security-posture" \
  -H "Content-Type" application/json" \
  -d '{
    "implemented_techniques": ["AID-H-001", "AID-H-002", "AID-D-001", "AID-I-001"],
    "view": "both",
    "system_type": "rag"
  }'
```

**Response:**
```json
{
  "implemented_count": 4,
  "summary": {
    "overall_posture": "developing",
    "key_insights": [
      "Good foundation in Harden tactic",
      "Limited detection capabilities",
      "No Model hardening techniques"
    ],
    "top_priorities": [
      "Implement AID-D-002 (Anomaly Detection)",
      "Implement AID-M-001 (Training Data Validation)"
    ]
  },
  "technical_coverage": {
    "overall_coverage": {
      "percentage": 25.0,
      "implemented": 4,
      "total": 156
    },
    "by_tactic": [
      {"tactic": "Harden", "percentage": 11.1, "implemented": 2, "total": 18}
    ],
    "critical_gaps": [
      {"technique_id": "AID-M-001", "name": "Training Data Validation", "tactic": "Model"}
    ]
  },
  "threat_coverage": {
    "coverage_rate": {
      "owasp": 0.4,
      "atlas": 0.07,
      "maestro": 0.15
    },
    "covered_threats": {
      "owasp": ["LLM01", "LLM02", "LLM03", "LLM05"],
      "atlas": ["AML.T0020", "AML.T0043", "AML.T0051"]
    },
    "uncovered_threats": {
      "owasp": ["LLM04", "LLM06", "LLM07", "LLM08", "LLM09", "LLM10"]
    }
  }
}
```

---

### Tool 18: Compare Techniques

**Purpose**: Side-by-side comparison of multiple AIDEFEND techniques with heuristic scoring (effectiveness, complexity, cost). Helps make informed implementation decisions.

**When to use**: Technology selection, budget prioritization, understanding trade-offs, or educating stakeholders.

**100% LOCAL** - All scoring uses heuristic algorithms based on metadata, no external API calls.

### Scoring Logic (Context-Aware)

- **Effectiveness (0-100)**:
  - **Prevention Bonus (+25)**: Higher score for preventive controls (hardening, filters) vs. detection.
  - **Asset Criticality (+15)**: Bonus for protecting critical assets like Model Weights or Training Data.
  - **Validation Ready (+10)**: Bonus if technique is verifiable/testable.
  - **Threat Coverage**: Points for each OWASP/ATLAS/MAESTRO threat covered.

- **Complexity (0-100)**:
  - **Cross-Domain Friction**: Penalties for techniques requiring cross-team coordination (e.g., DevOps + Data Science).
  - **Human Scale**: Penalties for process-heavy techniques (training, policy).
  - **Integration Phase**: "Building" phase techniques are rated as higher complexity than runtime deployment.

- **Cost (0-100)**:
  - **OpEx vs CapEx**: "Detection" techniques have higher OpEx scores (logs, alerts) than "Prevention" (set-and-forget).
  - **Cloud Costs**: Cloud-native techniques include estimated infrastructure costs.
  - **Tooling**: Commercial tools add cost; pure open-source reduces cost.

#### MCP Mode Example (Claude Desktop):

```
You: "Compare AID-H-001, AID-D-001, and AID-I-001. Which should I implement first?"

Claude: [Uses compare_techniques tool]
        Technique Comparison Matrix

        Techniques Compared: 3

        ## Summary Statistics
        - Average Effectiveness: 75.0/100
        - Average Complexity: 45.0/100
        - Average Cost: 38.0/100

        ## Comparison Matrix

        | Technique | Effectiveness | Complexity | Cost |
        |-----------|---------------|------------|------|
        | AID-H-001 | 85/100 | 35/100 | 30/100 |
        | AID-D-001 | 75/100 | 50/100 | 40/100 |
        | AID-I-001 | 65/100 | 50/100 | 45/100 |

        ## Implementation Recommendations

        ### Quick Wins
        - AID-H-001: High effectiveness (85), low complexity (35), low cost (30)

        ### Implementation Priority (by effectiveness/complexity ratio)
        1. AID-H-001 (ratio: 2.43) ⭐ Highest ROI
        2. AID-D-001 (ratio: 1.50)
        3. AID-I-001 (ratio: 1.30)

        Recommendation: Start with AID-H-001 for quick impact!
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/compare-techniques" \
  -H "Content-Type: application/json" \
  -d '{
    "technique_ids": ["AID-H-001", "AID-D-001", "AID-I-001"],
    "include_recommendations": true
  }'
```

**Response:**
```json
{
  "input_techniques": ["AID-H-001", "AID-D-001", "AID-I-001"],
  "comparison_matrix": [
    {
      "source_id": "AID-H-001",
      "name": "Baseline Input Validation",
      "tactic": "Harden",
      "effectiveness_score": 85,
      "complexity_score": 35,
      "cost_score": 30,
      "threat_coverage": {
        "owasp": 3,
        "atlas": 2,
        "maestro": 1
      },
      "has_implementation_strategies": true,
      "has_code_snippets": true,
      "has_opensource_tools": true
    }
  ],
  "summary": {
    "techniques_compared": 3,
    "average_effectiveness": 75.0,
    "average_complexity": 45.0,
    "average_cost": 38.3
  },
  "recommendations": [
    {
      "category": "Quick Wins",
      "description": "High effectiveness, low complexity, low cost",
      "techniques": [
        {"id": "AID-H-001", "name": "Baseline Input Validation"}
      ]
    },
    {
      "category": "Implementation Priority",
      "description": "Ordered by effectiveness-to-complexity ratio",
      "techniques": [
        {"id": "AID-H-001", "name": "Baseline Input Validation"},
        {"id": "AID-D-001", "name": "Semantic Anomaly Detection"},
        {"id": "AID-I-001", "name": "Prompt Isolation"}
      ]
    }
  ]
}
```

---

### Tool 19: Generate Incident Playbook

**Purpose**: Generate structured incident response playbooks for AI security incidents. Provides timeline-based action plans following NIST incident response phases.

**When to use**: Active incident response, IR planning, training materials, or security operations runbook development.

**100% LOCAL** - Integrates with local classify_threat and get_defenses_for_threat tools, no external API calls.

#### MCP Mode Example (Claude Desktop):

```
You: "We detected suspicious prompt injection attempts bypassing our validation. Generate an incident playbook."

Claude: [Uses generate_incident_playbook tool]
        🚨 Incident Response Playbook

        Primary Threat Identified: OWASP-LLM01 (Prompt Injection)
        Confidence: 90%
        Total Action Items: 23

        ## Immediate Actions (0-15 min)

        1. 🔴 Activate Incident Response Team
           Priority: CRITICAL
           Time: 2-5 minutes

        2. 🔴 Isolate Affected LLM Endpoints
           Priority: CRITICAL
           Time: 5 minutes
           Description: Temporarily disable or rate-limit affected endpoints

        ## Investigation (15 min - 2 hours)

        1. 🟠 Perform Threat Classification
           Priority: HIGH
           Time: 10-15 minutes
           Tools: classify_threat tool

        2. 🟠 Collect IOCs
           Priority: HIGH
           Time: 20-30 minutes
           Description: Gather IP addresses, user IDs, timestamps, request patterns

        ## Containment (2-8 hours)

        1. 🔴 Deploy Defense: AID-H-001 (Baseline Input Validation)
           Priority: HIGH
           Time: 1-3 hours

        2. 🔴 Deploy Defense: AID-H-002 (Prompt Guard)
           Priority: HIGH
           Time: 1-3 hours

        ## Recovery & Remediation (8+ hours)

        1. 🟠 Implement Security Controls
           Priority: HIGH
           Time: 4-8 hours
           Reference: See defense techniques in containment phase

        2. 🟡 Conduct Post-Incident Review
           Priority: MEDIUM
           Time: 2-3 hours
```

#### REST API Example:

```bash
curl -X POST "http://localhost:8000/api/v1/generate-incident-playbook" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_description": "Production LLM API showing unusual outputs. Users report getting responses that reveal internal system prompts and training data. Attack patterns from multiple IPs.",
    "include_defense_techniques": true
  }'
```

**Response:**
```json
{
  "incident_summary": {
    "description": "Production LLM API showing unusual outputs...",
    "total_action_items": 23,
    "estimated_total_time": "1-3 days",
    "primary_threat": {
      "threat_id": "OWASP-LLM01",
      "framework": "OWASP LLM Top 10",
      "description": "Prompt Injection",
      "confidence": 0.9
    }
  },
  "timeline": {
    "immediate": {
      "phase": "Immediate Actions",
      "timeframe": "0-15 minutes",
      "objective": "Initial response, evidence preservation, and containment",
      "actions": [
        {
          "action": "Activate Incident Response Team",
          "priority": "CRITICAL",
          "description": "Notify designated IR team members",
          "estimated_time": "2-5 minutes"
        },
        {
          "action": "Isolate Affected LLM Endpoints",
          "priority": "CRITICAL",
          "description": "Temporarily disable or rate-limit affected LLM API endpoints",
          "estimated_time": "5 minutes"
        }
      ]
    },
    "investigation": {
      "phase": "Investigation",
      "timeframe": "15 minutes - 2 hours",
      "actions": [...]
    },
    "containment": {
      "phase": "Containment",
      "timeframe": "2-8 hours",
      "actions": [...]
    },
    "recovery": {
      "phase": "Recovery & Remediation",
      "timeframe": "8+ hours",
      "actions": [...]
    }
  },
  "defense_techniques": {
    "techniques": [
      {
        "source_id": "AID-H-001",
        "name": "Baseline Input Validation",
        "tactic": "Harden",
        "description": "Implement robust input validation..."
      },
      {
        "source_id": "AID-H-002",
        "name": "Prompt Guard",
        "tactic": "Harden",
        "description": "Deploy prompt injection detection..."
      }
    ]
  },
  "generated_at": "2025-01-18T10:30:00Z"
}
```

---

## Additional Resources

- **API Documentation**: http://localhost:8000/docs (when service is running)
- **Main README**: [README.md](../README.md)
- **Installation Guide**: [INSTALL.md](../INSTALL.md)
- **Configuration Guide**: [CONFIGURATION.md](CONFIGURATION.md)
- **Security Policy**: [SECURITY.md](../SECURITY.md)
