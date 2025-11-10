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
            if name == "query_aidefend":
                return await handle_query(arguments)

            elif name == "get_aidefend_status":
                return await handle_status()

            elif name == "sync_aidefend":
                return await handle_sync()

            else:
                raise ValueError(f"Unknown tool: {name}")

        except Exception as e:
            logger.error(f"Error handling tool call '{name}': {e}", exc_info=True)
            return [TextContent(
                type="text",
                text=f"Error: {str(e)}\n\nPlease try again or check the service logs for details."
            )]

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
