"""
Pydantic schemas for API request/response validation.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


from pydantic import BaseModel, Field, field_validator


from app.config import settings
from app.security import validate_query_text, validate_top_k, validate_chunked_query


def _utc_now() -> datetime:
    """Return current UTC time. Replacement for deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc)


class QueryRequest(BaseModel):
    """Request model for RAG query endpoint."""

    query_text: str = Field(
        ...,
        min_length=3,
        max_length=settings.MAX_TOTAL_QUERY_LENGTH,
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
        if len(v) > settings.MAX_QUERY_LENGTH:
            sanitized, _ = validate_chunked_query(v)
            return sanitized
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
        default_factory=_utc_now,
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
        description="Current GitHub commit SHA"
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
        default_factory=_utc_now,
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
        default_factory=_utc_now,
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
        default_factory=_utc_now,
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
        """Validate technique ID list (empty array allowed for baseline analysis)."""
        if len(v) > 100:
            raise ValueError("Too many techniques (max 100)")
        # Normalize IDs (skip if empty for baseline analysis)
        if not v:
            return []
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
        description="Covered threats grouped by framework key"
    )
    coverage_rate: Dict[str, float] = Field(
        description="Coverage percentage for each framework"
    )
    framework_totals: Dict[str, int] = Field(
        description="Total normalized threat items available in each framework"
    )
    by_technique: List[Dict[str, Any]] = Field(
        description="Detailed threat coverage per technique"
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
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
                        "owasp": ["LLM01", "ML02:2023", "ASI03:2026"],
                        "owasp_llm": ["LLM01"],
                        "owasp_ml": ["ML02:2023"],
                        "owasp_agentic": ["ASI03:2026"],
                        "atlas": ["AML.T0020", "AML.T0043"],
                        "maestro": []
                    },
                    "coverage_rate": {
                        "owasp": 0.1,
                        "owasp_llm": 0.1,
                        "owasp_ml": 0.1,
                        "owasp_agentic": 0.1,
                        "atlas": 0.047,
                        "maestro": 0.0
                    },
                    "framework_totals": {
                        "owasp": 30,
                        "owasp_llm": 10,
                        "owasp_ml": 10,
                        "owasp_agentic": 10,
                        "atlas": 43,
                        "maestro": 54
                    },
                    "by_technique": [
                        {
                            "technique_id": "AID-D-001",
                            "technique_name": "Input Validation",
                            "tactic": "Detect",
                            "threats_covered": {
                                "owasp": ["LLM01"],
                                "owasp_llm": ["LLM01"],
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
    detail_level: str = Field(
        default="basic",
        description="Level of detail: 'basic' (IDs only), 'standard' (brief summaries for top 5), 'detailed' (full summaries + code for top 5)",
        examples=["basic", "standard", "detailed"]
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

    @field_validator("detail_level")
    @classmethod
    def validate_detail_level(cls, v: str) -> str:
        """Validate detail_level parameter."""
        allowed_values = ["basic", "standard", "detailed"]
        if v not in allowed_values:
            raise ValueError(f"detail_level must be one of {allowed_values}")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "implemented_techniques": ["AID-D-001", "AID-H-002"],
                    "exclude_tactics": ["Model"],
                    "top_k": 10,
                    "detail_level": "basic"
                },
                {
                    "implemented_techniques": [],
                    "exclude_tactics": [],
                    "top_k": 5,
                    "detail_level": "detailed"
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
    actionable_strategies: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Detailed implementation strategies for top 5 recommendations (only when detail_level='standard' or 'detailed')"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Compound tool metadata (only when detail_level='standard' or 'detailed')"
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
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


# ===== Security Posture Tool Schemas =====

class SecurityPostureRequest(BaseModel):
    """Request model for security posture analysis endpoint."""

    implemented_techniques: List[str] = Field(
        ...,
        min_length=1,
        max_length=200,
        description="List of implemented AIDEFEND technique IDs",
        examples=[["AID-H-001", "AID-D-001", "AID-I-001"]]
    )
    view: str = Field(
        default="both",
        description="Analysis view: 'both', 'technical', or 'threat'"
    )
    system_type: Optional[str] = Field(
        default=None,
        description="Optional system type for context-aware analysis"
    )

    @field_validator("implemented_techniques")
    @classmethod
    def validate_technique_ids(cls, v: List[str]) -> List[str]:
        """Validate technique ID list."""
        if not v:
            raise ValueError("implemented_techniques cannot be empty")
        if len(v) > 200:
            raise ValueError("Too many techniques (max 200)")
        return [tid.strip().upper() for tid in v]

    @field_validator("view")
    @classmethod
    def validate_view(cls, v: str) -> str:
        """Validate view parameter."""
        valid_views = ["both", "technical", "threat"]
        if v not in valid_views:
            raise ValueError(f"view must be one of: {', '.join(valid_views)}")
        return v

    @field_validator("system_type")
    @classmethod
    def validate_system_type(cls, v: Optional[str]) -> Optional[str]:
        """Validate system_type parameter."""
        if v is None:
            return v
        valid_types = ["chatbot", "rag", "agent", "classifier", "generative", "multimodal"]
        if v not in valid_types:
            raise ValueError(f"system_type must be one of: {', '.join(valid_types)}")
        return v


# ===== Technique Comparison Tool Schemas =====

class TechniqueComparisonRequest(BaseModel):
    """Request model for technique comparison endpoint."""

    technique_ids: List[str] = Field(
        ...,
        min_length=2,
        max_length=10,
        description="List of technique IDs to compare (2-10)",
        examples=[["AID-H-001", "AID-D-002", "AID-I-001"]]
    )
    include_recommendations: bool = Field(
        default=True,
        description="Include prioritization recommendations"
    )

    @field_validator("technique_ids")
    @classmethod
    def validate_technique_ids(cls, v: List[str]) -> List[str]:
        """Validate technique ID list."""
        if len(v) < 2:
            raise ValueError("At least 2 technique IDs required for comparison")
        if len(v) > 10:
            raise ValueError("Too many techniques (max 10)")
        return [tid.strip().upper() for tid in v]


# ===== Incident Response Tool Schemas =====

class IncidentPlaybookRequest(BaseModel):
    """Request model for incident response playbook endpoint."""

    incident_description: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Free-text description of the AI security incident",
        examples=["Suspicious prompt injection attempts detected in production chatbot"]
    )
    include_defense_techniques: bool = Field(
        default=True,
        description="Include specific AIDEFEND defense techniques in playbook"
    )

    @field_validator("incident_description")
    @classmethod
    def validate_incident_description(cls, v: str) -> str:
        """Validate incident description."""
        if not v or not v.strip():
            raise ValueError("incident_description cannot be empty")
        v = v.strip()
        if len(v) < 10:
            raise ValueError("incident_description too short (min 10 characters)")
        if len(v) > 1000:
            raise ValueError("incident_description too long (max 1000 characters)")
        return v


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
        description="Normalized threat IDs grouped by framework key"
    )
    threat_details: List[Dict[str, Any]] = Field(
        description="Detailed threat information for each match"
    )
    recommended_actions: List[Dict[str, Any]] = Field(
        description="Suggested followup tool calls for further investigation"
    )
    timestamp: datetime = Field(
        default_factory=_utc_now,
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
