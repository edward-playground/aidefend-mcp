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
    framework_version: Optional[str] = Field(
        default=None,
        description="AIDEFEND framework semantic version (e.g., '1.20251107')"
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


# ===== Threat Coverage Tool Schemas =====

class ThreatCoverageRequest(BaseModel):
    """Request model for threat coverage analysis endpoint."""

    implemented_techniques: List[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of implemented AIDEFEND technique IDs",
        examples=[["AID-D-001", "AID-H-002", "AID-I-003"]]
    )

    @field_validator("implemented_techniques")
    @classmethod
    def validate_technique_ids(cls, v: List[str]) -> List[str]:
        """Validate technique ID list."""
        if not v:
            raise ValueError("implemented_techniques cannot be empty")
        if len(v) > 100:
            raise ValueError("Too many techniques (max 100)")
        # Normalize IDs
        return [tid.strip().upper() for tid in v]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "implemented_techniques": ["AID-D-001", "AID-H-002", "AID-I-003"]
                }
            ]
        }
    }


class ThreatCoverageResponse(BaseModel):
    """Response model for threat coverage analysis endpoint."""

    input_count: int = Field(
        description="Number of techniques provided in request",
        ge=0
    )
    valid_count: int = Field(
        description="Number of valid techniques found in database",
        ge=0
    )
    invalid_count: int = Field(
        description="Number of invalid/unknown technique IDs",
        ge=0
    )
    invalid_techniques: List[str] = Field(
        description="List of technique IDs that were not found"
    )
    covered: Dict[str, List[str]] = Field(
        description="Covered threats grouped by framework (owasp, atlas, maestro)"
    )
    coverage_rate: Dict[str, float] = Field(
        description="Coverage percentage for each framework"
    )
    by_technique: List[Dict[str, Any]] = Field(
        description="Detailed threat coverage per technique"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Analysis timestamp (UTC)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "input_count": 3,
                    "valid_count": 3,
                    "invalid_count": 0,
                    "invalid_techniques": [],
                    "covered": {
                        "owasp": ["LLM01", "LLM02", "LLM03"],
                        "atlas": ["AML.T0020", "AML.T0043"],
                        "maestro": []
                    },
                    "coverage_rate": {
                        "owasp": 0.3,
                        "atlas": 0.047,
                        "maestro": 0.0
                    },
                    "by_technique": [
                        {
                            "technique_id": "AID-D-001",
                            "technique_name": "Input Validation",
                            "tactic": "Detect",
                            "threats_covered": {
                                "owasp": ["LLM01"],
                                "atlas": [],
                                "maestro": []
                            }
                        }
                    ],
                    "timestamp": "2025-11-12T10:30:00Z"
                }
            ]
        }
    }


# ===== Implementation Plan Tool Schemas =====

class ImplementationPlanRequest(BaseModel):
    """Request model for implementation plan recommendation endpoint."""

    implemented_techniques: Optional[List[str]] = Field(
        default=None,
        description="List of already implemented technique IDs (optional)",
        examples=[["AID-D-001", "AID-H-002"]]
    )
    exclude_tactics: Optional[List[str]] = Field(
        default=None,
        description="List of tactics to exclude from recommendations (optional)",
        examples=[["Model", "Harden"]]
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Number of recommendations to return (1-20)"
    )

    @field_validator("implemented_techniques")
    @classmethod
    def validate_implemented_techniques(cls, v: Optional[List[str]]) -> List[str]:
        """Validate and normalize implemented techniques list."""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("implemented_techniques must be a list")
        return [tid.strip().upper() for tid in v]

    @field_validator("exclude_tactics")
    @classmethod
    def validate_exclude_tactics(cls, v: Optional[List[str]]) -> List[str]:
        """Validate and normalize exclude tactics list."""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("exclude_tactics must be a list")
        return [tactic.strip().title() for tactic in v]

    @field_validator("top_k")
    @classmethod
    def validate_top_k_value(cls, v: int) -> int:
        """Validate top_k parameter."""
        if v < 1 or v > 20:
            raise ValueError("top_k must be between 1 and 20")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "implemented_techniques": ["AID-D-001", "AID-H-002"],
                    "exclude_tactics": ["Model"],
                    "top_k": 10
                }
            ]
        }
    }


