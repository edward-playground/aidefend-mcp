"""
FastAPI application for AIDEFEND MCP Service.
Provides REST API endpoints with comprehensive security.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any
from datetime import datetime, timezone

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
    SyncStatus,
    ThreatCoverageRequest,
    ThreatCoverageResponse,
    ImplementationPlanRequest,
    ImplementationPlanResponse,
    ClassifyThreatRequest,
    ClassifyThreatResponse
)
from app.core import query_engine, QueryEngineNotInitializedError
from app.sync import run_sync, sync_loop, is_sync_in_progress, get_last_sync_error
from app.utils import load_version_info
from app.security import InputValidationError, SecurityError
from app.audit import audit_tool_call, audit_tool_completion

# Import P0 tools
from app.tools import (
    get_statistics,
    validate_technique_id,
    get_technique_detail,
    get_defenses_for_threat,
    get_secure_code_snippet,
    analyze_coverage,
    map_to_compliance_framework,
    get_quick_reference
)

# Import new tools
from app.tools.threat_coverage import get_threat_coverage
from app.tools.implementation_plan import get_implementation_plan
from app.tools.classify_threat import classify_threat

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


# ==================== P0 Tool Endpoints ====================

@app.get("/api/v1/statistics", tags=["Tools"])
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

    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Statistics failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get statistics: {str(e)}"
        )


@app.post("/api/v1/validate-technique-id", tags=["Tools"])
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
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Validation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed: {str(e)}"
        )


@app.get("/api/v1/technique/{technique_id}", tags=["Tools"])
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
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Get technique detail failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get technique detail: {str(e)}"
        )


@app.post("/api/v1/defenses-for-threat", tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_get_defenses_for_threat(
    request: Request,
    threat_id: str = None,
    threat_keyword: str = None,
    top_k: int = 10
):
    """
    Find AIDEFEND defense techniques for a specific threat.

    Supports threat IDs from OWASP LLM Top 10, MITRE ATLAS, MAESTRO,
    or natural language threat keywords.
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
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Get defenses for threat failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get defenses: {str(e)}"
        )


@app.post("/api/v1/code-snippets", tags=["Tools"])
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
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Get code snippets failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get code snippets: {str(e)}"
        )


@app.post("/api/v1/analyze-coverage", tags=["Tools"])
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
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Analyze coverage failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze coverage: {str(e)}"
        )


@app.post("/api/v1/compliance-mapping", tags=["Tools"])
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
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Compliance mapping failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to map to compliance framework: {str(e)}"
        )


@app.post("/api/v1/quick-reference", tags=["Tools"])
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
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Quick reference failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate quick reference: {str(e)}"
        )


# ==================== New Tool Endpoints ====================

@app.post("/api/v1/threat-coverage", response_model=ThreatCoverageResponse, tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_get_threat_coverage(request: Request, coverage_request: ThreatCoverageRequest):
    """
    Analyze threat coverage for implemented defense techniques.

    Given a list of implemented AIDEFEND technique IDs, this endpoint:
    - Validates each technique ID against the database
    - Retrieves threat mappings from defends_against field
    - Calculates coverage rates for OWASP LLM Top 10, MITRE ATLAS, and MAESTRO
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
            result_summary=f"{result['valid_count']}/{result['input_count']} valid, OWASP: {len(result['covered']['owasp'])}, ATLAS: {len(result['covered']['atlas'])}"
        )

        return ThreatCoverageResponse(**result)

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Threat coverage analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze threat coverage: {str(e)}"
        )


@app.post("/api/v1/implementation-plan", response_model=ImplementationPlanResponse, tags=["Tools"])
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
            "top_k": plan_request.top_k
        },
        start_time
    )

    try:
        result = await get_implementation_plan(
            implemented_techniques=plan_request.implemented_techniques,
            exclude_tactics=plan_request.exclude_tactics,
            top_k=plan_request.top_k
        )

        audit_tool_completion(
            audit_ctx,
            success=True,
            result_summary=f"{len(result['recommendations'])} recommendations, {len(result['categories']['quick_wins'])} quick wins"
        )

        return ImplementationPlanResponse(**result)

    except InputValidationError as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Validation error", error_message=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Implementation plan generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate implementation plan: {str(e)}"
        )


@app.post("/api/v1/classify-threat", response_model=ClassifyThreatResponse, tags=["Tools"])
@limiter.limit("60/minute" if settings.ENABLE_RATE_LIMITING else "1000/minute")
async def api_classify_threat(request: Request, classify_request: ClassifyThreatRequest):
    """
    Classify threats in text using static keyword dictionary matching.

    Maps common threat terms to standard framework IDs (OWASP LLM Top 10,
    MITRE ATLAS, MAESTRO) using simple keyword matching.

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
    except Exception as e:
        audit_tool_completion(audit_ctx, success=False, result_summary="Error", error_message=str(e))
        logger.error(f"Threat classification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to classify threat: {str(e)}"
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
