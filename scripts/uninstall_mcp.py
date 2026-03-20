"""
AIDEFEND MCP - Uninstaller

This script removes AIDEFEND configuration from Claude Desktop while
preserving all other MCP servers and settings.

Usage:
    python scripts/uninstall_mcp.py              # Interactive mode
    python scripts/uninstall_mcp.py --auto       # Automatic mode (no prompts)
    python scripts/uninstall_mcp.py --help       # Show help
"""

import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Fix Windows console encoding for Unicode characters (emojis)
if sys.platform == "win32":
    try:
        # Try to set UTF-8 encoding for Windows console
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        # If reconfigure fails, continue with default encoding
        # Emojis may not display correctly, but script will still work
        pass


def print_banner(title: str, width: int = 68):
    """Print a formatted banner"""
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)
    print()


def print_separator(width: int = 68):
    """Print a separator line"""
    print()
    print("-" * width)
    print()


def get_claude_config_path() -> Path:
    """Get Claude Desktop config file path for current OS"""
    if sys.platform == "win32":
        import os
        appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        return appdata / 'Claude' / 'claude_desktop_config.json'
    elif sys.platform == "darwin":
        return Path.home() / 'Library' / 'Application Support' / 'Claude' / 'claude_desktop_config.json'
    else:
        return Path.home() / '.config' / 'Claude' / 'claude_desktop_config.json'


def backup_config(config_path: Path, verbose: bool = True) -> Optional[Path]:
    """Backup existing config file"""
    if not config_path.exists():
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = config_path.with_suffix(f'.json.backup.{timestamp}')

    shutil.copy2(config_path, backup_path)

    if verbose:
        print(f"✅ Backup created: {backup_path.name}")

    return backup_path


def remove_aidefend(
    config_path: Path,
    auto: bool = False,
    verbose: bool = True
) -> bool:
    """
    Remove AIDEFEND from Claude Desktop config.

    Args:
        config_path: Path to claude_desktop_config.json
        auto: Skip confirmation prompts
        verbose: Print detailed information

    Returns:
        True if removal was successful, False if not found
    """
    # Check if config file exists
    if not config_path.exists():
        if verbose:
            print()
            print("ℹ️  No Claude Desktop config file found")
            print(f"   Expected location: {config_path}")
            print()
            print("AIDEFEND is not installed. Nothing to uninstall.")
        return False

    # Read config
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        if not isinstance(config, dict):
            if verbose:
                print("❌ Error: Invalid config format")
            return False

    except json.JSONDecodeError as e:
        print()
        print("❌ Error: Config file has invalid JSON format")
        print(f"   Location: Line {e.lineno}, Column {e.colno}")
        print(f"   Message: {e.msg}")
        print()
        print("Cannot uninstall. Please fix the config file manually.")
        return False

    except Exception as e:
        print(f"❌ Error reading config file: {e}")
        return False

    # Check if AIDEFEND is installed
    if 'mcpServers' not in config or 'aidefend' not in config['mcpServers']:
        if verbose:
            print()
            print("ℹ️  AIDEFEND is not installed in Claude Desktop")
            print()
            print("Nothing to uninstall.")
        return False

    # Show current config
    if verbose:
        print()
        print("📋 Current configuration:")
        print()

        aidefend_config = config['mcpServers']['aidefend']
        print(f"   AIDEFEND location: {aidefend_config.get('cwd', 'unknown')}")

        other_servers = [
            name for name in config['mcpServers'].keys()
            if name != 'aidefend'
        ]

        if other_servers:
            print(f"   Other MCP tools: {len(other_servers)}")
            for name in other_servers:
                print(f"     • {name}")
        else:
            print("   Other MCP tools: None")

        print()

    # Confirmation (unless auto mode)
    if not auto:
        print_separator()
        response = input("Remove AIDEFEND configuration? (y/n): ")
        if response.lower() != 'y':
            print()
            print("❌ Uninstall cancelled")
            return False
        print()

    # Create backup
    backup_path = backup_config(config_path, verbose=verbose)

    # Remove AIDEFEND
    del config['mcpServers']['aidefend']

    # If mcpServers is now empty, optionally remove it
    # (keep it for consistency, even if empty)

    # Write updated config
    try:
        # Write to temp file first (atomic operation)
        temp_path = config_path.with_suffix('.json.tmp')

        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # Verify
        with open(temp_path, 'r', encoding='utf-8') as f:
            test_load = json.load(f)

        # Atomic rename
        temp_path.replace(config_path)

        if verbose:
            print("✅ AIDEFEND removed from Claude Desktop")

            other_servers = [
                name for name in config.get('mcpServers', {}).keys()
            ]
            if other_servers:
                print(f"✅ {len(other_servers)} other tool(s) preserved")

        return True

    except Exception as e:
        print()
        print(f"❌ Error writing configuration: {e}")
        print()
        if backup_path:
            print(f"Your original config was backed up: {backup_path.name}")
        return False


def main():
    """Main uninstall flow"""
    parser = argparse.ArgumentParser(
        description="AIDEFEND MCP - Uninstaller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/uninstall_mcp.py              # Interactive mode
  python scripts/uninstall_mcp.py --auto       # Automatic mode (no prompts)
        """
    )

    parser.add_argument(
        '--auto',
        action='store_true',
        help='Automatic mode: no confirmation prompts'
    )

    args = parser.parse_args()

    # Banner
    print_banner("AIDEFEND MCP - Uninstaller")

    # Detect config path
    print("🔍 Checking installation...")
    print()

    config_path = get_claude_config_path()
    print(f"   Claude config: {config_path}")
    print()

    # Remove AIDEFEND
    success = remove_aidefend(
        config_path,
        auto=args.auto,
        verbose=True
    )

    if not success:
        sys.exit(1)

    # Success message
    print_banner("✅ Uninstall Complete")

    print("📌 Next steps:")
    print()
    print("  1. Restart Claude Desktop to apply changes")
    print()
    print("  2. Your local AIDEFEND files remain untouched:")
    print(f"     {Path(__file__).parent.parent}")
    print()
    print("  3. To reinstall, run:")
    print("     python scripts/setup_mcp.py")
    print()

    print_separator()
    print()
    print("💡 If you want to completely remove AIDEFEND:")
    print("   - Delete the project folder manually")
    print()
    print_separator()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print()
        print("❌ Uninstall cancelled by user")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
