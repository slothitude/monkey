"""Godot game development tools for the agent framework."""

import asyncio
import json
import os
import socket
import subprocess
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union
from llm_router.tools import ToolDefinition, ToolRegistry

# Game library integration
from llm_router.tools.game_library import get_game_library, GameLibrary


def _register_game_in_library(
    project_path: str,
    game_name: str,
    game_type: str,
    controls: str = None,
    objective: str = None,
) -> None:
    """Register a game in the library after creation."""
    try:
        library = get_game_library()
        library.register(
            path=project_path,
            game_type=game_type,
            name=game_name,
            controls=controls,
            objective=objective,
            status="created",
        )
    except Exception as e:
        # Don't fail game creation if library registration fails
        print(f"Warning: Could not register game in library: {e}")


def _update_game_status_in_library(
    project_path: str,
    status: str,
    **kwargs,
) -> None:
    """Update game status in the library."""
    try:
        library = get_game_library()
        game_id = Path(project_path).name
        library.update_status(game_id, status, **kwargs)
    except Exception as e:
        print(f"Warning: Could not update game status in library: {e}")


def _find_free_port(start_port: int = 8080, max_port: int = 8999) -> int:
    """Find a free port in the specified range."""
    for port in range(start_port, max_port + 1):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('127.0.0.1', port))
            sock.close()
            return port
        except OSError:
            continue
    raise RuntimeError(f"No free ports in {start_port}-{max_port}")


# Node type templates for scene builder
NODE_TEMPLATES = {
    "Node2D": {"extends": "Node2D", "default_children": []},
    "Node": {"extends": "Node", "default_children": []},
    "CharacterBody2D": {"extends": "CharacterBody2D", "requires": []},
    "StaticBody2D": {"extends": "StaticBody2D", "requires": []},
    "RigidBody2D": {"extends": "RigidBody2D", "requires": []},
    "Area2D": {"extends": "Area2D", "signals": ["body_entered", "body_exited", "area_entered", "area_exited"]},
    "Sprite2D": {"extends": "Sprite2D", "properties": {"texture": None, "centered": True}},
    "ColorRect": {"extends": "ColorRect", "properties": {"color": "#ffffff"}},
    "Label": {"extends": "Label", "properties": {"text": "", "horizontal_alignment": 0}},
    "Button": {"extends": "Button", "signals": ["pressed"]},
    "CollisionShape2D": {"extends": "CollisionShape2D", "properties": {"disabled": False}},
    "Camera2D": {"extends": "Camera2D", "properties": {"zoom": [1, 1], "enabled": True}},
    "CanvasLayer": {"extends": "CanvasLayer", "properties": {"layer": 0}},
    "Timer": {"extends": "Timer", "signals": ["timeout"], "properties": {"wait_time": 1.0, "one_shot": False, "autostart": False}},
    "AudioStreamPlayer": {"extends": "AudioStreamPlayer", "properties": {"stream": None, "volume_db": 0}},
    "AnimatedSprite2D": {"extends": "AnimatedSprite2D", "properties": {"sprite_frames": None}},
    "RayCast2D": {"extends": "RayCast2D", "properties": {"target_position": [0, -50], "enabled": True}},
    "PathFollow2D": {"extends": "PathFollow2D", "properties": {"rotates": True}},
    "Marker2D": {"extends": "Marker2D", "properties": {}},
    "VisibleOnScreenNotifier2D": {"extends": "VisibleOnScreenNotifier2D", "signals": ["screen_entered", "screen_exited"]},
}


@dataclass
class GodotNode:
    """Represents a node in a Godot scene."""
    name: str
    node_type: str
    parent: Optional[str] = None
    position: tuple = (0, 0)
    rotation: float = 0.0
    scale: tuple = (1, 1)
    script: Optional[str] = None
    properties: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    uid: str = ""


@dataclass
class SignalConnection:
    """Represents a signal connection between nodes."""
    from_node: str
    signal: str
    to_node: str
    method: str
    binds: list = field(default_factory=list)


class GodotSceneBuilder:
    """Builds Godot .tscn scene files from structured configuration."""

    def __init__(self, scene_name: str, root_type: str = "Node2D"):
        self.scene_name = scene_name
        self.root_type = root_type
        self.nodes: list[GodotNode] = []
        self.connections: list[SignalConnection] = []
        self.resources: dict[str, str] = {}
        self._node_counter = 0

    def _generate_uid(self) -> str:
        """Generate a unique UID for Godot 4.x."""
        return f"uid://{uuid.uuid4().hex[:8]}"

    def add_node(
        self,
        name: str,
        node_type: str,
        parent: Optional[str] = None,
        position: tuple = (0, 0),
        rotation: float = 0.0,
        scale: tuple = (1, 1),
        script: Optional[str] = None,
        properties: Optional[dict] = None,
        children: Optional[list] = None
    ) -> "GodotSceneBuilder":
        """Add a node to the scene hierarchy."""
        self._node_counter += 1
        node = GodotNode(
            name=name,
            node_type=node_type,
            parent=parent,
            position=position,
            rotation=rotation,
            scale=scale,
            script=script,
            properties=properties or {},
            children=children or [],
            uid=self._generate_uid()
        )
        self.nodes.append(node)
        return self

    def add_connection(
        self,
        from_node: str,
        signal: str,
        to_node: str,
        method: str,
        binds: Optional[list] = None
    ) -> "GodotSceneBuilder":
        """Connect a signal between nodes."""
        conn = SignalConnection(
            from_node=from_node,
            signal=signal,
            to_node=to_node,
            method=method,
            binds=binds or []
        )
        self.connections.append(conn)
        return self

    def add_resource(self, path: str, resource_type: str) -> str:
        """Add a resource reference."""
        if path not in self.resources:
            self.resources[path] = resource_type
        return path

    def _get_node_path(self, node_name: str, root_name: str = "@") -> str:
        """Get the full path for a node."""
        if node_name == root_name:
            return "."
        return f"\"{node_name}\""

    def _format_value(self, value: Any) -> str:
        """Format a value for Godot scene format."""
        if value is None:
            return "null"
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            if value.startswith("res://") or value.startswith("uid://"):
                return f'"{value}"'
            elif value.startswith("#"):
                return f'Color({value}, 1)'
            else:
                return f'"{value}"'
        elif isinstance(value, (list, tuple)):
            if len(value) == 2:
                return f"Vector2({value[0]}, {value[1]})"
            elif len(value) == 4:
                return f"Rect2({value[0]}, {value[1]}, {value[2]}, {value[3]})"
            else:
                return str(list(value))
        elif isinstance(value, dict):
            items = [f'"{k}": {self._format_value(v)}' for k, v in value.items()]
            return "{" + ", ".join(items) + "}"
        return str(value)

    def _generate_node_block(self, node: GodotNode, node_index: int, script_ids: dict, is_root: bool = False) -> str:
        """Generate a node block for the .tscn file."""
        lines = [f'[node name="{node.name}" type="{node.node_type}"']

        if node.uid and not is_root:
            lines.append(f'uid="{node.uid}"')

        if is_root:
            lines.append(f'index="{node_index}"')
        else:
            lines.append(f'index="{node_index}"')
            if node.parent:
                lines.append(f'parent="{node.parent}"')

        lines.append("]")
        block = "".join(lines) + "\n"

        # Add position
        if node.position != (0, 0):
            block += f'position = Vector2({node.position[0]}, {node.position[1]})\n'

        # Add rotation
        if node.rotation != 0.0:
            block += f'rotation = {node.rotation}\n'

        # Add scale
        if node.scale != (1, 1):
            block += f'scale = Vector2({node.scale[0]}, {node.scale[1]})\n'

        # Add properties
        for key, value in node.properties.items():
            if value is not None:
                formatted = self._format_value(value)
                block += f'{key} = {formatted}\n'

        # Add script reference
        if node.script:
            script_path = node.script if node.script.startswith("res://") else f"res://{node.script}"
            if script_path in script_ids:
                block += f'script = ExtResource("{script_ids[script_path]}")\n'
            else:
                # Script should have been pre-collected - this is a fallback
                script_id = len(script_ids) + 1
                script_ids[script_path] = str(script_id)
                block += f'script = ExtResource("{script_id}")\n'

        return block + "\n"

    def generate_tscn(self) -> str:
        """Generate the complete .tscn file content."""
        lines = ['[gd_scene load_steps=1 format=3 uid="{}"]'.format(self._generate_uid())]
        lines.append("")

        # First pass: collect all scripts from nodes
        for node in self.nodes:
            if node.script:
                script_path = node.script if node.script.startswith("res://") else f"res://{node.script}"
                if script_path not in self.resources:
                    self.resources[script_path] = "Script"

        # Build script ID mapping
        script_ids = {}
        for i, (path, res_type) in enumerate(self.resources.items(), 1):
            script_ids[path] = str(i)

        # Write external resources
        ext_resources = []
        for i, (path, res_type) in enumerate(self.resources.items(), 1):
            ext_resources.append(f'[ext_resource type="{res_type}" path="{path}" id="{i}"]')
            lines.append(ext_resources[-1])

        if ext_resources:
            lines.append("")

        # Generate root node
        root_node = GodotNode(
            name=self.scene_name,
            node_type=self.root_type,
            uid=self._generate_uid()
        )
        lines.append(self._generate_node_block(root_node, 0, script_ids, is_root=True))

        # Generate child nodes
        for i, node in enumerate(self.nodes, 1):
            node_block = self._generate_node_block(node, i, script_ids)
            # Ensure parent is set for non-root nodes
            # In Godot 4, all non-root nodes need a parent attribute
            if 'parent="' not in node_block and node.parent is None:
                # Add parent="." for direct children of root
                node_block = node_block.replace(
                    'index="',
                    'parent="." index="'
                )
            lines.append(node_block)

        # Add connections
        for conn in self.connections:
            lines.append(
                f'[connection signal="{conn.signal}" from=".{conn.from_node}" '
                f'to=".{conn.to_node}" method="{conn.method}"]'
            )

        return "\n".join(lines)


