"""
FastAPI application for AIDEFEND MCP Service.
Provides REST API endpoints with comprehensive security.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status, Depends, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app import __version__
from app.config import settings
from app.logger import get_logger, setup_logger
from app.auth import get_current_user
from app.schemas import (
    QueryRequest,
    QueryResponse,
    StatusResponse,
    HealthResponse,
    ErrorResponse,
    SyncStatus,
    ThreatCoverageRequest,
    ThreatCoverageResponse,
    ImplementationPlanRequest,
    ImplementationPlanResponse,
    ClassifyThreatRequest,
    ClassifyThreatResponse,
    SecurityPostureRequest,
    TechniqueComparisonRequest,
    IncidentPlaybookRequest,
)
from app.core import query_engine, QueryEngineNotInitializedError
from app.sync import run_sync, sync_loop, is_sync_in_progress, get_last_sync_error
from app.utils import load_version_info
from app.security import InputValidationError, SecurityError
from app.audit import audit_tool_call, audit_tool_completion

# Import all tools from unified package
from app.tools import (
    get_statistics,
    validate_technique_id,
    get_technique_detail,
    get_defenses_for_threat,
    get_secure_code_snippet,
    analyze_coverage,
    map_to_compliance_framework,
    get_quick_reference,
    get_threat_coverage,
    get_implementation_plan,
    classify_threat,
    comprehensive_search,
    analyze_security_posture,
    compare_techniques,
    generate_incident_playbook,
)

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

    # Clean up stale lock files from crashed processes
    try:
        from app.sync import cleanup_stale_lock
        cleanup_stale_lock()
    except Exception as e:
        logger.warning(f"Failed to cleanup stale lock on startup: {e}")

    # Ensure database is ready (auto-initialize or repair if needed)
    # This handles both new installations and corrupted databases
    try:
        from app.sync import ensure_database_ready
        logger.info("Checking database health...")
        await ensure_database_ready()
        logger.info("Database is ready")
    except Exception as e:
        logger.error(f"Critical: Failed to ensure database ready: {e}")
        # This is a fatal error - cannot start without database
        raise RuntimeError("Database initialization/repair failed - cannot start REST API server")

    # Check for embedding model changes
    version_info = load_version_info()
    if version_info:
        stored_model = version_info.get("embedding_model")
        current_model = settings.EMBEDDING_MODEL

        if stored_model and stored_model != current_model:
            logger.warning("=" * 60)
            logger.warning("⚠️  EMBEDDING MODEL CHANGE DETECTED")
            logger.warning(f"⚠️  Database model: {stored_model}")
            logger.warning(f"⚠️  Configured model: {current_model}")
            logger.warning("⚠️")
            logger.warning("⚠️  Database rebuild recommended for optimal performance.")
            logger.warning("⚠️  Run: python __main__.py --resync")
            logger.warning("=" * 60)

    # Check for multi-worker configuration issue
    if settings.API_WORKERS > 1:
        logger.warning("=" * 60)
        logger.warning("⚠️  CONFIGURATION WARNING: API_WORKERS > 1 detected")
        logger.warning("⚠️  Multi-worker mode is NOT supported by this service.")
        logger.warning("⚠️  Sync architecture requires single worker for data consistency.")
        logger.warning("⚠️  Please set API_WORKERS=1 in your configuration.")
        logger.warning("=" * 60)

    # Startup tasks
    try:
        # Initialize query engine
        logger.info("Initializing query engine...")
        await query_engine.initialize()

        # Check if this is a cold start (no database exists)
        # Use SAME logic as mcp_server.py to prevent race conditions
        if not query_engine.is_ready:
            logger.warning("=" * 60)
            logger.warning("⚠️  COLD START DETECTED - No database found")
            logger.warning("⚠️  Performing blocking sync (may take 30-60 seconds)")
            logger.warning("=" * 60)

            # Blocking sync for cold start to prevent race condition
            sync_success = await run_sync()

            if sync_success:
                logger.info("✅ Initial sync completed successfully")
            else:
                logger.error("❌ Initial sync failed - queries will fail")
                logger.error("   User must manually run sync_aidefend tool or restart service")
        else:
            # Warm start - database exists, serve immediately.
            # Periodic sync loop will check for updates without blocking initial queries.
            logger.info("Warm start detected (database exists)")
            logger.info("Serving existing database immediately; periodic sync loop will handle update checks")

        # Start background sync loop if enabled
        if settings.ENABLE_AUTO_SYNC:
            logger.info(
                f"Starting background sync loop (interval: {settings.SYNC_INTERVAL_SECONDS}s)"
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

# Create routers for authentication separation
# Public router: No authentication required (health checks, monitoring)
public_router = APIRouter()

# Protected router: Authentication required (core functionality)
# Only applied when AUTH_MODE != "no_auth"
protected_router = APIRouter(
    dependencies=[Depends(get_current_user)]
)


# Security middleware
@app.middleware("http")
async def limit_request_size_middleware(request: Request, call_next):
    """
    Limit request body size to prevent DoS attacks.

    Checks Content-Length header and rejects requests exceeding 1MB.
    Returns HTTP 413 (Payload Too Large) if limit is exceeded.
    """
    MAX_REQUEST_SIZE = 1048576  # 1MB in bytes

    content_length = request.headers.get("content-length")

    if content_length:
        try:
            content_length_int = int(content_length)
            if content_length_int > MAX_REQUEST_SIZE:
                logger.warning(
                    f"Request rejected: size {content_length_int} bytes exceeds limit {MAX_REQUEST_SIZE} bytes",
                    extra={
                        "client": request.client.host if request.client else "unknown",
                        "path": request.url.path,
                        "content_length": content_length_int
                    }
                )
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={
                        "error": "REQUEST_TOO_LARGE",
                        "message": f"Request body exceeds maximum allowed size of {MAX_REQUEST_SIZE} bytes (1MB)",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
        except ValueError:
            # Invalid Content-Length header - let FastAPI handle it
            logger.warning(f"Invalid Content-Length header: {content_length}")

    response = await call_next(request)
    return response


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
    start_time = datetime.now(timezone.utc)

    logger.info(
        f"Request: {request.method} {request.url.path}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else "unknown"
        }
    )

    response = await call_next(request)

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        f"Response: {response.status_code} ({duration:.3f}s)",
        extra={
            "status_code": response.status_code,
            "duration_seconds": duration
        }
    )

    return response





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
            timestamp=datetime.now(timezone.utc)
        ).model_dump(mode='json')
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
            timestamp=datetime.now(timezone.utc)
        ).model_dump(mode='json')
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
            timestamp=datetime.now(timezone.utc)
        ).model_dump(mode='json')
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Handle all other exceptions.

    Security: Explicitly hides internal error details from API responses
    to prevent information leakage. Full error details are logged server-side
    with a unique error ID for correlation.
    """
    # Generate unique error ID for correlation
    import uuid
    error_id = str(uuid.uuid4())[:8]

    # Log full error details server-side with error ID
    logger.error(
        f"Unhandled exception [ID: {error_id}]: {exc}",
        exc_info=True,
        extra={
            "error_id": error_id,
            "client": request.client.host if request.client else "unknown",
            "path": request.url.path,
            "method": request.method
        }
    )

    # Return generic error to client without internal details
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="INTERNAL_ERROR",
            message=f"An internal error occurred. Reference ID: {error_id}",
            timestamp=datetime.now(timezone.utc)
        ).model_dump(mode='json')
    )


