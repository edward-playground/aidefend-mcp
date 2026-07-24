"""
MCP (Model Context Protocol) Server for AIDEFEND.

This module provides an MCP interface to the AIDEFEND knowledge base,
allowing AI assistants like Claude Desktop to query defense strategies
through the MCP protocol.

The MCP server shares the same core logic (QueryEngine) as the REST API,
ensuring consistent results across both interfaces.
"""

import asyncio
import sys
from contextlib import suppress
from typing import Any, Dict, List
from bs4 import BeautifulSoup

# MCP SDK imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# AIDEFEND imports
from app.core import query_engine, QueryEngineNotInitializedError
from app.schemas import QueryRequest, ContextChunk
from app.config import settings
from app.sync import run_sync, sync_loop, get_last_sync_error
from app.logger import get_logger
from app.security import (
    InputValidationError,
    SecurityError,
    validate_bounded_integer,
)
from app.audit import audit_tool_call, audit_tool_completion
from app.framework_utils import FRAMEWORK_LABELS, framework_coverage_label
from app.utils import load_version_info, escape_markdown
from datetime import datetime

# Import all tools from unified package
from app.tools import (
    get_statistics,
    validate_technique_id,
    get_technique_detail,
    get_defenses_for_threat,
    get_secure_code_snippet,
    analyze_coverage,
    map_to_compliance_framework,
    get_quick_reference,
    get_threat_coverage,
    get_implementation_plan,
    classify_threat,
    comprehensive_search,
    analyze_security_posture,
    compare_techniques,
    generate_incident_playbook,
)

logger = get_logger(__name__)


def _ordered_framework_coverage_keys(*mappings: Dict[str, Any]) -> List[str]:
    """Keep legacy framework order, then append additive source labels."""
    observed = {
        key
        for mapping in mappings
        if isinstance(mapping, dict)
        for key in mapping
        if key != "owasp"
    }
    known = list(FRAMEWORK_LABELS)
    dynamic = sorted(observed - set(known))
    return [*known, *dynamic]


async def _dispatch_tool_call(
    name: str, arguments: Dict[str, Any]
) -> List[TextContent]:
    """Dispatch one MCP tool call without converting failures into successes."""
    if name == "query_aidefend":
        return await handle_query(arguments)
    if name == "get_aidefend_status":
        return await handle_status()
    if name == "sync_aidefend":
        return await handle_sync()
    if name == "get_statistics":
        return await handle_get_statistics(arguments)
    if name == "validate_technique_id":
        return await handle_validate_technique_id(arguments)
    if name == "get_technique_detail":
        return await handle_get_technique_detail(arguments)
    if name == "get_defenses_for_threat":
        return await handle_get_defenses_for_threat(arguments)
    if name == "get_secure_code_snippet":
        return await handle_get_secure_code_snippet(arguments)
    if name == "analyze_coverage":
        return await handle_analyze_coverage(arguments)
    if name == "map_to_compliance_framework":
        return await handle_map_to_compliance_framework(arguments)
    if name == "get_quick_reference":
        return await handle_get_quick_reference(arguments)
    if name == "get_threat_coverage":
        return await handle_get_threat_coverage(arguments)
    if name == "get_implementation_plan":
        return await handle_get_implementation_plan(arguments)
    if name == "classify_threat":
        return await handle_classify_threat(arguments)
    if name == "comprehensive_search":
        return await handle_comprehensive_search(arguments)
    if name == "analyze_security_posture":
        return await handle_analyze_security_posture(arguments)
    if name == "compare_techniques":
        return await handle_compare_techniques(arguments)
    if name == "generate_incident_playbook":
        return await handle_generate_incident_playbook(arguments)
    raise ValueError(f"Unknown tool: {name}")


def _register_call_tool_handler(server: Server):
    """Register the production dispatcher and preserve MCP error semantics."""

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        try:
            return await _dispatch_tool_call(name, arguments)
        except Exception as exc:
            # The MCP SDK converts a raised exception to CallToolResult(isError=True).
            # Returning an "Error: ..." TextContent here would incorrectly report
            # a successful tool call to clients.
            logger.error(
                f"Error handling tool call '{name}': {exc}", exc_info=True
            )
            raise

    return call_tool


def _format_scope_boundary(
    scope_boundary: Any, *, heading_level: int = 2
) -> str:
    """Render schema-2.3 scope metadata as readable, injection-safe Markdown."""
    if not isinstance(scope_boundary, dict) or not scope_boundary:
        return ""

    responsibility = scope_boundary.get("responsibility")
    if not isinstance(responsibility, str) or not responsibility.strip():
        responsibility = ""

    relationships = []
    raw_relationships = scope_boundary.get("relatedTechniques", [])
    if isinstance(raw_relationships, list):
        for relationship in raw_relationships:
            if not isinstance(relationship, dict):
                continue
            related_id = relationship.get("id")
            comparison = relationship.get("comparison")
            if not isinstance(related_id, str) or not related_id.strip():
                continue
            if not isinstance(comparison, str) or not comparison.strip():
                continue
            relationships.append(
                (
                    escape_markdown(related_id.strip()),
                    escape_markdown(" ".join(comparison.split())),
                )
            )

    if not responsibility and not relationships:
        return ""

    level = max(1, min(6, heading_level))
    output = f"{'#' * level} Scope Boundary\n\n"
    if responsibility:
        output += (
            f"**Responsibility:** {escape_markdown(responsibility.strip())}\n\n"
        )
    if relationships:
        output += "**Related Techniques:**\n"
        for related_id, comparison in relationships:
            output += f"- **{related_id}:** {comparison}\n"
        output += "\n"
    return output


def _format_resolution_diagnostics(
    unrecognized_ids: Any,
    expanded_parent_families: Any,
    *,
    heading_level: int = 2,
) -> str:
    """Render ID migration diagnostics supplied by framework-aware tools."""
    invalid = (
        [item for item in unrecognized_ids if isinstance(item, str) and item]
        if isinstance(unrecognized_ids, list)
        else []
    )
    expanded = (
        expanded_parent_families
        if isinstance(expanded_parent_families, dict)
        else {}
    )
    valid_expansions = []
    for parent_id, child_ids in expanded.items():
        if not isinstance(parent_id, str) or not isinstance(child_ids, list):
            continue
        children = [child for child in child_ids if isinstance(child, str) and child]
        if children:
            valid_expansions.append((parent_id, children))

    if not invalid and not valid_expansions:
        return ""

    level = max(1, min(6, heading_level))
    output = f"{'#' * level} Technique ID Resolution\n\n"
    if invalid:
        output += "**Unrecognized Technique IDs:**\n"
        for technique_id in invalid:
            output += f"- {escape_markdown(technique_id)}\n"
        output += "\n"
    if valid_expansions:
        output += "**Expanded Parent Families:**\n"
        for parent_id, child_ids in valid_expansions:
            rendered_children = ", ".join(escape_markdown(item) for item in child_ids)
            output += f"- **{escape_markdown(parent_id)}** -> {rendered_children}\n"
        output += "\n"
    return output


def _format_tool_inventory(tools: Any, *, heading_level: int = 2) -> str:
    """Render every schema-2.3 tool category without silently dropping one."""
    if not isinstance(tools, dict):
        return ""
    categories = (
        ("opensource", "Open Source"),
        ("source_available", "Source Available / Open Weight"),
        ("commercial", "Commercial"),
    )
    populated = []
    for key, label in categories:
        values = tools.get(key)
        if isinstance(values, list) and values:
            populated.append((label, values))
    if not populated:
        return ""

    level = max(1, min(6, heading_level))
    output = f"{'#' * level} Tools\n\n"
    for label, values in populated:
        output += f"**{label}:**\n"
        for value in values:
            output += f"- {escape_markdown(str(value))}\n"
        output += "\n"
    return output


def _format_record_tool_inventory(
    record: Any, *, heading_level: int = 2
) -> str:
    """Render tool arrays stored as flat public-record fields."""
    if not isinstance(record, dict):
        return ""
    return _format_tool_inventory(
        {
            "opensource": record.get("tools_opensource", []),
            "source_available": record.get("tools_source_available", []),
            "commercial": record.get("tools_commercial", []),
        },
        heading_level=heading_level,
    )


def _plain_strategy_text(value: Any) -> str:
    """Convert trusted framework guidance HTML to compact Markdown-safe text."""
    if not isinstance(value, str) or not value.strip():
        return ""
    soup = BeautifulSoup(value, "html.parser")
    for code_node in soup.find_all(["pre", "code"]):
        code_node.decompose()
    return escape_markdown(" ".join(soup.get_text(" ", strip=True).split()))


def _format_implementation_strategies(
    strategies: Any, *, heading_level: int = 2
) -> str:
    """Render guidance IDs, implementation text, how-to text, and code."""
    if not isinstance(strategies, list):
        return ""
    strategies = [item for item in strategies if isinstance(item, dict)]
    if not strategies:
        return ""

    level = max(1, min(5, heading_level))
    output = f"{'#' * level} Implementation Guidance\n\n"
    for index, strategy in enumerate(strategies, 1):
        guidance_id = str(strategy.get("guidance_id") or f"Guidance {index}")
        implementation = str(strategy.get("implementation") or "").strip()
        output += f"{'#' * (level + 1)} {escape_markdown(guidance_id)}\n\n"
        if implementation:
            output += f"**Implementation:** {escape_markdown(implementation)}\n\n"
        how_to = _plain_strategy_text(strategy.get("how_to"))
        if how_to:
            output += f"**How to:** {how_to}\n\n"
        code_examples = strategy.get("code_examples")
        if isinstance(code_examples, list):
            for code_index, example in enumerate(code_examples, 1):
                if not isinstance(example, dict):
                    continue
                code = example.get("code")
                if not isinstance(code, str) or not code.strip():
                    continue
                language = str(example.get("language") or "text")
                output += (
                    f"**Code Example {code_index} "
                    f"({escape_markdown(language)}):**\n\n"
                )
                output += "\n".join(
                    f"    {line}" for line in code.strip().splitlines()
                )
                output += "\n\n"
    return output