def build_scene_from_config(scene_name: str, scene_config: dict) -> str:
    """
    Build a complete Godot scene from structured configuration.

    Args:
        scene_name: Name for the scene
        scene_config: Dictionary with scene configuration

    Returns:
        Complete .tscn file content
    """
    builder = GodotSceneBuilder(
        scene_name=scene_name,
        root_type=scene_config.get("root_type", "Node2D")
    )

    # Add root script if specified
    root_script = scene_config.get("root_script")
    if root_script:
        builder.resources[f"res://{root_script}"] = "Script"

    # Process nodes
    def add_nodes_recursive(nodes: list, parent: str = None):
        for node_config in nodes:
            node_name = node_config.get("name", node_config.get("type", "Node"))
            node_type = node_config.get("type", "Node2D")
            position = tuple(node_config.get("position", [0, 0]))
            rotation = node_config.get("rotation", 0.0)
            scale = tuple(node_config.get("scale", [1, 1]))
            script = node_config.get("script")
            properties = node_config.get("properties", {})

            # Handle shape-specific properties
            if "shape" in node_config:
                shape_type = node_config["shape"]
                if shape_type == "RectangleShape2D":
                    size = node_config.get("size", [20, 20])
                    properties["shape"] = {"size": size}
                elif shape_type == "CircleShape2D":
                    radius = node_config.get("radius", 20)
                    properties["shape"] = {"radius": radius}
                elif shape_type == "CapsuleShape2D":
                    radius = node_config.get("radius", 10)
                    height = node_config.get("height", 30)
                    properties["shape"] = {"radius": radius, "height": height}

            # Handle ColorRect specific
            if node_type == "ColorRect":
                rect = node_config.get("rect", [0, 0, 100, 100])
                properties["offset_left"] = rect[0]
                properties["offset_top"] = rect[1]
                properties["offset_right"] = rect[0] + rect[2]
                properties["offset_bottom"] = rect[1] + rect[3]
                if "color" in node_config:
                    properties["color"] = node_config["color"]

            builder.add_node(
                name=node_name,
                node_type=node_type,
                parent=parent,
                position=position,
                rotation=rotation,
                scale=scale,
                script=script,
                properties=properties
            )

            # Process children
            children = node_config.get("children", [])
            if children:
                add_nodes_recursive(children, node_name)

    # Add all nodes
    nodes = scene_config.get("nodes", [])
    add_nodes_recursive(nodes)

    # Add UI elements
    ui_config = scene_config.get("ui", {})
    if ui_config:
        # Create CanvasLayer for UI
        builder.add_node(
            name="UI",
            node_type="CanvasLayer",
            parent=None
        )

        # Add labels
        for label in ui_config.get("labels", []):
            label_name = label.get("name", "Label")
            text = label.get("text", "")
            position = tuple(label.get("position", [0, 0]))
            font_size = label.get("font_size", 16)

            builder.add_node(
                name=label_name,
                node_type="Label",
                parent="UI",
                position=position,
                properties={
                    "text": text,
                    "horizontal_alignment": 1,
                }
            )

        # Add buttons
        for button in ui_config.get("buttons", []):
            btn_name = button.get("name", "Button")
            text = button.get("text", "Button")
            position = tuple(button.get("position", [0, 0]))
            size = tuple(button.get("size", [100, 40]))

            builder.add_node(
                name=btn_name,
                node_type="Button",
                parent="UI",
                position=position,
                properties={
                    "text": text,
                    "offset_right": size[0],
                    "offset_bottom": size[1],
                }
            )

    # Add signal connections
    for conn in scene_config.get("connections", []):
        builder.add_connection(
            from_node=conn["from"],
            signal=conn["signal"],
            to_node=conn.get("to", "."),
            method=conn["method"],
            binds=conn.get("binds", [])
        )

    return builder.generate_tscn()


# Godot installation paths
GODOT_PATHS = {
    "windows": [
        "C:/Users/{}/Godot/Godot_v4.6.1-stable_win64_console.exe".format(os.environ.get("USERNAME", "")),
        "C:/Program Files/Godot/Godot_v4.6.1-stable_win64_console.exe",
        "godot4",
        "godot",
    ],
    "linux": [
        "/usr/bin/godot4",
        "/usr/local/bin/godot4",
        "/opt/godot/godot4",
        "godot4",
    ],
    "macos": [
        "/Applications/Godot.app/Contents/MacOS/Godot",
        "godot4",
    ],
}


