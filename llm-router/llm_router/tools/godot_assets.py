"""Asset generation tools for Godot games - sprites, sounds, and animations."""

import base64
import io
import math
import os
import struct
from pathlib import Path
from typing import Optional

from llm_router.tools import ToolDefinition, ToolRegistry


# =============================================================================
# SPRITE GENERATION (SVG-based)
# =============================================================================

def create_svg_sprite(
    sprite_type: str,
    size: tuple[int, int],
    color: str,
    outline_color: Optional[str] = None,
    outline_width: int = 0,
    rotation: float = 0
) -> str:
    """
    Create an SVG sprite.

    Args:
        sprite_type: rectangle, circle, triangle, star, heart, arrow, diamond, hexagon
        size: (width, height)
        color: Fill color (hex, e.g., "#ff0000")
        outline_color: Optional outline color
        outline_width: Outline width in pixels
        rotation: Rotation in degrees

    Returns:
        SVG content as string
    """
    width, height = size
    cx, cy = width // 2, height // 2

    # Base SVG with rotation transform
    outline_style = f"stroke:{outline_color};stroke-width:{outline_width};" if outline_color else ""
    transform = f' transform="rotate({rotation} {cx} {cy})"' if rotation else ""

    svg_start = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
    svg_end = '</svg>'

    if sprite_type == "rectangle":
        body = f'<rect x="0" y="0" width="{width}" height="{height}" fill="{color}" {outline_style}style="{outline_style}"/>'

    elif sprite_type == "circle":
        radius = min(width, height) // 2
        body = f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{color}" style="{outline_style}"/>'

    elif sprite_type == "ellipse":
        rx, ry = width // 2, height // 2
        body = f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{color}" style="{outline_style}"/>'

    elif sprite_type == "triangle":
        points = f"{cx},0 {width},{height} 0,{height}"
        body = f'<polygon points="{points}" fill="{color}" style="{outline_style}"{transform}/>'

    elif sprite_type == "star":
        # 5-pointed star
        points = _generate_star_points(cx, cy, min(width, height) // 2, min(width, height) // 4, 5)
        body = f'<polygon points="{points}" fill="{color}" style="{outline_style}"{transform}/>'

    elif sprite_type == "heart":
        # Heart shape using path
        scale = min(width, height) / 100
        path = f"M {cx} {height * 0.3} " \
               f"C {cx - 25 * scale} {cy - 40 * scale}, {cx - 50 * scale} {cy}, {cx} {height * 0.8} " \
               f"C {cx + 50 * scale} {cy}, {cx + 25 * scale} {cy - 40 * scale}, {cx} {height * 0.3} Z"
        body = f'<path d="{path}" fill="{color}" style="{outline_style}"{transform}/>'

    elif sprite_type == "arrow":
        # Arrow pointing right
        arrow_w = width * 0.3
        points = f"0,{height * 0.3} {width - arrow_w},{height * 0.3} {width - arrow_w},0 {width},{cy} {width - arrow_w},{height} {width - arrow_w},{height * 0.7} 0,{height * 0.7}"
        body = f'<polygon points="{points}" fill="{color}" style="{outline_style}"{transform}/>'

    elif sprite_type == "diamond":
        points = f"{cx},0 {width},{cy} {cx},{height} 0,{cy}"
        body = f'<polygon points="{points}" fill="{color}" style="{outline_style}"{transform}/>'

    elif sprite_type == "hexagon":
        points = _generate_polygon_points(cx, cy, min(width, height) // 2, 6)
        body = f'<polygon points="{points}" fill="{color}" style="{outline_style}"{transform}/>'

    elif sprite_type == "octagon":
        points = _generate_polygon_points(cx, cy, min(width, height) // 2, 8)
        body = f'<polygon points="{points}" fill="{color}" style="{outline_style}"{transform}/>'

    elif sprite_type == "cross":
        w, h = width * 0.3, height * 0.3
        body = f'<path d="M {cx - w/2} 0 L {cx + w/2} 0 L {cx + w/2} {cy - h/2} L {width} {cy - h/2} L {width} {cy + h/2} L {cx + w/2} {cy + h/2} L {cx + w/2} {height} L {cx - w/2} {height} L {cx - w/2} {cy + h/2} L 0 {cy + h/2} L 0 {cy - h/2} L {cx - w/2} {cy - h/2} Z" fill="{color}" style="{outline_style}"/>'

    elif sprite_type == "player_ship":
        # Simple spaceship shape
        points = f"{cx},0 {width},{height} {cx},{height * 0.7} 0,{height}"
        body = f'<polygon points="{points}" fill="{color}" style="{outline_style}"/>'

    elif sprite_type == "enemy":
        # Simple enemy ship (inverted triangle)
        points = f"0,0 {width},0 {cx},{height}"
        body = f'<polygon points="{points}" fill="{color}" style="{outline_style}"/>'

    elif sprite_type == "bullet":
        # Small bullet/missile
        body = f'<ellipse cx="{cx}" cy="{cy}" rx="{width * 0.3}" ry="{height * 0.5}" fill="{color}" style="{outline_style}"/>'

    elif sprite_type == "coin":
        # Coin with inner circle
        r = min(width, height) // 2
        body = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" style="{outline_style}"/>'
        if r > 5:
            inner_r = r // 2
            body += f'<circle cx="{cx}" cy="{cy}" r="{inner_r}" fill="none" stroke="#ffffff" stroke-width="2" opacity="0.5"/>'

    elif sprite_type == "paddle":
        # Pong paddle
        body = f'<rect x="0" y="0" width="{width}" height="{height}" rx="3" ry="3" fill="{color}" style="{outline_style}"/>'

    elif sprite_type == "ball":
        # Pong ball
        r = min(width, height) // 2
        body = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" style="{outline_style}"/>'
        # Add highlight
        if r > 5:
            body += f'<circle cx="{cx - r//3}" cy="{cy - r//3}" r="{r//4}" fill="#ffffff" opacity="0.3"/>'

    else:
        # Default to rectangle
        body = f'<rect x="0" y="0" width="{width}" height="{height}" fill="{color}" style="{outline_style}"/>'

    return f"{svg_start}<g>{body}</g>{svg_end}"


def _generate_star_points(cx: int, cy: int, outer_r: int, inner_r: int, points: int) -> str:
    """Generate points for a star polygon."""
    coords = []
    angle_step = math.pi / points

    for i in range(points * 2):
        r = outer_r if i % 2 == 0 else inner_r
        angle = i * angle_step - math.pi / 2
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        coords.append(f"{x:.1f},{y:.1f}")

    return " ".join(coords)


def _generate_polygon_points(cx: int, cy: int, r: int, sides: int) -> str:
    """Generate points for a regular polygon."""
    coords = []
    angle_step = 2 * math.pi / sides

    for i in range(sides):
        angle = i * angle_step - math.pi / 2
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        coords.append(f"{x:.1f},{y:.1f}")

    return " ".join(coords)


async def godot_create_sprite(
    project_path: str,
    sprite_name: str,
    sprite_config: dict
) -> dict:
    """
    Create a sprite asset for the game.

    Args:
        project_path: Path to the Godot project
        sprite_name: Name for the sprite file (without extension)
        sprite_config: Sprite configuration

    sprite_config options:
        - type: rectangle, circle, triangle, star, heart, arrow, diamond, hexagon, player_ship, enemy, bullet, coin, paddle, ball
        - size: [width, height] (default: [64, 64])
        - color: Fill color hex (default: "#4488ff")
        - outline_color: Optional outline color
        - outline_width: Outline width in pixels
        - rotation: Rotation in degrees

    Returns:
        Dict with sprite info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        # Extract config
        sprite_type = sprite_config.get("type", "rectangle")
        size = tuple(sprite_config.get("size", [64, 64]))
        color = sprite_config.get("color", "#4488ff")
        outline_color = sprite_config.get("outline_color")
        outline_width = sprite_config.get("outline_width", 0)
        rotation = sprite_config.get("rotation", 0)

        # Create assets directory
        assets_dir = project_dir / "assets" / "sprites"
        assets_dir.mkdir(parents=True, exist_ok=True)

        # Generate SVG
        svg_content = create_svg_sprite(
            sprite_type=sprite_type,
            size=size,
            color=color,
            outline_color=outline_color,
            outline_width=outline_width,
            rotation=rotation
        )

        # Save SVG file
        sprite_file = assets_dir / f"{sprite_name}.svg"
        sprite_file.write_text(svg_content)

        return {
            "success": True,
            "sprite_path": str(sprite_file),
            "sprite_name": sprite_name,
            "sprite_type": sprite_type,
            "size": size,
            "resource_path": f"res://assets/sprites/{sprite_name}.svg",
            "message": f"Created {sprite_type} sprite '{sprite_name}' ({size[0]}x{size[1]})",
        }

    except Exception as e:
        return {"error": str(e), "sprite_name": sprite_name}


# =============================================================================
# SOUND GENERATION (WAV)
# =============================================================================

def create_wav_sound(
    sound_type: str,
    frequency: float,
    duration: float,
    volume: float,
    sample_rate: int = 22050
) -> bytes:
    """
    Create a WAV sound file.

    Args:
        sound_type: beep, tone, noise, explosion, jump, collect, hit, powerup
        frequency: Frequency in Hz
        duration: Duration in seconds
        volume: Volume 0.0 to 1.0
        sample_rate: Audio sample rate

    Returns:
        WAV file content as bytes
    """
    import random

    num_samples = int(sample_rate * duration)
    samples = []

    for i in range(num_samples):
        t = i / sample_rate  # Time in seconds
        progress = i / num_samples  # Progress through sound (0 to 1)

        if sound_type == "beep" or sound_type == "tone":
            # Simple sine wave
            value = math.sin(2 * math.pi * frequency * t)
            # Apply envelope (quick attack, medium decay)
            envelope = min(1.0, (1 - progress) * 4)

        elif sound_type == "square":
            # Square wave (8-bit style)
            value = 1.0 if math.sin(2 * math.pi * frequency * t) > 0 else -1.0
            envelope = min(1.0, (1 - progress) * 3)

        elif sound_type == "noise":
            # White noise
            value = random.uniform(-1, 1)
            envelope = (1 - progress) ** 2

        elif sound_type == "explosion":
            # Low frequency rumble with noise
            base = math.sin(2 * math.pi * 80 * t) * (1 - progress)
            noise = random.uniform(-0.3, 0.3)
            value = base + noise
            envelope = (1 - progress) ** 0.5

        elif sound_type == "jump":
            # Rising frequency sweep
            freq = frequency * (1 + progress * 2)
            value = math.sin(2 * math.pi * freq * t)
            envelope = 1 - progress

        elif sound_type == "collect":
            # Two-tone pickup sound
            freq = frequency if progress < 0.5 else frequency * 1.5
            value = math.sin(2 * math.pi * freq * t)
            envelope = (1 - progress) * 2 if progress < 0.5 else (1 - progress)

        elif sound_type == "hit":
            # Quick impact sound
            value = math.sin(2 * math.pi * frequency * t) * (1 - progress * 4)
            noise = random.uniform(-0.2, 0.2) * (1 - progress)
            value += noise
            envelope = max(0, 1 - progress * 3)

        elif sound_type == "powerup":
            # Rising arpeggio
            freq = frequency * (1 + int(progress * 4) * 0.25)
            value = math.sin(2 * math.pi * freq * t)
            envelope = 1 - progress * 0.5

        elif sound_type == "hurt":
            # Descending tone
            freq = frequency * (1 - progress * 0.5)
            value = math.sin(2 * math.pi * freq * t) + random.uniform(-0.1, 0.1)
            envelope = 1 - progress

        elif sound_type == "victory":
            # Triumphant fanfare (simplified)
            freq = frequency * (1 + int(progress * 3) * 0.33)
            value = math.sin(2 * math.pi * freq * t)
            envelope = min(1.0, progress * 4) * (1 - (progress - 0.5) * 2) if progress > 0.5 else min(1.0, progress * 4)

        else:
            # Default to sine wave
            value = math.sin(2 * math.pi * frequency * t)
            envelope = 1 - progress

        # Apply envelope and volume
        sample = int(value * envelope * volume * 32767)
        sample = max(-32768, min(32767, sample))  # Clamp to 16-bit range
        samples.append(sample)

    # Create WAV file
    return _create_wav_bytes(samples, sample_rate)


def _create_wav_bytes(samples: list[int], sample_rate: int) -> bytes:
    """Create WAV file bytes from sample list."""
    num_samples = len(samples)
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * block_align

    # WAV header
    header = io.BytesIO()
    header.write(b'RIFF')
    header.write(struct.pack('<I', 36 + data_size))  # File size - 8
    header.write(b'WAVE')
    header.write(b'fmt ')
    header.write(struct.pack('<I', 16))  # Format chunk size
    header.write(struct.pack('<H', 1))   # PCM format
    header.write(struct.pack('<H', num_channels))
    header.write(struct.pack('<I', sample_rate))
    header.write(struct.pack('<I', byte_rate))
    header.write(struct.pack('<H', block_align))
    header.write(struct.pack('<H', bits_per_sample))
    header.write(b'data')
    header.write(struct.pack('<I', data_size))

    # Sample data
    for sample in samples:
        header.write(struct.pack('<h', sample))

    return header.getvalue()


async def godot_create_sound(
    project_path: str,
    sound_name: str,
    sound_config: dict
) -> dict:
    """
    Create a sound effect for the game.

    Args:
        project_path: Path to the Godot project
        sound_name: Name for the sound file (without extension)
        sound_config: Sound configuration

    sound_config options:
        - type: beep, tone, square, noise, explosion, jump, collect, hit, powerup, hurt, victory
        - frequency: Hz (default: 440)
        - duration: seconds (default: 0.2)
        - volume: 0.0 to 1.0 (default: 0.5)

    Returns:
        Dict with sound info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        # Extract config
        sound_type = sound_config.get("type", "beep")
        frequency = sound_config.get("frequency", 440)
        duration = sound_config.get("duration", 0.2)
        volume = sound_config.get("volume", 0.5)

        # Clamp values
        frequency = max(20, min(20000, frequency))
        duration = max(0.01, min(5.0, duration))
        volume = max(0.0, min(1.0, volume))

        # Create assets directory
        assets_dir = project_dir / "assets" / "sounds"
        assets_dir.mkdir(parents=True, exist_ok=True)

        # Generate WAV
        wav_data = create_wav_sound(
            sound_type=sound_type,
            frequency=frequency,
            duration=duration,
            volume=volume
        )

        # Save WAV file
        sound_file = assets_dir / f"{sound_name}.wav"
        sound_file.write_bytes(wav_data)

        return {
            "success": True,
            "sound_path": str(sound_file),
            "sound_name": sound_name,
            "sound_type": sound_type,
            "frequency": frequency,
            "duration": duration,
            "resource_path": f"res://assets/sounds/{sound_name}.wav",
            "message": f"Created {sound_type} sound '{sound_name}' ({frequency}Hz, {duration}s)",
        }

    except Exception as e:
        return {"error": str(e), "sound_name": sound_name}


async def godot_create_animation(
    project_path: str,
    animation_name: str,
    frames: list[dict]
) -> dict:
    """
    Create an animated sprite with multiple frames.

    Args:
        project_path: Path to the Godot project
        animation_name: Name for the animation
        frames: List of frame configurations

    Each frame config:
        - sprite_config: See godot_create_sprite
        - duration: Frame duration in seconds

    Returns:
        Dict with animation info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        if not frames:
            return {"error": "At least one frame is required"}

        # Create assets directory
        assets_dir = project_dir / "assets" / "animations"
        assets_dir.mkdir(parents=True, exist_ok=True)

        frame_paths = []
        total_duration = 0

        for i, frame in enumerate(frames):
            sprite_config = frame.get("sprite_config", {})
            duration = frame.get("duration", 0.1)
            total_duration += duration

            # Create sprite for this frame
            sprite_result = await godot_create_sprite(
                project_path=project_path,
                sprite_name=f"{animation_name}_frame_{i:02d}",
                sprite_config=sprite_config
            )

            if "error" in sprite_result:
                return sprite_result

            frame_paths.append({
                "frame": i,
                "path": sprite_result["resource_path"],
                "duration": duration
            })

        # Create SpriteFrames resource file
        frames_content = f'''[gd_resource type="SpriteFrames" format=3]

[resource]
animations = [{{
"frames": [{{
"duration": {frames[0].get("duration", 0.1)},
"texture": null
}}],
"loop": true,
"name": "{animation_name}",
"speed": {len(frames) / total_duration if total_duration > 0 else 10}
}}]
'''

        frames_file = assets_dir / f"{animation_name}.tres"
        frames_file.write_text(frames_content)

        return {
            "success": True,
            "animation_name": animation_name,
            "frame_count": len(frames),
            "total_duration": total_duration,
            "frames": frame_paths,
            "resource_path": f"res://assets/animations/{animation_name}.tres",
            "message": f"Created animation '{animation_name}' with {len(frames)} frames",
        }

    except Exception as e:
        return {"error": str(e), "animation_name": animation_name}


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

GODOT_CREATE_SPRITE_DEF = ToolDefinition(
    name="godot_create_sprite",
    description="""Create a sprite asset for a Godot game.

Sprite types: rectangle, circle, triangle, star, heart, arrow, diamond, hexagon, octagon, cross,
player_ship, enemy, bullet, coin, paddle, ball, ellipse

Sprites are saved as SVG files in assets/sprites/ directory.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "sprite_name": {"type": "string", "description": "Name for the sprite (without extension)"},
            "sprite_config": {
                "type": "object",
                "description": "Sprite configuration",
                "properties": {
                    "type": {"type": "string", "description": "Sprite shape type"},
                    "size": {"type": "array", "items": {"type": "integer"}, "description": "[width, height]"},
                    "color": {"type": "string", "description": "Fill color (hex, e.g., #ff0000)"},
                    "outline_color": {"type": "string", "description": "Outline color (optional)"},
                    "outline_width": {"type": "integer", "description": "Outline width in pixels"},
                    "rotation": {"type": "number", "description": "Rotation in degrees"}
                }
            }
        },
        "required": ["project_path", "sprite_name", "sprite_config"],
    },
    function=godot_create_sprite,
    category="godot",
)