async def serve():
    """
    Start the MCP server using stdio transport.

    This function initializes the MCP server and registers all available tools.
    It runs indefinitely, processing tool calls from MCP clients (like Claude Desktop).
    """
    # Create MCP server instance
    server = Server("aidefend-mcp")
    sync_task = None

    logger.info("Initializing AIDEFEND MCP Server...")

    # Clean up stale lock files from crashed processes
    # This should be done before any sync operations
    try:
        from app.sync import cleanup_stale_lock
        cleanup_stale_lock()
    except Exception as e:
        logger.warning(f"Failed to cleanup stale lock on startup: {e}")

    # Ensure database is ready (auto-initialize or repair if needed)
    # This handles both new installations and corrupted databases
    try:
        from app.sync import ensure_database_ready
        logger.info("Checking database health...")
        await ensure_database_ready()
        logger.info("Database is ready")
    except Exception as e:
        # Do NOT crash the MCP server on a first-run/repair failure (transient network,
        # proxy blocking GitHub/HuggingFace, etc.). Start in a degraded state: tools return a
        # clear "not ready — run sync_aidefend" message and the user can call the
        # sync_aidefend tool to build the knowledge base without restarting the client.
        logger.error(
            f"Database not ready at startup ({e}). Starting MCP server in DEGRADED mode; "
            f"call the sync_aidefend tool to build the knowledge base."
        )

    # Tool 1: Query AIDEFEND knowledge base
    @server.list_tools()
    async def list_tools() -> List[Tool]:
        """
        List all available MCP tools.

        Returns:
            List of Tool objects that MCP clients can call
        """
        return [
            Tool(
                name="query_aidefend",
                description=(
                    "Search the AIDEFEND AI security defense knowledge base. "
                    "Use this to find defense strategies, techniques, and best practices "
                    "for AI/ML security threats like prompt injection, model poisoning, "
                    "data extraction, etc. Returns relevant defense tactics and implementation guidance."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Your search query in natural language. "
                                "Examples: 'how to prevent prompt injection', "
                                "'defend against model poisoning', "
                                "'secure AI supply chain'"
                            )
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results to return (default: 5, max: 20)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 20
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="get_aidefend_status",
                description=(
                    "Get the current status of the AIDEFEND knowledge base, "
                    "including total indexed documents, embedding model info, "
                    "and sync status. Use this to check if the service is ready."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="sync_aidefend",
                description=(
                    "Manually synchronize with the configured AIDEFEND source "
                    "(the public GitHub repository by default) "
                    "to fetch the latest defense tactics and techniques. "
                    "Note: This may take a few minutes. Auto-sync runs every hour by default."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            # P0 Tool 1: Statistics
            Tool(
                name="get_statistics",
                description=(
                    "Get comprehensive statistics about the AIDEFEND knowledge base including "
                    "total documents, breakdown by tactic/pillar/phase, threat framework coverage, "
                    "and tools availability. Essential for understanding the scope of the knowledge base."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            # P0 Tool 2: Validate Technique ID
            Tool(
                name="validate_technique_id",
                description=(
                    "Validate if a technique ID exists and is correctly formatted. "
                    "Provides fuzzy matching suggestions if ID is not found. "
                    "Use this before querying specific techniques to avoid errors."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "technique_id": {
                            "type": "string",
                            "description": "Technique ID to validate (e.g., 'AID-H-001', 'AID-D-001.001')"
                        }
                    },
                    "required": ["technique_id"]
                }
            ),
            # P0 Tool 3: Get Technique Detail
            Tool(
                name="get_technique_detail",
                description=(
                    "Get complete details for a specific AIDEFEND technique including "
                    "all sub-techniques, implementation guidance with code examples, "
                    "tool recommendations, and threat mappings. This is the primary tool "
                    "for deep-diving into a specific defense technique."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "technique_id": {
                            "type": "string",
                            "description": "Technique or sub-technique ID (e.g., 'AID-H-001', 'AID-H-002.002')"
                        },
                        "include_code": {
                            "type": "boolean",
                            "description": "Include full code examples (default: true)",
                            "default": True
                        },
                        "include_tools": {
                            "type": "boolean",
                            "description": "Include tool recommendations (default: true)",
                            "default": True
                        }
                    },
                    "required": ["technique_id"]
                }
            ),
            # P0 Tool 4: Get Defenses for Threat
            Tool(
                name="get_defenses_for_threat",
                description=(
                    "Find AIDEFEND defense techniques for a specific threat. "
                    "Supports threat IDs from the mapped framework set "
                    "(e.g., 'LLM01', 'ML01:2023', 'ASI01:2026', 'T0043', 'NISTAML.031'), "
                    "or natural language threat keywords "
                    "(e.g., 'prompt injection'). Essential for threat-driven defense planning."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "threat_id": {
                            "type": "string",
                            "description": "Threat ID from a mapped framework (e.g., 'LLM01', 'ML01:2023', 'T0043', 'NISTAML.031')"
                        },
                        "threat_keyword": {
                            "type": "string",
                            "description": "Natural language threat keyword (e.g., 'prompt injection', 'model poisoning')"
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of defense techniques to return (1-50, default: 10)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50
                        }
                    },
                    "required": [],
                    "anyOf": [
                        {"required": ["threat_id"]},
                        {"required": ["threat_keyword"]},
                    ],
                }
            ),
            # P0 Tool 5: Get Secure Code Snippet
            Tool(
                name="get_secure_code_snippet",
                description=(
                    "Extract executable secure code snippets from AIDEFEND implementation guidance. "
                    "Search by technique ID or topic keyword to get copy-paste ready code examples. "
                    "Perfect for developers implementing specific security controls."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "technique_id": {
                            "type": "string",
                            "description": "Specific technique/subtechnique ID"
                        },
                        "topic": {
                            "type": "string",
                            "description": "Topic keyword (e.g., 'input validation', 'RAG security')"
                        },
                        "language": {
                            "type": "string",
                            "description": "Programming language filter (e.g., 'python', 'javascript')"
                        },
                        "max_snippets": {
                            "type": "integer",
                            "description": "Maximum number of snippets (1-20, default: 5)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 20
                        }
                    },
                    "required": [],
                    "anyOf": [
                        {"required": ["technique_id"]},
                        {"required": ["topic"]},
                    ],
                }
            ),
            # P0 Tool 6: Analyze Coverage
            Tool(
                name="analyze_coverage",
                description=(
                    "Analyze defense coverage based on implemented techniques and identify gaps. "
                    "Provides coverage percentage by tactic/pillar/phase, threat framework coverage, "
                    "and prioritized recommendations. Essential for security program management."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "implemented_techniques": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of technique IDs already implemented"
                        },
                        "system_type": {
                            "type": "string",
                            "description": "Optional system type for context-aware analysis",
                            "enum": ["chatbot", "rag", "agent", "classifier", "generative", "multimodal"]
                        }
                    },
                    "required": ["implemented_techniques"]
                }
            ),
            # P0 Tool 7: Map to Compliance Framework
            Tool(
                name="map_to_compliance_framework",
                description=(
                    "Map AIDEFEND techniques to compliance framework requirements "
                    "(NIST AI RMF, EU AI Act, ISO 42001, CSA AI Controls, OWASP ASVS). "
                    "Uses heuristic-based analysis for mapping (100% local, no external API calls). Critical for governance and audit."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "technique_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of technique IDs to map"
                        },
                        "framework": {
                            "type": "string",
                            "description": "Compliance framework (default: nist_ai_rmf)",
                            "enum": ["nist_ai_rmf", "eu_ai_act", "iso_42001", "csa_ai_controls", "owasp_asvs"],
                            "default": "nist_ai_rmf"
                        }
                    },
                    "required": ["technique_ids"]
                }
            ),
            # P0 Tool 8: Get Quick Reference
            Tool(
                name="get_quick_reference",
                description=(
                    "Generate a quick reference guide for a specific security topic. "
                    "Provides actionable checklist organized by priority (quick wins, must-haves, nice-to-haves). "
                    "Perfect for fast decision-making and presentations."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Security topic (e.g., 'prompt injection', 'RAG security')"
                        },
                        "format": {
                            "type": "string",
                            "description": "Output format (default: checklist)",
                            "enum": ["checklist", "table", "markdown"],
                            "default": "checklist"
                        },
                        "max_items": {
                            "type": "integer",
                            "description": "Maximum items (5-20, default: 10)",
                            "default": 10,
                            "minimum": 5,
                            "maximum": 20
                        }
                    },
                    "required": ["topic"]
                }
            ),
            # New Tool 1: Threat Coverage Analysis
            Tool(
                name="get_threat_coverage",
                description=(
                    "Analyze threat coverage for implemented defense techniques. "
                    "Given a list of AIDEFEND technique IDs, calculates which threats "
                    "are covered across all mapped external frameworks and provides "
                    "coverage rates. Essential for tracking security posture and identifying gaps."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "implemented_techniques": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of implemented technique IDs (e.g., ['AID-D-001', 'AID-H-002'])",
                            "minItems": 0,
                            "maxItems": 200
                        }
                    },
                    "required": ["implemented_techniques"]
                }
            ),
            # New Tool 2: Implementation Plan Recommendations
            Tool(
                name="get_implementation_plan",
                description=(
                    "Get ranked recommendations for next defense techniques to implement "
                    "based on heuristic scoring (threat importance, ease of implementation, "
                    "phase weight, pillar weight). Use this to prioritize security investments. "
                    "Note: This tool provides ONLY heuristic scores. You should use these scores "
                    "to make final recommendations via your own reasoning. "
                    "IMPORTANT: Use detail_level='detailed' to get actionable strategies and code snippets "
                    "for top 5 recommendations, eliminating the need for subsequent get_technique_detail calls."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "implemented_techniques": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of already implemented technique IDs (optional)",
                            "default": []
                        },
                        "exclude_tactics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tactics to exclude (e.g., ['Model', 'Harden'])",
                            "default": []
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of recommendations to return (1-20, default: 10)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 20
                        },
                        "detail_level": {
                            "type": "string",
                            "description": "Level of detail: 'basic' (IDs only), 'standard' (brief summaries for top 5), 'detailed' (full summaries + code for top 5)",
                            "enum": ["basic", "standard", "detailed"],
                            "default": "basic"
                        }
                    },
                    "required": []
                }
            ),
            # New Tool 3: Classify Threat from Text (local static + fuzzy matching)
            Tool(
                name="classify_threat",
                description=(
                    "Classify threats in text using a 2-tier local matching system: "
                    "1) Static keyword matching (free), "
                    "2) Fuzzy matching for typo tolerance (free). "
                    "Maps common threat terms (prompt injection, model poisoning, etc.) to "
                    "standard framework IDs used by the service. "
                    "No external API or paid LLM inference is used."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Input text containing threat-related content (e.g., incident report, alert)",
                            "minLength": 1,
                            "maxLength": 10000
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Maximum keywords to return (1-10, default: 5)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 10
                        }
                    },
                    "required": ["text"]
                }
            ),
            # New Tool 4: Comprehensive Search (Multi-Query Aggregation)
            Tool(
                name="comprehensive_search",
                description=(
                    "🔍 Auto-expanding semantic search for exploratory questions. "
                    "Perfect when you don't know the exact keywords to search.\n\n"
                    "✅ USE THIS when:\n"
                    "- Broad exploratory questions ('What defenses exist for deepfakes?')\n"
                    "- User unsure of technical terminology or related concepts\n"
                    "- Want comprehensive coverage across multiple related topics\n"
                    "- Exploring a new threat landscape\n\n"
                    "❌ DON'T USE when:\n"
                    "- Known specific threat ID (LLM01, T0043) → use get_defenses_for_threat\n"
                    "- Precise keyword search → use query_aidefend (faster)\n"
                    "- Need code/implementation details → use get_technique_detail afterward\n"
                    "- User already knows exact technique ID → use get_technique_detail\n\n"
                    "This tool automatically generates 4-5 related queries (e.g., 'deepfakes' → "
                    "'synthetic media', 'deepfake detection', 'media manipulation'), executes them "
                    "in parallel, deduplicates results by source_id, and provides coverage summary "
                    "showing tactics/pillars distribution."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": (
                                "Broad topic to search comprehensively. "
                                "Examples: 'deepfakes', 'prompt injection', 'model poisoning', "
                                "'RAG vulnerabilities', 'supply chain security', 'adversarial attacks'"
                            ),
                            "minLength": 3,
                            "maxLength": 200
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum total results to return (5-50, default: 20)",
                            "default": 20,
                            "minimum": 5,
                            "maximum": 50
                        },
                        "include_subtechniques": {
                            "type": "boolean",
                            "description": "Include sub-techniques in results (default: true)",
                            "default": True
                        }
                    },
                    "required": ["topic"]
                }
            ),
            # New Tool 5: Unified Security Posture Analysis
            Tool(
                name="analyze_security_posture",
                description=(
                    "🛡️ Comprehensive security posture analysis combining technical and threat perspectives. "
                    "This unified tool merges analyze_coverage + get_threat_coverage functionality.\n\n"
                    "✅ USE THIS to get holistic view of:\n"
                    "- Technical coverage: Tactics/pillars/phases distribution and gaps\n"
                    "- Threat coverage: Coverage rates across all mapped threat frameworks\n"
                    "- Combined insights: Overall security posture assessment\n"
                    "- Prioritized recommendations: What to implement next\n\n"
                    "Supports 3 views:\n"
                    "- 'both' (default): Full analysis (technical + threat)\n"
                    "- 'technical': Only tactic/pillar/phase coverage\n"
                    "- 'threat': Only threat framework coverage\n\n"
                    "💡 TIP: Use empty array [] for baseline security planning (shows all gaps and 0% coverage)\n\n"
                    "Perfect for security program management, audits, and strategic planning."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "implemented_techniques": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of technique IDs already implemented (e.g., ['AID-H-001', 'AID-D-001']). Use empty array [] for baseline analysis.",
                            "maxItems": 200,
                            "default": []
                        },
                        "view": {
                            "type": "string",
                            "description": "Analysis view: 'both' (default), 'technical', or 'threat'",
                            "enum": ["both", "technical", "threat"],
                            "default": "both"
                        },
                        "system_type": {
                            "type": "string",
                            "description": "Optional system type for context-aware analysis",
                            "enum": ["chatbot", "rag", "agent", "classifier", "generative", "multimodal"]
                        }
                    },
                    "required": []
                }
            ),
            # New Tool 6: Technique Comparison Matrix
            Tool(
                name="compare_techniques",
                description=(
                    "🔬 Side-by-side comparison of multiple AIDEFEND techniques with heuristic scoring.\n\n"
                    "Provides comparison matrix showing:\n"
                    "- **Effectiveness Score (0-100):** Based on threat coverage, implementation support\n"
                    "- **Complexity Score (0-100):** Based on implementation depth and requirements\n"
                    "- **Cost Score (0-100):** Based on tooling and resource needs\n\n"
                    "✅ USE THIS when:\n"
                    "- Evaluating multiple techniques for selection\n"
                    "- Prioritizing implementation based on ROI\n"
                    "- Understanding trade-offs between different approaches\n"
                    "- Building business case for security investments\n\n"
                    "Includes smart recommendations:\n"
                    "- **Quick Wins:** High effectiveness, low complexity/cost\n"
                    "- **Strategic Investments:** High effectiveness but resource-intensive\n"
                    "- **Implementation Priority:** Ordered by effectiveness-to-complexity ratio\n\n"
                    "All scoring is 100% local using metadata analysis - no ML inference or external APIs."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "technique_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of technique IDs to compare (e.g., ['AID-H-001', 'AID-D-002'])",
                            "minItems": 2,
                            "maxItems": 10
                        },
                        "include_recommendations": {
                            "type": "boolean",
                            "description": "Include prioritization recommendations (default: true)",
                            "default": True
                        }
                    },
                    "required": ["technique_ids"]
                }
            ),
            # New Tool 7: Incident Response Playbook Generator
            Tool(
                name="generate_incident_playbook",
                description=(
                    "🚨 Generate structured incident response playbook based on threat classification.\n\n"
                    "Provides timeline-based action plan following NIST incident response phases:\n"
                    "1. **Immediate Actions (0-15 min):** Assessment, team activation, evidence preservation\n"
                    "2. **Investigation (15 min - 2 hours):** Threat classification, scope analysis, IOC collection\n"
                    "3. **Containment (2-8 hours):** Isolation, defense deployment, attack vector blocking\n"
                    "4. **Recovery (8+ hours):** Security controls, service restoration, post-incident review\n\n"
                    "✅ USE THIS when:\n"
                    "- Responding to active AI/ML security incident\n"
                    "- Planning incident response procedures\n"
                    "- Training IR teams on AI-specific threats\n"
                    "- Documenting security incident workflows\n\n"
                    "Integrates with existing tools:\n"
                    "- Automatically classifies threats (via classify_threat)\n"
                    "- Recommends specific defense techniques (via get_defenses_for_threat)\n"
                    "- Provides context-aware, actionable checklists\n\n"
                    "100% local implementation - all analysis happens on your machine."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "incident_description": {
                            "type": "string",
                            "description": (
                                "Free-text description of the incident. "
                                "Examples: 'Suspicious prompt injection attempts detected', "
                                "'Model outputs revealing training data', "
                                "'Unusual API query patterns suggesting model extraction'"
                            ),
                            "minLength": 10,
                            "maxLength": 1000
                        },
                        "include_defense_techniques": {
                            "type": "boolean",
                            "description": "Include specific AIDEFEND defense techniques in playbook (default: true)",
                            "default": True
                        }
                    },
                    "required": ["incident_description"]
                }
            )
        ]

    _register_call_tool_handler(server)

    # Initialize services before accepting connections (prevents cold start timeout)
    try:
        logger.info("Initializing query engine for MCP...")
        await query_engine.initialize()

        # Check if this is a cold start (no database exists)
        if not query_engine.is_ready:
            logger.warning("=" * 60)
            logger.warning("⚠️  COLD START DETECTED - No database found")
            logger.warning("⚠️  Performing blocking sync (may take 30-60 seconds)")
            logger.warning("⚠️  Server will be ready after initial sync completes")
            logger.warning("=" * 60)

            # Blocking sync for cold start to prevent race condition
            logger.info("Running initial sync (blocking)...")
            sync_success = await run_sync()

            if sync_success:
                logger.info("✅ Initial sync completed successfully")
                logger.info("✅ MCP server ready for queries")
            else:
                logger.error("❌ Initial sync failed - queries will fail")
                logger.error("   User must manually run sync_aidefend tool")
        else:
            # Warm start - database exists, serve immediately.
            # Periodic/manual sync can refresh content without blocking initial tool calls.
            logger.info("Warm start detected (database exists)")
            logger.info("Serving existing database immediately; periodic/manual sync will handle update checks")

        if settings.ENABLE_AUTO_SYNC:
            logger.info(
                f"Starting MCP background sync loop (interval: {settings.SYNC_INTERVAL_SECONDS}s)"
            )
            sync_task = asyncio.create_task(sync_loop(), name="aidefend-mcp-sync")
        else:
            logger.info("MCP auto-sync disabled")

        logger.info("MCP services initialized. Ready for connections.")

    except Exception as e:
        logger.error(f"MCP startup initialization failed: {e}", exc_info=True)
        # Continue anyway - tools will handle QueryEngineNotInitializedError

    # Run the MCP server
    logger.info("Starting MCP server on stdio...")
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    finally:
        # Graceful shutdown: release resources
        logger.info("MCP server shutting down, cleaning up resources...")
        if sync_task is not None:
            sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await sync_task
        try:
            # Reset query engine state to release DB handles
            query_engine._initialized = False
            query_engine._db = None
            query_engine._table = None
            query_engine._id_cache = None
            logger.info("Query engine resources released")
        except Exception as cleanup_err:
            logger.warning(f"Error during shutdown cleanup: {cleanup_err}")


