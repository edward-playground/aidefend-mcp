"""
AIDEFEND MCP - One-Click Installation

This script provides a complete, automated installation of AIDEFEND MCP service:
1. Checks system requirements (Python 3.9+, Node.js 18+)
2. Installs Python dependencies
3. Installs Node.js dependencies
4. Configures MCP clients (Claude Desktop and/or Claude Code) with safe config merging

Usage:
    python scripts/install.py                      # Interactive installation (Claude Desktop)
    python scripts/install.py --client desktop     # Configure Claude Desktop only
    python scripts/install.py --client code        # Configure Claude Code (VSCode) only
    python scripts/install.py --client both        # Configure both clients
    python scripts/install.py --auto               # Fully automated (no prompts)
    python scripts/install.py --no-mcp             # Skip MCP configuration
    python scripts/install.py --dry-run            # Preview without making changes
    python scripts/install.py --check              # Check prerequisites only (no install)
    python scripts/install.py --help               # Show this help
"""

import sys
import os
import json
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

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
    Check if Node.js AND npm are installed and versions meet requirements (18+).

    Returns:
        (is_valid, version_string or error_message)
    """
    try:
        # Check Node.js
        node_result = subprocess.run(
            ['node', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if node_result.returncode != 0:
            return False, "Node.js command failed"

        node_version = node_result.stdout.strip()

        # Parse version (e.g., "v18.17.0" -> 18)
        if node_version.startswith('v'):
            major_version = int(node_version[1:].split('.')[0])
            if major_version < 18:
                return False, f"{node_version} (requires v18+)"
        else:
            return False, node_version

        # Check npm (Windows uses npm.cmd, Unix uses npm)
        npm_cmd = 'npm.cmd' if sys.platform == 'win32' else 'npm'

        try:
            npm_result = subprocess.run(
                [npm_cmd, '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if npm_result.returncode != 0:
                return False, f"npm command failed (Node.js {node_version} found but npm not working)"

            npm_version = npm_result.stdout.strip()

            # Both node and npm are OK
            return True, f"{node_version}, npm {npm_version}"

        except FileNotFoundError:
            return False, f"npm not found (Node.js {node_version} found but npm is missing)"

    except FileNotFoundError:
        return False, "Node.js not found"
    except Exception as e:
        return False, str(e)


def download_with_progress(url: str, target_path: Path, description: str = "Downloading") -> bool:
    """
    Download file with real-time progress bar.

    Args:
        url: URL to download from
        target_path: Path to save file
        description: Description to show in progress bar

    Returns:
        True if successful, False otherwise
    """
    import urllib.request

    try:
        print(f"   📥 {description} from {url}")
        print(f"   💾 Saving to: {target_path}")

        # Get file size
        with urllib.request.urlopen(url) as response:
            total_size = int(response.headers.get('content-length', 0))

            # Download with progress
            downloaded = 0
            block_size = 8192
            last_progress = -1

            with open(target_path, 'wb') as f:
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break

                    downloaded += len(buffer)
                    f.write(buffer)

                    # Show progress every 5%
                    if total_size > 0:
                        progress = int((downloaded / total_size) * 100)
                        if progress >= last_progress + 5 or downloaded == total_size:
                            # Create progress bar
                            bar_width = 30
                            filled = int(bar_width * downloaded / total_size)
                            bar = '=' * filled + '>' + ' ' * (bar_width - filled - 1)
                            mb_downloaded = downloaded / 1_048_576
                            mb_total = total_size / 1_048_576
                            print(f"\r   [{bar}] {progress}% ({mb_downloaded:.1f} MB / {mb_total:.1f} MB)", end='', flush=True)
                            last_progress = progress

            print()  # New line after progress bar
            print(f"   ✅ Downloaded successfully ({total_size / 1_048_576:.1f} MB)")
            return True

    except Exception as e:
        print(f"\n   ❌ Download failed: {e}")
        return False


def get_nodejs_lts_info() -> Tuple[bool, dict]:
    """
    Get latest Node.js LTS version info from nodejs.org API.

    Returns:
        (success, info_dict or error_message)
        info_dict contains: version, lts_name, files
    """
    import urllib.request
    import json

    try:
        # Fetch Node.js version index
        url = "https://nodejs.org/dist/index.json"
        with urllib.request.urlopen(url, timeout=10) as response:
            versions = json.loads(response.read())

        # Find latest LTS version
        for version_info in versions:
            if version_info.get('lts'):  # LTS versions have this field set
                return True, {
                    'version': version_info['version'],  # e.g., "v20.11.0"
                    'lts_name': version_info['lts'],     # e.g., "Iron"
                    'files': version_info.get('files', [])
                }

        return False, "No LTS version found"

    except Exception as e:
        return False, f"Failed to fetch LTS info: {e}"


def download_nodejs_installer(version_info: dict, target_dir: Path = None) -> Tuple[bool, str]:
    """
    Download Node.js installer for current platform.
    Automatically detects architecture (x64, ARM64, x86).

    Args:
        version_info: Version info dict from get_nodejs_lts_info()
        target_dir: Directory to save installer (default: temp directory)

    Returns:
        (success, installer_path or error_message)
    """
    import tempfile
    import platform

    if target_dir is None:
        target_dir = Path(tempfile.gettempdir())

    version = version_info['version']  # e.g., "v20.11.0"
    lts_name = version_info['lts_name']
    
    arch = platform.machine().lower()

    # Determine installer filename based on platform and architecture
    if sys.platform == "win32":
        # Windows: .msi installer
        if arch in ["amd64", "x86_64"]:
            arch_suffix = "x64"
        elif arch in ["arm64", "aarch64"]:
            arch_suffix = "arm64"
        else:
            arch_suffix = "x86"
            
        filename = f"node-{version}-{arch_suffix}.msi"
        installer_path = target_dir / filename
        download_url = f"https://nodejs.org/dist/{version}/{filename}"
        
    elif sys.platform == "darwin":
        # macOS: .pkg installer
        # Note: standard .pkg is universal or x64, but arm64 specific pkg exists for newer versions
        if arch in ["arm64", "aarch64"]:
             # Apple Silicon
            filename = f"node-{version}-arm64.pkg"
        else:
            # Intel Mac
            filename = f"node-{version}.pkg"
            
        installer_path = target_dir / filename
        download_url = f"https://nodejs.org/dist/{version}/{filename}"
        
    else:
        # Linux: suggest package manager instead
        return False, "LINUX_USE_PACKAGE_MANAGER"

    # Download with progress bar
    print(f"\n📦 Downloading Node.js {version} LTS ({lts_name}) for {sys.platform}...")
    success = download_with_progress(download_url, installer_path, f"Node.js {version}")

    if success:
        return True, str(installer_path)
    else:
        return False, "Download failed"


def install_nodejs_auto() -> Tuple[bool, str]:
    """
    Semi-automated Node.js installation with user permission.

    This function:
    1. Checks if Node.js >= 18 is installed
    2. Asks user permission
    3. Downloads latest LTS installer
    4. Runs installer with appropriate UI for platform

    Returns:
        (success, message)
    """
    # Step 1: Check if already installed
    node_valid, node_msg = check_node_version()
    if node_valid:
        return True, f"Already installed: {node_msg}"

    # Step 2: Get latest LTS version info
    print("\n   Checking latest Node.js LTS version...")
    lts_success, lts_info = get_nodejs_lts_info()

    if not lts_success:
        print(f"   ❌ {lts_info}")
        return False, "SHOW_MANUAL"

    version = lts_info['version']
    lts_name = lts_info['lts_name']

    # Step 3: Ask user permission
    print("\n" + "=" * 70)
    print("Node.js Installation Required")
    print("=" * 70)
    print(f"\n⚠️  Node.js 18+ is required for parsing AIDEFEND JavaScript files")
    print(f"   Current status: {node_msg}\n")
    print(f"✅ Automatic installation will:")
    print(f"   • Download Node.js {version} LTS ({lts_name}) from nodejs.org")

    if sys.platform == "win32":
        print(f"   • File size: ~30-35 MB (.msi installer)")
        print(f"   • Install with standard Windows installer UI")
        print(f"   • May show UAC prompt for admin privileges")
    elif sys.platform == "darwin":
        print(f"   • File size: ~30-35 MB (.pkg installer)")
        print(f"   • Install with standard macOS installer UI")
        print(f"   • May require admin password")
    else:  # Linux
        print(f"   • Recommend using your package manager (apt/yum/dnf)")
        print(f"   • Automatic installation not available on Linux")

    print(f"   • Will NOT restart your computer automatically\n")
    print("Options:")
    print("  [1] Automatic installation (recommended)")
    print("  [2] Show manual installation instructions\n")

    while True:
        choice = input("Choose option (1/2): ").strip()
        if choice in ["1", "2"]:
            break
        print("❌ Invalid choice. Please enter 1 or 2.")

    if choice == "2":
        return False, "SHOW_MANUAL"

    # Linux: can't auto-install, show package manager instructions
    if sys.platform not in ["win32", "darwin"]:
        return False, "SHOW_MANUAL"

    # Step 4: Download installer
    download_success, download_result = download_nodejs_installer(lts_info)
    if not download_success:
        print(f"❌ {download_result}")
        print("\nFalling back to manual installation instructions.")
        return False, "SHOW_MANUAL"

    installer_path = download_result

    # Step 5: Run installer
    print(f"\n🔧 Running Node.js installer...")

    if sys.platform == "win32":
        print("   ⚠️  Windows installer will open")
        print("   📝 Follow the installation wizard:")
        print("      1. Accept license agreement")
        print("      2. Keep default installation path")
        print("      3. Ensure 'Add to PATH' is checked")
        print("      4. Click through to complete installation")
        print(f"\n   Starting installer...")

        try:
            # Windows: Run MSI installer using os.startfile (handles file associations)
            os.startfile(str(installer_path))
            print(f"   ✅ Installer launched successfully")
            print(f"\n   ⏳ Please complete the installation wizard")
            print(f"   💡 After installation completes, you may need to:")
            print(f"      • Restart this terminal/command prompt")
            print(f"      • Run this installation script again")

            # Wait for user confirmation
            input("\n   Press Enter after installation completes...")

            # Clean up installer
            try:
                Path(installer_path).unlink()
            except OSError as cleanup_err:
                print(f"   ⚠️  Could not clean up installer: {cleanup_err}")

            # Verify installation
            print("\n   Verifying installation...")
            node_valid_retry, node_msg_retry = check_node_version()

            if node_valid_retry:
                print(f"   ✅ {node_msg_retry}")
                return True, "Installed successfully"
            else:
                # Node.js installed but not yet in PATH (needs environment refresh)
                print(f"   ⚠️  Installation verification: {node_msg_retry}")
                print("   🔄 Automatically refreshing environment variables...")

                # Try to refresh environment variables in current process (Windows)
                try:
                    import winreg
                    # Read from system environment
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                      r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment") as key:
                        system_path = winreg.QueryValueEx(key, "Path")[0]

                    # Read from user environment
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                        try:
                            user_path = winreg.QueryValueEx(key, "Path")[0]
                        except (FileNotFoundError, OSError):
                            user_path = ""

                    # Combine paths
                    new_path = system_path + (";" + user_path if user_path else "")
                    os.environ["PATH"] = new_path

                    print("   ✅ Environment variables refreshed")
                except Exception as e:
                    print(f"   ⚠️  Could not refresh automatically: {e}")

                # Verify Node.js is now accessible
                print("\n   Verifying Node.js after environment refresh...")
                node_valid_final, node_msg_final = check_node_version()

                if node_valid_final:
                    print(f"   ✅ {node_msg_final}")
                    print("   ✅ Continuing installation...\n")
                    return True, "Installed successfully (after PATH refresh)"
                else:
                    print(f"   ⚠️  Still not found: {node_msg_final}")
                    return True, "RESTART_NEEDED"

        except Exception as e:
            print(f"   ❌ Failed to launch installer: {e}")
            return False, "SHOW_MANUAL"

    elif sys.platform == "darwin":
        print("   ⚠️  macOS installer will open")
        print("   📝 Follow the installation wizard")
        print(f"\n   Starting installer...")

        try:
            # macOS: Open .pkg installer
            subprocess.run(['open', str(installer_path)], check=True)
            print(f"   ✅ Installer launched successfully")
            print(f"\n   ⏳ Please complete the installation wizard")

            input("\n   Press Enter after installation completes...")

            # Clean up
            try:
                Path(installer_path).unlink()
            except OSError as cleanup_err:
                print(f"   ⚠️  Could not clean up installer: {cleanup_err}")

            # Verify
            print("\n   Verifying installation...")
            node_valid_retry, node_msg_retry = check_node_version()

            if node_valid_retry:
                print(f"   ✅ {node_msg_retry}")
                return True, "Installed successfully"
            else:
                # Node.js installed but not yet in PATH (needs environment refresh)
                print(f"   ⚠️  Installation verification: {node_msg_retry}")
                print("   🔄 Automatically refreshing environment variables...")

                # Try to refresh environment variables in current process (macOS)
                # macOS: Update PATH from common locations
                node_paths = ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin"]
                for path in node_paths:
                    if path not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = path + ":" + os.environ.get("PATH", "")
                print("   ✅ Added common Node.js paths to PATH")

                # Verify Node.js is now accessible
                print("\n   Verifying Node.js after environment refresh...")
                node_valid_final, node_msg_final = check_node_version()

                if node_valid_final:
                    print(f"   ✅ {node_msg_final}")
                    print("   ✅ Continuing installation...\n")
                    return True, "Installed successfully (after PATH refresh)"
                else:
                    print(f"   ⚠️  Still not found: {node_msg_final}")
                    return True, "RESTART_NEEDED"

        except Exception as e:
            print(f"   ❌ Failed to launch installer: {e}")
            return False, "SHOW_MANUAL"

    return False, "Unknown platform"


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
            Path(os.environ.get('LOCALAPPDATA', '')) / 'AnthropicClaude' / 'Claude.exe',
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
        print("   This may take 2-4 minutes...")

    try:
        # Upgrade pip first
        if verbose:
            print("   ⬆️  Upgrading pip to latest version...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            check=False,  # Don't fail if pip upgrade fails (non-critical)
            capture_output=not verbose
        )

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


def check_macos_libomp() -> Tuple[bool, str]:
    """
    Check if libomp is installed on macOS (required for ONNX Runtime OpenMP support).

    On Apple Silicon Macs, ONNX Runtime may require OpenMP for optimal performance.
    While FastEmbed/LanceDB pre-built wheels often include bundled OpenMP, some
    configurations may need system libomp.

    Returns:
        (is_installed, message)
        - (True, "installed") if libomp is found
        - (True, "not_needed") if not on macOS
        - (False, "not_found") if libomp is missing
        - (False, "homebrew_not_found") if Homebrew is not installed
    """
    if sys.platform != "darwin":
        return True, "not_needed"

    # Check if Homebrew is installed
    try:
        brew_result = subprocess.run(
            ['brew', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if brew_result.returncode != 0:
            return False, "homebrew_not_found"
    except FileNotFoundError:
        return False, "homebrew_not_found"
    except Exception:
        return False, "homebrew_not_found"

    # Check if libomp is installed via Homebrew
    try:
        result = subprocess.run(
            ['brew', 'list', 'libomp'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return True, "installed"
        else:
            return False, "not_found"
    except Exception:
        return False, "not_found"


def check_macos_prerequisites() -> Tuple[bool, List[str]]:
    """
    Check macOS-specific prerequisites for ONNX Runtime and native dependencies.

    Returns:
        (all_ok, list of warning messages)
    """
    if sys.platform != "darwin":
        return True, []

    import platform

    warnings = []
    all_ok = True
    arch = platform.machine()
    is_apple_silicon = arch in ["arm64", "aarch64"]

    # Check Xcode Command Line Tools
    try:
        result = subprocess.run(
            ['xcode-select', '-p'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            warnings.append("Xcode Command Line Tools not installed")
            warnings.append("  Install with: xcode-select --install")
            all_ok = False
    except FileNotFoundError:
        warnings.append("Xcode Command Line Tools not found")
        warnings.append("  Install with: xcode-select --install")
        all_ok = False
    except Exception:
        pass  # Non-critical check

    # Check libomp (important for Apple Silicon)
    libomp_ok, libomp_status = check_macos_libomp()

    if not libomp_ok:
        if libomp_status == "homebrew_not_found":
            if is_apple_silicon:
                warnings.append("Homebrew not found (recommended for Apple Silicon)")
                warnings.append("  Install Homebrew: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
        elif libomp_status == "not_found":
            if is_apple_silicon:
                warnings.append("libomp not found (may be needed for ONNX Runtime on Apple Silicon)")
                warnings.append("  Install with: brew install libomp")
                # Note: This is a warning, not a hard failure, as pre-built wheels often work without it

    return all_ok, warnings


def is_vc_redist_installed() -> bool:
    """
    Check if Visual C++ Redistributable 2015-2022 is installed (Windows only).

    Checks registry for VC++ 14.x runtime (covers 2015, 2017, 2019, 2022 versions).
    Supports x64, ARM64, and x86 architectures.

    Returns:
        True if installed, False otherwise
    """
    if sys.platform != "win32":
        return True  # Not Windows, not needed

    try:
        import winreg
        import platform
        
        arch = platform.machine().lower()
        
        # Determine registry key based on architecture
        # HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\{arch}
        if arch in ["amd64", "x86_64"]:
            runtime_arch = "x64"
        elif arch in ["arm64", "aarch64"]:
            runtime_arch = "arm64"
        else:
            runtime_arch = "x86"
            
        key_path = f"SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\{runtime_arch}"
        
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                key_path,
                0,
                winreg.KEY_READ
            )
            # Check if "Installed" value is 1
            installed, _ = winreg.QueryValueEx(key, "Installed")
            winreg.CloseKey(key)
            return installed == 1
        except FileNotFoundError:
            return False
    except ImportError:
        # winreg not available (shouldn't happen on Windows, but handle it)
        return False


def download_vc_redist(target_dir: Path = None) -> Tuple[bool, str]:
    """
    Download Visual C++ Redistributable installer from Microsoft with progress bar.
    Automatically detects architecture (x64, ARM64, x86).
    
    Args:
        target_dir: Directory to save installer (default: temp directory)
        
    Returns:
        (success, installer_path or error_message)
    """
    import tempfile
    import platform
    
    if target_dir is None:
        target_dir = Path(tempfile.gettempdir())
        
    arch = platform.machine().lower()
    
    # Determine download URL and filename based on architecture
    if arch in ["amd64", "x86_64"]:
        filename = "vc_redist.x64.exe"
        download_url = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
        arch_name = "x64"
    elif arch in ["arm64", "aarch64"]:
        filename = "vc_redist.arm64.exe"
        download_url = "https://aka.ms/vs/17/release/vc_redist.arm64.exe"
        arch_name = "ARM64"
    else:
        # Fallback to x86 for 32-bit or unknown
        filename = "vc_redist.x86.exe"
        download_url = "https://aka.ms/vs/17/release/vc_redist.x86.exe"
        arch_name = "x86"

    installer_path = target_dir / filename

    print(f"\n📦 Downloading Visual C++ Redistributable ({arch_name})...")
    success = download_with_progress(download_url, installer_path, f"Visual C++ Redistributable ({arch_name})")

    if success:
        # Verify file size (should be ~13-25MB)
        file_size = installer_path.stat().st_size
        if file_size < 1_000_000:  # Less than 1MB is suspicious
            return False, f"Downloaded file too small ({file_size} bytes), may be corrupted"
        return True, str(installer_path)
    else:
        return False, "Download failed"


def install_vc_redist_auto() -> Tuple[bool, str]:
    """
    Semi-automated Visual C++ Redistributable installation with user permission.

    This function:
    1. Checks if already installed (via registry)
    2. Asks user permission
    3. Downloads installer from Microsoft
    4. Runs installer with /passive mode (shows progress, minimal UI)

    Returns:
        (success, message)
        - success=True, message="Already installed" → No action needed
        - success=True, message="NEWLY_INSTALLED" → Just installed, needs Python restart
        - success=False, message=reason → Installation failed
    """
    if sys.platform != "win32":
        return True, "Not Windows, not needed"

    # Step 1: Check if already installed
    if is_vc_redist_installed():
        return True, "Already installed"

    # Step 2: Ask user permission
    print("\n" + "=" * 70)
    print("Windows System Component Required")
    print("=" * 70)
    print("\n⚠️  This component is needed for AI functionality to work on Windows.")
    print("   (Microsoft Visual C++ Runtime Library)\n")
    print("Options:")
    print("  [1] Install automatically (recommended, estimated 1-2 minutes)")
    print("  [2] Show manual installation steps")
    print("  [3] Skip (I already have it installed)")

    while True:
        choice = input("\nChoose option (1/2/3): ").strip()
        if choice in ["1", "2", "3"]:
            break
        print("❌ Invalid choice. Please enter 1, 2, or 3.")

    if choice == "2":
        # Show manual instructions (existing behavior)
        return False, "SHOW_MANUAL"
    elif choice == "3":
        return False, "User skipped installation"

    # Step 3: Download installer
    success, result = download_vc_redist()
    if not success:
        print(f"❌ Download failed: {result}")
        print("\nFalling back to manual installation instructions.")
        return False, "SHOW_MANUAL"

    installer_path = result

    # Step 4: Run installer
    print("\n🔧 Running installer...")
    print("   ⚠️  UAC prompt will appear - please click 'Yes' to allow installation")
    print("   📊 Progress bar will show installation status")

    try:
        result = subprocess.run(
            [installer_path, "/install", "/passive", "/norestart"],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        # Clean up installer
        try:
            Path(installer_path).unlink()
        except OSError as cleanup_err:
            print(f"   ⚠️  Could not clean up installer: {cleanup_err}")

        if result.returncode == 0:
            print("   ✅ Installation completed successfully!")
            print("   ⚠️  Python process needs to be restarted to load new DLLs")
            return True, "NEWLY_INSTALLED"
        elif result.returncode == 1638:
            # Already installed (another version)
            print("   ✅ Already installed (detected during installation)")
            return True, "Already installed"
        elif result.returncode == 3010:
            # Success but reboot required
            print("   ✅ Installation completed successfully!")
            print("   ⚠️  Note: Restart recommended for changes to take full effect")
            return True, "NEWLY_INSTALLED"
        else:
            print(f"   ❌ Installation failed with exit code {result.returncode}")
            if result.stderr:
                print(f"   Error: {result.stderr}")
            return False, "SHOW_MANUAL"

    except subprocess.TimeoutExpired:
        print("   ❌ Installation timed out after 5 minutes")
        return False, "SHOW_MANUAL"
    except Exception as e:
        print(f"   ❌ Installation error: {e}")
        return False, "SHOW_MANUAL"


def verify_onnx_runtime() -> Tuple[bool, str]:
    """
    Verify that ONNX Runtime can be imported (checks for Visual C++ dependencies on Windows).

    This is critical on Windows where ONNX Runtime requires Microsoft Visual C++ Redistributable.

    Returns:
        (is_valid, message)
    """
    try:
        import onnxruntime
        return True, f"ONNX Runtime {onnxruntime.__version__}"
    except ImportError as e:
        error_msg = str(e)

        # Check if it's a DLL load error (missing Visual C++ Redistributable on Windows)
        if "DLL load failed" in error_msg or "pybind11_state" in error_msg:
            return False, "DLL_MISSING"
        else:
            return False, f"Import failed: {error_msg}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def verify_critical_dependencies(show_progress: bool = False) -> Tuple[bool, List[str]]:
    """
    Verify all critical dependencies can be imported.

    This catches missing dependencies that are implicitly required but may not be
    in requirements.txt (e.g., pandas required by LanceDB's .to_pandas() method).

    Args:
        show_progress: If True, show inline progress for each verification

    Returns:
        (all_valid, list of error messages)
    """
    critical_imports = {
        'pandas': 'Required by LanceDB for .to_pandas() conversions',
        'fastapi': 'Core web framework',
        'lancedb': 'Vector database',
        'fastembed': 'Embedding generation',
        'mcp': 'Model Context Protocol SDK',
        'pydantic': 'Data validation',
        'httpx': 'HTTP client',
        'rapidfuzz': 'Fuzzy string matching',
    }

    # Windows-specific dependencies
    if sys.platform == 'win32':
        critical_imports['pywin32'] = 'Windows platform APIs (required by MCP SDK on Windows)'

    errors = []
    total = len(critical_imports)
    for idx, (package, description) in enumerate(critical_imports.items(), 1):
        if show_progress:
            # Show inline progress on same line
            sys.stdout.write(f"\r   Verifying dependencies... ({idx}/{total}) {package}")
            sys.stdout.flush()

        try:
            # pywin32 has a different import name
            import_name = 'win32api' if package == 'pywin32' else package
            __import__(import_name)
        except ImportError as e:
            errors.append(f"   ❌ {package}: {description}\n      Error: {e}")

    if show_progress:
        # Clear the progress line and print completion
        sys.stdout.write("\r   " + " " * 60 + "\r")  # Clear line
        sys.stdout.flush()

    return len(errors) == 0, errors


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

    # Windows uses npm.cmd, Unix uses npm
    npm_cmd = 'npm.cmd' if sys.platform == 'win32' else 'npm'

    try:
        result = subprocess.run(
            [npm_cmd, 'install'],
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
        print("❌ npm command not found.")
        print("💡 This should not happen if prerequisites check passed.")
        print("   Please ensure npm is in your PATH and try again.")
        print("   Download Node.js from: https://nodejs.org/")
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
    """Create backup of existing config file and clean up old backups (keep last 3)."""
    if not config_path.exists():
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = config_path.with_suffix(f'.json.backup.{timestamp}')
    shutil.copy2(config_path, backup_path)
    print(f"✅ Backup created: {backup_path.name}")

    # Clean up old backups, keeping the most recent 3
    try:
        backup_pattern = config_path.stem + ".json.backup.*"
        backups = sorted(
            config_path.parent.glob(backup_pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        for old_backup in backups[3:]:
            try:
                old_backup.unlink()
                print(f"   Cleaned up old backup: {old_backup.name}")
            except OSError:
                pass
    except Exception:
        pass  # Non-critical cleanup

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

    # Warn if aidefend already exists (Fix #9)
    if 'aidefend' in existing_config['mcpServers']:
        existing = existing_config['mcpServers']['aidefend']
        existing_cmd = existing.get('command', 'unknown')
        print(f"\n⚠️  Existing 'aidefend' MCP config found (command: {existing_cmd})")
        print(f"   This will be replaced with the new configuration.")

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
        print("   This will only add AIDEFEND to your MCP services.")
        print("   Your existing MCP services will not be affected.")
        response = input("\n   Continue? [Y/n]: ").strip().lower()
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


def configure_claude_code(auto: bool = False, dry_run: bool = False) -> bool:
    """
    Configure Claude Code (VSCode extension) for MCP mode.

    Creates or updates .mcp.json in project root.

    Returns:
        True if successful
    """
    print("\nConfiguring Claude Code for MCP mode...")

    project_root = Path(__file__).parent.parent
    mcp_json_path = project_root / '.mcp.json'
    python_path = get_python_path()
    mcp_path = get_mcp_path()

    print(f"   Config file: {mcp_json_path}")
    print(f"   Python: {python_path}")
    print(f"   Project: {mcp_path}")

    # Validate paths
    if not validate_paths(python_path, mcp_path):
        return False

    # Create AIDEFEND config for Claude Code (.mcp.json format)
    aidefend_config = {
        "command": python_path,
        "args": [f"{mcp_path}/__main__.py", "--mcp"],
        "env": {}
    }

    # Safe merge if .mcp.json exists
    if mcp_json_path.exists():
        try:
            with open(mcp_json_path, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)
            if not isinstance(existing_config, dict):
                existing_config = {}
        except json.JSONDecodeError:
            print("⚠️  Existing .mcp.json has invalid JSON, creating new config")
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

    # Confirm if not auto mode
    if not auto and not dry_run:
        if mcp_json_path.exists():
            print("\n⚠️  This will modify your .mcp.json configuration.")
            print("   This will only add AIDEFEND to your MCP services.")
            print("   Your existing MCP services will not be affected.")
        else:
            print("\n📝 This will create .mcp.json in your project root.")
        response = input("\n   Continue? [Y/n]: ").strip().lower()
        if response and response != 'y':
            print("❌ Claude Code configuration cancelled")
            return False

    # Add/update AIDEFEND
    existing_config['mcpServers']['aidefend'] = aidefend_config

    # Show preserved servers
    if other_servers:
        print(f"✅ Preserving {len(other_servers)} existing MCP server(s):")
        for server_name in other_servers:
            print(f"   • {server_name}")

    # Write .mcp.json
    if dry_run:
        print("\n[DRY RUN] Would write .mcp.json:")
        print(json.dumps(existing_config, indent=2))
        return True

    try:
        with open(mcp_json_path, 'w', encoding='utf-8') as f:
            json.dump(existing_config, f, indent=2, ensure_ascii=False)
        print(f"✅ Configuration saved to: {mcp_json_path}")

        print("\n✅ Claude Code configuration completed successfully!")
        print("\n📝 NOTE: .mcp.json created in project root")
        print("   You can commit this file to share MCP config with your team")
        print("\n⚠️  IMPORTANT: Reload VSCode window to apply changes")
        print("   1. Press Ctrl+Shift+P (Windows/Linux) or Cmd+Shift+P (macOS)")
        print("   2. Type 'Reload Window' and press Enter")
        print("   3. Look for 'aidefend' in MCP tools")

        return True

    except Exception as e:
        print(f"❌ Failed to write .mcp.json: {e}")
        return False


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
    parser.add_argument('--client',
                       choices=['desktop', 'code', 'both'],
                       default='desktop',
                       help='Target client: desktop (Claude Desktop), code (Claude Code/VSCode), both (default: desktop)')

    args = parser.parse_args()

    # Check mode - only verify prerequisites
    if args.check:
        print_banner("AIDEFEND MCP - Prerequisites Check")

        all_ok = True

        # Check Python
        print("[1/5] Checking Python version...")
        py_valid, py_version = check_python_version()
        if py_valid:
            print(f"   ✅ Python {py_version} (OK)")
        else:
            print(f"   ❌ Python {py_version} - Need 3.9+")
            print(f"      Download: https://www.python.org/downloads/")
            all_ok = False

        # Check Node.js
        print("\n[2/5] Checking Node.js version...")
        node_valid, node_version = check_node_version()
        if node_valid:
            print(f"   ✅ Node.js {node_version} (OK)")
        else:
            print(f"   ❌ {node_version}")
            print(f"      Download: https://nodejs.org/")
            all_ok = False

        # Check platform-specific prerequisites
        print("\n[3/5] Checking platform-specific prerequisites...")
        if sys.platform == "darwin":
            import platform
            arch = platform.machine()
            print(f"   Platform: macOS ({arch})")
            macos_ok, macos_warnings = check_macos_prerequisites()
            if macos_ok and not macos_warnings:
                print(f"   ✅ macOS prerequisites OK")
            else:
                for warning in macos_warnings:
                    if warning.startswith("  "):
                        print(f"      {warning.strip()}")
                    else:
                        print(f"   ⚠️  {warning}")
                # macOS warnings are non-blocking (pre-built wheels often work)
        elif sys.platform == "win32":
            print(f"   Platform: Windows")
            if is_vc_redist_installed():
                print(f"   ✅ Visual C++ Redistributable installed")
            else:
                print(f"   ⚠️  Visual C++ Redistributable not detected")
                print(f"      Will be installed automatically if needed")
        else:
            print(f"   Platform: Linux")
            print(f"   ✅ No special prerequisites")

        # Check Claude Desktop
        print("\n[4/5] Checking Claude Desktop...")
        claude_installed, claude_info = check_claude_desktop_installed()
        if claude_installed:
            print(f"   ✅ Found: {claude_info}")
        else:
            print(f"   ⚠️  {claude_info}")
            print(f"      Download: https://claude.ai/download")
            print(f"      (Not required for REST API mode)")

        # Check Internet
        print("\n[5/5] Checking internet connectivity...")
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
    print_step(1, 6, "Checking Python version")
    py_valid, py_version = check_python_version()
    print(f"   Python version: {py_version}")

    if not py_valid:
        print(f"❌ Python 3.9+ required, found {py_version}")
        print("   Please upgrade Python: https://www.python.org/downloads/")
        return 1
    print("✅ Python version OK")

    # Check macOS-specific prerequisites (non-blocking warnings)
    if sys.platform == "darwin":
        import platform
        arch = platform.machine()
        is_apple_silicon = arch in ["arm64", "aarch64"]

        print(f"\n   🍎 Detected macOS ({arch})")
        macos_ok, macos_warnings = check_macos_prerequisites()

        if macos_warnings:
            print("\n   ⚠️  macOS Recommendations:")
            for warning in macos_warnings:
                if warning.startswith("  "):
                    print(f"      {warning.strip()}")
                else:
                    print(f"      • {warning}")
            print("\n   💡 Note: Installation may still succeed without these.")
            print("      If you encounter ONNX errors later, install the recommended packages.")

    # Step 2: Check Node.js
    print_step(2, 6, "Checking Node.js version")
    node_valid, node_version = check_node_version()
    print(f"   Node.js version: {node_version}")

    if not node_valid:
        # Try semi-automated installation
        node_success, node_result = install_nodejs_auto()

        if node_success:
            if node_result == "RESTART_NEEDED":
                print("\n🔄 Restarting installation to load Node.js...")
                print(f"   Command: {' '.join(sys.argv)}\n")
                print("=" * 70 + "\n")
                # Re-run the same script with same arguments
                result = subprocess.run([sys.executable] + sys.argv)
                return result.returncode
            
            print("✅ Node.js installed successfully")
            
            # Refresh PATH for current process so we can use node immediately
            import os
            if sys.platform == "win32":
                # Standard Node.js install path on Windows
                node_path = Path("C:/Program Files/nodejs")
                if node_path.exists():
                    os.environ["PATH"] = str(node_path) + os.pathsep + os.environ["PATH"]
                    print(f"   🔄 Refreshed PATH to include: {node_path}")
            elif sys.platform == "darwin":
                # Standard paths on macOS (pkg installer usually links to /usr/local/bin)
                # No action usually needed as /usr/local/bin is in PATH, but we can check
                pass
                
        elif node_result == "SHOW_MANUAL":
            # Show manual installation instructions
            print("\n" + "=" * 70)
            print("❌ Node.js 18+ Required")
            print("=" * 70)
            print(f"\n⚠️  Current status: {node_version}")
            print("   Node.js 18+ is required for parsing AIDEFEND JavaScript files.\n")

            if sys.platform == "win32":
                print("📥 Windows Installation:")
                print("   1. Download Node.js LTS:")
                print("      https://nodejs.org/")
                print("   2. Run the installer (.msi)")
                print("   3. Ensure 'Add to PATH' is checked")
                print("   4. Restart your terminal")
                print("   5. Run this installation script again")
            elif sys.platform == "darwin":
                print("📥 macOS Installation:")
                print("   Option 1 - Official Installer:")
                print("      https://nodejs.org/")
                print("   Option 2 - Homebrew:")
                print("      brew install node")
            else:  # Linux
                print("📥 Linux Installation:")
                print("   Ubuntu/Debian:")
                print("      curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -")
                print("      sudo apt-get install -y nodejs")
                print("   ")
                print("   Fedora/RHEL:")
                print("      curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash -")
                print("      sudo dnf install -y nodejs")
                print("   ")
                print("   Or use your package manager:")
                print("      • Arch: sudo pacman -S nodejs npm")
                print("      • openSUSE: sudo zypper install nodejs npm")

            print("\n💡 After installation, restart your terminal and run:")
            print("   python scripts/install.py")
            print("=" * 70)
            return 1
        else:
            # User skipped installation
            print(f"\n❌ Node.js installation {node_result}")
            print("   Service cannot function without Node.js 18+")
            print("   Please install manually and run this script again.")
            return 1

    print("✅ Node.js version OK")

    # Step 3: Install Python dependencies
    if not args.dry_run:
        print_step(3, 6, "Installing Python dependencies")
        if not install_python_dependencies(verbose=True):
            print("❌ Failed to install Python dependencies")
            return 1

        # Verify ONNX Runtime can be imported (critical for Windows)
        print("\n   Verifying ONNX Runtime...")
        onnx_valid, onnx_msg = verify_onnx_runtime()

        if not onnx_valid:
            if onnx_msg == "DLL_MISSING":
                # Windows-specific DLL error - missing Visual C++ Redistributable
                # Try semi-automated installation
                vc_success, vc_result = install_vc_redist_auto()

                if vc_success:
                    # Check if VC++ was just installed (vs. already installed)
                    if vc_result == "NEWLY_INSTALLED":
                        # VC++ just installed - Python process needs restart to load DLLs
                        print("\n" + "=" * 70)
                        print("✅ Visual C++ Redistributable Installed Successfully")
                        print("=" * 70)
                        print("\n⚠️  IMPORTANT: Python needs to be restarted to load new DLLs")
                        
                        print("   Restarting installation automatically...\n")
                        print()
                        # Auto-restart the installation script
                        print("\n🔄 Restarting installation...")
                        print(f"   Command: {' '.join(sys.argv)}\n")
                        print("=" * 70 + "\n")

                        # Re-run the same script with same arguments
                        result = subprocess.run([sys.executable] + sys.argv)

                        # Exit with same code as restarted process
                        return result.returncode

                    # VC++ was already installed, retry ONNX Runtime import
                    print("\n   Retrying ONNX Runtime import...")
                    onnx_valid_retry, onnx_msg_retry = verify_onnx_runtime()

                    if onnx_valid_retry:
                        print(f"   ✅ {onnx_msg_retry}")
                    else:
                        # Still failing after VC++ was already installed
                        print(f"\n❌ ONNX Runtime still failing: {onnx_msg_retry}")
                        print("💡 Try reinstalling onnxruntime:")
                        print("   python -m pip uninstall onnxruntime -y")
                        print("   python -m pip install onnxruntime")
                        return 1
                elif vc_result == "SHOW_MANUAL":
                    # User chose manual installation or auto-install failed
                    print("\n" + "=" * 70)
                    print("❌ ONNX Runtime DLL Error (Windows)")
                    print("=" * 70)
                    print("\n⚠️  ONNX Runtime requires Microsoft Visual C++ Redistributable")
                    print("   This is a one-time installation needed for AI/ML libraries on Windows.\n")
                    print("📥 Manual installation steps:")
                    print("   1. Download Visual C++ Redistributable:")
                    print("      • Latest: https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist")
                    print("      • Direct: https://aka.ms/vs/17/release/vc_redist.x64.exe")
                    print("   2. Run the installer and follow the prompts")
                    print("   3. Restart your computer (recommended)")
                    print("   4. Run this installation script again\n")
                    print("💡 Alternative: The issue may resolve by reinstalling onnxruntime:")
                    print("   python -m pip uninstall onnxruntime -y")
                    print("   python -m pip install onnxruntime\n")
                    print("=" * 70)
                    return 1
                else:
                    # User skipped
                    print(f"\n❌ Visual C++ Redistributable installation {vc_result}")
                    print("   ONNX Runtime will not work without it.")
                    print("   Please install manually and run this script again.")
                    return 1
            else:
                # Other import error
                print(f"\n❌ ONNX Runtime verification failed: {onnx_msg}")
                print("💡 This may affect embedding functionality.")
                print("   Try: python -m pip install --upgrade onnxruntime")
                return 1

        print(f"   ✅ {onnx_msg}")

        # Verify all critical dependencies (catches implicit requirements like pandas)
        print("\n   Verifying all critical dependencies...")
        deps_valid, dep_errors = verify_critical_dependencies(show_progress=True)

        if not deps_valid:
            print("\n" + "=" * 70)
            print("❌ Missing Critical Dependencies")
            print("=" * 70)
            print("\n⚠️  Some required dependencies are missing:\n")
            for error in dep_errors:
                print(error)
            print("\n💡 This usually means requirements.txt is incomplete.")
            print("   Please report this issue at: https://github.com/anthropics/aidefend-mcp/issues")
            print("\n   Quick fix:")
            print("   python -m pip install -r requirements.txt")
            print("=" * 70)
            return 1

        print(f"   ✅ All critical dependencies verified")
    else:
        print_step(3, 6, "Installing Python dependencies [DRY RUN]")
        print("   Would run: pip install -r requirements.txt")

    # Step 4: Install Node.js dependencies
    if not args.dry_run:
        print_step(4, 6, "Installing Node.js dependencies")
        if not install_node_dependencies(verbose=True):
            print("❌ Failed to install Node.js dependencies")
            return 1
    else:
        print_step(4, 6, "Installing Node.js dependencies [DRY RUN]")
        print("   Would run: npm install")

    # Step 5: Configure MCP (optional)
    if not args.no_mcp:
        config_success = True

        # Configure Claude Desktop
        if args.client in ['desktop', 'both']:
            print_step(5, 6, "Configuring Claude Desktop (MCP mode)")
            if not configure_mcp(auto=args.auto, dry_run=args.dry_run):
                print("⚠️  Claude Desktop configuration failed")
                config_success = False

        # Configure Claude Code
        if args.client in ['code', 'both']:
            step_label = "Configuring Claude Code (MCP mode)" if args.client == 'code' else "Additionally configuring Claude Code (MCP mode)"
            print_step(5, 6, step_label)
            if not configure_claude_code(auto=args.auto, dry_run=args.dry_run):
                print("⚠️  Claude Code configuration failed")
                config_success = False

        if not config_success:
            print("\n⚠️  Some configurations failed, but dependencies are installed")
            print("   You can run setup again: python scripts/install.py --client <desktop|code|both>")
            return 1
    else:
        print_step(5, 6, "Skipping MCP configuration [--no-mcp]")

    # Step 6: Initial Database Sync (if MCP configured and not dry-run)
    if not args.no_mcp and not args.dry_run:
        print_step(6, 6, "Performing initial database sync")
        print("   This is a one-time operation (estimated 5 - 10 minutes)")
        print("   Downloading AIDEFEND content from GitHub and building vector database...")
        print("   • Downloading files: ~1-2 minutes")
        print("   • Generating embeddings for ~549 documents: ~5-10 minutes (CPU-based)")
        print("   Please be patient - this ensures fast queries later!")
        print("")

        try:
            project_root = Path(__file__).parent.parent
            result = subprocess.run(
                [sys.executable, str(project_root / '__main__.py'), '--resync'],
                cwd=str(project_root),
                timeout=600  # 10 minutes timeout
            )

            if result.returncode == 0:
                print("\n✅ Initial sync completed successfully")
                print("   Database is ready - no cold start delays!")
            else:
                print("\n⚠️  Initial sync failed (non-critical)")
                print("   The service will sync automatically on first use")
                print("   You can manually sync later: python __main__.py --resync")

        except subprocess.TimeoutExpired:
            print("\n⚠️  Initial sync timed out (this is rare)")
            print("   The service will sync automatically on first use")
            print("   You can manually sync later: python __main__.py --resync")
        except Exception as e:
            print(f"\n⚠️  Initial sync error: {e}")
            print("   The service will sync automatically on first use")
            print("   You can manually sync later: python __main__.py --resync")
    elif not args.no_mcp and args.dry_run:
        print_step(6, 6, "Initial database sync [DRY RUN]")
        print("   Would run: python __main__.py --resync")

    # Success
    print_banner("✅ Installation Complete!")

    if not args.dry_run:
        if not args.no_mcp:
            print("Next steps:")

            # Instructions based on which client was configured
            if args.client == 'desktop':
                print("  1. Restart Claude Desktop (close completely and reopen)")
                print("  2. Look for 'aidefend' in MCP tools (Search and tools icon ⚙️)")
                print("  3. Try: 'Search AIDEFEND for prompt injection defenses'")
            elif args.client == 'code':
                print("  1. Reload VSCode window (Ctrl+Shift+P → 'Reload Window')")
                print("  2. Look for 'aidefend' in MCP tools")
                print("  3. Try using AIDEFEND tools via / commands")
            elif args.client == 'both':
                print("  Claude Desktop:")
                print("    1. Restart Claude Desktop (close completely and reopen)")
                print("    2. Look for 'aidefend' in MCP tools (Search and tools icon ⚙️)")
                print("  Claude Code (VSCode):")
                print("    1. Reload VSCode window (Ctrl+Shift+P → 'Reload Window')")
                print("    2. Look for 'aidefend' in MCP tools")
        else:
            print("Dependencies installed successfully!")
            print("\nTo configure clients later:")
            print("  python scripts/install.py --client desktop    # Claude Desktop")
            print("  python scripts/install.py --client code       # Claude Code (VSCode)")
            print("  python scripts/install.py --client both       # Both clients")
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
