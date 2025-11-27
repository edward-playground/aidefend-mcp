"""
AIDEFEND MCP - One-Click Installation

This script provides a complete, automated installation of AIDEFEND MCP service:
1. Checks system requirements (Python 3.9+, Node.js 18+)
2. Installs Python dependencies
3. Installs Node.js dependencies
4. Configures Claude Desktop (MCP mode) with safe config merging

Usage:
    python scripts/install.py              # Interactive installation (recommended)
    python scripts/install.py --auto       # Fully automated (no prompts)
    python scripts/install.py --no-mcp     # Skip MCP configuration
    python scripts/install.py --dry-run    # Preview without making changes
    python scripts/install.py --check      # Check prerequisites only (no install)
    python scripts/install.py --help       # Show this help
"""

import sys
import json
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

# Fix Windows console encoding for Unicode characters (emojis)
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def print_banner(title: str, width: int = 70):
    """Print a formatted banner"""
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)
    print()


def print_step(step: int, total: int, description: str):
    """Print a step indicator"""
    print(f"\n[Step {step}/{total}] {description}")
    print("-" * 70)


def check_python_version() -> Tuple[bool, str]:
    """
    Check if Python version meets requirements (3.9+).

    Returns:
        (is_valid, version_string)
    """
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    if version.major < 3 or (version.major == 3 and version.minor < 9):
        return False, version_str

    return True, version_str


