# Changelog

All notable changes to AIDEFEND MCP Service will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-03-20

### Fixed
- **Security**: Sanitized technique IDs in implementation plan tool to prevent filter injection (defense-in-depth)
- **Stability**: Database atomic swap now has proper rollback on Windows if rename fails mid-operation
- **Stability**: Added exponential backoff to background sync loop to prevent hammering GitHub API on repeated failures
- **MCP Protocol**: Logger console handler now writes to stderr instead of stdout, preventing MCP protocol stream corruption
- **MCP Protocol**: Default logger no longer auto-creates console handler at import time
- **Sync**: Orphaned temporary tables from failed syncs are now properly detected and cleaned up
- **Windows**: Lock file check now uses O_RDWR mode for correct msvcrt.locking behavior
- **Sync**: Query engine is now paused during database swap to prevent read errors from stale table references
- **Sync**: Fixed TOCTOU race condition in lock file diagnostics (stat() after exists() check)
- **Thread Safety**: `_last_sync_error` global state is now protected by a threading lock
- **Install Script**: Replaced bare `except:` clauses with specific exception types for better error visibility
- **Install Script**: Warns user when overwriting existing aidefend MCP configuration
- **Install Script**: Old backup files are now cleaned up (keeps last 3)

### Improved
- **Memory**: Added periodic garbage collection hints during large embedding generation batches
- **Resources**: LanceDB connections are now explicitly released after sync operations
- **Shutdown**: MCP server now performs graceful cleanup of query engine resources on exit
- **Cache**: Embedding cache cleanup uses copy-on-write pattern to prevent corruption if interrupted

## [1.0.0] - 2025-12-01

### Added
- Initial release with 18 AI security defense tools
- Dual-mode architecture: REST API (FastAPI) and MCP (Claude Desktop)
- Vector search with LanceDB and FastEmbed (multilingual support)
- GitHub sync with cross-process file locking
- Persistent embedding cache for fast incremental syncs
- Comprehensive input validation and security hardening
- Docker support with multi-stage build
- One-click installation script for Claude Desktop
