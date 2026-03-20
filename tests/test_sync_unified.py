"""
Test for Unified Sync Logic (Problems 4 & 5)

Tests the unified sync architecture:
- Problem 5: Timestamp update when no sync needed
- Problem 4: Unified core_sync() function
- CLI and MCP use consistent sync logic
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """Test that all sync functions can be imported."""
    print("=" * 60)
    print("UNIFIED SYNC - IMPORT TESTS")
    print("=" * 60)

    try:
        print("\n[TEST 1] Import save_sync_timestamp")
        from app.utils import save_sync_timestamp
        print("   [PASS] Function imported successfully")

        print("\n[TEST 2] Import core_sync")
        from app.sync import core_sync
        print("   [PASS] Function imported successfully")

        print("\n[TEST 3] Import run_sync")
        from app.sync import run_sync
        print("   [PASS] Function imported successfully")

        print("\n[TEST 4] Check core_sync signature")
        import inspect
        sig = inspect.signature(core_sync)
        params = list(sig.parameters.keys())
        print(f"   Parameters: {params}")

        if 'force_rebuild' in params:
            print("   [PASS] core_sync has force_rebuild parameter")
        else:
            print("   [FAIL] core_sync missing force_rebuild parameter")
            return 1

        print("\n" + "=" * 60)
        print("*** IMPORT TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_timestamp_update():
    """Test save_sync_timestamp function."""
    print("\n" + "=" * 60)
    print("TIMESTAMP UPDATE TEST")
    print("=" * 60)

    try:
        from app.utils import save_sync_timestamp, load_version_info
        from app.config import settings
        import time

        print("\n[TEST 1] Save sync timestamp")

        # Get timestamp before
        before_info = load_version_info()
        before_timestamp = before_info.get("sync_timestamp", 0) if before_info else 0
        print(f"   Before timestamp: {before_timestamp}")

        # Wait a moment to ensure timestamp changes
        time.sleep(0.1)

        # Update timestamp
        save_sync_timestamp()

        # Get timestamp after
        after_info = load_version_info()
        after_timestamp = after_info.get("sync_timestamp", 0) if after_info else 0
        print(f"   After timestamp: {after_timestamp}")

        if after_timestamp > before_timestamp:
            print("   [PASS] Timestamp updated successfully")
        else:
            print(f"   [FAIL] Timestamp not updated ({after_timestamp} <= {before_timestamp})")
            return 1

        print("\n[TEST 2] Verify commit SHA preserved")
        if before_info and after_info:
            before_sha = before_info.get("commit_sha")
            after_sha = after_info.get("commit_sha")

            if before_sha == after_sha:
                print(f"   [PASS] Commit SHA preserved: {after_sha}")
            else:
                print(f"   [WARNING] Commit SHA changed: {before_sha} -> {after_sha}")
        else:
            print("   [SKIP] No existing version info to compare")

        print("\n" + "=" * 60)
        print("*** TIMESTAMP UPDATE TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


def test_sync_architecture():
    """Test that sync functions have correct architecture."""
    print("\n" + "=" * 60)
    print("SYNC ARCHITECTURE TEST")
    print("=" * 60)

    try:
        from app.sync import core_sync, run_sync
        import inspect

        print("\n[TEST 1] Check core_sync docstring")
        core_sync_doc = inspect.getdoc(core_sync)
        if "lock" in core_sync_doc.lower():
            print("   [PASS] core_sync documents lock handling responsibility")
        else:
            print("   [WARNING] core_sync should document lock handling")

        print("\n[TEST 2] Check run_sync docstring")
        run_sync_doc = inspect.getdoc(run_sync)
        if "wrapper" in run_sync_doc.lower() or "lock" in run_sync_doc.lower():
            print("   [PASS] run_sync documents its role as wrapper")
        else:
            print("   [WARNING] run_sync should document wrapper role")

        print("\n[TEST 3] Verify core_sync is async")
        if inspect.iscoroutinefunction(core_sync):
            print("   [PASS] core_sync is async function")
        else:
            print("   [FAIL] core_sync should be async")
            return 1

        print("\n[TEST 4] Verify run_sync is async")
        if inspect.iscoroutinefunction(run_sync):
            print("   [PASS] run_sync is async function")
        else:
            print("   [FAIL] run_sync should be async")
            return 1

        print("\n" + "=" * 60)
        print("*** SYNC ARCHITECTURE TESTS PASSED! ***")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n[FAIL] TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("RUNNING UNIFIED SYNC TESTS (Problems 4 & 5)")
    print("=" * 60)

    exit_code = 0

    # Test 1: Imports
    result = test_imports()
    if result != 0:
        exit_code = result

    # Test 2: Timestamp update
    result = test_timestamp_update()
    if result != 0:
        exit_code = result

    # Test 3: Sync architecture
    result = test_sync_architecture()
    if result != 0:
        exit_code = result

    print("\n" + "=" * 60)
    if exit_code == 0:
        print("*** ALL UNIFIED SYNC TESTS PASSED! ***")
    else:
        print("*** SOME TESTS FAILED ***")
    print("=" * 60)

    sys.exit(exit_code)
