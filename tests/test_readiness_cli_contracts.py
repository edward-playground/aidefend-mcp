"""Regression tests for readiness, transport parity, and safe CLI rebuilds."""

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.routing import serialize_response

import app.cli as cli_module
import app.config as config_module
import app.logger as logger_module
import app.main as main_module
import app.sync as sync_module
from app.config import Settings, settings
from app.schemas import ClassifyThreatResponse, SecurityPostureRequest


@pytest.mark.asyncio
async def test_health_is_side_effect_free_and_unready_returns_503(monkeypatch):
    engine = type("Engine", (), {})()
    engine.is_ready = False
    engine.get_stats = AsyncMock(
        return_value={
            "initialized": False,
            "document_count": 0,
            "model_loaded": False,
        }
    )
    engine.initialize = AsyncMock(side_effect=AssertionError("health must not initialize"))
    engine.health_check = AsyncMock(side_effect=AssertionError("health must not self-heal"))

    monkeypatch.setattr(main_module, "query_engine", engine)
    monkeypatch.setattr(main_module, "load_version_info", lambda: None)

    response = await main_module.health_check()
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["status"] == "unhealthy"
    assert payload["checks"] == {
        "database": False,
        "embedding_model": False,
        "sync_service": True,
    }
    engine.get_stats.assert_awaited_once_with()
    engine.initialize.assert_not_awaited()
    engine.health_check.assert_not_awaited()


@pytest.mark.asyncio
async def test_health_returns_200_only_when_query_dependencies_are_ready(monkeypatch):
    engine = type("Engine", (), {})()
    engine.is_ready = True
    engine.get_stats = AsyncMock(
        return_value={
            "initialized": True,
            "document_count": 42,
            "model_loaded": True,
        }
    )

    monkeypatch.setattr(main_module, "query_engine", engine)
    monkeypatch.setattr(main_module, "load_version_info", lambda: None)

    response = await main_module.health_check()
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["status"] == "healthy"
    assert payload["checks"]["database"] is True
    assert payload["checks"]["embedding_model"] is True


@pytest.mark.asyncio
async def test_health_reports_stale_but_queryable_database_as_degraded(monkeypatch):
    engine = type("Engine", (), {})()
    engine.is_ready = True
    engine.get_stats = AsyncMock(
        return_value={
            "initialized": True,
            "document_count": 42,
            "model_loaded": True,
        }
    )
    stale_time = datetime.now(timezone.utc) - timedelta(
        seconds=(main_module.settings.SYNC_INTERVAL_SECONDS * 2) + 60
    )
    engine.get_stats.return_value["version_info"] = {
        "last_synced_at": stale_time.isoformat(),
    }

    monkeypatch.setattr(main_module, "query_engine", engine)
    monkeypatch.setattr(
        main_module,
        "load_version_info",
        lambda: (_ for _ in ()).throw(
            AssertionError("health must use the stats generation snapshot")
        ),
    )

    response = await main_module.health_check()
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["status"] == "degraded"
    assert payload["checks"] == {
        "database": True,
        "embedding_model": True,
        "sync_service": False,
    }


@pytest.mark.asyncio
async def test_health_probe_failure_returns_503(monkeypatch):
    engine = type("Engine", (), {})()
    engine.is_ready = False
    engine.get_stats = AsyncMock(side_effect=RuntimeError("stats unavailable"))

    monkeypatch.setattr(main_module, "query_engine", engine)

    response = await main_module.health_check()
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["status"] == "unhealthy"


def test_security_posture_rest_schema_matches_mcp_empty_baseline_contract():
    assert SecurityPostureRequest().implemented_techniques == []
    assert SecurityPostureRequest(implemented_techniques=[]).implemented_techniques == []
    assert SecurityPostureRequest(
        implemented_techniques=[" aid-h-001 "]
    ).implemented_techniques == ["AID-H-001"]

    schema = SecurityPostureRequest.model_json_schema()
    assert "implemented_techniques" not in schema.get("required", [])
    implemented_schema = schema["properties"]["implemented_techniques"]
    assert implemented_schema.get("default") == []
    assert implemented_schema.get("minItems", 0) == 0
    assert implemented_schema["maxItems"] == 200


