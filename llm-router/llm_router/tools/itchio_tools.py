"""itch.io integration tools using Butler CLI for game publishing.

WORKFLOW:
1. itchio_setup() - Download and install Butler from GitHub releases
2. itchio_login() - Authenticate with itch.io (opens browser for OAuth)
3. User creates game page manually at https://itch.io/game/new (Cloudflare blocks automation)
4. itchio_upload() - Upload game build to itch.io
"""

import asyncio
import json
import os
import platform
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Optional

from llm_router.tools import ToolDefinition, ToolRegistry

# Default Butler install location
BUTLER_INSTALL_DIR = Path.home() / "butler"
BUTLER_GITHUB_VERSION = "v15.26.1"


def get_butler_path() -> Optional[str]:
    """Find Butler executable - check PATH, then default install location."""
    # Check system PATH first
    butler = shutil.which("butler")
    if butler:
        return butler

    # Check default install location
    system = platform.system().lower()
    if system == "windows":
        butler_exe = BUTLER_INSTALL_DIR / "windows-amd64" / "butler.exe"
    elif system == "darwin":
        butler_exe = BUTLER_INSTALL_DIR / "darwin-amd64" / "butler"
    else:
        butler_exe = BUTLER_INSTALL_DIR / "linux-amd64" / "butler"

    if butler_exe.exists():
        return str(butler_exe)

    return None


