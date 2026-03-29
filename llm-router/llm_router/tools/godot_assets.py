"""Asset generation tools for Godot games - sprites, sounds, and animations.

Also includes Kenney.nl asset pack downloader for CC0 licensed game assets.
"""

import asyncio
import base64
import io
import math
import os
import re
import struct
import zipfile
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime

import httpx

from llm_router.tools import ToolDefinition, ToolRegistry

# Optional: PIL for image processing
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# =============================================================================
# KENNEY.NL ASSET PACK DOWNLOADER
# =============================================================================

KENNEY_FEED_URL = "https://kenney.nl/feed"
KENNEY_ASSET_URL = "https://kenney.nl/assets/{slug}"
KENNEY_DOWNLOAD_URL = "https://kenney.nl/assets/{slug}/download"

# Cache for Kenney assets to avoid repeated fetches
_kenney_assets_cache: list[dict] | None = None
_kenney_cache_time: datetime | None = None
CACHE_TTL_SECONDS = 3600  # 1 hour cache


async def _fetch_kenney_feed() -> list[dict]:
    """
    Fetch and parse the Kenney.nl RSS feed.

    Returns list of assets with:
    - name: Asset pack name
    - slug: URL slug for downloading
    - category: Asset category (2D, 3D, Audio, Textures, UI, Pixel)
    - url: Full URL to asset page
    - date: Release date
    """
    global _kenney_assets_cache, _kenney_cache_time

    # Check cache
    now = datetime.now()
    if _kenney_assets_cache and _kenney_cache_time:
        if (now - _kenney_cache_time).total_seconds() < CACHE_TTL_SECONDS:
            return _kenney_assets_cache

    assets = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(KENNEY_FEED_URL)
        response.raise_for_status()
        content = response.text

        # Parse RSS 2.0 feed - items are between <item> tags
        # Split into items using regex that handles CDATA sections
        items = re.split(r'<item>', content, flags=re.IGNORECASE)

        for item in items[1:]:  # Skip first split (header)
            asset = {}

            # Extract title
            title_match = re.search(r'<title>([^<]+)</title>', item, re.IGNORECASE)
            if title_match:
                asset['name'] = title_match.group(1).strip()

            # Extract link
            link_match = re.search(r'<link>([^<]+)</link>', item, re.IGNORECASE)
            if link_match:
                url = link_match.group(1).strip()
                asset['url'] = url
                # Extract slug from URL
                slug_match = re.search(r'/assets/([^/]+)/?$', url)
                if slug_match:
                    asset['slug'] = slug_match.group(1)

            # Extract guid as backup slug
            guid_match = re.search(r'<guid[^>]*>([^<]+)</guid>', item, re.IGNORECASE)
            if guid_match and not asset.get('slug'):
                asset['slug'] = guid_match.group(1).strip()

            # Extract category - Kenney uses explicit <category> tags
            cat_match = re.search(r'<category>([^<]+)</category>', item, re.IGNORECASE)
            if cat_match:
                asset['category'] = cat_match.group(1).strip()
            else:
                # Fallback: infer from description
                if '3D' in item:
                    asset['category'] = "3D"
                elif 'Audio' in item.lower():
                    asset['category'] = "Audio"
                elif 'Texture' in item.lower():
                    asset['category'] = "Textures"
                else:
                    asset['category'] = "2D"

            # Extract date
            date_match = re.search(r'<pubDate>([^<]+)</pubDate>', item, re.IGNORECASE)
            if date_match:
                asset['date'] = date_match.group(1).strip()

            if asset.get('name') and asset.get('slug'):
                assets.append(asset)

    # Update cache
    _kenney_assets_cache = assets
    _kenney_cache_time = now

    return assets


async def _download_kenney_zip(slug: str, target_path: Path) -> Path:
    """
    Download a Kenney.nl asset pack ZIP file.

    Args:
        slug: Asset pack slug (e.g., "new-platformer-pack")
        target_path: Directory to save the ZIP file

    Returns:
        Path to the downloaded ZIP file
    """
    target_path.mkdir(parents=True, exist_ok=True)
    zip_path = target_path / f"{slug}.zip"

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        # First, get the asset page to find the download link
        asset_url = KENNEY_ASSET_URL.format(slug=slug)
        page_response = await client.get(asset_url)

        if page_response.status_code != 200:
            raise Exception(f"Failed to get asset page: HTTP {page_response.status_code}")

        page_content = page_response.text

        # Find the download link in the page
        # Pattern: href='https://kenney.nl/media/pages/assets/{slug}/{hash}/kenney_{slug}-{version}.zip'
        dl_match = re.search(
            r"href='(https://kenney\.nl/media/pages/assets/[^']+\.zip)'",
            page_content
        )

        if not dl_match:
            # Try with double quotes
            dl_match = re.search(
                r'href="(https://kenney\.nl/media/pages/assets/[^"]+\.zip)"',
                page_content
            )

        if not dl_match:
            raise Exception(f"Could not find download link for asset: {slug}")

        download_url = dl_match.group(1)

        # Download the ZIP file
        response = await client.get(download_url)

        if response.status_code != 200:
            raise Exception(f"Failed to download ZIP: HTTP {response.status_code}")

        # Save ZIP file
        zip_path.write_bytes(response.content)

    return zip_path