def test_threat_coverage_rest_schema_preserves_active_framework_labels():
    from app.schemas import ThreatCoverageResponse

    response = ThreatCoverageResponse.model_validate(
        {
            "input_count": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "invalid_techniques": [],
            "resolved_actionable_count": 0,
            "expanded_parent_families": {},
            "covered": {},
            "coverage_rate": {},
            "framework_totals": {},
            "framework_labels": {
                "owasp_llm": "OWASP LLM Top 10 2026",
            },
            "by_technique": [],
        }
    )

    assert response.model_dump()["framework_labels"]["owasp_llm"] == (
        "OWASP LLM Top 10 2026"
    )


def test_classify_threat_rest_schema_preserves_mapping_status():
    response = ClassifyThreatResponse.model_validate(
        {
            "source": "static_keyword",
            "input_text_preview": "prompt injection",
            "keywords_found": [],
            "normalized_threats": {"owasp": ["LLM01"], "atlas": [], "maestro": []},
            "threat_details": [],
            "recommended_actions": [],
            "mapping_status": {
                "all_emitted_claims_resolvable": True,
                "corpus_mapping_available": True,
                "unresolved_claims": [],
                "unmapped_keywords": [],
                "classifier_owasp_llm_edition": "2026",
                "classifier_owasp_llm_label": "OWASP LLM Top 10 2026",
                "active_index_owasp_llm_edition": "2026",
                "active_index_owasp_llm_label": "OWASP LLM Top 10 2026",
                "migration_registry_status": "active",
                "owasp_llm_catalog_aligned": True,
            },
        }
    )

    assert response.mapping_status.all_emitted_claims_resolvable is True
    assert response.mapping_status.corpus_mapping_available is True
    assert response.mapping_status.unresolved_claims == []
    assert response.mapping_status.unmapped_keywords == []
    assert response.mapping_status.classifier_owasp_llm_edition == "2026"
    assert response.mapping_status.classifier_owasp_llm_label == "OWASP LLM Top 10 2026"
    assert response.mapping_status.active_index_owasp_llm_edition == "2026"
    assert response.mapping_status.active_index_owasp_llm_label == "OWASP LLM Top 10 2026"
    assert response.mapping_status.migration_registry_status == "active"
    assert response.mapping_status.owasp_llm_catalog_aligned is True


@pytest.mark.asyncio
async def test_status_exposes_complete_current_public_metadata_contract(monkeypatch):
    version_info = {
        "commit_sha": "legacy-commit",
        "framework_version": "1.20260721",
        "framework_public_schema_version": "2.4",
        "index_schema_version": "2.0",
        "source_kind": "local",
        "source_revision_kind": "local_content_sha1",
        "source_revision": "local-revision",
        "source_repository": "local-working-tree",
        "source_ref": "working-tree",
        "source_content_sha256": "a" * 64,
        "framework_migrations_schema_version": "1.0",
        "framework_migrations_registry_version": "2026-08-05",
        "framework_migrations_sha256": "c" * 64,
        "total_documents": 1234,
    }

    monkeypatch.setattr(main_module, "load_version_info", lambda: version_info)
    monkeypatch.setattr(main_module, "is_sync_in_progress", lambda: False)
    monkeypatch.setattr(main_module, "get_last_sync_error", lambda: None)

    response = await main_module.get_status.__wrapped__(None)
    sync_info = response.sync_info

    assert sync_info is not None
    assert sync_info.current_commit_sha == "local-revision"
    assert sync_info.framework_version == "1.20260721"
    assert sync_info.framework_public_schema_version == "2.4"
    assert sync_info.index_schema_version == "2.0"
    assert sync_info.source_kind == "local"
    assert sync_info.source_revision_kind == "local_content_sha1"
    assert sync_info.source_revision == "local-revision"
    assert sync_info.source_repository == "local-working-tree"
    assert sync_info.source_ref == "working-tree"
    assert sync_info.source_content_sha256 == "a" * 64
    assert sync_info.framework_migrations_schema_version == "1.0"
    assert sync_info.framework_migrations_registry_version == "2026-08-05"
    assert sync_info.framework_migrations_sha256 == "c" * 64

    status_route = next(
        route
        for route in main_module.protected_router.routes
        if getattr(route, "path", None) == "/api/v1/status"
    )
    serialized = await serialize_response(
        field=status_route.response_field,
        response_content=response,
        exclude=status_route.response_model_exclude,
        by_alias=status_route.response_model_by_alias,
        exclude_unset=status_route.response_model_exclude_unset,
        exclude_defaults=status_route.response_model_exclude_defaults,
        exclude_none=status_route.response_model_exclude_none,
        is_coroutine=True,
    )
    serialized_sync = serialized["sync_info"]

    assert serialized_sync["framework_public_schema_version"] == "2.4"
    assert serialized_sync["last_synced_at"] is None

    openapi_sync_schema = main_module.app.openapi()["components"]["schemas"][
        "SyncStatus"
    ]
    assert set(openapi_sync_schema["properties"]) == {
        "last_synced_at",
        "current_commit_sha",
        "framework_version",
        "framework_public_schema_version",
        "index_schema_version",
        "source_kind",
        "source_revision_kind",
        "source_revision",
        "source_repository",
        "source_ref",
        "source_content_sha256",
        "framework_migrations_schema_version",
        "framework_migrations_registry_version",
        "framework_migrations_sha256",
        "total_documents",
        "is_syncing",
    }


