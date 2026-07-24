"""
AIDEFEND MCP Service - Unified Entry Point (thin shim).

The real command-line logic lives in ``app.cli`` so that the installed console script can
point at a normally-named module (``app.cli:main``). Installing a top-level module literally
named ``__main__`` collides with the console-script launcher, which itself runs as
``__main__``. This shim keeps the documented ``python __main__.py [--mcp|--resync]`` flow
working when running from a source checkout.

Usage:
    python __main__.py              # REST API mode (default)
    python __main__.py --mcp        # MCP mode for Claude Desktop
    python __main__.py --help       # Show help message
"""

from app.cli import main

if __name__ == "__main__":
    main()
