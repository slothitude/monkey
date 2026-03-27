"""AI Art Generation tools using Pixazo.ai API.

This module provides tools for generating sprites, textures, and music using AI.

Configuration:
    Set PIXAZO_API_KEY environment variable or in config.yaml:
    art_providers:
      pixazo:
        api_key: ${PIXAZO_API_KEY}
"""

import os
import asyncio
from pathlib import Path
from typing import Optional

from llm_router.tools import ToolDefinition, ToolRegistry

# Try to import httpx, fall back to aiohttp
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


# API Configuration
PIXAZO_API_KEY = os.environ.get("PIXAZO_API_KEY", "")
PIXAZO_FLUX_URL = "https://gateway.pixazo.ai/flux-1-schnell/v1/getData"
PIXAZO_SDXL_URL = "https://gateway.pixazo.ai/getImage/v1/getSDXLImage"
PIXAZO_TRACKS_URL = "https://gateway.pixazo.ai/tracks/v1/generate"
PIXAZO_TRACKS_STATUS_URL = "https://gateway.pixazo.ai/tracks/v1/status"


async def _download_image(url: str, save_path: Path) -> bool:
    """Download an image from URL and save to path."""
    try:
        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(url, follow_redirects=True)
                if response.status_code == 200:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    save_path.write_bytes(response.content)
                    return True
        elif HAS_AIOHTTP:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        save_path.parent.mkdir(parents=True, exist_ok=True)
                        save_path.write_bytes(await response.read())
                        return True
        return False
    except Exception as e:
        print(f"Error downloading image: {e}")
        return False