def check_node_version() -> Tuple[bool, str]:
    """
    Check if Node.js is installed and version meets requirements (18+).

    Returns:
        (is_valid, version_string or error_message)
    """
    try:
        result = subprocess.run(
            ['node', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            return False, "Node.js command failed"

        version_str = result.stdout.strip()
        # Parse version (e.g., "v18.17.0" -> 18)
        if version_str.startswith('v'):
            major_version = int(version_str[1:].split('.')[0])
            if major_version >= 18:
                return True, version_str
            else:
                return False, f"{version_str} (requires v18+)"

        return False, version_str

    except FileNotFoundError:
        return False, "Node.js not found"
    except Exception as e:
        return False, str(e)


def check_claude_desktop_installed() -> Tuple[bool, str]:
    """
    Check if Claude Desktop is likely installed.

    Returns:
        (is_installed, installation_path or error_message)
    """
    if sys.platform == "win32":
        import os
        # Check common installation locations
        locations = [
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Claude' / 'Claude.exe',
            Path(os.environ.get('APPDATA', '')) / 'Claude' / 'Claude.exe',
        ]
        for loc in locations:
            if loc.exists():
                return True, str(loc)
        return False, "Not found in standard locations"

    elif sys.platform == "darwin":
        claude_app = Path('/Applications/Claude.app')
        if claude_app.exists():
            return True, str(claude_app)
        return False, "Not found in /Applications"

    else:  # Linux
        # On Linux, check if config directory exists (less reliable)
        config_path = get_claude_config_path()
        if config_path.parent.exists():
            return True, "Config directory exists"
        return False, "Config directory not found"


def check_internet_connectivity() -> bool:
    """
    Check if internet connection is available.

    Returns:
        True if internet is available
    """
    try:
        import socket
        # Try to connect to Google DNS
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def install_python_dependencies(verbose: bool = True) -> bool:
    """
    Install Python dependencies from requirements.txt.

    Returns:
        True if successful
    """
    requirements_file = Path(__file__).parent.parent / 'requirements.txt'

    if not requirements_file.exists():
        print(f"❌ Requirements file not found: {requirements_file}")
        return False

    if verbose:
        print("Installing Python dependencies...")
        print(f"   Using: {requirements_file}")
        print("   This may take 2-5 minutes...")

    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-r', str(requirements_file)],
            capture_output=not verbose,
            text=True,
            timeout=600  # 10 minutes timeout
        )

        if result.returncode == 0:
            if verbose:
                print("✅ Python dependencies installed successfully")
            return True
        else:
            print(f"❌ pip install failed with code {result.returncode}")
            if result.stderr:
                print(f"   Error: {result.stderr}")

            # Provide helpful hints
            print("\n💡 Troubleshooting hints:")
            if not check_internet_connectivity():
                print("   • No internet connection detected")
                print("   • Check your network connection")
                print("   • If behind firewall/proxy, use: pip install -r requirements.txt --proxy YOUR_PROXY")
            else:
                print("   • Try upgrading pip: python -m pip install --upgrade pip")
                print("   • For China users: pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple")
                print("   • Check logs above for specific package errors")

            return False

    except subprocess.TimeoutExpired:
        print("❌ pip install timed out (10 minutes)")
        print("💡 This usually means slow network or large packages")
        print("   Try running manually: python -m pip install -r requirements.txt")
        return False
    except Exception as e:
        print(f"❌ Failed to install Python dependencies: {e}")
        return False


def install_node_dependencies(verbose: bool = True) -> bool:
    """
    Install Node.js dependencies using npm.

    Returns:
        True if successful
    """
    project_root = Path(__file__).parent.parent
    package_json = project_root / 'package.json'

    if not package_json.exists():
        print(f"❌ package.json not found: {package_json}")
        return False

    if verbose:
        print("Installing Node.js dependencies...")
        print(f"   Using: {package_json}")
        print("   This may take 1-2 minutes...")

    try:
        result = subprocess.run(
            ['npm', 'install'],
            cwd=str(project_root),
            capture_output=not verbose,
            text=True,
            timeout=300  # 5 minutes timeout
        )

        if result.returncode == 0:
            if verbose:
                print("✅ Node.js dependencies installed successfully")
            return True
        else:
            print(f"❌ npm install failed with code {result.returncode}")
            if result.stderr:
                print(f"   Error: {result.stderr}")

            # Provide helpful hints
            print("\n💡 Troubleshooting hints:")
            if not check_internet_connectivity():
                print("   • No internet connection detected")
                print("   • Check your network connection")
            else:
                print("   • Try: npm install --verbose (for detailed logs)")
                print("   • For China users: npm install --registry=https://registry.npmmirror.com")
                print("   • Try clearing cache: npm cache clean --force")

            return False

    except subprocess.TimeoutExpired:
        print("❌ npm install timed out (5 minutes)")
        print("💡 Try running manually: npm install")
        return False
    except FileNotFoundError:
        print("❌ npm command not found. Please install Node.js first.")
        print("💡 Download from: https://nodejs.org/")
        return False
    except Exception as e:
        print(f"❌ Failed to install Node.js dependencies: {e}")
        return False


def get_claude_config_path() -> Path:
    """Get Claude Desktop config file path for current OS."""
    if sys.platform == "win32":
        import os
        appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        return appdata / 'Claude' / 'claude_desktop_config.json'
    elif sys.platform == "darwin":
        return Path.home() / 'Library' / 'Application Support' / 'Claude' / 'claude_desktop_config.json'
    else:
        return Path.home() / '.config' / 'Claude' / 'claude_desktop_config.json'


def get_python_path() -> str:
    """Get current Python executable path (JSON compatible)."""
    return str(Path(sys.executable)).replace('\\', '/')


def get_mcp_path() -> str:
    """Get AIDEFEND MCP project directory path (JSON compatible)."""
    project_root = Path(__file__).resolve().parent.parent
    return str(project_root).replace('\\', '/')


def validate_paths(python_path: str, mcp_path: str) -> bool:
    """Validate that required paths exist."""
    issues = []

    py_path = Path(python_path)
    if not py_path.exists():
        issues.append(f"Python executable not found: {python_path}")

    mcp_dir = Path(mcp_path)
    if not mcp_dir.exists():
        issues.append(f"MCP directory not found: {mcp_path}")

    main_file = mcp_dir / '__main__.py'
    if not main_file.exists():
        issues.append(f"__main__.py not found in: {mcp_path}")

    if issues:
        print("\n❌ Path validation failed:")
        for issue in issues:
            print(f"   • {issue}")
        return False

    return True


def backup_config(config_path: Path) -> Optional[Path]:
    """Create backup of existing config file."""
    if not config_path.exists():
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = config_path.with_suffix(f'.json.backup.{timestamp}')
    shutil.copy2(config_path, backup_path)
    print(f"✅ Backup created: {backup_path.name}")
    return backup_path


def merge_config(config_path: Path, aidefend_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely merge AIDEFEND config into existing Claude Desktop config.
    Preserves all existing MCP servers and settings.
    """
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)
            if not isinstance(existing_config, dict):
                existing_config = {}
        except json.JSONDecodeError:
            print("⚠️  Existing config has invalid JSON, creating new config")
            existing_config = {}
    else:
        existing_config = {}

    # Ensure mcpServers exists
    if 'mcpServers' not in existing_config:
        existing_config['mcpServers'] = {}

    # Get list of other servers before modification
    other_servers = [
        name for name in existing_config['mcpServers'].keys()
        if name != 'aidefend'
    ]

    # Add/update AIDEFEND
    existing_config['mcpServers']['aidefend'] = aidefend_config

    # Show preserved servers
    if other_servers:
        print(f"✅ Preserving {len(other_servers)} existing MCP tool(s):")
        for server_name in other_servers:
            print(f"   • {server_name}")

    return existing_config


def write_config(config_path: Path, config: Dict[str, Any], dry_run: bool = False) -> bool:
    """Write config to file (atomic operation)."""
    if dry_run:
        print("\n[DRY RUN] Would write configuration:")
        print(json.dumps(config, indent=2))
        return True

    # Create parent directory if needed
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write: write to temp file, then rename
    temp_path = config_path.with_suffix('.json.tmp')
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        temp_path.replace(config_path)
        print(f"✅ Configuration saved to: {config_path}")
        return True

    except Exception as e:
        print(f"❌ Failed to write config: {e}")
        if temp_path.exists():
            temp_path.unlink()
        return False


def configure_mcp(auto: bool = False, dry_run: bool = False) -> bool:
    """
    Configure Claude Desktop for MCP mode.

    Returns:
        True if successful
    """
    print("\nConfiguring Claude Desktop for MCP mode...")

    # Check if Claude Desktop is installed (warning only, not blocking)
    claude_installed, claude_info = check_claude_desktop_installed()
    if not claude_installed:
        print(f"\n⚠️  Warning: Claude Desktop may not be installed")
        print(f"   {claude_info}")
        print(f"   Download from: https://claude.ai/download")
        print(f"   Configuration will still be created for when you install it.\n")

    # Get paths
    config_path = get_claude_config_path()
    python_path = get_python_path()
    mcp_path = get_mcp_path()

    print(f"   Config file: {config_path}")
    print(f"   Python: {python_path}")
    print(f"   Project: {mcp_path}")

    # Validate paths
    if not validate_paths(python_path, mcp_path):
        return False

    # Create AIDEFEND config
    aidefend_config = {
        "command": python_path,
        "args": [f"{mcp_path}/__main__.py", "--mcp"],
        "cwd": mcp_path
    }

    # Confirm if not auto mode
    if not auto and not dry_run:
        print("\n⚠️  This will modify your Claude Desktop configuration.")
        response = input("   Continue? [Y/n]: ").strip().lower()
        if response and response != 'y':
            print("❌ MCP configuration cancelled")
            return False

    # Backup existing config
    if not dry_run:
        backup_config(config_path)

    # Merge configurations
    merged_config = merge_config(config_path, aidefend_config)

    # Write config
    if not write_config(config_path, merged_config, dry_run):
        return False

    if not dry_run:
        print("\n✅ MCP configuration completed successfully!")
        print("\n⚠️  IMPORTANT: Restart Claude Desktop to apply changes")
        print("   1. Completely close Claude Desktop")
        print("   2. Reopen Claude Desktop")
        print("   3. Look for 'aidefend' in MCP tools list (🔌 icon)")

    return True


def main():
    """Main installation workflow."""
    parser = argparse.ArgumentParser(
        description="AIDEFEND MCP One-Click Installation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--auto', action='store_true',
                       help='Fully automated mode (no prompts)')
    parser.add_argument('--no-mcp', action='store_true',
                       help='Skip MCP configuration')
    parser.add_argument('--dry-run', action='store_true',
                       help='Preview without making changes')
    parser.add_argument('--check', action='store_true',
                       help='Check prerequisites only (no installation)')

    args = parser.parse_args()

    # Check mode - only verify prerequisites
    if args.check:
        print_banner("AIDEFEND MCP - Prerequisites Check")

        all_ok = True

        # Check Python
        print("[1/4] Checking Python version...")
        py_valid, py_version = check_python_version()
        if py_valid:
            print(f"   ✅ Python {py_version} (OK)")
        else:
            print(f"   ❌ Python {py_version} - Need 3.9+")
            print(f"      Download: https://www.python.org/downloads/")
            all_ok = False

        # Check Node.js
        print("\n[2/4] Checking Node.js version...")
        node_valid, node_version = check_node_version()
        if node_valid:
            print(f"   ✅ Node.js {node_version} (OK)")
        else:
            print(f"   ❌ {node_version}")
            print(f"      Download: https://nodejs.org/")
            all_ok = False

        # Check Claude Desktop
        print("\n[3/4] Checking Claude Desktop...")
        claude_installed, claude_info = check_claude_desktop_installed()
        if claude_installed:
            print(f"   ✅ Found: {claude_info}")
        else:
            print(f"   ⚠️  {claude_info}")
            print(f"      Download: https://claude.ai/download")
            print(f"      (Not required for REST API mode)")

        # Check Internet
        print("\n[4/4] Checking internet connectivity...")
        if check_internet_connectivity():
            print(f"   ✅ Internet connection available")
        else:
            print(f"   ⚠️  No internet detected")
            print(f"      Required for downloading dependencies")

        print("\n" + "=" * 70)
        if all_ok:
            print("✅ All prerequisites met! Ready to install.")
            print("\nRun: python scripts/install.py")
        else:
            print("❌ Some prerequisites missing. Please install them first.")
        print("=" * 70)

        return 0 if all_ok else 1

    print_banner("AIDEFEND MCP - One-Click Installation")

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")

    # Step 1: Check Python version
    print_step(1, 5, "Checking Python version")
    py_valid, py_version = check_python_version()
    print(f"   Python version: {py_version}")

    if not py_valid:
        print(f"❌ Python 3.9+ required, found {py_version}")
        print("   Please upgrade Python: https://www.python.org/downloads/")
        return 1
    print("✅ Python version OK")

    # Step 2: Check Node.js
    print_step(2, 5, "Checking Node.js version")
    node_valid, node_version = check_node_version()
    print(f"   Node.js version: {node_version}")

    if not node_valid:
        print(f"❌ Node.js 18+ required")
        print("   Please install Node.js: https://nodejs.org/")
        return 1
    print("✅ Node.js version OK")

    # Step 3: Install Python dependencies
    if not args.dry_run:
        print_step(3, 5, "Installing Python dependencies")
        if not install_python_dependencies(verbose=True):
            print("❌ Failed to install Python dependencies")
            return 1
    else:
        print_step(3, 5, "Installing Python dependencies [DRY RUN]")
        print("   Would run: pip install -r requirements.txt")

    # Step 4: Install Node.js dependencies
    if not args.dry_run:
        print_step(4, 5, "Installing Node.js dependencies")
        if not install_node_dependencies(verbose=True):
            print("❌ Failed to install Node.js dependencies")
            return 1
    else:
        print_step(4, 5, "Installing Node.js dependencies [DRY RUN]")
        print("   Would run: npm install")

    # Step 5: Configure MCP (optional)
    if not args.no_mcp:
        print_step(5, 5, "Configuring Claude Desktop (MCP mode)")
        if not configure_mcp(auto=args.auto, dry_run=args.dry_run):
            print("⚠️  MCP configuration failed, but dependencies are installed")
            print("   You can run MCP setup later: python scripts/install.py")
            return 1
    else:
        print_step(5, 5, "Skipping MCP configuration [--no-mcp]")

    # Success
    print_banner("✅ Installation Complete!")

    if not args.dry_run:
        if not args.no_mcp:
            print("Next steps:")
            print("  1. Restart Claude Desktop (close completely and reopen)")
            print("  2. Look for 'aidefend' in MCP tools (🔌 icon)")
            print("  3. Try: 'Search AIDEFEND for prompt injection defenses'")
        else:
            print("Dependencies installed successfully!")
            print("\nTo configure Claude Desktop later:")
            print("  python scripts/install.py")
            print("\nTo start REST API mode:")
            print("  python __main__.py")
    else:
        print("This was a dry run. No changes were made.")
        print("Run without --dry-run to perform actual installation.")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n❌ Installation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