async def handle_query(arguments: Dict[str, Any]) -> List[TextContent]:
    """
    Handle query_aidefend tool call.

    Args:
        arguments: Dict containing 'query' and optional 'top_k'

    Returns:
        List of TextContent with formatted search results
    """
    query_text = arguments.get("query", "").strip()
    top_k = arguments.get("top_k", 5)

    if not query_text:
        raise InputValidationError("Query text cannot be empty")

    top_k = validate_bounded_integer(top_k, "top_k", 1, 20)

    try:
        # Validate input and create request
        # (This may raise InputValidationError or SecurityError)
        request = QueryRequest(query_text=query_text, top_k=top_k)

        logger.info(f"MCP query: '{query_text[:50]}...' (top_k={top_k})")

        if len(request.query_text) > settings.MAX_QUERY_LENGTH:
            from app.tools.chunked_search import search_with_chunking

            chunked_result = await search_with_chunking(
                query_text=request.query_text,
                top_k=request.top_k
            )
            results = []
            for item in chunked_result.get("results", []):
                item_metadata = item.get("metadata", {})
                if not isinstance(item_metadata, dict):
                    item_metadata = {}
                results.append(
                    ContextChunk(
                        source_id=item.get("source_id", "N/A"),
                        tactic=item.get("tactic", "N/A"),
                        text=item.get("text", ""),
                        metadata={
                            "type": item.get(
                                "type", item_metadata.get("type", "N/A")
                            ),
                            "name": item.get(
                                "name", item_metadata.get("name", "N/A")
                            ),
                            "pillar": item.get(
                                "pillar", item_metadata.get("pillar", "")
                            ),
                            "phase": item.get(
                                "phase", item_metadata.get("phase", "")
                            ),
                            "tools_opensource": item.get(
                                "tools_opensource",
                                item_metadata.get("tools_opensource", []),
                            ),
                            "tools_source_available": item.get(
                                "tools_source_available",
                                item_metadata.get("tools_source_available", []),
                            ),
                            "tools_commercial": item.get(
                                "tools_commercial",
                                item_metadata.get("tools_commercial", []),
                            ),
                            "scope_boundary": item.get(
                                "scope_boundary",
                                item_metadata.get("scope_boundary", {}),
                            ),
                        },
                        score=item.get("score", item.get("_distance", 0.0)),
                    )
                )
        else:
            # Use the same QueryEngine as REST API
            results = await query_engine.search(request)

        if not results:
            return [TextContent(
                type="text",
                text=(
                    f"No results found for query: '{escape_markdown(query_text)}'\n\n"
                    "Try:\n"
                    "- Using different keywords\n"
                    "- Making the query more specific\n"
                    "- Checking if the knowledge base is synced (use get_aidefend_status)"
                )
            )]

        # Format results for MCP client
        formatted_text = format_search_results(query_text, results, top_k)

        return [TextContent(type="text", text=formatted_text)]

    # Handle input validation errors
    except (InputValidationError, SecurityError) as e:
        logger.warning(f"MCP query validation failed: {e}")
        raise

    # Handle service not ready errors
    except QueryEngineNotInitializedError as e:
        logger.error(f"MCP query failed, engine not ready: {e}")
        raise

    # Handle all other errors
    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        raise


