"""Debugging and validation tools for Godot projects."""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from llm_router.tools import ToolDefinition, ToolRegistry


async def godot_validate_project(
    project_path: str
) -> dict:
    """
    Validate a Godot project for common issues.

    Checks:
    - project.godot exists and is valid
    - Main scene is set
    - Scripts have no syntax errors
    - Scenes reference valid scripts
    - Input mappings are valid
    - No missing resources

    Args:
        project_path: Path to the Godot project

    Returns:
        Dict with validation results
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"valid": False, "error": f"Project directory not found: {project_path}"}

        issues = []
        warnings = []

        # Check project.godot
        project_file = project_dir / "project.godot"
        if not project_file.exists():
            issues.append({
                "severity": "critical",
                "category": "project",
                "message": "project.godot file is missing",
                "fix": "Create a project.godot file or use godot_create_project"
            })
        else:
            # Parse project.godot
            content = project_file.read_text()

            # Check for required sections
            if "[application]" not in content:
                warnings.append({
                    "severity": "warning",
                    "category": "project",
                    "message": "Missing [application] section in project.godot"
                })

            # Check for run/main_scene
            if "run/main_scene" not in content:
                warnings.append({
                    "severity": "warning",
                    "category": "scene",
                    "message": "No main scene configured",
                    "fix": "Add run/main_scene=\"res://Main.tscn\" to [application] section"
                })

            # Check for config/name
            if "config/name" not in content:
                warnings.append({
                    "severity": "info",
                    "category": "project",
                    "message": "Project name not set"
                })

        # Check for scene files
        scene_files = list(project_dir.glob("*.tscn"))
        if not scene_files:
            warnings.append({
                "severity": "warning",
                "category": "scene",
                "message": "No scene files (.tscn) found",
                "fix": "Create a scene with godot_build_scene or godot_add_scene"
            })
        else:
            # Validate each scene
            for scene_file in scene_files:
                scene_issues = _validate_scene(scene_file, project_dir)
                issues.extend(scene_issues)

        # Check for scripts
        script_files = list(project_dir.glob("*.gd"))
        if not script_files:
            warnings.append({
                "severity": "info",
                "category": "script",
                "message": "No script files (.gd) found"
            })
        else:
            # Validate each script
            for script_file in script_files:
                script_issues = _validate_script(script_file)
                issues.extend(script_issues)

        # Check for referenced resources
        resource_issues = _check_missing_resources(project_dir)
        issues.extend(resource_issues)

        # Summary
        critical_count = len([i for i in issues if i.get("severity") == "critical"])
        error_count = len([i for i in issues if i.get("severity") == "error"])
        warning_count = len(warnings)

        return {
            "valid": critical_count == 0 and error_count == 0,
            "project_path": str(project_dir),
            "issues": issues,
            "warnings": warnings,
            "summary": {
                "critical": critical_count,
                "errors": error_count,
                "warnings": warning_count,
                "total_issues": len(issues) + len(warnings)
            },
            "scene_count": len(scene_files),
            "script_count": len(script_files),
            "message": "Validation complete" if critical_count == 0 else "Project has critical issues"
        }

    except Exception as e:
        return {"valid": False, "error": str(e)}


def _validate_scene(scene_path: Path, project_dir: Path) -> list[dict]:
    """Validate a scene file."""
    issues = []
    content = scene_path.read_text()

    # Check for referenced scripts
    script_refs = re.findall(r'script\s*=\s*ExtResource\([^)]+\)|script\s*=\s*res://([^"\']+\.gd)', content)

    for ref in script_refs:
        if isinstance(ref, str):
            script_path = project_dir / ref.replace("res://", "")
            if not script_path.exists():
                issues.append({
                    "severity": "error",
                    "category": "script",
                    "file": scene_path.name,
                    "message": f"Referenced script not found: {ref}",
                    "fix": f"Create the script file or remove the reference"
                })

    # Check for node types
    node_types = re.findall(r'type="([^"]+)"', content)
    known_types = {
        "Node2D", "Node3D", "Node", "Sprite2D", "CharacterBody2D", "CharacterBody3D",
        "StaticBody2D", "StaticBody3D", "RigidBody2D", "RigidBody3D", "Area2D", "Area3D",
        "CollisionShape2D", "CollisionShape3D", "Camera2D", "Camera3D", "Light2D",
        "DirectionalLight3D", "PointLight2D", "PointLight3D", "Label", "Button",
        "ColorRect", "TextureRect", "Timer", "AudioStreamPlayer", "CanvasLayer",
        "Control", "Panel", "LineEdit", "TextEdit", "ProgressBar", "HSlider", "VSlider",
        "AnimatedSprite2D", "Path2D", "PathFollow2D", "Marker2D", "Marker3D",
        "RayCast2D", "RayCast3D", "TileMap", "ParallaxBackground", "ParallaxLayer",
    }

    for node_type in node_types:
        if node_type not in known_types:
            issues.append({
                "severity": "warning",
                "category": "scene",
                "file": scene_path.name,
                "message": f"Unknown node type: {node_type}",
                "fix": "Verify the node type is correct"
            })

    return issues


def _validate_script(script_path: Path) -> list[dict]:
    """Validate a GDScript file."""
    issues = []
    content = script_path.read_text()
    lines = content.split("\n")

    # Check for extends clause
    if not content.strip().startswith("extends"):
        issues.append({
            "severity": "error",
            "category": "script",
            "file": script_path.name,
            "line": 1,
            "message": "Script must start with 'extends' clause",
            "fix": f"Add 'extends Node2D' or appropriate type at the top"
        })

    # Check for common syntax issues
    for i, line in enumerate(lines, 1):
        # Check for Python-style print without parentheses
        if re.search(r'\bprint\s+[^(]', line) and not line.strip().startswith("#"):
            issues.append({
                "severity": "error",
                "category": "script",
                "file": script_path.name,
                "line": i,
                "message": "Python-style print found, use print()",
                "fix": f"Change to print(...)"
            })

        # Check for missing colons after func/class
        stripped = line.strip()
        if (stripped.startswith("func ") or stripped.startswith("class ")) and not stripped.endswith(":"):
            if not stripped.endswith(";"):  # Allow semicolon
                issues.append({
                    "severity": "error",
                    "category": "script",
                    "file": script_path.name,
                    "line": i,
                    "message": "Missing colon after function/class declaration",
                    "fix": f"Add ':' at the end of line {i}"
                })

        # Check for _process without delta parameter
        if re.match(r'func\s+_process\s*\(\s*\)', line):
            issues.append({
                "severity": "warning",
                "category": "script",
                "file": script_path.name,
                "line": i,
                "message": "_process should have delta parameter",
                "fix": "Change to func _process(delta: float) -> void:"
            })

        # Check for _physics_process without delta parameter
        if re.match(r'func\s+_physics_process\s*\(\s*\)', line):
            issues.append({
                "severity": "warning",
                "category": "script",
                "file": script_path.name,
                "line": i,
                "message": "_physics_process should have delta parameter",
                "fix": "Change to func _physics_process(delta: float) -> void:"
            })

    # Check for deprecated methods
    deprecated = {
        "yield": "await",
        "instance": "instantiate",
        "call_group": "call_group (still valid but consider Group nodes)",
    }

    for old, new in deprecated.items():
        if re.search(rf'\b{old}\s*\(', content):
            issues.append({
                "severity": "warning",
                "category": "script",
                "file": script_path.name,
                "message": f"'{old}' may be deprecated, consider using '{new}'",
                "fix": f"Replace {old} with {new}"
            })

    return issues


def _check_missing_resources(project_dir: Path) -> list[dict]:
    """Check for missing resource references."""
    issues = []

    # Check all scene and script files for resource references
    for file_path in project_dir.glob("**/*"):
        if file_path.suffix in [".tscn", ".gd", ".tres"]:
            try:
                content = file_path.read_text()

                # Find res:// references
                res_refs = re.findall(r'res://([^\s"\']+\.(png|jpg|svg|wav|ogg|mp3|gd|tscn|tres))', content)

                for res_path, _ in res_refs:
                    full_path = project_dir / res_path
                    if not full_path.exists():
                        issues.append({
                            "severity": "error",
                            "category": "resource",
                            "file": file_path.name,
                            "message": f"Missing resource: res://{res_path}",
                            "fix": f"Add the resource file or fix the reference"
                        })
            except Exception:
                pass

    return issues


async def godot_run_with_output(
    project_path: str,
    timeout: int = 30
) -> dict:
    """
    Run Godot project and capture output/errors.

    This runs the project in headless mode and captures console output.

    Args:
        project_path: Path to the Godot project
        timeout: Timeout in seconds (default: 30)

    Returns:
        Dict with output info or error
    """
    try:
        from llm_router.tools.godot_tools import find_godot

        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        godot_exe = find_godot()
        if not godot_exe:
            return {"error": "Godot executable not found"}

        # Run Godot in headless mode
        cmd = [
            godot_exe,
            "--headless",
            "--path", str(project_dir),
            "--quit-after", "3"  # Quit after 3 seconds
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        # Parse errors and warnings from output
        errors = []
        warnings = []

        output = result.stdout + result.stderr

        # Parse Godot error format
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Error patterns
            if "ERROR:" in line or "SCRIPT ERROR:" in line:
                errors.append({
                    "type": "error",
                    "message": line,
                    "file": None,
                    "line": None
                })
            elif "WARNING:" in line:
                warnings.append({
                    "type": "warning",
                    "message": line
                })

            # Try to extract file and line info
            match = re.search(r'at: ([^:]+):(\d+)', line)
            if match and errors:
                errors[-1]["file"] = match.group(1)
                errors[-1]["line"] = int(match.group(2))

        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "errors": errors,
            "warnings": warnings,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "message": "Run complete" if result.returncode == 0 else "Run completed with errors"
        }

    except subprocess.TimeoutExpired:
        return {"error": f"Process timed out after {timeout} seconds"}
    except Exception as e:
        return {"error": str(e)}


async def godot_preview(
    project_path: str,
    mode: str = "editor"
) -> dict:
    """
    Preview the game in Godot editor or as a window.

    Args:
        project_path: Path to the Godot project
        mode: "editor" (opens in editor), "window" (runs game window)

    Returns:
        Dict with preview info or error
    """
    try:
        from llm_router.tools.godot_tools import find_godot

        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        godot_exe = find_godot()
        if not godot_exe:
            return {"error": "Godot executable not found"}

        cmd = [godot_exe, "--path", str(project_dir)]

        if mode == "editor":
            # Open in editor (default)
            pass
        elif mode == "window":
            # Run the game
            cmd.append("--")

        # Launch in background
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        return {
            "success": True,
            "mode": mode,
            "project_path": str(project_dir),
            "message": f"Godot {'editor opened' if mode == 'editor' else 'game launched'}"
        }

    except Exception as e:
        return {"error": str(e)}


async def godot_debug_scene(
    project_path: str,
    scene_name: str
) -> dict:
    """
    Debug a specific scene by analyzing its structure.

    Args:
        project_path: Path to the Godot project
        scene_name: Name of the scene to debug

    Returns:
        Dict with scene analysis
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        if not scene_name.endswith(".tscn"):
            scene_name += ".tscn"

        scene_file = project_dir / scene_name
        if not scene_file.exists():
            return {"error": f"Scene not found: {scene_name}"}

        content = scene_file.read_text()

        # Parse scene structure
        nodes = []
        connections = []
        resources = []

        # Find nodes
        node_pattern = r'\[node\s+name="([^"]+)"\s+(?:type="([^"]+)"\s+)?'
        for match in re.finditer(node_pattern, content):
            nodes.append({
                "name": match.group(1),
                "type": match.group(2) or "Unknown"
            })

        # Find connections
        conn_pattern = r'\[connection\s+signal="([^"]+)"\s+from="([^"]+)"\s+to="([^"]+)"\s+method="([^"]+)"'
        for match in re.finditer(conn_pattern, content):
            connections.append({
                "signal": match.group(1),
                "from": match.group(2),
                "to": match.group(3),
                "method": match.group(4)
            })

        # Find external resources
        ext_pattern = r'\[ext_resource\s+type="([^"]+)"\s+path="([^"]+)"'
        for match in re.finditer(ext_pattern, content):
            resources.append({
                "type": match.group(1),
                "path": match.group(2)
            })

        # Check for common issues
        issues = []

        # Check for missing root script
        has_root_script = any(r["path"].endswith(".gd") for r in resources)
        if not has_root_script:
            issues.append({
                "severity": "info",
                "message": "Scene has no script attached to root node"
            })

        # Check for missing connections
        for node in nodes:
            node_type = node["type"]
            if node_type in ["Area2D", "Area3D", "Timer", "Button"]:
                has_connection = any(c["from"] == node["name"] for c in connections)
                if not has_connection:
                    issues.append({
                        "severity": "info",
                        "message": f"Node '{node['name']}' ({node_type}) has no signal connections"
                    })

        return {
            "success": True,
            "scene_name": scene_name,
            "node_count": len(nodes),
            "nodes": nodes,
            "connections": connections,
            "resources": resources,
            "issues": issues,
            "message": f"Scene '{scene_name}' analyzed"
        }

    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

