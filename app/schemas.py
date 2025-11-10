"""
Pydantic schemas for API request/response validation.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.config import settings
from app.security import validate_query_text, validate_top_k


class QueryRequest(BaseModel):
    """Request model for RAG query endpoint."""

    query_text: str = Field(
        ...,
        min_length=3,
        max_length=settings.MAX_QUERY_LENGTH,
        description="Natural language query for AIDEFEND knowledge base",
        examples=["How to harden AI models against adversarial attacks?"]
    )
    top_k: int = Field(
        default=settings.DEFAULT_TOP_K,
        ge=1,
        le=settings.MAX_TOP_K,
        description="Number of relevant context chunks to retrieve"
    )

    @field_validator("query_text")
    @classmethod
    def validate_and_sanitize_query(cls, v: str) -> str:
        """Validate and sanitize query text using security module."""
        return validate_query_text(v)

    @field_validator("top_k")
    @classmethod
    def validate_top_k_value(cls, v: int) -> int:
        """Validate top_k parameter."""
        return validate_top_k(v, max_allowed=settings.MAX_TOP_K)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query_text": "What are the best practices for model hardening?",
                    "top_k": 5
                }
            ]
        }
    }


class ContextChunk(BaseModel):
    """Model for a single retrieved context chunk."""

    source_id: str = Field(
        description="AIDEFEND technique/sub-technique ID (e.g., AID-H-001.001)"
    )
    tactic: str = Field(
        description="AIDEFEND tactic name (e.g., Harden, Detect, Isolate)"
    )
    text: str = Field(
        description="Retrieved context text chunk"
    )
    metadata: Dict[str, Any] = Field(
        description="Additional metadata (type, name, pillar, phase, etc.)"
    )
    score: float = Field(
        description="Similarity/relevance score (lower is better for L2 distance)",
        ge=0.0
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "source_id": "AID-H-001.001",
                    "tactic": "Harden",
                    "text": "Sub-Technique: Input Validation\nDescription: Implement robust input validation...",
                    "metadata": {
                        "type": "subtechnique",
                        "name": "Input Validation",
                        "pillar": "app",
                        "phase": "building"
                    },
                    "score": 0.234
                }
            ]
        }
    }


class QueryResponse(BaseModel):
    """Response model for RAG query endpoint."""

    query_text: str = Field(
        description="Original query text"
    )
    context_chunks: List[ContextChunk] = Field(
        description="Retrieved relevant context chunks"
    )
    total_results: int = Field(
        description="Number of results returned"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Query timestamp (UTC)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query_text": "How to detect prompt injection attacks?",
                    "context_chunks": [
                        {
                            "source_id": "AID-D-002.001",
                            "tactic": "Detect",
                            "text": "Sub-Technique: Prompt Injection Detection...",
                            "metadata": {"type": "subtechnique", "name": "Prompt Injection Detection"},
                            "score": 0.156
                        }
                    ],
                    "total_results": 1,
                    "timestamp": "2025-11-09T10:30:00Z"
                }
            ]
        }
    }


class SyncStatus(BaseModel):
    """Model for synchronization status information."""

    last_synced_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last successful sync (UTC)"
    )
    current_commit_sha: Optional[str] = Field(
        default=None,
        description="Current GitHub commit SHA",
        pattern=r"^[a-f0-9]{40}$"
    )
    total_documents: Optional[int] = Field(
        default=None,
        description="Total number of indexed documents",
        ge=0
    )
    is_syncing: bool = Field(
        default=False,
        description="Whether a sync operation is currently in progress"
    )


class StatusResponse(BaseModel):
    """Response model for service status endpoint."""

    status: str = Field(
        description="Service status (online, syncing, error)"
    )
    sync_info: Optional[SyncStatus] = Field(
        default=None,
        description="Synchronization status information"
    )
    message: str = Field(
        description="Human-readable status message"
    )
    version: str = Field(
        description="Service version"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Status check timestamp (UTC)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "online",
                    "sync_info": {
                        "last_synced_at": "2025-11-09T09:00:00Z",
                        "current_commit_sha": "abc123def456...",
                        "total_documents": 1250,
                        "is_syncing": False
                    },
                    "message": "Service is online and synchronized",
                    "version": "1.0.0",
                    "timestamp": "2025-11-09T10:30:00Z"
                }
            ]
        }
    }


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: str = Field(
        description="Health status (healthy, unhealthy)"
    )
    checks: Dict[str, bool] = Field(
        description="Individual health check results"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Health check timestamp (UTC)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "checks": {
                        "database": True,
                        "embedding_model": True,
                        "sync_service": True
                    },
                    "timestamp": "2025-11-09T10:30:00Z"
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str = Field(
        description="Error type/code"
    )
    message: str = Field(
        description="Human-readable error message"
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional error details (only in development mode)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Error timestamp (UTC)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "error": "VALIDATION_ERROR",
                    "message": "Query text contains invalid characters",
                    "details": None,
                    "timestamp": "2025-11-09T10:30:00Z"
                }
            ]
        }
    }