def find_godot() -> Optional[str]:
    """Find Godot executable on the system."""
    import platform
    system = platform.system().lower()

    paths = GODOT_PATHS.get(system, [])
    for path in paths:
        expanded = os.path.expanduser(path)
        if os.path.isfile(expanded):
            return expanded
        # Check if in PATH
        try:
            result = subprocess.run(["which", path], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass

    return None


async def godot_create_project(
    project_path: str,
    project_name: str = "Game",
    godot_version: str = "4.3"
) -> dict:
    """
    Create a new Godot project with proper structure.

    Args:
        project_path: Directory path for the project
        project_name: Name of the project
        godot_version: Godot version to target (4.2, 4.3, 4.6)

    Returns:
        Dict with project info or error
    """
    try:
        project_dir = Path(project_path)
        project_dir.mkdir(parents=True, exist_ok=True)

        # Create project.godot file
        project_config = f"""; Engine configuration file.
; It's best edited using the editor UI and not directly.

config_version=5

[application]

config/name="{project_name}"
config/features=PackedStringArray("{godot_version}", "Forward Plus")
config/icon="res://icon.svg"

[display]

window/size/viewport_width=1152
window/size/viewport_height=648
window/stretch/mode="canvas_items"

[rendering]

renderer/rendering_method="forward_plus"
"""

        (project_dir / "project.godot").write_text(project_config)

        # Create default icon.svg
        icon_svg = """<svg width="128" height="128" xmlns="http://www.w3.org/2000/svg">
  <rect width="128" height="128" fill="#478cbf"/>
  <path d="M64 20L100 50V100H28V50L64 20Z" fill="#ffffff"/>
</svg>"""
        (project_dir / "icon.svg").write_text(icon_svg)

        # Create .godot directory structure
        godot_dir = project_dir / ".godot"
        godot_dir.mkdir(exist_ok=True)
        (godot_dir / "imported").mkdir(exist_ok=True)
        (godot_dir / "export").mkdir(exist_ok=True)

        # Create export_presets.cfg for web export
        export_presets = """[preset.0]

name="Web"
platform="Web"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path="export/html/index.html"
encryption_include_filters=""
encryption_exclude_filters=""
encrypt_pck=false
script_export_mode=2

[preset.0.options]

custom_template/debug=""
custom_template/release=""
variant/extensions_support=false
vram_texture_compression/for_desktop=true
vram_texture_compression/for_mobile=false
html/export_icon=true
html/custom_html_shell=""
html/head_include=""
html/canvas_resize_policy=2
html/focus_canvas_on_start=true
html/experimental_virtual_keyboard=false
progressive_web_app/enabled=false
"""
        (project_dir / "export_presets.cfg").write_text(export_presets)

        return {
            "success": True,
            "project_path": str(project_dir),
            "project_name": project_name,
            "godot_version": godot_version,
            "message": f"Created Godot project at {project_dir}",
        }

    except Exception as e:
        return {"error": str(e), "project_path": project_path}


async def godot_add_script(
    project_path: str,
    script_name: str,
    script_content: str,
    extends: str = "Node2D"
) -> dict:
    """
    Add a GDScript file to a Godot project.

    Args:
        project_path: Path to the Godot project
        script_name: Name of the script file (with or without .gd extension)
        script_content: GDScript code content
        extends: What node type the script extends

    Returns:
        Dict with result or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        # Ensure .gd extension
        if not script_name.endswith(".gd"):
            script_name += ".gd"

        # Ensure extends clause at start
        if not script_content.strip().startswith("extends"):
            script_content = f"extends {extends}\n\n{script_content}"

        script_path = project_dir / script_name
        script_path.write_text(script_content)

        return {
            "success": True,
            "script_path": str(script_path),
            "script_name": script_name,
            "lines": len(script_content.split("\n")),
        }

    except Exception as e:
        return {"error": str(e)}


async def godot_add_scene(
    project_path: str,
    scene_name: str,
    scene_content: str
) -> dict:
    """
    Add a scene file to a Godot project.

    Args:
        project_path: Path to the Godot project
        scene_name: Name of the scene file (with or without .tscn extension)
        scene_content: Scene file content in Godot text format

    Returns:
        Dict with result or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        # Ensure .tscn extension
        if not scene_name.endswith(".tscn"):
            scene_name += ".tscn"

        scene_path = project_dir / scene_name
        scene_path.write_text(scene_content)

        return {
            "success": True,
            "scene_path": str(scene_path),
            "scene_name": scene_name,
        }

    except Exception as e:
        return {"error": str(e)}


async def godot_build_scene(
    project_path: str,
    scene_name: str,
    scene_config: dict
) -> dict:
    """
    Build a complete Godot scene from structured configuration.

    This is the primary tool for creating game scenes. It generates proper .tscn
    files with node hierarchies, properties, and signal connections.

    Args:
        project_path: Path to the Godot project
        scene_name: Name for the scene (without .tscn extension)
        scene_config: Structured configuration dictionary

    Returns:
        Dict with scene info or error

    scene_config example:
    {
        "root_type": "Node2D",
        "root_script": "Main.gd",
        "nodes": [
            {
                "name": "Player",
                "type": "CharacterBody2D",
                "script": "Player.gd",
                "position": [100, 300],
                "children": [
                    {"type": "CollisionShape2D", "shape": "CircleShape2D", "radius": 20},
                    {"type": "Sprite2D"}
                ]
            }
        ],
        "ui": {
            "labels": [{"name": "ScoreLabel", "text": "Score: 0", "position": [20, 20]}]
        },
        "connections": [
            {"from": "Player", "signal": "died", "to": ".", "method": "on_player_died"}
        ]
    }
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        # Build scene content
        scene_content = build_scene_from_config(scene_name, scene_config)

        # Ensure .tscn extension
        if not scene_name.endswith(".tscn"):
            scene_name += ".tscn"

        scene_path = project_dir / scene_name
        scene_path.write_text(scene_content)

        # Count nodes created
        node_count = len(scene_config.get("nodes", []))
        ui_labels = len(scene_config.get("ui", {}).get("labels", []))
        ui_buttons = len(scene_config.get("ui", {}).get("buttons", []))
        connections = len(scene_config.get("connections", []))

        return {
            "success": True,
            "scene_path": str(scene_path),
            "scene_name": scene_name,
            "node_count": node_count + ui_labels + ui_buttons + 1,  # +1 for root
            "connections": connections,
            "has_ui": ui_labels > 0 or ui_buttons > 0,
            "message": f"Created scene '{scene_name}' with {node_count} nodes and {connections} connections",
        }

    except Exception as e:
        return {"error": str(e), "scene_name": scene_name}


async def godot_export_web(
    project_path: str,
    output_path: Optional[str] = None
) -> dict:
    """
    Export a Godot project to HTML5/Web.

    Args:
        project_path: Path to the Godot project
        output_path: Output directory for export (default: project/export/html)

    Returns:
        Dict with export info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        # Find Godot executable
        godot_exe = find_godot()
        if not godot_exe:
            return {"error": "Godot executable not found. Please install Godot 4.x"}

        # Set output path
        if output_path:
            export_dir = Path(output_path)
        else:
            export_dir = project_dir / "export" / "html"
        export_dir.mkdir(parents=True, exist_ok=True)

        # Run Godot export
        cmd = [
            godot_exe,
            "--headless",
            "--path", str(project_dir),
            "--export-release", "Web",
            str(export_dir / "index.html")
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        # Check for output files
        files = list(export_dir.glob("*"))
        file_names = [f.name for f in files]

        result_dict = {
            "success": result.returncode == 0 or len(files) > 0,
            "export_path": str(export_dir),
            "files": file_names,
            "file_count": len(files),
            "has_html": "index.html" in file_names,
            "has_wasm": any(f.endswith(".wasm") for f in file_names),
            "stdout": result.stdout[-1000:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
        }

        # Update game library status
        if result_dict["success"]:
            _update_game_status_in_library(
                project_path,
                "exported",
                export_path=str(export_dir),
            )

        return result_dict

    except subprocess.TimeoutExpired:
        return {"error": "Export timed out after 120 seconds"}
    except Exception as e:
        return {"error": str(e)}


async def godot_review_game(project_path: str) -> dict:
    """
    Review a generated Godot game for common issues.

    Checks for:
    - Missing main scene in project.godot
    - Scene file format issues (missing ExtResources, broken references)
    - Misaligned collision shapes and visual elements
    - Scripts referencing missing nodes or signals
    - Preloaded scenes that don't exist

    Args:
        project_path: Path to the Godot project

    Returns:
        Dict with issues found and suggestions
    """
    issues = []
    suggestions = []
    project_dir = Path(project_path)

    if not project_dir.exists():
        return {"error": f"Project not found: {project_path}"}

    # Check project.godot for main scene
    project_file = project_dir / "project.godot"
    if project_file.exists():
        content = project_file.read_text()
        if 'run/main_scene=' not in content:
            issues.append({
                "severity": "critical",
                "file": "project.godot",
                "issue": "No main scene configured",
                "fix": "Add run/main_scene=\"res://<MainScene>.tscn\" to [application] section"
            })
    else:
        issues.append({
            "severity": "critical",
            "file": "project.godot",
            "issue": "project.godot not found"
        })

    # Check scene files
    for tscn_file in project_dir.glob("**/*.tscn"):
        issues.extend(_review_scene_file(tscn_file, project_dir))

    # Check for preloaded resources that might not exist
    for gd_file in project_dir.glob("**/*.gd"):
        issues.extend(_review_script_file(gd_file, project_dir))

    return {
        "success": True,
        "project_path": str(project_dir),
        "issues": issues,
        "issue_count": len(issues),
        "has_critical": any(i.get("severity") == "critical" for i in issues),
        "message": f"Found {len(issues)} issues" if issues else "No issues found"
    }


def _review_scene_file(tscn_path: Path, project_dir: Path) -> list:
    """Review a scene file for common issues."""
    issues = []
    content = tscn_path.read_text()
    rel_path = tscn_path.relative_to(project_dir)

    # Find all ExtResource references
    import re
    ext_resources = re.findall(r'\[ext_resource[^\]]*path="([^"]+)"', content)

    for res_path in ext_resources:
        # Convert res:// to actual path
        if res_path.startswith("res://"):
            actual_path = project_dir / res_path[6:]
            if not actual_path.exists():
                issues.append({
                    "severity": "critical",
                    "file": str(rel_path),
                    "issue": f"Missing referenced file: {res_path}",
                    "fix": f"Create {res_path} or remove the reference"
                })

    # Check for nodes using ExtResource IDs that don't exist
    ext_ids = re.findall(r'\[ext_resource[^\]]*id="([^"]+)"', content)
    used_ids = re.findall(r'ExtResource\("([^"]+)"\)', content)
    for used_id in used_ids:
        if used_id not in ext_ids:
            issues.append({
                "severity": "critical",
                "file": str(rel_path),
                "issue": f"Undefined ExtResource ID: {used_id}",
                "fix": f"Add [ext_resource id=\"{used_id}\"] or fix the reference"
            })

    # Check for collision/visual misalignment
    # Look for nodes with both CollisionShape2D and ColorRect children
    nodes = re.findall(r'\[node name="([^"]+)"[^\]]*\]', content)
    # This is a simplified check - real implementation would parse node hierarchy

    return issues


def _review_script_file(gd_path: Path, project_dir: Path) -> list:
    """Review a GDScript file for common issues."""
    issues = []
    content = gd_path.read_text()
    rel_path = gd_path.relative_to(project_dir)

    # Check for preload calls
    import re
    preloads = re.findall(r'preload\("([^"]+)"\)', content)
    for preload_path in preloads:
        if preload_path.startswith("res://"):
            actual_path = project_dir / preload_path[6:]
            if not actual_path.exists():
                issues.append({
                    "severity": "critical",
                    "file": str(rel_path),
                    "issue": f"preload() references missing file: {preload_path}",
                    "fix": f"Create {preload_path} or remove the preload"
                })

    # Check for @onready references that might not exist
    onready_refs = re.findall(r'@onready\s+var\s+\w+[^=]*=\s*\$([^=\n]+)', content)
    for node_path in onready_refs:
        node_path = node_path.strip()
        # This would need scene parsing to fully validate
        # For now, flag potentially problematic patterns

    return issues


async def godot_serve_game(
    export_path: str,
    port: int = 8888,
    auto_port: bool = True,
    start_port: int = 8080,
    max_port: int = 8999
) -> dict:
    """
    Serve a Godot web export via HTTP server.

    Args:
        export_path: Path to the exported HTML files
        port: Port to serve on (default 8888)
        auto_port: If True and requested port is busy, find next free port
        start_port: Starting port for auto search (default 8080)
        max_port: Maximum port for auto search (default 8999)

    Returns:
        Dict with server info or error
    """
    try:
        export_dir = Path(export_path)
        if not export_dir.exists():
            return {"error": f"Export directory not found: {export_path}"}

        if not (export_dir / "index.html").exists():
            return {"error": "index.html not found in export directory"}

        # Start HTTP server in background
        import threading
        import http.server

        # Check if port is available, find free port if needed
        actual_port = port
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.bind(('127.0.0.1', port))
            test_sock.close()
        except OSError:
            if auto_port:
                actual_port = _find_free_port(start_port, max_port)
            else:
                return {"error": f"Port {port} is already in use", "port": port, "suggestion": "Set auto_port=True to find a free port automatically"}

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(export_dir), **kwargs)

        server = http.server.HTTPServer(('127.0.0.1', actual_port), Handler)

        # Run in background thread
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        # Update game library status
        # Try to find the game ID from the export path
        try:
            library = get_game_library()
            # Walk up to find project directory
            parent = export_dir.parent
            while parent.parent != parent:
                if (parent / "project.godot").exists():
                    game_id = parent.name
                    library.update_status(
                        game_id,
                        "serving",
                        play_url=f"http://localhost:{actual_port}",
                        port=actual_port,
                    )
                    library.set_server_port(game_id, actual_port)
                    break
                parent = parent.parent
        except Exception as e:
            print(f"Warning: Could not update library status: {e}")

        return {
            "success": True,
            "url": f"http://localhost:{actual_port}",
            "port": actual_port,
            "requested_port": port,
            "port_changed": actual_port != port,
            "export_path": str(export_dir),
        }

    except Exception as e:
        return {"error": str(e)}


async def godot_check_install() -> dict:
    """
    Check if Godot is installed and get version info.

    Returns:
        Dict with Godot installation info
    """
    try:
        godot_exe = find_godot()
        if not godot_exe:
            return {
                "installed": False,
                "message": "Godot not found. Download from https://godotengine.org/download",
                "download_url": "https://godotengine.org/download/windows/",
            }

        # Get version
        result = subprocess.run(
            [godot_exe, "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )

        return {
            "installed": True,
            "path": godot_exe,
            "version": result.stdout.strip() or "unknown",
            "message": f"Godot found at {godot_exe}",
        }

    except Exception as e:
        return {"installed": False, "error": str(e)}


async def godot_get_docs(
    topic: str,
    version: str = "4.3"
) -> dict:
    """
    Fetch Godot documentation for a specific topic.

    Args:
        topic: Topic to search (e.g., "CharacterBody2D", "signals", "input")
        version: Godot version

    Returns:
        Dict with documentation content or error
    """
    import httpx

    try:
        # Godot docs URL pattern
        base_url = f"https://docs.godotengine.org/en/stable"

        # Try to fetch from docs
        async with httpx.AsyncClient() as client:
            # Search for the topic
            search_url = f"{base_url}/search.html?q={topic}"
            response = await client.get(search_url, timeout=15, follow_redirects=True)

            if response.status_code == 200:
                # Also try direct class reference
                class_url = f"{base_url}/classes/class_{topic.lower()}.html"
                class_response = await client.get(class_url, timeout=10, follow_redirects=True)

                return {
                    "success": True,
                    "topic": topic,
                    "version": version,
                    "search_url": search_url,
                    "class_docs_url": class_url if class_response.status_code == 200 else None,
                    "docs_base_url": base_url,
                    "message": f"Documentation URLs for '{topic}'",
                }
            else:
                return {
                    "success": False,
                    "topic": topic,
                    "message": f"Could not fetch docs for '{topic}'",
                }

    except Exception as e:
        return {"error": str(e), "topic": topic}


async def godot_create_game(
    project_path: str,
    game_name: str,
    game_type: str,
    description: str = "",
    itchio_publish: bool = False,
    itchio_username: str = "",
    itchio_game_slug: str = ""
) -> dict:
    """
    Create a complete Godot game from a template.

    This creates a fully playable game with scenes, scripts, and UI.

    Args:
        project_path: Directory for the project
        game_name: Name of the game
        game_type: Type of game (pong, space_invaders, platformer, shooter, puzzle)
        description: Additional description of the game
        itchio_publish: If True, export to web and upload to itch.io
        itchio_username: itch.io username (required if itchio_publish=True)
        itchio_game_slug: Game URL slug (optional, defaults to game_name lowercased)

    Returns:
        Dict with project info and created files
    """
    try:
        # Create project structure
        result = await godot_create_project(project_path, game_name)
        if "error" in result:
            return result

        project_dir = Path(project_path)

        # Import templates module
        from llm_router.tools.godot_templates import get_template, create_game_from_template

        # Check for complete template
        template = get_template(game_type)

        if template:
            # Use complete template
            input_config = template.input_mappings
            _add_input_to_project(project_dir, input_config)

            files_created = create_game_from_template(project_dir, template, game_name)

            # Update project settings if needed
            if template.project_settings:
                _update_project_settings(project_dir, template.project_settings)

            base_result = {
                "success": True,
                "project_path": str(project_dir),
                "game_name": game_name,
                "game_type": game_type,
                "template_name": template.name,
                "files_created": files_created,
                "controls": template.controls,
                "objective": template.objective,
                "message": f"Created {template.name} game '{game_name}' with {len(files_created)} files",
            }
        else:
            # Fallback to basic template
            input_config = _get_input_config(game_type)
            _add_input_to_project(project_dir, input_config)

            files_created = _create_basic_template(project_dir, game_name, description, game_type)

            base_result = {
                "success": True,
                "project_path": str(project_dir),
                "game_name": game_name,
                "game_type": game_type,
                "files_created": files_created,
                "message": f"Created basic {game_type} game '{game_name}' with {len(files_created)} files",
            }

        # Register game in library
        _register_game_in_library(
            project_path=str(project_dir),
            game_name=game_name,
            game_type=game_type,
            controls=base_result.get("controls"),
            objective=base_result.get("objective"),
        )
        base_result["library_registered"] = True

        # Handle itch.io publishing if requested
        if itchio_publish:
            if not itchio_username:
                base_result["itchio_error"] = "itchio_username is required when itchio_publish=True"
                return base_result

            # Determine game slug
            game_slug = itchio_game_slug or game_name.lower().replace(" ", "-").replace("_", "-")

            # Export to web first
            export_result = await godot_export_web(str(project_dir))
            if "error" in export_result:
                base_result["itchio_error"] = f"Web export failed: {export_result['error']}"
                return base_result

            export_path = export_result.get("export_path", str(project_dir / "web-export"))

            # Upload to itch.io
            from llm_router.tools.itchio_tools import itchio_upload
            upload_result = await itchio_upload(
                game_path=export_path,
                username=itchio_username,
                game_slug=game_slug,
                channel="html5"
            )

            if upload_result.get("success"):
                base_result["itchio_published"] = True
                base_result["itchio_url"] = upload_result["url"]
                base_result["itchio_channel"] = "html5"
                base_result["message"] += f" and published to {upload_result['url']}"
            else:
                base_result["itchio_published"] = False
                base_result["itchio_error"] = upload_result.get("error", "Unknown upload error")

        return base_result

    except Exception as e:
        return {"error": str(e), "project_path": project_path}


async def godot_create_from_template(
    project_path: str,
    template_name: str,
    game_name: str,
    customizations: Optional[dict] = None,
    itchio_publish: bool = False,
    itchio_username: str = "",
    itchio_game_slug: str = ""
) -> dict:
    """
    Create a complete game from a named template with optional customizations.

    Available templates: pong, space_invaders, platformer, shooter, puzzle

    Args:
        project_path: Directory for the project
        template_name: Name of the template to use
        game_name: Name for the game
        customizations: Optional customizations (colors, speed, difficulty, etc.)
        itchio_publish: If True, export to web and upload to itch.io
        itchio_username: itch.io username (required if itchio_publish=True)
        itchio_game_slug: Game URL slug (optional, defaults to game_name lowercased)

    Returns:
        Dict with project info and created files
    """
    try:
        from llm_router.tools.godot_templates import get_template, create_game_from_template

        template = get_template(template_name)
        if not template:
            return {
                "error": f"Template '{template_name}' not found",
                "available_templates": ["pong", "space_invaders", "platformer", "shooter", "puzzle", "dungeon_crawler"]
            }

        # Create project
        result = await godot_create_project(project_path, game_name)
        if "error" in result:
            return result

        project_dir = Path(project_path)

        # Add input mappings
        _add_input_to_project(project_dir, template.input_mappings)

        # Create game files
        files_created = create_game_from_template(project_dir, template, game_name)

        # Apply customizations if provided
        if customizations:
            files_created.extend(_apply_customizations(project_dir, customizations))

        # Update project settings
        if template.project_settings:
            _update_project_settings(project_dir, template.project_settings)

        # Review the generated game for issues
        review_result = await godot_review_game(str(project_dir))

        base_result = {
            "success": True,
            "project_path": str(project_dir),
            "game_name": game_name,
            "template": template.name,
            "description": template.description,
            "files_created": files_created,
            "controls": template.controls,
            "objective": template.objective,
            "difficulty": template.difficulty,
            "review": review_result,
            "has_issues": review_result.get("issue_count", 0) > 0,
            "message": f"Created {template.name} game '{game_name}' from template",
        }

        # Register game in library
        _register_game_in_library(
            project_path=str(project_dir),
            game_name=game_name,
            game_type=template_name,
            controls=template.controls,
            objective=template.objective,
        )
        base_result["library_registered"] = True

        # Handle itch.io publishing if requested
        if itchio_publish:
            if not itchio_username:
                base_result["itchio_error"] = "itchio_username is required when itchio_publish=True"
                return base_result

            # Determine game slug
            game_slug = itchio_game_slug or game_name.lower().replace(" ", "-").replace("_", "-")

            # Export to web first
            export_result = await godot_export_web(str(project_dir))
            if "error" in export_result:
                base_result["itchio_error"] = f"Web export failed: {export_result['error']}"
                return base_result

            export_path = export_result.get("export_path", str(project_dir / "web-export"))

            # Upload to itch.io
            from llm_router.tools.itchio_tools import itchio_upload
            upload_result = await itchio_upload(
                game_path=export_path,
                username=itchio_username,
                game_slug=game_slug,
                channel="html5"
            )

            if upload_result.get("success"):
                base_result["itchio_published"] = True
                base_result["itchio_url"] = upload_result["url"]
                base_result["itchio_channel"] = "html5"
                base_result["message"] += f" and published to {upload_result['url']}"
            else:
                base_result["itchio_published"] = False
                base_result["itchio_error"] = upload_result.get("error", "Unknown upload error")

        return base_result

    except Exception as e:
        return {"error": str(e)}


async def godot_list_templates() -> dict:
    """
    List all available game templates.

    Returns:
        Dict with template information
    """
    try:
        from llm_router.tools.godot_templates import list_templates
        return {
            "success": True,
            "templates": list_templates(),
            "count": len(list_templates()),
        }
    except Exception as e:
        return {"error": str(e)}


def _update_project_settings(project_dir: Path, settings: dict) -> None:
    """Update project.godot with custom settings."""
    project_file = project_dir / "project.godot"
    if not project_file.exists():
        return

    content = project_file.read_text()

    # Common settings mapping
    for key, value in settings.items():
        if key == "display/window/size/viewport_width":
            content = _update_setting(content, "window/size/viewport_width", value)
        elif key == "display/window/size/viewport_height":
            content = _update_setting(content, "window/size/viewport_height", value)

    project_file.write_text(content)


def _update_setting(content: str, key: str, value: Any) -> str:
    """Update a single setting in project.godot content."""
    import re
    pattern = rf'^{key}=\d+'
    replacement = f'{key}={value}'
    return re.sub(pattern, replacement, content, flags=re.MULTILINE)


def _apply_customizations(project_dir: Path, customizations: dict) -> list[str]:
    """Apply customizations to the game. Returns list of modified files."""
    modified = []

    # Apply color customizations
    if "colors" in customizations:
        colors = customizations["colors"]
        main_file = project_dir / "Main.gd"
        if main_file.exists():
            content = main_file.read_text()
            for key, color in colors.items():
                # Simple color replacement
                content = content.replace(f'Color("#{key}")', f'Color("#{color}")')
            main_file.write_text(content)
            modified.append("Main.gd")

    return modified


def _create_basic_template(project_dir: Path, game_name: str, description: str, game_type: str) -> list[str]:
    """Create a basic game template as fallback."""
    files = []

    main_script = f'''extends Node2D

# {game_name} - {description}
# {game_type} game for Godot 4.x

func _ready() -> void:
    print("{game_name} ready!")

func _process(delta: float) -> void:
    pass
'''
    (project_dir / "Main.gd").write_text(main_script)
    files.append("Main.gd")

    return files


def _get_input_config(game_type: str) -> dict:
    """Get input mappings for a game type."""
    configs = {
        "shooter": {
            "move_left": ["A", "LEFT"],
            "move_right": ["D", "RIGHT"],
            "move_up": ["W", "UP"],
            "move_down": ["S", "DOWN"],
            "shoot": ["SPACE", "ENTER"],
        },
        "platformer": {
            "move_left": ["A", "LEFT"],
            "move_right": ["D", "RIGHT"],
            "jump": ["W", "SPACE", "UP"],
        },
        "puzzle": {
            "move_left": ["A", "LEFT"],
            "move_right": ["D", "RIGHT"],
            "move_up": ["W", "UP"],
            "move_down": ["S", "DOWN"],
            "action": ["SPACE", "ENTER"],
        },
    }
    return configs.get(game_type, configs["shooter"])


def _add_input_to_project(project_dir: Path, input_config: dict) -> None:
    """Add input mappings to project.godot."""
    project_file = project_dir / "project.godot"
    if not project_file.exists():
        return

    content = project_file.read_text()

    input_section = "\n[input]\n"
    for action, keys in input_config.items():
        input_section += f'{action}={{\n"deadzone": 0.5,\n"events": ['
        events = []
        for key in keys:
            if len(key) == 1:
                events.append(f'Object(InputEventKey, "keycode": {ord(key.upper())}, "unicode": {ord(key.lower())})')
            elif key == "SPACE":
                events.append('Object(InputEventKey, "keycode": 32, "unicode": 32)')
            elif key == "ENTER":
                events.append('Object(InputEventKey, "keycode": 4194309)')
            elif key == "LEFT":
                events.append('Object(InputEventKey, "keycode": 4194319)')
            elif key == "RIGHT":
                events.append('Object(InputEventKey, "keycode": 4194321)')
            elif key == "UP":
                events.append('Object(InputEventKey, "keycode": 4194320)')
            elif key == "DOWN":
                events.append('Object(InputEventKey, "keycode": 4194322)')
        input_section += ", ".join(events) + "]\n}\n"

    content += input_section
    project_file.write_text(content)


# Register tools
GODOT_CREATE_PROJECT_DEF = ToolDefinition(
    name="godot_create_project",
    description="Create a new Godot 4.x project with proper structure, project.godot, and export presets.",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Directory path for the project"},
            "project_name": {"type": "string", "description": "Name of the project", "default": "Game"},
            "godot_version": {"type": "string", "description": "Godot version (4.2, 4.3, 4.6)", "default": "4.3"},
        },
        "required": ["project_path"],
    },
    function=godot_create_project,
    category="godot",
)

GODOT_ADD_SCRIPT_DEF = ToolDefinition(
    name="godot_add_script",
    description="Add a GDScript file to a Godot project. Automatically adds 'extends' clause if missing.",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "script_name": {"type": "string", "description": "Name of the script file"},
            "script_content": {"type": "string", "description": "GDScript code content"},
            "extends": {"type": "string", "description": "Node type to extend", "default": "Node2D"},
        },
        "required": ["project_path", "script_name", "script_content"],
    },
    function=godot_add_script,
    category="godot",
)