async def godot_list_kenney_assets(
    category: str = None
) -> dict:
    """
    List available asset packs from Kenney.nl.

    Kenney.nl provides CC0 (Creative Commons Zero) licensed game assets -
    completely free, no attribution required.

    Args:
        category: Filter by category: "2D", "3D", "Audio", "Textures", "UI", "Pixel", or None for all

    Returns:
        Dict with:
        - success: bool
        - assets: List of asset packs
        - count: Number of assets returned
    """
    try:
        assets = await _fetch_kenney_feed()

        # Filter by category if specified
        if category:
            category_upper = category.upper()
            assets = [a for a in assets if a.get('category', '').upper() == category_upper]

        return {
            "success": True,
            "assets": assets,
            "count": len(assets),
            "message": f"Found {len(assets)} Kenney.nl asset packs" + (f" in category '{category}'" if category else ""),
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "assets": [],
            "count": 0,
        }


async def godot_search_kenney_assets(
    query: str
) -> dict:
    """
    Search Kenney.nl asset packs by keyword.

    Searches asset pack names for the given query (case-insensitive).

    Args:
        query: Search keyword (e.g., "platformer", "space", "car", "dungeon")

    Returns:
        Dict with:
        - success: bool
        - assets: List of matching asset packs
        - count: Number of matches
        - query: The search query used
    """
    try:
        assets = await _fetch_kenney_feed()

        # Search in name (case-insensitive)
        query_lower = query.lower()
        matches = [
            a for a in assets
            if query_lower in a.get('name', '').lower() or
               query_lower in a.get('slug', '').lower()
        ]

        # Sort by relevance (exact match first, then starts with, then contains)
        def relevance(asset):
            name = asset.get('name', '').lower()
            slug = asset.get('slug', '').lower()
            if name == query_lower or slug == query_lower:
                return 0
            if name.startswith(query_lower) or slug.startswith(query_lower):
                return 1
            return 2

        matches.sort(key=relevance)

        return {
            "success": True,
            "assets": matches,
            "count": len(matches),
            "query": query,
            "message": f"Found {len(matches)} asset packs matching '{query}'",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "assets": [],
            "count": 0,
            "query": query,
        }


async def godot_download_kenney_asset(
    project_path: str,
    asset_slug: str,
    target_folder: str = "assets/kenney"
) -> dict:
    """
    Download a Kenney.nl asset pack and extract it into a Godot project.

    Downloads ZIP from Kenney.nl and extracts to the specified folder.
    All assets are CC0 licensed - free to use, no attribution required.

    Args:
        project_path: Path to the Godot project
        asset_slug: Asset pack slug (e.g., "new-platformer-pack", "pirate-kit")
        target_folder: Where to extract within the project (default: "assets/kenney")

    Returns:
        Dict with:
        - success: bool
        - asset_slug: The downloaded asset slug
        - target_path: Where files were extracted
        - files_extracted: Number of files
        - resource_prefix: res:// path for use in Godot
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        # Create target directory
        target_path = project_dir / target_folder / asset_slug
        target_path.mkdir(parents=True, exist_ok=True)

        # Download ZIP to temp location
        temp_dir = Path(tempfile.mkdtemp())
        try:
            zip_path = await _download_kenney_zip(asset_slug, temp_dir)

            # Extract ZIP
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Check if ZIP contains a root folder
                namelist = zf.namelist()
                has_root_folder = all(n.startswith(namelist[0].split('/')[0] + '/') for n in namelist if '/' in n)

                if has_root_folder:
                    # Extract to parent, then rename
                    zf.extractall(temp_dir)
                    extracted_folder = temp_dir / namelist[0].split('/')[0]

                    # Move contents to target
                    if extracted_folder.exists() and extracted_folder.is_dir():
                        for item in extracted_folder.iterdir():
                            dest = target_path / item.name
                            if dest.exists():
                                if dest.is_dir():
                                    import shutil
                                    shutil.rmtree(dest)
                                else:
                                    dest.unlink()
                            item.rename(dest)
                else:
                    # Extract directly to target
                    zf.extractall(target_path)

        finally:
            # Cleanup temp directory
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

        # Count files
        files = list(target_path.rglob("*"))
        file_count = len([f for f in files if f.is_file()])

        # Generate resource prefix
        resource_prefix = f"res://{target_folder}/{asset_slug}/"

        return {
            "success": True,
            "asset_slug": asset_slug,
            "target_path": str(target_path),
            "files_extracted": file_count,
            "resource_prefix": resource_prefix,
            "message": f"Downloaded and extracted '{asset_slug}' ({file_count} files) to {target_path}",
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "asset_slug": asset_slug,
        }


# =============================================================================
# GODOT RESOURCE GENERATION (TileSet, SpriteFrames)
# =============================================================================

def create_tileset_resource(
    project_path: str,
    tileset_name: str,
    tiles: list[dict],
    tile_size: list[int] = None,
    output_path: str = None
) -> dict:
    """Create a Godot TileSet resource file (.tres).

    Generates a .tres file that can be loaded by Godot's TileMap node.

    Args:
        project_path: Path to the Godot project
        tileset_name: Name for the tileset
        tiles: List of tile definitions, each with:
            - name: Tile name
            - texture_path: res:// path to the tile texture
            - shape: (optional) Collision shape type: "rectangle", "none"
            - z_index: (optional) Z-ordering
        tile_size: [width, height] for all tiles (auto-detected if None)
        output_path: Custom output path (default: assets/tilesets/)

    Returns:
        Dict with tileset info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        if not tiles:
            return {"error": "At least one tile is required"}

        # Determine output path
        if output_path:
            tileset_dir = project_dir / output_path
        else:
            tileset_dir = project_dir / "assets" / "tilesets"
        tileset_dir.mkdir(parents=True, exist_ok=True)

        # Auto-detect tile size if not provided
        if not tile_size:
            tile_size = [32, 32]

        # Generate UID-like string (simplified)
        uid = f"tileset_{tileset_name}_{hash(tileset_name) % 1000000:06d}"

        # Build the .tres content
        ext_resources = []
        tile_definitions = []

        for i, tile in enumerate(tiles):
            tile_name = tile.get("name", f"tile_{i}")
            texture_path = tile.get("texture_path", "")
            shape = tile.get("shape", "none")
            z_index = tile.get("z_index", 0)

            # Add external resource reference
            ext_resources.append(
                f'[ext_resource type="Texture2D" path="{texture_path}" id="tex_{i}"]'
            )

            # Build tile definition
            tile_def = f'''{i}: {{
"id": {i},
"name": "{tile_name}",
"texture": ExtResource("tex_{i}"),
"tex_offset": Vector2i(0, 0),
"modulate": Color(1, 1, 1, 1),
"z_index": {z_index},
"y_sort_origin": 0,
"probability": 1.0,
"occluder": null,
"physics": {{"linear_velocity": Vector2(0, 0), "angular_velocity": 0.0, "polygons": []}},
"custom_data": []
}}'''
            tile_definitions.append(tile_def)

        # Build complete .tres file
        tres_content = f'''[gd_resource type="TileSet" load_steps={len(tiles) + 2} format=3 uid="uid://{uid}"]

{chr(10).join(ext_resources)}

[resource]
tile_size = Vector2i({tile_size[0]}, {tile_size[1]})
tile_shape = 1
tile_layout = 0
tile_offset_axis = 0
tile_render_shape = 0
sources = [{{
"id": 0,
"name": "{tileset_name}",
"atlas": ExtResource("tex_0"),
"texture_region_size": Vector2i({tile_size[0]}, {tile_size[1]}),
"margin": Vector2i(0, 0),
"separation": Vector2i(0, 0),
"texture_origin": Vector2i(0, 0),
"tiles": {{
{chr(10).join("    " + t + "," for t in tile_definitions)}
}}
}}]
'''

        # Save the file
        tres_path = tileset_dir / f"{tileset_name}.tres"
        tres_path.write_text(tres_content)

        return {
            "success": True,
            "tileset_name": tileset_name,
            "tileset_path": str(tres_path),
            "resource_path": f"res://assets/tilesets/{tileset_name}.tres",
            "tile_count": len(tiles),
            "tile_size": tile_size,
            "tiles": tiles,
            "message": f"Created TileSet '{tileset_name}' with {len(tiles)} tiles"
        }

    except Exception as e:
        return {"error": str(e), "tileset_name": tileset_name}


