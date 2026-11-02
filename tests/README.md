# Tests

Unit and integration tests for AIDEFEND MCP Service.

## Running Tests

```bash
# Initialize the current Framework/index once for release and live-corpus gates
python __main__.py --resync

# Run the rolling suite against the current synchronized Framework
pytest -m "not current_snapshot"

# Run the rolling suite with coverage
pytest -m "not current_snapshot" --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth.py

# Run the rolling suite with verbose output
pytest -m "not current_snapshot" -v
```

The full suite includes release gates that inspect the active Framework corpus
and index. Use a fresh `DATA_PATH` and run `aidefend-mcp --resync` instead when
testing an installed wheel or an extracted-and-installed sdist.

The `current_snapshot` marker preserves exact counts and digests for the
historical 2026-11-01 Framework snapshot. Use `pytest -m current_snapshot` only
with that snapshot. CI excludes these historical assertions from its rolling
release gate and requires zero skipped tests in the selected suite.

## Test Structure

- `test_auth.py`, `test_auth_integration.py` - configuration and REST authentication
- `test_core_generation_io_async.py`, `test_database_recovery.py` - query-engine and database lifecycle
- `test_sync_unified.py`, `test_source_provenance.py` - sync, immutable source provenance, and generation identity
- `test_parser*.py` - bundled JavaScript parser and static evaluator
- `test_distribution_inventory.py`, `test_readiness_cli_contracts.py` - packaging, CLI, and release contracts
- Tool-specific modules such as `test_threat_coverage.py` and `test_incident_response.py`

## Test Requirements

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

## Writing Tests

Follow pytest conventions:
- Test files: `test_*.py`
- Test functions: `def test_*()`
- Use fixtures for common setup
- Mark slow tests: `@pytest.mark.slow`
- Mark integration tests: `@pytest.mark.integration`