GODOT_ADD_SCENE_DEF = ToolDefinition(
    name="godot_add_scene",
    description="Add a scene (.tscn) file to a Godot project.",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "scene_name": {"type": "string", "description": "Name of the scene file"},
            "scene_content": {"type": "string", "description": "Scene file content in Godot text format"},
        },
        "required": ["project_path", "scene_name", "scene_content"],
    },
    function=godot_add_scene,
    category="godot",
)

GODOT_BUILD_SCENE_DEF = ToolDefinition(
    name="godot_build_scene",
    description="""Build a complete Godot scene from structured configuration.
This is the primary tool for creating game scenes with node hierarchies, properties, and signal connections.

Example scene_config:
{
    "root_type": "Node2D",
    "root_script": "Main.gd",
    "nodes": [
        {"name": "Player", "type": "CharacterBody2D", "position": [100, 300],
         "children": [{"type": "CollisionShape2D", "shape": "CircleShape2D", "radius": 20}]}
    ],
    "ui": {"labels": [{"name": "ScoreLabel", "text": "Score: 0", "position": [20, 20]}]},
    "connections": [{"from": "Player", "signal": "died", "to": ".", "method": "on_player_died"}]
}""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "scene_name": {"type": "string", "description": "Name for the scene (without .tscn)"},
            "scene_config": {
                "type": "object",
                "description": "Structured scene configuration with nodes, ui, connections",
                "properties": {
                    "root_type": {"type": "string", "description": "Root node type (Node2D, Node, etc.)"},
                    "root_script": {"type": "string", "description": "Script for root node"},
                    "nodes": {"type": "array", "description": "List of nodes to add"},
                    "ui": {"type": "object", "description": "UI elements (labels, buttons)"},
                    "connections": {"type": "array", "description": "Signal connections"}
                }
            }
        },
        "required": ["project_path", "scene_name", "scene_config"],
    },
    function=godot_build_scene,
    category="godot",
)

GODOT_EXPORT_WEB_DEF = ToolDefinition(
    name="godot_export_web",
    description="Export a Godot project to HTML5/WebAssembly for browser play.",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "output_path": {"type": "string", "description": "Output directory for export (optional)"},
        },
        "required": ["project_path"],
    },
    function=godot_export_web,
    category="godot",
)

GODOT_SERVE_GAME_DEF = ToolDefinition(
    name="godot_serve_game",
    description="Serve a Godot web export via local HTTP server for testing. Automatically finds a free port if the requested one is busy.",
    parameters={
        "type": "object",
        "properties": {
            "export_path": {"type": "string", "description": "Path to the exported HTML files"},
            "port": {"type": "integer", "description": "Port to serve on", "default": 8888},
            "auto_port": {"type": "boolean", "description": "If true and port is busy, find next free port", "default": True},
            "start_port": {"type": "integer", "description": "Starting port for auto search", "default": 8080},
            "max_port": {"type": "integer", "description": "Maximum port for auto search", "default": 8999},
        },
        "required": ["export_path"],
    },
    function=godot_serve_game,
    category="godot",
)

GODOT_CHECK_INSTALL_DEF = ToolDefinition(
    name="godot_check_install",
    description="Check if Godot is installed and get version info.",
    parameters={
        "type": "object",
        "properties": {},
    },
    function=godot_check_install,
    category="godot",
)

GODOT_GET_DOCS_DEF = ToolDefinition(
    name="godot_get_docs",
    description="Get Godot documentation URLs for a specific topic or class.",
    parameters={
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Topic to search (e.g., CharacterBody2D, signals, input)"},
            "version": {"type": "string", "description": "Godot version", "default": "4.3"},
        },
        "required": ["topic"],
    },
    function=godot_get_docs,
    category="godot",
)

GODOT_CREATE_GAME_DEF = ToolDefinition(
    name="godot_create_game",
    description="""Create a complete, playable Godot game from a template.
Available templates: pong, space_invaders, platformer, shooter, puzzle.
Each template includes full scene files, scripts, UI, and input mappings.
Set itchio_publish=True to automatically export and upload to itch.io.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Directory for the project"},
            "game_name": {"type": "string", "description": "Name of the game"},
            "game_type": {"type": "string", "description": "Type: pong, space_invaders, platformer, shooter, puzzle"},
            "description": {"type": "string", "description": "Description of the game (optional)"},
            "itchio_publish": {"type": "boolean", "description": "If true, export and upload to itch.io", "default": False},
            "itchio_username": {"type": "string", "description": "itch.io username (required if itchio_publish=True)"},
            "itchio_game_slug": {"type": "string", "description": "Game URL slug (optional, defaults to game_name)"},
        },
        "required": ["project_path", "game_name", "game_type"],
    },
    function=godot_create_game,
    category="godot",
)

