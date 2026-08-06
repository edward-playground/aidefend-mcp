"""
Configuration module for AIDEFEND MCP Service.
Uses Pydantic BaseSettings for environment variable management.
"""

import ipaddress
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional, Literal
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get logger for config warnings
logger = logging.getLogger(__name__)

# Project root directory (parent of 'app' directory)
# This ensures paths are resolved relative to project root, not cwd
PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def _resolve_default_data_path(project_root: Path = PROJECT_ROOT) -> Path:
    """Choose a writable default without making source checkouts surprising.

    A source checkout keeps its historical repo data location. A wheel lives
    under site-packages, which is commonly read-only for the user who runs the
    installed console script, so installed copies use the platform's per-user
    application-data directory instead.
    """
    if (project_root / "pyproject.toml").is_file() and (project_root / "app").is_dir():
        return project_root / "data"

    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "AIDEFEND" / "aidefend-mcp"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "aidefend-mcp"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / "aidefend-mcp"


DEFAULT_DATA_PATH = _resolve_default_data_path()
IS_SOURCE_CHECKOUT = (
    (PROJECT_ROOT / "pyproject.toml").is_file()
    and (PROJECT_ROOT / "app").is_dir()
)
RELATIVE_STORAGE_BASE = PROJECT_ROOT if IS_SOURCE_CHECKOUT else DEFAULT_DATA_PATH


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    IMPORTANT: Source-checkout paths resolve relative to the repository.
    Installed-wheel storage resolves under the platform's per-user application
    data directory, never under a potentially read-only site-packages tree.
    This keeps Claude Desktop behavior independent of its working directory.
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

    # Legacy digest fallback retained for configuration compatibility. Runtime
    # sync discovers the current ordered tactic list from framework main.js.
    AIDEFEND_FILES: List[str] = Field(
        default=[
            "aidefend-intro.js",  # Required framework release metadata
            "model.js",
            "harden.js",
            "detect.js",
            "isolate.js",
            "deceive.js",
            "evict.js",
            "restore.js"
        ],
        description=(
            "Legacy source-file list used only when a digest caller does not provide the "
            "main.js-derived manifest; runtime sync discovers tactics dynamically"
        )
    )

    # Local Storage Paths
    # All paths resolved relative to PROJECT_ROOT for consistent behavior
    DATA_PATH: Path = Field(
        default=DEFAULT_DATA_PATH,
        description="Root data directory"
    )
    DB_PATH: Path = Field(
        default=DEFAULT_DATA_PATH / "aidefend_kb.lancedb",
        description="LanceDB database path"
    )
    RAW_PATH: Path = Field(
        default=DEFAULT_DATA_PATH / "raw_content",
        description="Directory for raw downloaded files"
    )
    VERSION_FILE: Path = Field(
        default=DEFAULT_DATA_PATH / "local_version.json",
        description="File storing current sync version"
    )
    LOG_PATH: Optional[Path] = Field(
        default=DEFAULT_DATA_PATH / "logs" / "aidefend_mcp.log",
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
    MODEL_CACHE_DIR: Optional[str] = Field(
        default=None,
        description=(
            "Directory for the FastEmbed/ONNX model cache. Default (None) uses FastEmbed's "
            "own cache location (unchanged behavior). Set to a path on a persisted volume "
            "(in Docker: /app/data/models) so the ~280MB model is downloaded once and "
            "survives container restarts instead of being re-fetched every time."
        )
    )

    # Cache Schema Version
    # Increment when metadata structure changes require cache rebuild
    # Version History:
    # 1.0 (2025-11): Initial version with JSON array format for pillar/phase
    # 2.0 (2026-07): Preserve framework warnings in the searchable index
    # 3.0 (2026-07): Support framework schema 2.3 (canonical guidance IDs,
    #                source-available tools, scope boundaries, actionable flags)
    # 3.1 (2026-07): Rebuild scope-aware embedding text and canonicalize every
    #                list field as a JSON array in LanceDB.
    # 3.2 (2026-07): Keep scope and all tool inventories inside the embedding
    #                token window and verify exact tokenizer visibility.
    # 3.3 (2026-08): Persist a generation ID in every Lance row and atomically
    #                bind table activation/rollback to version metadata.
    CACHE_SCHEMA_VERSION: str = Field(
        default="3.3",
        description="Cache schema version for automatic invalidation on breaking changes"
    )
    # Embedding inputs did not change in index schema 3.3. Keep this contract
    # separate so the mandatory Lance rebuild reuses content/model-validated
    # 3.2 vectors instead of forcing a costly CPU re-embedding.
    EMBEDDING_CACHE_SCHEMA_VERSION: str = Field(
        default="3.2",
        description="Embedding cache schema version, independent of Lance index layout"
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
        description=(
            "Automatically create a LanceDB vector index after the first sync "
            "when the dataset is large enough"
        )
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
        default=[],
        description=(
            "Allowed CORS origins as EXACT strings (e.g. 'http://localhost:3000'). "
            "Starlette matches these literally — port/host wildcards like "
            "'http://localhost:*' do NOT work; use CORS_ORIGIN_REGEX for that."
        )
    )
    CORS_ORIGIN_REGEX: str = Field(
        default=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
        description=(
            "Regex matched against the request Origin for CORS. Default allows localhost, "
            "127.0.0.1, and [::1] on any port (any local dev UI). Set to '' to disable "
            "regex matching and rely solely on CORS_ORIGINS."
        )
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
        # Anchor .env to PROJECT_ROOT (not the launch CWD) so the same file is loaded no
        # matter where the service is started from — critical for MCP clients that launch
        # with cwd != project root. Matches the PROJECT_ROOT policy used for every path above.
        env_file=str(PROJECT_ROOT / ".env"),
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

    @field_validator("LOCAL_FRAMEWORK_PATH", mode="before")
    @classmethod
    def normalize_optional_local_framework_path(cls, v):
        """Treat an unset/blank container override as remote-source mode."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("DATA_PATH", "DB_PATH", "RAW_PATH", "VERSION_FILE", "LOG_PATH")
    @classmethod
    def validate_storage_paths(cls, v: Optional[Path]) -> Optional[Path]:
        """
        Ensure paths are absolute.

        Source checkouts preserve repository-relative behavior. Installed
        wheels resolve relative values beneath the writable user-data root.
        """
        if v is None:
            return None
        # Never resolve an installed wheel's storage beneath site-packages.
        if not v.is_absolute():
            return (RELATIVE_STORAGE_BASE / v).resolve()
        return v

    @field_validator("LOCAL_FRAMEWORK_PATH")
    @classmethod
    def resolve_local_framework_path(cls, v: Optional[Path]) -> Optional[Path]:
        """Resolve an explicit relative source path without using site-packages."""
        if v is None or v.is_absolute():
            return v
        base = PROJECT_ROOT if IS_SOURCE_CHECKOUT else Path.cwd()
        return (base / v).resolve()

    @model_validator(mode='after')
    def derive_paths_from_data_path(self):
        """Keep default storage paths together when DATA_PATH is overridden."""
        if "DATA_PATH" not in self.model_fields_set:
            return self

        derived_paths = {
            "DB_PATH": self.DATA_PATH / "aidefend_kb.lancedb",
            "RAW_PATH": self.DATA_PATH / "raw_content",
            "VERSION_FILE": self.DATA_PATH / "local_version.json",
            "LOG_PATH": self.DATA_PATH / "logs" / "aidefend_mcp.log",
        }
        for field_name, derived_path in derived_paths.items():
            if field_name not in self.model_fields_set:
                setattr(self, field_name, derived_path)
        return self

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
    def validate_authoritative_storage_is_lease_scoped(self):
        """Keep every mutable sync artifact under the locked DATA_PATH.

        The service-instance lease is anchored at ``DATA_PATH/sync.lock``. If
        an authoritative database, raw-source directory, or version file could
        live outside that canonical root, two processes with different
        DATA_PATH values could mutate the same generation while holding
        different locks. Resolve aliases and existing symlinks before enforcing
        containment so the ownership boundary cannot be bypassed by spelling.
        """
        canonical_data_path = self.DATA_PATH.resolve(strict=False)
        self.DATA_PATH = canonical_data_path

        for field_name in ("DB_PATH", "RAW_PATH", "VERSION_FILE"):
            configured_path = getattr(self, field_name)
            canonical_path = configured_path.resolve(strict=False)
            if not canonical_path.is_relative_to(canonical_data_path):
                raise ValueError(
                    f"{field_name} must be contained within DATA_PATH because "
                    "DATA_PATH/sync.lock is the exclusive ownership boundary. "
                    f"Resolved DATA_PATH={canonical_data_path}; "
                    f"resolved {field_name}={canonical_path}"
                )
            setattr(self, field_name, canonical_path)
        return self

    @field_validator("API_HOST")
    @classmethod
    def normalize_api_host(cls, value: str) -> str:
        """Normalize a bind host and reject values Uvicorn cannot use safely."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("API_HOST must be a non-empty host or IP address")
        return normalized

    @model_validator(mode='after')
    def validate_api_host_with_auth(self):
        """
        Validate API host binding with authentication mode.

        Security Policy: no-auth mode is allowed only on an explicit loopback
        address (or ``localhost``). Wildcard, LAN, public, empty, and unknown
        hostname bindings require authentication.

        Note: Uses model_validator(mode='after') to ensure all fields are validated
        before cross-field validation is performed.
        """
        host = self.API_HOST.strip()
        if host.lower() == "localhost":
            is_loopback_binding = True
        else:
            try:
                is_loopback_binding = ipaddress.ip_address(host).is_loopback
            except ValueError:
                # Hostnames can resolve differently across machines or change
                # after validation, so unknown names fail closed in no-auth mode.
                is_loopback_binding = False

        if not is_loopback_binding and self.AUTH_MODE == "no_auth":
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
                    f"      CORS_ORIGINS=[\"https://example.com\"]\n\n"
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