# ==================== PUBLIC ENDPOINTS (No Authentication) ====================

@public_router.get("/", include_in_schema=False)
async def root():
    """Root endpoint redirect to docs."""
    return {
        "service": "AIDEFEND MCP Service",
        "version": __version__,
        "docs": "/docs",
        "status": "/api/v1/status",
        "health": "/health"
    }


@public_router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint for container orchestration.
    Returns basic health status of all components.

    Also checks data staleness - if data hasn't been synced in 2x the sync interval,
    returns 'degraded' status to alert monitoring systems.
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

        # Check data staleness
        version_info = load_version_info()
        overall_status = "healthy"

        if version_info and "last_synced_at" in version_info:
            try:
                last_synced = datetime.fromisoformat(version_info["last_synced_at"].replace('Z', '+00:00'))
                age_seconds = (datetime.now(timezone.utc) - last_synced).total_seconds()
                max_age_seconds = settings.SYNC_INTERVAL_SECONDS * 2

                if age_seconds > max_age_seconds:
                    overall_status = "degraded"
                    checks["sync_service"] = False
                    logger.warning(
                        f"Data is stale: last sync was {age_seconds / 3600:.1f} hours ago "
                        f"(max: {max_age_seconds / 3600:.1f} hours)"
                    )
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse last_synced_at: {e}")

        # Overall status considers all checks
        if not all(checks.values()):
            overall_status = "degraded" if overall_status == "healthy" and checks["database"] else "unhealthy"

        return HealthResponse(
            status=overall_status,
            checks=checks,
            timestamp=datetime.now(timezone.utc)
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            checks=checks,
            timestamp=datetime.now(timezone.utc)
        )


