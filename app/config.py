"""
Configuration module for AIDEFEND MCP Service.
Uses Pydantic BaseSettings for environment variable management.
"""

import logging
from pathlib import Path
from typing import List, Optional, Literal
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get logger for config warnings
logger = logging.getLogger(__name__)

# Project root directory (parent of 'app' directory)
# This ensures paths are resolved relative to project root, not cwd
PROJECT_ROOT = Path(__file__).parent.parent.resolve()


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    IMPORTANT: All paths are resolved relative to PROJECT_ROOT to ensure
    consistent behavior regardless of where the service is launched from.
    This is critical for Claude Desktop integration where cwd may vary.
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
    LOCAL_FRAMEWORK_PATH: Optional[Path] = Field(
        default=None,
        description="Optional local AIDEFEND framework repository path to use instead of GitHub sync"
    )

    # AIDEFEND framework files to sync
    AIDEFEND_FILES: List[str] = Field(
        default=[
            "aidefend-intro.js",  # For extracting framework version
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
    # All paths resolved relative to PROJECT_ROOT for consistent behavior
    DATA_PATH: Path = Field(
        default=PROJECT_ROOT / "data",
        description="Root data directory"
    )
    DB_PATH: Path = Field(
        default=PROJECT_ROOT / "data" / "aidefend_kb.lancedb",
        description="LanceDB database path"
    )
    RAW_PATH: Path = Field(
        default=PROJECT_ROOT / "data" / "raw_content",
        description="Directory for raw downloaded files"
    )
    VERSION_FILE: Path = Field(
        default=PROJECT_ROOT / "data" / "local_version.json",
        description="File storing current sync version"
    )
    LOG_PATH: Optional[Path] = Field(
        default=PROJECT_ROOT / "data" / "logs" / "aidefend_mcp.log",
        description="Log file path (None to disable file logging)"
    )

    # Embedding Configuration
    EMBEDDING_MODEL: str = Field(
        default="Xenova/multilingual-e5-base",
        description="FastEmbed model for embeddings (ONNX-based, multilingual support)"
    )
    EMBEDDING_DIMENSION: int = Field(
        default=768,
        description="Embedding vector dimension (768 for multilingual-e5-base)"
    )

    # Cache Schema Version
    # Increment when metadata structure changes require cache rebuild
    # Version History:
    # 1.0 (2025-11): Initial version with JSON array format for pillar/phase
    CACHE_SCHEMA_VERSION: str = Field(
        default="1.0",
        description="Cache schema version for automatic invalidation on breaking changes"
    )

    # Fuzzy Matching Configuration (for classify_threat tool)
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
    AUTO_CREATE_INDEX: bool = Field(
        default=True,
        description="Automatically create LanceDB vector index after first sync for 2-5x faster queries"
    )
    ENABLE_AUTO_SYNC: bool = Field(
        default=True,
        description="Enable automatic background sync"
    )
    LOCK_MAX_AGE_SECONDS: int = Field(
        default=1800,
        ge=300,
        le=7200,
        description="Maximum age (in seconds) for lock file before considered stale (30 minutes default, min 5 min, max 2 hours)"
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
        default=1500,
        ge=100,
        le=5000,
        description="Maximum query text length (aligned with multilingual-e5-base model's 512 token limit)"
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

    # Chunked Query Configuration (for long text processing)
    MAX_TOTAL_QUERY_LENGTH: int = Field(
        default=5000,
        ge=1500,
        le=50000,
        description="Maximum total query length for chunked search (conservative: 5000 chars)"
    )
    MAX_CHUNKS: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of chunks for long queries (conservative: 5 chunks)"
    )
    MAX_CHUNKS_PROCESSING_TIME: int = Field(
        default=15,
        ge=5,
        le=60,
        description="Maximum processing time in seconds for chunked queries (conservative: 15s)"
    )
    CHUNK_SIZE: int = Field(
        default=1200,
        ge=500,
        le=2000,
        description="Target size for each chunk in characters (must be < MAX_QUERY_LENGTH)"
    )
    CHUNK_OVERLAP: int = Field(
        default=200,
        ge=0,
        le=500,
        description="Overlap between chunks to preserve context (chars)"
    )

    # Authentication Configuration
    AUTH_MODE: Literal["no_auth", "api_key"] = Field(
        default="no_auth",
        description=(
            "Authentication mode for REST API. "
            "Options: 'no_auth' (local development only), 'api_key' (production deployment). "
            "MCP mode does not use HTTP authentication (secured via file permissions)."
        )
    )
    AIDEFEND_API_KEY: Optional[str] = Field(
        default=None,
        description=(
            "API Key for authentication when AUTH_MODE='api_key'. "
            "Generate using: python scripts/generate_api_key.py. "
            "Required when AUTH_MODE='api_key', ignored when AUTH_MODE='no_auth'."
        )
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

    @field_validator("DATA_PATH", "DB_PATH", "RAW_PATH", "VERSION_FILE", "LOG_PATH", "LOCAL_FRAMEWORK_PATH")
    @classmethod
    def validate_paths(cls, v: Optional[Path]) -> Optional[Path]:
        """
        Ensure paths are absolute.

        Paths are already resolved relative to PROJECT_ROOT in defaults,
        but this validator handles custom paths from environment variables.
        """
        if v is None:
            return None
        # If path is relative, resolve it relative to PROJECT_ROOT
        if not v.is_absolute():
            return (PROJECT_ROOT / v).resolve()
        return v

    @model_validator(mode='after')
    def validate_local_framework_path(self):
        """Validate optional local framework source path."""
        if self.LOCAL_FRAMEWORK_PATH is None:
            return self

        if not self.LOCAL_FRAMEWORK_PATH.exists():
            raise ValueError(
                f"LOCAL_FRAMEWORK_PATH does not exist: {self.LOCAL_FRAMEWORK_PATH}"
            )
        if not self.LOCAL_FRAMEWORK_PATH.is_dir():
            raise ValueError(
                f"LOCAL_FRAMEWORK_PATH must be a directory: {self.LOCAL_FRAMEWORK_PATH}"
            )
        return self

    @model_validator(mode='after')
    def validate_api_host_with_auth(self):
        """
        Validate API host binding with authentication mode.

        Security Policy: Binding to 0.0.0.0 (all interfaces) requires authentication.
        This prevents accidental exposure of unauthenticated service to network.

        Note: Uses model_validator(mode='after') to ensure all fields are validated
        before cross-field validation is performed.
        """
        # Check if binding to external interfaces (0.0.0.0 or empty string)
        is_external_binding = self.API_HOST in ["0.0.0.0", ""]  # nosec B104

        if is_external_binding and self.AUTH_MODE == "no_auth":
            raise ValueError(
                "\n" + "=" * 70 + "\n"
                "SECURITY ERROR: Cannot bind to external IP without authentication!\n\n"
                f"  Current settings:\n"
                f"    - API_HOST: {self.API_HOST} (exposes service to network)\n"
                f"    - AUTH_MODE: {self.AUTH_MODE} (no authentication required)\n\n"
                f"  This configuration exposes your service WITHOUT authentication.\n\n"
                f"  Please choose one of the following:\n"
                f"    1. Bind to localhost only:\n"
                f"         Set API_HOST=127.0.0.1 in .env\n"
                f"    2. Enable authentication:\n"
                f"         Set AUTH_MODE=api_key in .env\n"
                f"         Set AIDEFEND_API_KEY=<your-secret-key>\n"
                f"         (Generate key: python scripts/generate_api_key.py)\n\n"
                f"  See SECURITY.md for deployment best practices.\n"
                + "=" * 70
            )

        return self

    @field_validator("AIDEFEND_API_KEY")
    @classmethod
    def validate_api_key_requirement(cls, v: Optional[str], info) -> Optional[str]:
        """
        Validate API key presence when api_key mode is enabled.

        Security Policy: api_key mode requires a configured API key.
        """
        auth_mode = info.data.get("AUTH_MODE", "no_auth")

        if auth_mode == "api_key":
            if not v or len(v.strip()) == 0:
                raise ValueError(
                    "\n" + "=" * 70 + "\n"
                    "CONFIGURATION ERROR: API Key required for api_key mode!\n\n"
                    f"  Current settings:\n"
                    f"    - AUTH_MODE: {auth_mode} (requires authentication)\n"
                    f"    - AIDEFEND_API_KEY: <not set>\n\n"
                    f"  Please set AIDEFEND_API_KEY in .env:\n\n"
                    f"  1. Generate a secure API key:\n"
                    f"       python scripts/generate_api_key.py\n\n"
                    f"  2. Add to .env file:\n"
                    f"       AIDEFEND_API_KEY=<generated-key>\n\n"
                    f"  See SECURITY.md for API key management best practices.\n"
                    + "=" * 70
                )

        return v

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_with_auth(cls, v: List[str], info) -> List[str]:
        """
        Validate CORS configuration with authentication mode.

        Warning: Permissive CORS in api_key mode may expose API keys via browser requests.
        """
        auth_mode = info.data.get("AUTH_MODE", "no_auth")

        if auth_mode == "api_key":
            # Check for wildcard origins
            has_wildcard = any(
                origin == "*" or
                origin.startswith("http://*") or
                origin.startswith("https://*") or
                origin == "http://*" or
                origin == "https://*"
                for origin in v
            )

            if has_wildcard:
                logger.warning(
                    "\n" + "=" * 70 + "\n"
                    "SECURITY WARNING: Permissive CORS with authentication enabled!\n\n"
                    f"  Current settings:\n"
                    f"    - AUTH_MODE: {auth_mode} (authentication required)\n"
                    f"    - CORS_ORIGINS: {v} (allows broad access)\n\n"
                    f"  Recommendation:\n"
                    f"    Restrict CORS_ORIGINS to specific domains in production:\n"
                    f"      CORS_ORIGINS=[\"https://your-domain.com\"]\n\n"
                    f"  This prevents unauthorized websites from making requests\n"
                    f"  with users' API keys via browser.\n"
                    + "=" * 70
                )

        return v

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

    @property
    def sync_source_mode(self) -> str:
        """Return the active sync source mode."""
        return "local" if self.LOCAL_FRAMEWORK_PATH else "github"

    @property
    def local_framework_tactics_path(self) -> Optional[Path]:
        """Return local tactics directory when local source mode is enabled."""
        if self.LOCAL_FRAMEWORK_PATH is None:
            return None
        return self.LOCAL_FRAMEWORK_PATH / self.GITHUB_TACTICS_PATH

    def get_raw_file_url(self, filename: str, commit_sha: str) -> str:
        """
        Construct URL for raw file download.

        Args:
            filename: Name of the file
            commit_sha: Git commit SHA

        Returns:
            Full URL to raw file
        """
        # aidefend-intro.js is at root level, other files are in tactics/ subfolder
        if filename == "aidefend-intro.js":
            return f"{self.github_raw_base_url}/{commit_sha}/{filename}"
        else:
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