def create_sprite_frames_resource(
    project_path: str,
    frames_name: str,
    animations: list[dict],
    output_path: str = None
) -> dict:
    """Create a Godot SpriteFrames resource file (.tres) for animated characters.

    Generates a .tres file that can be used with AnimatedSprite2D nodes.

    Args:
        project_path: Path to the Godot project
        frames_name: Name for the SpriteFrames resource
        animations: List of animation definitions, each with:
            - name: Animation name (e.g., "idle", "walk", "jump")
            - frames: List of res:// paths to frame textures
            - speed: Animation speed (FPS, default: 5.0)
            - loop: Whether to loop (default: True)
        output_path: Custom output path (default: assets/animations/)

    Returns:
        Dict with SpriteFrames info or error
    """
    try:
        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        if not animations:
            return {"error": "At least one animation is required"}

        # Determine output path
        if output_path:
            frames_dir = project_dir / output_path
        else:
            frames_dir = project_dir / "assets" / "animations"
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Generate UID
        uid = f"sprframes_{frames_name}_{hash(frames_name) % 1000000:06d}"

        # Build external resources and animation definitions
        ext_resources = []
        ext_resource_counter = 0
        anim_defs = []

        for anim in animations:
            anim_name = anim.get("name", "default")
            frame_paths = anim.get("frames", [])
            speed = anim.get("speed", 5.0)
            loop = anim.get("loop", True)

            frame_refs = []
            for frame_path in frame_paths:
                ext_id = f"frame_{ext_resource_counter}"
                ext_resources.append(
                    f'[ext_resource type="Texture2D" path="{frame_path}" id="{ext_id}"]'
                )
                frame_refs.append(f'ExtResource("{ext_id}")')
                ext_resource_counter += 1

            # Build animation definition
            frames_list = ", ".join(frame_refs) if frame_refs else ""
            anim_def = f'''{{
"frames": [{frames_list}],
"loop": {"true" if loop else "false"},
"name": &"{anim_name}",
"speed": {speed}
}}'''
            anim_defs.append(anim_def)

        # Calculate load_steps (1 main + external resources)
        load_steps = 1 + len(ext_resources)

        # Build complete .tres file
        tres_content = f'''[gd_resource type="SpriteFrames" load_steps={load_steps} format=3 uid="uid://{uid}"]

{chr(10).join(ext_resources)}

[resource]
animations = [
{chr(10).join("    " + a + "," for a in anim_defs)}
]
'''

        # Save the file
        tres_path = frames_dir / f"{frames_name}_frames.tres"
        tres_path.write_text(tres_content)

        # Calculate total frame count
        total_frames = sum(len(a.get("frames", [])) for a in animations)

        return {
            "success": True,
            "frames_name": frames_name,
            "frames_path": str(tres_path),
            "resource_path": f"res://assets/animations/{frames_name}_frames.tres",
            "animation_count": len(animations),
            "total_frames": total_frames,
            "animations": animations,
            "message": f"Created SpriteFrames '{frames_name}' with {len(animations)} animations ({total_frames} frames total)"
        }

    except Exception as e:
        return {"error": str(e), "frames_name": frames_name}


