"""Blender MCP workflow tools for 3D asset creation.

Complete workflow from text-to-3D generation to Blender import.
"""

import asyncio
import base64
import json
import os
import socket
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime

import httpx

from llm_router.tools import ToolDefinition, ToolRegistry


# Configuration
HUNYUAN_API_URL = os.environ.get("HUNYUAN_API_URL", "http://192.168.0.18:8080")
BLENDER_MCP_HOST = os.environ.get("BLENDER_MCP_HOST", "localhost")
BLENDER_MCP_PORT = int(os.environ.get("BLENDER_MCP_PORT", "9876"))


async def hunyuan_generate_glb(
    text_prompt: Optional[str] = None,
    image_path: Optional[str] = None,
    octree_resolution: int = 256,
    num_inference_steps: int = 5,
    guidance_scale: float = 5.0,
    seed: int = 1234,
    remove_background: bool = True,
    texture: bool = True,
) -> dict:
    """
    Generate a 3D model using Hunyuan3D and return the GLB data.

    Args:
        text_prompt: Text description of the 3D model
        image_path: Optional path to reference image
        octree_resolution: Quality of generation (16-512)
        num_inference_steps: Number of inference steps (1-100)
        guidance_scale: Guidance scale for generation
        seed: Random seed for reproducibility
        remove_background: Whether to remove background from input image
        texture: Whether to generate with texture

    Returns:
        dict with glb_data (bytes), filename, and metadata
    """
    if not text_prompt and not image_path:
        return {"error": "Either text_prompt or image_path is required"}

    # Prepare image data if provided
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

    # Build Gradio API request
    num_chunks = 8000
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
        num_chunks,            # num_chunks
        True,                  # randomize_seed
    ]

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            # Use textured endpoint if texture requested
            endpoint = "/api/textured_shape_generation" if texture else "/api/shape_generation"

            response = await client.post(
                f"{HUNYUAN_API_URL}{endpoint}",
                json={"data": data},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code != 200:
                return {
                    "error": f"Hunyuan3D generation failed: {response.status_code} - {response.text[:500]}"
                }

            result = response.json()

            if "data" not in result:
                return {"error": f"Unexpected response format: {result}"}

            file_info = result["data"][0]

            # Get the generated file path
            if isinstance(file_info, dict) and "path" in file_info:
                glb_path = file_info["path"]
            elif isinstance(file_info, str):
                glb_path = file_info
            else:
                return {"error": f"Unexpected file info format: {file_info}"}

            # Download the GLB file
            file_url = f"{HUNYUAN_API_URL}/file={glb_path}"
            file_response = await client.get(file_url)

            if file_response.status_code != 200:
                return {"error": f"Failed to download generated file: {file_response.status_code}"}

            glb_data = file_response.content

            # Generate filename from prompt
            if text_prompt:
                # Create safe filename from first few words
                safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in text_prompt[:30])
                safe_name = safe_name.strip().replace(" ", "_")
                filename = f"{safe_name}.glb"
            else:
                filename = f"model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.glb"

            return {
                "success": True,
                "glb_data": glb_data,
                "filename": filename,
                "file_size_kb": len(glb_data) // 1024,
                "textured": texture,
            }

    except httpx.ConnectError:
        return {
            "error": f"Cannot connect to Hunyuan3D server at {HUNYUAN_API_URL}"
        }
    except httpx.TimeoutException:
        return {"error": "Hunyuan3D generation timed out"}
    except Exception as e:
        return {"error": f"Hunyuan3D request failed: {str(e)}"}