async def generate_sprite_ai(
    project_path: str,
    sprite_name: str,
    sprite_config: dict
) -> dict:
    """Generate a sprite using AI image generation via Pixazo.ai API.

    Args:
        project_path: Path to the Godot project
        sprite_name: Name for the sprite (without extension)
        sprite_config: Sprite configuration

    sprite_config options:
        - prompt: Description of the sprite
        - size: [width, height] (default: [64, 64])
        - style: pixel_art, cartoon, realistic, anime (default: pixel_art)

    Returns:
        Dict with sprite info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        if not PIXAZO_API_KEY:
            return {
                "error": "PIXAZO_API_KEY not set. Set environment variable.",
                "hint": "export PIXAZO_API_KEY=your_key_here"
            }

        # Create assets directory
        assets_dir = project_dir / "assets" / "sprites"
        assets_dir.mkdir(parents=True, exist_ok=True)

        # Build prompt based on style
        base_prompt = sprite_config.get("prompt", sprite_name)
        style = sprite_config.get("style", "pixel_art")
        size = sprite_config.get("size", [64, 64])

        style_prompts = {
            "pixel_art": f"Pixel art sprite of {base_prompt}, pixel art style, {size[0]}x{size[1]} pixels, game asset, white background",
            "cartoon": f"Cartoon style sprite of {base_prompt}, bright colors, bold outlines, game asset",
            "realistic": f"Realistic sprite of {base_prompt}, detailed, high quality, game asset",
            "anime": f"Anime style sprite of {base_prompt}, cel-shaded, vibrant colors, game asset",
        }

        prompt = style_prompts.get(style, style_prompts["pixel_art"])

        # Generate using Flux-1-Schnell (fast)
        payload = {
            "prompt": prompt,
            "num_steps": 4,
            "seed": sprite_config.get("seed", 42),
            "height": size[1],
            "width": size[0]
        }

        sprite_path = assets_dir / f"{sprite_name}.png"

        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    PIXAZO_FLUX_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Ocp-Apim-Subscription-Key": PIXAZO_API_KEY
                    },
                    json=payload
                )

                if response.status_code != 200:
                    return {"error": f"API request failed: {response.status_code}", "details": response.text}

                data = response.json()
        elif HAS_AIOHTTP:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    PIXAZO_FLUX_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Ocp-Apim-Subscription-Key": PIXAZO_API_KEY
                    },
                    json=payload
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        return {"error": f"API request failed: {response.status}", "details": text}
                    data = await response.json()
        else:
            return {"error": "No HTTP client available. Install httpx or aiohttp."}

        image_url = data.get("output")
        if not image_url:
            return {"error": "No image URL in response", "response": data}

        # Download the image
        if await _download_image(image_url, sprite_path):
            return {
                "success": True,
                "sprite_path": str(sprite_path),
                "sprite_name": sprite_name,
                "resource_path": f"res://assets/sprites/{sprite_name}.png",
                "size": size,
                "style": style,
                "image_url": image_url,
                "message": f"Generated {style} sprite '{sprite_name}'"
            }
        else:
            return {"error": "Failed to download generated image"}

    except Exception as e:
        return {"error": str(e), "sprite_name": sprite_name}


async def generate_texture_ai(
    project_path: str,
    texture_name: str,
    texture_config: dict
) -> dict:
    """Generate a texture using AI image generation via Pixazo.ai API.

    Args:
        project_path: Path to the Godot project
        texture_name: Name for the texture (without extension)
        texture_config: Texture configuration

    texture_config options:
        - prompt: Description of the texture
        - size: [width, height] (default: [256, 256])
        - seamless: Generate seamless texture (default: True)

    Returns:
        Dict with texture info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        if not PIXAZO_API_KEY:
            return {"error": "PIXAZO_API_KEY not set"}

        # Create assets directory
        assets_dir = project_dir / "assets" / "textures"
        assets_dir.mkdir(parents=True, exist_ok=True)

        size = texture_config.get("size", [256, 256])
        seamless = texture_config.get("seamless", True)
        base_prompt = texture_config.get("prompt", texture_name)

        prompt = f"{base_prompt}, seamless tileable texture" if seamless else base_prompt

        payload = {
            "prompt": prompt,
            "num_steps": 4,
            "seed": texture_config.get("seed", 42),
            "height": size[1],
            "width": size[0]
        }

        texture_path = assets_dir / f"{texture_name}.png"

        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    PIXAZO_FLUX_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Ocp-Apim-Subscription-Key": PIXAZO_API_KEY
                    },
                    json=payload
                )
                if response.status_code != 200:
                    return {"error": f"API request failed: {response.status_code}"}
                data = response.json()
        elif HAS_AIOHTTP:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    PIXAZO_FLUX_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Ocp-Apim-Subscription-Key": PIXAZO_API_KEY
                    },
                    json=payload
                ) as response:
                    if response.status != 200:
                        return {"error": f"API request failed: {response.status}"}
                    data = await response.json()
        else:
            return {"error": "No HTTP client available"}

        image_url = data.get("output")
        if not image_url:
            return {"error": "No image URL in response"}

        if await _download_image(image_url, texture_path):
            return {
                "success": True,
                "texture_path": str(texture_path),
                "texture_name": texture_name,
                "resource_path": f"res://assets/textures/{texture_name}.png",
                "size": size,
                "seamless": seamless,
                "message": f"Generated texture '{texture_name}'"
            }
        else:
            return {"error": "Failed to download generated texture"}

    except Exception as e:
        return {"error": str(e), "texture_name": texture_name}


