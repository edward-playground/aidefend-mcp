"""
AIDEFEND MCP - Automated Claude Desktop Setup

This script automatically configures Claude Desktop to use AIDEFEND MCP server.
It safely merges the configuration while preserving all existing MCP tools.

Usage:
    python scripts/setup_mcp.py              # Interactive mode (recommended)
    python scripts/setup_mcp.py --auto       # Automatic mode (no prompts)
    python scripts/setup_mcp.py --dry-run    # Preview without writing
    python scripts/setup_mcp.py --help       # Show help
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
    """
    Get Claude Desktop config file path for current OS.

    Returns:
        Path to claude_desktop_config.json
    """
    if sys.platform == "win32":
        # Windows: %APPDATA%\Claude\claude_desktop_config.json
        import os
        appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        return appdata / 'Claude' / 'claude_desktop_config.json'
    elif sys.platform == "darwin":
        # macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
        return Path.home() / 'Library' / 'Application Support' / 'Claude' / 'claude_desktop_config.json'
    else:
        # Linux: ~/.config/Claude/claude_desktop_config.json
        return Path.home() / '.config' / 'Claude' / 'claude_desktop_config.json'


def get_python_path() -> str:
    """
    Get current Python executable path.

    Returns:
        Python path with forward slashes (JSON compatible)
    """
    python_path = sys.executable
    # Convert to forward slashes for JSON (Windows compatibility)
    return str(Path(python_path)).replace('\\', '/')


def get_mcp_path() -> str:
    """
    Get AIDEFEND MCP project directory path.

    Returns:
        Project path with forward slashes (JSON compatible)
    """
    # This script is in scripts/ subdirectory
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent

    # Convert to forward slashes for JSON
    return str(project_root).replace('\\', '/')


def validate_paths(python_path: str, mcp_path: str) -> bool:
    """
    Validate that required paths exist and are correct.

    Args:
        python_path: Python executable path
        mcp_path: MCP project directory path

    Returns:
        True if all paths are valid
    """
    issues = []

    # Check Python executable
    py_path = Path(python_path)
    if not py_path.exists():
        issues.append(f"Python executable not found: {python_path}")
    elif not py_path.is_file():
        issues.append(f"Python path is not a file: {python_path}")

    # Check MCP directory
    mcp_dir = Path(mcp_path)
    if not mcp_dir.exists():
        issues.append(f"MCP directory not found: {mcp_path}")
    elif not mcp_dir.is_dir():
        issues.append(f"MCP path is not a directory: {mcp_path}")

    # Check __main__.py exists
    main_file = mcp_dir / '__main__.py'
    if not main_file.exists():
        issues.append(f"__main__.py not found in: {mcp_path}")

    if issues:
        print()
        print("❌ Path validation failed:")
        for issue in issues:
            print(f"   • {issue}")
        print()
        return False

    return True


def backup_config(config_path: Path, verbose: bool = True) -> Optional[Path]:
    """
    Backup existing config file.

    Args:
        config_path: Config file to backup
        verbose: Whether to print backup info

    Returns:
        Backup file path, or None if no backup needed
    """
    if not config_path.exists():
        return None

    # Create backup filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = config_path.with_suffix(f'.json.backup.{timestamp}')

    # Copy file
    shutil.copy2(config_path, backup_path)

    if verbose:
        print(f"✅ Backup created: {backup_path.name}")

    return backup_path


def merge_config(
    config_path: Path,
    aidefend_config: Dict[str, Any],
    force: bool = False,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Safely merge AIDEFEND config into existing Claude Desktop config.

    This function:
    1. Reads existing config (if exists)
    2. Preserves ALL existing MCP servers
    3. Preserves ALL top-level settings (theme, shortcuts, etc.)
    4. Only adds/updates mcpServers.aidefend

    Args:
        config_path: Path to claude_desktop_config.json
        aidefend_config: AIDEFEND MCP server configuration
        force: Skip confirmation prompts
        verbose: Print merge information

    Returns:
        Merged configuration dictionary
    """
    # Read existing config
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)

            if not isinstance(existing_config, dict):
                if verbose:
                    print("⚠️  Warning: Invalid config format, creating new config")
                existing_config = {}

        except json.JSONDecodeError as e:
            print()
            print("❌ Error: Config file has invalid JSON format")
            print(f"   Location: Line {e.lineno}, Column {e.colno}")
            print(f"   Message: {e.msg}")
            print()
            print("Please fix the config file manually or delete it and retry.")
            sys.exit(1)

        except Exception as e:
            print(f"❌ Error reading config file: {e}")
            sys.exit(1)
    else:
        existing_config = {}

    # Ensure mcpServers exists
    if 'mcpServers' not in existing_config:
        existing_config['mcpServers'] = {}

    # Check for existing AIDEFEND config
    has_existing = 'aidefend' in existing_config['mcpServers']

    if has_existing and verbose:
        old_config = existing_config['mcpServers']['aidefend']
        old_path = old_config.get('cwd', '(unknown)')
        new_path = aidefend_config['cwd']

        if old_path != new_path:
            print()
            print("⚠️  Detected existing AIDEFEND configuration:")
            print(f"    Old path: {old_path}")
            print(f"    New path: {new_path}")
            print()

            if not force:
                response = input("Update to new path? (y/n): ")
                if response.lower() != 'y':
                    print("❌ Installation cancelled")
                    sys.exit(0)

    # Get list of other servers (before modification)
    other_servers = [
        name for name in existing_config['mcpServers'].keys()
        if name != 'aidefend'
    ]

    # Add/update AIDEFEND (KEY: Only modify this one entry)
    existing_config['mcpServers']['aidefend'] = aidefend_config

    # Show preserved servers
    if other_servers and verbose:
        print()
        print(f"✅ Preserving {len(other_servers)} existing MCP tool(s):")
        for server_name in other_servers:
            print(f"   • {server_name}")
        print()

    return existing_config


