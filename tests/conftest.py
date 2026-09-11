"""Explicit environment isolation for tests that construct their own storage."""

import pytest


@pytest.fixture
def isolated_storage_environment(monkeypatch):
    """Keep live-corpus settings intact while isolating per-test Settings inputs."""
    for name in ("DATA_PATH", "DB_PATH", "RAW_PATH", "VERSION_FILE", "LOG_PATH"):
        monkeypatch.delenv(name, raising=False)