class ImplementationPlanResponse(BaseModel):
    """Response model for implementation plan recommendation endpoint."""

    input: Dict[str, Any] = Field(
        description="Summary of input parameters"
    )
    recommendations: List[Dict[str, Any]] = Field(
        description="Ranked list of recommended techniques with scores"
    )
    categories: Dict[str, List[str]] = Field(
        description="Recommendations categorized by priority (quick_wins, high_priority, standard)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Plan generation timestamp (UTC)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "input": {
                        "implemented_count": 2,
                        "exclude_tactics": ["Model"],
                        "top_k": 10
                    },
                    "recommendations": [
                        {
                            "rank": 1,
                            "technique_id": "AID-D-014",
                            "technique_name": "Prompt Injection Detection",
                            "tactic": "Detect",
                            "score": 8.5,
                            "score_breakdown": {
                                "threat_importance": 3.0,
                                "ease_of_implementation": 2.0,
                                "phase_weight": 1.5,
                                "pillar_weight": 1.5,
                                "tool_ecosystem": 0.5
                            },
                            "reasoning": "Covers high-risk threats; Has open-source tools available; Detection adds defense-in-depth",
                            "has_opensource_tools": True,
                            "pillar": "Detect",
                            "phase": "Development"
                        }
                    ],
                    "categories": {
                        "quick_wins": ["AID-D-014", "AID-D-015"],
                        "high_priority": ["AID-D-014", "AID-H-010"],
                        "standard": ["AID-I-005", "AID-R-001"]
                    },
                    "timestamp": "2025-11-12T10:30:00Z"
                }
            ]
        }
    }


# ===== Classify Threat Tool Schemas =====

class ClassifyThreatRequest(BaseModel):
    """Request model for threat classification endpoint."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Input text containing threat-related content",
        examples=["Recent prompt injection attack detected in production"]
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of keywords to return (1-10)"
    )

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Validate input text."""
        if not v or not v.strip():
            raise ValueError("text cannot be empty")
        if len(v) > 10000:
            raise ValueError("text too long (max 10000 characters)")
        return v.strip()

    @field_validator("top_k")
    @classmethod
    def validate_top_k_value(cls, v: int) -> int:
        """Validate top_k parameter."""
        if v < 1 or v > 10:
            raise ValueError("top_k must be between 1 and 10")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "text": "We detected a prompt injection attack that bypassed our input validation",
                    "top_k": 5
                }
            ]
        }
    }


class ClassifyThreatResponse(BaseModel):
    """Response model for threat classification endpoint."""

    source: str = Field(
        description="Match source: 'static_keyword' (direct match), 'fuzzy_match' (typo-tolerant), or 'no_match' (no threats found)"
    )
    input_text_preview: str = Field(
        description="First 100 characters of input text"
    )
    keywords_found: List[Dict[str, Any]] = Field(
        description="List of matched threat keywords with confidence scores"
    )
    normalized_threats: Dict[str, List[str]] = Field(
        description="Normalized threat IDs grouped by framework (owasp, atlas, maestro)"
    )
    threat_details: List[Dict[str, Any]] = Field(
        description="Detailed threat information for each match"
    )
    recommended_actions: List[Dict[str, Any]] = Field(
        description="Suggested followup tool calls for further investigation"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Classification timestamp (UTC)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "source": "static_keyword",
                    "input_text_preview": "We detected a prompt injection attack that bypassed our input validation",
                    "keywords_found": [
                        {
                            "keyword": "prompt injection",
                            "match_type": "primary",
                            "confidence": 0.9
                        },
                        {
                            "keyword": "insecure output",
                            "match_type": "alias",
                            "confidence": 0.77
                        }
                    ],
                    "normalized_threats": {
                        "owasp": ["LLM01", "LLM02"],
                        "atlas": [],
                        "maestro": []
                    },
                    "threat_details": [
                        {
                            "threat_id": "OWASP-LLM01",
                            "threat_name": "Prompt Injection",
                            "confidence": 0.9,
                            "matched_keyword": "prompt injection",
                            "match_type": "primary"
                        }
                    ],
                    "recommended_actions": [
                        {
                            "tool": "get_defenses_for_threat",
                            "args": {"threat_id": "LLM01"},
                            "reason": "Find defense techniques for LLM01"
                        },
                        {
                            "tool": "get_quick_reference",
                            "args": {"topic": "prompt injection", "max_items": 10},
                            "reason": "Get actionable mitigation steps for prompt injection"
                        }
                    ],
                    "timestamp": "2025-11-12T10:30:00Z"
                }
            ]
        }
    }
