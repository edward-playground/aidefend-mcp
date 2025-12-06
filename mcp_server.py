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
from app.utils import load_version_info
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
    get_quick_reference,
    comprehensive_search,
    analyze_security_posture,
    compare_techniques,
    generate_incident_playbook
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
        logger.error(f"Critical: Failed to ensure database ready: {e}")
        # This is a fatal error - cannot start without database
        raise RuntimeError("Database initialization/repair failed - cannot start MCP server")

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
                            "type": "number",
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
                            "type": "number",
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
                    "- Threat coverage: OWASP/ATLAS/MAESTRO frameworks coverage rates\n"
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

            elif name == "comprehensive_search":
                return await handle_comprehensive_search(arguments)

            elif name == "analyze_security_posture":
                return await handle_analyze_security_posture(arguments)

            elif name == "compare_techniques":
                return await handle_compare_techniques(arguments)

            elif name == "generate_incident_playbook":
                return await handle_generate_incident_playbook(arguments)

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
            # Warm start - database exists, trigger background sync to check for updates
            logger.info("Warm start detected (database exists)")
            logger.info("Triggering background sync check for updates...")
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
            commit_sha = version_info.get("commit_sha", "N/A")
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
                    f"**Git Commit:** {commit_sha[:8] if len(commit_sha) >= 8 else commit_sha}\n"
                    f"**Last Synced:** {last_synced}\n"
                )
            else:
                status_text += (
                    f"**Framework Version:** ⚠️ Not available\n"
                    f"**Git Commit:** {commit_sha[:8] if len(commit_sha) >= 8 else commit_sha}\n"
                    f"**Last Synced:** {last_synced}\n"
                )
        elif stats.get('framework_version'):
            # Fallback to stats if version_info not available
            status_text += f"**Framework Version:** {stats['framework_version']}\n"

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
        return [TextContent(
            type="text",
            text=f"Failed to get status: {str(e)}"
        )]


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

    sync_text = (
        "# Starting AIDEFEND Knowledge Base Sync\n\n"
        "Synchronizing with GitHub repository...\n"
        "This may take a few minutes.\n\n"
    )

    try:
        # run_sync() handles lock acquisition/release and calls core_sync()
        success = await run_sync()

        if success:
            sync_text += (
                "**✅ Sync Completed Successfully!**\n\n"
                "The knowledge base has been updated with the latest defense tactics.\n\n"
                "⏳ **Query engine is reloading...** (takes ~2-3 seconds)\n"
                "Please wait briefly before using `query_aidefend`.\n\n"
                "💡 Tip: Use `get_aidefend_status` to verify the service is ready."
            )
        else:
            error = get_last_sync_error() or "Unknown error - check logs for details"
            sync_text += (
                f"**❌ Sync Failed**\n\n"
                f"{error}\n"
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
        output += f"- **OWASP LLM Items:** {tfc['owasp_llm_items_covered']}/{tfc.get('owasp_llm_total_items', 10)} ({tfc.get('owasp_llm_coverage_percentage', 0)}%)\n"
        output += f"- **MITRE ATLAS Items:** {tfc['mitre_atlas_items_covered']}\n"
        output += f"- **MAESTRO Items:** {tfc.get('maestro_items_covered', 0)}\n"
        output += f"- **Techniques with Threat Mappings:** {tfc.get('techniques_with_threat_mappings', 0)} ({tfc.get('techniques_mapped_percentage', 0)}%)\n"

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
        output += f"**Framework Version:** {result['framework'].get('version', 'N/A')}\n"
        output += f"**Total Techniques Mapped:** {result['total_mapped']}\n\n"

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
        output += f"**Topic:** {result['input_topic']}\n"
        output += f"**Search Strategy:** Multi-query ({len(result['queries_executed'])} queries executed)\n"
        output += f"**Total Results:** {result['total_results_after_dedup']} (deduplicated from {result['total_results_before_dedup']})\n\n"

        output += "## Queries Executed\n\n"
        for i, query in enumerate(result['queries_executed'], 1):
            output += f"{i}. {query}\n"
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
                output += f"**Matched Query:** {item['matched_query']}\n"

                if item.get('pillar'):
                    output += f"**Pillar:** {item['pillar']}\n"
                if item.get('phase'):
                    output += f"**Phase:** {item['phase']}\n"

                output += f"\n**Description:**\n{item['description'][:300]}...\n\n"
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
            pct = result['technical_coverage'].get('overall_coverage', {}).get('percentage', 0)
            summary_text = f"Technical: {pct:.1f}%"
        elif view == "threat" and result.get("threat_coverage"):
            owasp = result['threat_coverage'].get('coverage_rate', {}).get('owasp', 0)
            summary_text = f"OWASP: {owasp:.1f}%"
        else:
            summary_text = "Analysis complete"

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=summary_text
        )

        # Format output
        output = "# Security Posture Analysis\n\n"
        output += f"**View:** {view.title()}\n"
        output += f"**Techniques Analyzed:** {result['implemented_count']}\n"
        if system_type:
            output += f"**System Type:** {system_type}\n"
        output += "\n"

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
        if view in ["both", "technical"] and result.get("technical_coverage"):
            tech = result["technical_coverage"]
            output += "## Technical Coverage\n\n"

            # Fix: Use correct key 'analysis_summary' instead of 'overall_coverage'
            overall = tech.get("analysis_summary", {})
            output += f"**Coverage:** {overall.get('coverage_percentage', 0):.1f}% "
            output += f"({overall.get('coverage_level', 'unknown')})\n"
            output += f"**Implemented:** {overall.get('techniques_implemented', 0)}/{overall.get('total_techniques_available', 0)} techniques\n\n"

            # By Tactic - Fix: Use 'coverage_by_tactic' and convert dict to list
            coverage_by_tactic = tech.get("coverage_by_tactic", {})
            if coverage_by_tactic:
                output += "### Coverage by Tactic\n\n"
                # Convert dict to sorted list (by percentage descending)
                tactic_list = [
                    {"tactic": tactic, **stats}
                    for tactic, stats in coverage_by_tactic.items()
                ]
                for tactic_info in sorted(tactic_list, key=lambda x: -x["percentage"]):
                    emoji = "❌" if tactic_info["percentage"] == 0 else "🟡"
                    output += f"{emoji} **{tactic_info['tactic']}:** {tactic_info['percentage']:.1f}% "
                    output += f"({tactic_info['implemented']}/{tactic_info['total']})\n"
                output += "\n"

            # Critical Gaps (gap analysis - uses 'reason' not 'technique_id')
            if tech.get("critical_gaps"):
                output += "### Critical Gaps (High Priority)\n\n"
                for gap in tech["critical_gaps"][:5]:
                    output += f"- **{gap.get('tactic', 'Unknown')}:** {gap.get('reason', 'No description')}\n"
                    if gap.get('risk'):
                        output += f"  - Risk: {gap['risk']}\n"
                output += "\n"

            # Recommendations (specific technique suggestions - uses 'technique_id')
            if tech.get("recommendations"):
                output += "### Recommended Techniques\n\n"
                for rec in tech["recommendations"][:5]:
                    output += f"- **{rec.get('technique_id', 'Unknown')}:** {rec.get('name', 'No name')}\n"
                    output += f"  - Tactic: {rec.get('tactic', 'Unknown')}\n"
                    output += f"  - Priority: {rec.get('priority', 'MEDIUM')}\n"
                    if rec.get('reason'):
                        output += f"  - Reason: {rec['reason']}\n"
                output += "\n"

        # Threat Coverage Section
        if view in ["both", "threat"] and result.get("threat_coverage"):
            threat = result["threat_coverage"]
            output += "## Threat Framework Coverage\n\n"

            coverage_rate = threat.get("coverage_rate", {})
            output += f"**OWASP LLM Top 10:** {coverage_rate.get('owasp', 0):.1f}%\n"
            output += f"**MITRE ATLAS:** {coverage_rate.get('atlas', 0):.1f}%\n"
            output += f"**MAESTRO:** {coverage_rate.get('maestro', 0):.1f}%\n\n"

            # Covered Threats
            covered = threat.get("covered_threats", {})
            if covered.get("owasp"):
                output += "### OWASP Threats Covered\n\n"
                output += f"{', '.join(covered['owasp'])}\n\n"

            # Uncovered Threats
            uncovered = threat.get("uncovered_threats", {})
            if uncovered.get("owasp"):
                output += "### OWASP Threats NOT Covered (High Priority)\n\n"
                output += f"{', '.join(uncovered['owasp'][:5])}\n\n"

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
            output += f"| **{tech['source_id']}**<br/>{tech['name'][:40]}... | "
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
                output += f"- **Threat Coverage:** OWASP ({threat_cov['owasp']}), "
                output += f"ATLAS ({threat_cov['atlas']}), MAESTRO ({threat_cov['maestro']})\n"

            # Implementation support
            if tech['has_implementation_strategies']:
                output += "- ✅ Has implementation strategies\n"
            if tech['has_code_snippets']:
                output += "- ✅ Has code examples\n"
            if tech['has_opensource_tools']:
                output += "- ✅ Opensource tools available\n"
            if tech['has_commercial_tools']:
                output += "- 💰 Commercial tools required\n"

            output += "\n"

            # Brief description
            output += f"**Description:** {tech['description']}\n\n"
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
        output += f"**Description:** {summary['description']}\n\n"

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
        if include_defense_techniques and result.get('defense_techniques'):
            defense = result['defense_techniques']
            output += "## 🛡️ Recommended Defense Techniques\n\n"

            if defense.get('techniques'):
                output += f"**Total Techniques Found:** {len(defense['techniques'])}\n\n"
                output += "### Top Defense Techniques\n\n"

                for i, tech in enumerate(defense['techniques'][:5], 1):
                    output += f"{i}. **{tech['source_id']}:** {tech['name']}\n"
                    output += f"   - **Tactic:** {tech['tactic']}\n"
                    output += f"   - **Description:** {tech['description'][:150]}...\n\n"

                output += "\n*Use `get_technique_detail` for implementation details.*\n\n"
            else:
                output += "*No specific defense techniques found. Consider using `comprehensive_search` "
                output += "to explore related defenses.*\n\n"

        # Threat classification details
        if result.get('threat_classification') and result['threat_classification'].get('matched_threats'):
            output += "## 🔍 Threat Classification Details\n\n"

            threats = result['threat_classification']['matched_threats']
            output += f"**Matched Threats:** {len(threats)}\n\n"

            for i, threat in enumerate(threats[:5], 1):
                output += f"{i}. **{threat.get('threat_id', 'N/A')}** ({threat.get('framework', 'Unknown')})\n"
                output += f"   - **Confidence:** {threat.get('confidence', 0):.1f}%\n"
                output += f"   - **Keyword Match:** {threat.get('keyword', 'N/A')}\n"
                output += f"   - **Description:** {threat.get('description', 'N/A')[:150]}...\n\n"

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
