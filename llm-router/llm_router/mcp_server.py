"""MCP Server for LLM Router - Exposes all tools for Claude Code.

This creates an MCP (Model Context Protocol) server that exposes:
1. Worker Pool tools for task delegation
2. Godot Game Maker tools for game creation
3. AI Art tools for asset generation

Run this server:
    python -m llm_router.mcp_server

Or configure in Claude Code settings:
    {
        "mcpServers": {
            "llm-router": {
                "command": "python",
                "args": ["-m", "llm_router.mcp_server"],
                "cwd": "/path/to/llm-router"
            }
        }
    }
"""

import asyncio
import json
import sys
from typing import Any, Callable

# Initialize worker pool on import
from llm_router.mcp_worker import (
    initialize_worker_pool,
    delegate_task_async,
    analyze_task_async,
    spawn_worker_async,
    execute_skill_async,
    list_workers_async,
    list_skills_async,
)


# =============================================================================
# Tool Definitions
# =============================================================================

TOOL_DEFINITIONS = [
    # ==================== Worker Pool Tools ====================
    {
        "name": "delegate_task",
        "description": "Delegate a complex task to the worker pool. The task will be analyzed, broken down into subtasks, and executed by appropriate worker agents.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The task description to delegate"},
                "spawn_missing": {"type": "boolean", "description": "Whether to spawn new workers if needed (default: true)"},
                "context": {"type": "string", "description": "Optional context information"}
            },
            "required": ["task"]
        }
    },
    {
        "name": "analyze_task",
        "description": "Analyze a task and see how it would be broken down into subtasks without executing.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The task to analyze"}
            },
            "required": ["task"]
        }
    },
    {
        "name": "spawn_worker",
        "description": "Spawn a new worker agent with specific skills.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Worker name"},
                "description": {"type": "string", "description": "What this worker does"},
                "skills": {"type": "array", "items": {"type": "string"}, "description": "List of skills"},
                "model": {"type": "string", "description": "Model to use (default: minimaxai/minimax-m2.5)"}
            },
            "required": ["name", "description"]
        }
    },
    {
        "name": "execute_skill",
        "description": "Execute a specific skill directly.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "Name of the skill to execute"}
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "list_workers",
        "description": "List all available workers in the pool.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "list_skills",
        "description": "List all available skills.",
        "parameters": {"type": "object", "properties": {}}
    },

    # ==================== Godot Project Tools ====================
    {
        "name": "godot_check_install",
        "description": "Check if Godot is installed and get version info.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "godot_create_project",
        "description": "Create a new Godot 4.x project with proper structure, project.godot, and export presets.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Directory path for the project"},
                "project_name": {"type": "string", "description": "Name of the project", "default": "Game"},
                "godot_version": {"type": "string", "description": "Godot version (4.2, 4.3, 4.6)", "default": "4.3"}
            },
            "required": ["project_path"]
        }
    },
    {
        "name": "godot_create_game",
        "description": "Create a complete, playable Godot game from a template. Templates: pong, space_invaders, platformer, shooter, puzzle.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Directory for the project"},
                "game_name": {"type": "string", "description": "Name of the game"},
                "game_type": {"type": "string", "description": "Type: pong, space_invaders, platformer, shooter, puzzle"},
                "description": {"type": "string", "description": "Description of the game"}
            },
            "required": ["project_path", "game_name", "game_type"]
        }
    },
    {
        "name": "godot_create_from_template",
        "description": "Create a complete game from a named template with optional customizations.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Directory for the project"},
                "template_name": {"type": "string", "description": "Template: pong, space_invaders, platformer, shooter, puzzle"},
                "game_name": {"type": "string", "description": "Name for the game"},
                "customizations": {"type": "object", "description": "Optional customizations (colors, speed, difficulty)"}
            },
            "required": ["project_path", "template_name", "game_name"]
        }
    },
    {
        "name": "godot_list_templates",
        "description": "List all available game templates with descriptions, controls, and objectives.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "godot_build_scene",
        "description": "Build a complete Godot scene from structured configuration with nodes, UI, and connections.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "scene_name": {"type": "string", "description": "Name for the scene"},
                "scene_config": {"type": "object", "description": "Structured scene configuration"}
            },
            "required": ["project_path", "scene_name", "scene_config"]
        }
    },
    {
        "name": "godot_add_script",
        "description": "Add a GDScript file to a Godot project. Automatically adds 'extends' clause if missing.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "script_name": {"type": "string", "description": "Name of the script file"},
                "script_content": {"type": "string", "description": "GDScript code content"},
                "extends": {"type": "string", "description": "Node type to extend", "default": "Node2D"}
            },
            "required": ["project_path", "script_name", "script_content"]
        }
    },
    {
        "name": "godot_export_web",
        "description": "Export a Godot project to HTML5/WebAssembly for browser play.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "output_path": {"type": "string", "description": "Output directory for export"}
            },
            "required": ["project_path"]
        }
    },
    {
        "name": "godot_serve_game",
        "description": "Serve a Godot web export via local HTTP server for testing.",
        "parameters": {
            "type": "object",
            "properties": {
                "export_path": {"type": "string", "description": "Path to the exported HTML files"},
                "port": {"type": "integer", "description": "Port to serve on", "default": 8888}
            },
            "required": ["export_path"]
        }
    },

    # ==================== Godot Asset Tools ====================
    {
        "name": "godot_create_sprite",
        "description": "Create a sprite asset for a Godot game. Types: rectangle, circle, triangle, star, heart, arrow, diamond, hexagon, player_ship, enemy, bullet, coin, paddle, ball.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "sprite_name": {"type": "string", "description": "Name for the sprite"},
                "sprite_config": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "description": "Sprite shape type"},
                        "size": {"type": "array", "items": {"type": "integer"}},
                        "color": {"type": "string", "description": "Fill color (hex)"},
                        "outline_color": {"type": "string"},
                        "outline_width": {"type": "integer"}
                    }
                }
            },
            "required": ["project_path", "sprite_name", "sprite_config"]
        }
    },
    {
        "name": "godot_create_sound",
        "description": "Create a sound effect for a Godot game. Types: beep, tone, square, noise, explosion, jump, collect, hit, powerup, hurt, victory.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "sound_name": {"type": "string", "description": "Name for the sound"},
                "sound_config": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "description": "Sound type"},
                        "frequency": {"type": "number", "description": "Frequency in Hz"},
                        "duration": {"type": "number", "description": "Duration in seconds"},
                        "volume": {"type": "number", "description": "Volume 0.0 to 1.0"}
                    }
                }
            },
            "required": ["project_path", "sound_name", "sound_config"]
        }
    },
    {
        "name": "godot_create_animation",
        "description": "Create an animated sprite with multiple frames.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "animation_name": {"type": "string", "description": "Name for the animation"},
                "frames": {"type": "array", "description": "List of frame configurations"}
            },
            "required": ["project_path", "animation_name", "frames"]
        }
    },

    # ==================== Godot Debug Tools ====================
    {
        "name": "godot_validate_project",
        "description": "Validate a Godot project for common issues (missing files, syntax errors, broken references).",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"}
            },
            "required": ["project_path"]
        }
    },
    {
        "name": "godot_run_with_output",
        "description": "Run Godot project in headless mode and capture output/errors.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30}
            },
            "required": ["project_path"]
        }
    },
    {
        "name": "godot_preview",
        "description": "Preview the game in Godot editor or as a window.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "mode": {"type": "string", "description": "editor or window", "default": "editor"}
            },
            "required": ["project_path"]
        }
    },
    {
        "name": "godot_debug_scene",
        "description": "Debug a specific scene by analyzing its structure, nodes, connections, and resources.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "scene_name": {"type": "string", "description": "Name of the scene to debug"}
            },
            "required": ["project_path", "scene_name"]
        }
    },

    # ==================== AI Art Tools ====================
    {
        "name": "godot_generate_sprite_ai",
        "description": "Generate a sprite using AI image generation (Pixazo). Styles: pixel_art, cartoon, realistic, anime. Requires PIXAZO_API_KEY.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "sprite_name": {"type": "string", "description": "Name for the sprite"},
                "sprite_config": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Description of the sprite"},
                        "size": {"type": "array", "items": {"type": "integer"}, "default": [64, 64]},
                        "style": {"type": "string", "description": "Style: pixel_art, cartoon, realistic, anime"}
                    }
                }
            },
            "required": ["project_path", "sprite_name", "sprite_config"]
        }
    },
    {
        "name": "godot_generate_texture_ai",
        "description": "Generate a texture using AI image generation. Requires PIXAZO_API_KEY.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "texture_name": {"type": "string", "description": "Name for the texture"},
                "texture_config": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Description of the texture"},
                        "size": {"type": "array", "items": {"type": "integer"}, "default": [256, 256]},
                        "seamless": {"type": "boolean", "default": "true"}
                    }
                }
            },
            "required": ["project_path", "texture_name", "texture_config"]
        }
    },
    {
        "name": "godot_generate_character_ai",
        "description": "Generate a character with multiple animations using AI. Requires PIXAZO_API_KEY.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "character_name": {"type": "string", "description": "Name for the character"},
                "character_config": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Description of the character"},
                        "animations": {"type": "array", "items": {"type": "string"}, "default": ["idle", "walk", "run", "jump"]},
                        "size": {"type": "array", "items": {"type": "integer"}, "default": [64, 64]}
                    }
                }
            },
            "required": ["project_path", "character_name", "character_config"]
        }
    },
    {
        "name": "godot_generate_music_ai",
        "description": "Generate music using AI (Pixazo). Requires PIXAZO_API_KEY. Returns task_id for async status check.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {"type": "string", "description": "Path to the Godot project"},
                "music_name": {"type": "string", "description": "Name for the music"},
                "prompt": {"type": "string", "description": "Description of the music style"},
                "duration": {"type": "integer", "default": 120},
                "bpm": {"type": "integer", "default": 140},
                "instrumental": {"type": "boolean", "default": true}
            },
            "required": ["project_path", "music_name", "prompt"]
        }
    },
]


