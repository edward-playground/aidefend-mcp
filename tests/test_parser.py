"""
Test script for Node.js JavaScript parser.
Verifies parsing of AIDEFEND tactic files.
"""

from pathlib import Path
import sys
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils import parse_js_file_with_node
from app.framework_manifest import FrameworkManifestError, parse_tactic_manifest


def _manifest_defined_source(settings):
    candidates = []
    if settings.LOCAL_FRAMEWORK_PATH:
        candidates.append(Path(settings.LOCAL_FRAMEWORK_PATH))
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "aidefense-framework",
            settings.RAW_PATH,
        ]
    )
    failures = []
    for root in candidates:
        manifest_path = root / "main.js"
        if not manifest_path.is_file():
            failures.append(f"{manifest_path}: missing")
            continue
        try:
            tactic_files = parse_tactic_manifest(
                manifest_path.read_text(encoding="utf-8-sig"),
                tactics_path=settings.GITHUB_TACTICS_PATH,
            )
        except (OSError, UnicodeError, FrameworkManifestError) as exc:
            failures.append(f"{manifest_path}: {exc}")
            continue

        tactic_root = root / "tactics" if (root / "tactics").is_dir() else root
        missing = [name for name in tactic_files if not (tactic_root / name).is_file()]
        if missing:
            failures.append(f"{manifest_path}: missing tactic files {missing}")
            continue
        return tactic_root, tactic_files

    pytest.fail("No complete manifest-defined AIDEFEND source is available: " + "; ".join(failures))


def test_parse_files(monkeypatch):
    """Test Node.js parser on all tactic files."""

    from app.config import settings

    raw_path, test_files = _manifest_defined_source(settings)
    monkeypatch.setattr(settings, "RAW_PATH", raw_path)

    print("Testing Node.js parser on AIDEFEND tactic files...")
    print("=" * 60)

    success_count = 0
    fail_count = 0

    for filename in test_files:
        file_path = raw_path / filename

        assert file_path.is_file(), f"Missing tactic source: {file_path}"

        try:
            result = parse_js_file_with_node(file_path)

            tactic_name = result.get("name", "Unknown")
            technique_count = len(result.get("techniques", []))

            print(f"[PASS] {filename}")
            print(f"       Tactic: {tactic_name}")
            print(f"       Techniques: {technique_count}")
            print()

            success_count += 1

        except Exception as e:
            print(f"[FAIL] {filename}")
            print(f"       Error: {e}")
            print()

            fail_count += 1

    print("=" * 60)
    print(f"Results: {success_count} success, {fail_count} failed")

    assert success_count == len(test_files)
    assert fail_count == 0, f"{fail_count} files failed to parse"

    print("\nAll files parsed successfully!")


if __name__ == "__main__":
    raise SystemExit("Run this parser contract with pytest")