# ==================== PROTECTED ENDPOINTS (Authentication Required) ====================

@protected_router.get("/api/v1/status", response_model=StatusResponse, tags=["Status"])
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
                framework_version=version_info.get("framework_version"),
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
            timestamp=datetime.now(timezone.utc)
        )

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve status"
        )


@protected_router.post("/api/v1/query", response_model=QueryResponse, tags=["Query"])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def query_aidefend(request: Request, query_request: QueryRequest):
    """
    Query the AIDEFEND knowledge base using RAG.

    Performs semantic search over AIDEFEND tactics, techniques, and strategies.
    Returns the most relevant context chunks for the given query.

    **Automatic Chunking:** For long queries (> 1500 chars), the system automatically
    chunks the text and combines results from multiple searches.

    **Security:** Query text is validated and sanitized to prevent injection attacks.
    Long queries are subject to additional limits (max 5000 chars, max 5 chunks).
    """
    from app.tools.chunked_search import search_with_chunking
    from app.security import InputValidationError

    try:
        query_text = query_request.query_text
        query_length = len(query_text)

        logger.info(
            f"Query received",
            extra={
                "query_preview": query_text[:50],
                "query_length": query_length,
                "top_k": query_request.top_k,
                "chunking_eligible": query_length > settings.MAX_QUERY_LENGTH
            }
        )

        # Determine if chunking is needed
        if query_length > settings.MAX_QUERY_LENGTH:
            # Use chunked search for long queries
            logger.info(
                f"Using chunked search for long query",
                extra={"query_length": query_length}
            )

            try:
                result = await search_with_chunking(
                    query_text=query_text,
                    top_k=query_request.top_k
                )

                # result contains: {results: [...], metadata: {...}}
                chunks = result['results']
                metadata = result['metadata']

                logger.info(
                    f"Chunked search completed",
                    extra={
                        "chunks_processed": metadata.get('chunks_processed', 0),
                        "results_found": len(chunks),
                        "processing_time": metadata.get('processing_time_seconds', 0)
                    }
                )

                # Add chunking metadata to response (via extra field if available)
                # For now, log it - can extend QueryResponse schema later if needed
                return QueryResponse(
                    query_text=query_text,
                    context_chunks=chunks,
                    total_results=len(chunks),
                    timestamp=datetime.now(timezone.utc)
                )

            except asyncio.TimeoutError as e:
                logger.error(f"Chunked search timeout: {e}")
                raise HTTPException(
                    status_code=status.HTTP_408_REQUEST_TIMEOUT,
                    detail=str(e)
                )
            except InputValidationError as e:
                logger.warning(f"Chunked query validation failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e)
                )

        else:
            # Regular search for normal-length queries
            chunks = await query_engine.search(query_request)

            return QueryResponse(
                query_text=query_text,
                context_chunks=chunks,
                total_results=len(chunks),
                timestamp=datetime.now(timezone.utc)
            )

    except QueryEngineNotInitializedError:
        raise
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Query processing failed"
        )


@protected_router.post("/api/v1/sync", tags=["Admin"])
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
        "timestamp": datetime.now(timezone.utc)
    }


# ==================== P0 Tool Endpoints ====================

@protected_router.get("/api/v1/statistics", tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_get_statistics(request: Request):
    """
    Get comprehensive statistics about the AIDEFEND knowledge base.

    Returns statistics including total documents, breakdown by tactic/pillar/phase,
    threat framework coverage, and tools availability.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call("get_statistics", {}, start_time)

    try:
        result = await get_statistics()

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{result['overview']['total_documents']} documents"
        )

        return result

    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Statistics failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get statistics: {str(e)}"
        )


@protected_router.post("/api/v1/validate-technique-id", tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_validate_technique_id(request: Request, technique_id: str):
    """
    Validate if a technique ID exists and is correctly formatted.

    Provides fuzzy matching suggestions if ID is not found.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call("validate_technique_id", {"technique_id": technique_id}, start_time)

    try:
        result = await validate_technique_id(technique_id)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Valid: {result['valid']}"
        )

        return result

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Validation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed: {str(e)}"
        )


