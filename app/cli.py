"""
AIDEFEND MCP Service - Command-line entry point.

This module provides a unified entry point for running the AIDEFEND service
in either REST API mode or MCP (Model Context Protocol) mode.

It lives in a normally-named module (app.cli) rather than __main__ so that the
installed console script (``aidefend-mcp``) resolves ``app.cli:main`` cleanly. Installing a
top-level module literally named ``__main__`` collides with the console-script launcher,
which itself runs as ``__main__`` at import time. The repo-root ``__main__.py`` is a thin
shim that calls ``main()`` here, so ``python __main__.py [--mcp|--resync]`` still works.

Usage:
    aidefend-mcp                    # Installed package, REST API mode
    aidefend-mcp --mcp              # Installed package, MCP mode
    python __main__.py --help       # Source checkout compatibility shim
"""

import asyncio
import sys
from pathlib import Path


def _invocation_command() -> str:
    """Return the documented launcher for the current execution context."""
    if Path(sys.argv[0]).name.casefold() == "__main__.py":
        return "python __main__.py"
    return "aidefend-mcp"


def print_help():
    """Print usage information."""
    command = _invocation_command()
    help_text = f"""
AIDEFEND MCP Service - AI Security Defense Knowledge Base

USAGE:
    {command} [OPTIONS]

LAUNCHERS:
    Installed package: aidefend-mcp [OPTIONS]
    Source checkout:   python __main__.py [OPTIONS]

OPTIONS:
    (no options)    Start REST API server (default mode)
                    - Access at: http://127.0.0.1:8000
                    - API docs: http://127.0.0.1:8000/docs
                    - Health check: http://127.0.0.1:8000/health

    --api           Start REST API server (explicit, same as no options)
                    - Use this for clarity in documentation or scripts

    --mcp           Start MCP server for Claude Desktop
                    - Uses stdio transport (standard input/output)
                    - Configure in Claude Desktop's config.json
                    - See INSTALL.md for setup instructions

    --resync        Safely rebuild the database from the configured source
                    - Builds and validates a replacement before switching tables
                    - Keeps the current database and version metadata during staging
                    - Then exits (you can then start any mode)
                    - Use this when upgrading embedding models or repairing the index

    --force         Deprecated compatibility flag for --resync
                    - Lock files are never deleted or overridden
                    - Resync already performs a validated forced rebuild

    --help, -h      Show this help message

EXAMPLES:
    # Start REST API server (for system integration)
    {command}

    # Start MCP server (for Claude Desktop)
    {command} --mcp

    # Resync database (when upgrading embedding models)
    {command} --resync

ENVIRONMENT:
    Configuration is loaded from .env file (see .env.example)

DOCUMENTATION:
    - README.md: Project overview and features
    - INSTALL.md: Installation and configuration guide
    - GitHub: https://github.com/edward-playground/aidefend-mcp

For more information, visit the documentation or run the service with --help.
"""
    print(help_text)


def check_for_running_server() -> bool:
    """
    Check if MCP server or other instance is currently running.

    Uses the stable cross-process DATA_PATH ownership lease.

    Returns:
        True if server is running, False otherwise
    """
    from app.config import settings

    # File existence is not ownership; the OS lock state is authoritative.
    lock_file = settings.DATA_PATH / "sync.lock"
    if lock_file.exists():
        try:
            from app.instance_lock import is_lock_file_held_by_other_process

            if is_lock_file_held_by_other_process(lock_file):
                return True
        except Exception as exc:
            # If we cannot prove the path is free, fail closed.
            print(f"Warning: could not inspect sync lock state: {exc}", file=sys.stderr)
            return True

    return False