async def generate_character_ai(
    project_path: str,
    character_name: str,
    character_config: dict
) -> dict:
    """Generate a character with multiple animations using AI.

    Args:
        project_path: Path to the Godot project
        character_name: Name for the character (without extension)
        character_config: Character configuration

    character_config options:
        - prompt: Description of the character
        - animations: List of animation names (default: ["idle", "walk", "run", "jump"])
        - size: [width, height] (default: [64, 64])

    Returns:
        Dict with character info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        if not PIXAZO_API_KEY:
            return {"error": "PIXAZO_API_KEY not set"}

        # Create assets directory
        assets_dir = project_dir / "assets" / "characters"
        assets_dir.mkdir(parents=True, exist_ok=True)

        base_prompt = character_config.get("prompt", character_name)
        animations = character_config.get("animations", ["idle", "walk", "run", "jump"])
        size = character_config.get("size", [64, 64])

        frames = []
        for anim in animations:
            frame_prompt = f"{base_prompt}, {anim} pose, pixel art style, game character"

            frame_result = await generate_sprite_ai(
                project_path,
                f"{character_name}_{anim}",
                {
                    "prompt": frame_prompt,
                    "size": size,
                    "style": "pixel_art"
                }
            )

            if frame_result.get("success"):
                frames.append({
                    "animation": anim,
                    "path": frame_result["sprite_path"],
                    "resource_path": frame_result["resource_path"]
                })

        if not frames:
            return {"error": "Failed to generate any character frames"}

        # Create SpriteFrames resource file
        frames_content = f'''[gd_resource type="SpriteFrames" format=3 uid="uid://c{character_name}"]

[resource]
animations = [{{
"frames": [{{
"duration": 0.1,
"texture": null
}}],
"loop": true,
"name": "{animations[0]}",
"speed": 10.0
}}]
'''
        frames_file = assets_dir / f"{character_name}_frames.tres"
        frames_file.write_text(frames_content)

        return {
            "success": True,
            "character_name": character_name,
            "frames": frames,
            "frame_count": len(frames),
            "animations": animations,
            "resource_path": f"res://assets/characters/{character_name}_frames.tres",
            "message": f"Generated character '{character_name}' with {len(frames)} animation frames"
        }

    except Exception as e:
        return {"error": str(e), "character_name": character_name}


async def generate_music_ai(
    project_path: str,
    music_name: str,
    prompt: str,
    duration: int = 120,
    bpm: int = 140,
    instrumental: bool = True
) -> dict:
    """Generate music using Pixazo.ai API.

    Args:
        project_path: Path to the Godot project
        music_name: Name for the music (without extension)
        prompt: Description of the music
        duration: Duration in seconds (default: 120)
        bpm: Beats per minute (default: 140)
        instrumental: Whether to generate instrumental (default: True)

    Returns:
        Dict with music info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        if not PIXAZO_API_KEY:
            return {"error": "PIXAZO_API_KEY not set"}

        # Create assets directory
        assets_dir = project_dir / "assets" / "music"
        assets_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "prompt": prompt,
            "lyrics": "",
            "instrumental": instrumental,
            "duration": min(duration, 300),  # Max 5 minutes
            "bpm": bpm,
            "infer_steps": 25,
            "guidance_scale": 7.5,
            "seed": 42
        }

        # Start music generation
        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    PIXAZO_TRACKS_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Ocp-Apim-Subscription-Key": PIXAZO_API_KEY
                    },
                    json=payload
                )
                if response.status_code != 200:
                    return {"error": f"API request failed: {response.status_code}"}
                data = response.json()
        elif HAS_AIOHTTP:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    PIXAZO_TRACKS_URL,
                    headers={
                        "Content-Type": "application/json",
                        "Ocp-Apim-Subscription-Key": PIXAZO_API_KEY
                    },
                    json=payload
                ) as response:
                    if response.status != 200:
                        return {"error": f"API request failed: {response.status}"}
                    data = await response.json()
        else:
            return {"error": "No HTTP client available"}

        task_id = data.get("task_id")
        status = data.get("status", "queued")

        # Return task info - user needs to poll for completion
        music_path = assets_dir / f"{music_name}.mp3"

        return {
            "success": True,
            "task_id": task_id,
            "status": status,
            "music_name": music_name,
            "music_path": str(music_path),
            "resource_path": f"res://assets/music/{music_name}.mp3",
            "duration": duration,
            "bpm": bpm,
            "message": f"Music generation started (task: {task_id})",
            "note": "Music generation is async. Check status with task_id."
        }

    except Exception as e:
        return {"error": str(e), "music_name": music_name}


async def check_music_status(task_id: str) -> dict:
    """Check the status of a music generation task."""
    try:
        if not PIXAZO_API_KEY:
            return {"error": "PIXAZO_API_KEY not set"}

        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{PIXAZO_TRACKS_STATUS_URL}/{task_id}",
                    headers={
                        "Ocp-Apim-Subscription-Key": PIXAZO_API_KEY
                    }
                )
                if response.status_code != 200:
                    return {"error": f"API request failed: {response.status_code}"}
                return response.json()
        elif HAS_AIOHTTP:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{PIXAZO_TRACKS_STATUS_URL}/{task_id}",
                    headers={
                        "Ocp-Apim-Subscription-Key": PIXAZO_API_KEY
                    }
                ) as response:
                    if response.status != 200:
                        return {"error": f"API request failed: {response.status}"}
                    return await response.json()
        else:
            return {"error": "No HTTP client available"}

    except Exception as e:
        return {"error": str(e), "task_id": task_id}