async def handle_status() -> List[TextContent]:
    """
    Handle get_aidefend_status tool call.

    Returns:
        List of TextContent with service status information including detailed version info
    """
    logger.info("MCP status request")

    try:
        stats = await query_engine.get_stats()

        # Build status text
        status_text = (
            "# AIDEFEND Knowledge Base Status\n\n"
            f"**Initialization Status:** {'✅ Ready' if stats['initialized'] else '❌ Not Ready'}\n"
        )

        # Add detailed framework version information (merged from get_framework_version)
        version_info = load_version_info()
        if version_info:
            framework_version = version_info.get("framework_version")
            source_revision = (
                version_info.get("source_revision")
                or version_info.get("commit_sha", "N/A")
            )
            source_kind = version_info.get("source_kind", "github")
            revision_label = (
                "Git Commit" if source_kind == "github" else "Local Content SHA-1"
            )
            last_synced = version_info.get("last_synced_at", "N/A")

            if framework_version:
                # Parse version to extract date (format: 1.YYYYMMDD)
                try:
                    date_str = framework_version.split('.')[1]  # Extract "20251107"
                    year = date_str[0:4]
                    month = date_str[4:6]
                    day = date_str[6:8]
                    readable_date = f"{year}-{month}-{day}"
                except (IndexError, ValueError):
                    readable_date = "Unknown"

                status_text += (
                    f"**Framework Version:** {framework_version} (Released: {readable_date})\n"
                    f"**{revision_label}:** "
                    f"{source_revision[:8] if len(source_revision) >= 8 else source_revision}\n"
                    f"**Last Synced:** {last_synced}\n"
                )
            else:
                status_text += (
                    f"**Framework Version:** ⚠️ Not available\n"
                    f"**{revision_label}:** "
                    f"{source_revision[:8] if len(source_revision) >= 8 else source_revision}\n"
                    f"**Last Synced:** {last_synced}\n"
                )
            status_text += (
                f"**Authoring Schema:** "
                f"{version_info.get('framework_authoring_schema_version', 'N/A')}\n"
                f"**Public Data Schema:** "
                f"{version_info.get('framework_public_schema_version', 'N/A')}\n"
                f"**MCP Index Schema:** {version_info.get('index_schema_version', 'N/A')}\n"
                f"**Source:** {source_kind} "
                f"({version_info.get('source_repository', 'N/A')}@"
                f"{version_info.get('source_ref', 'N/A')})\n"
                f"**Source Content SHA-256:** "
                f"{version_info.get('source_content_sha256', 'N/A')}\n"
                f"**Schema Metadata SHA-256:** "
                f"{version_info.get('framework_schema_metadata_sha256', 'N/A')}\n"
            )
        elif stats.get('framework_version'):
            # Fallback to stats if version_info not available
            status_text += f"**Framework Version:** {stats['framework_version']}\n"

        status_text += (
            "**Framework Content:** AIDEFEND AI Defense Framework, created by Edward Lee, "
            "https://aidefend.net, licensed under CC BY 4.0.\n"
        )

        status_text += (
            f"**Indexed Documents:** {stats['document_count']:,}\n"
            f"**Embedding Model:** {stats.get('embedding_model', 'N/A')}\n"
            f"**Model Loaded:** {'✅ Yes' if stats['model_loaded'] else '❌ No'}\n"
        )

        # Add error info if present
        if 'error' in stats:
            status_text += f"\n**Error:** {stats['error']}\n"

        # Add sync error if present
        sync_error = get_last_sync_error()
        if sync_error:
            status_text += f"\n**Last Sync Error:** {sync_error}\n"

        # Add usage hint
        if stats['initialized'] and stats['document_count'] > 0:
            status_text += (
                "\n---\n\n"
                "**Status:** Service is ready for queries!\n"
                "Use `query_aidefend` to search for AI defense strategies.\n\n"
                "💡 **Tip:** To update to the latest framework version, use `sync_aidefend`."
            )
        else:
            status_text += (
                "\n---\n\n"
                "**Status:** Service needs initial synchronization.\n"
                "Use `sync_aidefend` to download the knowledge base."
            )

        return [TextContent(type="text", text=status_text)]

    except Exception as e:
        logger.error(f"Status check failed: {e}", exc_info=True)
        raise


async def handle_sync() -> List[TextContent]:
    """
    Handle sync_aidefend tool call.

    Uses run_sync() which internally calls core_sync(force_rebuild=False).
    This performs a normal sync check (downloads updates if available).

    For force rebuild, users should use CLI: python __main__.py --resync
    For corruption repair, ensure_database_ready() runs at startup.

    Returns:
        List of TextContent with sync result
    """
    logger.info("MCP sync request")

    source_description = (
        f"local framework working tree ({settings.LOCAL_FRAMEWORK_PATH})"
        if settings.LOCAL_FRAMEWORK_PATH
        else f"GitHub repository {settings.github_repo_path}@{settings.GITHUB_BRANCH}"
    )
    sync_text = (
        "# Starting AIDEFEND Knowledge Base Sync\n\n"
        f"Synchronizing with {source_description}...\n"
        "This may take a few minutes.\n\n"
    )

    try:
        # run_sync() handles lock acquisition/release and calls core_sync()
        success = await run_sync()

        if success:
            sync_text += (
                "**✅ Sync Completed Successfully!**\n\n"
                "The knowledge base has been updated with the latest defense tactics.\n\n"
                "✅ **Query engine reload verified.**\n"
                "The updated index is ready for queries.\n\n"
                "💡 Tip: Use `get_aidefend_status` to verify the service is ready."
            )
        else:
            error = get_last_sync_error() or "Unknown error - check logs for details"
            raise RuntimeError(f"AIDEFEND sync failed: {error}")

        return [TextContent(type="text", text=sync_text)]

    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        raise


def format_search_results(query: str, results: List, top_k: int) -> str:
    """
    Format search results into a readable markdown text.

    Args:
        query: Original search query
        results: List of ContextChunk results
        top_k: Number of results requested

    Returns:
        Formatted markdown string
    """
    output = f"# AIDEFEND Search Results\n\n"
    output += f"**Query:** {escape_markdown(query)}\n"
    output += f"**Found:** {len(results)} result(s)\n\n"
    output += "---\n\n"

    for i, result in enumerate(results, 1):
        metadata = result.metadata

        output += f"## {i}. {metadata.get('name', 'N/A')}\n\n"
        output += f"**ID:** {result.source_id}\n"
        output += f"**Tactic:** {result.tactic}\n"
        output += f"**Type:** {metadata.get('type', 'N/A').title()}\n"
        output += f"**Relevance Score:** {result.score:.2f}\n\n"

        # Add pillar and phase if available
        if metadata.get('pillar'):
            output += f"**Pillar:** {metadata['pillar']}\n"
        if metadata.get('phase'):
            output += f"**Phase:** {metadata['phase']}\n"

        output += f"\n### Description\n\n{result.text}\n\n"
        output += _format_scope_boundary(
            metadata.get('scope_boundary'), heading_level=3
        )
        output += _format_record_tool_inventory(metadata, heading_level=3)
        output += "---\n\n"

    # Add footer with usage hint
    output += (
        "*Tip: For more specific results, try refining your query with keywords like "
        "'prompt injection', 'model poisoning', 'supply chain', etc.*"
    )

    return output


# ==================== P0 Tool Handlers ====================

