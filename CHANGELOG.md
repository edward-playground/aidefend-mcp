# Changelog

All notable changes to AIDEFEND MCP Service will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Synchronize and strictly validate the framework's public edition-migration registry from
  the same immutable source snapshot as the indexed tactics.
- Resolve current, bare, `latest`, named, and superseded OWASP LLM references to canonical
  2026 IDs with structured `canonical`, `migrated`, `normalized`, `fallback_latest`,
  `ambiguous`, or `invalid` metadata.

### Fixed
- Bind every physical index build to a unique generation identity, durably pair
  LanceDB table renames with version metadata, and preserve verified rollback
  generations across crashes, transient I/O failures, initialization failures,
  and cancellation.
- Retain database reader/writer and `DATA_PATH` ownership locks until underlying
  thread workers actually finish, even when an HTTP, MCP, CLI, background-sync,
  recovery, or maintenance caller is cancelled.
- Require `DB_PATH`, `RAW_PATH`, and `VERSION_FILE` to resolve inside the
  canonical `DATA_PATH` ownership boundary so path aliases or shared external
  artifacts cannot bypass process exclusivity.
- Keep the development security-audit environment on `cryptography` 50.0.0 or
  later, which fixes PYSEC-2026-3552 inherited through Safety/Authlib.
- Materialize the framework's bounded static `join` / `replace` / arrow-expression
  `map` chains without executing tactic source code.
- Reject unsupported calls, computed members, spreads, free variables, dynamic
  templates, and other non-static AST shapes at the parser boundary instead of
  silently emitting `null`, marker strings, or incomplete objects.
- Preserve every declared framework-edition label as an alias of its stable key,
  reject cross-framework label collisions and active-label drift, and validate
  multi-word framework item IDs with framework-specific normalization.
- Bound parser AST nodes, evaluation operations, call-chain depth, array size,
  individual string results, and serialized output size.
- Bound Framework Public Schema JSON nesting before decoding so malformed
  metadata fails closed consistently across CPython 3.10-3.14.
- Render launcher-aware CLI help and recovery guidance so an installed wheel
  recommends `aidefend-mcp`, while a source checkout continues to recommend
  `python __main__.py`.
- Report the effective configured REST host and port in the CLI startup banner.
- Permit unauthenticated REST binding only on an explicit IPv4/IPv6 loopback
  address, fail closed for wildcard/LAN/unknown hosts, and render IPv6 URLs correctly.

### Changed
- Extend the configured Python support and hosted CI matrix through Python
  3.14; release publication remains gated on the complete Python/OS matrix.
- Use `app` as the canonical Python package, remove the redundant repository-root
  package marker, and retain `__main__.py` only as the source-checkout CLI shim.
- Run parser and clean-install CI on the latest Node.js 24 LTS patch release
  while retaining the documented Node.js 18+ parser compatibility floor.
- Upgrade the exact lock-pinned and vendored Acorn parser runtime to 8.18.0,
  with official npm integrity, license, vendored-file digest, and parser checks.
- Upgrade RapidFuzz to 3.14.5 so the fuzzy-classification dependency has native
  CPython 3.14 wheels on the supported release platforms.
- Refresh the compatible FastAPI, Starlette, Uvicorn, Pydantic, settings,
  Windows runtime, rate-limit, parser, lock, and release-tool dependencies to
  their current Python 3.10-3.14-compatible stable lines.
- Define the 1.3.0 embedding contract as `fastembed==0.8.0` with the declared
  CPU `onnxruntime` dependency. Retire the previous unvalidated GPU setup and
  performance claims; accelerator support now requires a separate,
  conflict-free dependency path and complete release testing.
- Discover the Framework Public Schema dynamically from the root
  `version.schemaVersion` value in `data/data.json` from the same local source
  root or immutable GitHub revision as the indexed tactics. Remove the unused
  authoring-only metadata discovery path and its REST/status response fields;
  these fields were not present in a tagged or formally published release.
- Treat each configured `DATA_PATH` as a lifetime single-process ownership
  boundary across REST, stdio MCP, resync, and maintenance operations. REST
  and MCP running concurrently, or multiple service replicas, require
  independent storage copies; horizontal scaling with shared state requires an
  external data layer designed for concurrent clients.