# =============================================================================
# Tool Definitions
# =============================================================================

GODOT_GENERATE_SPRITE_AI_DEF = ToolDefinition(
    name="godot_generate_sprite_ai",
    description="""Generate a sprite using AI image generation via Pixazo.ai API.

Requires PIXAZO_API_KEY environment variable.

Styles: pixel_art, cartoon, realistic, anime""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "sprite_name": {"type": "string", "description": "Name for the sprite (without extension)"},
            "sprite_config": {
                "type": "object",
                "description": "Sprite configuration",
                "properties": {
                    "prompt": {"type": "string", "description": "Description of the sprite"},
                    "size": {"type": "array", "items": {"type": "integer"}, "default": [64, 64]},
                    "style": {"type": "string", "description": "Style: pixel_art, cartoon, realistic, anime", "default": "pixel_art"}
                }
            }
        },
        "required": ["project_path", "sprite_name", "sprite_config"],
    },
    function=generate_sprite_ai,
    category="godot",
)

GODOT_GENERATE_TEXTURE_AI_DEF = ToolDefinition(
    name="godot_generate_texture_ai",
    description="""Generate a texture using AI image generation via Pixazo.ai API.

Requires PIXAZO_API_KEY environment variable.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "texture_name": {"type": "string", "description": "Name for the texture (without extension)"},
            "texture_config": {
                "type": "object",
                "description": "Texture configuration",
                "properties": {
                    "prompt": {"type": "string", "description": "Description of the texture"},
                    "size": {"type": "array", "items": {"type": "integer"}, "default": [256, 256]},
                    "seamless": {"type": "boolean", "default": True}
                }
            }
        },
        "required": ["project_path", "texture_name", "texture_config"],
    },
    function=generate_texture_ai,
    category="godot",
)

GODOT_GENERATE_CHARACTER_AI_DEF = ToolDefinition(
    name="godot_generate_character_ai",
    description="""Generate a character with multiple animations using AI.

Requires PIXAZO_API_KEY environment variable.

Generates sprites for each animation and creates SpriteFrames resource.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "character_name": {"type": "string", "description": "Name for the character (without extension)"},
            "character_config": {
                "type": "object",
                "description": "Character configuration",
                "properties": {
                    "prompt": {"type": "string", "description": "Description of the character"},
                    "animations": {"type": "array", "items": {"type": "string"}, "default": ["idle", "walk", "run", "jump"]},
                    "size": {"type": "array", "items": {"type": "integer"}, "default": [64, 64]}
                }
            }
        },
        "required": ["project_path", "character_name", "character_config"],
    },
    function=generate_character_ai,
    category="godot",
)

GODOT_GENERATE_MUSIC_AI_DEF = ToolDefinition(
    name="godot_generate_music_ai",
    description="""Generate music using Pixazo.ai API.

Requires PIXAZO_API_KEY environment variable.

Music generation is asynchronous - returns task_id for status checking.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "music_name": {"type": "string", "description": "Name for the music (without extension)"},
            "prompt": {"type": "string", "description": "Description of the music style"},
            "duration": {"type": "integer", "default": 120, "description": "Duration in seconds"},
            "bpm": {"type": "integer", "default": 140, "description": "Beats per minute"},
            "instrumental": {"type": "boolean", "default": True, "description": "Generate instrumental only"}
        },
        "required": ["project_path", "music_name", "prompt"],
    },
    function=generate_music_ai,
    category="godot",
)


def register_ai_art_tools(registry: ToolRegistry) -> None:
    """Register all AI art tools with a registry."""
    registry.register(GODOT_GENERATE_SPRITE_AI_DEF)
    registry.register(GODOT_GENERATE_TEXTURE_AI_DEF)
    registry.register(GODOT_GENERATE_CHARACTER_AI_DEF)
    registry.register(GODOT_GENERATE_MUSIC_AI_DEF)
