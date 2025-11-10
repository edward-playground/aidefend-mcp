@echo off
REM Quick start script for AIDEFEND MCP Service (Windows)
REM Supports both REST API mode and MCP mode

REM Parse command-line arguments
set MODE=api
if "%1"=="--mcp" set MODE=mcp
if "%1"=="-m" set MODE=mcp
if "%1"=="--help" goto :help
if "%1"=="-h" goto :help
goto :start

:help
echo AIDEFEND MCP Service - Quick Start Script
echo.
echo Usage: start.bat [OPTIONS]
echo.
echo Options:
echo   (no options)    Start in REST API mode (default)
echo   --mcp, -m       Start in MCP mode for Claude Desktop
echo   --help, -h      Show this help message
echo.
echo Examples:
echo   start.bat           # Start REST API server
echo   start.bat --mcp     # Start MCP server
exit /b 0

:start
echo ==========================================
if "%MODE%"=="mcp" (
    echo AIDEFEND MCP Service - MCP Mode
) else (
    echo AIDEFEND MCP Service - REST API Mode
)
echo ==========================================
echo.

REM Check Python
echo Checking Python version...
python --version
if %errorlevel% neq 0 (
    echo X Python not found. Please install Python 3.9+ first.
    exit /b 1
)
echo + Python OK

REM Create .env if not exists
if not exist .env (
    echo Creating .env file from template...
    copy .env.example .env
    echo + .env created
) else (
    echo + .env already exists
)

REM Create virtual environment if needed
if not exist venv (
    echo.
    echo Creating virtual environment...
    python -m venv venv
    echo + Virtual environment created

    echo.
    echo Activating virtual environment...
    call venv\Scripts\activate.bat

    echo.
    echo Installing dependencies (this may take a few minutes)...
    pip install -r requirements.txt
    echo + Dependencies installed
) else (
    echo + Virtual environment exists
    call venv\Scripts\activate.bat
)

echo.
echo ==========================================
if "%MODE%"=="mcp" (
    echo Starting AIDEFEND MCP Server...
    echo ==========================================
    echo.
    echo The service will:
    echo   1. Download AIDEFEND framework from GitHub ^(if needed^)
    echo   2. Parse and index the content
    echo   3. Start the MCP server ^(stdio mode^)
    echo.
    echo Note: This server communicates via stdin/stdout.
    echo       Configure Claude Desktop to connect to this server.
    echo.
    echo Press Ctrl+C to stop the server.
    echo.

    REM Start MCP server
    python -m aidefend_mcp --mcp
) else (
    echo Starting AIDEFEND REST API Server...
    echo ==========================================
    echo.
    echo The service will:
    echo   1. Download AIDEFEND framework from GitHub ^(if needed^)
    echo   2. Parse and index the content
    echo   3. Start the API server on http://localhost:8000
    echo.
    echo API documentation will be available at:
    echo   http://localhost:8000/docs
    echo.
    echo This may take a few minutes on first run...
    echo.

    REM Start REST API server
    python -m aidefend_mcp
)
