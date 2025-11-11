# Tests

Unit and integration tests for AIDEFEND MCP Service.

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_config.py

# Run with verbose output
pytest -v
```

## Test Structure

- `test_config.py` - Configuration and settings validation
- `test_core.py` - Vector database and query engine
- `test_sync.py` - GitHub sync and JavaScript parsing
- `test_api.py` - REST API endpoints
- `test_mcp.py` - MCP server protocol
- `test_security.py` - Security validations

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