# =============================================================================
# Tool Handlers
# =============================================================================

async def handle_tool_call(tool_name: str, arguments: dict) -> dict:
    """Handle a tool call and return the result."""

    # Worker Pool Tools
    if tool_name == "delegate_task":
        return await delegate_task_async(
            task=arguments.get("task"),
            spawn_missing=arguments.get("spawn_missing", True),
            context=arguments.get("context")
        )

    elif tool_name == "analyze_task":
        return await analyze_task_async(task=arguments.get("task"))

    elif tool_name == "spawn_worker":
        return await spawn_worker_async(
            name=arguments.get("name"),
            description=arguments.get("description"),
            skills=arguments.get("skills", []),
            model=arguments.get("model", "minimaxai/minimax-m2.5")
        )

    elif tool_name == "execute_skill":
        return await execute_skill_async(
            skill_name=arguments.get("skill_name"),
            **{k: v for k, v in arguments.items() if k != "skill_name"}
        )

    elif tool_name == "list_workers":
        return await list_workers_async()

    elif tool_name == "list_skills":
        return await list_skills_async()

    # Godot Tools - Import and call dynamically
    elif tool_name.startswith("godot_"):
        return await handle_godot_tool(tool_name, arguments)

    else:
        return {"error": f"Unknown tool: {tool_name}"}


