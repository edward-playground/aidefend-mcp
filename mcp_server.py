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
from typing import Any, Dict, List

# MCP SDK imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# AIDEFEND imports
from app.core import query_engine, QueryEngineNotInitializedError
from app.schemas import QueryRequest
from app.sync import run_sync, get_last_sync_error
from app.logger import get_logger
from app.security import InputValidationError, SecurityError
from app.audit import audit_tool_call, audit_tool_completion
from datetime import datetime

# Import all P0 tools
from app.tools import (
    get_statistics,
    validate_technique_id,
    get_technique_detail,
    get_defenses_for_threat,
    get_secure_code_snippet,
    analyze_coverage,
    map_to_compliance_framework,
    get_quick_reference
)

# Import new tools
from app.tools.threat_coverage import get_threat_coverage
from app.tools.implementation_plan import get_implementation_plan
from app.tools.classify_threat import classify_threat

logger = get_logger(__name__)


async def serve():
    """
    Start the MCP server using stdio transport.

    This function initializes the MCP server and registers all available tools.
    It runs indefinitely, processing tool calls from MCP clients (like Claude Desktop).
    """
    # Create MCP server instance
    server = Server("aidefend-mcp")

    logger.info("Initializing AIDEFEND MCP Server...")

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
                            "type": "number",
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
                    "Manually trigger synchronization with the AIDEFEND GitHub repository "
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
                    "all sub-techniques, implementation strategies with code examples, "
                    "tool recommendations, and threat mappings. This is the primary tool "
                    "for deep-diving into a specific defense technique."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "technique_id": {
                            "type": "string",
                            "description": "Technique or sub-technique ID (e.g., 'AID-H-001', 'AID-H-001.001')"
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
                    "Supports threat IDs from OWASP LLM Top 10 (e.g., 'LLM01'), "
                    "MITRE ATLAS (e.g., 'T0043'), MAESTRO, or natural language threat keywords "
                    "(e.g., 'prompt injection'). Essential for threat-driven defense planning."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "threat_id": {
                            "type": "string",
                            "description": "Threat ID from OWASP/ATLAS/MAESTRO (e.g., 'LLM01', 'T0043')"
                        },
                        "threat_keyword": {
                            "type": "string",
                            "description": "Natural language threat keyword (e.g., 'prompt injection', 'model poisoning')"
                        },
                        "top_k": {
                            "type": "number",
                            "description": "Number of defense techniques to return (1-50, default: 10)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50
                        }
                    },
                    "required": []
                }
            ),
            # P0 Tool 5: Get Secure Code Snippet
            Tool(
                name="get_secure_code_snippet",
                description=(
                    "Extract executable secure code snippets from AIDEFEND implementation strategies. "
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
                            "type": "number",
                            "description": "Maximum number of snippets (1-20, default: 5)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 20
                        }
                    },
                    "required": []
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
                    "Uses LLM-based analysis for dynamic mapping. Critical for governance and audit."
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
                        },
                        "use_llm": {
                            "type": "boolean",
                            "description": "Use LLM for mapping (default: true)",
                            "default": True
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
                            "type": "number",
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
                    "are covered (OWASP LLM Top 10, MITRE ATLAS, MAESTRO) and provides "
                    "coverage rates. Essential for tracking security posture and identifying gaps."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "implemented_techniques": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of implemented technique IDs (e.g., ['AID-D-001', 'AID-H-002'])",
                            "minItems": 1,
                            "maxItems": 100
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
                    "to make final recommendations via your own reasoning."
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
                            "type": "number",
                            "description": "Number of recommendations to return (1-20, default: 10)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 20
                        }
                    },
                    "required": []
                }
            ),
            # New Tool 3: Classify Threat from Text (3-Tier: Static + Fuzzy + LLM)
            Tool(
                name="classify_threat",
                description=(
                    "Classify threats in text using 3-tier matching system: "
                    "1) Static keyword matching (free), "
                    "2) Fuzzy matching for typo tolerance (free), "
                    "3) LLM semantic inference (optional, user-paid). "
                    "Maps common threat terms (prompt injection, model poisoning, etc.) to "
                    "standard framework IDs (OWASP LLM, MITRE ATLAS, MAESTRO). "
                    "Gracefully degrades if user hasn't enabled/configured LLM fallback."
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
                            "type": "number",
                            "description": "Maximum keywords to return (1-10, default: 5)",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 10
                        }
                    },
                    "required": ["text"]
                }
            )
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """
        Handle MCP tool calls.

        Args:
            name: Name of the tool to call
            arguments: Tool arguments as a dictionary

        Returns:
            List of TextContent responses

        Raises:
            ValueError: If tool name is unknown or arguments are invalid
        """
        try:
            # Original tools
            if name == "query_aidefend":
                return await handle_query(arguments)

            elif name == "get_aidefend_status":
                return await handle_status()

            elif name == "sync_aidefend":
                return await handle_sync()

            # P0 Tools
            elif name == "get_statistics":
                return await handle_get_statistics(arguments)

            elif name == "validate_technique_id":
                return await handle_validate_technique_id(arguments)

            elif name == "get_technique_detail":
                return await handle_get_technique_detail(arguments)

            elif name == "get_defenses_for_threat":
                return await handle_get_defenses_for_threat(arguments)

            elif name == "get_secure_code_snippet":
                return await handle_get_secure_code_snippet(arguments)

            elif name == "analyze_coverage":
                return await handle_analyze_coverage(arguments)

            elif name == "map_to_compliance_framework":
                return await handle_map_to_compliance_framework(arguments)

            elif name == "get_quick_reference":
                return await handle_get_quick_reference(arguments)

            # New Tools
            elif name == "get_threat_coverage":
                return await handle_get_threat_coverage(arguments)

            elif name == "get_implementation_plan":
                return await handle_get_implementation_plan(arguments)

            elif name == "classify_threat":
                return await handle_classify_threat(arguments)

            else:
                raise ValueError(f"Unknown tool: {name}")

        except Exception as e:
            logger.error(f"Error handling tool call '{name}': {e}", exc_info=True)
            return [TextContent(
                type="text",
                text=f"Error: {str(e)}\n\nPlease try again or check the service logs for details."
            )]

    # Initialize services before accepting connections (prevents cold start timeout)
    try:
        logger.info("Initializing query engine for MCP...")
        await query_engine.initialize()

        logger.info("Triggering initial sync check for MCP...")
        asyncio.create_task(run_sync())

        logger.info("MCP services initialized. Ready for connections.")

    except Exception as e:
        logger.error(f"MCP startup initialization failed: {e}", exc_info=True)
        # Continue anyway - tools will handle QueryEngineNotInitializedError

    # Run the MCP server
    logger.info("Starting MCP server on stdio...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


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
        return [TextContent(
            type="text",
            text="Error: Query text cannot be empty. Please provide a search query."
        )]

    # Validate top_k
    if not isinstance(top_k, (int, float)):
        top_k = 5
    top_k = max(1, min(int(top_k), 20))

    try:
        # Validate input and create request
        # (This may raise InputValidationError or SecurityError)
        request = QueryRequest(query_text=query_text, top_k=top_k)

        logger.info(f"MCP query: '{query_text[:50]}...' (top_k={top_k})")

        # Use the same QueryEngine as REST API
        results = await query_engine.search(request)

        if not results:
            return [TextContent(
                type="text",
                text=(
                    f"No results found for query: '{query_text}'\n\n"
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
        return [TextContent(
            type="text",
            text=f"Invalid query: {str(e)}\n\nPlease check your input and try again."
        )]

    # Handle service not ready errors
    except QueryEngineNotInitializedError as e:
        logger.error(f"MCP query failed, engine not ready: {e}")
        return [TextContent(
            type="text",
            text=(
                f"Service not ready: {str(e)}\n\n"
                "The knowledge base may not be initialized yet.\n"
                "Try running 'sync_aidefend' first to download and index the AIDEFEND framework."
            )
        )]

    # Handle all other errors
    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        return [TextContent(
            type="text",
            text=f"Query failed: {str(e)}\n\nPlease check the service status or try again."
        )]


async def handle_status() -> List[TextContent]:
    """
    Handle get_aidefend_status tool call.

    Returns:
        List of TextContent with service status information
    """
    logger.info("MCP status request")

    try:
        stats = await query_engine.get_stats()

        status_text = (
            "# AIDEFEND Knowledge Base Status\n\n"
            f"**Initialization Status:** {'✅ Ready' if stats['initialized'] else '❌ Not Ready'}\n"
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
                "Use `query_aidefend` to search for AI defense strategies."
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
        return [TextContent(
            type="text",
            text=f"Failed to get status: {str(e)}"
        )]


async def handle_sync() -> List[TextContent]:
    """
    Handle sync_aidefend tool call.

    Returns:
        List of TextContent with sync result
    """
    logger.info("MCP sync request")

    sync_text = (
        "# Starting AIDEFEND Knowledge Base Sync\n\n"
        "Synchronizing with GitHub repository...\n"
        "This may take a few minutes.\n\n"
    )

    try:
        success = await run_sync()

        if success:
            sync_text += (
                "**✅ Sync Completed Successfully!**\n\n"
                "The knowledge base has been updated with the latest defense tactics.\n"
                "You can now query for AI security strategies using `query_aidefend`."
            )
        else:
            error = get_last_sync_error() or "Unknown error"
            sync_text += (
                f"**❌ Sync Failed**\n\n"
                f"Error: {error}\n\n"
                "Please check:\n"
                "- Internet connection\n"
                "- GitHub repository access\n"
                "- Service logs for details"
            )

        return [TextContent(type="text", text=sync_text)]

    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        return [TextContent(
            type="text",
            text=f"**❌ Sync Failed**\n\nError: {str(e)}"
        )]


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
    output += f"**Query:** {query}\n"
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
        output += f"**Total Documents:** {result['overview']['total_documents']}\n"
        output += f"**Techniques:** {result['overview']['total_techniques']}\n"
        output += f"**Sub-techniques:** {result['overview']['total_subtechniques']}\n"
        output += f"**Strategies:** {result['overview']['total_strategies']}\n\n"

        output += "## Coverage by Tactic\n\n"
        for tactic, count in result['by_tactic'].items():
            output += f"- **{tactic}:** {count}\n"

        output += "\n## Threat Framework Coverage\n\n"
        tfc = result['threat_framework_coverage']
        output += f"- **OWASP LLM Items:** {tfc['owasp_llm_items_covered']}\n"
        output += f"- **MITRE ATLAS Items:** {tfc['mitre_atlas_items_covered']}\n"
        output += f"- **Coverage:** {tfc['coverage_percentage']}%\n"

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
        output += f"**Type:** {tech['type']}\n\n"

        output += "## Description\n\n"
        output += tech['description'] + "\n\n"

        if tech.get('defends_against'):
            output += "## Defends Against\n\n"
            for fw in tech['defends_against']:
                output += f"### {fw['framework']}\n"
                for item in fw['items'][:5]:
                    output += f"- {item}\n"
                output += "\n"

        if tech.get('tools') and include_tools:
            output += "## Tools\n\n"
            if tech['tools'].get('opensource'):
                output += "**Open Source:**\n"
                for tool in tech['tools']['opensource'][:5]:
                    output += f"- {tool}\n"
                output += "\n"

        if result['subtechniques']:
            output += f"## Sub-Techniques ({len(result['subtechniques'])})\n\n"
            for st in result['subtechniques'][:10]:
                output += f"### {st['id']}: {st['name']}\n"
                output += f"- **Pillar:** {st['pillar']}\n"
                output += f"- **Phase:** {st['phase']}\n\n"

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
        output += f"**Query:** {query.get('threat_id') or query.get('threat_keyword')}\n"
        output += f"**Results:** {result['total_results']}\n\n"

        for i, tech in enumerate(result['defense_techniques'][:10], 1):
            output += f"## {i}. {tech['technique']['name']}\n\n"
            output += f"**ID:** {tech['technique']['id']}\n"
            output += f"**Tactic:** {tech['technique']['tactic']}\n"
            output += f"**Relevance:** {tech['relevance_score']:.2f}\n\n"

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
        output += f"**Query:** {result['query']}\n"
        output += f"**Snippets Found:** {result['total_snippets']}\n\n"

        for i, snippet in enumerate(result['code_snippets'], 1):
            output += f"## Snippet {i}: {snippet['technique_name']}\n\n"
            output += f"**Technique ID:** {snippet['technique_id']}\n"
            output += f"**Language:** {snippet['language']}\n"
            output += f"**Strategy:** {snippet['strategy']}\n\n"
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
        output += f"**Total Mapped:** {result['total_mapped']}\n\n"

        for mapping in result['mappings']:
            output += f"## {mapping['technique_id']}: {mapping['technique_name']}\n\n"
            output += f"**Framework Controls:**\n"
            for control in mapping['framework_controls']:
                output += f"- {control}\n"
            output += f"\n**Confidence:** {mapping['mapping_confidence']}\n\n"

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
            result_summary=f"{result['valid_count']}/{result['input_count']} valid, OWASP: {len(result['covered']['owasp'])}, ATLAS: {len(result['covered']['atlas'])}"
        )

        output = "# Threat Coverage Analysis\n\n"
        output += f"**Techniques Analyzed:** {result['input_count']}\n"
        output += f"**Valid Techniques:** {result['valid_count']}\n"
        output += f"**Invalid Techniques:** {result['invalid_count']}\n\n"

        if result['invalid_techniques']:
            output += "## Invalid Technique IDs\n\n"
            for tech_id in result['invalid_techniques']:
                output += f"- {tech_id}\n"
            output += "\n"

        output += "## Threat Coverage by Framework\n\n"
        output += f"### OWASP LLM Top 10\n"
        output += f"**Coverage:** {result['coverage_rate']['owasp'] * 100:.1f}% ({len(result['covered']['owasp'])}/10)\n"
        if result['covered']['owasp']:
            output += f"**Threats Covered:** {', '.join(result['covered']['owasp'])}\n"
        output += "\n"

        output += f"### MITRE ATLAS\n"
        output += f"**Coverage:** {result['coverage_rate']['atlas'] * 100:.1f}% ({len(result['covered']['atlas'])}/43)\n"
        if result['covered']['atlas']:
            output += f"**Threats Covered:** {', '.join(result['covered']['atlas'][:10])}"
            if len(result['covered']['atlas']) > 10:
                output += f" ... +{len(result['covered']['atlas']) - 10} more"
            output += "\n"
        output += "\n"

        output += "## Coverage by Technique\n\n"
        for tech_data in result['by_technique'][:10]:
            output += f"### {tech_data['technique_id']}: {tech_data['technique_name']}\n"
            owasp_threats = tech_data['threats_covered']['owasp']
            atlas_threats = tech_data['threats_covered']['atlas']
            if owasp_threats:
                output += f"- **OWASP:** {', '.join(owasp_threats)}\n"
            if atlas_threats:
                output += f"- **ATLAS:** {', '.join(atlas_threats)}\n"
            output += "\n"

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

        result = await get_implementation_plan(
            implemented_techniques=implemented_techniques,
            exclude_tactics=exclude_tactics,
            top_k=top_k
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{len(result['recommendations'])} recommendations, {len(result['categories']['quick_wins'])} quick wins"
        )

        output = "# Defense Implementation Plan\n\n"
        output += f"**Implemented Techniques:** {result['input']['implemented_count']}\n"
        if result['input']['exclude_tactics']:
            output += f"**Excluded Tactics:** {', '.join(result['input']['exclude_tactics'])}\n"
        output += f"**Recommendations Generated:** {len(result['recommendations'])}\n\n"

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
            output += "\n"

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
            result_summary=f"{len(result['keywords_found'])} keywords matched, OWASP: {len(result['normalized_threats']['owasp'])}, ATLAS: {len(result['normalized_threats']['atlas'])}"
        )

        output = "# Threat Classification Results\n\n"

        # Display classification source/tier
        source = result.get('source', 'unknown')
        source_labels = {
            'static_keyword': '🔍 Static Keyword Match (Tier 1)',
            'fuzzy_match': '🔎 Fuzzy Match - Typo Tolerant (Tier 2)',
            'llm_inferred': '🤖 LLM Semantic Inference (Tier 3)',
            'no_match': '❌ No Match Found'
        }
        output += f"**Classification Source:** {source_labels.get(source, source)}\n"
        output += f"**Input Text:** {result['input_text_preview']}\n"
        output += f"**Keywords Matched:** {len(result['keywords_found'])}\n\n"

        if result['keywords_found']:
            output += "## Matched Keywords\n\n"
            for kw in result['keywords_found']:
                confidence_emoji = "🟢" if kw['confidence'] >= 0.85 else "🟡" if kw['confidence'] >= 0.7 else "🟠"
                match_type_label = "Primary" if kw['match_type'] == "primary" else "Alias"
                output += f"{confidence_emoji} **{kw['keyword'].title()}** ({match_type_label}, confidence: {kw['confidence']})\n"
            output += "\n"

        output += "## Normalized Threat IDs\n\n"
        if result['normalized_threats']['owasp']:
            output += f"**OWASP LLM Top 10:** {', '.join(result['normalized_threats']['owasp'])}\n"
        if result['normalized_threats']['atlas']:
            output += f"**MITRE ATLAS:** {', '.join(result['normalized_threats']['atlas'])}\n"
        if result['normalized_threats']['maestro']:
            output += f"**MAESTRO:** {', '.join(result['normalized_threats']['maestro'])}\n"

        if not any(result['normalized_threats'].values()):
            output += "*No threat IDs identified*\n"
        output += "\n"

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
        elif source == 'llm_inferred':
            output += "*Note: LLM semantic inference used. Result based on AI understanding of context.*\n"
        else:
            output += "*Note: No threats matched. Consider rephrasing or check if threat is in keyword dictionary.*\n"

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