@protected_router.get("/api/v1/technique/{technique_id}", tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_get_technique_detail(
    request: Request,
    technique_id: str,
    include_code: bool = True,
    include_tools: bool = True
):
    """
    Get complete details for a specific AIDEFEND technique.

    Includes all sub-techniques, implementation strategies with code examples,
    tool recommendations, and threat mappings.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "get_technique_detail",
        {"technique_id": technique_id, "include_code": include_code, "include_tools": include_tools},
        start_time
    )

    try:
        result = await get_technique_detail(technique_id, include_code, include_tools)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{result['metadata']['total_subtechniques']} subtechniques"
        )

        return result

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Get technique detail failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get technique detail: {str(e)}"
        )


@protected_router.post("/api/v1/defenses-for-threat", tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_get_defenses_for_threat(
    request: Request,
    threat_id: str = None,
    threat_keyword: str = None,
    top_k: int = 10
):
    """
    Find AIDEFEND defense techniques for a specific threat.

    Supports threat IDs from the mapped framework set or natural language
    threat keywords.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "get_defenses_for_threat",
        {"threat_id": threat_id, "threat_keyword": threat_keyword, "top_k": top_k},
        start_time
    )

    try:
        result = await get_defenses_for_threat(
            threat_id=threat_id,
            threat_keyword=threat_keyword,
            top_k=top_k
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{result['total_results']} defenses"
        )

        return result

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Get defenses for threat failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get defenses: {str(e)}"
        )


@protected_router.post("/api/v1/code-snippets", tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_get_secure_code_snippet(
    request: Request,
    technique_id: str = None,
    topic: str = None,
    language: str = None,
    max_snippets: int = 5
):
    """
    Extract executable secure code snippets from AIDEFEND implementation strategies.

    Search by technique ID or topic keyword to get copy-paste ready code examples.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "get_secure_code_snippet",
        {"technique_id": technique_id, "topic": topic, "language": language, "max_snippets": max_snippets},
        start_time
    )

    try:
        result = await get_secure_code_snippet(
            technique_id=technique_id,
            topic=topic,
            language=language,
            max_snippets=max_snippets
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{result['total_snippets']} snippets"
        )

        return result

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Get code snippets failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get code snippets: {str(e)}"
        )


@protected_router.post("/api/v1/analyze-coverage", tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_analyze_coverage(
    request: Request,
    implemented_techniques: list[str],
    system_type: str = None
):
    """
    Analyze defense coverage based on implemented techniques and identify gaps.

    Provides coverage percentage by tactic/pillar/phase, threat framework coverage,
    and prioritized recommendations.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "analyze_coverage",
        {"implemented_techniques": implemented_techniques, "system_type": system_type},
        start_time
    )

    try:
        result = await analyze_coverage(
            implemented_techniques=implemented_techniques,
            system_type=system_type
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{result['analysis_summary']['coverage_percentage']}% coverage"
        )

        return result

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Analyze coverage failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze coverage: {str(e)}"
        )


@protected_router.post("/api/v1/compliance-mapping", tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_map_to_compliance_framework(
    request: Request,
    technique_ids: list[str],
    framework: str = "nist_ai_rmf"
):
    """
    Map AIDEFEND techniques to compliance framework requirements.

    Supports NIST AI RMF, EU AI Act, ISO 42001, CSA AI Controls, OWASP ASVS.
    Uses heuristic-based analysis for mapping (100% local, no external API calls).
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "map_to_compliance_framework",
        {"technique_ids": technique_ids, "framework": framework},
        start_time
    )

    try:
        result = await map_to_compliance_framework(
            technique_ids=technique_ids,
            framework=framework
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{result['total_mapped']} techniques mapped"
        )

        return result

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Compliance mapping failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to map to compliance framework: {str(e)}"
        )


@protected_router.post("/api/v1/quick-reference", tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_get_quick_reference(
    request: Request,
    topic: str,
    format: str = "checklist",
    max_items: int = 10
):
    """
    Generate a quick reference guide for a specific security topic.

    Provides actionable checklist organized by priority (quick wins, must-haves, nice-to-haves).
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "get_quick_reference",
        {"topic": topic, "format": format, "max_items": max_items},
        start_time
    )

    try:
        result = await get_quick_reference(
            topic=topic,
            format=format,
            max_items=max_items
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{result['total_items']} items"
        )

        return result

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Quick reference failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate quick reference: {str(e)}"
        )