async def handle_godot_tool(tool_name: str, arguments: dict) -> dict:
    """Handle Godot tool calls."""

    # Import the appropriate module based on tool name
    try:
        if tool_name in ["godot_check_install", "godot_create_project", "godot_create_game",
                         "godot_create_from_template", "godot_list_templates", "godot_build_scene",
                         "godot_add_script", "godot_export_web", "godot_serve_game"]:
            from llm_router.tools import godot_tools

            if tool_name == "godot_check_install":
                return await godot_tools.godot_check_install()
            elif tool_name == "godot_create_project":
                return await godot_tools.godot_create_project(**arguments)
            elif tool_name == "godot_create_game":
                return await godot_tools.godot_create_game(**arguments)
            elif tool_name == "godot_create_from_template":
                return await godot_tools.godot_create_from_template(**arguments)
            elif tool_name == "godot_list_templates":
                return await godot_tools.godot_list_templates()
            elif tool_name == "godot_build_scene":
                return await godot_tools.godot_build_scene(**arguments)
            elif tool_name == "godot_add_script":
                return await godot_tools.godot_add_script(**arguments)
            elif tool_name == "godot_export_web":
                return await godot_tools.godot_export_web(**arguments)
            elif tool_name == "godot_serve_game":
                return await godot_tools.godot_serve_game(**arguments)

        elif tool_name in ["godot_create_sprite", "godot_create_sound", "godot_create_animation"]:
            from llm_router.tools import godot_assets

            if tool_name == "godot_create_sprite":
                return await godot_assets.godot_create_sprite(**arguments)
            elif tool_name == "godot_create_sound":
                return await godot_assets.godot_create_sound(**arguments)
            elif tool_name == "godot_create_animation":
                return await godot_assets.godot_create_animation(**arguments)

        elif tool_name in ["godot_validate_project", "godot_run_with_output",
                           "godot_preview", "godot_debug_scene"]:
            from llm_router.tools import godot_debug

            if tool_name == "godot_validate_project":
                return await godot_debug.godot_validate_project(**arguments)
            elif tool_name == "godot_run_with_output":
                return await godot_debug.godot_run_with_output(**arguments)
            elif tool_name == "godot_preview":
                return await godot_debug.godot_preview(**arguments)
            elif tool_name == "godot_debug_scene":
                return await godot_debug.godot_debug_scene(**arguments)

        elif tool_name in ["godot_generate_sprite_ai", "godot_generate_texture_ai",
                           "godot_generate_character_ai", "godot_generate_music_ai"]:
            from llm_router.tools import ai_art

            if tool_name == "godot_generate_sprite_ai":
                return await ai_art.generate_sprite_ai(**arguments)
            elif tool_name == "godot_generate_texture_ai":
                return await ai_art.generate_texture_ai(**arguments)
            elif tool_name == "godot_generate_character_ai":
                return await ai_art.generate_character_ai(**arguments)
            elif tool_name == "godot_generate_music_ai":
                return await ai_art.generate_music_ai(**arguments)

        return {"error": f"Unknown Godot tool: {tool_name}"}

    except Exception as e:
        return {"error": str(e), "tool": tool_name}


# =============================================================================
# MCP Server
# =============================================================================

class MCPServer:
    """Simple MCP server implementation."""

    def __init__(self):
        self.running = False
        # Initialize pool
        initialize_worker_pool()

    async def handle_request(self, request: dict) -> dict:
        """Handle an MCP request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "llm-router",
                            "version": "2.0.0"
                        }
                    }
                }

            elif method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": TOOL_DEFINITIONS
                    }
                }

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                result = await handle_tool_call(tool_name, arguments)

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2, default=str)
                            }
                        ]
                    }
                }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown method: {method}"
                    }
                }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }

    async def run(self):
        """Run the MCP server, reading from stdin and writing to stdout."""
        self.running = True

        while self.running:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )

                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                    response = await self.handle_request(request)
                    print(json.dumps(response), flush=True)
                except json.JSONDecodeError as e:
                    print(json.dumps({
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32700,
                            "message": f"Parse error: {e}"
                        }
                    }), flush=True)

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32603,
                        "message": str(e)
                    }
                }), flush=True)


def main():
    """Main entry point."""
    server = MCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
