"""AI Art Generation tools using Pixazo.ai API.

This module provides tools for generating sprites, textures, and music using AI.

Configuration:
    Set PIXAZO_API_KEY environment variable or in config.yaml:
    art_providers:
      pixazo:
        api_key: ${PIXAZO_API_KEY}
"""

import os
import io
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

try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# API Configuration
PIXAZO_API_KEY = os.environ.get("PIXAZO_API_KEY", "b07f2a4ffe134506af0d30a56892eb6b")
PIXAZO_FLUX_URL = "https://gateway.pixazo.ai/flux-1-schnell/v1/getData"
PIXAZO_SDXL_URL = "https://gateway.pixazo.ai/getImage/v1/getSDXLImage"
PIXAZO_TRACKS_URL = "https://gateway.pixazo.ai/tracks/v1/generate"
PIXAZO_TRACKS_STATUS_URL = "https://gateway.pixazo.ai/tracks/v1/status"


async def _download_image(url: str, save_path: Path, auto_crop: bool = True) -> bool:
    """Download an image from URL and save to path.

    Args:
        url: Image URL to download
        save_path: Path to save the image
        auto_crop: If True, automatically crop to content using OpenCV
    """
    try:
        image_data = None

        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(url, follow_redirects=True)
                if response.status_code == 200:
                    image_data = response.content
        elif HAS_AIOHTTP:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_data = await response.read()

        if image_data is None:
            return False

        save_path.parent.mkdir(parents=True, exist_ok=True)

        # Auto-crop using OpenCV if available
        if auto_crop and HAS_OPENCV:
            image_data = _crop_to_content(image_data)

        save_path.write_bytes(image_data)
        return True
    except Exception as e:
        print(f"Error downloading image: {e}")
        return False


