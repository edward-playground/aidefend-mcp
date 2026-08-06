[English README](README.md) | [繁體中文 README](README-繁體中文.md)

---

# AIDEFEND MCP / REST API Service

[![CI](https://github.com/edward-playground/aidefend-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/edward-playground/aidefend-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10-3.14](https://img.shields.io/badge/python-3.10%20|%203.14-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141.1-009688.svg)](https://fastapi.tiangolo.com)

Local retrieval service for the [AIDEFEND framework](https://github.com/edward-playground/aidefense-framework).

This repository safely parses the framework's JavaScript tactics, builds a local LanceDB knowledge base, and exposes the result through:

- a REST API for applications and automation
- an MCP server for AI assistants such as Claude Desktop

This repository is **not** the framework itself. It is the service layer on top of the framework.

## What You Get

- Local semantic search over AIDEFEND content
- REST API and MCP access from the same indexed knowledge base
- Automatic sync from the upstream GitHub repository by default
- Optional local framework override for contributors working on both repos
- Multilingual embedding search with `Xenova/multilingual-e5-base`
- Automated tests and Bandit security scanning in GitHub Actions

## How It Works

1. Sync AIDEFEND tactic files from GitHub.
2. Parse the JavaScript files with a Node.js AST parser. The service does not execute upstream framework code.
3. Expand tactics into techniques, sub-techniques, and strategies.
4. Generate embeddings and store the documents in LanceDB.
5. Serve the indexed data over REST or MCP.

## Rolling Framework Compatibility

The current release validation snapshot is AIDEFEND **1.20260805** with public
schema **2.3** and MCP index schema **3.3**. It includes all three framework
tool categories: open-source,
source-available/open-weight, and commercial. Snapshot IDs, titles, counts,
and ordering are examples of what was validated for this release, not
permanent runtime constraints.

Within the supported framework contract, synchronization dynamically rebuilds
both the MCP and REST data from the selected source. Content additions and
removals, ID renumbering, title or guidance edits, count and order changes, and
compatible additive fields do not require customer-specific configuration.
Source-defined threat-framework labels are also carried through coverage and
analytics instead of being limited to the exact label set in this snapshot.
When a supported framework is renamed again, its active label becomes the
display name while every declared edition label remains an input alias for the
same stable API key. Cross-framework label collisions, mismatched active
edition labels, and malformed multi-word item identifiers are rejected during
sync rather than guessed.
Exact scope-boundary and tool values remain available as structured MCP/REST
metadata even if unusually long content exceeds the embedding model's
searchable token window; that condition is warned about rather than rejecting
an otherwise valid update.

Framework-edition migrations are synchronized from
`data/framework-migrations.json` in the same immutable source snapshot. The
active OWASP LLM edition is **2026**. Bare IDs and `latest` references resolve
to that edition; an explicit 2025 ID is migrated by its declared semantic
successor, never by reusing the same rank. Responses expose the canonical 2026
ID and structured resolution metadata. Unsupported or genuinely ambiguous
references fail closed without running a threat lookup. The validated registry
and index provenance are committed together in the atomically replaced version
metadata, so a failed update cannot pair a new resolver catalog with an older
database.

The Framework Public Schema is discovered dynamically from the root
`version.schemaVersion` value in `data/data.json`. Local-source mode reads that
file from the same configured framework root as the tactics; GitHub mode reads
it from the exact immutable commit used for those tactics, never separately
from a floating branch. This public dataset is used only for schema metadata
discovery and is not indexed a second time or substituted for the tactic
authoring sources. Missing or invalid metadata safely reports the public schema
as unavailable without guessing or weakening the full parser and index
validation gates.

With automatic sync enabled (the default), the service checks once at startup
and then every `SYNC_INTERVAL_SECONDS` seconds: 3600 by default, configurable
from 60 to 86400. Repeated failures use backoff. Separately, a rolling daily
upstream canary exercises the latest public framework in addition to the exact
release snapshot.

The service does not claim automatic compatibility with arbitrary breaking
schema changes. Every candidate index is validated before activation. If an
upstream source is invalid or genuinely incompatible, an existing installation
keeps serving its last-known-good index through MCP and REST and reports the
sync error. Version metadata is written by atomic replacement; if that final
commit fails after database activation, the uncommitted database is taken
offline and the last-known-good database is restored when one exists. A clean
installation without a validated index fails explicitly instead of publishing
partial or misinterpreted data; support for a new breaking contract must be
released deliberately.
For example, a fourth semantic tool category or a changed field shape is
treated as a breaking contract and rejected rather than silently discarded.

## Requirements

- Python 3.10 to 3.14
- Node.js 18+
- Git
- About 2 to 3 GB free disk space for dependencies, embedding model, and local database

`npm` is not required for installation or runtime. The Acorn parser is bundled
in `vendor/`; Node.js 18+ is the only JavaScript runtime prerequisite.

Normal users do **not** need to configure any personal local path. The default setup syncs from GitHub.

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/edward-playground/aidefend-mcp.git
cd aidefend-mcp
```

### 2. Pick an installation path

| Use case | Recommended command |
| --- | --- |
| Claude Desktop MCP | `python scripts/install.py` |
| Claude Code MCP | `python scripts/install.py --client code` |
| REST API only | `python scripts/install.py --no-mcp` |
| Manual setup | Follow [INSTALL.md](INSTALL.md) |

### 3. Build the local knowledge base

```bash
python __main__.py --resync
```

The first sync downloads the framework, embedding model, and creates the local database. Expect several minutes on a clean machine.

### 4. Run the service

REST API:

```bash
python __main__.py
```

MCP server:

```bash
python __main__.py --mcp
```

Choose one runtime for each data directory. A REST process, stdio MCP process,
`--resync` command, or maintenance command must have exclusive ownership of its
configured `DATA_PATH`. To run REST and MCP at the same time, configure separate
data directories and keep each instance's `DB_PATH`, `RAW_PATH`, and
`VERSION_FILE` with that instance; do not share any of those paths.

Health check:

```bash
curl http://127.0.0.1:8000/health
```

### Data-directory lock and upgrades

`DATA_PATH/sync.lock` is a persistent rendezvous file for the operating-system
lock. The file may remain after a clean shutdown; its presence or age is not
evidence that the lock is active. Do not delete or replace it to force another
service or resync to start. Stop the process that owns the data directory, or
use a different complete set of storage paths.

Before upgrading from a release that did not hold this lock for the complete
service lifetime, stop every REST service, close MCP clients that launch the
stdio server, and let all resync or maintenance commands finish. Then upgrade
and start one owner for each `DATA_PATH`.

## Manual Setup From a Fresh Clone

If you want a clean, explicit install path instead of the helper script:

```bash
python -m venv .venv
```

Activate the virtual environment.

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The secure JavaScript parser uses the Acorn runtime bundled in `vendor/`, so
this setup does not download Node packages or require `npm`.

Create local config:

macOS/Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Then run:

```bash
python __main__.py --resync
python __main__.py
```

## Optional Local Framework Override

By default the service syncs from GitHub. If you are developing this repo alongside a local checkout of `aidefense-framework`, you can point the sync to your local source:

```env
LOCAL_FRAMEWORK_PATH=/path/to/aidefense-framework
```

This is optional and should stay unset for normal open-source users.

## Common Commands

```bash
# Rebuild the local database from the configured source
python __main__.py --resync

# Run the REST API
python __main__.py

# Run the MCP server
python __main__.py --mcp

# Run tests / static scan (first install the dev dependencies)
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m bandit -q -r app
```

## Docker

The container binds `0.0.0.0`, so authentication is required — set an API key before starting:

```bash
# 1. Create your .env and generate a REST API key
cp .env.example .env
python scripts/generate_api_key.py     # copy the value into AIDEFEND_API_KEY in .env

# 2. Start the service
docker compose up -d
```

Use one service replica per writable data volume. Horizontal scaling requires
an independent data copy or volume for every replica, or an external data layer
designed for concurrent clients; the bundled local LanceDB directory must not
be shared by multiple replicas.

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for auth details.

## Documentation

- Installation: [INSTALL.md](INSTALL.md)
- Configuration: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- Advanced configuration: [docs/ADVANCED_CONFIGURATION.md](docs/ADVANCED_CONFIGURATION.md)
- Tool reference: [docs/TOOLS.md](docs/TOOLS.md)
- Security notes: [SECURITY.md](SECURITY.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)

## Repository Notes

- `data/`, local caches, coverage output, and `.env` are ignored by git and are not required in the repository.
- A source checkout stores runtime data under `data/`. An installed wheel uses
  the OS per-user application-data directory; Docker uses `/app/data`.
- One `DATA_PATH` supports one REST, MCP, resync, or maintenance process at a
  time. Concurrent modes or replicas require independent storage.
- CI builds and verifies a live upstream index, exercises all 18 MCP and 18
  REST tool paths from both the source checkout and an externally installed
  wheel on Linux, and runs clean-wheel install/parser/console checks on
  Windows, macOS, and Linux across Python 3.10-3.14. A release is not ready
  until that hosted matrix passes. Bandit and a real
  container build/runtime contract run alongside the daily rolling-upstream
  canary and framework release dispatches.
- The source contract discovers the ordered tactic set from the framework's
  `main.js` manifest, including parent/shared mappings, actionable
  sub-techniques, warnings, and implementation guidance.

## License and Framework Content

The AIDEFEND MCP Service source code is licensed under the MIT License. See
[LICENSE](LICENSE).

The framework content downloaded, indexed, and returned by this service keeps
its own license:

> AIDEFEND AI Defense Framework, created by Edward Lee,
> https://aidefend.net, licensed under CC BY 4.0.

Framework software is Apache-2.0, framework content/data is CC BY 4.0, and
trademark rights are not granted. See [THIRD_PARTY_CONTENT.md](THIRD_PARTY_CONTENT.md)
and the framework repository's licensing files for details. The synchronized
edition-migration registry also carries source-specific attribution and
CC BY-SA 4.0 terms for its normalized OWASP-derived identifiers, names,
metadata, and summaries; those terms are recorded in the registry itself.