# ==================== New Tool Endpoints ====================

@protected_router.post("/api/v1/threat-coverage", response_model=ThreatCoverageResponse, tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_get_threat_coverage(request: Request, coverage_request: ThreatCoverageRequest):
    """
    Analyze threat coverage for implemented defense techniques.

    Given a list of implemented AIDEFEND technique IDs, this endpoint:
    - Validates each technique ID against the database
    - Retrieves threat mappings from defends_against field
    - Calculates coverage rates for all mapped threat frameworks
    - Returns detailed per-technique threat mapping

    **Use Case**: Track which threats are covered by your implemented defenses
    and identify coverage gaps.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "get_threat_coverage",
        {"implemented_techniques": coverage_request.implemented_techniques},
        start_time
    )

    try:
        result = await get_threat_coverage(coverage_request.implemented_techniques)

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{result['valid_count']}/{result['input_count']} valid techniques analyzed"
        )

        return ThreatCoverageResponse(**result)

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Threat coverage analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze threat coverage: {str(e)}"
        )


@protected_router.post("/api/v1/implementation-plan", response_model=ImplementationPlanResponse, tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_get_implementation_plan(request: Request, plan_request: ImplementationPlanRequest):
    """
    Get ranked recommendations for next defense techniques to implement.

    Uses heuristic scoring based on:
    - Threat importance (covers high-risk threats like LLM01, LLM03, T0020)
    - Ease of implementation (open-source tools available)
    - Phase weight (Design > Development > Deployment > Runtime)
    - Pillar weight (Prevent > Detect > Respond)
    - Tool ecosystem maturity (commercial tools available)

    **Note**: This tool provides ONLY heuristic scores. LLM should use these
    scores to make final recommendations via RAG.

    **Use Case**: Prioritize which defense techniques to implement next based
    on risk coverage and implementation effort.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "get_implementation_plan",
        {
            "implemented_techniques": plan_request.implemented_techniques or [],
            "exclude_tactics": plan_request.exclude_tactics or [],
            "top_k": plan_request.top_k,
            "detail_level": plan_request.detail_level
        },
        start_time
    )

    try:
        result = await get_implementation_plan(
            implemented_techniques=plan_request.implemented_techniques,
            exclude_tactics=plan_request.exclude_tactics,
            top_k=plan_request.top_k,
            detail_level=plan_request.detail_level
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{len(result['recommendations'])} recommendations, {len(result['categories']['quick_wins'])} quick wins, detail_level={plan_request.detail_level}"
        )

        return ImplementationPlanResponse(**result)

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Implementation plan generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate implementation plan: {str(e)}"
        )


@protected_router.post("/api/v1/classify-threat", response_model=ClassifyThreatResponse, tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_classify_threat(request: Request, classify_request: ClassifyThreatRequest):
    """
    Classify threats in text using static keyword dictionary matching.

    Maps common threat terms to the standard framework IDs used by the service
    using simple keyword matching.

    **Method**: Static keyword dictionary with ~40 threat terms
    - Primary keyword matching (e.g., "prompt injection" -> LLM01)
    - Alias matching (e.g., "jailbreak" -> LLM01)
    - Confidence scoring based on match quality

    **Note**: This tool uses ONLY static keyword matching. NO NLP, NO embedding,
    NO auto-chain. LLM handles text understanding and orchestration.

    **Use Case**: Quickly normalize threat keywords from incident reports,
    security alerts, or vulnerability descriptions to standard framework IDs.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "classify_threat",
        {"text_preview": classify_request.text[:100], "top_k": classify_request.top_k},
        start_time
    )

    try:
        result = await classify_threat(
            text=classify_request.text,
            top_k=classify_request.top_k
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{len(result['keywords_found'])} keywords matched, OWASP: {len(result['normalized_threats']['owasp'])}, ATLAS: {len(result['normalized_threats']['atlas'])}"
        )

        return ClassifyThreatResponse(**result)

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Threat classification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to classify threat: {str(e)}"
        )


@protected_router.post("/api/v1/comprehensive-search", tags=["Tools"])
@limiter.limit("30/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_comprehensive_search(
    request: Request,
    topic: str,
    max_results: int = 20,
    include_subtechniques: bool = True
):
    """
    Perform comprehensive multi-query semantic search for broad topics.

    Automatically generates related queries, executes parallel searches,
    deduplicates results, and returns aggregated coverage.

    **Use Case**: Handle broad questions like "deepfakes defenses",
    "prompt injection overview", "RAG security" in a single call to avoid
    timeout from sequential tool calls.

    **Features**:
    - Multi-query generation (4-5 related queries)
    - Parallel execution for speed
    - Automatic deduplication by source_id
    - Coverage summary (tactics, pillars, phases)
    - Related search suggestions

    **Parameters**:
    - `topic`: Broad topic to search (e.g., "deepfakes", "prompt injection")
    - `max_results`: Maximum total results (5-50, default: 20)
    - `include_subtechniques`: Include sub-techniques (default: true)

    **Returns**: Dict with queries executed, results, and coverage summary
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "comprehensive_search",
        {"topic": topic, "max_results": max_results},
        start_time
    )

    try:
        result = await comprehensive_search(
            topic=topic,
            max_results=max_results,
            include_subtechniques=include_subtechniques
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Found {len(result['results'])} results across {len(result['queries_executed'])} queries"
        )

        return result

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Not initialized", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Comprehensive search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to perform comprehensive search: {str(e)}"
        )


