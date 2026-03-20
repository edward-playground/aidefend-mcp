"""
AIDEFEND MCP Service - Unified Entry Point

This module provides a unified entry point for running the AIDEFEND service
in either REST API mode or MCP (Model Context Protocol) mode.

Usage:
    C:/Python313/python.exe __main__.py              # REST API mode (default)
    C:/Python313/python.exe __main__.py --mcp        # MCP mode for Claude Desktop
    C:/Python313/python.exe __main__.py --help       # Show help message
"""

import sys
import asyncio


def print_help():
    """Print usage information."""
    help_text = """
AIDEFEND MCP Service - AI Security Defense Knowledge Base

USAGE:
    C:/Python313/python.exe __main__.py [OPTIONS]

OPTIONS:
    (no options)    Start REST API server (default mode)
                    - Access at: http://127.0.0.1:8000
                    - API docs: http://127.0.0.1:8000/docs
                    - Health check: http://127.0.0.1:8000/api/v1/health

    --mcp           Start MCP server for Claude Desktop
                    - Uses stdio transport (standard input/output)
                    - Configure in Claude Desktop's config.json
                    - See INSTALL.md for setup instructions

    --force-resync  Delete existing database and force a fresh sync
                    - Deletes data/aidefend_kb.lancedb and data/local_version.json
                    - Then starts REST API server with fresh sync
                    - Use this when upgrading embedding models

    --help, -h      Show this help message

EXAMPLES:
    # Start REST API server (for system integration)
    C:/Python313/python.exe __main__.py

    # Start MCP server (for Claude Desktop)
    C:/Python313/python.exe __main__.py --mcp

    # Force resync (when upgrading embedding models)
    C:/Python313/python.exe __main__.py --force-resync

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
    3. Force resync mode: Delete database and start fresh

    The mode is selected via command-line argument.
    """
    # Handle force-resync first (cleanup, then continue to REST API mode)
    if len(sys.argv) > 1 and sys.argv[1].lower() == "--force-resync":
        print("🔄 Force Re-sync Mode", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("This will delete the existing database and force a fresh sync.", file=sys.stderr)
        print("Use this when upgrading embedding models or fixing database issues.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        try:
            from app.config import settings
            import shutil

            # Delete LanceDB database
            if settings.DB_PATH.exists():
                print(f"✓ Deleting database: {settings.DB_PATH}", file=sys.stderr)
                shutil.rmtree(settings.DB_PATH)
            else:
                print(f"  Database not found (already clean): {settings.DB_PATH}", file=sys.stderr)

            # Delete version file
            if settings.VERSION_FILE.exists():
                print(f"✓ Deleting version file: {settings.VERSION_FILE}", file=sys.stderr)
                settings.VERSION_FILE.unlink()
            else:
                print(f"  Version file not found (already clean): {settings.VERSION_FILE}", file=sys.stderr)

            print("=" * 60, file=sys.stderr)
            print("✅ Cleanup complete! Starting fresh sync...", file=sys.stderr)
            print("=" * 60, file=sys.stderr)

        except Exception as e:
            print(f"❌ Error during cleanup: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)

        # Continue to REST API mode below (will trigger automatic sync)

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
                sys.exit(0)

            except KeyboardInterrupt:
                print("\nMCP Server stopped by user", file=sys.stderr)
                sys.exit(0)
            except Exception as e:
                print(f"MCP Server error: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc(file=sys.stderr)
                sys.exit(1)

        # Force resync already handled above, fall through to REST API mode
        elif arg == "--force-resync":
            pass  # Already handled above, will start REST API below

        # Unknown argument
        else:
            print(f"Error: Unknown argument '{sys.argv[1]}'", file=sys.stderr)
            print("Use --help to see available options", file=sys.stderr)
            sys.exit(1)

    # Start REST API server (default mode, also runs after --force-resync)
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
