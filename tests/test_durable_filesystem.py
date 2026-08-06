"""Cross-platform regressions for transaction filesystem primitives."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.sync as sync_module
import app.utils as utils_module


def test_durable_rename_moves_directory_tree(tmp_path):
    source = tmp_path / "aidefend_new_sync.lance"
    destination = tmp_path / "aidefend.lance"
    source.mkdir()
    (source / "generation.txt").write_text("new", encoding="utf-8")

    utils_module._durable_rename(source, destination)

    assert not source.exists()
    assert destination.is_dir()
    assert (destination / "generation.txt").read_text(encoding="utf-8") == "new"


def test_durable_rename_refuses_existing_destination(tmp_path):
    source = tmp_path / "source.lance"
    destination = tmp_path / "destination.lance"
    source.mkdir()
    destination.mkdir()
    (source / "generation.txt").write_text("source", encoding="utf-8")
    (destination / "generation.txt").write_text("destination", encoding="utf-8")

    with pytest.raises(FileExistsError, match="destination already exists"):
        utils_module._durable_rename(source, destination)

    assert (source / "generation.txt").read_text(encoding="utf-8") == "source"
    assert (destination / "generation.txt").read_text(encoding="utf-8") == "destination"


def test_durable_rename_missing_source_does_not_create_destination(tmp_path):
    source = tmp_path / "missing.lance"
    destination = tmp_path / "destination.lance"

    with pytest.raises(OSError):
        utils_module._durable_rename(source, destination)

    assert not source.exists()
    assert not destination.exists()


def test_durable_rename_windows_move_failure_retains_source(tmp_path, monkeypatch):
    source = tmp_path / "source.lance"
    destination = tmp_path / "destination.lance"
    source.mkdir()
    (source / "generation.txt").write_text("retain", encoding="utf-8")
    real_os = utils_module.os
    fake_os = SimpleNamespace(name="nt", path=real_os.path)
    monkeypatch.setattr(utils_module, "os", fake_os)

    def fail_move(*_args, **_kwargs):
        raise OSError("synthetic MoveFileExW failure")

    monkeypatch.setattr(utils_module, "_windows_move_file", fail_move)

    with pytest.raises(OSError, match="synthetic MoveFileExW failure"):
        utils_module._durable_rename(source, destination)

    assert (source / "generation.txt").read_text(encoding="utf-8") == "retain"
    assert not destination.exists()


def test_durable_unlink_removes_regular_file(tmp_path):
    marker = tmp_path / "generation_activation.pending.json"
    marker.write_text('{"schema_version":"test"}', encoding="utf-8")

    utils_module._durable_unlink(marker)

    assert not marker.exists()
    assert list(tmp_path.glob(f".{marker.name}.deleted-*")) == []


def test_durable_unlink_missing_file_obeys_missing_ok(tmp_path):
    marker = tmp_path / "missing.pending.json"

    utils_module._durable_unlink(marker, missing_ok=True)

    with pytest.raises(FileNotFoundError):
        utils_module._durable_unlink(marker, missing_ok=False)


def test_durable_unlink_rejects_directory_without_moving_it(tmp_path):
    marker = tmp_path / "generation_activation.pending.json"
    marker.mkdir()
    (marker / "evidence.txt").write_text("retain", encoding="utf-8")

    with pytest.raises(IsADirectoryError, match="must be a file"):
        utils_module._durable_unlink(marker, missing_ok=True)

    assert marker.is_dir()
    assert (marker / "evidence.txt").read_text(encoding="utf-8") == "retain"
    assert list(tmp_path.glob(f".{marker.name}.deleted-*")) == []


def test_durable_unlink_windows_move_failure_retains_source(tmp_path, monkeypatch):
    marker = tmp_path / "generation_activation.pending.json"
    marker.write_text('{"schema_version":"test"}', encoding="utf-8")
    real_os = utils_module.os
    fake_os = SimpleNamespace(
        name="nt",
        lstat=real_os.lstat,
        getpid=real_os.getpid,
        path=real_os.path,
    )
    monkeypatch.setattr(utils_module, "os", fake_os)

    def fail_move(*_args, **_kwargs):
        raise OSError("synthetic MoveFileExW failure")

    monkeypatch.setattr(utils_module, "_durable_rename", fail_move)

    with pytest.raises(OSError, match="synthetic MoveFileExW failure"):
        utils_module._durable_unlink(marker, missing_ok=True)

    assert marker.read_text(encoding="utf-8") == '{"schema_version":"test"}'
    assert list(tmp_path.glob(f".{marker.name}.deleted-*")) == []


def test_fsync_directory_flushes_and_closes_descriptor(tmp_path, monkeypatch):
    calls = []
    real_os = utils_module.os

    fake_os = SimpleNamespace(
        O_RDONLY=real_os.O_RDONLY,
        O_DIRECTORY=getattr(real_os, "O_DIRECTORY", 0),
        open=lambda path, flags: calls.append(("open", path, flags)) or 73,
        fsync=lambda descriptor: calls.append(("fsync", descriptor)),
        close=lambda descriptor: calls.append(("close", descriptor)),
    )
    monkeypatch.setattr(utils_module, "os", fake_os)

    utils_module._fsync_directory(tmp_path)

    assert calls == [
        (
            "open",
            str(tmp_path),
            real_os.O_RDONLY | getattr(real_os, "O_DIRECTORY", 0),
        ),
        ("fsync", 73),
        ("close", 73),
    ]


def test_fsync_directory_closes_descriptor_when_flush_fails(tmp_path, monkeypatch):
    calls = []
    real_os = utils_module.os

    def fail_fsync(descriptor):
        calls.append(("fsync", descriptor))
        raise OSError("synthetic directory fsync failure")

    fake_os = SimpleNamespace(
        O_RDONLY=real_os.O_RDONLY,
        O_DIRECTORY=getattr(real_os, "O_DIRECTORY", 0),
        open=lambda path, flags: calls.append(("open", path, flags)) or 91,
        fsync=fail_fsync,
        close=lambda descriptor: calls.append(("close", descriptor)),
    )
    monkeypatch.setattr(utils_module, "os", fake_os)

    with pytest.raises(OSError, match="synthetic directory fsync failure"):
        utils_module._fsync_directory(tmp_path)

    assert calls[-2:] == [("fsync", 91), ("close", 91)]


class _FakeMoveFileEx:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, source, destination, flags):
        self.calls.append((source, destination, flags))
        return self.result


@pytest.mark.parametrize(
    ("replace_existing", "expected_flags"),
    ((False, 0x8), (True, 0x9)),
)
def test_windows_move_file_uses_write_through_flags(
    tmp_path,
    monkeypatch,
    replace_existing,
    expected_flags,
):
    move_file_ex = _FakeMoveFileEx(result=1)
    fake_windll = SimpleNamespace(
        kernel32=SimpleNamespace(MoveFileExW=move_file_ex)
    )
    monkeypatch.setattr(utils_module.ctypes, "windll", fake_windll, raising=False)
    source = tmp_path / "source"
    destination = tmp_path / "destination"

    utils_module._windows_move_file(
        source,
        destination,
        replace_existing=replace_existing,
    )

    assert move_file_ex.calls == [
        (str(source), str(destination), expected_flags)
    ]


def test_windows_move_file_failure_propagates_without_fallback(tmp_path, monkeypatch):
    move_file_ex = _FakeMoveFileEx(result=0)
    fake_windll = SimpleNamespace(
        kernel32=SimpleNamespace(MoveFileExW=move_file_ex)
    )
    expected_error = OSError("synthetic MoveFileExW failure")
    monkeypatch.setattr(utils_module.ctypes, "windll", fake_windll, raising=False)
    monkeypatch.setattr(
        utils_module.ctypes,
        "WinError",
        lambda: expected_error,
        raising=False,
    )
    source = tmp_path / "source"
    destination = tmp_path / "destination"

    with pytest.raises(OSError, match="synthetic MoveFileExW failure") as raised:
        utils_module._windows_move_file(
            source,
            destination,
            replace_existing=False,
        )

    assert raised.value is expected_error
    assert move_file_ex.calls == [(str(source), str(destination), 0x8)]


def test_tombstone_cleanup_is_exact_and_refuses_non_regular_entries(
    tmp_path,
    monkeypatch,
):
    regular = tmp_path / (
        ".generation_activation.pending.json.deleted-123-"
        "0000000000000001"
    )
    regular.write_text("retained deletion debris", encoding="utf-8")
    directory = tmp_path / (
        ".generation_activation.pending.json.deleted-123-"
        "0000000000000002"
    )
    directory.mkdir()
    unknown = tmp_path / ".unrelated.deleted-123-0000000000000003"
    unknown.write_text("unrelated", encoding="utf-8")

    monkeypatch.setattr(sync_module.settings, "DATA_PATH", tmp_path)
    monkeypatch.setattr(sync_module.settings, "DB_PATH", tmp_path)

    sync_module._cleanup_durable_tombstones_best_effort()

    assert not regular.exists()
    assert directory.is_dir()
    assert unknown.read_text(encoding="utf-8") == "unrelated"


def test_tombstone_cleanup_has_a_bounded_eligible_scan(tmp_path, monkeypatch):
    tombstones = []
    for index in range(3):
        tombstone = tmp_path / (
            ".generation_activation.pending.json.deleted-123-"
            f"{index:016x}"
        )
        tombstone.write_text("debris", encoding="utf-8")
        tombstones.append(tombstone)

    monkeypatch.setattr(sync_module.settings, "DATA_PATH", tmp_path)
    monkeypatch.setattr(sync_module.settings, "DB_PATH", tmp_path)
    monkeypatch.setattr(sync_module, "MAX_DURABLE_TOMBSTONES_PER_CLEANUP", 2)

    sync_module._cleanup_durable_tombstones_best_effort()

    assert [path.exists() for path in tombstones] == [False, False, True]


def test_tombstone_cleanup_includes_nested_version_file_parent(
    tmp_path, monkeypatch
):
    database_root = tmp_path / "database" / "aidefend_kb.lancedb"
    version_root = tmp_path / "nested" / "state"
    database_root.mkdir(parents=True)
    version_root.mkdir(parents=True)

    marker_tombstone = version_root / (
        ".generation_activation.pending.json.deleted-123-"
        "0000000000000001"
    )
    sidecar_tombstone = database_root / (
        ".aidefend_backup.version.json.deleted-123-"
        "0000000000000002"
    )
    marker_tombstone.write_text("marker debris", encoding="utf-8")
    sidecar_tombstone.write_text("sidecar debris", encoding="utf-8")

    monkeypatch.setattr(sync_module.settings, "DATA_PATH", tmp_path)
    monkeypatch.setattr(sync_module.settings, "DB_PATH", database_root)
    monkeypatch.setattr(
        sync_module.settings,
        "VERSION_FILE",
        version_root / "local_version.json",
    )

    sync_module._cleanup_durable_tombstones_best_effort()

    assert marker_tombstone.exists() is False
    assert sidecar_tombstone.exists() is False