def check_blender_mcp() -> bool:
    """Check if Blender MCP server is running."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((BLENDER_MCP_HOST, BLENDER_MCP_PORT))
        sock.close()
        return result == 0
    except Exception:
        return False


async def send_to_blender_mcp(command: dict) -> dict:
    """Send a command to Blender MCP server."""
    if not check_blender_mcp():
        return {"error": "Blender MCP server not running. Start Blender with MCP addon."}

    try:
        reader, writer = await asyncio.open_connection(
            BLENDER_MCP_HOST, BLENDER_MCP_PORT
        )

        # Send command
        message = json.dumps(command) + "\n"
        writer.write(message.encode())
        await writer.drain()

        # Read response
        response_data = await reader.readline()
        writer.close()
        await writer.wait_closed()

        return json.loads(response_data.decode())
    except Exception as e:
        return {"error": f"Failed to communicate with Blender MCP: {str(e)}"}


async def text_to_3d_blender(
    text_prompt: str,
    output_dir: Optional[str] = None,
    import_to_blender: bool = True,
    texture: bool = True,
    octree_resolution: int = 256,
) -> dict:
    """
    Complete workflow: Generate 3D model from text and import to Blender.

    This tool:
    1. Generates a 3D model using Hunyuan3D
    2. Saves the GLB file to disk
    3. Optionally imports to Blender via MCP

    Args:
        text_prompt: Text description of the 3D model to generate
        output_dir: Directory to save the GLB file (default: ./output/3d)
        import_to_blender: Whether to import directly to Blender
        texture: Whether to generate with texture
        octree_resolution: Quality of generation (128-512)

    Returns:
        dict with status, file path, and Blender import status
    """
    # Generate the 3D model
    gen_result = await hunyuan_generate_glb(
        text_prompt=text_prompt,
        octree_resolution=octree_resolution,
        texture=texture,
    )

    if not gen_result.get("success"):
        return gen_result

    # Determine output directory
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = Path.cwd() / "output" / "3d"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save the GLB file
    output_path = out_dir / gen_result["filename"]
    with open(output_path, "wb") as f:
        f.write(gen_result["glb_data"])

    result = {
        "success": True,
        "message": f"Generated 3D model: {gen_result['filename']}",
        "file_path": str(output_path),
        "file_size_kb": gen_result["file_size_kb"],
        "textured": gen_result["textured"],
        "blender_import": None,
    }

    # Import to Blender if requested and MCP is available
    if import_to_blender:
        if check_blender_mcp():
            import_result = await send_to_blender_mcp({
                "type": "import_glb",
                "filepath": str(output_path),
                "name": gen_result["filename"].replace(".glb", ""),
            })
            result["blender_import"] = import_result
        else:
            result["blender_import"] = {
                "status": "skipped",
                "reason": "Blender MCP not running. Start Blender with MCP addon to enable auto-import."
            }

    return result


async def image_to_3d_blender(
    image_path: str,
    output_dir: Optional[str] = None,
    import_to_blender: bool = True,
    texture: bool = True,
    remove_background: bool = True,
) -> dict:
    """
    Complete workflow: Generate 3D model from image and import to Blender.

    Args:
        image_path: Path to the reference image
        output_dir: Directory to save the GLB file
        import_to_blender: Whether to import directly to Blender
        texture: Whether to generate with texture
        remove_background: Whether to remove background from image

    Returns:
        dict with status, file path, and Blender import status
    """
    # Generate the 3D model
    gen_result = await hunyuan_generate_glb(
        image_path=image_path,
        remove_background=remove_background,
        texture=texture,
    )

    if not gen_result.get("success"):
        return gen_result

    # Determine output directory
    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = Path.cwd() / "output" / "3d"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save the GLB file
    output_path = out_dir / gen_result["filename"]
    with open(output_path, "wb") as f:
        f.write(gen_result["glb_data"])

    result = {
        "success": True,
        "message": f"Generated 3D model from image: {gen_result['filename']}",
        "file_path": str(output_path),
        "file_size_kb": gen_result["file_size_kb"],
        "textured": gen_result["textured"],
        "source_image": image_path,
        "blender_import": None,
    }

    # Import to Blender if requested and MCP is available
    if import_to_blender:
        if check_blender_mcp():
            import_result = await send_to_blender_mcp({
                "type": "import_glb",
                "filepath": str(output_path),
                "name": gen_result["filename"].replace(".glb", ""),
            })
            result["blender_import"] = import_result
        else:
            result["blender_import"] = {
                "status": "skipped",
                "reason": "Blender MCP not running"
            }

    return result


async def blender_mcp_status() -> dict:
    """
    Check Blender MCP server status.

    Returns:
        dict with connection status and available commands
    """
    is_running = check_blender_mcp()

    result = {
        "running": is_running,
        "host": BLENDER_MCP_HOST,
        "port": BLENDER_MCP_PORT,
    }

    if is_running:
        # Try to get scene info
        scene_info = await send_to_blender_mcp({"type": "get_scene_info"})
        result["scene_info"] = scene_info
        result["message"] = "Blender MCP is connected and ready"
    else:
        result["message"] = (
            "Blender MCP not running. To enable:\n"
            "1. Open Blender\n"
            "2. Enable BlenderMCP addon in Preferences > Add-ons\n"
            "3. Click 'Start Server' in the BlenderMCP panel (View3D > Sidebar)"
        )

    return result


async def hunyuan_status() -> dict:
    """
    Check Hunyuan3D server status.

    Returns:
        dict with server status
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
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
            "message": f"Cannot connect to Hunyuan3D server at {HUNYUAN_API_URL}"
        }
    except Exception as e:
        return {
            "running": False,
            "url": HUNYUAN_API_URL,
            "message": f"Error checking server: {str(e)}"
        }
    except Exception as e:
        return {
            "running": False,
            "url": HUNYUAN_API_URL,
            "message": f"Error checking server: {str(e)}"
        }


