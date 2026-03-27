"""
MCP Tools for the Game-Playing Agent.

Exposes game agent capabilities as MCP tools for integration with Claude Code.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import GameAgentConfig
from .player import GamePlayer, GameResult
from .vision.fast_detector import GameState

logger = logging.getLogger(__name__)

# Try to import MCP, make it optional
try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    Server = None
    # Create placeholder classes for when MCP is not available
    @dataclass
    class Tool:
        name: str
        description: str
        inputSchema: dict

    @dataclass
    class TextContent:
        type: str
        text: str

# Global player instance (managed by tools)
_player: Optional[GamePlayer] = None
_config: Optional[GameAgentConfig] = None


def get_player(llm_client: Any = None) -> GamePlayer:
    """Get or create the global player instance."""
    global _player, _config
    if _player is None:
        _config = GameAgentConfig()
        _player = GamePlayer(_config, llm_client=llm_client)
    return _player


# Tool definitions
TOOLS = [
    Tool(
        name="game_start",
        description="Start the game agent and open the browser to the game URL",
        inputSchema={
            "type": "object",
            "properties": {
                "game_url": {
                    "type": "string",
                    "description": "URL of the game to play (default: http://localhost:8888)"
                }
            }
        }
    ),
    Tool(
        name="game_stop",
        description="Stop the game agent and close the browser",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="game_play",
        description="Start playing the game autonomously until victory, death, or max frames",
        inputSchema={
            "type": "object",
            "properties": {
                "max_frames": {
                    "type": "integer",
                    "description": "Maximum frames to play (default: 10000)"
                },
                "use_rules": {
                    "type": "boolean",
                    "description": "Use rule-based decisions (default: true)"
                },
                "explore": {
                    "type": "boolean",
                    "description": "Allow exploration for Q-learning (default: true)"
                }
            }
        }
    ),
    Tool(
        name="game_step",
        description="Execute a single game step (screenshot, detect, decide, act)",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="game_pause",
        description="Pause automatic gameplay",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="game_resume",
        description="Resume paused gameplay",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="game_status",
        description="Get current game agent status and statistics",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="game_train",
        description="Train the agent by playing multiple games",
        inputSchema={
            "type": "object",
            "properties": {
                "num_games": {
                    "type": "integer",
                    "description": "Number of games to play (default: 10)"
                },
                "save_every": {
                    "type": "integer",
                    "description": "Save Q-table every N games (default: 5)"
                }
            }
        }
    ),
    Tool(
        name="game_detect_state",
        description="Take a screenshot and detect current game state (no actions taken)",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="game_execute_action",
        description="Execute a specific action by name",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to execute (move_forward, attack, cast_heal, etc.)"
                }
            },
            "required": ["action"]
        }
    ),
    Tool(
        name="game_q_stats",
        description="Get Q-learning statistics",
        inputSchema={"type": "object", "properties": {}}
    ),
    Tool(
        name="game_q_reset",
        description="Reset Q-table (clear all learned values)",
        inputSchema={"type": "object", "properties": {}}
    ),
]


async def handle_tool_call(name: str, arguments: Dict[str, Any], llm_client: Any = None) -> List[TextContent]:
    """Handle MCP tool calls."""
    global _player

    try:
        if name == "game_start":
            player = get_player(llm_client)
            if arguments.get("game_url"):
                player.config.game_url = arguments["game_url"]
            await player.start()
            return [TextContent(
                type="text",
                text=f"Game agent started. Browser opened to {player.config.game_url}"
            )]

        elif name == "game_stop":
            player = get_player()
            await player.stop()
            _player = None
            return [TextContent(type="text", text="Game agent stopped and browser closed.")]

        elif name == "game_play":
            player = get_player()
            max_frames = arguments.get("max_frames", 10000)
            use_rules = arguments.get("use_rules", True)
            explore = arguments.get("explore", True)

            result = await player.play_game(
                max_frames=max_frames,
                use_rules=use_rules,
                explore=explore
            )

            return [TextContent(
                type="text",
                text=format_game_result(result)
            )]

        elif name == "game_step":
            player = get_player()
            state = await player.step()
            return [TextContent(
                type="text",
                text=format_state(state)
            )]

        elif name == "game_pause":
            player = get_player()
            player.pause()
            return [TextContent(type="text", text="Game paused.")]

        elif name == "game_resume":
            player = get_player()
            player.resume()
            return [TextContent(type="text", text="Game resumed.")]

        elif name == "game_status":
            player = get_player()
            status = player.get_status()
            return [TextContent(
                type="text",
                text=json.dumps(status, indent=2, default=str)
            )]

        elif name == "game_train":
            player = get_player(llm_client)
            num_games = arguments.get("num_games", 10)
            save_every = arguments.get("save_every", 5)

            results = await player.train(num_games=num_games, save_every=save_every)

            summary = format_training_results(results)
            return [TextContent(type="text", text=summary)]

        elif name == "game_detect_state":
            player = get_player()
            screenshot = await player.browser.take_screenshot()
            state = player.detector.detect_state(screenshot)
            return [TextContent(
                type="text",
                text=format_state(state)
            )]

        elif name == "game_execute_action":
            player = get_player()
            action = arguments["action"]
            await player.execute_action(action)
            return [TextContent(
                type="text",
                text=f"Executed action: {action}"
            )]

        elif name == "game_q_stats":
            player = get_player()
            if player.q_learner:
                stats = player.q_learner.get_statistics()
                return [TextContent(
                    type="text",
                    text=json.dumps(stats, indent=2)
                )]
            return [TextContent(type="text", text="Q-learning not enabled.")]

        elif name == "game_q_reset":
            player = get_player()
            if player.q_learner:
                player.q_learner.reset()
                return [TextContent(type="text", text="Q-table reset.")]
            return [TextContent(type="text", text="Q-learning not enabled.")]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.error(f"Tool error {name}: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


def format_state(state: GameState) -> str:
    """Format game state for display."""
    return f"""Game State:
  Health: {state.health_pct * 100:.0f}%
  Mana: {state.mana_pct * 100:.0f}%
  Floor: {state.floor}

  Enemy Ahead: {state.enemy_ahead} ({state.enemy_type})
  Stairs Ahead: {state.stairs_ahead}
  Chest Ahead: {state.chest_ahead}

  Game Over: {state.game_over}
  Victory: {state.victory}

  Detection Time: {state.detection_time_ms:.1f}ms
