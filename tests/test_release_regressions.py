"""Focused regressions for the July 2026 framework compatibility release."""

import asyncio
import json
from pathlib import Path

import pytest

import app.sync as sync_module
from app.config import Settings, settings
from app.sync import _calculate_statistics_from_records
from app.tools.implementation_plan import _calculate_recommendation_score


def test_response_phase_receives_recommendation_weight():
    score, breakdown = _calculate_recommendation_score(
        {
            "defends_against": "[]",
            "tools_opensource": "[]",
            "tools_commercial": "[]",
            "phase": json.dumps(["response"]),
            "pillar": "[]",
        }
    )

    assert score == 1.2
    assert breakdown["phase_weight"] == 1.2


def test_implementation_priority_tracks_2026_poisoning_concept_not_legacy_rank():
    def score_for(item):
        return _calculate_recommendation_score(
            {
                "defends_against": json.dumps(
                    [
                        {
                            "framework": "OWASP LLM Top 10 2026",
                            "items": [item],
                        }
                    ]
                ),
                "tools_opensource": "[]",
                "tools_source_available": "[]",
                "tools_commercial": "[]",
                "phase": "[]",
                "pillar": "[]",
            }
        )[1]["threat_importance"]

    assert score_for("LLM05:2026") == 3.0
    assert score_for("LLM03:2026") == 0.0


def test_data_path_override_derives_all_default_storage_paths(tmp_path):
    configured = Settings(DATA_PATH=tmp_path)

    assert configured.DB_PATH == tmp_path / "aidefend_kb.lancedb"
    assert configured.RAW_PATH == tmp_path / "raw_content"
    assert configured.VERSION_FILE == tmp_path / "local_version.json"
    assert configured.LOG_PATH == tmp_path / "logs" / "aidefend_mcp.log"


@pytest.mark.parametrize("field_name", ["DB_PATH", "RAW_PATH", "VERSION_FILE"])
def test_authoritative_storage_cannot_escape_data_path_lease(tmp_path, field_name):
    data_path = tmp_path / "owned" / "data"
    outside_path = data_path / ".." / "shared" / field_name.lower()

    with pytest.raises(ValueError, match=rf"{field_name} must be contained"):
        Settings(
            DATA_PATH=data_path,
            **{field_name: outside_path},
            _env_file=None,
        )


def test_authoritative_storage_paths_are_canonicalized_inside_lease(tmp_path):
    data_path = tmp_path / "owned" / "data"
    configured = Settings(
        DATA_PATH=data_path,
        DB_PATH=data_path / "nested" / ".." / "database",
        RAW_PATH=data_path / "nested" / ".." / "raw",
        VERSION_FILE=data_path / "nested" / ".." / "version.json",
        _env_file=None,
    )

    assert configured.DATA_PATH == data_path.resolve()
    assert configured.DB_PATH == (data_path / "database").resolve()
    assert configured.RAW_PATH == (data_path / "raw").resolve()
    assert configured.VERSION_FILE == (data_path / "version.json").resolve()


def test_code_coverage_counts_strategy_documents_only():
    records = [
        {
            "source_id": "AID-M-001",
            "type": "technique",
            "tactic": "Model",
            "pillar": json.dumps(["model"]),
            "phase": json.dumps(["building"]),
            "implementation_guidance": json.dumps([{"implementation": "One"}]),
            "defends_against": "[]",
            "tools_opensource": "[]",
            "tools_commercial": "[]",
            "has_code_snippets": True,
        },
        {
            "source_id": "AID-M-001.S1",
            "type": "strategy",
            "tactic": "Model",
            "pillar": json.dumps(["model"]),
            "phase": json.dumps(["building"]),
            "implementation_guidance": json.dumps([{"implementation": "One"}]),
            "defends_against": "[]",
            "tools_opensource": "[]",
            "tools_commercial": "[]",
            "has_code_snippets": True,
        },
    ]

    resources = _calculate_statistics_from_records(records)["implementation_resources"]
    assert resources["documents_with_code_snippets"] == 1
    assert resources["strategies_total"] == 1
    assert resources["code_coverage_percentage"] == 100.0