def validate_merged_config(config: Dict[str, Any]) -> bool:
    """
    Validate merged configuration.

    Args:
        config: Configuration to validate

    Returns:
        True if valid
    """
    # Check basic structure
    if 'mcpServers' not in config:
        print("❌ Error: Missing mcpServers")
        return False

    if not isinstance(config['mcpServers'], dict):
        print("❌ Error: mcpServers is not a dictionary")
        return False

    # Check AIDEFEND config
    if 'aidefend' not in config['mcpServers']:
        print("❌ Error: Missing aidefend configuration")
        return False

    aidefend = config['mcpServers']['aidefend']

    # Check required fields
    required_fields = ['command', 'args', 'cwd']
    for field in required_fields:
        if field not in aidefend:
            print(f"❌ Error: aidefend missing required field: {field}")
            return False

    # Validate paths exist
    python_path = Path(aidefend['command'])
    if not python_path.exists():
        print(f"⚠️  Warning: Python path does not exist: {python_path}")
        return False

    mcp_path = Path(aidefend['cwd'])
    if not mcp_path.exists():
        print(f"⚠️  Warning: MCP path does not exist: {mcp_path}")
        return False

    return True


def write_config(config_path: Path, config: Dict[str, Any]) -> None:
    """
    Write configuration to file atomically.

    Uses atomic write (write to temp, then rename) to avoid corruption.

    Args:
        config_path: Destination config file
        config: Configuration to write
    """
    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary file first
    temp_path = config_path.with_suffix('.json.tmp')

    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # Verify written file is valid JSON
        with open(temp_path, 'r', encoding='utf-8') as f:
            test_load = json.load(f)

        # Verify content matches
        assert test_load == config, "Verification failed: written content doesn't match"

        # Atomic rename (replace existing file)
        temp_path.replace(config_path)

    except Exception as e:
        # Clean up temp file if it exists
        if temp_path.exists():
            temp_path.unlink()
        raise e


def show_preview(config: Dict[str, Any], other_servers: list):
    """Show preview of configuration to be written"""
    print_separator()
    print()
    print("📝 Configuration to be written:")
    print()
    print("{")
    print('  "mcpServers": {')

    # Show other servers (preserved)
    for server_name in other_servers:
        print(f'    "{server_name}": {{ ... }},     ← Preserved')

    # Show AIDEFEND (new/updated)
    aidefend = config['mcpServers']['aidefend']
    status = "Updated" if other_servers else "New"
    print(f'    "aidefend": {{              ← {status}')
    print(f'      "command": "{aidefend["command"]}",')
    print(f'      "args": [')
    for arg in aidefend['args']:
        print(f'        "{arg}",')
    # Remove trailing comma from last arg
    print(f'      ],')
    print(f'      "cwd": "{aidefend["cwd"]}"')
    print(f'    }}')

    print('  }')
    print('}')
    print()


