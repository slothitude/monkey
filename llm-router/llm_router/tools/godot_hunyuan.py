"""Hunyuan3D integration tools for Godot games.

Generate 3D assets and characters using a local Hunyuan3D server.
Uses Gradio API to communicate with the Hunyuan3D web interface.
"""

import asyncio
import base64
import os
import httpx
from pathlib import Path
from typing import Optional
from datetime import datetime

from llm_router.tools import ToolDefinition, ToolRegistry


# Default Hunyuan3D server URL (change if using different port)
HUNYUAN_API_URL = os.environ.get("HUNYUAN_API_URL", "http://192.168.0.18:8080")

# Default generation parameters
DEFAULT_OCTREE_RESOLUTION = 256
DEFAULT_INFERENCE_STEPS = 5
DEFAULT_GUIDANCE_SCALE = 5.0
DEFAULT_SEED = 1234
DEFAULT_NUM_CHUNKS = 8000


async def godot_generate_3d(
    project_path: str,
    asset_name: str,
    text_prompt: Optional[str] = None,
    image_path: Optional[str] = None,
    octree_resolution: int = DEFAULT_OCTREE_RESOLUTION,
    num_inference_steps: int = DEFAULT_INFERENCE_STEPS,
    guidance_scale: float = DEFAULT_GUIDANCE_SCALE,
    seed: int = DEFAULT_SEED,
    remove_background: bool = True,
) -> dict:
    """
    Generate a 3D model using Hunyuan3D and save it to a Godot project.

    Args:
        project_path: Path to the Godot project
        asset_name: Name for the generated asset (without .glb extension)
        text_prompt: Text description of the 3D model
        image_path: Optional path to reference image
        octree_resolution: Quality of generation (16-512, higher = better but slower)
        num_inference_steps: Number of inference steps (1-100)
        guidance_scale: Guidance scale for generation
        seed: Random seed for reproducibility
        remove_background: Whether to remove background from input image

    Returns:
        dict with status and path to generated file
    """
    # Validate inputs
    if not text_prompt and not image_path:
        return {"error": "Either text_prompt or image_path is required"}

    # Prepare project path
    project_dir = Path(project_path)
    if not project_dir.exists():
        return {"error": f"Project path does not exist: {project_path}"}

    # Create assets/models directory
    models_dir = project_dir / "assets" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    # Prepare Gradio API request
    # Endpoint: /shape_generation
    # Parameters: caption, image, mv_images (front/back/left/right), steps, guidance_scale,
    #             seed, octree_resolution, check_box_rembg, num_chunks, randomize_seed

    image_data = None
    if image_path:
        image_path = Path(image_path)
        if not image_path.exists():
            return {"error": f"Image file does not exist: {image_path}"}
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("ascii")
            image_data = {
                "path": str(image_path),
                "url": f"data:image/png;base64,{image_b64}",
                "meta": {"_type": "gradio.FileData"}
            }

    # Build the data array for Gradio API
    # Order: caption, image, mv_front, mv_back, mv_left, mv_right, steps, guidance_scale,
    #        seed, octree_resolution, rembg, num_chunks, randomize_seed
    data = [
        text_prompt,           # caption
        image_data,            # image
        None,                  # mv_image_front
        None,                  # mv_image_back
        None,                  # mv_image_left
        None,                  # mv_image_right
        num_inference_steps,   # steps
        guidance_scale,        # guidance_scale
        seed,                  # seed
        octree_resolution,     # octree_resolution
        remove_background,     # check_box_rembg
        DEFAULT_NUM_CHUNKS,    # num_chunks
        True,                  # randomize_seed
    ]

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            # Step 1: Call the shape_generation endpoint
            response = await client.post(
                f"{HUNYUAN_API_URL}/api/shape_generation",
                json={"data": data},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code != 200:
                return {
                    "error": f"Hunyuan3D generation failed: {response.status_code} - {response.text[:500]}"
                }

            result = response.json()

            # Gradio returns: {"data": [file_info, html_output, mesh_stats, seed]}
            if "data" not in result:
                return {"error": f"Unexpected response format: {result}"}

            file_info = result["data"][0]

            # Get the generated file path from the response
            if isinstance(file_info, dict) and "path" in file_info:
                glb_path = file_info["path"]

                # Download the generated .glb file
                file_url = f"{HUNYUAN_API_URL}/file={glb_path}"
                file_response = await client.get(file_url)

                if file_response.status_code != 200:
                    return {"error": f"Failed to download generated file: {file_response.status_code}"}

                glb_data = file_response.content
            elif isinstance(file_info, str):
                # Direct path string
                file_url = f"{HUNYUAN_API_URL}/file={file_info}"
                file_response = await client.get(file_url)

                if file_response.status_code != 200:
                    return {"error": f"Failed to download generated file: {file_response.status_code}"}

                glb_data = file_response.content
            else:
                return {"error": f"Unexpected file info format: {file_info}"}

    except httpx.ConnectError:
        return {
            "error": f"Cannot connect to Hunyuan3D server at {HUNYUAN_API_URL}. "
                    f"Make sure the server is running (e.g., RUN.bat in Hunyuan3D-2-WinPortable)"
        }
    except httpx.TimeoutException:
        return {"error": "Hunyuan3D generation timed out (took >10 minutes)"}
    except Exception as e:
        return {"error": f"Hunyuan3D request failed: {str(e)}"}

    # Save the .glb file
    asset_filename = f"{asset_name}.glb" if not asset_name.endswith(".glb") else asset_name
    output_path = models_dir / asset_filename

    with open(output_path, "wb") as f:
        f.write(glb_data)

    return {
        "success": True,
        "message": f"Generated 3D model: {asset_filename}",
        "path": str(output_path),
        "godot_path": f"res://assets/models/{asset_filename}",
        "asset_name": asset_name,
        "file_size_kb": len(glb_data) // 1024,
    }


async def godot_generate_character_3d(
    project_path: str,
    character_name: str,
    description: str,
    character_type: str = "npc",
    add_script: bool = True,
    octree_resolution: int = DEFAULT_OCTREE_RESOLUTION,
    texture: bool = False,
) -> dict:
    """
    Generate a game-ready 3D character with mesh and optional script.

    Creates:
    - 3D mesh (.glb) in assets/models/
    - Character scene (.tscn) in scenes/characters/
    - GDScript (.gd) in scripts/ (if add_script=True)

    Args:
        project_path: Path to the Godot project
        character_name: Name for the character
        description: Visual description for generation
        character_type: Type of character (player, enemy, npc)
        add_script: Whether to generate a placeholder script
        octree_resolution: Quality of generation (128-512)
        texture: Whether to generate texture

    Returns:
        dict with status and paths to generated files
    """
    project_dir = Path(project_path)
    if not project_dir.exists():
        return {"error": f"Project path does not exist: {project_path}"}

    # Generate the 3D model
    gen_result = await godot_generate_3d(
        project_path=project_path,
        asset_name=character_name,
        text_prompt=description,
        octree_resolution=octree_resolution,
        texture=texture,
    )

    if not gen_result.get("success"):
        return gen_result

    created_files = [gen_result["path"]]

    # Create character scene
    scenes_dir = project_dir / "scenes" / "characters"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    scene_path = scenes_dir / f"{character_name}.tscn"

    # Determine node type based on character_type
    node_type_map = {
        "player": "CharacterBody3D",
        "enemy": "CharacterBody3D",
        "npc": "StaticBody3D",
        "prop": "StaticBody3D",
    }
    node_type = node_type_map.get(character_type.lower(), "Node3D")

    scene_content = f'''[gd_scene load_steps=3 format=3 uid="uid_{hash(character_name) % 1000000:06x}"]

[ext_resource type="PackedScene" uid="uid_{hash(character_name) % 1000000:06x}" path="res://assets/models/{character_name}.glb" id="1_mesh"]
'''

    if add_script:
        scene_content += f'''[ext_resource type="Script" path="res://scripts/{character_name}.gd" id="2_script"]
'''

    scene_content += f'''
[sub_resource type="CapsuleShape3D" id="CapsuleShape3D_1"]
radius = 0.5
height = 2.0

[node name="{character_name}" type="{node_type}"']
'''
    if add_script:
        scene_content += f'script = ExtResource("2_script")\n'

    scene_content += f'''
[node name="Mesh" parent="." instance=ExtResource("1_mesh")]

[node name="CollisionShape3D" type="CollisionShape3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0.5, 0)
shape = SubResource("CapsuleShape3D_1")
'''

    with open(scene_path, "w") as f:
        f.write(scene_content)
    created_files.append(str(scene_path))

    # Create placeholder script if requested
    if add_script:
        scripts_dir = project_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        script_path = scripts_dir / f"{character_name}.gd"

        script_templates = {
            "player": f'''extends CharacterBody3D
## {character_name} - Player Controller

const SPEED = 5.0
const JUMP_VELOCITY = 4.5

var gravity = ProjectSettings.get_setting("physics/3d/default_gravity")

func _physics_process(delta):
	# Add gravity
	if not is_on_floor():
		velocity.y -= gravity * delta

	# Jump
	if Input.is_action_just_pressed("ui_accept") and is_on_floor():
		velocity.y = JUMP_VELOCITY

	# Movement
	var input_dir = Input.get_vector("ui_left", "ui_right", "ui_up", "ui_down")
	var direction = (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()
	if direction:
		velocity.x = direction.x * SPEED
		velocity.z = direction.y * SPEED
	else:
		velocity.x = move_toward(velocity.x, 0, SPEED)
		velocity.z = move_toward(velocity.z, 0, SPEED)

	move_and_slide()
''',
            "enemy": f'''extends CharacterBody3D
## {character_name} - Enemy AI

const SPEED = 3.0
var gravity = ProjectSettings.get_setting("physics/3d/default_gravity")

@export var patrol_points: Array[Vector3] = []
@export var detection_range: float = 10.0

var current_patrol_index: int = 0
var player: Node3D = null

func _ready():
	# Find player in scene
	player = get_tree().get_first_node_in_group("player")

func _physics_process(delta):
	if not is_on_floor():
		velocity.y -= gravity * delta

	# Simple patrol behavior
	if patrol_points.is_empty():
		velocity.x = 0
		velocity.z = 0
	else:
		var target = patrol_points[current_patrol_index]
		var direction = (target - global_position).normalized()
		velocity.x = direction.x * SPEED
		velocity.z = direction.z * SPEED

		if global_position.distance_to(target) < 1.0:
			current_patrol_index = (current_patrol_index + 1) % patrol_points.size()

	move_and_slide()
''',
            "npc": f'''extends StaticBody3D
## {character_name} - NPC/Static Character

@export var dialogue: Array[String] = ["Hello, traveler!"]
@export var interaction_prompt: String = "Talk"

var can_interact: bool = true

func interact():
	if dialogue.is_empty():
		return dialogue[0]
	return dialogue[randi() % dialogue.size()]
''',
        }

        script_content = script_templates.get(character_type.lower(), script_templates["npc"])
        script_content = script_content.replace("{character_name}", character_name)

        with open(script_path, "w") as f:
            f.write(script_content)
        created_files.append(str(script_path))

    return {
        "success": True,
        "message": f"Generated 3D character: {character_name}",
        "character_type": character_type,
        "mesh_path": gen_result["godot_path"],
        "scene_path": f"res://scenes/characters/{character_name}.tscn",
        "script_path": f"res://scripts/{character_name}.gd" if add_script else None,
        "created_files": created_files,
    }


async def godot_list_hunyuan_models(
    project_path: str,
) -> dict:
    """
    List all 3D models generated by Hunyuan3D in a Godot project.

    Args:
        project_path: Path to the Godot project

    Returns:
        dict with list of models and their details
    """
    project_dir = Path(project_path)
    models_dir = project_dir / "assets" / "models"

    if not models_dir.exists():
        return {
            "success": True,
            "models": [],
            "message": "No models directory found"
        }

    models = []
    for glb_file in models_dir.glob("*.glb"):
        stat = glb_file.stat()
        models.append({
            "name": glb_file.stem,
            "filename": glb_file.name,
            "path": str(glb_file),
            "godot_path": f"res://assets/models/{glb_file.name}",
            "size_kb": stat.st_size // 1024,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    return {
        "success": True,
        "models": sorted(models, key=lambda m: m["name"]),
        "count": len(models),
        "models_dir": str(models_dir),
    }


async def hunyuan_server_status() -> dict:
    """
    Check if the Hunyuan3D server is running and accessible.

    Returns:
        dict with server status
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Try a simple request to check if server is up
            response = await client.get(f"{HUNYUAN_API_URL}/")
            return {
                "running": True,
                "url": HUNYUAN_API_URL,
                "status_code": response.status_code,
                "message": "Hunyuan3D server is running"
            }
    except httpx.ConnectError:
        return {
            "running": False,
            "url": HUNYUAN_API_URL,
            "message": f"Cannot connect to Hunyuan3D server at {HUNYUAN_API_URL}. "
                      f"Start it with RUN.bat in Hunyuan3D-2-WinPortable"
        }
    except Exception as e:
        return {
            "running": False,
            "url": HUNYUAN_API_URL,
            "message": f"Error checking server: {str(e)}"
        }


def register_godot_hunyuan_tools(registry: ToolRegistry) -> None:
    """Register Hunyuan3D tools for Godot."""

    registry.register(ToolDefinition(
        name="godot_generate_3d",
        description="Generate a 3D model using Hunyuan3D and save it to a Godot project. "
                   "Requires a running Hunyuan3D server (192.168.0.18:8080).",
        parameters={
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Path to the Godot project"
                },
                "asset_name": {
                    "type": "string",
                    "description": "Name for the generated asset (without .glb extension)"
                },
                "text_prompt": {
                    "type": "string",
                    "description": "Text description of the 3D model to generate"
                },
                "image_path": {
                    "type": "string",
                    "description": "Optional path to reference image for image-to-3D"
                },
                "octree_resolution": {
                    "type": "integer",
                    "description": "Quality of generation (128-512, higher = better)",
                    "default": 256
                },
                "texture": {
                    "type": "boolean",
                    "description": "Whether to generate texture",
                    "default": False
                }
            },
            "required": ["project_path", "asset_name"]
        },
        function=godot_generate_3d,
        category="godot_3d",
        examples=[
            'godot_generate_3d(project_path="./my_game", asset_name="robot", text_prompt="a sci-fi robot soldier")',
            'godot_generate_3d(project_path="./my_game", asset_name="tree", text_prompt="a stylized low-poly tree")'
        ]
    ))

    registry.register(ToolDefinition(
        name="godot_generate_character_3d",
        description="Generate a game-ready 3D character with mesh, scene, and script. "
                   "Creates a complete character setup for Godot.",
        parameters={
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Path to the Godot project"
                },
                "character_name": {
                    "type": "string",
                    "description": "Name for the character"
                },
                "description": {
                    "type": "string",
                    "description": "Visual description for 3D generation"
                },
                "character_type": {
                    "type": "string",
                    "enum": ["player", "enemy", "npc", "prop"],
                    "description": "Type of character (determines node type and script template)",
                    "default": "npc"
                },
                "add_script": {
                    "type": "boolean",
                    "description": "Whether to generate a placeholder script",
                    "default": True
                },
                "texture": {
                    "type": "boolean",
                    "description": "Whether to generate texture",
                    "default": False
                }
            },
            "required": ["project_path", "character_name", "description"]
        },
        function=godot_generate_character_3d,
        category="godot_3d",
        examples=[
            'godot_generate_character_3d(project_path="./my_game", character_name="Player", description="futuristic soldier in armor", character_type="player")',
            'godot_generate_character_3d(project_path="./my_game", character_name="Alien", description="green alien creature", character_type="enemy")'
        ]
    ))

    registry.register(ToolDefinition(
        name="godot_list_hunyuan_models",
        description="List all 3D models generated by Hunyuan3D in a Godot project.",
        parameters={
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Path to the Godot project"
                }
            },
            "required": ["project_path"]
        },
        function=godot_list_hunyuan_models,
        category="godot_3d",
    ))

    registry.register(ToolDefinition(
        name="hunyuan_server_status",
        description="Check if the Hunyuan3D server is running and accessible.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        function=hunyuan_server_status,
        category="godot_3d",
    ))