async def generate_animated_character(
    project_path: str,
    character_name: str,
    character_config: dict
) -> dict:
    """Generate an animated character with AI-generated sprites and SpriteFrames resource.

    This is a high-level function that:
    1. Generates sprite frames for each animation
    2. Creates a sprite sheet
    3. Generates a Godot SpriteFrames resource

    Args:
        project_path: Path to the Godot project
        character_name: Name for the character
        character_config: Configuration with:
            - prompt: Base description of the character
            - animations: List of animation configs with name and frame_count
            - style: pixel_art_16, pixel_art_32, cartoon, realistic
            - size: [width, height] for each frame
            - seed: Random seed for consistency

    Returns:
        Dict with character info or error
    """
    try:
        # Import here to avoid circular imports
        from llm_router.tools.ai_art import (
            generate_sprite_with_alpha,
            create_sprite_sheet
        )
        if not HAS_PIL:
            return {"error": "PIL/Pillow not installed. Run: pip install Pillow"}

        project_dir = Path(project_path)
        if not project_dir.exists():
            return {"error": f"Project not found: {project_path}"}

        base_prompt = character_config.get("prompt", character_name)
        animations = character_config.get("animations", [
            {"name": "idle", "frame_count": 4},
            {"name": "walk", "frame_count": 4}
        ])
        style = character_config.get("style", "pixel_art_32")
        size = character_config.get("size", [32, 32])
        seed = character_config.get("seed", 42)

        # Create character directory
        char_dir = project_dir / "assets" / "characters" / character_name
        char_dir.mkdir(parents=True, exist_ok=True)

        # Generate all animation frames
        all_animations = []
        all_frames = []

        for anim in animations:
            anim_name = anim.get("name", "idle")
            frame_count = anim.get("frame_count", 4)

            anim_frames = []
            anim_paths = []

            for frame_idx in range(frame_count):
                # Create prompt for this animation frame
                frame_prompt = f"{base_prompt}, {anim_name} animation pose {frame_idx + 1} of {frame_count}"

                # Generate sprite
                result = await generate_sprite_with_alpha(
                    project_path,
                    f"characters/{character_name}/{anim_name}_{frame_idx:02d}",
                    {
                        "prompt": frame_prompt,
                        "size": size,
                        "style": style,
                        "remove_bg": True,
                        "seamless": False,
                        "seed": seed + hash(anim_name) + frame_idx
                    }
                )

                if result.get("success"):
                    frame_path = result["sprite_path"]
                    anim_paths.append(result["resource_path"])

                    # Load frame for sprite sheet
                    from PIL import Image
                    frame_img = Image.open(frame_path)
                    anim_frames.append(frame_img)
                    all_frames.append(frame_img)
                else:
                    print(f"Warning: Failed to generate frame {frame_idx} for {anim_name}")

            if anim_frames:
                all_animations.append({
                    "name": anim_name,
                    "frames": anim_paths,
                    "speed": anim.get("speed", 5.0),
                    "loop": anim.get("loop", True)
                })

        if not all_frames:
            return {"error": "Failed to generate any animation frames"}

        # Create sprite sheet
        sprite_sheet, metadata = create_sprite_sheet(all_frames)
        if sprite_sheet:
            sheet_path = char_dir / f"{character_name}_spritesheet.png"
            sprite_sheet.save(sheet_path, "PNG")

        # Create SpriteFrames resource
        frames_result = create_sprite_frames_resource(
            project_path,
            character_name,
            all_animations
        )

        return {
            "success": True,
            "character_name": character_name,
            "character_dir": str(char_dir),
            "animations": all_animations,
            "animation_count": len(all_animations),
            "total_frames": len(all_frames),
            "sprite_sheet": str(sheet_path) if sprite_sheet else None,
            "sprite_frames_resource": frames_result.get("resource_path"),
            "style": style,
            "size": size,
            "message": f"Generated animated character '{character_name}' with {len(all_animations)} animations"
        }

    except Exception as e:
        return {"error": str(e), "character_name": character_name}


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

    # Dungeon Crawler sprites
    elif sprite_type == "dungeon_wall":
        # Stone wall texture pattern
        body = f'<rect x="0" y="0" width="{width}" height="{height}" fill="{color}"/>'
        # Add brick pattern
        brick_h = height // 4
        brick_w = width // 2
        for row in range(4):
            y = row * brick_h
            offset = (row % 2) * (brick_w // 2)
            for col in range(-1, 3):
                x = col * brick_w + offset
                body += f'<rect x="{x}" y="{y}" width="{brick_w-2}" height="{brick_h-2}" fill="none" stroke="#333344" stroke-width="1"/>'

    elif sprite_type == "dungeon_wall_left":
        # Left-facing wall perspective
        body = f'<polygon points="0,0 {width},0 {width*0.7},{height} 0,{height}" fill="{color}"/>'
        # Add brick lines
        for i in range(1, 4):
            y = i * height // 4
            body += f'<line x1="0" y1="{y}" x2="{width - width*0.3*i/4}" y2="{y}" stroke="#333344" stroke-width="2"/>'

    elif sprite_type == "dungeon_wall_right":
        # Right-facing wall perspective
        body = f'<polygon points="0,0 {width},0 {width},{height} {width*0.3},{height}" fill="{color}"/>'
        for i in range(1, 4):
            y = i * height // 4
            body += f'<line x1="{width*0.3*i/4}" y1="{y}" x2="{width}" y2="{y}" stroke="#333344" stroke-width="2"/>'

    elif sprite_type == "dungeon_floor":
        # Floor tile with perspective
        body = f'<polygon points="0,0 {width},0 {width*0.8},{height} {width*0.2},{height}" fill="{color}"/>'
        # Add tile lines
        body += f'<line x1="0" y1="0" x2="{width*0.2}" y2="{height}" stroke="#222233" stroke-width="1"/>'
        body += f'<line x1="{width}" y1="0" x2="{width*0.8}" y2="{height}" stroke="#222233" stroke-width="1"/>'

    elif sprite_type == "dungeon_door":
        # Wooden door
        door_w = width * 0.7
        door_h = height * 0.85
        door_x = (width - door_w) / 2
        door_y = height * 0.05
        body = f'<rect x="{door_x}" y="{door_y}" width="{door_w}" height="{door_h}" fill="#8b4513"/>'
        # Door frame
        body += f'<rect x="{door_x-3}" y="{door_y-3}" width="{door_w+6}" height="6" fill="#4a3520"/>'
        body += f'<rect x="{door_x-3}" y="{door_y+door_h-3}" width="{door_w+6}" height="6" fill="#4a3520"/>'
        # Door handle
        body += f'<circle cx="{door_x+door_w*0.8}" cy="{door_y+door_h*0.5}" r="{door_w*0.08}" fill="#ffd700"/>'
        # Wood grain lines
        for i in range(3):
            line_y = door_y + door_h * (i + 1) / 4
            body += f'<line x1="{door_x+5}" y1="{line_y}" x2="{door_x+door_w-5}" y2="{line_y}" stroke="#6b3510" stroke-width="1"/>'

    elif sprite_type == "dungeon_door_open":
        # Open door frame
        body = f'<rect x="0" y="0" width="{width*0.15}" height="{height}" fill="#4a3520"/>'
        body += f'<rect x="{width*0.85}" y="0" width="{width*0.15}" height="{height}" fill="#4a3520"/>'
        body += f'<rect x="0" y="0" width="{width}" height="{height*0.08}" fill="#4a3520"/>'

    elif sprite_type == "dungeon_stairs":
        # Stairs going down
        num_steps = 4
        step_w = width * 0.6
        step_h = height / num_steps
        body = ""  # Initialize body
        for i in range(num_steps):
            y = i * step_h
            x = (width - step_w) / 2 + i * (step_w * 0.1)
            w = step_w - i * (step_w * 0.2)
            shade = 0.5 + i * 0.1
            step_color = f"rgb({int(100*shade)},{int(100*shade)},{int(120*shade)})"
            body += f'<rect x="{x}" y="{y}" width="{w}" height="{step_h-2}" fill="{step_color}"/>'

    elif sprite_type == "dungeon_chest":
        # Treasure chest
        chest_w = width * 0.8
        chest_h = height * 0.6
        chest_x = (width - chest_w) / 2
        chest_y = height * 0.35
        # Base
        body = f'<rect x="{chest_x}" y="{chest_y}" width="{chest_w}" height="{chest_h}" fill="#8b4513" rx="3"/>'
        # Lid
        body += f'<rect x="{chest_x}" y="{chest_y-height*0.15}" width="{chest_w}" height="{chest_h*0.4}" fill="#a0522d" rx="5"/>'
        # Lock
        lock_w = chest_w * 0.15
        lock_h = chest_h * 0.3
        body += f'<rect x="{width/2-lock_w/2}" y="{chest_y+chest_h*0.3}" width="{lock_w}" height="{lock_h}" fill="#ffd700" rx="2"/>'
        # Bands
        body += f'<rect x="{chest_x}" y="{chest_y}" width="4" height="{chest_h}" fill="#4a3520"/>'
        body += f'<rect x="{chest_x+chest_w-4}" y="{chest_y}" width="4" height="{chest_h}" fill="#4a3520"/>'

    elif sprite_type == "potion_health":
        # Health potion (red)
        body = f'<ellipse cx="{cx}" cy="{height*0.7}" rx="{width*0.3}" ry="{height*0.25}" fill="#aa2222"/>'
        body += f'<rect x="{cx-width*0.15}" y="{height*0.2}" width="{width*0.3}" height="{height*0.5}" fill="#cc3333" rx="3"/>'
        body += f'<ellipse cx="{cx}" cy="{height*0.2}" rx="{width*0.15}" ry="{height*0.08}" fill="#dd4444"/>'
        # Cork
        body += f'<rect x="{cx-width*0.1}" y="{height*0.05}" width="{width*0.2}" height="{height*0.15}" fill="#8b4513"/>'

    elif sprite_type == "potion_mana":
        # Mana potion (blue)
        body = f'<ellipse cx="{cx}" cy="{height*0.7}" rx="{width*0.3}" ry="{height*0.25}" fill="#2222aa"/>'
        body += f'<rect x="{cx-width*0.15}" y="{height*0.2}" width="{width*0.3}" height="{height*0.5}" fill="#3333cc" rx="3"/>'
        body += f'<ellipse cx="{cx}" cy="{height*0.2}" rx="{width*0.15}" ry="{height*0.08}" fill="#4444dd"/>'
        body += f'<rect x="{cx-width*0.1}" y="{height*0.05}" width="{width*0.2}" height="{height*0.15}" fill="#8b4513"/>'

    elif sprite_type == "key":
        # Dungeon key
        body = f'<circle cx="{cx}" cy="{height*0.3}" r="{width*0.25}" fill="#ffd700" stroke="#cc9900" stroke-width="2"/>'
        body += f'<circle cx="{cx}" cy="{height*0.3}" r="{width*0.1}" fill="#cc9900"/>'
        body += f'<rect x="{cx-width*0.08}" y="{height*0.4}" width="{width*0.16}" height="{height*0.5}" fill="#ffd700"/>'
        body += f'<rect x="{cx}" y="{height*0.6}" width="{width*0.2}" height="{width*0.1}" fill="#ffd700"/>'
        body += f'<rect x="{cx}" y="{height*0.75}" width="{width*0.15}" height="{width*0.1}" fill="#ffd700"/>'

    elif sprite_type == "gold_coins":
        # Gold coin pile
        body = ""  # Initialize body
        for i in range(3):
            offset_x = (i - 1) * width * 0.2
            offset_y = abs(i - 1) * height * 0.1
            body += f'<ellipse cx="{cx+offset_x}" cy="{cy+offset_y}" rx="{width*0.25}" ry="{height*0.15}" fill="#ffd700" stroke="#cc9900" stroke-width="1"/>'

    elif sprite_type == "spell_fireball":
        # Fireball spell icon
        body = f'<circle cx="{cx}" cy="{cy}" r="{min(width,height)*0.4}" fill="#ff4400"/>'
        body += f'<circle cx="{cx}" cy="{cy}" r="{min(width,height)*0.25}" fill="#ffaa00"/>'
        # Flame effect
        body += f'<ellipse cx="{cx}" cy="{cy-height*0.3}" rx="{width*0.15}" ry="{height*0.25}" fill="#ffcc00" opacity="0.7"/>'

    elif sprite_type == "spell_lightning":
        # Lightning spell icon
        body = f'<rect x="0" y="0" width="{width}" height="{height}" fill="#2222aa" rx="5"/>'
        body += f'<polygon points="{cx-width*0.1},0 {cx+width*0.3},{cy} {cx},{cy} {cx+width*0.1},{height} {cx-width*0.3},{cy} {cx},{cy}" fill="#ffff44"/>'

    elif sprite_type == "spell_heal":
        # Heal spell icon (cross)
        body = f'<rect x="0" y="0" width="{width}" height="{height}" fill="#44aa44" rx="5"/>'
        cross_w = width * 0.2
        cross_h = height * 0.6
        body += f'<rect x="{cx-cross_w/2}" y="{(height-cross_h)/2}" width="{cross_w}" height="{cross_h}" fill="#ffffff"/>'
        body += f'<rect x="{(width-cross_h)/2}" y="{cy-cross_w/2}" width="{cross_h}" height="{cross_w}" fill="#ffffff"/>'

    elif sprite_type == "spell_shield":
        # Shield spell icon
        body = f'<rect x="0" y="0" width="{width}" height="{height}" fill="#4444aa" rx="5"/>'
        body += f'<path d="M {cx} {height*0.1} L {width*0.85} {height*0.3} L {width*0.85} {height*0.6} Q {cx} {height*0.9} {width*0.15} {height*0.6} L {width*0.15} {height*0.3} Z" fill="#aaddff" stroke="#ffffff" stroke-width="2"/>'

    elif sprite_type == "enemy_rat":
        # Small rat enemy
        body = f'<ellipse cx="{cx}" cy="{cy+height*0.2}" rx="{width*0.35}" ry="{height*0.25}" fill="#886644"/>'
        body = f'<ellipse cx="{cx+width*0.2}" cy="{cy-height*0.1}" rx="{width*0.25}" ry="{height*0.2}" fill="#886644"/>'
        # Ears
        body += f'<circle cx="{cx+width*0.35}" cy="{cy-height*0.25}" r="{width*0.08}" fill="#997755"/>'
        body += f'<circle cx="{cx+width*0.15}" cy="{cy-height*0.3}" r="{width*0.08}" fill="#997755"/>'
        # Eye
        body += f'<circle cx="{cx+width*0.3}" cy="{cy-height*0.1}" r="{width*0.05}" fill="#111111"/>'
        # Tail
        body += f'<path d="M {cx-width*0.3} {cy+height*0.3} Q {cx-width*0.5} {cy+height*0.5} {cx-width*0.4} {cy+height*0.45}" stroke="#775533" stroke-width="2" fill="none"/>'

    elif sprite_type == "enemy_goblin":
        # Goblin enemy
        body = f'<ellipse cx="{cx}" cy="{cy+height*0.15}" rx="{width*0.3}" ry="{height*0.35}" fill="#448844"/>'
        # Head
        body += f'<ellipse cx="{cx}" cy="{cy-height*0.2}" rx="{width*0.25}" ry="{height*0.22}" fill="#448844"/>'
        # Ears
        body += f'<polygon points="{cx-width*0.3},{cy-height*0.3} {cx-width*0.45},{cy-height*0.5} {cx-width*0.2},{cy-height*0.35}" fill="#448844"/>'
        body += f'<polygon points="{cx+width*0.3},{cy-height*0.3} {cx+width*0.45},{cy-height*0.5} {cx+width*0.2},{cy-height*0.35}" fill="#448844"/>'
        # Eyes
        body += f'<circle cx="{cx-width*0.1}" cy="{cy-height*0.25}" r="{width*0.06}" fill="#ffcc00"/>'
        body += f'<circle cx="{cx+width*0.1}" cy="{cy-height*0.25}" r="{width*0.06}" fill="#ffcc00"/>'

    elif sprite_type == "enemy_skeleton":
        # Skeleton enemy
        body = f'<ellipse cx="{cx}" cy="{cy+height*0.1}" rx="{width*0.25}" ry="{height*0.35}" fill="#cccccc"/>'
        # Skull
        body += f'<circle cx="{cx}" cy="{cy-height*0.2}" r="{width*0.25}" fill="#dddddd"/>'
        # Eye sockets
        body += f'<circle cx="{cx-width*0.1}" cy="{cy-height*0.25}" r="{width*0.07}" fill="#111111"/>'
        body += f'<circle cx="{cx+width*0.1}" cy="{cy-height*0.25}" r="{width*0.07}" fill="#111111"/>'
        # Nose hole
        body += f'<polygon points="{cx},{cy-height*0.12} {cx-width*0.05},{cy-height*0.08} {cx+width*0.05},{cy-height*0.08}" fill="#111111"/>'
        # Ribs
        for i in range(3):
            y = cy + height * (0.0 + i * 0.15)
            body += f'<line x1="{cx-width*0.2}" y1="{y}" x2="{cx+width*0.2}" y2="{y}" stroke="#aaaaaa" stroke-width="2"/>'

    elif sprite_type == "enemy_orc":
        # Orc enemy - larger, green
        body = f'<ellipse cx="{cx}" cy="{cy+height*0.1}" rx="{width*0.35}" ry="{height*0.4}" fill="#336633"/>'
        # Head
        body += f'<ellipse cx="{cx}" cy="{cy-height*0.25}" rx="{width*0.3}" ry="{height*0.25}" fill="#336633"/>'
        # Tusks
        body += f'<polygon points="{cx-width*0.15},{cy-height*0.05} {cx-width*0.2},{cy-height*0.15} {cx-width*0.1},{cy-height*0.1}" fill="#dddddd"/>'
        body += f'<polygon points="{cx+width*0.15},{cy-height*0.05} {cx+width*0.2},{cy-height*0.15} {cx+width*0.1},{cy-height*0.1}" fill="#dddddd"/>'
        # Eyes
        body += f'<circle cx="{cx-width*0.12}" cy="{cy-height*0.3}" r="{width*0.06}" fill="#ff0000"/>'
        body += f'<circle cx="{cx+width*0.12}" cy="{cy-height*0.3}" r="{width*0.06}" fill="#ff0000"/>'

    elif sprite_type == "enemy_demon":
        # Demon enemy - red, horns
        body = f'<ellipse cx="{cx}" cy="{cy+height*0.1}" rx="{width*0.3}" ry="{height*0.38}" fill="#883333"/>'
        # Head
        body += f'<ellipse cx="{cx}" cy="{cy-height*0.2}" rx="{width*0.25}" ry="{height*0.22}" fill="#aa4444"/>'
        # Horns
        body += f'<polygon points="{cx-width*0.2},{cy-height*0.3} {cx-width*0.35},{cy-height*0.6} {cx-width*0.1},{cy-height*0.35}" fill="#442222"/>'
        body += f'<polygon points="{cx+width*0.2},{cy-height*0.3} {cx+width*0.35},{cy-height*0.6} {cx+width*0.1},{cy-height*0.35}" fill="#442222"/>'
        # Eyes
        body += f'<circle cx="{cx-width*0.1}" cy="{cy-height*0.22}" r="{width*0.07}" fill="#ffff00"/>'
        body += f'<circle cx="{cx+width*0.1}" cy="{cy-height*0.22}" r="{width*0.07}" fill="#ffff00"/>'

    elif sprite_type == "enemy_dragon_boss":
        # Dragon boss - large, wings
        body = f'<ellipse cx="{cx}" cy="{cy+height*0.15}" rx="{width*0.35}" ry="{height*0.35}" fill="#aa2222"/>'
        # Head
        body += f'<ellipse cx="{cx}" cy="{cy-height*0.25}" rx="{width*0.25}" ry="{height*0.2}" fill="#cc3333"/>'
        # Snout
        body += f'<ellipse cx="{cx}" cy="{cy-height*0.15}" rx="{width*0.15}" ry="{height*0.1}" fill="#cc3333"/>'
        # Wings
        body += f'<polygon points="{cx-width*0.35},{cy} {cx-width*0.7},{cy-height*0.3} {cx-width*0.5},{cy+height*0.1} {cx-width*0.3},{cy+height*0.2}" fill="#881111"/>'
        body += f'<polygon points="{cx+width*0.35},{cy} {cx+width*0.7},{cy-height*0.3} {cx+width*0.5},{cy+height*0.1} {cx+width*0.3},{cy+height*0.2}" fill="#881111"/>'
        # Eyes
        body += f'<circle cx="{cx-width*0.1}" cy="{cy-height*0.3}" r="{width*0.06}" fill="#ffff00"/>'
        body += f'<circle cx="{cx+width*0.1}" cy="{cy-height*0.3}" r="{width*0.06}" fill="#ffff00"/>'
        # Nostrils with smoke
        body += f'<circle cx="{cx-width*0.05}" cy="{cy-height*0.1}" r="{width*0.03}" fill="#222222"/>'
        body += f'<circle cx="{cx+width*0.05}" cy="{cy-height*0.1}" r="{width*0.03}" fill="#222222"/>'

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

Sprite types:
- Basic: rectangle, circle, triangle, star, heart, arrow, diamond, hexagon, octagon, cross, ellipse
- Game: player_ship, enemy, bullet, coin, paddle, ball
- Dungeon: dungeon_wall, dungeon_wall_left, dungeon_wall_right, dungeon_floor, dungeon_door, dungeon_door_open, dungeon_stairs, dungeon_chest
- Items: potion_health, potion_mana, key, gold_coins
- Spells: spell_fireball, spell_lightning, spell_heal, spell_shield
- Enemies: enemy_rat, enemy_goblin, enemy_skeleton, enemy_orc, enemy_demon, enemy_dragon_boss

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


# =============================================================================
# KENNEY.NL TOOL DEFINITIONS
# =============================================================================

GODOT_LIST_KENNEY_ASSETS_DEF = ToolDefinition(
    name="godot_list_kenney_assets",
    description="""List available free CC0 game asset packs from Kenney.nl.

Kenney.nl provides thousands of free game assets under Creative Commons Zero license -
completely free to use, no attribution required.

Categories: 2D, 3D, Audio, Textures, UI, Pixel""",
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Filter by category: 2D, 3D, Audio, Textures, UI, Pixel (optional)",
                "enum": ["2D", "3D", "Audio", "Textures", "UI", "Pixel"]
            }
        },
        "required": [],
    },
    function=godot_list_kenney_assets,
    category="godot",
)