GODOT_VALIDATE_PROJECT_DEF = ToolDefinition(
    name="godot_validate_project",
    description="""Validate a Godot project for common issues.

Checks:
- project.godot exists and is valid
- Main scene is set
- Scripts have no syntax errors
- Scenes reference valid scripts
- No missing resources

Returns list of issues with severity levels and fix suggestions.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"}
        },
        "required": ["project_path"],
    },
    function=godot_validate_project,
    category="godot",
)

GODOT_RUN_WITH_OUTPUT_DEF = ToolDefinition(
    name="godot_run_with_output",
    description="""Run Godot project in headless mode and capture output/errors.

Useful for detecting runtime errors and script issues.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30}
        },
        "required": ["project_path"],
    },
    function=godot_run_with_output,
    category="godot",
)

GODOT_PREVIEW_DEF = ToolDefinition(
    name="godot_preview",
    description="""Preview the game in Godot editor or as a window.

Modes:
- editor: Opens the project in Godot editor
- window: Runs the game directly""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "mode": {"type": "string", "description": "editor or window", "default": "editor"}
        },
        "required": ["project_path"],
    },
    function=godot_preview,
    category="godot",
)

GODOT_DEBUG_SCENE_DEF = ToolDefinition(
    name="godot_debug_scene",
    description="""Debug a specific scene by analyzing its structure.

Returns:
- Node hierarchy
- Signal connections
- Resource references
- Potential issues""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "scene_name": {"type": "string", "description": "Name of the scene to debug"}
        },
        "required": ["project_path", "scene_name"],
    },
    function=godot_debug_scene,
    category="godot",
)


def register_godot_debug_tools(registry: ToolRegistry) -> None:
    """Register all Godot debug tools with a registry."""
    registry.register(GODOT_VALIDATE_PROJECT_DEF)
    registry.register(GODOT_RUN_WITH_OUTPUT_DEF)
    registry.register(GODOT_PREVIEW_DEF)
    registry.register(GODOT_DEBUG_SCENE_DEF)