@protected_router.post("/api/v1/security-posture", tags=["Tools"])
@limiter.limit("30/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_analyze_security_posture(
    request: Request,
    posture_request: SecurityPostureRequest
):
    """
    Comprehensive security posture analysis combining technical and threat perspectives.

    Provides unified view of security coverage including tactic/pillar/phase distribution,
    threat framework coverage rates across all mapped external frameworks, and prioritized recommendations.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "analyze_security_posture",
        {
            "implemented_techniques": posture_request.implemented_techniques,
            "view": posture_request.view,
            "system_type": posture_request.system_type
        },
        start_time
    )

    try:
        result = await analyze_security_posture(
            implemented_techniques=posture_request.implemented_techniques,
            view=posture_request.view,
            system_type=posture_request.system_type
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Posture analysis: {result.get('implemented_count', 0)} techniques"
        )

        return result

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Security posture analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze security posture: {str(e)}"
        )


@protected_router.post("/api/v1/compare-techniques", tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_compare_techniques(
    request: Request,
    comparison_request: TechniqueComparisonRequest
):
    """
    Side-by-side comparison of multiple AIDEFEND techniques with heuristic scoring.

    Provides comparison matrix showing effectiveness, complexity, and cost scores.
    Includes quick wins, strategic investments, and implementation priority recommendations.
    All scoring is 100% local using metadata analysis.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "compare_techniques",
        {
            "technique_ids": comparison_request.technique_ids,
            "include_recommendations": comparison_request.include_recommendations
        },
        start_time
    )

    try:
        result = await compare_techniques(
            technique_ids=comparison_request.technique_ids,
            include_recommendations=comparison_request.include_recommendations
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Compared {result['summary']['techniques_compared']} techniques"
        )

        return result

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Technique comparison failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compare techniques: {str(e)}"
        )


@protected_router.post("/api/v1/incident-playbook", tags=["Tools"])
@limiter.limit("30/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_generate_incident_playbook(
    request: Request,
    playbook_request: IncidentPlaybookRequest
):
    """
    Generate structured incident response playbook based on threat classification.

    Provides timeline-based action plan following NIST incident response phases:
    immediate actions, investigation, containment, and recovery.
    Integrates with threat classification and defense technique recommendations.
    """
    start_time = datetime.now()
    audit_ctx = audit_tool_call(
        "generate_incident_playbook",
        {
            "incident_description": playbook_request.incident_description[:100],
            "include_defense_techniques": playbook_request.include_defense_techniques
        },
        start_time
    )

    try:
        result = await generate_incident_playbook(
            incident_description=playbook_request.incident_description,
            include_defense_techniques=playbook_request.include_defense_techniques
        )

        total_actions = result['incident_summary']['total_action_items']
        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"Generated playbook with {total_actions} actions"
        )

        return result

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except QueryEngineNotInitializedError:
        raise
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Incident playbook generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate incident playbook: {str(e)}"
        )


# ==================== ROUTER REGISTRATION ====================

# Register routers with the main app
# Order matters: public router first (for /health checks), then protected
app.include_router(public_router)
app.include_router(protected_router)


# ==================== CORS MIDDLEWARE ====================

# Add CORS middleware (applied AFTER routers are registered)
if settings.ENABLE_CORS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )


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
