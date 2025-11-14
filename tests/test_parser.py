"""
Test script for Node.js JavaScript parser.
Verifies parsing of AIDEFEND tactic files.
"""

from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils import parse_js_file_with_node

def test_parse_files():
    """Test Node.js parser on all tactic files."""

    test_files = [
        "model.js",
        "harden.js",
        "detect.js",
        "isolate.js",
        "deceive.js",
        "evict.js",
        "restore.js"
    ]

    raw_path = Path("data/raw_content")

    print("Testing Node.js parser on AIDEFEND tactic files...")
    print("=" * 60)

    success_count = 0
    fail_count = 0

    for filename in test_files:
        file_path = raw_path / filename

        if not file_path.exists():
            print(f"[SKIP] {filename} (file not found)")
            continue

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

    if fail_count > 0:
        sys.exit(1)
    else:
        print("\nAll files parsed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    test_parse_files()