"""


def format_game_result(result: GameResult) -> str:
    """Format game result for display."""
    status = "VICTORY!" if result.victory else "GAME OVER"
    return f"""{status}
Duration: {result.stats.duration_seconds:.1f}s
Frames: {result.stats.frames_processed}
Actions: {result.stats.actions_taken}
Floor Reached: {result.stats.floors_reached}
Enemies Killed: {result.stats.enemies_killed}
Chests Opened: {result.stats.chests_opened}
Vision Calls: {result.stats.vision_calls}
FPS: {result.stats.fps:.1f}
{f"Error: {result.error}" if result.error else ""}
"""


def format_training_results(results: list) -> str:
    """Format training results summary."""
    victories = sum(1 for r in results if r.victory)
    avg_floors = sum(r.stats.floors_reached for r in results) / len(results)
    avg_duration = sum(r.stats.duration_seconds for r in results) / len(results)

    return f"""Training Complete
Games Played: {len(results)}
Victories: {victories} ({victories/len(results)*100:.0f}%)
Avg Floor Reached: {avg_floors:.1f}
Avg Duration: {avg_duration:.1f}s
"""


def register_game_tools(mcp: "Server", llm_client: Any = None) -> None:
    """Register game agent tools with an MCP server."""
    if not MCP_AVAILABLE:
        logger.warning("MCP not available, cannot register tools")
        return

    @mcp.list_tools()
    async def list_tools():
        return TOOLS

    @mcp.call_tool()
    async def call_tool(name: str, arguments: dict):
        return await handle_tool_call(name, arguments, llm_client)


def create_game_mcp_server(llm_client: Any = None) -> Optional["Server"]:
    """Create a standalone MCP server for the game agent."""
    if not MCP_AVAILABLE:
        logger.warning("MCP not available, cannot create server")
        return None

    server = Server("game-agent")
    register_game_tools(server, llm_client)
    return server