@pytest.mark.asyncio
async def test_sync_loop_checks_immediately(monkeypatch):
    called = asyncio.Event()
    calls = 0

    async def fake_run_sync():
        nonlocal calls
        calls += 1
        called.set()
        return True

    monkeypatch.setattr(sync_module, "run_sync", fake_run_sync)
    monkeypatch.setattr(settings, "ENABLE_AUTO_SYNC", True)
    monkeypatch.setattr(settings, "SYNC_INTERVAL_SECONDS", 3600)

    task = asyncio.create_task(sync_module.sync_loop())
    await asyncio.wait_for(called.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls == 1


@pytest.mark.asyncio
async def test_core_sync_fails_closed_on_one_invalid_tactic(tmp_path, monkeypatch):
    sha = "a" * 40
    tactic_fixtures = {
        "govern.js": ("futureGovern", "Govern", "AID-GV-999"),
        "observe.js": ("futureObserve", "Observe", "AID-OB-999"),
        "recover-next.js": ("futureRecover", "Recover Next", "AID-RN-999"),
    }
    intro_path = tmp_path / "aidefend-intro.js"
    intro_path.write_text('export const aidefendVersion = "1.20260713";', encoding="utf-8")
    manifest_path = tmp_path / "main.js"
    manifest_path.write_text(
        "\n".join(
            [
                f"import {{ {fixture[0]} }} from './tactics/{name}';"
                for name, fixture in tactic_fixtures.items()
            ]
            + [
                "export const aidefendData = { tactics: [",
                ", ".join(fixture[0] for fixture in tactic_fixtures.values()),
                "] };",
            ]
        ),
        encoding="utf-8",
    )
    staged_paths = {"aidefend-intro.js": intro_path}
    for file_name in tactic_fixtures:
        path = tmp_path / file_name
        path.write_text("export const placeholder = {};", encoding="utf-8")
        staged_paths[file_name] = path

    async def fake_fetch_latest_commit_sha():
        return sha

    async def fake_download_file(file_name, _sha):
        return staged_paths[file_name]

    async def fake_download_intro_file(_sha):
        return intro_path

    async def fake_download_manifest_file(_sha):
        return manifest_path

    async def fake_download_framework_public_data_file(
        _sha,
        *,
        previous_source_revision=None,
    ):
        del previous_source_revision
        return sync_module.FrameworkPublicDataStageResult(
            None,
            sync_module.FrameworkPublicDataDiscoveryStatus.INVALID,
        )

    async def fake_download_framework_migrations_file(_sha):
        return None

    def fake_parse_tactic_file(path: Path):
        if path.name == "observe.js":
            return None
        _binding, tactic_name, tactic_id = tactic_fixtures[path.name]
        return {
            "name": tactic_name,
            "purpose": f"Synthetic {tactic_name} tactic.",
            "techniques": [
                {
                    "id": tactic_id,
                    "name": "Test Control",
                    "description": "Valid control used to test fail-closed sync.",
                    "pillar": ["app"],
                    "phase": ["validation"],
                    "defendsAgainst": [
                        {
                            "framework": framework,
                            "items": ["N/A (synthetic fail-closed fixture)"],
                        }
                        for framework in sync_module.EXPECTED_FRAMEWORK_LABELS
                    ],
                    "implementationGuidance": [
                        {
                            "implementation": "Test strategy",
                            "howTo": "<p>Test only.</p>",
                        }
                    ],
                }
            ],
        }

    embed_called = False
    version_saved = False

    async def fake_embed_and_index(_documents, **_kwargs):
        nonlocal embed_called
        embed_called = True
        return True, {}

    def fake_save_version_info(*_args, **_kwargs):
        nonlocal version_saved
        version_saved = True

    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(settings, "LOCAL_FRAMEWORK_PATH", None)
    monkeypatch.setattr(sync_module, "fetch_latest_commit_sha", fake_fetch_latest_commit_sha)
    monkeypatch.setattr(sync_module, "get_local_commit_sha", lambda: None)
    monkeypatch.setattr(sync_module, "load_version_info", lambda: {})
    monkeypatch.setattr(sync_module, "download_file", fake_download_file)
    monkeypatch.setattr(sync_module, "download_intro_file", fake_download_intro_file)
    monkeypatch.setattr(sync_module, "download_manifest_file", fake_download_manifest_file)
    monkeypatch.setattr(
        sync_module,
        "download_framework_migrations_file",
        fake_download_framework_migrations_file,
    )
    monkeypatch.setattr(
        sync_module,
        "download_framework_public_data_file",
        fake_download_framework_public_data_file,
    )
    monkeypatch.setattr(sync_module, "extract_framework_version", lambda _path: "1.20260713")
    monkeypatch.setattr(sync_module, "parse_tactic_file", fake_parse_tactic_file)
    monkeypatch.setattr(sync_module, "embed_and_index", fake_embed_and_index)
    monkeypatch.setattr(sync_module, "save_version_info", fake_save_version_info)

    assert await sync_module.core_sync() is False
    assert embed_called is False
    assert version_saved is False


@pytest.mark.asyncio
async def test_core_sync_routes_metadata_commit_through_activation_without_cleanup_on_failure(
    tmp_path, monkeypatch
):
    sha = "b" * 40
    manifest_path = tmp_path / "main.js"
    tactic_path = tmp_path / "model.js"
    intro_path = tmp_path / "aidefend-intro.js"
    for path in (manifest_path, tactic_path, intro_path):
        path.write_text("// synthetic sync fixture", encoding="utf-8")

    async def fake_fetch_latest_commit_sha():
        return sha

    async def fake_download_manifest_file(_sha):
        return manifest_path

    async def fake_download_file(_file_name, _sha):
        return tactic_path

    async def fake_download_intro_file(_sha):
        return intro_path

    async def fake_download_framework_migrations_file(_sha):
        return None

    async def fake_download_framework_public_data_file(_sha, *, previous_source_revision=None):
        del previous_source_revision
        return sync_module.FrameworkPublicDataStageResult(
            path=None,
            status=sync_module.FrameworkPublicDataDiscoveryStatus.INVALID,
        )

    async def fake_embed_and_index(_documents, **kwargs):
        statistics = {
            "overview": {
                "total_documents": 1,
                "total_actionable_items": 1,
            }
        }
        commit_sha, metadata = kwargs["version_metadata_builder"](statistics)
        assert metadata["framework_public_schema_version"] == "unknown"
        assert "framework_public_schema_source" not in metadata
        try:
            sync_module.save_version_info(commit_sha, dict(metadata))
        except OSError:
            events.append("activation-failed")
            return False, None
        raise AssertionError("synthetic metadata write unexpectedly succeeded")

    events = []

    def fail_save_version_info(*_args, **_kwargs):
        events.append("save")
        raise OSError("simulated metadata write failure")

    async def unexpected_cleanup():
        events.append("cleanup")
        return True

    async def unexpected_vector_index():
        events.append("vector-index")

    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "aidefend_kb.lancedb")
    monkeypatch.setattr(sync_module, "_using_local_framework_source", lambda: False)
    monkeypatch.setattr(sync_module, "fetch_latest_commit_sha", fake_fetch_latest_commit_sha)
    monkeypatch.setattr(sync_module, "download_manifest_file", fake_download_manifest_file)
    monkeypatch.setattr(
        sync_module,
        "download_framework_migrations_file",
        fake_download_framework_migrations_file,
    )
    monkeypatch.setattr(
        sync_module,
        "download_framework_public_data_file",
        fake_download_framework_public_data_file,
    )
    monkeypatch.setattr(sync_module, "parse_staged_tactic_manifest", lambda _path: ["model.js"])
    monkeypatch.setattr(
        sync_module,
        "_framework_source_files",
        lambda _tactic_files, **_kwargs: ["model.js", "aidefend-intro.js"],
    )
    monkeypatch.setattr(sync_module, "get_local_commit_sha", lambda: None)
    monkeypatch.setattr(sync_module, "load_version_info", lambda: {})
    monkeypatch.setattr(sync_module, "download_file", fake_download_file)
    monkeypatch.setattr(sync_module, "download_intro_file", fake_download_intro_file)
    monkeypatch.setattr(
        sync_module,
        "_compute_staged_framework_digest",
        lambda *_args, **_kwargs: "d" * 64,
    )
    monkeypatch.setattr(sync_module, "extract_framework_version", lambda _path: "1.20260724")
    monkeypatch.setattr(sync_module, "parse_tactic_file", lambda _path: {"name": "Model"})
    monkeypatch.setattr(sync_module, "validate_tactic_contract", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        sync_module,
        "validate_framework_migrations_corpus_contract",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        sync_module,
        "extract_documents_from_tactic",
        lambda _tactic: [{"source_id": "AID-M-001"}],
    )
    monkeypatch.setattr(sync_module, "embed_and_index", fake_embed_and_index)
    monkeypatch.setattr(sync_module, "save_version_info", fail_save_version_info)
    monkeypatch.setattr(sync_module, "_cleanup_successful_sync_artifacts", unexpected_cleanup)
    monkeypatch.setattr(sync_module, "_create_vector_index_if_needed", unexpected_vector_index)

    assert await sync_module.core_sync(force_rebuild=True) is False
    assert events == ["save", "activation-failed"]
    assert "Failed to embed and index documents" in sync_module.get_last_sync_error()
