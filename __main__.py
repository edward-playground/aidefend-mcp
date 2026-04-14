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

    --resync        Delete existing database and resync from configured source
                    - Deletes data/aidefend_kb.lancedb and data/local_version.json
                    - Then exits (you can then start any mode)
                    - Use this when upgrading embedding models or fixing database issues
                    - Requires all running services to be stopped first

    --force         Use with --resync to force cleanup even if server is running
                    - WARNING: May cause running services to crash
                    - Only use if you're sure no important operations are in progress

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


def check_for_running_server() -> bool:
    """
    Check if MCP server or other instance is currently running.

    Uses cross-process lock detection to identify if another process
    is holding the sync lock.

    Returns:
        True if server is running, False otherwise
    """
    from app.config import settings

    # Method 1: Check if lock file exists and is held by another process
    lock_file = settings.DATA_PATH / "sync.lock"
    if lock_file.exists():
        try:
            from app.sync import is_lock_held_by_other_process
            if is_lock_held_by_other_process():
                return True
        except Exception:
            # If we can't determine, assume it's safe to proceed
            pass

    return False


def main():
    """
    Main entry point for AIDEFEND MCP Service.

    Supports multiple modes:
    1. REST API mode (default or --api): FastAPI server for HTTP queries
    2. MCP mode (--mcp): stdio-based server for Claude Desktop integration
    3. Resync mode (--resync): Delete database and resync from configured source

    The mode is selected via command-line argument.
    """
    # Handle resync first (cleanup, then exit)
    if len(sys.argv) > 1 and sys.argv[1].lower() == "--resync":
        print("🔄 Database Resync Mode", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("This will delete the existing database and force a fresh sync.", file=sys.stderr)
        print("Use this when upgrading embedding models or fixing database issues.", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        # Check for --force flag
        force_mode = len(sys.argv) > 2 and sys.argv[2].lower() == "--force"

        try:
            from app.config import settings
            import shutil

            # Step 1: Check if server is running (unless --force is used)
            if not force_mode and check_for_running_server():
                print("\n" + "=" * 60, file=sys.stderr)
                print("⚠️  ERROR: AIDEFEND MCP Server is currently running!", file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                print("\nResync requires exclusive access to the database.", file=sys.stderr)
                print("Please stop all running instances first:\n", file=sys.stderr)
                print("  1. Close Claude Desktop (or other MCP clients)", file=sys.stderr)
                print("  2. Wait 5-10 seconds for graceful shutdown", file=sys.stderr)
                print("  3. Run resync again: python __main__.py --resync\n", file=sys.stderr)
                print("Alternative: Use --force flag to override (⚠️  may cause data loss):", file=sys.stderr)
                print("  python __main__.py --resync --force\n", file=sys.stderr)
                sys.exit(1)

            # Step 2: If force mode, remove lock file
            if force_mode:
                lock_file = settings.DATA_PATH / "sync.lock"
                if lock_file.exists():
                    # First check lock file age for diagnostics
                    try:
                        from datetime import datetime
                        mtime = datetime.fromtimestamp(lock_file.stat().st_mtime)
                        age = datetime.now() - mtime
                        age_seconds = age.total_seconds()
                        print(f"⚠️  Force mode: Lock file age = {age_seconds:.1f} seconds", file=sys.stderr)
                    except Exception:
                        pass

                    # Check if lock is actively held by another process
                    from app.sync import is_lock_held_by_other_process
                    if is_lock_held_by_other_process():
                        print("\n" + "=" * 60, file=sys.stderr)
                        print("❌ ERROR: Lock is actively held by another process!", file=sys.stderr)
                        print("=" * 60, file=sys.stderr)
                        print("\n--force cannot override locks held by running processes.", file=sys.stderr)
                        print("\nTo proceed safely:", file=sys.stderr)
                        print("  1. Stop the running AIDEFEND service first", file=sys.stderr)
                        print("  2. Close Claude Desktop (if using MCP mode)", file=sys.stderr)
                        print("  3. Wait 5-10 seconds for graceful shutdown", file=sys.stderr)
                        print("  4. Run resync again: python __main__.py --resync --force\n", file=sys.stderr)
                        sys.exit(1)

                    # Try to remove lock file
                    print("⚠️  Force mode: Removing lock file", file=sys.stderr)
                    try:
                        lock_file.unlink()
                        print("✓ Lock file removed", file=sys.stderr)

                        # CRITICAL: Wait for file system to fully release the lock
                        # This prevents "lock age = 0.0 seconds" bug on Windows
                        print("   Waiting for lock to fully release...", file=sys.stderr)
                        import time
                        time.sleep(2)
                        print("✓ Lock released", file=sys.stderr)

                    except PermissionError as e:
                        # Windows-specific: File is locked by OS
                        print("\n" + "=" * 60, file=sys.stderr)
                        print("❌ ERROR: Cannot remove lock file (Windows file lock)", file=sys.stderr)
                        print("=" * 60, file=sys.stderr)
                        print(f"\nError: {e}", file=sys.stderr)
                        print("\nOn Windows, locked files cannot be deleted even with --force.", file=sys.stderr)
                        print("The lock is held by another process (MCP server or sync operation).", file=sys.stderr)
                        print("\nTo proceed:", file=sys.stderr)
                        print("  1. Close all AIDEFEND instances (Claude Desktop, REST API, etc.)", file=sys.stderr)
                        print("  2. Wait 10-15 seconds", file=sys.stderr)
                        print("  3. Run resync again: python __main__.py --resync --force\n", file=sys.stderr)
                        sys.exit(1)
                    except Exception as e:
                        # Other unexpected errors
                        print("\n" + "=" * 60, file=sys.stderr)
                        print(f"❌ ERROR: Failed to remove lock file: {e}", file=sys.stderr)
                        print("=" * 60, file=sys.stderr)
                        print("\nCannot proceed with resync.\n", file=sys.stderr)
                        sys.exit(1)

            # Step 3: Acquire lock before deleting database
            from app.sync import _acquire_sync_lock, _release_sync_lock

            lock_acquired = asyncio.run(_acquire_sync_lock())
            if not lock_acquired:
                print("=" * 60, file=sys.stderr)
                print("❌ Failed to acquire lock. Another sync may be in progress.", file=sys.stderr)
                print("=" * 60, file=sys.stderr)

                if force_mode:
                    # Already using --force, so provide different guidance
                    print("\nEven with --force, cannot acquire lock.", file=sys.stderr)
                    print("This indicates an active sync operation is in progress.", file=sys.stderr)
                    print("\nPlease wait for the sync to complete, or:", file=sys.stderr)
                    print("  1. Stop all AIDEFEND instances", file=sys.stderr)
                    print("  2. Wait 10-15 seconds", file=sys.stderr)
                    print("  3. Try again\n", file=sys.stderr)
                else:
                    # Not using --force yet
                    print("\nIf you're sure no sync is running, use --force flag:", file=sys.stderr)
                    print("  python __main__.py --resync --force\n", file=sys.stderr)
                sys.exit(1)

            try:
                # Step 4: Delete database (now protected by lock)
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

                # Run sync WHILE holding the lock (prevents race conditions)
                # This ensures users see progress in the same terminal
                print("", file=sys.stderr)
                print("📊 Running initial sync (this will take 5-15 minutes)...", file=sys.stderr)
                print("=" * 60, file=sys.stderr)

                # Import sync function
                from app.sync import core_sync
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

                # Run core_sync with force_rebuild=True
                # We already hold the lock, so use core_sync() not run_sync()
                sync_success = asyncio.run(core_sync(force_rebuild=True))

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

            finally:
                # Step 5: Release lock after sync completes
                _release_sync_lock()

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

    # Default: REST API mode (also reached via --api)
    print("Starting AIDEFEND REST API Server...", file=sys.stderr)
    print("API will be available at: http://127.0.0.1:8000", file=sys.stderr)
    print("API documentation: http://127.0.0.1:8000/docs", file=sys.stderr)
    print("-" * 60, file=sys.stderr)

    try:
        import uvicorn
        from app.main import app
        from app.config import settings

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