def main():
    """
    Main entry point for AIDEFEND MCP Service.

    Supports multiple modes:
    1. REST API mode (default or --api): FastAPI server for HTTP queries
    2. MCP mode (--mcp): stdio-based server for Claude Desktop integration
    3. Resync mode (--resync): Safely rebuild from the configured source

    The mode is selected via command-line argument.
    """
    command = _invocation_command()

    # Handle resync first (staged rebuild, then exit)
    if len(sys.argv) > 1 and sys.argv[1].lower() == "--resync":
        print("🔄 Database Resync Mode", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("This will build a fresh index and switch to it after validation.", file=sys.stderr)
        print("The current database and version metadata remain in place during staging.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        # Retained only for command-line compatibility. It never bypasses or
        # deletes the stable ownership lease.
        force_mode = len(sys.argv) > 2 and sys.argv[2].lower() == "--force"
        if force_mode:
            print(
                "Note: --force is deprecated; --resync already performs the "
                "safe forced rebuild.",
                file=sys.stderr,
            )

        service_lock_acquired = False
        try:
            # An advisory probe gives a useful error, then the atomic lease
            # acquisition below closes the check/acquire race.
            if check_for_running_server():
                print("\n" + "=" * 60, file=sys.stderr)
                print("⚠️  ERROR: AIDEFEND MCP Server is currently running!", file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                print("\nResync requires exclusive access to the database.", file=sys.stderr)
                print("Please stop all running instances first:\n", file=sys.stderr)
                print("  1. Close Claude Desktop (or other MCP clients)", file=sys.stderr)
                print("  2. Wait 5-10 seconds for graceful shutdown", file=sys.stderr)
                print(f"  3. Run resync again: {command} --resync\n", file=sys.stderr)
                sys.exit(1)

            from app.sync import (
                _acquire_sync_lock,
                _release_sync_lock,
                acquire_service_instance_lock,
                release_service_instance_lock,
            )

            service_lock_acquired = acquire_service_instance_lock()
            if not service_lock_acquired:
                print(
                    "Another AIDEFEND process acquired DATA_PATH; resync aborted.",
                    file=sys.stderr,
                )
                sys.exit(1)

            lock_acquired = asyncio.run(_acquire_sync_lock())
            if not lock_acquired:
                print("=" * 60, file=sys.stderr)
                print("❌ Failed to acquire lock. Another sync may be in progress.", file=sys.stderr)
                print("=" * 60, file=sys.stderr)

                print("\nAnother sync or recovery is already running.", file=sys.stderr)
                print("Stop the owner or wait; --force never overrides the lease.\n", file=sys.stderr)
                sys.exit(1)

            try:
                # Step 4: Build into the sync pipeline's temporary table. Do not
                # delete the live database or version metadata first: core_sync()
                # performs the validated blue-green table swap and writes version
                # metadata only after the rebuilt query engine is ready.
                print("=" * 60, file=sys.stderr)
                print("Starting staged database rebuild...", file=sys.stderr)
                print("The current database remains available until table swap.", file=sys.stderr)
                print("=" * 60, file=sys.stderr)

                # Run sync WHILE holding the lock (prevents race conditions)
                # This ensures users see progress in the same terminal
                print("", file=sys.stderr)
                print("📊 Running forced rebuild (this will take 5-15 minutes)...", file=sys.stderr)
                print("=" * 60, file=sys.stderr)

                # Import the cancellation-safe worker boundary. The CLI owns
                # the outer service and operation leases until this drains.
                import logging

                from app.logger import setup_logger
                from app.sync import _run_cli_sync_to_completion

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

                sync_success = asyncio.run(
                    _run_cli_sync_to_completion(force_rebuild=True)
                )

                print("", file=sys.stderr)

                if not sync_success:
                    from app.sync import get_last_sync_error
                    last_error = get_last_sync_error()

                    print("=" * 60, file=sys.stderr)
                    print("❌ Database rebuild failed!", file=sys.stderr)
                    if last_error:
                        print(f"   Error: {last_error}", file=sys.stderr)
                    print("   The existing version metadata was not removed by this command.", file=sys.stderr)
                    print("   Check data/logs/aidefend_mcp.log for details", file=sys.stderr)
                    print("=" * 60, file=sys.stderr)
                    sys.exit(1)

                print("=" * 60, file=sys.stderr)
                print("✅ Sync complete!", file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                print("", file=sys.stderr)
                print("You can now start the service with:", file=sys.stderr)
                print(f"  • MCP mode:      {command} --mcp", file=sys.stderr)
                print(f"  • REST API mode: {command} --api", file=sys.stderr)
                print("", file=sys.stderr)
                sys.exit(0)

            finally:
                # Release only the process-local operation boundary here; the
                # outer finally retains DATA_PATH ownership until all handles
                # and sync work are finished.
                _release_sync_lock()

        except Exception as e:
            print(f"❌ Error during resync: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)
        finally:
            if service_lock_acquired:
                # The CLI sync/close pair completes inside one asyncio runner;
                # only then may this synchronous lifetime lease be released.
                release_service_instance_lock()

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

        # --resync already handled above (exits after sync)
        # --api falls through to REST API startup below
        elif arg in ["--resync", "--api"]:
            pass

        # Unknown argument
        else:
            print(f"Error: Unknown argument '{sys.argv[1]}'", file=sys.stderr)
            print("Use --help to see available options", file=sys.stderr)
            sys.exit(1)

    try:
        import uvicorn

        from app.config import settings
        from app.main import app

        # Default: REST API mode (also reached via --api). Report the effective
        # validated settings so operators do not probe the wrong socket after
        # overriding API_HOST or API_PORT.
        url_host = settings.API_HOST
        if ":" in url_host and not url_host.startswith("["):
            url_host = f"[{url_host}]"
        base_url = f"http://{url_host}:{settings.API_PORT}"
        print("Starting AIDEFEND REST API Server...", file=sys.stderr)
        print(f"API will be available at: {base_url}", file=sys.stderr)
        print(f"API documentation: {base_url}/docs", file=sys.stderr)
        print("-" * 60, file=sys.stderr)

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