GODOT_SEARCH_KENNEY_ASSETS_DEF = ToolDefinition(
    name="godot_search_kenney_assets",
    description="""Search Kenney.nl asset packs by keyword.

Returns matching asset packs sorted by relevance.""",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keyword (e.g., 'platformer', 'space', 'car', 'dungeon')"
            }
        },
        "required": ["query"],
    },
    function=godot_search_kenney_assets,
    category="godot",
)

GODOT_DOWNLOAD_KENNEY_ASSET_DEF = ToolDefinition(
    name="godot_download_kenney_asset",
    description="""Download a Kenney.nl asset pack and extract it into a Godot project.

Downloads the ZIP file and extracts all assets to the project folder.
All assets are CC0 licensed - free to use, no attribution required.

Use godot_list_kenney_assets or godot_search_kenney_assets to find available asset packs.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "Path to the Godot project"
            },
            "asset_slug": {
                "type": "string",
                "description": "Asset pack slug from the list (e.g., 'new-platformer-pack', 'pirate-kit')"
            },
            "target_folder": {
                "type": "string",
                "description": "Where to extract within the project (default: 'assets/kenney')"
            }
        },
        "required": ["project_path", "asset_slug"],
    },
    function=godot_download_kenney_asset,
    category="godot",
)


# =============================================================================
# TILESET AND SPRITEFRAMES TOOL DEFINITIONS
# =============================================================================

GODOT_CREATE_TILESET_DEF = ToolDefinition(
    name="godot_create_tileset",
    description="""Create a Godot TileSet resource file (.tres) for use with TileMap nodes.

Generates a .tres file that can be loaded directly by Godot's TileMap system.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "tileset_name": {"type": "string", "description": "Name for the tileset"},
            "tiles": {
                "type": "array",
                "description": "List of tile definitions",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Tile name"},
                        "texture_path": {"type": "string", "description": "res:// path to tile texture"},
                        "shape": {"type": "string", "description": "Collision shape: rectangle or none"},
                        "z_index": {"type": "integer", "description": "Z-ordering (default: 0)"}
                    }
                }
            },
            "tile_size": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "[width, height] for all tiles"
            },
            "output_path": {"type": "string", "description": "Custom output path (optional)"}
        },
        "required": ["project_path", "tileset_name", "tiles"],
    },
    function=create_tileset_resource,
    category="godot",
)