async def itchio_setup() -> dict:
    """
    Download and install Butler CLI from GitHub releases.

    This is the first step in the itch.io workflow.

    Returns:
        Dict with installation status and Butler path
    """
    try:
        # Check if already installed
        butler_path = get_butler_path()
        if butler_path:
            # Get version
            result = subprocess.run(
                [butler_path, "-V"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return {
                    "installed": True,
                    "path": butler_path,
                    "version": result.stdout.strip(),
                    "message": f"Butler already installed at {butler_path}"
                }

        # Download from GitHub releases
        system = platform.system().lower()
        machine = platform.machine().lower()

        if system == "windows":
            arch = "amd64"
            ext = "zip"
        elif system == "darwin":
            arch = "amd64" if machine == "x86_64" else "arm64"
            ext = "zip"
        else:  # Linux
            arch = "amd64"
            ext = "zip"

        download_url = f"https://github.com/itchio/butler/releases/download/{BUTLER_GITHUB_VERSION}/butler-{system}-{arch}.{ext}"

        # Create install directory
        BUTLER_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        extract_dir = BUTLER_INSTALL_DIR / f"{system}-{arch}"
        zip_path = BUTLER_INSTALL_DIR / f"butler.{ext}"

        # Download
        print(f"Downloading Butler from {download_url}...")
        urllib.request.urlretrieve(download_url, zip_path)

        # Extract
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(BUTLER_INSTALL_DIR)

        # Clean up zip
        zip_path.unlink()

        # Find the executable
        butler_path = get_butler_path()
        if butler_path:
            # Make executable on Unix
            if system != "windows":
                os.chmod(butler_path, 0o755)

            return {
                "installed": True,
                "path": butler_path,
                "version": BUTLER_GITHUB_VERSION,
                "message": f"Butler installed to {butler_path}",
                "note": "Add to PATH or use full path for uploads"
            }
        else:
            return {
                "installed": False,
                "error": "Downloaded but couldn't find Butler executable"
            }

    except Exception as e:
        return {
            "installed": False,
            "error": f"Failed to install Butler: {str(e)}",
            "manual_install": "Download from https://github.com/itchio/butler/releases"
        }


async def itchio_check_butler() -> dict:
    """
    Check if Butler CLI is installed and get version info.

    Returns:
        Dict with installation status and version
    """
    try:
        butler_path = get_butler_path()

        if not butler_path:
            return {
                "installed": False,
                "error": "Butler CLI not found",
                "solution": "Run itchio_setup() to auto-install, or install manually",
                "install_instructions": {
                    "auto": "Run itchio_setup() tool",
                    "windows": "scoop install butler",
                    "macos": "brew install butler",
                    "manual": f"Download from https://github.com/itchio/butler/releases"
                }
            }

        # Get version
        result = subprocess.run(
            [butler_path, "-V"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return {
                "installed": True,
                "path": butler_path,
                "version": result.stdout.strip(),
                "message": f"Butler {result.stdout.strip()} is ready"
            }
        else:
            return {
                "installed": False,
                "error": f"Butler error: {result.stderr}"
            }

    except subprocess.TimeoutExpired:
        return {"installed": False, "error": "Butler command timed out"}
    except Exception as e:
        return {"installed": False, "error": str(e)}


async def itchio_login() -> dict:
    """
    Login to itch.io - opens browser for OAuth authentication.

    NOTE: This requires user interaction in the browser window.
    Cloudflare blocks automated login, so OAuth must be completed manually.

    Returns:
        Dict with login status
    """
    try:
        butler_path = get_butler_path()
        if not butler_path:
            return {
                "success": False,
                "error": "Butler not installed. Run itchio_setup() first."
            }

        # Butler login requires interactive browser OAuth
        # Run it and let user complete in browser
        proc = await asyncio.create_subprocess_exec(
            butler_path, "login",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=120  # 2 minutes for user to complete OAuth
        )

        stdout_text = stdout.decode() if stdout else ""
        stderr_text = stderr.decode() if stderr else ""

        if "Authenticated successfully" in stdout_text or proc.returncode == 0:
            return {
                "success": True,
                "message": "Successfully logged in to itch.io",
                "credentials_path": str(Path.home() / ".config" / "itch" / "butler_creds")
            }
        else:
            return {
                "success": False,
                "error": stderr_text or stdout_text,
                "note": "Complete login in the browser window that opens"
            }

    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Login timed out - complete OAuth in browser within 2 minutes"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def itchio_upload(
    game_path: str,
    username: str,
    game_slug: str,
    channel: str = "html5",
    version: Optional[str] = None
) -> dict:
    """
    Upload a game build to itch.io using Butler.

    PREREQUISITES:
    1. Butler installed (itchio_setup)
    2. Logged in (itchio_login)
    3. Game page created at https://itch.io/game/new (manual step - Cloudflare blocks automation)

    Args:
        game_path: Path to the game build directory
        username: itch.io username
        game_slug: Game URL slug (e.g., "my-game" for username.itch.io/my-game)
        channel: Upload channel (windows, mac, linux, html5, android)
        version: Optional version number

    Returns:
        Dict with upload status and game URL
    """
    try:
        butler_path = get_butler_path()
        if not butler_path:
            return {
                "success": False,
                "error": "Butler not installed. Run itchio_setup() first."
            }

        game_dir = Path(game_path)
        if not game_dir.exists():
            return {"success": False, "error": f"Game path not found: {game_path}"}

        # Construct itch.io target
        target = f"{username}/{game_slug}:{channel}"

        # Build butler push command
        cmd = [butler_path, "push", str(game_dir), target]
        if version:
            cmd.extend(["--userversion", version])

        # Run butler push
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=300  # 5 minute timeout for uploads
        )

        stdout_text = stdout.decode() if stdout else ""
        stderr_text = stderr.decode() if stderr else ""

        if proc.returncode == 0:
            game_url = f"https://{username}.itch.io/{game_slug}"
            return {
                "success": True,
                "url": game_url,
                "channel": channel,
                "username": username,
                "game_slug": game_slug,
                "message": f"Successfully uploaded to {game_url}",
                "output": stdout_text[-1000:] if len(stdout_text) > 1000 else stdout_text
            }
        else:
            # Parse common errors
            error_lower = (stderr_text + stdout_text).lower()

            if "not logged in" in error_lower or "credentials" in error_lower:
                return {
                    "success": False,
                    "error": "Not logged in. Run itchio_login() first.",
                    "details": stderr_text
                }
            elif "invalid game" in error_lower:
                return {
                    "success": False,
                    "error": f"Game '{game_slug}' not found.",
                    "solution": f"Create the game page at https://itch.io/game/new first (Cloudflare blocks automation)",
                    "required_slug": game_slug,
                    "required_url": f"https://{username}.itch.io/{game_slug}"
                }
            else:
                return {
                    "success": False,
                    "error": f"Upload failed: {stderr_text or stdout_text}"
                }

    except asyncio.TimeoutError:
        return {"success": False, "error": "Upload timed out (took > 5 minutes)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def itchio_publish_workflow(
    game_path: str,
    username: str,
    game_name: str,
    game_slug: Optional[str] = None,
    channel: str = "html5"
) -> dict:
    """
    Complete workflow to publish a game to itch.io.

    This handles:
    1. Checking/Installing Butler
    2. Checking authentication
    3. Uploading the game
    4. Returning the game URL

    NOTE: Game page must be created manually at https://itch.io/game/new
    (Cloudflare blocks automated creation)

    Args:
        game_path: Path to the game build directory
        username: itch.io username
        game_name: Display name of the game
        game_slug: URL slug (defaults to game_name lowercased)
        channel: Upload channel (default: html5)

    Returns:
        Dict with final status and game URL
    """
    results = {}

    # Step 1: Check/Install Butler
    check = await itchio_check_butler()
    if not check.get("installed"):
        results["setup"] = await itchio_setup()
        check = await itchio_check_butler()
        if not check.get("installed"):
            results["error"] = "Failed to install Butler"
            return results

    results["butler"] = check

    # Step 2: Check authentication
    # (We skip actual login check since it requires browser interaction)

    # Step 3: Upload
    slug = game_slug or game_name.lower().replace(" ", "-").replace("_", "-")

    upload_result = await itchio_upload(
        game_path=game_path,
        username=username,
        game_slug=slug,
        channel=channel
    )
    results["upload"] = upload_result

    if upload_result.get("success"):
        results["success"] = True
        results["url"] = upload_result["url"]
        results["message"] = f"Game published at {upload_result['url']}"
    else:
        results["success"] = False
        results["error"] = upload_result.get("error")
        # Add helpful info for manual game creation
        results["manual_step"] = {
            "action": "Create game page",
            "url": "https://itch.io/game/new",
            "required": {
                "title": game_name,
                "slug": slug,
                "type": "HTML" if channel == "html5" else "Downloadable"
            }
        }

    return results


# Tool Definitions
ITCHIO_SETUP_DEF = ToolDefinition(
    name="itchio_setup",
    description="Download and install Butler CLI from GitHub releases. Run this first to set up itch.io publishing.",
    parameters={
        "type": "object",
        "properties": {},
    },
    function=itchio_setup,
    category="itchio",
)

ITCHIO_CHECK_BUTLER_DEF = ToolDefinition(
    name="itchio_check_butler",
    description="Check if Butler CLI is installed and get version info.",
    parameters={
        "type": "object",
        "properties": {},
    },
    function=itchio_check_butler,
    category="itchio",
)

ITCHIO_LOGIN_DEF = ToolDefinition(
    name="itchio_login",
    description="Login to itch.io - opens browser for OAuth. User must complete login in browser.",
    parameters={
        "type": "object",
        "properties": {},
    },
    function=itchio_login,
    category="itchio",
)

ITCHIO_UPLOAD_DEF = ToolDefinition(
    name="itchio_upload",
    description="Upload a game build to itch.io. Requires Butler installed and game page created manually.",
    parameters={
        "type": "object",
        "properties": {
            "game_path": {
                "type": "string",
                "description": "Path to the game build directory"
            },
            "username": {
                "type": "string",
                "description": "Your itch.io username"
            },
            "game_slug": {
                "type": "string",
                "description": "Game URL slug (e.g., 'my-game' for username.itch.io/my-game)"
            },
            "channel": {
                "type": "string",
                "description": "Upload channel",
                "default": "html5",
                "enum": ["windows", "mac", "linux", "html5", "android"]
            },
            "version": {
                "type": "string",
                "description": "Optional version number"
            },
        },
        "required": ["game_path", "username", "game_slug"],
    },
    function=itchio_upload,
    category="itchio",
)

ITCHIO_PUBLISH_WORKFLOW_DEF = ToolDefinition(
    name="itchio_publish",
    description="""Complete workflow to publish a game to itch.io.
Handles Butler setup and upload. NOTE: Game page must be created manually at https://itch.io/game/new first.""",
    parameters={
        "type": "object",
        "properties": {
            "game_path": {
                "type": "string",
                "description": "Path to the game build directory"
            },
            "username": {
                "type": "string",
                "description": "Your itch.io username"
            },
            "game_name": {
                "type": "string",
                "description": "Display name of the game"
            },
            "game_slug": {
                "type": "string",
                "description": "URL slug (optional, defaults to game_name lowercased)"
            },
            "channel": {
                "type": "string",
                "description": "Upload channel",
                "default": "html5"
            },
        },
        "required": ["game_path", "username", "game_name"],
    },
    function=itchio_publish_workflow,
    category="itchio",
)


def register_itchio_tools(registry: ToolRegistry) -> None:
    """Register all itch.io tools with a registry."""
    registry.register(ITCHIO_SETUP_DEF)
    registry.register(ITCHIO_CHECK_BUTLER_DEF)
    registry.register(ITCHIO_LOGIN_DEF)
    registry.register(ITCHIO_UPLOAD_DEF)
    registry.register(ITCHIO_PUBLISH_WORKFLOW_DEF)