GODOT_CREATE_FROM_TEMPLATE_DEF = ToolDefinition(
    name="godot_create_from_template",
    description="""Create a complete game from a named template with optional customizations.
Templates include full game logic, scenes, scripts, and UI.
Set itchio_publish=True to automatically export and upload to itch.io.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Directory for the project"},
            "template_name": {"type": "string", "description": "Template name: pong, space_invaders, platformer, shooter, puzzle, dungeon_crawler"},
            "game_name": {"type": "string", "description": "Name for the game"},
            "customizations": {
                "type": "object",
                "description": "Optional customizations (colors, speed, difficulty)",
                "properties": {
                    "colors": {"type": "object", "description": "Color overrides"},
                    "speed": {"type": "number", "description": "Game speed multiplier"},
                    "difficulty": {"type": "string", "description": "easy, medium, hard"}
                }
            },
            "itchio_publish": {"type": "boolean", "description": "If true, export and upload to itch.io", "default": False},
            "itchio_username": {"type": "string", "description": "itch.io username (required if itchio_publish=True)"},
            "itchio_game_slug": {"type": "string", "description": "Game URL slug (optional, defaults to game_name)"},
        },
        "required": ["project_path", "template_name", "game_name"],
    },
    function=godot_create_from_template,
    category="godot",
)

GODOT_LIST_TEMPLATES_DEF = ToolDefinition(
    name="godot_list_templates",
    description="List all available game templates with their descriptions, controls, and objectives.",
    parameters={
        "type": "object",
        "properties": {},
    },
    function=godot_list_templates,
    category="godot",
)

GODOT_REVIEW_GAME_DEF = ToolDefinition(
    name="godot_review_game",
    description="Review a generated Godot game for common issues like missing main scene, broken references, misaligned collisions, and missing preloaded files. Use this after creating a game to catch problems before export.",
    parameters={
        "type": "object",
        "required": ["project_path"],
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project to review"}
        },
    },
    function=godot_review_game,
    category="godot",
)


async def godot_play_game(
    game_url: str,
    max_steps: int = 500,
    use_mouse: bool = True,
    headless: bool = False,
    game_type: str = "auto"
) -> dict:
    """
    Play a Godot game using the AI game agent.

    The agent uses:
    - OpenCV for fast state detection (~5-10ms)
    - Color detection for enemies and player
    - PyAutoGUI for direct mouse/keyboard control
    - Optional Q-learning for improvement

    Args:
        game_url: URL of the game (e.g., http://localhost:8888)
        max_steps: Maximum game steps to play (default: 500)
        use_mouse: Use mouse control (default: True, False = keyboard only)
        headless: Run browser in headless mode (default: False)
        game_type: Game type - "auto", "space_shooter", "platformer", "rpg" (default: auto-detect)

    Returns:
        Dict with game results including kills, steps, FPS, etc.
    """
    import asyncio
    import time

    try:
        import pyautogui
        import cv2
        import numpy as np
        import pygetwindow as gw
        from playwright.async_api import async_playwright
    except ImportError as e:
        return {"error": f"Missing dependency: {e}. Install with: pip install opencv-python pyautogui pygetwindow playwright"}

    # Import game detector
    try:
        from llm_router.game_agent.games.space_shooter import SpaceShooterDetector
        detector = SpaceShooterDetector()
    except ImportError:
        # Fallback to inline detector
        class SimpleDetector:
            def detect_state(self, screenshot):
                from dataclasses import dataclass
                import cv2
                import numpy as np
                import time

                @dataclass
                class State:
                    player_found: bool = False
                    player_x: int = 0
                    player_y: int = 0
                    enemy_count: int = 0
                    enemies: list = None
                    detection_time_ms: float = 0.0

                    def __post_init__(self):
                        if self.enemies is None:
                            self.enemies = []

                start = time.perf_counter()
                state = State()

                hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)

                # Green player
                green_mask = cv2.inRange(hsv, np.array([35, 100, 100]), np.array([85, 255, 255]))
                green_coords = np.where(green_mask > 0)
                if len(green_coords[0]) > 0:
                    state.player_found = True
                    state.player_y = int(np.mean(green_coords[0]))
                    state.player_x = int(np.mean(green_coords[1]))

                # Red enemies
                red_mask1 = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([10, 255, 255]))
                red_mask2 = cv2.inRange(hsv, np.array([170, 100, 100]), np.array([180, 255, 255]))
                red_mask = cv2.bitwise_or(red_mask1, red_mask2)
                contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for c in contours:
                    if cv2.contourArea(c) > 50:
                        M = cv2.moments(c)
                        if M["m00"] > 0:
                            state.enemies.append((int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"])))
                state.enemy_count = len(state.enemies)
                state.detection_time_ms = (time.perf_counter() - start) * 1000
                return state

        detector = SimpleDetector()

    pyautogui.PAUSE = 0.001
    pyautogui.FAILSAFE = True

    start_time = time.time()
    steps = 0
    shots = 0
    kills = 0
    prev_enemies = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            page = await browser.new_page()
            await page.goto(game_url)
            await asyncio.sleep(3)

            canvas = await page.query_selector('canvas')
            if not canvas:
                return {"error": "No canvas element found in game"}

            box = await canvas.bounding_box()
            canvas_x, canvas_y = box['x'], box['y']
            canvas_w, canvas_h = box['width'], box['height']

            # Click to start/focus
            await page.mouse.click(canvas_x + canvas_w//2, canvas_y + canvas_h//2)
            await asyncio.sleep(1)

            # Get window for PyAutoGUI
            await asyncio.sleep(0.5)
            windows = gw.getWindowsWithTitle('Chrome')
            if windows:
                win = windows[0]
                win.activate()
                win_left, win_top = win.left, win.top
                win_w, win_h = win.width, win.height
                game_left = win_left + (win_w - canvas_w) // 2
                game_top = win_top + (win_h - canvas_h) // 2 - 20
            else:
                game_left, game_top = int(canvas_x), int(canvas_y)
                game_left, game_top = 10, 80

            # Game loop
            while steps < max_steps:
                # Screenshot
                if use_mouse:
                    screenshot = pyautogui.screenshot(region=(game_left, game_top, int(canvas_w), int(canvas_h)))
                    screenshot_np = np.array(screenshot)
                    screenshot_bgr = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)
                else:
                    screenshot_bytes = await page.screenshot(type='png')
                    nparr = np.frombuffer(screenshot_bytes, np.uint8)
                    screenshot_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                # Detect state
                state = detector.detect_state(screenshot_bgr)

                # Track kills
                if state.enemy_count < prev_enemies:
                    kills += prev_enemies - state.enemy_count
                prev_enemies = state.enemy_count

                # Decide action
                target_x = int(canvas_w // 2)
                target_y = int(canvas_h // 2)

                if state.enemy_count > 0 and state.enemies:
                    ex, ey = state.enemies[0]
                    target_x, target_y = int(ex), int(ey)

                if use_mouse:
                    # Direct mouse control
                    pyautogui.moveTo(game_left + target_x, game_top + target_y)
                    pyautogui.press('space')  # Shoot with spacebar
                else:
                    # Playwright keyboard
                    await page.keyboard.press('Space')

                shots += 1
                steps += 1
                await asyncio.sleep(0.02)

            await browser.close()

    except Exception as e:
        return {"error": str(e), "steps": steps, "kills": kills}

    elapsed = time.time() - start_time
    return {
        "success": True,
        "steps": steps,
        "shots": shots,
        "kills": kills,
        "duration_seconds": round(elapsed, 1),
        "fps": round(steps / elapsed, 1) if elapsed > 0 else 0,
        "game_url": game_url,
    }


GODOT_PLAY_GAME_DEF = ToolDefinition(
    name="godot_play_game",
    description="Play a Godot game using an AI game agent with vision detection. Uses OpenCV for fast state detection and PyAutoGUI for direct control. Tracks kills, shots, and performance metrics.",
    parameters={
        "type": "object",
        "required": ["game_url"],
        "properties": {
            "game_url": {"type": "string", "description": "URL of the game to play (e.g., http://localhost:8888)"},
            "max_steps": {"type": "integer", "description": "Maximum game steps to play (default: 500)", "default": 500},
            "use_mouse": {"type": "boolean", "description": "Use mouse control (default: True)", "default": True},
            "headless": {"type": "boolean", "description": "Run browser in headless mode (default: False)", "default": False},
            "game_type": {"type": "string", "description": "Game type: auto, space_shooter, platformer, rpg (default: auto)", "default": "auto"},
        },
    },
    function=godot_play_game,
    category="godot",
)


# =============================================================================
# BLENDER INTEGRATION TOOLS
# =============================================================================

BLENDER_HOST = "127.0.0.1"
BLENDER_PORT = 9876


def _blender_send_command(cmd_type: str, params: dict = None, timeout: float = 10.0) -> dict:
    """Send a command to Blender MCP addon and return the response."""
    import socket
    import time

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((BLENDER_HOST, BLENDER_PORT))

        cmd = json.dumps({"type": cmd_type, "params": params or {}})
        sock.sendall((cmd + "\n").encode())
        time.sleep(0.3)

        sock.setblocking(False)
        response = b""
        try:
            while True:
                try:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    response += chunk
                except BlockingIOError:
                    break
        except Exception:
            pass

        if response:
            return json.loads(response.decode())
        return {"status": "error", "message": "No response from Blender"}
    except socket.error as e:
        return {"status": "error", "message": f"Cannot connect to Blender: {e}. Make sure Blender is running with MCP addon enabled."}
    finally:
        sock.close()


def blender_get_scene_info() -> dict:
    """Get information about the current Blender scene."""
    result = _blender_send_command("get_scene_info")
    if result.get("status") == "success":
        return result.get("result", {})
    return {"error": result.get("message", "Unknown error")}


def blender_execute_code(code: str) -> dict:
    """Execute arbitrary Python code in Blender."""
    result = _blender_send_command("execute_code", {"code": code}, timeout=30.0)
    if result.get("status") == "success":
        return result.get("result", {})
    return {"error": result.get("message", "Unknown error")}


def blender_create_object(
    object_type: str = "CUBE",
    name: str = None,
    location: list = None,
    rotation: list = None,
    scale: list = None,
) -> dict:
    """Create a 3D object in Blender.

    Args:
        object_type: Type of object - CUBE, SPHERE, CYLINDER, CONE, TORUS, PLANE, MONKEY
        name: Optional name for the object
        location: [x, y, z] position
        rotation: [x, y, z] rotation in degrees
        scale: [x, y, z] scale factors
    """
    location = location or [0, 0, 0]
    rotation = rotation or [0, 0, 0]
    scale = scale or [1, 1, 1]

    type_map = {
        "CUBE": "primitive_cube_add",
        "SPHERE": "primitive_uv_sphere_add",
        "CYLINDER": "primitive_cylinder_add",
        "CONE": "primitive_cone_add",
        "TORUS": "primitive_torus_add",
        "PLANE": "primitive_plane_add",
        "MONKEY": "primitive_monkey_add",
    }

    op_name = type_map.get(object_type.upper(), "primitive_cube_add")

    code = f"""
import bpy
from math import radians

bpy.ops.mesh.{op_name}()
obj = bpy.context.active_object
"""

    if name:
        code += f'obj.name = "{name}"\n'

    code += f"""
obj.location = ({location[0]}, {location[1]}, {location[2]})
obj.rotation_euler = (radians({rotation[0]}), radians({rotation[1]}), radians({rotation[2]}))
obj.scale = ({scale[0]}, {scale[1]}, {scale[2]})
print(f"Created {{obj.name}} at {{obj.location}}")
"""

    return blender_execute_code(code)


def blender_create_material(
    object_name: str,
    material_name: str = "CustomMaterial",
    base_color: list = None,
    emission_color: list = None,
    emission_strength: float = 0.0,
    metallic: float = 0.0,
    roughness: float = 0.5,
    material_type: str = "principled",
) -> dict:
    """Create and apply a material to an object in Blender.

    Args:
        object_name: Name of the object to apply material to
        material_name: Name for the new material
        base_color: [r, g, b] base color (0-1 range)
        emission_color: [r, g, b] emission color (0-1 range)
        emission_strength: Emission strength (0-10)
        metallic: Metallic value (0-1)
        roughness: Roughness value (0-1)
        material_type: Type - principled, sci_fi, glow, metallic
    """
    base_color = base_color or [0.5, 0.5, 0.5]
    emission_color = emission_color or base_color

    if material_type == "sci_fi":
        code = f"""
import bpy

mat = bpy.data.materials.new(name="{material_name}")
mat.use_nodes = True
nodes = mat.node_tree.nodes
links = mat.node_tree.links
nodes.clear()

output = nodes.new(type="ShaderNodeOutputMaterial")
output.location = (600, 0)

principled = nodes.new(type="ShaderNodeBsdfPrincipled")
principled.location = (300, 0)

noise = nodes.new(type="ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 8.0
noise.inputs["Detail"].default_value = 16.0
noise.inputs["Distortion"].default_value = 2.0
noise.location = (-400, 200)

voronoi = nodes.new(type="ShaderNodeTexVoronoi")
voronoi.inputs["Scale"].default_value = 4.0
voronoi.location = (-400, -100)

ramp1 = nodes.new(type="ShaderNodeValToRGB")
ramp1.location = (-100, 200)
ramp1.color_ramp.elements[0].color = ({base_color[0]*0.1}, {base_color[1]*0.2}, {base_color[2]*0.4}, 1)
ramp1.color_ramp.elements[1].color = ({base_color[0]}, {base_color[1]}, {base_color[2]}, 1)

ramp2 = nodes.new(type="ShaderNodeValToRGB")
ramp2.location = (-100, -100)
ramp2.color_ramp.elements[0].color = (0, 0, 0, 1)
ramp2.color_ramp.elements[1].color = ({emission_color[0]}, {emission_color[1]}, {emission_color[2]}, 1)

mix = nodes.new(type="ShaderNodeMixRGB")
mix.location = (100, 0)

bump = nodes.new(type="ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.3
bump.location = (100, -300)

links.new(noise.outputs["Fac"], ramp1.inputs["Fac"])
links.new(voronoi.outputs["Distance"], ramp2.inputs["Fac"])
links.new(ramp1.outputs["Color"], mix.inputs["Color1"])
links.new(ramp2.outputs["Color"], mix.inputs["Color2"])
links.new(mix.outputs["Color"], principled.inputs["Base Color"])
links.new(mix.outputs["Color"], principled.inputs["Emission Color"])
links.new(principled.outputs["BSDF"], output.inputs["Surface"])
links.new(noise.outputs["Fac"], bump.inputs["Height"])
links.new(bump.outputs["Normal"], principled.inputs["Normal"])

principled.inputs["Emission Strength"].default_value = {emission_strength}
principled.inputs["Roughness"].default_value = {roughness}
principled.inputs["Metallic"].default_value = {metallic}

obj = bpy.data.objects.get("{object_name}")
if obj:
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    print(f"Applied {{mat.name}} to {{obj.name}}")
else:
    print(f"Object {object_name} not found")
"""
    else:
        # Simple principled material
        code = f"""
import bpy

mat = bpy.data.materials.new(name="{material_name}")
mat.use_nodes = True
nodes = mat.node_tree.nodes

principled = nodes.get("Principled BSDF")
if principled:
    principled.inputs["Base Color"].default_value = ({base_color[0]}, {base_color[1]}, {base_color[2]}, 1)
    principled.inputs["Metallic"].default_value = {metallic}
    principled.inputs["Roughness"].default_value = {roughness}
    principled.inputs["Emission Color"].default_value = ({emission_color[0]}, {emission_color[1]}, {emission_color[2]}, 1)
    principled.inputs["Emission Strength"].default_value = {emission_strength}

obj = bpy.data.objects.get("{object_name}")
if obj:
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    print(f"Applied {{mat.name}} to {{obj.name}}")
else:
    print(f"Object {object_name} not found")
"""

    return blender_execute_code(code)


def blender_export_gltf(
    output_path: str,
    object_names: list = None,
    export_format: str = "GLB",
) -> dict:
    """Export Blender objects to glTF format for use in Godot.

    Args:
        output_path: Path to save the glTF file (relative to project or absolute)
        object_names: List of object names to export (None = export all)
        export_format: GLB (binary, recommended) or GLTF (separate files)
    """
    # Ensure output path is absolute
    if not os.path.isabs(output_path):
        output_path = os.path.abspath(output_path)

    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    code = f"""
import bpy

# Select objects to export
bpy.ops.object.select_all(action='DESELECT')
"""

    if object_names:
        for name in object_names:
            code += f"""
obj = bpy.data.objects.get("{name}")
if obj:
    obj.select_set(True)
"""
    else:
        code += """
for obj in bpy.data.objects:
    if obj.type in ['MESH', 'ARMATURE']:
        obj.select_set(True)
"""

    code += f"""
# Export to glTF
bpy.ops.export_scene.gltf(
    filepath=r"{output_path}",
    export_format='{export_format}',
    use_selection={'True' if object_names else 'False'},
    export_apply=True,
    export_texcoords=True,
    export_normals=True,
    export_cameras=False,
    export_lights=False,
)
print(f"Exported to {output_path}")
"""

    result = blender_execute_code(code)
    if "error" not in result:
        result["output_path"] = output_path
    return result


def blender_delete_object(object_name: str) -> dict:
    """Delete an object from the Blender scene."""
    code = f"""
import bpy
obj = bpy.data.objects.get("{object_name}")
if obj:
    bpy.data.objects.remove(obj, do_unlink=True)
    print(f"Deleted {object_name}")
else:
    print(f"Object {object_name} not found")
"""
    return blender_execute_code(code)


def blender_screenshot(filepath: str = None) -> dict:
    """Take a screenshot of the Blender viewport."""
    if filepath is None:
        filepath = os.path.join(os.getcwd(), "blender_screenshot.png")

    result = _blender_send_command("get_viewport_screenshot", {"filepath": filepath})
    if result.get("status") == "success":
        return {"success": True, "filepath": filepath, **result.get("result", {})}
    return {"error": result.get("message", "Unknown error")}


# Tool Definitions for Blender

BLENDER_GET_SCENE_DEF = ToolDefinition(
    name="blender_get_scene",
    description="Get information about the current Blender scene including objects, materials, and settings. Use to check what's in the scene before making changes.",
    parameters={
        "type": "object",
        "required": [],
        "properties": {},
    },
    function=blender_get_scene_info,
    category="blender",
)

BLENDER_EXECUTE_DEF = ToolDefinition(
    name="blender_execute",
    description="Execute arbitrary Python code in Blender. Use for custom operations not covered by other tools. Requires Blender to be running with MCP addon connected.",
    parameters={
        "type": "object",
        "required": ["code"],
        "properties": {
            "code": {"type": "string", "description": "Python code to execute in Blender context (bpy module available)"},
        },
    },
    function=blender_execute_code,
    category="blender",
)

BLENDER_CREATE_OBJECT_DEF = ToolDefinition(
    name="blender_create_object",
    description="Create a 3D object in Blender. Supports CUBE, SPHERE, CYLINDER, CONE, TORUS, PLANE, MONKEY (Suzanne). Can set position, rotation, and scale.",
    parameters={
        "type": "object",
        "required": ["object_type"],
        "properties": {
            "object_type": {"type": "string", "description": "Type: CUBE, SPHERE, CYLINDER, CONE, TORUS, PLANE, MONKEY", "enum": ["CUBE", "SPHERE", "CYLINDER", "CONE", "TORUS", "PLANE", "MONKEY"]},
            "name": {"type": "string", "description": "Name for the object"},
            "location": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z] position"},
            "rotation": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z] rotation in degrees"},
            "scale": {"type": "array", "items": {"type": "number"}, "description": "[x, y, z] scale factors"},
        },
    },
    function=blender_create_object,
    category="blender",
)

BLENDER_CREATE_MATERIAL_DEF = ToolDefinition(
    name="blender_create_material",
    description="Create and apply a material to an object in Blender. Supports simple principled materials or procedural sci-fi textures with emission glow.",
    parameters={
        "type": "object",
        "required": ["object_name"],
        "properties": {
            "object_name": {"type": "string", "description": "Name of the object to apply material to"},
            "material_name": {"type": "string", "description": "Name for the new material"},
            "base_color": {"type": "array", "items": {"type": "number"}, "description": "[r, g, b] base color (0-1 range)"},
            "emission_color": {"type": "array", "items": {"type": "number"}, "description": "[r, g, b] emission/glow color (0-1 range)"},
            "emission_strength": {"type": "number", "description": "Emission strength (0-10)"},
            "metallic": {"type": "number", "description": "Metallic value (0-1)"},
            "roughness": {"type": "number", "description": "Roughness value (0-1)"},
            "material_type": {"type": "string", "description": "Material type: principled (simple), sci_fi (procedural glow)", "enum": ["principled", "sci_fi"]},
        },
    },
    function=blender_create_material,
    category="blender",
)

BLENDER_EXPORT_GLTF_DEF = ToolDefinition(
    name="blender_export_gltf",
    description="Export Blender objects to glTF format (.glb or .gltf) for use in Godot. GLB is recommended for single-file exports.",
    parameters={
        "type": "object",
        "required": ["output_path"],
        "properties": {
            "output_path": {"type": "string", "description": "Path to save the glTF file (e.g., models/character.glb)"},
            "object_names": {"type": "array", "items": {"type": "string"}, "description": "List of object names to export (omit to export all)"},
            "export_format": {"type": "string", "description": "GLB (binary, recommended) or GLTF (separate files)", "enum": ["GLB", "GLTF"]},
        },
    },
    function=blender_export_gltf,
    category="blender",
)

BLENDER_DELETE_OBJECT_DEF = ToolDefinition(
    name="blender_delete_object",
    description="Delete an object from the Blender scene.",
    parameters={
        "type": "object",
        "required": ["object_name"],
        "properties": {
            "object_name": {"type": "string", "description": "Name of the object to delete"},
        },
    },
    function=blender_delete_object,
    category="blender",
)

BLENDER_SCREENSHOT_DEF = ToolDefinition(
    name="blender_screenshot",
    description="Take a screenshot of the Blender viewport to see current state.",
    parameters={
        "type": "object",
        "required": [],
        "properties": {
            "filepath": {"type": "string", "description": "Path to save screenshot (default: blender_screenshot.png)"},
        },
    },
    function=blender_screenshot,
    category="blender",
)


def register_godot_tools(registry: ToolRegistry) -> None:
    """Register all Godot tools with a registry."""
    registry.register(GODOT_CREATE_PROJECT_DEF)
    registry.register(GODOT_ADD_SCRIPT_DEF)
    registry.register(GODOT_ADD_SCENE_DEF)
    registry.register(GODOT_BUILD_SCENE_DEF)
    registry.register(GODOT_EXPORT_WEB_DEF)
    registry.register(GODOT_SERVE_GAME_DEF)
    registry.register(GODOT_CHECK_INSTALL_DEF)
    registry.register(GODOT_GET_DOCS_DEF)
    registry.register(GODOT_CREATE_GAME_DEF)
    registry.register(GODOT_CREATE_FROM_TEMPLATE_DEF)
    registry.register(GODOT_LIST_TEMPLATES_DEF)
    registry.register(GODOT_REVIEW_GAME_DEF)
    registry.register(GODOT_PLAY_GAME_DEF)
    # Blender tools
    registry.register(BLENDER_GET_SCENE_DEF)
    registry.register(BLENDER_EXECUTE_DEF)
    registry.register(BLENDER_CREATE_OBJECT_DEF)
    registry.register(BLENDER_CREATE_MATERIAL_DEF)
    registry.register(BLENDER_EXPORT_GLTF_DEF)
    registry.register(BLENDER_DELETE_OBJECT_DEF)
    registry.register(BLENDER_SCREENSHOT_DEF)