def register_blender_workflow_tools(registry: ToolRegistry) -> None:
    """Register Blender workflow tools."""

    registry.register(ToolDefinition(
        name="text_to_3d_blender",
        description="Generate a 3D model from text prompt and optionally import to Blender. "
                   "Complete workflow from text description to 3D asset.",
        parameters={
            "type": "object",
            "properties": {
                "text_prompt": {
                    "type": "string",
                    "description": "Text description of the 3D model to generate"
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory to save the GLB file (default: ./output/3d)"
                },
                "import_to_blender": {
                    "type": "boolean",
                    "description": "Whether to import directly to Blender via MCP",
                    "default": True
                },
                "texture": {
                    "type": "boolean",
                    "description": "Whether to generate with texture",
                    "default": True
                },
                "octree_resolution": {
                    "type": "integer",
                    "description": "Quality of generation (128-512)",
                    "default": 256
                }
            },
            "required": ["text_prompt"]
        },
        function=text_to_3d_blender,
        category="blender_workflow",
        examples=[
            'text_to_3d_blender(text_prompt="A sci-fi robot soldier")',
            'text_to_3d_blender(text_prompt="A medieval sword", texture=True, import_to_blender=True)'
        ]
    ))

    registry.register(ToolDefinition(
        name="image_to_3d_blender",
        description="Generate a 3D model from an image and optionally import to Blender.",
        parameters={
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Path to the reference image"
                },
                "output_dir": {
                    "type": "string",
                    "description": "Directory to save the GLB file"
                },
                "import_to_blender": {
                    "type": "boolean",
                    "description": "Whether to import directly to Blender via MCP",
                    "default": True
                },
                "texture": {
                    "type": "boolean",
                    "description": "Whether to generate with texture",
                    "default": True
                },
                "remove_background": {
                    "type": "boolean",
                    "description": "Whether to remove background from image",
                    "default": True
                }
            },
            "required": ["image_path"]
        },
        function=image_to_3d_blender,
        category="blender_workflow",
    ))

    registry.register(ToolDefinition(
        name="blender_mcp_status",
        description="Check if Blender MCP server is running and connected.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        function=blender_mcp_status,
        category="blender_workflow",
    ))

    registry.register(ToolDefinition(
        name="hunyuan_status",
        description="Check if Hunyuan3D server is running.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        function=hunyuan_status,
        category="blender_workflow",
    ))
