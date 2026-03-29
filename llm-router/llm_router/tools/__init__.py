"""Tool registry for the agent framework."""

from typing import Callable, Any
from dataclasses import dataclass, field


@dataclass
class ToolDefinition:
    """Definition of a tool."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    function: Callable
    category: str = "general"
    dangerous: bool = False  # Requires confirmation
    examples: list[str] = field(default_factory=list)


class ToolRegistry:
    """
    Registry for managing tools that can be used by agents.

    Example:
        registry = ToolRegistry()

        # Register a tool
        registry.register(ToolDefinition(
            name="web_search",
            description="Search the web",
            parameters={"query": {"type": "string"}},
            function=search_function
        ))

        # Get tool for use
        tool = registry.get("web_search")
        result = await tool.function(query="AI news")
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool."""
        self._tools.pop(name, None)

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self, category: str | None = None) -> list[ToolDefinition]:
        """List all tools, optionally filtered by category."""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    def get_definitions(self) -> dict[str, dict]:
        """Get all tool definitions in OpenAI format."""
        return {
            name: {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            }
            for name, tool in self._tools.items()
        }

    def get_functions(self) -> dict[str, Callable]:
        """Get all tool functions."""
        return {name: tool.function for name, tool in self._tools.items()}

    def to_dict(self) -> dict:
        """Serialize registry to dict (without functions)."""
        return {
            name: {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "category": tool.category,
                "dangerous": tool.dangerous,
                "examples": tool.examples,
            }
            for name, tool in self._tools.items()
        }


# Global tool registry instance
_global_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
        # Register built-in tools
        from llm_router.tools.builtin import register_builtin_tools
        register_builtin_tools(_global_registry)
        # Register Godot tools
        from llm_router.tools.godot_tools import register_godot_tools
        register_godot_tools(_global_registry)
        # Register Godot asset tools
        from llm_router.tools.godot_assets import register_godot_asset_tools
        register_godot_asset_tools(_global_registry)
        # Register Godot debug tools
        from llm_router.tools.godot_debug import register_godot_debug_tools
        register_godot_debug_tools(_global_registry)
        # Register AI art tools
        from llm_router.tools.ai_art import register_ai_art_tools
        register_ai_art_tools(_global_registry)
        # Register itch.io tools
        from llm_router.tools.itchio_tools import register_itchio_tools
        register_itchio_tools(_global_registry)
        # Register game library tools
        from llm_router.tools.game_library import register_game_library_tools
        register_game_library_tools(_global_registry)
        # Register Hunyuan3D tools for 3D asset generation
        from llm_router.tools.godot_hunyuan import register_godot_hunyuan_tools
        register_godot_hunyuan_tools(_global_registry)
        # Register Blender workflow tools
        from llm_router.tools.blender_workflow import register_blender_workflow_tools
        register_blender_workflow_tools(_global_registry)
    return _global_registry