GODOT_CREATE_SOUND_DEF = ToolDefinition(
    name="godot_create_sound",
    description="""Create a sound effect for a Godot game.

Sound types: beep, tone, square, noise, explosion, jump, collect, hit, powerup, hurt, victory

Sounds are saved as WAV files in assets/sounds/ directory.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "sound_name": {"type": "string", "description": "Name for the sound (without extension)"},
            "sound_config": {
                "type": "object",
                "description": "Sound configuration",
                "properties": {
                    "type": {"type": "string", "description": "Sound type (beep, explosion, jump, etc.)"},
                    "frequency": {"type": "number", "description": "Frequency in Hz (20-20000)"},
                    "duration": {"type": "number", "description": "Duration in seconds (0.01-5.0)"},
                    "volume": {"type": "number", "description": "Volume 0.0 to 1.0"}
                }
            }
        },
        "required": ["project_path", "sound_name", "sound_config"],
    },
    function=godot_create_sound,
    category="godot",
)

GODOT_CREATE_ANIMATION_DEF = ToolDefinition(
    name="godot_create_animation",
    description="""Create an animated sprite with multiple frames.

Each frame has a sprite_config (see godot_create_sprite) and duration.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "animation_name": {"type": "string", "description": "Name for the animation"},
            "frames": {
                "type": "array",
                "description": "List of frame configurations",
                "items": {
                    "type": "object",
                    "properties": {
                        "sprite_config": {"type": "object", "description": "Sprite configuration for this frame"},
                        "duration": {"type": "number", "description": "Frame duration in seconds"}
                    }
                }
            }
        },
        "required": ["project_path", "animation_name", "frames"],
    },
    function=godot_create_animation,
    category="godot",
)


def register_godot_asset_tools(registry: ToolRegistry) -> None:
    """Register all Godot asset tools with a registry."""
    registry.register(GODOT_CREATE_SPRITE_DEF)
    registry.register(GODOT_CREATE_SOUND_DEF)
    registry.register(GODOT_CREATE_ANIMATION_DEF)
