"""Fail-closed handling for registries embedded in atomic version metadata."""

from __future__ import annotations

import pytest

from app.framework_migrations import FrameworkMigrationRegistryError
from app.framework_utils import (
    framework_labels_from_registry,
    framework_labels_from_version_info,
)
from tests.framework_migration_fixtures import owasp_llm_2026_registry


@pytest.mark.parametrize("invalid_registry", [None, [], "not-an-object"])
def test_present_non_object_registry_in_version_info_fails_closed(
    invalid_registry,
):
    with pytest.raises(
        FrameworkMigrationRegistryError,
        match=r"version_info\.framework_migrations must be an object when present",
    ):
        framework_labels_from_version_info(
            {"framework_migrations": invalid_registry}
        )


def test_present_empty_registry_in_version_info_fails_validation():
    with pytest.raises(
        FrameworkMigrationRegistryError,
        match="schemaVersion is unsupported",
    ):
        framework_labels_from_version_info({"framework_migrations": {}})


def test_absent_registry_key_retains_explicit_legacy_contract():
    labels = framework_labels_from_version_info({"framework_version": "legacy"})
    assert labels["owasp_llm"] == "OWASP LLM Top 10 2025"


def test_current_registry_in_version_info_activates_current_label():
    labels = framework_labels_from_version_info(
        {"framework_migrations": owasp_llm_2026_registry()}
    )
    assert labels["owasp_llm"] == "OWASP LLM Top 10 2026"


@pytest.mark.parametrize("invalid_registry", [[], "not-an-object"])
def test_direct_non_object_registry_input_fails_closed(invalid_registry):
    with pytest.raises(
        FrameworkMigrationRegistryError,
        match="framework migration registry must be an object",
    ):
        framework_labels_from_registry(invalid_registry)
