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

    --api           Start REST API server (explicit, same as no options)
                    - Use this for clarity in documentation or scripts

    --mcp           Start MCP server for Claude Desktop
                    - Uses stdio transport (standard input/output)
                    - Configure in Claude Desktop's config.json
                    - See INSTALL.md for setup instructions

    --resync        Delete existing database and resync from GitHub
                    - Deletes data/aidefend_kb.lancedb and data/local_version.json
                    - Then exits (you can then start any mode)
                    - Use this when upgrading embedding models or fixing database issues

    --help, -h      Show this help message

EXAMPLES:
    # Start REST API server (for system integration)
    python __main__.py

    # Start MCP server (for Claude Desktop)
    python __main__.py --mcp

    # Resync database (when upgrading embedding models)
    python __main__.py --resync

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

    Supports multiple modes:
    1. REST API mode (default or --api): FastAPI server for HTTP queries
    2. MCP mode (--mcp): stdio-based server for Claude Desktop integration
    3. Resync mode (--resync): Delete database and resync from GitHub

    The mode is selected via command-line argument.
    """
    # Handle resync first (cleanup, then exit)
    if len(sys.argv) > 1 and sys.argv[1].lower() == "--resync":
        print("🔄 Database Resync Mode", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("This will delete the existing database and force a fresh sync.", file=sys.stderr)
        print("Use this when upgrading embedding models or fixing database issues.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        try:
            from app.config import settings
            import shutil

            # Delete LanceDB database
            if settings.DB_PATH.exists():
                print(f"✓ Deleting database: {settings.DB_PATH.name}", file=sys.stderr)
                shutil.rmtree(settings.DB_PATH)
            else:
                print(f"  Database not found (already clean): {settings.DB_PATH.name}", file=sys.stderr)

            # Delete version file
            if settings.VERSION_FILE.exists():
                print(f"✓ Deleting version file: {settings.VERSION_FILE.name}", file=sys.stderr)
                settings.VERSION_FILE.unlink()
            else:
                print(f"  Version file not found (already clean): {settings.VERSION_FILE.name}", file=sys.stderr)

            print("=" * 60, file=sys.stderr)
            print("✅ Cleanup complete! Starting fresh sync...", file=sys.stderr)
            print("=" * 60, file=sys.stderr)

            # Run sync BEFORE starting the server
            # This ensures users see progress in the same terminal
            print("", file=sys.stderr)
            print("📊 Running initial sync (this will take 5-15 minutes)...", file=sys.stderr)
            print("=" * 60, file=sys.stderr)

            # Import sync function
            from app.sync import run_sync
            from app.logger import setup_logger
            import logging

            # Setup logging with console output
            setup_logger()

            # Add console handler to show progress in terminal
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)

            # Configure root logger to show INFO messages
            # All child loggers (including 'app.sync') will inherit this configuration
            root_logger = logging.getLogger()
            root_logger.setLevel(logging.INFO)  # Set root logger level to INFO
            root_logger.addHandler(console_handler)

            print("", file=sys.stderr)

            # Run sync synchronously
            sync_success = asyncio.run(run_sync())

            print("", file=sys.stderr)

            if not sync_success:
                from app.sync import get_last_sync_error
                last_error = get_last_sync_error()
                
                print("=" * 60, file=sys.stderr)
                print("❌ Initial sync failed!", file=sys.stderr)
                if last_error:
                    print(f"   Error: {last_error}", file=sys.stderr)
                print("   Check data/logs/aidefend_mcp.log for details", file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                sys.exit(1)

            print("=" * 60, file=sys.stderr)
            print("✅ Sync complete!", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            print("", file=sys.stderr)
            print("You can now start the service with:", file=sys.stderr)
            print("  • MCP mode:      python __main__.py --mcp", file=sys.stderr)
            print("  • REST API mode: python __main__.py --api", file=sys.stderr)
            print("", file=sys.stderr)
            sys.exit(0)

        except Exception as e:
            print(f"❌ Error during resync: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)

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

        # REST API mode (explicit)
        elif arg == "--api":
            pass  # Fall through to default REST API mode below

        # Resync already handled above
        elif arg == "--resync":
            pass  # Already handled above, exited after sync

        # Unknown argument
        else:
            print(f"Error: Unknown argument '{sys.argv[1]}'", file=sys.stderr)
            print("Use --help to see available options", file=sys.stderr)
            sys.exit(1)

    # Default: REST API mode
    else:
        try:
            # Import config first to trigger validation
            from app.config import settings

            # Print startup banner
            print("Starting AIDEFEND REST API Server...", file=sys.stderr)
            print(f"API will be available at: http://{settings.API_HOST}:{settings.API_PORT}", file=sys.stderr)
            print(f"API documentation: http://{settings.API_HOST}:{settings.API_PORT}/docs", file=sys.stderr)
            print("-" * 60, file=sys.stderr)

            # Security warning for no_auth mode
            if settings.AUTH_MODE == "no_auth":
                print("", file=sys.stderr)
                print("=" * 70, file=sys.stderr)
                print("⚠️  WARNING: Running in NO AUTHENTICATION mode", file=sys.stderr)
                print("=" * 70, file=sys.stderr)
                print("", file=sys.stderr)
                print("  Authentication is DISABLED. This mode is only suitable for:", file=sys.stderr)
                print("    - Local development on 127.0.0.1 (localhost)", file=sys.stderr)
                print("    - Trusted private networks", file=sys.stderr)
                print("    - Personal use on your own machine", file=sys.stderr)
                print("", file=sys.stderr)
                print("  For production deployment:", file=sys.stderr)
                print("    1. Set AUTH_MODE=api_key in .env", file=sys.stderr)
                print("    2. Generate API key: python scripts/generate_api_key.py", file=sys.stderr)
                print("    3. Set AIDEFEND_API_KEY in .env", file=sys.stderr)
                print("", file=sys.stderr)
                print("  See SECURITY.md for deployment best practices.", file=sys.stderr)
                print("=" * 70, file=sys.stderr)
                print("", file=sys.stderr)
            elif settings.AUTH_MODE == "api_key":
                print("", file=sys.stderr)
                print("🔒 Authentication: API Key mode enabled", file=sys.stderr)
                print("   Clients must provide X-API-Key header", file=sys.stderr)
                print("", file=sys.stderr)

            # Import and run FastAPI server
            import uvicorn
            from app.main import app

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