async def handle_get_statistics(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_statistics tool call with audit logging."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("get_statistics", arguments, start_time)

    try:
        result = await get_statistics()

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Retrieved statistics: {result['overview']['total_documents']} docs"
        )

        # Format output
        import json
        output = "# AIDEFEND Knowledge Base Statistics\n\n"
        overview = result['overview']
        output += f"**Total Documents:** {overview['total_documents']}\n"
        output += f"**Techniques:** {overview['total_techniques']}\n"
        output += f"**Sub-techniques:** {overview['total_subtechniques']}\n"
        output += f"**Strategies:** {overview['total_strategies']}\n"
        for field, label in (
            ("total_actionable_items", "Actionable Controls"),
            ("total_parent_families", "Parent Families"),
            ("total_standalone_techniques", "Standalone Techniques"),
        ):
            if field in overview:
                output += f"**{label}:** {overview[field]}\n"
        output += "\n"

        output += "## Coverage by Tactic\n\n"
        for tactic, count in result['by_tactic'].items():
            output += f"- **{tactic}:** {count}\n"

        actionable_by_tactic = result.get('actionable_by_tactic', {})
        if actionable_by_tactic:
            output += "\n## Actionable Controls by Tactic\n\n"
            for tactic, count in actionable_by_tactic.items():
                output += f"- **{tactic}:** {count}\n"

        by_pillar = result.get('by_pillar', {})
        if by_pillar:
            output += "\n## Actionable Controls by Pillar\n\n"
            for pillar, count in by_pillar.items():
                output += f"- **{pillar}:** {count}\n"

        by_phase = result.get('by_phase', {})
        if by_phase:
            output += "\n## Actionable Controls by Phase\n\n"
            for phase, count in by_phase.items():
                output += f"- **{phase}:** {count}\n"

        tools = result.get('tools_availability', {})
        if tools:
            output += "\n## Tool and Scope Availability\n\n"
            for label, count_key, coverage_key in (
                (
                    "Open Source",
                    "techniques_with_opensource_tools",
                    "opensource_coverage_percentage",
                ),
                (
                    "Source Available / Open Weight",
                    "techniques_with_source_available_tools",
                    "source_available_coverage_percentage",
                ),
                (
                    "Commercial",
                    "techniques_with_commercial_tools",
                    "commercial_coverage_percentage",
                ),
            ):
                if count_key not in tools:
                    continue
                output += f"- **{label}:** {tools[count_key]} controls"
                if coverage_key in tools:
                    output += f" ({tools[coverage_key]}%)"
                output += "\n"
            for field, label in (
                ("controls_with_scope_boundaries", "Controls with Scope Boundaries"),
                (
                    "actionable_controls_with_scope_boundaries",
                    "Actionable Controls with Scope Boundaries",
                ),
            ):
                if field in tools:
                    output += f"- **{label}:** {tools[field]}\n"

        resources = result.get('implementation_resources', {})
        if resources:
            output += "\n## Implementation Resources\n\n"
            for field, label in (
                ("strategies_total", "Guidance Records"),
                ("canonical_guidance_documents", "Canonical Guidance IDs"),
                ("documents_with_code_snippets", "Guidance Records with Code"),
            ):
                if field in resources:
                    output += f"- **{label}:** {resources[field]}\n"
            if "code_coverage_percentage" in resources:
                output += (
                    "- **Guidance Code Coverage:** "
                    f"{resources['code_coverage_percentage']}%\n"
                )

        output += "\n## Threat Framework Coverage\n\n"
        tfc = result['threat_framework_coverage']
        by_framework = tfc.get("by_framework", {})
        if by_framework:
            for framework_meta in by_framework.values():
                label = framework_meta.get("label", "Unknown Framework")
                covered = framework_meta.get("items_covered", 0)
                total = framework_meta.get("total_items")
                pct = framework_meta.get("coverage_percentage")
                if total is None or pct is None:
                    output += f"- **{label}:** {covered} mapped items (authoritative total unavailable)\n"
                else:
                    output += f"- **{label}:** {covered}/{total} ({pct}%)\n"
        else:
            output += f"- **OWASP LLM Items:** {tfc['owasp_llm_items_covered']}/{tfc.get('owasp_llm_total_items', 10)} ({tfc.get('owasp_llm_coverage_percentage', 0)}%)\n"
            output += f"- **MITRE ATLAS Items:** {tfc['mitre_atlas_items_covered']}\n"
            output += f"- **MAESTRO Items:** {tfc.get('maestro_items_covered', 0)}\n"
        output += f"- **Actionable Items with Threat Mappings:** {tfc.get('techniques_with_threat_mappings', 0)} ({tfc.get('techniques_mapped_percentage', 0)}%)\n"

        output += f"\n*Last synced: {result['overview']['last_synced']}*"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_validate_technique_id(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle validate_technique_id tool call with audit logging."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("validate_technique_id", arguments, start_time)

    try:
        technique_id = arguments.get("technique_id", "")
        result = await validate_technique_id(technique_id)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Valid: {result['valid']}"
        )

        output = f"# Technique ID Validation: {technique_id}\n\n"

        if result['valid']:
            tech = result['technique']
            output += "✅ **Valid Technique ID**\n\n"
            output += f"**Name:** {tech['name']}\n"
            output += f"**Type:** {tech['type']}\n"
            output += f"**Tactic:** {tech['tactic']}\n"
            if tech.get('pillar'):
                output += f"**Pillar:** {tech['pillar']}\n"
            if tech.get('phase'):
                output += f"**Phase:** {tech['phase']}\n"
            if 'is_actionable' in tech:
                output += (
                    f"**Actionable:** {'Yes' if tech['is_actionable'] else 'No'}\n"
                )
            if tech.get('is_parent_family'):
                output += "**Parent Family:** Yes\n"
            output += "\n"
            output += _format_scope_boundary(
                tech.get('scope_boundary'), heading_level=2
            )
            output += _format_tool_inventory(
                {
                    "opensource": tech.get("tools_opensource", []),
                    "source_available": tech.get("tools_source_available", []),
                    "commercial": tech.get("tools_commercial", []),
                },
                heading_level=2,
            )
        else:
            output += f"❌ **Invalid/Not Found**\n\n"
            output += f"**Reason:** {result['reason']}\n\n"

            if result.get('suggestions'):
                output += "### Suggested Alternatives:\n\n"
                for sugg in result['suggestions'][:5]:
                    output += f"- **{sugg['id']}**: {sugg['name']} (similarity: {sugg['similarity_score']})\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_get_technique_detail(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_technique_detail tool call with audit logging."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("get_technique_detail", arguments, start_time)

    try:
        technique_id = arguments.get("technique_id", "")
        include_code = arguments.get("include_code", True)
        include_tools = arguments.get("include_tools", True)

        result = await get_technique_detail(technique_id, include_code, include_tools)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Retrieved {result['metadata']['total_subtechniques']} subtechniques"
        )

        tech = result['technique']
        output = f"# {tech['name']}\n\n"
        output += f"**ID:** {tech['id']}\n"
        output += f"**Tactic:** {tech['tactic']}\n"
        output += f"**Type:** {tech['type']}\n"
        if tech.get('pillar'):
            pillars = ", ".join(
                escape_markdown(str(value)) for value in tech['pillar']
            )
            output += f"**Pillar:** {pillars}\n"
        if tech.get('phase'):
            phases = ", ".join(
                escape_markdown(str(value)) for value in tech['phase']
            )
            output += f"**Phase:** {phases}\n"
        output += "\n"

        output += "## Description\n\n"
        output += tech['description'] + "\n\n"
        output += _format_scope_boundary(
            tech.get('scope_boundary'), heading_level=2
        )

        if tech.get('warnings'):
            output += "## Warnings and Scope Notes\n\n"
            for warning in tech['warnings']:
                level = warning.get('level', 'Important')
                description = warning.get('description', '')
                output += f"- **{level}:** {description}\n"
            output += "\n"

        if tech.get('defends_against'):
            output += "## Defends Against\n\n"
            for fw in tech['defends_against']:
                output += f"### {fw['framework']}\n"
                for item in fw['items']:
                    output += f"- {item}\n"
                output += "\n"

        if include_tools:
            output += _format_tool_inventory(
                tech.get('tools'), heading_level=2
            )

        output += _format_implementation_strategies(
            result.get('strategies'), heading_level=2
        )

        if result['subtechniques']:
            output += f"## Sub-Techniques ({len(result['subtechniques'])})\n\n"
            for st in result['subtechniques']:
                output += f"### {st['id']}: {st['name']}\n"
                output += f"- **Pillar:** {st['pillar']}\n"
                output += f"- **Phase:** {st['phase']}\n"
                for warning in st.get('warnings', []):
                    output += (
                        f"- **Warning — {warning.get('level', 'Important')}:** "
                        f"{warning.get('description', '')}\n"
                    )
                output += "\n"
                description = st.get('description')
                if isinstance(description, str) and description.strip():
                    output += "#### Description\n\n"
                    output += f"{escape_markdown(description.strip())}\n\n"
                output += _format_scope_boundary(
                    st.get('scope_boundary'), heading_level=4
                )
                if st.get('defends_against'):
                    output += "#### Defends Against\n\n"
                    for framework in st['defends_against']:
                        framework_name = escape_markdown(
                            str(framework.get('framework', 'Unknown'))
                        )
                        output += f"**{framework_name}:**\n"
                        for item in framework.get('items', []):
                            output += f"- {escape_markdown(str(item))}\n"
                        output += "\n"
                if include_tools:
                    output += _format_tool_inventory(
                        st.get('tools'), heading_level=4
                    )
                output += _format_implementation_strategies(
                    st.get('strategies'), heading_level=4
                )

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_get_defenses_for_threat(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_defenses_for_threat tool call."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("get_defenses_for_threat", arguments, start_time)

    try:
        result = await get_defenses_for_threat(**arguments)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Found {result['total_results']} defenses"
        )

        query = result['threat_query']
        output = "# Defense Techniques for Threat\n\n"
        output += f"**Query:** {escape_markdown(query.get('threat_id') or query.get('threat_keyword') or '')}\n"
        output += f"**Results:** {result['total_results']}\n\n"

        for i, tech in enumerate(result['defense_techniques'], 1):
            output += f"## {i}. {tech['technique']['name']}\n\n"
            output += f"**ID:** {tech['technique']['id']}\n"
            output += f"**Tactic:** {tech['technique']['tactic']}\n"
            output += f"**Relevance:** {tech['relevance_score']:.2f}\n\n"
            output += _format_scope_boundary(
                tech['technique'].get('scope_boundary'), heading_level=3
            )
            output += _format_tool_inventory(
                {
                    "opensource": tech['technique'].get("tools_opensource", []),
                    "source_available": tech['technique'].get(
                        "tools_source_available", []
                    ),
                    "commercial": tech['technique'].get("tools_commercial", []),
                },
                heading_level=3,
            )

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_get_secure_code_snippet(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_secure_code_snippet tool call."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("get_secure_code_snippet", arguments, start_time)

    try:
        result = await get_secure_code_snippet(**arguments)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Found {result['total_snippets']} code snippets"
        )

        output = "# Secure Code Snippets\n\n"
        query = result['query']
        query_desc = query.get('technique_id') or query.get('topic') or str(query)
        output += f"**Query:** {escape_markdown(query_desc)}\n"
        output += f"**Snippets Found:** {result['total_snippets']}\n\n"

        for i, snippet in enumerate(result['code_snippets'], 1):
            output += f"## Snippet {i}: {snippet['technique_name']}\n\n"
            output += f"**Technique ID:** {snippet['technique_id']}\n"
            output += f"**Language:** {snippet['language']}\n"
            output += f"**Implementation:** {snippet['implementation']}\n\n"
            output += _format_scope_boundary(
                snippet.get('scope_boundary'), heading_level=3
            )
            output += _format_record_tool_inventory(snippet, heading_level=3)
            output += "```" + snippet['language'] + "\n"
            output += snippet['code'] + "\n"
            output += "```\n\n"

        output += "\n⚠️ **Security Warning:** Review and test all code before production use.\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_analyze_coverage(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle analyze_coverage tool call."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("analyze_coverage", arguments, start_time)

    try:
        result = await analyze_coverage(**arguments)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Coverage: {result['analysis_summary']['coverage_percentage']}%"
        )

        summary = result['analysis_summary']
        output = "# Defense Coverage Analysis\n\n"
        output += f"**Coverage:** {summary['coverage_percentage']}% ({summary['coverage_level']})\n"
        output += f"**Implemented:** {summary['techniques_implemented']}/{summary['total_techniques_available']}\n\n"
        output += _format_resolution_diagnostics(
            summary.get('unrecognized_technique_ids'),
            summary.get('expanded_parent_families'),
        )

        output += "## Coverage by Tactic\n\n"
        for tactic, data in result['coverage_by_tactic'].items():
            status_emoji = {"not_covered": "❌", "minimal": "🟡", "partial": "🟠", "good": "🟢", "comprehensive": "✅"}.get(data['status'], "⚪")
            output += f"{status_emoji} **{tactic}:** {data['percentage']}% ({data['implemented']}/{data['total']})\n"

        if result['critical_gaps']:
            output += "\n## Critical Gaps\n\n"
            for gap in result['critical_gaps'][:5]:
                output += f"- **{gap.get('tactic', 'General')}:** {gap['reason']}\n"

        if result['recommendations']:
            output += "\n## Recommended Next Steps\n\n"
            for rec in result['recommendations'][:5]:
                output += f"{rec['rank']}. **{rec['technique_id']}** - {rec['name']}\n"
                output += f"   *{rec['reason']}*\n\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_map_to_compliance_framework(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle map_to_compliance_framework tool call."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("map_to_compliance_framework", arguments, start_time)

    try:
        result = await map_to_compliance_framework(**arguments)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Mapped {result['total_mapped']} techniques"
        )

        output = f"# Compliance Mapping: {result['framework']['name']}\n\n"
        output += f"**Framework Version:** {result['framework'].get('version', 'N/A')}\n"
        if 'total_requested' in result:
            output += f"**Technique IDs Requested:** {result['total_requested']}\n"
        output += f"**Total Techniques Mapped:** {result['total_mapped']}\n\n"
        output += _format_resolution_diagnostics(
            result.get('unrecognized_technique_ids'),
            {},
        )

        # Display coverage summary if available
        if result.get('summary'):
            summary = result['summary']
            output += "## Coverage Summary\n\n"
            output += f"**Total Controls in Framework:** {summary.get('total_controls_in_framework', 'N/A')}\n"
            output += f"**Covered Controls:** {summary.get('covered_controls', 0)}\n"
            output += f"**Coverage Percentage:** {summary.get('coverage_percentage', '0%')}\n\n"

            # Show uncovered critical controls
            if summary.get('uncovered_critical_controls'):
                output += "### Uncovered Critical Controls (High Priority)\n\n"
                for control_id in summary['uncovered_critical_controls']:
                    output += f"- {control_id}\n"
                output += "\n"

        output += "## Technique Mappings\n\n"

        for mapping in result['mappings']:
            output += f"## {mapping['technique_id']}: {mapping['technique_name']}\n\n"
            if mapping.get('error'):
                output += f"**Not Mapped:** {mapping['error']}\n\n"
                continue
            output += f"**Framework Controls:**\n\n"

            # Format control objects as readable Markdown
            for control in mapping['framework_controls']:
                if isinstance(control, dict):
                    # Control is an object with id, description, confidence
                    control_id = control.get('id', 'Unknown')
                    description = control.get('description', 'No description available')
                    confidence = control.get('confidence', 'medium')
                    output += f"- **{control_id}**: {description} *(Confidence: {confidence})*\n"
                else:
                    # Fallback for string controls (backward compatibility)
                    output += f"- {control}\n"

            output += f"\n**Mapping Confidence:** {mapping['mapping_confidence']}\n\n"
            output += _format_scope_boundary(
                mapping.get('scope_boundary'), heading_level=3
            )

        output += f"\n*{result['disclaimer']}*\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_get_quick_reference(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_quick_reference tool call."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("get_quick_reference", arguments, start_time)

    try:
        result = await get_quick_reference(**arguments)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Generated reference with {result['total_items']} items"
        )

        output = f"# Quick Reference: {result['topic']}\n\n"
        output += result['formatted_output']

        scoped_items = []
        for category in ('quick_wins', 'must_haves', 'nice_to_haves'):
            for item in result.get(category, []):
                if item.get('scope_boundary'):
                    scoped_items.append(item)
        if scoped_items:
            output += "\n\n## Scope Boundaries\n\n"
            for item in scoped_items:
                output += (
                    f"### {item.get('technique_id', 'N/A')}: "
                    f"{item.get('name', 'N/A')}\n\n"
                )
                output += _format_scope_boundary(
                    item.get('scope_boundary'), heading_level=4
                )

        tool_items = []
        for category in ('quick_wins', 'must_haves', 'nice_to_haves'):
            for item in result.get(category, []):
                if any(
                    item.get(field)
                    for field in (
                        'tools_opensource',
                        'tools_source_available',
                        'tools_commercial',
                    )
                ):
                    tool_items.append(item)
        if tool_items:
            output += "\n\n## Tool Inventories\n\n"
            for item in tool_items:
                output += (
                    f"### {item.get('technique_id', 'N/A')}: "
                    f"{item.get('name', 'N/A')}\n\n"
                )
                output += _format_record_tool_inventory(item, heading_level=4)

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