def test_resync_failure_does_not_predelete_live_database_or_version(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "aidefend_kb.lancedb"
    database_path.mkdir()
    database_marker = database_path / "live.marker"
    database_marker.write_text("current database", encoding="utf-8")
    version_path = tmp_path / "local_version.json"
    version_path.write_text('{"source_revision":"current"}', encoding="utf-8")

    rebuild_calls = []
    release_calls = []

    async def fake_acquire_sync_lock():
        return True

    def fake_release_sync_lock():
        release_calls.append(True)

    async def fake_core_sync(*, force_rebuild=False):
        rebuild_calls.append(force_rebuild)
        return False

    monkeypatch.setattr(settings, "DATA_PATH", tmp_path)
    monkeypatch.setattr(settings, "DB_PATH", database_path)
    monkeypatch.setattr(settings, "VERSION_FILE", version_path)
    monkeypatch.setattr(cli_module, "check_for_running_server", lambda: False)
    monkeypatch.setattr(sync_module, "_acquire_sync_lock", fake_acquire_sync_lock)
    monkeypatch.setattr(sync_module, "_release_sync_lock", fake_release_sync_lock)
    monkeypatch.setattr(sync_module, "core_sync", fake_core_sync)
    monkeypatch.setattr(sync_module, "get_last_sync_error", lambda: "expected failure")
    monkeypatch.setattr(logger_module, "setup_logger", lambda: None)
    monkeypatch.setattr(sys, "argv", ["aidefend-mcp", "--resync"])

    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    try:
        with pytest.raises(SystemExit) as exc_info:
            cli_module.main()
    finally:
        for handler in list(root_logger.handlers):
            if handler not in original_handlers:
                root_logger.removeHandler(handler)

    assert exc_info.value.code == 1
    assert rebuild_calls == [True]
    assert release_calls == [True]
    assert database_marker.read_text(encoding="utf-8") == "current database"
    assert version_path.read_text(encoding="utf-8") == '{"source_revision":"current"}'


@pytest.mark.parametrize(
    ("argv0", "expected_command"),
    [
        ("aidefend-mcp", "aidefend-mcp"),
        ("aidefend-mcp.exe", "aidefend-mcp"),
        (str(Path("source") / "__main__.py"), "python __main__.py"),
    ],
)
def test_cli_help_uses_the_launcher_for_the_current_installation(
    argv0, expected_command, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", [argv0, "--help"])

    cli_module.print_help()

    stdout = capsys.readouterr().out
    assert f"USAGE:\n    {expected_command} [OPTIONS]" in stdout
    assert f"{expected_command} --mcp" in stdout
    assert f"{expected_command} --resync" in stdout
    assert "Installed package: aidefend-mcp [OPTIONS]" in stdout
    assert "Source checkout:   python __main__.py [OPTIONS]" in stdout


def test_api_cli_banner_uses_effective_host_and_port(monkeypatch, capsys):
    import uvicorn

    calls = []

    def fake_run(_app, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(settings, "API_HOST", "127.0.0.2")
    monkeypatch.setattr(settings, "API_PORT", 18765)
    monkeypatch.setattr(settings, "API_WORKERS", 1)
    monkeypatch.setattr(settings, "LOG_LEVEL", "INFO")
    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["aidefend-mcp", "--api"])

    cli_module.main()

    stderr = capsys.readouterr().err
    assert "API will be available at: http://127.0.0.2:18765" in stderr
    assert "API documentation: http://127.0.0.2:18765/docs" in stderr
    assert calls == [
        {
            "host": "127.0.0.2",
            "port": 18765,
            "workers": 1,
            "log_level": "info",
        }
    ]


def test_api_cli_banner_brackets_ipv6_host(monkeypatch, capsys):
    import uvicorn

    calls = []

    def fake_run(_app, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(settings, "API_HOST", "::1")
    monkeypatch.setattr(settings, "API_PORT", 18766)
    monkeypatch.setattr(settings, "API_WORKERS", 1)
    monkeypatch.setattr(settings, "LOG_LEVEL", "INFO")
    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["aidefend-mcp", "--api"])

    cli_module.main()

    stderr = capsys.readouterr().err
    assert "API will be available at: http://[::1]:18766" in stderr
    assert "API documentation: http://[::1]:18766/docs" in stderr
    assert calls[0]["host"] == "::1"


def test_container_definition_static_contracts():
    repository_root = Path(__file__).resolve().parents[1]
    dockerfile = (repository_root / 'Dockerfile').read_text(encoding='utf-8')
    compose = (repository_root / 'docker-compose.yml').read_text(encoding='utf-8')
    dockerignore = (repository_root / '.dockerignore').read_text(encoding='utf-8')

    # The slim runtime must carry the native ONNX/OpenMP dependency and must
    # prove imports/parser availability during the image build.
    for contract in (
        'libgomp1',
        'HOME=/home/aidefend',
        'node --check parse_js_module.mjs',
        'node vendor/acorn.mjs',
        'python -m pip check',
        'import app.main, fastembed, lancedb, mcp_server, onnxruntime, pyarrow',
        '--start-period=900s',
    ):
        assert contract in dockerfile

    # Compose must remain externally reachable only with fail-closed API-key
    # authentication. Every local .env setting is forwarded, but these explicit
    # values override unsafe host defaults such as API_HOST=127.0.0.1.
    assert 'env_file:' in compose
    assert 'path: .env' in compose
    assert 'required: false' in compose
    assert 'API_HOST=0.0.0.0' in compose
    assert 'LOCAL_FRAMEWORK_PATH=' in compose
    assert 'AUTH_MODE=${AUTH_MODE:-api_key}' in compose
    assert 'AIDEFEND_API_KEY=${AIDEFEND_API_KEY:?' in compose
    assert 'start_period: 900s' in compose

    # A colon followed by a space turns an unquoted YAML list scalar into a
    # mapping. Guard every interpolated environment list item against the exact
    # bug that previously made docker compose config fail.
    interpolated_items = [
        line.strip()[2:]
        for line in compose.splitlines()
        if line.strip().startswith('- ') and '=${' in line
    ]
    assert interpolated_items
    assert all(': ' not in item for item in interpolated_items)

    ignored_patterns = {
        line.strip()
        for line in dockerignore.splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    }
    assert {
        '.env*',
        'node_modules/',
        'test-artifacts/',
        '.release-check-*/',
        '.wheelcheck/',
        '.tmp_*/',
        'coverage.xml',
        '.claude/',
    } <= ignored_patterns

    # Verify every local COPY input exists and is not directly excluded by a
    # simple root ignore. Multi-stage COPY --from sources are image paths.
    copy_sources = []
    for raw_line in dockerfile.splitlines():
        line = raw_line.strip()
        if not line.startswith('COPY ') or '--from=' in line:
            continue
        copy_sources.extend(line.split()[1:-1])

    assert set(copy_sources) == {
        'requirements.txt',
        'app/',
        '__main__.py',
        'mcp_server.py',
        'parse_js_module.mjs',
        'vendor/',
        'LICENSE',
        'THIRD_PARTY_CONTENT.md',
    }
    simple_ignored_roots = {
        pattern.rstrip('/')
        for pattern in ignored_patterns
        if not any(token in pattern for token in ('*', '?', '['))
    }
    for source in copy_sources:
        assert (repository_root / source).exists(), source
        assert source.rstrip('/') not in simple_ignored_roots, source


def test_blank_container_local_source_does_not_forward_a_native_host_path(monkeypatch):
    monkeypatch.setenv('LOCAL_FRAMEWORK_PATH', '')
    configured = Settings(_env_file=None)
    assert configured.LOCAL_FRAMEWORK_PATH is None
    assert configured.sync_source_mode == 'github'


def test_installed_wheel_defaults_to_platform_user_data_not_site_packages(
    tmp_path, monkeypatch
):
    installed_root = tmp_path / "venv" / "Lib" / "site-packages"
    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setattr(config_module.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

    assert config_module._resolve_default_data_path(installed_root) == (
        local_app_data / "AIDEFEND" / "aidefend-mcp"
    )

    source_root = tmp_path / "source"
    (source_root / "app").mkdir(parents=True)
    (source_root / "pyproject.toml").write_text("[project]", encoding="utf-8")
    assert config_module._resolve_default_data_path(source_root) == source_root / "data"


def test_installed_wheel_relative_storage_override_stays_under_user_data(
    tmp_path, monkeypatch
):
    user_data = tmp_path / "user-data"
    monkeypatch.setattr(config_module, "RELATIVE_STORAGE_BASE", user_data)

    configured = Settings(DATA_PATH=Path("custom"), _env_file=None)

    assert configured.DATA_PATH == (user_data / "custom").resolve()
    assert configured.DB_PATH == configured.DATA_PATH / "aidefend_kb.lancedb"
    assert configured.RAW_PATH == configured.DATA_PATH / "raw_content"
    assert configured.VERSION_FILE == configured.DATA_PATH / "local_version.json"


def test_local_framework_container_instructions_mount_the_host_checkout_read_only():
    repository_root = Path(__file__).resolve().parents[1]
    for guide_name in ('INSTALL.md', 'INSTALL-繁體中文.md'):
        guide = (repository_root / guide_name).read_text(encoding='utf-8')
        assert '--env LOCAL_FRAMEWORK_PATH=/framework' in guide
        assert '--volume ../aidefense-framework:/framework:ro' in guide
        assert 'aidefend-mcp python __main__.py --resync' in guide
        assert 'docker compose run --rm --service-ports' in guide


def test_container_readiness_uses_vendored_parser_and_real_dependencies():
    repository_root = Path(__file__).resolve().parents[1]
    dockerfile = (repository_root / "Dockerfile").read_text(encoding="utf-8")
    compose = (repository_root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "COPY vendor/ ./vendor/" in dockerfile
    assert "npm ci" not in dockerfile
    for container_config in (dockerfile, compose):
        assert "os.environ.get('API_PORT','8000')" in container_config
        assert "c.get('database') and c.get('embedding_model')" in container_config


def test_ci_release_gate_proves_manifest_all_tools_and_zero_skips():
    repository_root = Path(__file__).resolve().parents[1]
    workflow = (
        repository_root / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    for contract in (
        "python __main__.py --resync",
        "python scripts/verify_index_manifest.py",
        "--junitxml=test-artifacts/pytest.xml",
        "Release test suite skipped {skipped} test(s)",
        "python scripts/smoke_all_tools.py --data-path data --transport both --timeout 180",
        "python scripts/build_release_artifacts.py --outdir dist",
        "python scripts/verify_distribution_inventory.py dist",
        "python -m pip_audit -r requirements-dev.txt",
        "npm audit --omit=dev --audit-level=high",
        "docker compose config --quiet",
        "docker build --check .",
        "docker build --tag aidefend-mcp:ci .",
        'AIDEFEND_CI_DATA_VOLUME: aidefend-mcp-ci-data',
        "aidefend-mcp:ci __main__.py --resync",
        "aidefend-mcp:ci scripts/verify_index_manifest.py",
        "aidefend-mcp:ci scripts/smoke_all_tools.py \\",
        "--data-path /app/data",
        "--publish 127.0.0.1:18000:8000",
        "http://127.0.0.1:18000/health",
        "name: Clean wheel -",
        "os: [ubuntu-latest, windows-latest, macos-latest]",
        'python: ["3.10", "3.11", "3.12", "3.13", "3.14"]',
        "scripts/verify_clean_install.py",
        "cp scripts/verify_index_manifest.py /tmp/aidefend-wheel-smoke/scripts/verify_index_manifest.py",
        'export PYTHONPATH=""',
        'export DATA_PATH="$GITHUB_WORKSPACE/data"',
        "assert not Path(app.__file__).resolve().is_relative_to(workspace)",
        "python scripts/verify_index_manifest.py",
        "python scripts/smoke_all_tools.py \\",
        '--data-path "$DATA_PATH"',
    ):
        assert contract in workflow

    assert "timeout-minutes: 60" in workflow
    assert "timeout-minutes: 75" in workflow
    assert workflow.count('node-version: "24"') == 2
    assert 'node-version: "24.19.0"' not in workflow
    assert 'node-version: "22.7.0"' not in workflow
    assert '"node": ">=18.0.0"' in (
        repository_root / "package.json"
    ).read_text(encoding="utf-8")
    assert "npm ci" not in workflow
    clean_install_job = workflow.split("clean-install:", 1)[1].split(
        "\n  container:", 1
    )[0]
    assert "--no-deps" not in clean_install_job
    assert 'PYTHONPATH: ""' in clean_install_job
    assert workflow.count(
        "python scripts/build_release_artifacts.py --outdir dist"
    ) == 2
    assert workflow.count(
        "python scripts/verify_distribution_inventory.py dist"
    ) == 2
    container_job = workflow.split("\n  container:", 1)[1].split("\n  bandit:", 1)[0]
    assert "GITHUB_BRANCH: ${{ github.event.client_payload.framework_ref" in container_job
    assert "source=${{ github.workspace }}/scripts,target=/app/scripts,readonly" in container_job
    assert "scripts/verify_index_manifest.py" in container_job
    assert "scripts/smoke_all_tools.py" in container_job


def test_github_workflows_use_one_current_official_action_major():
    repository_root = Path(__file__).resolve().parents[1]
    action_prefixes = (
        "actions/checkout@",
        "actions/setup-node@",
        "actions/setup-python@",
        "actions/upload-artifact@",
    )

    action_uses = []
    for workflow_path in (repository_root / ".github" / "workflows").glob("*.yml"):
        for raw_line in workflow_path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("uses: ") and any(
                prefix in stripped for prefix in action_prefixes
            ):
                action_uses.append((workflow_path.name, stripped))

    assert action_uses
    assert all(line.endswith("@v7") for _, line in action_uses), action_uses

    security_workflow = (
        repository_root / ".github" / "workflows" / "security.yml"
    ).read_text(encoding="utf-8")
    assert "github/codeql-action/init@v4" in security_workflow
    assert "github/codeql-action/analyze@v4" in security_workflow
    assert "github/codeql-action/init@v3" not in security_workflow


def test_scheduled_security_workflow_is_fail_closed():
    repository_root = Path(__file__).resolve().parents[1]
    workflow = (
        repository_root / ".github" / "workflows" / "security.yml"
    ).read_text(encoding="utf-8")

    assert "bandit -q -r app mcp_server.py __main__.py" in workflow
    assert "python -m pip_audit -r requirements.txt" in workflow
    assert "if-no-files-found: error" in workflow
    assert "continue-on-error" not in workflow
    assert "|| true" not in workflow
    assert "safety check" not in workflow


def test_sync_parser_recovery_guidance_matches_vendored_runtime():
    repository_root = Path(__file__).resolve().parents[1]
    sync_source = (repository_root / "app" / "sync.py").read_text(encoding="utf-8")

    assert "npm install" not in sync_source
    assert "npm list acorn" not in sync_source
    assert "node --check parse_js_module.mjs" in sync_source
    assert "node --check vendor/acorn.mjs" in sync_source


def test_release_runtime_is_explicitly_cpu_only():
    repository_root = Path(__file__).resolve().parents[1]
    core_source = (repository_root / "app" / "core.py").read_text(
        encoding="utf-8"
    )
    benchmark_source = (
        repository_root / "scripts" / "benchmark_search.py"
    ).read_text(encoding="utf-8")
    dependency_metadata = "\n".join(
        (repository_root / name).read_text(encoding="utf-8")
        for name in ("pyproject.toml", "requirements.txt")
    ).lower()

    assert 'task_name="aidefend-embedding-model-load-cpu"' in core_source
    assert "providers=" not in core_source
    assert "CUDAExecutionProvider" not in core_source
    assert "embedding-model-load-gpu" not in core_source
    assert "GPU providers" not in core_source
    assert "GPU if available" not in benchmark_source
    assert "fastembed-gpu" not in dependency_metadata
    assert "onnxruntime-gpu" not in dependency_metadata


def test_public_runtime_does_not_promise_unverified_fixed_speedups():
    repository_root = Path(__file__).resolve().parents[1]
    public_sources = (
        repository_root / "app" / "config.py",
        repository_root / "app" / "core.py",
        repository_root / "app" / "sync.py",
        repository_root / "app" / "tools" / "comprehensive_search.py",
        repository_root / "scripts" / "create_lancedb_index.py",
    )
    combined_source = "\n".join(
        path.read_text(encoding="utf-8") for path in public_sources
    )

    assert "2-5x" not in combined_source
    assert "20-30% faster" not in combined_source
    assert "500-1000ms per search" not in combined_source
    assert "100-300ms per search" not in combined_source
