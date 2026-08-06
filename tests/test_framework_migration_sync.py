"""Fail-closed synchronization gates for the public migration registry."""

from __future__ import annotations

import json

import pytest

import app.sync as sync_module
from app.config import settings
from app.framework_migrations import FrameworkMigrationRegistryError
from tests.framework_migration_fixtures import owasp_llm_2026_registry


def _parsed_tactics(label: object, item: object):
    return [
        {
            "name": "Harden",
            "techniques": [
                {
                    "id": "AID-H-001",
                    "defendsAgainst": [
                        {"framework": label, "items": [item]}
                    ],
                }
            ],
        }
    ]


def test_registry_loader_accepts_strict_utf8_json(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    path = tmp_path / sync_module.FRAMEWORK_MIGRATIONS_FILENAME
    registry = owasp_llm_2026_registry()
    path.write_text(json.dumps(registry), encoding="utf-8-sig")
    assert sync_module.load_and_validate_framework_migrations(path) == registry
    assert sync_module.compute_framework_migrations_sha256(path)


@pytest.mark.parametrize(
    "payload",
    [
        b"[]",
        b'{"schemaVersion":"1.0","schemaVersion":"1.0"}',
        b'{"schemaVersion":NaN}',
        b"\xff\xfe\xfa",
        b"{",
    ],
)
def test_registry_loader_rejects_non_object_duplicate_nonfinite_and_invalid_json(
    tmp_path, monkeypatch, payload
):
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    path = tmp_path / sync_module.FRAMEWORK_MIGRATIONS_FILENAME
    path.write_bytes(payload)
    with pytest.raises(FrameworkMigrationRegistryError):
        sync_module.load_and_validate_framework_migrations(path)


def test_registry_loader_enforces_size_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RAW_PATH", tmp_path)
    monkeypatch.setattr(sync_module, "MAX_FRAMEWORK_MIGRATIONS_BYTES", 8)
    path = tmp_path / sync_module.FRAMEWORK_MIGRATIONS_FILENAME
    path.write_bytes(b"{}" * 5)
    with pytest.raises(FrameworkMigrationRegistryError, match="size"):
        sync_module.load_and_validate_framework_migrations(path)


def test_corpus_contract_accepts_only_matching_legacy_or_active_editions():
    sync_module.validate_framework_migrations_corpus_contract(
        None,
        _parsed_tactics(
            "OWASP LLM Top 10 2025",
            "LLM01:2025 Prompt Injection",
        ),
    )
    sync_module.validate_framework_migrations_corpus_contract(
        owasp_llm_2026_registry(),
        _parsed_tactics(
            "OWASP LLM Top 10 2026",
            "LLM01:2026 Prompt Injection",
        ),
    )
    sync_module.validate_framework_migrations_corpus_contract(
        owasp_llm_2026_registry(),
        _parsed_tactics("OWASP LLM Top 10 2026", "N/A"),
    )


@pytest.mark.parametrize(
    "registry, label, item",
    [
        (None, " OWASP LLM Top 10 2025", "LLM01:2025 Prompt Injection"),
        (None, 2025, "LLM01:2025 Prompt Injection"),
        (
            None,
            "OWASP LLM Top 10 2026",
            "LLM01:2026 Prompt Injection",
        ),
        (
            owasp_llm_2026_registry(),
            "OWASP LLM Top 10 2026 ",
            "LLM01:2026 Prompt Injection",
        ),
        (
            owasp_llm_2026_registry(),
            "OWASP LLM Top 10 2025",
            "LLM01:2025 Prompt Injection",
        ),
        (
            owasp_llm_2026_registry(),
            "OWASP LLM Top 10 2026",
            " LLM01:2026 Prompt Injection",
        ),
        (
            owasp_llm_2026_registry(),
            "OWASP LLM Top 10 2026",
            "LLM01:2025 Prompt Injection",
        ),
        (
            owasp_llm_2026_registry(),
            "OWASP LLM Top 10 2026",
            "LLM01:2026 Wrong Name",
        ),
        (
            owasp_llm_2026_registry(),
            "OWASP LLM Top 10 2026",
            "N/A (not exact)",
        ),
    ],
)
def test_corpus_contract_rejects_label_and_item_drift(registry, label, item):
    with pytest.raises(FrameworkMigrationRegistryError):
        sync_module.validate_framework_migrations_corpus_contract(
            registry,
            _parsed_tactics(label, item),
        )


def test_sync_statistics_label_comes_from_staged_registry_not_old_metadata():
    record = {
        "source_id": "AID-H-001.001",
        "type": "subtechnique",
        "tactic": "Harden",
        "pillar": '["app"]',
        "phase": '["operation"]',
        "scope_boundary": "{}",
        "is_actionable": True,
        "is_parent_family": False,
        "defends_against": json.dumps(
            [
                {
                    "framework": "OWASP LLM Top 10 2026",
                    "items": ["LLM01:2026 Prompt Injection"],
                }
            ]
        ),
        "tools_opensource": "[]",
        "tools_source_available": "[]",
        "tools_commercial": "[]",
        "guidance_id": "",
    }
    labels = sync_module.framework_labels_from_registry(
        owasp_llm_2026_registry()
    )
    statistics = sync_module._calculate_statistics_from_records(
        [record], framework_labels=labels
    )
    assert statistics["threat_framework_coverage"]["by_framework"][
        "owasp_llm"
    ]["label"] == "OWASP LLM Top 10 2026"
