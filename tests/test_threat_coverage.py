"""Contract tests for threat coverage and framework mapping normalization."""

import pytest

from app.framework_utils import (
    FRAMEWORK_LABELS,
    build_framework_metrics,
    coverage_lists_from_sets,
    extract_framework_coverage,
    framework_key,
    merge_framework_coverage_sets,
    normalize_framework_item,
)
from app.security import InputValidationError
from app.tools.threat_coverage import get_threat_coverage


def test_imports():
    """The public tool is exported from both supported import locations."""
    from app.tools import get_threat_coverage as exported_tool

    assert callable(get_threat_coverage)
    assert exported_tool is get_threat_coverage


@pytest.mark.asyncio
async def test_parameter_validation_runs_before_database_access():
    """Invalid container shape, members, and size fail without a database."""
    with pytest.raises(InputValidationError, match="must be a list"):
        await get_threat_coverage("AID-H-001")

    with pytest.raises(InputValidationError, match="only strings"):
        await get_threat_coverage(["AID-H-001", 42])

    with pytest.raises(InputValidationError, match="max 200"):
        await get_threat_coverage([f"AID-H-{index:03d}" for index in range(201)])


@pytest.mark.asyncio
async def test_empty_list_produces_zero_coverage_baseline(monkeypatch):
    """Empty implementations are a supported baseline, not a validation error."""
    import app.core as core_module

    class EmptyQueryEngine:
        is_ready = True

        async def read_table(self, callback):
            return []

        async def read_table_snapshot(self, _callback):
            return [], None

    monkeypatch.setattr(core_module, "query_engine", EmptyQueryEngine())

    result = await get_threat_coverage([])

    assert result["input_count"] == 0
    assert result["valid_count"] == 0
    assert result["invalid_count"] == 0
    assert result["by_technique"] == []
    assert all(rate == 0.0 for rate in result["coverage_rate"].values())
    assert all(items == [] for items in result["covered"].values())


def test_framework_mapping_normalization_uses_schema_23_labels():
    """All current framework families normalize to stable public identifiers."""
    mappings = [
        {
            "framework": "OWASP LLM Top 10 2025",
            "items": ["LLM01:2025 Prompt Injection"],
        },
        {
            "framework": "OWASP ML Top 10 2023",
            "items": ["ML03:2023 Model Inversion Attack"],
        },
        {
            "framework": "OWASP Top 10 for Agentic Applications 2026",
            "items": ["ASI02:2026 Tool Misuse"],
        },
        {
            "framework": "MITRE ATLAS",
            "items": ["AML.T0043.001 Craft Adversarial Data"],
        },
        {
            "framework": "MAESTRO",
            "items": ["Agent Tool Misuse (L7)"],
        },
        {
            "framework": "NIST Adversarial Machine Learning 2025",
            "items": ["NISTAML.004 Evasion"],
        },
        {
            "framework": "Cisco Integrated AI Security and Safety Framework",
            "items": ["AISubtech-2.1 Runtime input validation"],
        },
        {
            "framework": "Google Secure AI Framework 2.0 - Risks",
            "items": ["MODEL-01: Model manipulation"],
        },
        {
            "framework": "Databricks AI Security Framework 3.0",
            "items": ["Model Serving Abuse (runtime)"],
        },
    ]

    coverage = extract_framework_coverage(mappings)

    assert coverage["owasp_llm"] == {"LLM01"}
    assert coverage["owasp_ml"] == {"ML03:2023"}
    assert coverage["owasp_agentic"] == {"ASI02:2026"}
    assert coverage["atlas"] == {"AML.T0043.001"}
    assert coverage["maestro"] == {"Agent Tool Misuse (L7)"}
    assert coverage["nist_aml"] == {"NISTAML.004"}
    assert coverage["cisco"] == {"AISUBTECH-2.1"}
    assert coverage["google_saif"] == {"MODEL-01"}
    assert coverage["databricks"] == {"Model Serving Abuse"}


def test_agentic_framework_rename_preserves_stable_key_and_legacy_input():
    """The source rename changes display text without breaking API identifiers."""
    current_label = "OWASP Top 10 for Agentic Applications 2026"
    legacy_label = "OWASP Agentic AI Top 10 2026"

    assert FRAMEWORK_LABELS["owasp_agentic"] == current_label
    assert framework_key(current_label) == "owasp_agentic"
    assert framework_key(legacy_label) == "owasp_agentic"
    assert (
        normalize_framework_item(current_label, "ASI02:2026 Tool Misuse")
        == "ASI02:2026"
    )
    assert (
        normalize_framework_item(legacy_label, "ASI02:2026 Tool Misuse")
        == "ASI02:2026"
    )


def test_framework_merge_deduplicates_and_builds_owasp_union():
    first = extract_framework_coverage([
        {"framework": "OWASP LLM Top 10 2025", "items": ["LLM01"]},
        {"framework": "MITRE ATLAS", "items": ["AML.T0043"]},
    ])
    second = extract_framework_coverage([
        {"framework": "OWASP LLM Top 10 2025", "items": ["LLM01", "LLM02"]},
        {"framework": "OWASP ML Top 10 2023", "items": ["ML03:2023"]},
    ])

    merged = coverage_lists_from_sets(merge_framework_coverage_sets(first, second))

    assert merged["owasp_llm"] == ["LLM01", "LLM02"]
    assert merged["owasp_ml"] == ["ML03:2023"]
    assert merged["owasp"] == ["LLM01", "LLM02", "ML03:2023"]
    assert merged["atlas"] == ["AML.T0043"]


def test_additive_framework_label_is_preserved_in_coverage_and_metrics():
    label = "OpenSSF AI Model Signing Profile"
    dynamic_key = f"framework:{label}"
    first = extract_framework_coverage(
        [{"framework": label, "items": ["AIM-1: Verify model provenance"]}]
    )
    second = extract_framework_coverage(
        [{"framework": label, "items": ["AIM-2: Verify deployment identity"]}]
    )

    total = merge_framework_coverage_sets(first, second)
    metrics = build_framework_metrics(first, total)

    assert first[dynamic_key] == {"AIM-1"}
    assert total[dynamic_key] == {"AIM-1", "AIM-2"}
    assert metrics["by_framework"][label] == {
        "label": label,
        "items_covered": 1,
        "total_items": None,
        "coverage_percentage": None,
        "coverage_scope": "mapped_items_count_only",
    }
    assert metrics["mitre_atlas_items_covered"] == 0
