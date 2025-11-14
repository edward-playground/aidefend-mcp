#!/bin/bash
# Quick start script for AIDEFEND MCP Service
# Supports both REST API mode and MCP mode

set -e

# Parse command-line arguments
MODE="api"  # Default mode
if [ "$1" = "--mcp" ] || [ "$1" = "-m" ]; then
    MODE="mcp"
elif [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "AIDEFEND MCP Service - Quick Start Script"
    echo ""
    echo "Usage: ./start.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  (no options)    Start in REST API mode (default)"
    echo "  --mcp, -m       Start in MCP mode for Claude Desktop"
    echo "  --help, -h      Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./start.sh           # Start REST API server"
    echo "  ./start.sh --mcp     # Start MCP server"
    exit 0
fi

echo "=========================================="
if [ "$MODE" = "mcp" ]; then
    echo "AIDEFEND MCP Service - MCP Mode"
else
    echo "AIDEFEND MCP Service - REST API Mode"
fi
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "✓ Python $python_version"

# Create .env if not exists
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ .env created"
else
    echo "✓ .env already exists"
fi

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python -m venv venv
    echo "✓ Virtual environment created"

    echo ""
    echo "Activating virtual environment..."
    source venv/bin/activate || . venv/Scripts/activate

    echo ""
    echo "Installing Python dependencies (this may take a few minutes)..."
    pip install -r requirements.txt
    echo "✓ Python dependencies installed"
else
    echo "✓ Virtual environment exists"
    source venv/bin/activate || . venv/Scripts/activate
fi

# Install Node.js dependencies (required for JavaScript parsing)
echo ""
echo "Checking Node.js dependencies..."
if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies (required for parsing AIDEFEND framework)..."
    npm install
    echo "✓ Node.js dependencies installed"
else
    echo "✓ Node.js dependencies already installed"
fi

echo ""
echo "=========================================="
if [ "$MODE" = "mcp" ]; then
    echo "Starting AIDEFEND MCP Server..."
    echo "=========================================="
    echo ""
    echo "The service will:"
    echo "  1. Download AIDEFEND framework from GitHub (if needed)"
    echo "  2. Parse and index the content"
    echo "  3. Start the MCP server (stdio mode)"
    echo ""
    echo "Note: This server communicates via stdin/stdout."
    echo "      Configure Claude Desktop to connect to this server."
    echo ""
    echo "Press Ctrl+C to stop the server."
    echo ""

    # Start MCP server
    python -m aidefend_mcp --mcp
else
    echo "Starting AIDEFEND REST API Server..."
    echo "=========================================="
    echo ""
    echo "The service will:"
    echo "  1. Download AIDEFEND framework from GitHub (if needed)"
    echo "  2. Parse and index the content"
    echo "  3. Start the API server on http://localhost:8000"
    echo ""
    echo "API documentation will be available at:"
    echo "  http://localhost:8000/docs"
    echo ""
    echo "This may take a few minutes on first run..."
    echo ""

    # Start REST API server
    python -m aidefend_mcp
fi
