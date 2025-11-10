@echo off
REM Quick start script for AIDEFEND MCP Service (Windows)

echo ==========================================
echo AIDEFEND MCP Service - Quick Start
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

REM Check Node.js
echo Checking Node.js...
node --version
if %errorlevel% neq 0 (
    echo X Node.js not found. Please install Node.js first.
    exit /b 1
)
echo + Node.js OK

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
echo Starting AIDEFEND MCP Service...
echo ==========================================
echo.
echo The service will:
echo   1. Download AIDEFEND framework from GitHub
echo   2. Parse and index the content
echo   3. Start the API server on http://localhost:8000
echo.
echo This may take a few minutes on first run...
echo.

REM Start the service
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
