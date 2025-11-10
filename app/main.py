"""
FastAPI application for AIDEFEND MCP Service.
Provides REST API endpoints with comprehensive security.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app import __version__
from app.config import settings
from app.logger import get_logger, setup_logger
from app.schemas import (
    QueryRequest,
    QueryResponse,
    StatusResponse,
    HealthResponse,
    ErrorResponse,
    SyncStatus
)
from app.core import query_engine, QueryEngineNotInitializedError
from app.sync import run_sync, sync_loop, is_sync_in_progress, get_last_sync_error
from app.utils import load_version_info
from app.security import InputValidationError, SecurityError

# Setup logger
logger = setup_logger(
    name="aidefend_mcp",
    log_level=settings.LOG_LEVEL,
    log_file=settings.LOG_PATH if settings.ENABLE_FILE_LOGGING else None,
    enable_console=True
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


# Application lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    logger.info("=" * 60)
    logger.info("AIDEFEND MCP Service starting up...")
    logger.info(f"Version: {__version__}")
    logger.info("=" * 60)

    # Startup tasks
    try:
        # Initialize query engine
        logger.info("Initializing query engine...")
        await query_engine.initialize()

        # Trigger initial sync (non-blocking)
        logger.info("Triggering initial sync...")
        asyncio.create_task(run_sync())

        # Start background sync loop if enabled
        if settings.ENABLE_AUTO_SYNC:
            logger.info(
                f"Starting background sync (interval: {settings.SYNC_INTERVAL_SECONDS}s)"
            )
            asyncio.create_task(sync_loop())
        else:
            logger.info("Auto-sync disabled")

        logger.info("Startup complete!")

    except Exception as e:
        logger.error(f"Startup error: {e}", exc_info=True)

    yield

    # Shutdown tasks
    logger.info("Shutting down AIDEFEND MCP Service...")
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="AIDEFEND MCP Service",
    description=(
        "A local, decentralized RAG engine for the AIDEFEND AI security framework. "
        "Provides secure, private access to AIDEFEND knowledge base."
    ),
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Security middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    if settings.ENABLE_SECURITY_HEADERS:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    return response


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log all requests."""
    start_time = datetime.utcnow()

    logger.info(
        f"Request: {request.method} {request.url.path}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else "unknown"
        }
    )

    response = await call_next(request)

    duration = (datetime.utcnow() - start_time).total_seconds()
    logger.info(
        f"Response: {response.status_code} ({duration:.3f}s)",
        extra={
            "status_code": response.status_code,
            "duration_seconds": duration
        }
    )

    return response


# CORS middleware
if settings.ENABLE_CORS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


# Exception handlers
@app.exception_handler(InputValidationError)
async def validation_error_handler(request: Request, exc: InputValidationError):
    """Handle input validation errors."""
    logger.warning(f"Validation error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            error="VALIDATION_ERROR",
            message=str(exc),
            timestamp=datetime.utcnow()
        ).model_dump()
    )


@app.exception_handler(SecurityError)
async def security_error_handler(request: Request, exc: SecurityError):
    """Handle security errors."""
    logger.warning(f"Security error: {exc}", extra={"client": request.client.host if request.client else "unknown"})
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=ErrorResponse(
            error="SECURITY_ERROR",
            message="Access denied",
            timestamp=datetime.utcnow()
        ).model_dump()
    )


@app.exception_handler(QueryEngineNotInitializedError)
async def engine_not_initialized_handler(request: Request, exc: QueryEngineNotInitializedError):
    """Handle query engine not initialized errors."""
    logger.error(f"Query engine not initialized: {exc}")
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=ErrorResponse(
            error="SERVICE_NOT_READY",
            message="Service is initializing. Please wait for initial sync to complete.",
            timestamp=datetime.utcnow()
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="INTERNAL_ERROR",
            message="An internal error occurred",
            timestamp=datetime.utcnow()
        ).model_dump()
    )


# API Endpoints

@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint redirect to docs."""
    return {
        "service": "AIDEFEND MCP Service",
        "version": __version__,
        "docs": "/docs",
        "status": "/api/v1/status",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint for container orchestration.
    Returns basic health status of all components.
    """
    checks = {
        "database": False,
        "embedding_model": False,
        "sync_service": True  # Always true if service is running
    }

    try:
        # Check query engine
        engine_healthy = await query_engine.health_check()
        checks["database"] = engine_healthy
        checks["embedding_model"] = engine_healthy

        overall_status = "healthy" if all(checks.values()) else "unhealthy"

        return HealthResponse(
            status=overall_status,
            checks=checks,
            timestamp=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            checks=checks,
            timestamp=datetime.utcnow()
        )


@app.get("/api/v1/status", response_model=StatusResponse, tags=["Status"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def get_status(request: Request):
    """
    Get service status and synchronization information.
    Returns current version, last sync time, and document count.
    """
    try:
        # Load version info
        version_info = load_version_info()

        # Get sync status
        sync_status = None
        if version_info:
            sync_status = SyncStatus(
                last_synced_at=datetime.fromisoformat(version_info["last_synced_at"]) if "last_synced_at" in version_info else None,
                current_commit_sha=version_info.get("commit_sha"),
                total_documents=version_info.get("total_documents"),
                is_syncing=is_sync_in_progress()
            )

        # Determine status
        if is_sync_in_progress():
            status_str = "syncing"
            message = "Sync in progress..."
        elif version_info:
            status_str = "online"
            message = "Service is online and synchronized"
        else:
            status_str = "initializing"
            message = "Initial sync pending"

        # Check for errors
        last_error = get_last_sync_error()
        if last_error:
            status_str = "error"
            message = f"Last sync failed: {last_error}"

        return StatusResponse(
            status=status_str,
            sync_info=sync_status,
            message=message,
            version=__version__,
            timestamp=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve status"
        )


@app.post("/api/v1/query", response_model=QueryResponse, tags=["Query"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def query_aidefend(request: Request, query_request: QueryRequest):
    """
    Query the AIDEFEND knowledge base using RAG.

    Performs semantic search over AIDEFEND tactics, techniques, and strategies.
    Returns the most relevant context chunks for the given query.

    **Security:** Query text is validated and sanitized to prevent injection attacks.
    """
    try:
        logger.info(
            f"Query received",
            extra={
                "query_preview": query_request.query_text[:50],
                "top_k": query_request.top_k
            }
        )

        # Perform search
        chunks = await query_engine.search(query_request)

        return QueryResponse(
            query_text=query_request.query_text,
            context_chunks=chunks,
            total_results=len(chunks),
            timestamp=datetime.utcnow()
        )

    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Query processing failed"
        )


@app.post("/api/v1/sync", tags=["Admin"])
@limiter.limit("5/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def trigger_sync(request: Request):
    """
    Manually trigger a sync operation.

    **Note:** This endpoint has stricter rate limiting (5/minute).
    """
    if is_sync_in_progress():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sync already in progress"
        )

    # Trigger sync in background
    asyncio.create_task(run_sync())

    return {
        "status": "sync_triggered",
        "message": "Sync operation started in background",
        "timestamp": datetime.utcnow()
    }


# Run application
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        workers=settings.API_WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True
    )
