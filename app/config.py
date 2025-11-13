"""
Configuration module for AIDEFEND MCP Service.
Uses Pydantic BaseSettings for environment variable management.
"""

from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    # GitHub Repository Configuration
    GITHUB_REPO_OWNER: str = Field(
        default="edward-playground",
        description="GitHub repository owner"
    )
    GITHUB_REPO_NAME: str = Field(
        default="aidefense-framework",
        description="GitHub repository name"
    )
    GITHUB_BRANCH: str = Field(
        default="main",
        description="GitHub branch to sync from"
    )
    GITHUB_TACTICS_PATH: str = Field(
        default="tactics",
        description="Path to tactics directory in repository"
    )

    # AIDEFEND framework files to sync
    AIDEFEND_FILES: List[str] = Field(
        default=[
            "model.js",
            "harden.js",
            "detect.js",
            "isolate.js",
            "deceive.js",
            "evict.js",
            "restore.js"
        ],
        description="List of .js files to sync from tactics directory"
    )

    # Local Storage Paths
    DATA_PATH: Path = Field(
        default=Path("./data"),
        description="Root data directory"
    )
    DB_PATH: Path = Field(
        default=Path("./data/aidefend_kb.lancedb"),
        description="LanceDB database path"
    )
    RAW_PATH: Path = Field(
        default=Path("./data/raw_content"),
        description="Directory for raw downloaded files"
    )
    VERSION_FILE: Path = Field(
        default=Path("./data/local_version.json"),
        description="File storing current sync version"
    )
    LOG_PATH: Optional[Path] = Field(
        default=Path("./data/logs/aidefend_mcp.log"),
        description="Log file path (None to disable file logging)"
    )

    # Embedding Configuration
    EMBEDDING_MODEL: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="FastEmbed model for embeddings (ONNX-based, lightweight)"
    )
    EMBEDDING_DIMENSION: int = Field(
        default=384,
        description="Embedding vector dimension (384 for bge-small-en-v1.5)"
    )

    # LLM Configuration (for compliance mapping and other AI features)
    ANTHROPIC_API_KEY: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude (required for LLM-based compliance mapping)"
    )
    CLAUDE_MODEL: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Claude model to use for LLM features"
    )
    CLAUDE_MAX_TOKENS: int = Field(
        default=2048,
        ge=256,
        le=4096,
        description="Maximum tokens for Claude responses"
    )

    # LLM Fallback Configuration (for classify_threat tool)
    ENABLE_LLM_FALLBACK: bool = Field(
        default=False,
        description="Enable LLM semantic inference fallback for threat classification (requires ANTHROPIC_API_KEY)"
    )
    LLM_FALLBACK_THRESHOLD: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold before triggering LLM fallback (0.0-1.0)"
    )
    ENABLE_FUZZY_MATCHING: bool = Field(
        default=True,
        description="Enable fuzzy string matching for typo tolerance in threat classification (free, zero cost)"
    )
    FUZZY_MATCH_CUTOFF: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score for fuzzy matches (0.0-1.0)"
    )

    # Sync Configuration
    SYNC_INTERVAL_SECONDS: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Sync interval in seconds (1 hour default, min 1 min, max 24 hours)"
    )
    SYNC_TIMEOUT_SECONDS: int = Field(
        default=300,
        ge=30,
        le=1800,
        description="Timeout for sync operations (5 minutes default)"
    )
    ENABLE_AUTO_SYNC: bool = Field(
        default=True,
        description="Enable automatic background sync"
    )

    # API Configuration
    API_HOST: str = Field(
        default="127.0.0.1",
        description="API server host"
    )
    API_PORT: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="API server port"
    )
    API_WORKERS: int = Field(
        default=1,
        ge=1,
        le=1,
        description="Number of API workers (MUST be 1 for sync safety - asyncio.Lock + LanceDB write conflicts)"
    )

    # Security Configuration
    MAX_QUERY_LENGTH: int = Field(
        default=2000,
        ge=100,
        le=5000,
        description="Maximum query text length"
    )
    MAX_TOP_K: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Maximum number of search results"
    )
    DEFAULT_TOP_K: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Default number of search results"
    )
    ENABLE_RATE_LIMITING: bool = Field(
        default=True,
        description="Enable rate limiting on API endpoints"
    )
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=60,
        ge=1,
        le=1000,
        description="Maximum requests per minute per IP"
    )

    # CORS Configuration
    ENABLE_CORS: bool = Field(
        default=True,
        description="Enable CORS middleware"
    )
    CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:*", "https://localhost:*"],
        description="Allowed CORS origins"
    )

    # Logging Configuration
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    ENABLE_FILE_LOGGING: bool = Field(
        default=True,
        description="Enable logging to file"
    )

    # Security Headers
    ENABLE_SECURITY_HEADERS: bool = Field(
        default=True,
        description="Enable security headers middleware"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore extra environment variables
    )

    @field_validator("API_WORKERS")
    @classmethod
    def validate_workers(cls, v: int) -> int:
        """Validate API workers count - MUST be 1 for sync safety."""
        if v > 1:
            raise ValueError(
                "API_WORKERS must be 1. Multi-worker mode is NOT supported due to "
                "asyncio.Lock limitations and LanceDB write conflicts. "
                "Using multiple workers will cause data corruption."
            )
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")
        return v

    @field_validator("DATA_PATH", "DB_PATH", "RAW_PATH", "VERSION_FILE", "LOG_PATH")
    @classmethod
    def validate_paths(cls, v: Optional[Path]) -> Optional[Path]:
        """Ensure paths are absolute and resolve them."""
        if v is None:
            return None
        return v.resolve()

    @property
    def github_repo_api_url(self) -> str:
        """Construct GitHub API repository URL."""
        return f"https://api.github.com/repos/{self.GITHUB_REPO_OWNER}/{self.GITHUB_REPO_NAME}"

    @property
    def github_repo_path(self) -> str:
        """Construct GitHub repository path (owner/repo)."""
        return f"{self.GITHUB_REPO_OWNER}/{self.GITHUB_REPO_NAME}"

    @property
    def github_raw_base_url(self) -> str:
        """Construct GitHub raw content base URL."""
        return f"https://raw.githubusercontent.com/{self.GITHUB_REPO_OWNER}/{self.GITHUB_REPO_NAME}"

    def get_raw_file_url(self, filename: str, commit_sha: str) -> str:
        """
        Construct URL for raw file download.

        Args:
            filename: Name of the file
            commit_sha: Git commit SHA

        Returns:
            Full URL to raw file
        """
        return f"{self.github_raw_base_url}/{commit_sha}/{self.GITHUB_TACTICS_PATH}/{filename}"

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.DATA_PATH.mkdir(parents=True, exist_ok=True)
        self.RAW_PATH.mkdir(parents=True, exist_ok=True)
        if self.LOG_PATH:
            self.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


# Create singleton settings instance
settings = Settings()

# Ensure directories exist on import
settings.ensure_directories()
