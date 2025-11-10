#!/bin/bash
# Quick start script for AIDEFEND MCP Service

set -e

echo "=========================================="
echo "AIDEFEND MCP Service - Quick Start"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "✓ Python $python_version"

# Check Node.js
echo "Checking Node.js..."
if ! command -v node &> /dev/null; then
    echo "✗ Node.js not found. Please install Node.js first."
    exit 1
fi
node_version=$(node --version)
echo "✓ Node.js $node_version"

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
    echo "Installing dependencies (this may take a few minutes)..."
    pip install -r requirements.txt
    echo "✓ Dependencies installed"
else
    echo "✓ Virtual environment exists"
    source venv/bin/activate || . venv/Scripts/activate
fi

echo ""
echo "=========================================="
echo "Starting AIDEFEND MCP Service..."
echo "=========================================="
echo ""
echo "The service will:"
echo "  1. Download AIDEFEND framework from GitHub"
echo "  2. Parse and index the content"
echo "  3. Start the API server on http://localhost:8000"
echo ""
echo "This may take a few minutes on first run..."
echo ""

# Start the service
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