- Keep `DATA_PATH/sync.lock` as a stable operating-system lock rendezvous rather
  than using file presence, age, manual deletion, or replacement as ownership
  evidence. Upgrades from pre-lifetime-lock releases require all older service
  and maintenance processes to stop first.
- Update the active OWASP mapping surface from LLM Top 10 2025 to the semantically
  re-reviewed LLM Top 10 2026 corpus; legacy 2025 queries migrate by concept rather than
  by same-rank number.
- Commit the validated migration registry and index provenance in one atomic version
  marker; source-manifest and registry digest changes force the required rebuild without
  invalidating otherwise reusable embeddings.
- Advance the exact release snapshot sentinel to AIDEFEND 1.20260805 and make the
  manual CI snapshot gate execute every `current_snapshot` test against either an
  explicit local source or the immutable framework files staged by CI.
- Upgrade the FastAPI/Starlette, MCP SDK, multipart parser, and FastEmbed/Pillow
  dependency chain to releases that clear the current vulnerability audit.
- Refresh the pinned pytest, pytest-asyncio, Black, Safety, and pip-audit
  development toolchain so the complete release environment also audits cleanly.

## [1.2.0] - 2026-07-24

### Added
- Preserve and expose AIDEFEND public schema 2.3 metadata, including canonical guidance IDs,
  multi-value pillar and phase fields, all three tool categories (open-source,
  source-available/open-weight, and commercial), scope boundaries, and actionable versus
  parent-family semantics.
- Record source kind, repository, ref, revision kind, and staged content digest so local
  development syncs and immutable GitHub deployments have explicit provenance.
- Add end-to-end smoke coverage for all 18 MCP tools and their 18 REST counterparts.
- Add an exact AIDEFEND 1.20260724 / public 2.3 / index 3.2
  release-snapshot gate plus a rolling daily canary against the latest upstream framework.

### Changed
- Rebuild and atomically swap validated LanceDB tables under coordinated read/write guards.
  Version metadata is also replaced atomically; if that commit fails, the service restores
  the last-known-good database or takes an uncommitted first-install database offline.
- Align search, detail, statistics, threat classification, comparison, planning, and incident
  outputs with the schema 2.3 hierarchy and canonical threat mappings.
- Carry source-defined threat-framework labels through coverage analytics without constraining
  runtime behavior to the exact set of labels in the release snapshot.
- Align the canonical Agentic Top 10 label with
  `OWASP Top 10 for Agentic Applications 2026` while preserving the stable
  `owasp_agentic` API key and accepting the prior label as legacy input.
- Package the static JavaScript parser and pinned Acorn runtime in wheel, sdist, and Docker
  deployments without requiring a runtime npm install.
- Treat content, ID, title, count, order, and compatible additive-field changes as dynamic
  framework data rather than fixed runtime constraints. Snapshot corpus counts remain
  examples, not acceptance thresholds.
- Keep exact scope-boundary and tool values in structured metadata when unusually long
  content exceeds the embedding token window; warn instead of rejecting a valid update.
- Validate every candidate index before activation and keep the last-known-good MCP/REST
  index online when a source is invalid or genuinely incompatible. Arbitrary breaking
  schema changes still require an explicit service update.
- Check for updates immediately at startup and then at the configurable
  `SYNC_INTERVAL_SECONDS` cadence (one hour by default, from one minute to 24 hours), with
  failure backoff. This runtime cadence is separate from the daily CI canary.

## [1.1.0] - 2026-07-14

### Fixed
- Resolve `aidefendVersion` exported constants used by framework template literals.
- Fail closed when any required tactic is missing, invalid, or cannot be parsed.
- Start and gracefully stop automatic sync in both REST and stdio MCP modes.
- Rebuild the index when the MCP index schema or embedding configuration changes.
- Preserve framework warning and scope-note content in search and technique details.
- Include the `response` lifecycle phase in implementation-plan scoring.
- Correct strategy code-coverage statistics and avoid fabricated framework totals.
- Package `app.tools`, the static parser, and its Acorn runtime in Python wheels.

### Changed
- Validate the complete manifest-defined tactic source contract before publishing a new database.
- Clarify the separate MIT service-code and CC BY 4.0 framework-content licenses.

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
