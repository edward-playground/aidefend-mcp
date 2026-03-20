# Contributing to AIDEFEND MCP Service

Thank you for your interest in contributing to the AIDEFEND MCP Service! This guide will help you get started with development.

## Development Setup

### Prerequisites

- Python 3.9 - 3.13
- Node.js 18+ (for JavaScript parsing)
- Git

### Setup Development Environment

1. **Clone the repository:**
   ```bash
   git clone https://github.com/edward-playground/aidefend-mcp.git
   cd aidefend-mcp
   ```

2. **Install dependencies:**
   ```bash
   # Install production dependencies
   pip install -r requirements.txt

   # Install development dependencies
   pip install -r requirements-dev.txt

   # Install Node.js dependencies
   npm install
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env as needed for development
   ```

4. **Run initial sync:**
   ```bash
   python __main__.py
   ```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_parser.py

# Run with coverage
pytest --cov=app --cov-report=html

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

### Code Quality

**Format code:**
```bash
black app/
isort app/
```

**Lint:**
```bash
flake8 app/
mypy app/
```

**Security scanning:**
```bash
# Static security analysis
bandit -r app/

# Dependency vulnerability scanning
safety check
```

### Running the Service Locally

**REST API mode:**
```bash
python __main__.py
# Access at: http://localhost:8000
# API docs: http://localhost:8000/docs
```

**MCP mode:**
```bash
python __main__.py --mcp
```

**Force resync:**
```bash
python __main__.py --resync
```

## Project Structure

```
aidefend-mcp/
├── __main__.py              # Unified entry point
├── mcp_server.py            # MCP protocol server
├── parse_js_module.mjs      # JavaScript parser (Node.js)
├── app/
│   ├── main.py              # FastAPI REST API
│   ├── core.py              # QueryEngine (shared by both modes)
│   ├── sync.py              # Background sync service
│   ├── config.py            # Configuration management
│   ├── security.py          # Input validation and security
│   ├── audit.py             # Audit logging
│   ├── logger.py            # Structured logging
│   ├── chunking.py          # Smart text chunking
│   ├── embedding_cache.py   # Embedding cache system
│   └── tools/               # P0 specialized tools
│       ├── statistics.py
│       ├── validation.py
│       ├── technique_detail.py
│       ├── defenses_for_threat.py
│       ├── code_snippets.py
│       ├── coverage_analysis.py
│       ├── compliance_mapping.py
│       ├── quick_reference.py
│       ├── threat_coverage.py
│       ├── implementation_plan.py
│       ├── classify_threat.py
│       ├── comprehensive_search.py
│       ├── security_posture.py
│       ├── technique_comparison.py
│       └── incident_response.py
├── tests/                   # Test suite
├── scripts/                 # Utility scripts
├── docs/                    # Additional documentation
└── data/                    # Runtime data (logs, database)
```

## Adding New Features

### Adding a New P0 Tool

1. **Create tool function** in `app/tools/your_tool.py`:
   ```python
   async def your_new_tool(param1: str, param2: int = 5) -> Dict[str, Any]:
       """Tool logic here."""
       from app.core import query_engine
       await query_engine.initialize()

       # Perform operations
       results = await query_engine.search(...)

       return {"results": results, "total": len(results)}
   ```

2. **Add REST API endpoint** in `app/main.py`:
   ```python
   @app.post("/api/v1/your-tool")
   async def your_tool_endpoint(param1: str, param2: int = 5):
       result = await your_new_tool(param1, param2)
       return result
   ```

3. **Add MCP tool handler** in `mcp_server.py`:
   - Add tool definition in `list_tools()`
   - Add handler in `call_tool()`
   - Create `handle_your_new_tool()` async function

4. **Add tests** in `tests/test_your_tool.py`

5. **Update documentation** in `docs/TOOLS.md`

## Testing Guidelines

### Writing Tests

- Use `pytest` for all tests
- Place tests in `tests/` directory
- Name test files as `test_*.py`
- Use descriptive test names: `test_feature_behavior_expected_outcome`

### Test Markers

```python
import pytest

@pytest.mark.unit
def test_validation_logic():
    ...

@pytest.mark.integration
async def test_full_query_flow():
    ...

@pytest.mark.slow
def test_large_dataset():
    ...
```

### Test Coverage

- Aim for 80%+ code coverage
- Focus on critical paths and edge cases
- Test error handling and validation

## Security

### Security Scanning

This repository includes automated security scanning via GitHub Actions:

**Automated scans run on:**
- Every push to `main` or `develop` branches
- All pull requests
- Weekly schedule (Mondays at 00:00 UTC)

**Security tools:**
- **Bandit**: Static security analysis for Python code
- **Safety**: Dependency vulnerability scanning
- **CodeQL**: Advanced semantic code analysis

### Reporting Security Issues

Please see [SECURITY.md](SECURITY.md) for vulnerability reporting procedures.

### Security Best Practices

1. **Input validation**: Always validate and sanitize user inputs
2. **No external APIs**: Keep all processing local and private
3. **Path traversal prevention**: Validate file paths
4. **Rate limiting**: Implement rate limits on new endpoints
5. **Audit logging**: Log all sensitive operations

## Code Style

### Python Style

Follow [PEP 8](https://pep8.org/) with the following specifics:

- **Line length**: 100 characters max
- **Indentation**: 4 spaces
- **String quotes**: Double quotes preferred
- **Type hints**: Use type hints for all function signatures
- **Docstrings**: Google-style docstrings

Example:
```python
async def search_techniques(
    query: str,
    top_k: int = 5,
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Search AIDEFEND techniques using semantic search.

    Args:
        query: Natural language search query
        top_k: Number of results to return
        filters: Optional filtering criteria

    Returns:
        Dictionary with search results and metadata

    Raises:
        ValidationError: If query is invalid
    """
    ...
```

### Formatting

Use automated formatters:
```bash
black app/      # Auto-format code
isort app/      # Sort imports
```

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test additions or changes
- `refactor:` Code refactoring
- `perf:` Performance improvements
- `chore:` Maintenance tasks

Examples:
```
feat: add incident response playbook generator
fix: resolve sync lock conflicts
docs: update configuration guide
test: add coverage for chunked search
```

## Pull Request Process

1. **Fork the repository** and create a feature branch
2. **Make your changes** following code style guidelines
3. **Add tests** for new functionality
4. **Run tests** and ensure they pass
5. **Update documentation** as needed
6. **Submit pull request** with clear description

### PR Checklist

- [ ] Tests added/updated and passing
- [ ] Documentation updated
- [ ] Code formatted with `black` and `isort`
- [ ] No new linting errors (`flake8`)
- [ ] Type hints added (`mypy` passes)
- [ ] Security scan passes (`bandit`)
- [ ] Commit messages follow convention

## Community

### Getting Help

- **Issues**: [GitHub Issues](https://github.com/edward-playground/aidefend-mcp/issues)
- **Discussions**: GitHub Discussions (if enabled)
- **Security**: [SECURITY.md](SECURITY.md) for vulnerability reporting

### Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Maintain a harassment-free environment

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

---

Thank you for contributing to AIDEFEND MCP Service! 🚀