# ==================== New Tool Handlers ====================

async def handle_get_threat_coverage(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_threat_coverage tool call."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("get_threat_coverage", arguments, start_time)

    try:
        implemented_techniques = arguments.get("implemented_techniques", [])
        result = await get_threat_coverage(implemented_techniques)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=(
                f"{result['valid_count']}/{result['input_count']} valid, "
                f"OWASP: {len(result['covered'].get('owasp', []))}, "
                f"ATLAS: {len(result['covered'].get('atlas', []))}"
            ),
        )

        output = "# Threat Coverage Analysis\n\n"
        output += f"**Techniques Analyzed:** {result['input_count']}\n"
        output += f"**Valid Techniques:** {result['valid_count']}\n"
        output += f"**Invalid Techniques:** {result['invalid_count']}\n\n"
        if 'resolved_actionable_count' in result:
            output += (
                "**Actionable Controls Resolved:** "
                f"{result['resolved_actionable_count']}\n\n"
            )

        if result['invalid_techniques']:
            output += "## Invalid Technique IDs\n\n"
            for tech_id in result['invalid_techniques']:
                output += f"- {tech_id}\n"
            output += "\n"
        output += _format_resolution_diagnostics(
            [], result.get('expanded_parent_families')
        )

        output += "## Threat Coverage by Framework\n\n"
        covered_by_framework = result["covered"]
        framework_totals = result.get("framework_totals", {})
        coverage_rates = result["coverage_rate"]
        for key in _ordered_framework_coverage_keys(
            covered_by_framework,
            framework_totals,
            coverage_rates,
        ):
            label = framework_coverage_label(key)
            covered = result['covered'].get(key, [])
            total = framework_totals.get(key, 0)
            rate = result['coverage_rate'].get(key, 0.0) * 100
            output += f"### {label}\n"
            output += f"**Coverage:** {rate:.1f}% ({len(covered)}/{total})\n"
            if covered:
                preview = covered[:10]
                output += f"**Threats Covered:** {', '.join(preview)}"
                if len(covered) > 10:
                    output += f" ... +{len(covered) - 10} more"
                output += "\n"
            output += "\n"

        output += "## Coverage by Technique\n\n"
        for tech_data in result['by_technique'][:10]:
            output += f"### {tech_data['technique_id']}: {tech_data['technique_name']}\n"
            if tech_data.get("coverage_scope") == "aggregated_subtechniques":
                output += "- **Scope:** Aggregated from child sub-techniques\n"
            threats_by_framework = tech_data['threats_covered']
            for key in _ordered_framework_coverage_keys(threats_by_framework):
                threats = threats_by_framework.get(key, [])
                if threats:
                    label = framework_coverage_label(key)
                    output += f"- **{label}:** {', '.join(threats[:5])}"
                    if len(threats) > 5:
                        output += f" ... +{len(threats) - 5} more"
                    output += "\n"
            output += "\n"
            output += _format_scope_boundary(
                tech_data.get('scope_boundary'), heading_level=4
            )

        if len(result['by_technique']) > 10:
            output += f"*... and {len(result['by_technique']) - 10} more techniques*\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_get_implementation_plan(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle get_implementation_plan tool call."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("get_implementation_plan", arguments, start_time)

    try:
        implemented_techniques = arguments.get("implemented_techniques")
        exclude_tactics = arguments.get("exclude_tactics")
        top_k = arguments.get("top_k", 10)
        detail_level = arguments.get("detail_level", "basic")

        result = await get_implementation_plan(
            implemented_techniques=implemented_techniques,
            exclude_tactics=exclude_tactics,
            top_k=top_k,
            detail_level=detail_level
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{len(result['recommendations'])} recommendations, {len(result['categories']['quick_wins'])} quick wins, detail_level={detail_level}"
        )

        output = "# Defense Implementation Plan\n\n"
        if 'requested_count' in result['input']:
            output += f"**Requested Technique IDs:** {result['input']['requested_count']}\n"
        output += f"**Implemented Techniques:** {result['input']['implemented_count']}\n"
        if result['input']['exclude_tactics']:
            output += f"**Excluded Tactics:** {', '.join(result['input']['exclude_tactics'])}\n"
        output += f"**Recommendations Generated:** {len(result['recommendations'])}\n\n"
        output += _format_resolution_diagnostics(
            result['input'].get('unrecognized_technique_ids'),
            result['input'].get('expanded_parent_families'),
        )

        # Category summaries
        output += "## Priority Categories\n\n"
        output += f"- ⚡ **Quick Wins** ({len(result['categories']['quick_wins'])} techniques): High score + open-source tools available\n"
        output += f"- 🎯 **High Priority** ({len(result['categories']['high_priority'])} techniques): Score ≥ 7.0\n"
        output += f"- 📋 **Standard** ({len(result['categories']['standard'])} techniques): Score < 7.0\n\n"

        output += "## Top Recommendations\n\n"
        for rec in result['recommendations']:
            rank_emoji = "🥇" if rec['rank'] == 1 else "🥈" if rec['rank'] == 2 else "🥉" if rec['rank'] == 3 else f"{rec['rank']}."
            output += f"{rank_emoji} **{rec['technique_id']}**: {rec['technique_name']}\n"
            output += f"   - **Score:** {rec['score']}/10\n"
            output += f"   - **Tactic:** {rec['tactic']}\n"
            output += f"   - **Pillar:** {rec['pillar']} | **Phase:** {rec['phase']}\n"

            # Score breakdown
            breakdown = rec['score_breakdown']
            output += f"   - **Score Breakdown:**\n"
            output += f"     - Threat Importance: {breakdown['threat_importance']}/3\n"
            output += f"     - Ease of Implementation: {breakdown['ease_of_implementation']}/2\n"
            output += f"     - Phase Weight: {breakdown['phase_weight']}/2\n"
            output += f"     - Pillar Weight: {breakdown['pillar_weight']}/2\n"
            output += f"     - Tool Ecosystem: {breakdown['tool_ecosystem']}/1\n"

            output += f"   - **Reasoning:** {rec['reasoning']}\n"
            if rec['has_opensource_tools']:
                output += "   - ✅ **Open-source tools available**\n"
            if rec.get('has_source_available_tools'):
                output += "   - **Source-available / open-weight tools available**\n"
            output += "\n"
            output += _format_record_tool_inventory(rec, heading_level=4)
            output += _format_scope_boundary(
                rec.get('scope_boundary'), heading_level=4
            )

        # Add actionable strategies if detail_level is "standard" or "detailed"
        if 'actionable_strategies' in result and result['actionable_strategies']:
            output += "## 🎯 Actionable Implementation Strategies (Top 5)\n\n"
            output += f"*Generated with detail_level='{detail_level}' - eliminates need for subsequent get_technique_detail calls*\n\n"

            for strategy_data in result['actionable_strategies']:
                tech_id = strategy_data['technique_id']
                tech_name = strategy_data['technique_name']
                strategies = strategy_data['strategies']
                strategy_count = strategy_data['strategy_count']

                output += f"### {tech_id}: {tech_name}\n\n"

                if 'error' in strategy_data:
                    output += f"*Error: {strategy_data['error']}*\n\n"
                    continue

                if strategy_count == 0:
                    output += "*No implementation strategies available in database*\n\n"
                    continue

                output += f"**{strategy_count} Implementation Strategies:**\n\n"

                for i, strat in enumerate(strategies, 1):
                    output += f"{i}. **{strat['strategy_name']}**\n"
                    output += f"   {strat['summary']}\n"

                    # Add code snippets if in "detailed" mode
                    if 'code_snippets' in strat:
                        code_count = strat.get('code_snippet_count', len(strat['code_snippets']))
                        output += f"\n   **Code Examples ({code_count}):**\n"
                        for j, code_block in enumerate(strat['code_snippets'], 1):
                            lang = code_block['language']
                            code = code_block['code']
                            output += f"\n   *Example {j} ({lang}):*\n"
                            output += f"   ```{lang}\n"
                            # Indent code block for proper markdown rendering
                            indented_code = '\n'.join('   ' + line for line in code.split('\n'))
                            output += f"{indented_code}\n"
                            output += "   ```\n"

                    output += "\n"

            # Add metadata
            if 'metadata' in result:
                metadata = result['metadata']
                output += f"\n---\n*Compound Tool Metadata: {metadata['strategies_fetched']} techniques processed with detail_level={metadata['detail_level']}*\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_classify_threat(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle classify_threat tool call."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("classify_threat", arguments, start_time)

    try:
        text = arguments.get("text", "")
        top_k = arguments.get("top_k", 5)

        result = await classify_threat(text=text, top_k=top_k)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{len(result['keywords_found'])} keywords matched"
        )

        output = "# Threat Classification Results\n\n"

        # Display classification source/tier
        source = result.get('source', 'unknown')
        source_labels = {
            'static_keyword': '🔍 Static Keyword Match (Tier 1)',
            'fuzzy_match': '🔎 Fuzzy Match - Typo Tolerant (Tier 2)',
            'no_match': '❌ No Match Found'
        }
        output += f"**Classification Source:** {source_labels.get(source, source)}\n"
        output += f"**Input Text:** {escape_markdown(result['input_text_preview'])}\n"
        output += f"**Keywords Matched:** {len(result['keywords_found'])}\n\n"

        if result['keywords_found']:
            output += "## Matched Keywords\n\n"
            for kw in result['keywords_found']:
                confidence_emoji = "🟢" if kw['confidence'] >= 0.85 else "🟡" if kw['confidence'] >= 0.7 else "🟠"
                match_type_label = "Primary" if kw['match_type'] == "primary" else "Alias"
                output += f"{confidence_emoji} **{kw['keyword'].title()}** ({match_type_label}, confidence: {kw['confidence']})\n"
            output += "\n"

        output += "## Normalized Threat IDs\n\n"
        classify_labels = {"owasp": "OWASP", "atlas": "MITRE ATLAS", "maestro": "MAESTRO"}
        has_normalized = False
        for key, values in result['normalized_threats'].items():
            if not values:
                continue
            has_normalized = True
            label = classify_labels.get(key, FRAMEWORK_LABELS.get(key, key.upper()))
            output += f"**{label}:** {', '.join(values)}\n"

        if not has_normalized:
            output += "*No threat IDs identified*\n"
        output += "\n"

        mapping_status = result.get("mapping_status", {})
        unresolved_claims = mapping_status.get("unresolved_claims", [])
        if unresolved_claims:
            output += (
                "⚠️ **Current index mapping:** The following classifier claims "
                "do not resolve to a defense in the synchronized framework: "
                + ", ".join(escape_markdown(claim) for claim in unresolved_claims)
                + "\n\n"
            )

        if result['threat_details']:
            output += "## Threat Details\n\n"
            for detail in result['threat_details']:
                output += f"- **{detail['threat_id']}**: {detail['threat_name']}\n"
                output += f"  - Confidence: {detail['confidence']}\n"
                output += f"  - Matched Keyword: {detail['matched_keyword']}\n"
                output += f"  - Match Type: {detail['match_type']}\n"
            output += "\n"

        if result['recommended_actions']:
            output += "## Recommended Next Steps\n\n"
            for action in result['recommended_actions']:
                output += f"- **{action['tool']}**\n"
                output += f"  - Args: {action['args']}\n"
                output += f"  - Reason: {action['reason']}\n"
            output += "\n"

        # Add tier-specific note
        if source == 'static_keyword':
            output += "*Note: Direct keyword match found. High confidence result.*\n"
        elif source == 'fuzzy_match':
            output += "*Note: Fuzzy matching applied for typo tolerance. Verify match accuracy.*\n"
        else:
            output += "*Note: No threats matched. Consider rephrasing or check if threat is in keyword dictionary.*\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_comprehensive_search(arguments: Dict[str, Any]) -> List[TextContent]:
    """
    Handler for comprehensive_search tool.

    Performs multi-query aggregated search for broad topics, preventing timeout
    from sequential tool calls.

    Args:
        arguments: Tool arguments (topic, max_results, include_subtechniques)

    Returns:
        List containing formatted TextContent response
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call("comprehensive_search", arguments, start_time)

    try:
        # Extract arguments with defaults
        topic = arguments.get("topic", "").strip()
        max_results = arguments.get("max_results", 20)
        include_subtechniques = arguments.get("include_subtechniques", True)

        # Call tool function
        result = await comprehensive_search(
            topic=topic,
            max_results=max_results,
            include_subtechniques=include_subtechniques
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Found {len(result['results'])} results across {len(result['queries_executed'])} queries"
        )

        # Format output for Claude Desktop
        output = "# Comprehensive Search Results\n\n"
        output += f"**Topic:** {escape_markdown(result['input_topic'])}\n"
        output += f"**Search Strategy:** Multi-query ({len(result['queries_executed'])} queries executed)\n"
        output += f"**Total Results:** {result['total_results_after_dedup']} (deduplicated from {result['total_results_before_dedup']})\n\n"

        output += "## Queries Executed\n\n"
        for i, query in enumerate(result['queries_executed'], 1):
            output += f"{i}. {escape_markdown(query)}\n"
        output += "\n"

        # Coverage summary
        coverage = result['coverage_summary']
        output += "## Coverage Summary\n\n"
        output += f"**Total Techniques:** {coverage['techniques']}\n"
        output += f"**Total Sub-techniques:** {coverage['subtechniques']}\n"
        output += f"**Tactics Covered:** {', '.join(coverage['tactics_covered'])}\n\n"

        if coverage.get('by_tactic'):
            output += "**By Tactic:**\n"
            for tactic, count in sorted(coverage['by_tactic'].items(), key=lambda x: -x[1]):
                output += f"  - {tactic}: {count}\n"
            output += "\n"

        if coverage.get('by_pillar'):
            output += "**By Pillar:**\n"
            for pillar, count in sorted(coverage['by_pillar'].items(), key=lambda x: -x[1]):
                output += f"  - {pillar}: {count}\n"
            output += "\n"

        # Results
        output += "## Results\n\n"
        if result['results']:
            for i, item in enumerate(result['results'], 1):
                output += f"### {i}. {item['name']} ({item['source_id']})\n\n"
                output += f"**Tactic:** {item['tactic']}\n"
                output += f"**Type:** {item['type']}\n"
                output += f"**Relevance Score:** {item['_distance']:.3f}\n"
                output += f"**Matched Query:** {escape_markdown(item['matched_query'])}\n"

                if item.get('pillar'):
                    output += f"**Pillar:** {item['pillar']}\n"
                if item.get('phase'):
                    output += f"**Phase:** {item['phase']}\n"

                desc = item['description']
                output += f"\n**Description:**\n{desc[:300]}{'...' if len(desc) > 300 else ''}\n\n"
                output += _format_scope_boundary(
                    item.get('scope_boundary'), heading_level=4
                )
                output += _format_record_tool_inventory(item, heading_level=4)
                output += "---\n\n"
        else:
            output += "*No results found for this topic.*\n\n"

        # Related searches
        if result.get('related_searches'):
            output += "## Related Searches\n\n"
            for suggestion in result['related_searches']:
                output += f"- {suggestion}\n"
            output += "\n"

        output += "---\n\n"
        output += "*Tip: Use `get_technique_detail` with a specific source_id for more information.*\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_analyze_security_posture(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle analyze_security_posture tool call."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("analyze_security_posture", arguments, start_time)

    try:
        # Extract parameters
        implemented_techniques = arguments.get("implemented_techniques", [])
        view = arguments.get("view", "both")
        system_type = arguments.get("system_type")

        # Call the unified tool
        result = await analyze_security_posture(
            implemented_techniques=implemented_techniques,
            view=view,
            system_type=system_type
        )

        # Determine success summary
        if view == "both" and result.get("summary"):
            summary_text = f"Posture: {result['summary']['overall_posture']}"
        elif view == "technical" and result.get("technical_coverage"):
            pct = result['technical_coverage'].get('analysis_summary', {}).get('coverage_percentage', 0)
            summary_text = f"Technical: {pct:.1f}%"
        elif view == "threat" and result.get("threat_coverage"):
            coverage_rates = result['threat_coverage'].get('coverage_rate', {})
            framework_rates = [
                coverage_rates.get(key, 0) * 100
                for key in _ordered_framework_coverage_keys(coverage_rates)
            ]
            avg_framework_rate = sum(framework_rates) / len(framework_rates) if framework_rates else 0.0
            summary_text = f"Threat coverage: {avg_framework_rate:.1f}% avg"
        else:
            summary_text = "Analysis complete"

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=summary_text
        )

        technical_summary = result.get("technical_coverage", {}).get(
            "analysis_summary", {}
        )
        threat_coverage = result.get("threat_coverage", {})
        posture_invalid_ids = (
            result.get("invalid_technique_ids")
            or result.get("unrecognized_technique_ids")
            or technical_summary.get("unrecognized_technique_ids")
            or threat_coverage.get("invalid_techniques")
            or []
        )
        posture_expansions = (
            result.get("expanded_parent_families")
            or technical_summary.get("expanded_parent_families")
            or threat_coverage.get("expanded_parent_families")
            or {}
        )

        # Format output
        output = "# Security Posture Analysis\n\n"
        output += f"**View:** {view.title()}\n"
        output += f"**Techniques Analyzed:** {result['implemented_count']}\n"
        if 'requested_count' in result:
            output += f"**Requested Technique IDs:** {result['requested_count']}\n"
        if 'implemented_actionable_count' in result:
            output += (
                "**Actionable Controls Resolved:** "
                f"{result['implemented_actionable_count']}\n"
            )
        if system_type:
            output += f"**System Type:** {system_type}\n"
        output += "\n"
        output += _format_resolution_diagnostics(
            posture_invalid_ids,
            posture_expansions,
        )

        # Unified summary (only for 'both' view)
        if view == "both" and result.get("summary"):
            summary = result["summary"]
            output += "## Overall Security Posture\n\n"
            output += f"**Assessment:** {summary['overall_posture'].upper()}\n\n"

            output += "### Key Insights\n\n"
            for insight in summary.get("key_insights", []):
                output += f"- {insight}\n"
            output += "\n"

            if summary.get("top_priorities"):
                output += "### Top Priorities\n\n"
                for priority in summary["top_priorities"]:
                    output += f"- {priority}\n"
                output += "\n"

        # Technical Coverage Section
        # analyze_coverage returns: analysis_summary, coverage_by_tactic (dict of dicts),
        # critical_gaps (with gap_type/tactic/severity/reason), recommendations
        if view in ["both", "technical"] and result.get("technical_coverage"):
            tech = result["technical_coverage"]
            output += "## Technical Coverage\n\n"

            overall = tech.get("analysis_summary", {})
            output += f"**Coverage:** {overall.get('coverage_percentage', 0):.1f}% "
            output += f"({overall.get('coverage_level', 'unknown')})\n"
            output += f"**Implemented:** {overall.get('techniques_implemented', 0)}/{overall.get('total_techniques_available', 0)} techniques\n\n"

            # By Tactic
            coverage_by_tactic = tech.get("coverage_by_tactic", {})
            if coverage_by_tactic:
                output += "### Coverage by Tactic\n\n"
                tactic_list = [
                    {"tactic": tactic, **stats}
                    for tactic, stats in coverage_by_tactic.items()
                ]
                for tactic_info in sorted(tactic_list, key=lambda x: -x.get("percentage", 0)):
                    output += f"- **{tactic_info['tactic']}:** {tactic_info.get('percentage', 0):.1f}% "
                    output += f"({tactic_info.get('implemented', 0)}/{tactic_info.get('total', 0)})\n"
                output += "\n"

            # Critical Gaps
            if tech.get("critical_gaps"):
                output += "### Critical Gaps (High Priority)\n\n"
                for gap in tech["critical_gaps"][:5]:
                    output += f"- **{gap.get('tactic', 'Unknown')}:** {gap.get('reason', 'No description')}\n"
                    if gap.get('risk'):
                        output += f"  - Risk: {gap['risk']}\n"
                output += "\n"

            # Recommendations
            if tech.get("recommendations"):
                output += "### Recommended Techniques\n\n"
                for rec in tech["recommendations"][:5]:
                    output += f"- **{rec.get('technique_id', 'Unknown')}:** {rec.get('name', 'No name')}\n"
                    output += f"  - Tactic: {rec.get('tactic', 'Unknown')}\n"
                    if rec.get('reason'):
                        output += f"  - Reason: {rec['reason']}\n"
                output += "\n"

        # Threat Coverage Section
        # get_threat_coverage returns: coverage_rate (fractions 0-1), covered (dict of lists)
        if view in ["both", "threat"] and result.get("threat_coverage"):
            threat = result["threat_coverage"]
            output += "## Threat Framework Coverage\n\n"

            coverage_rate = threat.get("coverage_rate", {})
            covered = threat.get("covered", {})
            framework_totals = threat.get("framework_totals", {})
            for key in _ordered_framework_coverage_keys(
                coverage_rate,
                covered,
                framework_totals,
            ):
                label = framework_coverage_label(key)
                rate = coverage_rate.get(key, 0) * 100
                count = len(covered.get(key, []))
                total = framework_totals.get(key, 0)
                output += f"**{label}:** {rate:.1f}% ({count}/{total})\n"
            output += "\n"

            if covered.get("owasp_llm"):
                output += "### OWASP Threats Covered\n\n"
                output += f"{', '.join(covered['owasp_llm'])}\n\n"

            # Compute uncovered OWASP threats
            all_owasp = ["LLM01", "LLM02", "LLM03", "LLM04", "LLM05",
                         "LLM06", "LLM07", "LLM08", "LLM09", "LLM10"]
            covered_owasp = covered.get("owasp_llm", [])
            uncovered_owasp = [t for t in all_owasp if t not in covered_owasp]
            if uncovered_owasp:
                output += "### OWASP Threats NOT Covered (High Priority)\n\n"
                output += f"{', '.join(uncovered_owasp[:5])}\n\n"

            scoped_techniques = [
                item
                for item in threat.get("by_technique", [])
                if item.get("scope_boundary")
            ]
            if scoped_techniques:
                output += "### Technique Scope Boundaries\n\n"
                for item in scoped_techniques[:10]:
                    output += (
                        f"#### {item.get('technique_id', 'N/A')}: "
                        f"{item.get('technique_name', 'N/A')}\n\n"
                    )
                    output += _format_scope_boundary(
                        item.get("scope_boundary"), heading_level=5
                    )
                if len(scoped_techniques) > 10:
                    output += (
                        f"*... and {len(scoped_techniques) - 10} more scoped "
                        "techniques*\n\n"
                    )

        output += "---\n\n"
        output += "*Tip: Use `get_implementation_plan` to get prioritized recommendations for next steps.*\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_compare_techniques(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle compare_techniques tool call."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("compare_techniques", arguments, start_time)

    try:
        # Extract parameters
        technique_ids = arguments.get("technique_ids", [])
        include_recommendations = arguments.get("include_recommendations", True)

        # Call the comparison tool
        result = await compare_techniques(
            technique_ids=technique_ids,
            include_recommendations=include_recommendations
        )

        # Audit success
        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Compared {result['summary']['techniques_compared']} techniques"
        )

        # Format output
        output = "# Technique Comparison Matrix\n\n"
        output += f"**Techniques Compared:** {result['summary']['techniques_compared']}\n"

        if result['summary'].get('techniques_not_found'):
            output += f"**Not Found:** {', '.join(result['summary']['techniques_not_found'])}\n"

        output += "\n"

        # Summary statistics
        output += "## Summary Statistics\n\n"
        summary = result['summary']
        output += f"- **Average Effectiveness:** {summary['average_effectiveness']:.1f}/100\n"
        output += f"- **Average Complexity:** {summary['average_complexity']:.1f}/100\n"
        output += f"- **Average Cost:** {summary['average_cost']:.1f}/100\n"
        output += f"- **Tactics Covered:** {', '.join(summary['tactics_covered'])}\n"
        output += f"- **Pillars Covered:** {', '.join(summary['pillars_covered'])}\n\n"

        # Comparison matrix table
        output += "## Comparison Matrix\n\n"
        output += "| Technique | Effectiveness | Complexity | Cost | Tactic | Pillar |\n"
        output += "|-----------|---------------|------------|------|--------|--------|\n"

        for tech in result['comparison_matrix']:
            name = tech['name']
            output += f"| **{tech['source_id']}**<br/>{name[:40]}{'...' if len(name) > 40 else ''} | "
            output += f"{tech['effectiveness_score']}/100 | "
            output += f"{tech['complexity_score']}/100 | "
            output += f"{tech['cost_score']}/100 | "
            output += f"{tech['tactic']} | "
            output += f"{tech['pillar']} |\n"

        output += "\n"

        # Detailed breakdown
        output += "## Detailed Analysis\n\n"

        for i, tech in enumerate(result['comparison_matrix'], 1):
            output += f"### {i}. {tech['name']} ({tech['source_id']})\n\n"

            # Scores with interpretation
            output += "**Scores:**\n"
            output += f"- 🎯 **Effectiveness:** {tech['effectiveness_score']}/100 "
            if tech['effectiveness_score'] >= 80:
                output += "(Excellent)\n"
            elif tech['effectiveness_score'] >= 60:
                output += "(Good)\n"
            elif tech['effectiveness_score'] >= 40:
                output += "(Moderate)\n"
            else:
                output += "(Limited)\n"

            output += f"- ⚙️ **Complexity:** {tech['complexity_score']}/100 "
            if tech['complexity_score'] >= 70:
                output += "(High - significant effort)\n"
            elif tech['complexity_score'] >= 40:
                output += "(Moderate)\n"
            else:
                output += "(Low - relatively simple)\n"

            output += f"- 💰 **Cost:** {tech['cost_score']}/100 "
            if tech['cost_score'] >= 70:
                output += "(High - significant investment)\n"
            elif tech['cost_score'] >= 40:
                output += "(Moderate)\n"
            else:
                output += "(Low)\n\n"

            # Key attributes
            output += "**Key Attributes:**\n"
            output += f"- **Tactic:** {tech['tactic']}\n"
            output += f"- **Pillar:** {tech['pillar']}\n"
            output += f"- **Phase:** {tech['phase']}\n"

            # Threat coverage
            threat_cov = tech['threat_coverage']
            if any(threat_cov.values()):
                by_framework = threat_cov.get("by_framework", {})
                if by_framework:
                    coverage_parts = [
                        f"{framework_coverage_label(key)} ({count})"
                        for key, count in by_framework.items()
                        if count
                    ]
                    if coverage_parts:
                        output += f"- **Threat Coverage:** {', '.join(coverage_parts)}\n"
                else:
                    output += f"- **Threat Coverage:** OWASP ({threat_cov['owasp']}), "
                    output += f"ATLAS ({threat_cov['atlas']}), MAESTRO ({threat_cov['maestro']})\n"

            # Implementation support
            if tech['has_implementation_guidance']:
                output += "- ✅ Has implementation guidance\n"
            if tech['has_code_snippets']:
                output += "- ✅ Has code examples\n"
            if tech['has_opensource_tools']:
                output += "- ✅ Open-source tools available\n"
            if tech.get('has_source_available_tools'):
                output += "- Source-available / open-weight tools available\n"
            if tech['has_commercial_tools']:
                output += "- 💰 Commercial tools available\n"

            output += "\n"

            output += _format_record_tool_inventory(tech, heading_level=4)

            # Brief description
            output += f"**Description:** {tech['description']}\n\n"
            output += _format_scope_boundary(
                tech.get('scope_boundary'), heading_level=4
            )
            output += "---\n\n"

        # Recommendations
        if include_recommendations and result.get('recommendations'):
            output += "## 📊 Implementation Recommendations\n\n"

            for rec in result['recommendations']:
                output += f"### {rec['category']}\n\n"
                output += f"*{rec['description']}*\n\n"

                for tech in rec['techniques']:
                    output += f"- **{tech['id']}:** {tech['name']}\n"

                output += "\n"

        output += "---\n\n"
        output += "*Tip: Use `get_technique_detail` to dive deeper into any technique, "
        output += "or `get_implementation_plan` for prioritized roadmap.*\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


async def handle_generate_incident_playbook(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle generate_incident_playbook tool call."""
    start_time = datetime.now()
    audit_ctx = audit_tool_call("generate_incident_playbook", arguments, start_time)

    try:
        # Extract parameters
        incident_description = arguments.get("incident_description", "")
        include_defense_techniques = arguments.get("include_defense_techniques", True)

        # Call the playbook generator
        result = await generate_incident_playbook(
            incident_description=incident_description,
            include_defense_techniques=include_defense_techniques
        )

        # Audit success
        total_actions = result['incident_summary']['total_action_items']
        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Generated playbook with {total_actions} actions"
        )

        # Format output
        output = "# 🚨 Incident Response Playbook\n\n"
        output += f"**Generated:** {result['generated_at']}\n\n"

        # Incident summary
        summary = result['incident_summary']
        output += "## 📋 Incident Summary\n\n"
        output += f"**Description:** {escape_markdown(summary['description'])}\n\n"

        if summary.get('primary_threat'):
            threat = summary['primary_threat']
            output += "**Primary Threat Identified:**\n"
            output += f"- **Threat ID:** {threat['threat_id']}\n"
            output += f"- **Framework:** {threat['framework']}\n"
            output += f"- **Confidence:** {threat['confidence']:.1f}%\n"
            output += f"- **Description:** {threat['description']}\n\n"

        output += f"**Total Action Items:** {summary['total_action_items']}\n"
        output += f"**Estimated Timeline:** {summary['estimated_total_time']}\n\n"

        output += "---\n\n"

        # Timeline-based playbook
        for phase_key, phase_data in result['timeline'].items():
            output += f"## {phase_data['phase']}\n\n"
            output += f"**⏱️ Timeframe:** {phase_data['timeframe']}\n\n"
            output += f"**🎯 Objective:** {phase_data['objective']}\n\n"

            output += "### Action Items\n\n"

            for i, action in enumerate(phase_data['actions'], 1):
                priority_emoji = {
                    "CRITICAL": "🔴",
                    "HIGH": "🟠",
                    "MEDIUM": "🟡",
                    "LOW": "🟢"
                }.get(action.get('priority', 'MEDIUM'), "⚪")

                output += f"#### {i}. {priority_emoji} {action['action']}\n\n"
                output += f"**Priority:** {action.get('priority', 'MEDIUM')}\n\n"
                output += f"**Description:** {action['description']}\n\n"
                output += f"**Estimated Time:** {action['estimated_time']}\n\n"

                if action.get('tools'):
                    output += f"**Tools:** {', '.join(action['tools'])}\n\n"

                if action.get('reference'):
                    output += f"**Reference:** {action['reference']}\n\n"

                output += "**Status:** [ ] Not Started\n\n"

            output += "---\n\n"

        # Defense techniques recommendation
        # get_defenses_for_threat returns {"defense_techniques": [{technique: {id, name, ...}, relevance_score}, ...]}
        if include_defense_techniques and result.get('defense_techniques'):
            defense = result['defense_techniques']
            output += "## 🛡️ Recommended Defense Techniques\n\n"

            defense_list = defense.get('defense_techniques', [])
            if defense_list:
                output += f"**Total Techniques Found:** {len(defense_list)}\n\n"
                output += "### Top Defense Techniques\n\n"

                for i, tech_entry in enumerate(defense_list[:5], 1):
                    tech = tech_entry.get('technique', {})
                    output += f"{i}. **{tech.get('id', 'N/A')}:** {tech.get('name', 'N/A')}\n"
                    output += f"   - **Tactic:** {tech.get('tactic', 'N/A')}\n"
                    desc = tech.get('description', 'N/A')
                    output += f"   - **Description:** {desc[:150]}{'...' if len(desc) > 150 else ''}\n\n"
                    output += _format_scope_boundary(
                        tech.get('scope_boundary'), heading_level=4
                    )
                    output += _format_record_tool_inventory(tech, heading_level=4)

                output += "\n*Use `get_technique_detail` for implementation details.*\n\n"
            else:
                output += "*No specific defense techniques found. Consider using `comprehensive_search` "
                output += "to explore related defenses.*\n\n"

        # Threat classification details
        # classify_threat returns threat_details (not matched_threats)
        if result.get('threat_classification') and result['threat_classification'].get('threat_details'):
            output += "## 🔍 Threat Classification Details\n\n"

            threats = result['threat_classification']['threat_details']
            output += f"**Matched Threats:** {len(threats)}\n\n"

            for i, threat in enumerate(threats[:5], 1):
                output += f"{i}. **{threat.get('threat_id', 'N/A')}**\n"
                output += f"   - **Confidence:** {threat.get('confidence', 0) * 100:.1f}%\n"
                output += f"   - **Keyword Match:** {threat.get('matched_keyword', 'N/A')}\n"
                output += f"   - **Threat Name:** {threat.get('threat_name', 'N/A')}\n\n"

        output += "---\n\n"

        # Next steps
        output += "## 📝 Next Steps\n\n"
        output += "1. ✅ Review and customize this playbook for your environment\n"
        output += "2. ✅ Assign action items to team members\n"
        output += "3. ✅ Set up monitoring for completion\n"
        output += "4. ✅ Update incident timeline in your tracking system\n"
        output += "5. ✅ Document lessons learned after resolution\n\n"

        output += "**Additional Resources:**\n"
        output += "- Use `get_technique_detail` for implementation guides\n"
        output += "- Use `get_secure_code_snippet` for code examples\n"
        output += "- Use `analyze_security_posture` to assess current defenses\n"
        output += "- Use `map_to_compliance_framework` for regulatory requirements\n\n"

        return [TextContent(type="text", text=output)]

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        raise


def main():
    """
    Main entry point for the MCP server.

    This function starts the asyncio event loop and runs the server.
    """
    try:
        # Write startup message to stderr (stdout is used for MCP protocol)
        print("AIDEFEND MCP Server starting...", file=sys.stderr)
        print("Waiting for MCP client connections...", file=sys.stderr)

        # Run the server
        asyncio.run(serve())

    except KeyboardInterrupt:
        print("\nMCP Server stopped by user", file=sys.stderr)
    except Exception as e:
        print(f"MCP Server error: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