def _crop_to_content(image_data: bytes) -> bytes:
    """Crop image to its content using OpenCV.

    Removes whitespace/background and centers the actual content.
    """
    try:
        # Decode image
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)

        if img is None:
            return image_data

        # Handle alpha channel
        if len(img.shape) == 3 and img.shape[2] == 4:
            # Use alpha channel for masking
            alpha = img[:, :, 3]
            _, thresh = cv2.threshold(alpha, 1, 255, cv2.THRESH_BINARY)
        else:
            # Convert to grayscale and threshold
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)

        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return image_data

        # Get bounding box of all contours
        x, y, w, h = cv2.boundingRect(np.vstack(contours))

        # Add small padding
        padding = 2
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(img.shape[1] - x, w + padding * 2)
        h = min(img.shape[0] - y, h + padding * 2)

        # Crop
        cropped = img[y:y+h, x:x+w]

        # Encode back to PNG
        success, encoded = cv2.imencode('.png', cropped)
        if success:
            return encoded.tobytes()

        return image_data
    except Exception as e:
        print(f"Cropping failed: {e}")
        return image_data


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

        # Download the image (with auto-crop enabled by default)
        auto_crop = sprite_config.get("auto_crop", True)
        if await _download_image(image_url, sprite_path, auto_crop=auto_crop):
            return {
                "success": True,
                "sprite_path": str(sprite_path),
                "sprite_name": sprite_name,
                "resource_path": f"res://assets/sprites/{sprite_name}.png",
                "size": size,
                "style": style,
                "image_url": image_url,
                "auto_cropped": auto_crop and HAS_OPENCV,
                "message": f"Generated {style} sprite '{sprite_name}'" + (" (auto-cropped)" if auto_crop and HAS_OPENCV else "")
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


# =============================================================================
# TILE GENERATION FUNCTIONS
# =============================================================================

async def create_tile_from_image(
    project_path: str,
    source_image: str,
    tile_name: str,
    tile_size: list = [32, 32],
    padding: int = 0,
    seamless: bool = False
) -> dict:
    """Convert an image into a game tile.

    Args:
        project_path: Path to the Godot project
        source_image: Path or URL to source image
        tile_name: Name for the tile (without extension)
        tile_size: Target tile size [width, height]
        padding: Pixels of padding around the tile content
        seamless: If True, make the tile seamlessly tileable

    Returns:
        Dict with tile info or error
    """
    if not HAS_PIL:
        return {"error": "PIL/Pillow not installed. Run: pip install Pillow"}

    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        # Create tiles directory
        tiles_dir = project_dir / "assets" / "tiles"
        tiles_dir.mkdir(parents=True, exist_ok=True)

        # Load source image
        if source_image.startswith("http"):
            # Download from URL
            temp_path = tiles_dir / f"_temp_{tile_name}.png"
            if await _download_image(source_image, temp_path, auto_crop=False):
                img = Image.open(temp_path)
            else:
                return {"error": "Failed to download source image"}
            temp_path.unlink()
        else:
            img = Image.open(source_image)

        # Convert to RGBA
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Resize to tile size
        if padding > 0:
            # Create padded image
            padded = Image.new('RGBA', tile_size, (0, 0, 0, 0))
            # Calculate position to center the image
            content_size = (tile_size[0] - padding * 2, tile_size[1] - padding * 2)
            resized = img.resize(content_size, Image.Resampling.LANCZOS)
            offset = padding
            padded.paste(resized, (offset, offset))
            img = padded
        else:
            img = img.resize(tile_size, Image.Resampling.LANCZOS)

        # Make seamless if requested
        if seamless:
            img = _make_seamless(img)

        # Save the tile
        tile_path = tiles_dir / f"{tile_name}.png"
        img.save(tile_path, "PNG")

        return {
            "success": True,
            "tile_path": str(tile_path),
            "tile_name": tile_name,
            "resource_path": f"res://assets/tiles/{tile_name}.png",
            "tile_size": tile_size,
            "seamless": seamless,
            "message": f"Created tile '{tile_name}' ({tile_size[0]}x{tile_size[1]})"
        }

    except Exception as e:
        return {"error": str(e)}


def _make_seamless(img: Image.Image) -> Image.Image:
    """Make an image seamlessly tileable using mirroring."""
    w, h = img.size

    # Create a new image with mirrored edges
    seamless = Image.new('RGBA', (w, h), (0, 0, 0, 0))

    # Quadrant approach: mirror the image to make it seamless
    # Top-left quadrant
    seamless.paste(img.crop((0, 0, w//2, h//2)), (0, 0))
    # Top-right quadrant (flipped horizontal)
    right_half = img.crop((w//2, 0, w, h//2))
    seamless.paste(ImageOps.mirror(right_half), (w//2, 0))
    # Bottom-left quadrant (flipped vertical)
    bottom_half = img.crop((0, h//2, w//2, h))
    seamless.paste(ImageOps.flip(bottom_half), (0, h//2))
    # Bottom-right quadrant (flipped both)
    corner = img.crop((w//2, h//2, w, h))
    seamless.paste(ImageOps.mirror(ImageOps.flip(corner)), (w//2, h//2))

    return seamless


async def create_mario_brick(
    project_path: str,
    brick_name: str = "mario_brick",
    brick_size: list = [32, 32],
    base_color: str = "#C84C31",
    mortar_color: str = "#8B4513",
    highlight_color: str = "#E8A862",
    crack_lines: bool = True,
    use_ai: bool = False,
    ai_prompt: str = None
) -> dict:
    """Create a Mario-style brick tile.

    Args:
        project_path: Path to the Godot project
        brick_name: Name for the brick tile
        brick_size: Size of the brick [width, height]
        base_color: Main brick color (hex)
        mortar_color: Mortar/crack color (hex)
        highlight_color: Highlight/edge color (hex)
        crack_lines: Add crack detail lines
        use_ai: Generate base texture with AI instead of procedural
        ai_prompt: Custom prompt for AI generation

    Returns:
        Dict with brick tile info or error
    """
    if not HAS_PIL:
        return {"error": "PIL/Pillow not installed. Run: pip install Pillow"}

    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        # Create tiles directory
        tiles_dir = project_dir / "assets" / "tiles"
        tiles_dir.mkdir(parents=True, exist_ok=True)

        w, h = brick_size

        if use_ai and ai_prompt:
            # Generate base texture with AI
            prompt = ai_prompt or "seamless pixel art brick texture, orange brown, classic video game style"
            result = await generate_texture_ai(
                project_path=project_path,
                texture_name=f"_{brick_name}_base",
                texture_config={
                    "prompt": prompt,
                    "size": brick_size,
                    "seamless": True
                }
            )
            if result.get("success"):
                # Load the AI-generated texture
                base_img = Image.open(result["texture_path"])
            else:
                # Fall back to procedural
                base_img = _create_procedural_brick(w, h, base_color, mortar_color, highlight_color, crack_lines)
        else:
            # Create procedural brick
            base_img = _create_procedural_brick(w, h, base_color, mortar_color, highlight_color, crack_lines)

        # Save the brick tile
        brick_path = tiles_dir / f"{brick_name}.png"
        base_img.save(brick_path, "PNG")

        return {
            "success": True,
            "tile_path": str(brick_path),
            "tile_name": brick_name,
            "resource_path": f"res://assets/tiles/{brick_name}.png",
            "tile_size": brick_size,
            "style": "ai" if use_ai else "procedural",
            "message": f"Created Mario brick '{brick_name}' ({w}x{h})"
        }

    except Exception as e:
        return {"error": str(e)}


def _create_procedural_brick(w: int, h: int, base_color: str, mortar_color: str, highlight_color: str, crack_lines: bool) -> Image.Image:
    """Create a procedural Mario-style brick image."""
    from PIL import Image, ImageDraw
    import random

    # Create base image
    img = Image.new('RGBA', (w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # Parse colors
    def hex_to_rgb(hex_str):
        hex_str = hex_str.lstrip('#')
        return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

    base_rgb = hex_to_rgb(base_color)
    mortar_rgb = hex_to_rgb(mortar_color)
    highlight_rgb = hex_to_rgb(highlight_color)

    # Draw main brick body
    draw.rectangle((0, 0, w-1, h-1), fill=base_rgb)

    # Draw mortar lines (horizontal cracks)
    if crack_lines:
        line_width = max(1, h // 16)
        # Horizontal lines
        for y in range(h // 4, h, h // 4):
            draw.line((0, y, w-1, y), fill=mortar_rgb, width=line_width)
        # Vertical lines (brick divisions)
        for x in range(w // 4, w, w // 4):
            draw.line((x, 0, x, h-1), fill=mortar_rgb, width=line_width)

    # Draw highlight on top edge
    draw.line((0, 0, w-1, 0), fill=highlight_rgb, width=max(1, h // 16))

    # Draw shadow on bottom edge
    shadow_color = tuple(max(0, c - 40) for c in base_rgb)
    draw.line((0, h-1, w-1, h-1), fill=shadow_color, width=max(1, h // 16))

    # Add some texture/noise
    pixels = list(img.getdata())
    for i in range(len(pixels)):
        if pixels[i][3] > 0:  # Only modify non-transparent pixels
            variation = random.randint(-10, 10)
            r, g, b, a = pixels[i]
            pixels[i] = (
                max(0, min(255, r + variation)),
                max(0, min(255, g + variation)),
                max(0, min(255, b + variation)),
                a
            )
    img.putdata(pixels)

    return img


# =============================================================================
# ENHANCED TILE GENERATION WORKFLOW
# =============================================================================

# Style presets for consistent tileset generation
TILE_STYLES = {
    "pixel_art_16": {
        "size": [16, 16],
        "prompt_suffix": "16x16 pixel art, 4-8 colors maximum, clean edges, game tile",
        "palette_size": 8
    },
    "pixel_art_32": {
        "size": [32, 32],
        "prompt_suffix": "32x32 pixel art, limited palette, clean edges, game tile",
        "palette_size": 12
    },
    "cartoon": {
        "size": [64, 64],
        "prompt_suffix": "cartoon style, bold outlines, flat colors, game asset",
        "outline": True
    },
    "realistic": {
        "size": [128, 128],
        "prompt_suffix": "realistic texture, detailed, high quality game asset",
        "detailed": True
    },
}

# Predefined tileset configurations
TILESET_PRESETS = {
    "platformer": {
        "background_tiles": ["ground", "grass_top", "dirt", "stone", "wood_platform"],
        "decoration_tiles": ["bush", "flower", "rock", "mushroom", "tree_trunk"],
        "objects": ["coin", "heart", "star"],
    },
    "dungeon": {
        "background_tiles": ["floor_stone", "wall_stone", "wall_brick", "door", "stairs"],
        "decoration_tiles": ["torch", "chest", "bones", "cobweb", "crack"],
        "objects": ["key", "gem", "potion"],
    },
    "forest": {
        "background_tiles": ["grass", "path", "water", "bridge", "leaves_ground"],
        "decoration_tiles": ["tree", "bush", "flower", "log", "mushroom"],
        "objects": ["acorn", "berry", "feather"],
    },
    "desert": {
        "background_tiles": ["sand", "sandstone", "brick_adobe", "cave_entrance"],
        "decoration_tiles": ["cactus", "skull", "tumbleweed", "palm_tree"],
        "objects": ["gem_ruby", "scroll", "lamp"],
    },
    "ice": {
        "background_tiles": ["ice_floor", "snow", "ice_wall", "frozen_water"],
        "decoration_tiles": ["icicle", "snowman", "pine_tree", "crystal"],
        "objects": ["gem_diamond", "frozen_heart", "snowflake"],
    },
}


def remove_white_background(img: Image.Image, threshold: int = 240) -> Image.Image:
    """Remove white/near-white background and make it transparent.

    Args:
        img: PIL Image (will be converted to RGBA)
        threshold: Pixels with R,G,B all above this become transparent

    Returns:
        RGBA PIL Image with transparent background
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    data = list(img.getdata())
    new_data = []
    for r, g, b, a in data:
        # Check if pixel is white/near-white
        if r >= threshold and g >= threshold and b >= threshold:
            new_data.append((255, 255, 255, 0))  # Transparent
        else:
            new_data.append((r, g, b, a))

    img.putdata(new_data)
    return img


def remove_color_background(img: Image.Image, target_color: tuple, tolerance: int = 30) -> Image.Image:
    """Remove a specific color background (chroma key).

    Args:
        img: PIL Image
        target_color: (R, G, B) color to remove
        tolerance: How close colors need to be to target

    Returns:
        RGBA PIL Image with transparent background
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    data = list(img.getdata())
    new_data = []
    tr, tg, tb = target_color

    for r, g, b, a in data:
        # Calculate distance from target color
        dist = abs(r - tr) + abs(g - tg) + abs(b - tb)
        if dist <= tolerance * 3:
            # Make transparent based on distance
            alpha = int(255 * (dist / (tolerance * 3)))
            new_data.append((r, g, b, alpha))
        else:
            new_data.append((r, g, b, a))

    img.putdata(new_data)
    return img


def make_seamless_offset_blend(img: Image.Image, blend_width: int = 8) -> Image.Image:
    """Make image seamlessly tileable using offset and blend algorithm.

    The algorithm:
    1. Offset image by 50% in both directions
    2. This moves edges to the center where they can be blended
    3. Apply feathered blend at center seams

    Args:
        img: PIL Image (should be RGBA)
        blend_width: Width of the blend zone in pixels

    Returns:
        Seamlessly tileable image
    """
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    w, h = img.size
    result = Image.new('RGBA', (w, h), (0, 0, 0, 0))

    half_w, half_h = w // 2, h // 2

    # Get quadrants from original
    q_tl = img.crop((0, 0, half_w, half_h))
    q_tr = img.crop((half_w, 0, w, half_h))
    q_bl = img.crop((0, half_h, half_w, h))
    q_br = img.crop((half_w, half_h, w, h))

    # Paste in swapped positions (offset by half)
    result.paste(q_br, (0, 0))           # Bottom-right → top-left
    result.paste(q_bl, (half_w, 0))      # Bottom-left → top-right
    result.paste(q_tr, (0, half_h))      # Top-right → bottom-left
    result.paste(q_tl, (half_w, half_h)) # Top-left → bottom-right

    # Create blend masks for seams
    # Horizontal seam (at half_h)
    for x in range(w):
        for y in range(half_h - blend_width // 2, half_h + blend_width // 2):
            if 0 <= y < h:
                # Calculate blend factor (0 at top of seam, 1 at bottom)
                t = (y - (half_h - blend_width // 2)) / blend_width
                t = max(0, min(1, t))

                # Get pixels from both sides
                orig_pixel = img.getpixel((x, y))
                offset_pixel = result.getpixel((x, y))

                # Blend based on distance from seam
                if t < 0.5:
                    # Closer to top - use more original
                    alpha = t * 2
                else:
                    alpha = (1 - t) * 2

                # Blend pixels
                r = int(orig_pixel[0] * alpha + offset_pixel[0] * (1 - alpha))
                g = int(orig_pixel[1] * alpha + offset_pixel[1] * (1 - alpha))
                b = int(orig_pixel[2] * alpha + offset_pixel[2] * (1 - alpha))
                a = int(orig_pixel[3] * alpha + offset_pixel[3] * (1 - alpha))
                result.putpixel((x, y), (r, g, b, a))

    # Vertical seam (at half_w)
    for y in range(h):
        for x in range(half_w - blend_width // 2, half_w + blend_width // 2):
            if 0 <= x < w:
                t = (x - (half_w - blend_width // 2)) / blend_width
                t = max(0, min(1, t))

                orig_pixel = img.getpixel((x, y))
                offset_pixel = result.getpixel((x, y))

                if t < 0.5:
                    alpha = t * 2
                else:
                    alpha = (1 - t) * 2

                r = int(orig_pixel[0] * alpha + offset_pixel[0] * (1 - alpha))
                g = int(orig_pixel[1] * alpha + offset_pixel[1] * (1 - alpha))
                b = int(orig_pixel[2] * alpha + offset_pixel[2] * (1 - alpha))
                a = int(orig_pixel[3] * alpha + offset_pixel[3] * (1 - alpha))
                result.putpixel((x, y), (r, g, b, a))

    return result


def create_sprite_sheet(frames: list, columns: int = None, frame_duration: int = 100) -> tuple:
    """Combine animation frames into a sprite sheet.

    Args:
        frames: List of PIL Images
        columns: Number of columns (auto-calculated if None)
        frame_duration: Duration per frame in milliseconds

    Returns:
        Tuple of (spritesheet Image, metadata dict)
    """
    if not frames:
        return None, {"error": "No frames provided"}

    # Get frame size (assume all same size)
    frame_w, frame_h = frames[0].size

    # Calculate layout
    num_frames = len(frames)
    if columns is None:
        columns = int(num_frames ** 0.5) + 1
    rows = (num_frames + columns - 1) // columns

    # Create sprite sheet
    sheet_w = columns * frame_w
    sheet_h = rows * frame_h
    sheet = Image.new('RGBA', (sheet_w, sheet_h), (0, 0, 0, 0))

    # Paste frames
    frame_data = []
    for i, frame in enumerate(frames):
        col = i % columns
        row = i // columns
        x = col * frame_w
        y = row * frame_h
        sheet.paste(frame, (x, y))

        frame_data.append({
            "index": i,
            "x": x,
            "y": y,
            "width": frame_w,
            "height": frame_h,
            "duration": frame_duration
        })

    metadata = {
        "frame_width": frame_w,
        "frame_height": frame_h,
        "columns": columns,
        "rows": rows,
        "frame_duration": frame_duration,
        "frames": frame_data
    }

    return sheet, metadata


async def generate_sprite_with_alpha(
    project_path: str,
    sprite_name: str,
    sprite_config: dict
) -> dict:
    """Generate a sprite with proper alpha channel handling.

    This is an enhanced version that ensures clean transparency.

    Args:
        project_path: Path to the Godot project
        sprite_name: Name for the sprite (without extension)
        sprite_config: Configuration dict with:
            - prompt: Description of the sprite
            - size: [width, height] (default: [64, 64])
            - style: pixel_art, cartoon, realistic (default: pixel_art)
            - remove_bg: True to remove white background (default: True)
            - seamless: True to make tileable (default: False)
            - seed: Random seed for reproducibility

    Returns:
        Dict with sprite info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        if not PIXAZO_API_KEY:
            return {"error": "PIXAZO_API_KEY not set"}

        # Create assets directory
        assets_dir = project_dir / "assets" / "sprites"
        assets_dir.mkdir(parents=True, exist_ok=True)

        # Get config
        base_prompt = sprite_config.get("prompt", sprite_name)
        style = sprite_config.get("style", "pixel_art_32")
        size = sprite_config.get("size", [64, 64])
        remove_bg = sprite_config.get("remove_bg", True)
        seamless = sprite_config.get("seamless", False)
        seed = sprite_config.get("seed", 42)

        # Get style settings - normalize style name
        if style == "pixel_art":
            style = "pixel_art_32"  # Default to 32px
        style_config = TILE_STYLES.get(style, TILE_STYLES.get("pixel_art_32", {}))
        style_suffix = style_config.get("prompt_suffix", "pixel art style")

        # Use size from style config if not specified
        if "size" not in sprite_config and "size" in style_config:
            size = style_config["size"]

        # Build prompt
        prompt = f"{base_prompt}, {style_suffix}, isolated on white background"

        # Generate via API
        payload = {
            "prompt": prompt,
            "num_steps": 4,
            "seed": seed,
            "height": size[1],
            "width": size[0]
        }

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

        # Download image
        img_data = None
        if HAS_HTTPX:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(image_url)
                if resp.status_code == 200:
                    img_data = resp.content
        elif HAS_AIOHTTP:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as resp:
                    if resp.status == 200:
                        img_data = await resp.read()

        if not img_data:
            return {"error": "Failed to download image"}

        # Process image
        img = Image.open(io.BytesIO(img_data))

        # Remove white background
        if remove_bg:
            img = remove_white_background(img, threshold=240)

        # Make seamless if requested
        if seamless:
            img = make_seamless_offset_blend(img)

        # Auto-crop to content with padding
        if HAS_OPENCV:
            # Convert to bytes, crop, convert back
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            cropped_data = _crop_to_content(buffer.getvalue())
            img = Image.open(io.BytesIO(cropped_data))

        # Save
        sprite_path = assets_dir / f"{sprite_name}.png"
        img.save(sprite_path, "PNG")

        return {
            "success": True,
            "sprite_path": str(sprite_path),
            "sprite_name": sprite_name,
            "resource_path": f"res://assets/sprites/{sprite_name}.png",
            "size": list(img.size),
            "style": style,
            "seamless": seamless,
            "alpha_removed": remove_bg,
            "message": f"Generated {style} sprite '{sprite_name}' with alpha channel"
        }

    except Exception as e:
        return {"error": str(e)}


async def generate_tileset_ai(
    project_path: str,
    tileset_name: str,
    tileset_config: dict
) -> dict:
    """Generate a coherent tileset with multiple tiles.

    Args:
        project_path: Path to the Godot project
        tileset_name: Name for the tileset
        tileset_config: Configuration dict with:
            - style: pixel_art_16, pixel_art_32, cartoon, realistic
            - theme: forest, dungeon, platformer, desert, ice (or custom)
            - tiles: list of tile names (optional, uses preset if not provided)
            - seed: Random seed for consistency
            - seamless: Make all tiles seamless (default: True)

    Returns:
        Dict with tileset info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        # Get config
        style = tileset_config.get("style", "pixel_art_32")
        theme = tileset_config.get("theme", "platformer")
        seed = tileset_config.get("seed", 42)
        seamless = tileset_config.get("seamless", True)
        custom_tiles = tileset_config.get("tiles", None)

        # Get tiles from preset or custom list
        if custom_tiles:
            tiles_to_generate = custom_tiles
        else:
            preset = TILESET_PRESETS.get(theme, TILESET_PRESETS["platformer"])
            tiles_to_generate = preset.get("background_tiles", []) + preset.get("decoration_tiles", [])

        if not tiles_to_generate:
            return {"error": "No tiles to generate"}

        # Get style config
        style_config = TILE_STYLES.get(style, TILE_STYLES["pixel_art_32"])
        size = style_config.get("size", [32, 32])

        # Create output directory
        tiles_dir = project_dir / "assets" / "tiles" / tileset_name
        tiles_dir.mkdir(parents=True, exist_ok=True)

        # Generate each tile
        generated_tiles = []
        for i, tile_name in enumerate(tiles_to_generate):
            # Use consistent seed based on tileset seed + tile index
            tile_seed = seed + i

            result = await generate_sprite_with_alpha(
                project_path,
                f"{tileset_name}/{tile_name}",
                {
                    "prompt": f"{tile_name} tile for {theme} environment",
                    "size": size,
                    "style": style.split('_')[0] + ('_16' if '16' in style else '_32' if '32' in style else ''),
                    "remove_bg": True,
                    "seamless": seamless,
                    "seed": tile_seed
                }
            )

            if result.get("success"):
                generated_tiles.append({
                    "name": tile_name,
                    "path": result["sprite_path"],
                    "resource_path": result["resource_path"],
                    "size": result["size"]
                })
            else:
                print(f"Warning: Failed to generate tile '{tile_name}': {result.get('error')}")

        return {
            "success": True,
            "tileset_name": tileset_name,
            "style": style,
            "theme": theme,
            "tiles": generated_tiles,
            "tile_count": len(generated_tiles),
            "tile_size": size,
            "seamless": seamless,
            "tiles_dir": str(tiles_dir),
            "message": f"Generated tileset '{tileset_name}' with {len(generated_tiles)} tiles"
        }

    except Exception as e:
        return {"error": str(e)}


def analyze_tile_needs(game_config: dict) -> dict:
    """Analyze what tiles need to be generated based on game requirements.

    Args:
        game_config: Dict with:
            - game_type: platformer, rpg, puzzle, etc.
            - environment: forest, dungeon, space, etc.
            - characters: list of character names
            - objects: list of object types
            - style: pixel_art, cartoon, realistic

    Returns:
        TileManifest dict describing all needed tiles
    """
    game_type = game_config.get("game_type", "platformer")
    environment = game_config.get("environment", "forest")
    characters = game_config.get("characters", ["player"])
    objects = game_config.get("objects", ["collectible"])
    style = game_config.get("style", "pixel_art_32")

    # Get preset for environment
    preset = TILESET_PRESETS.get(environment, TILESET_PRESETS["platformer"])

    # Build manifest
    manifest = {
        "tileset_name": f"{environment}_{game_type}",
        "style": style,
        "theme": environment,

        # Static tiles from preset
        "background_tiles": preset.get("background_tiles", []),
        "decoration_tiles": preset.get("decoration_tiles", []),

        # Characters with animations
        "characters": [
            {
                "name": char,
                "animations": ["idle", "walk", "run", "jump"] if game_type == "platformer" else ["idle", "walk"]
            }
            for char in characters
        ],

        # Objects
        "objects": [
            {
                "name": obj,
                "animations": ["idle", "collect"] if "collect" in obj or "coin" in obj else ["idle"]
            }
            for obj in objects
        ],

        # Style settings
        "tile_size": TILE_STYLES.get(style, {}).get("size", [32, 32]),
        "palette": None,  # Could be extracted or defined
    }

    return manifest


# Tool definitions for tile functions
GODOT_CREATE_TILE_DEF = ToolDefinition(
    name="godot_create_tile",
    description="Convert an image into a game tile with optional seamless tiling.",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "source_image": {"type": "string", "description": "Path or URL to source image"},
            "tile_name": {"type": "string", "description": "Name for the tile (without extension)"},
            "tile_size": {
                "type": "array",
                "items": {"type": "integer"},
                "default": [32, 32],
                "description": "Target tile size [width, height]"
            },
            "padding": {"type": "integer", "default": 0, "description": "Pixels of padding around content"},
            "seamless": {"type": "boolean", "default": False, "description": "Make tile seamlessly repeatable"}
        },
        "required": ["project_path", "source_image", "tile_name"]
    },
    function=create_tile_from_image,
    category="godot",
    examples=[
        'godot_create_tile(project_path="./my_game", source_image="./brick.png", tile_name="brick_tile", tile_size=[32, 32])'
    ]
)

GODOT_CREATE_MARIO_BRICK_DEF = ToolDefinition(
    name="godot_create_mario_brick",
    description="Create a Mario-style brick tile for platformer games. Can be procedural or AI-generated.",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "brick_name": {"type": "string", "default": "mario_brick", "description": "Name for the brick tile"},
            "brick_size": {
                "type": "array",
                "items": {"type": "integer"},
                "default": [32, 32],
                "description": "Size of the brick [width, height]"
            },
            "base_color": {"type": "string", "default": "#C84C31", "description": "Main brick color (hex)"},
            "mortar_color": {"type": "string", "default": "#8B4513", "description": "Mortar/crack color (hex)"},
            "highlight_color": {"type": "string", "default": "#E8A862", "description": "Highlight color (hex)"},
            "crack_lines": {"type": "boolean", "default": True, "description": "Add crack detail lines"},
            "use_ai": {"type": "boolean", "default": False, "description": "Generate base texture with AI"},
            "ai_prompt": {"type": "string", "description": "Custom prompt for AI generation (if use_ai=True)"}
        },
        "required": ["project_path"]
    },
    function=create_mario_brick,
    category="godot",
    examples=[
        'godot_create_mario_brick(project_path="./my_game", brick_name="ground_brick")',
        'godot_create_mario_brick(project_path="./my_game", brick_name="ai_brick", use_ai=True, ai_prompt="classic Mario brick texture, orange brown")'
    ]
)

GODOT_GENERATE_SPRITE_ALPHA_DEF = ToolDefinition(
    name="godot_generate_sprite_alpha",
    description="""Generate a sprite with proper alpha channel handling.

Ensures clean transparency by removing white backgrounds and optionally making tiles seamless.

Styles: pixel_art_16, pixel_art_32, cartoon, realistic""",
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
                    "style": {"type": "string", "description": "Style: pixel_art_16, pixel_art_32, cartoon, realistic", "default": "pixel_art_32"},
                    "remove_bg": {"type": "boolean", "default": True, "description": "Remove white background"},
                    "seamless": {"type": "boolean", "default": False, "description": "Make tile seamlessly repeatable"},
                    "seed": {"type": "integer", "default": 42, "description": "Random seed for reproducibility"}
                }
            }
        },
        "required": ["project_path", "sprite_name", "sprite_config"],
    },
    function=generate_sprite_with_alpha,
    category="godot",
)

GODOT_GENERATE_TILESET_AI_DEF = ToolDefinition(
    name="godot_generate_tileset_ai",
    description="""Generate a coherent tileset with multiple tiles.

Creates a full set of tiles for a specific theme with consistent style.
Themes: platformer, dungeon, forest, desert, ice

All tiles use the same seed base for visual consistency.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "tileset_name": {"type": "string", "description": "Name for the tileset"},
            "tileset_config": {
                "type": "object",
                "description": "Tileset configuration",
                "properties": {
                    "style": {"type": "string", "description": "Style: pixel_art_16, pixel_art_32, cartoon, realistic", "default": "pixel_art_32"},
                    "theme": {"type": "string", "description": "Theme: platformer, dungeon, forest, desert, ice", "default": "platformer"},
                    "tiles": {"type": "array", "items": {"type": "string"}, "description": "Custom list of tile names (optional)"},
                    "seed": {"type": "integer", "default": 42, "description": "Random seed for consistency"},
                    "seamless": {"type": "boolean", "default": True, "description": "Make all tiles seamless"}
                }
            }
        },
        "required": ["project_path", "tileset_name", "tileset_config"],
    },
    function=generate_tileset_ai,
    category="godot",
)

GODOT_ANALYZE_TILE_NEEDS_DEF = ToolDefinition(
    name="godot_analyze_tile_needs",
    description="""Analyze what tiles need to be generated based on game requirements.

Returns a TileManifest describing all needed tiles, characters, and objects.""",
    parameters={
        "type": "object",
        "properties": {
            "game_config": {
                "type": "object",
                "description": "Game configuration",
                "properties": {
                    "game_type": {"type": "string", "description": "Type: platformer, rpg, puzzle, etc.", "default": "platformer"},
                    "environment": {"type": "string", "description": "Environment: forest, dungeon, space, etc.", "default": "forest"},
                    "characters": {"type": "array", "items": {"type": "string"}, "description": "List of character names"},
                    "objects": {"type": "array", "items": {"type": "string"}, "description": "List of object types"},
                    "style": {"type": "string", "description": "Style: pixel_art_16, pixel_art_32, cartoon, realistic", "default": "pixel_art_32"}
                }
            }
        },
        "required": ["game_config"],
    },
    function=analyze_tile_needs,
    category="godot",
)


def register_ai_art_tools(registry: ToolRegistry) -> None:
    """Register all AI art tools with a registry."""
    registry.register(GODOT_GENERATE_SPRITE_AI_DEF)
    registry.register(GODOT_GENERATE_TEXTURE_AI_DEF)
    registry.register(GODOT_GENERATE_CHARACTER_AI_DEF)
    registry.register(GODOT_GENERATE_MUSIC_AI_DEF)
    registry.register(GODOT_CREATE_TILE_DEF)
    registry.register(GODOT_CREATE_MARIO_BRICK_DEF)
    # New tile workflow tools
    registry.register(GODOT_GENERATE_SPRITE_ALPHA_DEF)
    registry.register(GODOT_GENERATE_TILESET_AI_DEF)
    registry.register(GODOT_ANALYZE_TILE_NEEDS_DEF)