def main():
    """Main installation flow"""
    parser = argparse.ArgumentParser(
        description="AIDEFEND MCP - Automated Claude Desktop Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/setup_mcp.py              # Interactive mode (recommended)
  python scripts/setup_mcp.py --auto       # Automatic mode (no prompts)
  python scripts/setup_mcp.py --dry-run    # Preview without writing
  python scripts/setup_mcp.py --force      # Skip all confirmations
        """
    )

    parser.add_argument(
        '--auto',
        action='store_true',
        help='Automatic mode: no confirmation prompts'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview configuration without writing'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Force overwrite without confirmation'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed output'
    )

    args = parser.parse_args()

    # Banner
    if args.dry_run:
        print_banner("AIDEFEND MCP - Dry Run Mode (Preview Only)")
    elif args.auto:
        print_banner("AIDEFEND MCP - Automatic Setup Mode")
    else:
        print_banner("AIDEFEND MCP - Claude Desktop Setup Tool")

    # Detect paths
    print("🔍 Detecting system paths...")
    print()

    python_path = get_python_path()
    mcp_path = get_mcp_path()
    config_path = get_claude_config_path()

    print(f"✓ Python path: {python_path}")
    print(f"✓ MCP project path: {mcp_path}")
    print(f"✓ Claude config: {config_path}")

    # Validate paths
    if not validate_paths(python_path, mcp_path):
        print("Please fix the path issues and retry.")
        sys.exit(1)

    # Check Claude Desktop installed
    if not config_path.parent.exists():
        print_separator()
        print()
        print("❌ Error: Claude Desktop not detected")
        print()
        print(f"Expected config directory: {config_path.parent}")
        print()
        print("Possible reasons:")
        print("  1. Claude Desktop is not installed")
        print("  2. Claude Desktop version is too old (MCP not supported)")
        print("  3. Non-standard installation location")
        print()
        print("Solution:")
        print("  1. Download and install Claude Desktop:")
        print("     https://claude.ai/download")
        print()
        print("  2. Run Claude Desktop at least once (creates config file)")
        print()
        print("  3. Retry this script")
        print()
        sys.exit(1)

    # Build AIDEFEND configuration
    aidefend_config = {
        "command": python_path,
        "args": [
            f"{mcp_path}/__main__.py",
            "--mcp"
        ],
        "cwd": mcp_path
    }

    # Merge configuration
    merged_config = merge_config(
        config_path,
        aidefend_config,
        force=args.auto or args.force,
        verbose=not args.auto
    )

    # Get other servers for preview
    other_servers = [
        name for name in merged_config['mcpServers'].keys()
        if name != 'aidefend'
    ]

    # Show preview
    if not args.auto:
        show_preview(merged_config, other_servers)

    # Validate
    if not validate_merged_config(merged_config):
        print("Configuration validation failed.")
        sys.exit(1)

    # Dry run mode - stop here
    if args.dry_run:
        print_separator()
        print()
        print("ℹ️  This is dry-run mode. No changes were made.")
        print()
        print("To actually install, run:")
        print("  python scripts/setup_mcp.py")
        print()
        return

    # Confirmation (unless auto/force mode)
    if not args.auto and not args.force:
        print_separator()
        print()
        if config_path.exists():
            print("⚠️  Existing config will be backed up before modification")
            print()

        response = input("Write configuration? (y/n): ")
        if response.lower() != 'y':
            print()
            print("❌ Installation cancelled")
            sys.exit(0)

    print()

    # Backup existing config
    if config_path.exists():
        backup_path = backup_config(config_path, verbose=not args.auto)

    # Write configuration
    try:
        write_config(config_path, merged_config)
        print("✅ Configuration written successfully!")

        if other_servers:
            print(f"✅ All {len(other_servers)} existing tool(s) preserved")

    except Exception as e:
        print()
        print(f"❌ Error writing configuration: {e}")
        print()
        print("Your original config was backed up. Check:")
        print(f"  {backup_path if 'backup_path' in locals() else 'backup file'}")
        sys.exit(1)

    # Success message
    print_banner("🎉 Installation Complete!")

    print("📌 Next steps:")
    print()
    print("  1. Completely quit Claude Desktop:")

    if sys.platform == "win32":
        print("     - Right-click Claude in taskbar → Exit")
    elif sys.platform == "darwin":
        print("     - Press Cmd+Q to quit (not just close window)")
    else:
        print("     - Fully quit the application")

    print()
    print("  2. Restart Claude Desktop")
    print()
    print("  3. Verify AIDEFEND tools are loaded")
    print()
    print("  4. Start using AIDEFEND!")
    print("     Try asking: \"What techniques defend against prompt injection?\"")
    print()

    print_separator()
    print()
    print("💡 Useful commands:")
    print("  • Uninstall: python scripts/uninstall_mcp.py")
    print("  • Auto mode: python scripts/setup_mcp.py --auto")
    print("  • Dry run:   python scripts/setup_mcp.py --dry-run")
    print("  • Help:      python scripts/setup_mcp.py --help")
    print()
    print_separator()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print()
        print("❌ Installation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
