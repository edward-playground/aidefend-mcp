"""
AIDEFEND MCP Service - Unified Entry Point

This module provides a unified entry point for running the AIDEFEND service
in either REST API mode or MCP (Model Context Protocol) mode.

Usage:
    python __main__.py              # REST API mode (default)
    python __main__.py --mcp        # MCP mode for Claude Desktop
    python __main__.py --help       # Show help message
"""

import sys
import asyncio


def print_help():
    """Print usage information."""
    help_text = """
AIDEFEND MCP Service - AI Security Defense Knowledge Base

USAGE:
    python __main__.py [OPTIONS]

OPTIONS:
    (no options)    Start REST API server (default mode)
                    - Access at: http://127.0.0.1:8000
                    - API docs: http://127.0.0.1:8000/docs
                    - Health check: http://127.0.0.1:8000/api/v1/health

    --mcp           Start MCP server for Claude Desktop
                    - Uses stdio transport (standard input/output)
                    - Configure in Claude Desktop's config.json
                    - See INSTALL.md for setup instructions

    --help, -h      Show this help message

EXAMPLES:
    # Start REST API server (for system integration)
    python __main__.py

    # Start MCP server (for Claude Desktop)
    python __main__.py --mcp

ENVIRONMENT:
    Configuration is loaded from .env file (see .env.example)

DOCUMENTATION:
    - README.md: Project overview and features
    - INSTALL.md: Installation and configuration guide
    - GitHub: https://github.com/edward-playground/aidefend-mcp

For more information, visit the documentation or run the service with --help.
"""
    print(help_text)


def main():
    """
    Main entry point for AIDEFEND MCP Service.

    Supports two modes:
    1. REST API mode (default): FastAPI server for HTTP queries
    2. MCP mode: stdio-based server for Claude Desktop integration

    The mode is selected via command-line argument.
    """
    # Parse command-line arguments
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()

        # Help command
        if arg in ["--help", "-h", "help"]:
            print_help()
            sys.exit(0)

        # MCP mode
        elif arg == "--mcp":
            print("Starting AIDEFEND MCP Server (stdio mode)...", file=sys.stderr)
            print("This server uses stdin/stdout for MCP protocol.", file=sys.stderr)
            print("Configure Claude Desktop to connect to this server.", file=sys.stderr)
            print("-" * 60, file=sys.stderr)

            try:
                # Import and run MCP server
                from mcp_server import serve
                asyncio.run(serve())

            except KeyboardInterrupt:
                print("\nMCP Server stopped by user", file=sys.stderr)
                sys.exit(0)
            except Exception as e:
                print(f"MCP Server error: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                sys.exit(1)

        # Unknown argument
        else:
            print(f"Error: Unknown argument '{sys.argv[1]}'", file=sys.stderr)
            print("Use --help to see available options", file=sys.stderr)
            sys.exit(1)

    # Default: REST API mode
    else:
        print("Starting AIDEFEND REST API Server...", file=sys.stderr)
        print("API will be available at: http://127.0.0.1:8000", file=sys.stderr)
        print("API documentation: http://127.0.0.1:8000/docs", file=sys.stderr)
        print("-" * 60, file=sys.stderr)

        try:
            # Import and run FastAPI server
            import uvicorn
            from app.main import app
            from app.config import settings

            # Run server with config from settings
            uvicorn.run(
                app,
                host=settings.API_HOST,
                port=settings.API_PORT,
                workers=settings.API_WORKERS,
                log_level=settings.LOG_LEVEL.lower()
            )

        except KeyboardInterrupt:
            print("\nREST API Server stopped by user", file=sys.stderr)
            sys.exit(0)
        except Exception as e:
            print(f"REST API Server error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