GODOT_CREATE_SPRITE_FRAMES_DEF = ToolDefinition(
    name="godot_create_sprite_frames",
    description="""Create a Godot SpriteFrames resource file (.tres) for animated characters.

Generates a .tres file for use with AnimatedSprite2D nodes. Supports multiple animations.""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "frames_name": {"type": "string", "description": "Name for the SpriteFrames resource"},
            "animations": {
                "type": "array",
                "description": "List of animation definitions",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Animation name (e.g., 'idle', 'walk')"},
                        "frames": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of res:// paths to frame textures"
                        },
                        "speed": {"type": "number", "description": "Animation speed in FPS (default: 5.0)"},
                        "loop": {"type": "boolean", "description": "Whether to loop (default: true)"}
                    }
                }
            },
            "output_path": {"type": "string", "description": "Custom output path (optional)"}
        },
        "required": ["project_path", "frames_name", "animations"],
    },
    function=create_sprite_frames_resource,
    category="godot",
)

GODOT_GENERATE_ANIMATED_CHARACTER_DEF = ToolDefinition(
    name="godot_generate_animated_character",
    description="""Generate an animated character with AI-generated sprites and SpriteFrames resource.

This is a high-level function that:
1. Generates sprite frames for each animation using AI
2. Creates a sprite sheet
3. Generates a Godot SpriteFrames resource for use with AnimatedSprite2D

Styles: pixel_art_16, pixel_art_32, cartoon, realistic""",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "character_name": {"type": "string", "description": "Name for the character"},
            "character_config": {
                "type": "object",
                "description": "Character configuration",
                "properties": {
                    "prompt": {"type": "string", "description": "Base description of the character"},
                    "animations": {
                        "type": "array",
                        "description": "Animation configs with name and frame_count",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Animation name"},
                                "frame_count": {"type": "integer", "description": "Number of frames"},
                                "speed": {"type": "number", "description": "FPS"},
                                "loop": {"type": "boolean", "description": "Loop animation"}
                            }
                        }
                    },
                    "style": {"type": "string", "description": "Style: pixel_art_16, pixel_art_32, cartoon, realistic", "default": "pixel_art_32"},
                    "size": {"type": "array", "items": {"type": "integer"}, "description": "[width, height] per frame", "default": [32, 32]},
                    "seed": {"type": "integer", "description": "Random seed for consistency", "default": 42}
                }
            }
        },
        "required": ["project_path", "character_name", "character_config"],
    },
    function=generate_animated_character,
    category="godot",
)


def register_godot_asset_tools(registry: ToolRegistry) -> None:
    """Register all Godot asset tools with a registry."""
    registry.register(GODOT_CREATE_SPRITE_DEF)
    registry.register(GODOT_CREATE_SOUND_DEF)
    registry.register(GODOT_CREATE_ANIMATION_DEF)
    # Kenney.nl tools
    registry.register(GODOT_LIST_KENNEY_ASSETS_DEF)
    registry.register(GODOT_SEARCH_KENNEY_ASSETS_DEF)
    registry.register(GODOT_DOWNLOAD_KENNEY_ASSET_DEF)
    # TileSet and SpriteFrames tools
    registry.register(GODOT_CREATE_TILESET_DEF)
    registry.register(GODOT_CREATE_SPRITE_FRAMES_DEF)
    registry.register(GODOT_GENERATE_ANIMATED_CHARACTER_DEF)
