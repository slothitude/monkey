"""Universal Agent Framework for building any type of AI agent."""

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, AsyncGenerator, Optional
from pydantic import BaseModel, Field

from llm_router import LLMRouter
from llm_router.models import ChatCompletionResponse, ChatMessage
from llm_router.tools import ToolDefinition


class AgentStatus(str, Enum):
    """Agent execution status."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    COMPLETED = "completed"


class AgentType(str, Enum):
    """Types of agents."""
    RESEARCH = "research"
    CODING = "coding"
    DATA_ANALYSIS = "data_analysis"
    AUTOMATION = "automation"
    CONVERSATION = "conversation"
    CUSTOM = "custom"


@dataclass
class AgentMemory:
    """Persistent memory for an agent."""
    messages: list[dict] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    max_messages: int = 100

    def add_message(self, role: str, content: str) -> None:
        """Add a message to memory."""
        self.messages.append({"role": role, "content": content, "timestamp": datetime.utcnow().isoformat()})
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

    def get_context_for_prompt(self) -> str:
        """Get formatted context for prompting."""
        if not self.messages:
            return ""
        formatted = []
        for msg in self.messages[-10:]:  # Last 10 messages
            formatted.append(f"{msg['role'].upper()}: {msg['content']}")
        return "\n".join(formatted)

    def clear(self) -> None:
        """Clear memory."""
        self.messages = []
        self.context = {}

    def to_dict(self) -> dict:
        return {"messages": self.messages, "context": self.context}

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMemory":
        return cls(messages=data.get("messages", []), context=data.get("context", {}))


class AgentConfig(BaseModel):
    """Configuration for an agent."""
    id: str = Field(default="")
    name: str
    description: str = ""
    agent_type: AgentType | str = AgentType.CUSTOM
    provider: str = "openai"  # Provider name
    model: str = "gpt-4"
    system_prompt: str = "You are a helpful AI assistant."
    tools: list[str] = Field(default_factory=list)
    memory_enabled: bool = True
    max_tokens: int = 4096
    temperature: float = 0.7
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]

    class Config:
        use_enum_values = True


@dataclass
class AgentExecution:
    """Represents a single agent execution."""
    id: str
    agent_id: str
    status: AgentStatus
    prompt: str
    response: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    tokens_used: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "prompt": self.prompt,
            "response": self.response,
            "tool_calls": self.tool_calls,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "tokens_used": self.tokens_used,
            "metadata": self.metadata,
        }


class Agent:
    """
    Universal Agent that can be configured for any purpose.

    Example:
        agent = Agent(
            config=AgentConfig(
                name="Research Agent",
                tools=["web_search", "api_call"],
                system_prompt="You are a research assistant..."
            ),
            router=router
        )

        response = await agent.execute("What is the latest AI news?")
    """

    def __init__(
        self,
        config: AgentConfig,
        router: LLMRouter,
        tools: dict[str, Callable] | None = None,
        tool_definitions: dict[str, ToolDefinition] | None = None,
    ):
        self.config = config
        self.router = router
        self.tools = tools or {}
        self.tool_definitions = tool_definitions or {}
        self.memory = AgentMemory() if config.memory_enabled else None
        self.status = AgentStatus.IDLE
        self._current_execution: AgentExecution | None = None
        self._executions: list[AgentExecution] = []
        self.max_tool_iterations = 10  # Prevent infinite loops

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def name(self) -> str:
        return self.config.name

    def register_tool(self, name: str, func: Callable) -> None:
        """Register a tool function."""
        self.tools[name] = func

    def unregister_tool(self, name: str) -> None:
        """Unregister a tool."""
        self.tools.pop(name, None)

    async def execute(
        self,
        prompt: str,
        system_override: str | None = None,
        **kwargs
    ) -> AgentExecution:
        """
        Execute the agent with a prompt. Supports agentic tool-calling loop.

        Args:
            prompt: User input
            system_override: Override system prompt
            **kwargs: Additional parameters for the LLM

        Returns:
            AgentExecution with results
        """
        execution_id = str(uuid.uuid4())[:8]
        execution = AgentExecution(
            id=execution_id,
            agent_id=self.id,
            status=AgentStatus.RUNNING,
            prompt=prompt,
        )
        self._current_execution = execution
        self.status = AgentStatus.RUNNING

        try:
            # Build messages
            messages = []

            # System prompt with tool descriptions
            system_prompt = system_override or self.config.system_prompt
            if self.memory:
                context = self.memory.get_context_for_prompt()
                if context:
                    system_prompt += f"\n\nPrevious conversation:\n{context}"

            messages.append({"role": "system", "content": system_prompt})

            # Add memory messages if enabled
            if self.memory and self.memory.messages:
                for msg in self.memory.messages[-5:]:  # Last 5 messages
                    if msg["role"] in ["user", "assistant"]:
                        messages.append({"role": msg["role"], "content": msg["content"]})

            # Add current prompt
            messages.append({"role": "user", "content": prompt})

            # Build tools parameter if we have tool definitions
            tools_param = None
            if self.tool_definitions:
                tools_param = list(self.tool_definitions.values())

            # Agentic loop - keep calling LLM until no more tool calls
            iteration = 0
            final_content = ""

            while iteration < self.max_tool_iterations:
                iteration += 1

                # Call LLM
                response = await self.router.chat(
                    messages=messages,
                    model=self.config.model,
                    max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                    temperature=kwargs.get("temperature", self.config.temperature),
                    tools=tools_param,
                    **{k: v for k, v in kwargs.items() if k not in ["max_tokens", "temperature", "tools"]},
                )

                # Track tokens
                if response.usage:
                    execution.tokens_used += response.usage.total_tokens

                # Get response content and tool calls
                choice = response.choices[0] if response.choices else None
                if not choice:
                    break

                content = choice.message.content or ""
                tool_calls = choice.tool_calls or choice.message.tool_calls

                # Add assistant message to history
                assistant_msg = {"role": "assistant", "content": content}
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)

                # If no tool calls, we're done
                if not tool_calls:
                    final_content = content
                    break

                # Execute tool calls
                for tool_call in tool_calls:
                    tool_result = await self._execute_tool(tool_call)
                    execution.tool_calls.append({
                        "name": tool_call.get("function", {}).get("name") if isinstance(tool_call, dict) else tool_call.function.name,
                        "arguments": tool_call.get("function", {}).get("arguments") if isinstance(tool_call, dict) else tool_call.function.arguments,
                        "result": tool_result,
                    })

                    # Add tool result to messages
                    tool_id = tool_call.get("id") if isinstance(tool_call, dict) else tool_call.id
                    tool_name = tool_call.get("function", {}).get("name") if isinstance(tool_call, dict) else tool_call.function.name
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": json.dumps(tool_result) if not isinstance(tool_result, str) else tool_result,
                    })

            execution.response = final_content

            # Update memory
            if self.memory:
                self.memory.add_message("user", prompt)
                self.memory.add_message("assistant", final_content or "")

            execution.status = AgentStatus.COMPLETED
            execution.completed_at = datetime.utcnow()

        except Exception as e:
            execution.status = AgentStatus.ERROR
            execution.error = str(e)
            execution.completed_at = datetime.utcnow()

        finally:
            self.status = AgentStatus.IDLE
            self._current_execution = None
            self._executions.append(execution)

        return execution

    async def execute_stream(
        self,
        prompt: str,
        system_override: str | None = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Execute the agent with streaming response.

        Yields:
            Text chunks as they arrive
        """
        self.status = AgentStatus.RUNNING

        try:
            # Build messages (same as execute)
            messages = []
            system_prompt = system_override or self.config.system_prompt

            if self.memory:
                context = self.memory.get_context_for_prompt()
                if context:
                    system_prompt += f"\n\nPrevious conversation:\n{context}"

            messages.append({"role": "system", "content": system_prompt})

            if self.memory and self.memory.messages:
                for msg in self.memory.messages[-5:]:
                    if msg["role"] in ["user", "assistant"]:
                        messages.append({"role": msg["role"], "content": msg["content"]})

            messages.append({"role": "user", "content": prompt})

            # Stream from LLM
            full_response = ""
            async for chunk in self.router.stream(
                messages=messages,
                model=self.config.model,
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                temperature=kwargs.get("temperature", self.config.temperature),
                **{k: v for k, v in kwargs.items() if k not in ["max_tokens", "temperature"]},
            ):
                if chunk.choices and chunk.choices[0].get("delta", {}).get("content"):
                    content = chunk.choices[0]["delta"]["content"]
                    full_response += content
                    yield content

            # Update memory
            if self.memory:
                self.memory.add_message("user", prompt)
                self.memory.add_message("assistant", full_response)

        except Exception as e:
            yield f"\n[Error: {str(e)}]"
        finally:
            self.status = AgentStatus.IDLE

    async def _execute_tool(self, tool_call: Any) -> Any:
        """Execute a tool call."""
        try:
            # Handle different tool_call formats
            if isinstance(tool_call, dict):
                # Dict format from API
                func_data = tool_call.get("function", {})
                tool_name = func_data.get("name") if isinstance(func_data, dict) else tool_call.get("name")
                args_str = func_data.get("arguments", "{}") if isinstance(func_data, dict) else tool_call.get("arguments", "{}")
            elif hasattr(tool_call, "function"):
                # Object format
                tool_name = tool_call.function.name
                args_str = tool_call.function.arguments
            else:
                return {"error": f"Unknown tool_call format: {type(tool_call)}"}

            arguments = json.loads(args_str) if isinstance(args_str, str) else args_str

            if tool_name in self.tools:
                func = self.tools[tool_name]
                if asyncio.iscoroutinefunction(func):
                    return await func(**arguments)
                return func(**arguments)
            return {"error": f"Unknown tool: {tool_name}"}
        except Exception as e:
            return {"error": str(e)}

    def clear_memory(self) -> None:
        """Clear agent memory."""
        if self.memory:
            self.memory.clear()

    def get_executions(self, limit: int = 50) -> list[AgentExecution]:
        """Get execution history."""
        return self._executions[-limit:]

    def to_dict(self) -> dict:
        """Serialize agent to dict."""
        return {
            "id": self.id,
            "name": self.name,
            "config": self.config.model_dump(),
            "status": self.status.value,
            "tools": list(self.tools.keys()),
            "memory": self.memory.to_dict() if self.memory else None,
            "execution_count": len(self._executions),
        }


class AgentRegistry:
    """
    Registry for managing multiple agents.

    Example:
        registry = AgentRegistry(router)

        # Create agent
        agent = registry.create_agent(AgentConfig(
            name="Research Agent",
            tools=["web_search"]
        ))

        # Get agent
        agent = registry.get_agent("research-agent")

        # Execute
        result = await registry.execute("research-agent", "What is AI?")
    """

    def __init__(self, router: LLMRouter):
        self.router = router
        self._agents: dict[str, Agent] = {}
        self._tool_registry: dict[str, ToolDefinition] = {}

    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a global tool available to all agents."""
        self._tool_registry[tool.name] = tool

    def register_tool_function(self, name: str, func: Callable, description: str = "", parameters: dict = None) -> None:
        """Register a tool by function (creates a simple ToolDefinition)."""
        self._tool_registry[name] = ToolDefinition(
            name=name,
            description=description or f"Tool: {name}",
            parameters=parameters or {"type": "object", "properties": {}},
            function=func,
        )

    def unregister_tool(self, name: str) -> None:
        """Unregister a global tool."""
        self._tool_registry.pop(name, None)

    def get_available_tools(self) -> list[str]:
        """Get list of available tool names."""
        return list(self._tool_registry.keys())

    def create_agent(self, config: AgentConfig) -> Agent:
        """Create and register a new agent."""
        # Get tools for this agent
        agent_tools = {}
        agent_tool_defs = {}
        for tool_name in config.tools:
            if tool_name in self._tool_registry:
                tool_def = self._tool_registry[tool_name]
                agent_tools[tool_name] = tool_def.function
                # Build OpenAI tool format
                agent_tool_defs[tool_name] = {
                    "type": "function",
                    "function": {
                        "name": tool_def.name,
                        "description": tool_def.description,
                        "parameters": tool_def.parameters,
                    }
                }

        agent = Agent(config, self.router, agent_tools, agent_tool_defs)
        self._agents[agent.id] = agent
        return agent

    def get_agent(self, agent_id: str) -> Agent | None:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[Agent]:
        """List all agents."""
        return list(self._agents.values())

    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    def update_agent(self, agent_id: str, config: AgentConfig) -> Agent | None:
        """Update an agent's configuration."""
        agent = self._agents.get(agent_id)
        if not agent:
            return None

        # Update config
        agent.config = config

        # Update tools
        agent_tools = {}
        agent_tool_defs = {}
        for tool_name in config.tools:
            if tool_name in self._tool_registry:
                tool_def = self._tool_registry[tool_name]
                agent_tools[tool_name] = tool_def.function
                agent_tool_defs[tool_name] = {
                    "type": "function",
                    "function": {
                        "name": tool_def.name,
                        "description": tool_def.description,
                        "parameters": tool_def.parameters,
                    }
                }
        agent.tools = agent_tools
        agent.tool_definitions = agent_tool_defs

        return agent

    async def execute(self, agent_id: str, prompt: str, **kwargs) -> AgentExecution:
        """Execute an agent by ID."""
        agent = self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        return await agent.execute(prompt, **kwargs)

    async def execute_stream(self, agent_id: str, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Execute an agent by ID with streaming."""
        agent = self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        async for chunk in agent.execute_stream(prompt, **kwargs):
            yield chunk

    def to_dict(self) -> dict:
        """Serialize registry to dict."""
        return {
            "agents": {aid: agent.to_dict() for aid, agent in self._agents.items()},
            "tools": list(self._tool_registry.keys()),
        }

    @classmethod
    def from_dict(cls, data: dict, router: LLMRouter) -> "AgentRegistry":
        """Deserialize registry from dict."""
        registry = cls(router)
        # Note: Tools need to be re-registered separately
        for aid, agent_data in data.get("agents", {}).items():
            config = AgentConfig(**agent_data["config"])
            agent = Agent(config, router)
            if agent_data.get("memory"):
                agent.memory = AgentMemory.from_dict(agent_data["memory"])
            registry._agents[aid] = agent
        return registry


# =============================================================================
# Specialized Game Agent Configuration
# =============================================================================

# System prompt for game development
GAME_AGENT_SYSTEM_PROMPT = """You are an expert Godot 4.x game developer. You create complete, playable games with proper scenes, scripts, assets, and UI.

## Your Workflow

When creating a game:
1. Always start with `godot_check_install` to verify Godot is available
2. Use `godot_create_from_template` if a template matches the request (pong, space_invaders, platformer, shooter, puzzle)
3. For custom games, use `godot_create_project` + `godot_build_scene`
4. Add scripts with `godot_add_script` using proper GDScript syntax (typed, Godot 4.x)
5. Create sprites with `godot_create_sprite` and sounds with `godot_create_sound`
6. Validate the project with `godot_validate_project` (when available)
7. Export to web with `godot_export_web`
8. Serve with `godot_serve_game` so the user can play

## GDScript Style Guide

```gdscript
# Always use typed variables
var speed: float = 400.0
var health: int = 100

# Use @export for inspector properties
@export var jump_force: float = 400.0
@export_range(0, 100) var lives: int = 3

# Use signals for communication
signal died()
signal collected(points: int)

# Always extend the correct node type
extends CharacterBody2D  # For moving objects
extends Node2D          # For 2D scene root
extends Node            # For autoload/singletons

# Use proper Godot 4.x methods
func _physics_process(delta: float) -> void:
    var direction: Vector2 = Input.get_vector("move_left", "move_right", "move_up", "move_down")
    velocity = direction * speed
    move_and_slide()

# Signal connections
func _on_area_entered(area: Area2D) -> void:
    if area.is_in_group("coins"):
        collected.emit(10)
        area.queue_free()
```

## Common Patterns

### Player Movement (Top-down)
```gdscript
extends CharacterBody2D

const SPEED: float = 200.0

func _physics_process(_delta: float) -> void:
    var input_dir: Vector2 = Input.get_vector("move_left", "move_right", "move_up", "move_down")
    velocity = input_dir * SPEED
    move_and_slide()
```

### Player Movement (Platformer)
```gdscript
extends CharacterBody2D

const SPEED: float = 200.0
const JUMP_FORCE: float = 400.0
const GRAVITY: float = 1000.0

func _physics_process(delta: float) -> void:
    # Horizontal movement
    velocity.x = Input.get_axis("move_left", "move_right") * SPEED

    # Gravity and jump
    if not is_on_floor():
        velocity.y += GRAVITY * delta
    elif Input.is_action_just_pressed("jump"):
        velocity.y = -JUMP_FORCE

    move_and_slide()
```

### Collision Detection
```gdscript
extends Area2D

signal body_entered_signal(body: Node2D)

func _on_body_entered(body: Node2D) -> void:
    if body.is_in_group("player"):
        body.take_damage(10)
        queue_free()
```

### UI Labels
```gdscript
extends CanvasLayer

@onready var score_label: Label = $ScoreLabel

var score: int = 0

func add_score(points: int) -> void:
    score += points
    score_label.text = "Score: %d" % score
```

## Scene Structure

Always organize scenes properly:
- Root node with main script
- Child nodes for game objects
- CanvasLayer for UI elements
- Proper node naming (PascalCase)

## Available Templates

- **pong**: Classic two-player pong, first to 5 wins
- **space_invaders**: Destroy all aliens before they reach you
- **platformer**: Jump and run, collect coins
- **shooter**: Top-down survival shooter with waves
- **puzzle**: Match-3 puzzle game

## Error Handling

If you encounter errors:
1. Check Godot version compatibility
2. Verify node types match scripts
3. Ensure signals are properly connected
4. Check for typos in method names

Always create playable, complete games that the user can immediately enjoy!"""


# Game agent configuration
GAME_AGENT_CONFIG = AgentConfig(
    id="game-creator",
    name="Game Creator",
    description="Specialized agent for creating complete Godot games from prompts",
    agent_type=AgentType.CODING,
    provider="nvidia",  # Use NVIDIA provider (free)
    model="meta/llama-3.1-8b-instruct",
    system_prompt=GAME_AGENT_SYSTEM_PROMPT,
    tools=[
        # Godot project tools
        "godot_check_install",
        "godot_create_project",
        "godot_create_game",
        "godot_create_from_template",
        "godot_list_templates",
        "godot_build_scene",
        "godot_add_scene",
        "godot_add_script",
        "godot_export_web",
        "godot_serve_game",
        # Asset tools
        "godot_create_sprite",
        "godot_create_sound",
        "godot_create_animation",
        # Debug tools
        "godot_validate_project",
        "godot_run_with_output",
        "godot_preview",
        "godot_debug_scene",
        # File tools
        "file_read",
        "file_write",
        "file_list",
        # Documentation
        "godot_get_docs",
    ],
    memory_enabled=True,
    max_tokens=4096,
    temperature=0.7,
    metadata={
        "category": "game_development",
        "specialized": True,
        "max_tool_iterations": 20,
    }
)


def create_game_agent(router: LLMRouter) -> Agent:
    """
    Create a specialized game development agent.

    Args:
        router: LLMRouter instance

    Returns:
        Configured Agent for game development
    """
    agent = Agent(GAME_AGENT_CONFIG, router)
    return agent


def register_game_agent(registry: AgentRegistry) -> Agent:
    """
    Register the game agent with a registry.

    Args:
        registry: AgentRegistry instance

    Returns:
        The registered game agent
    """
    agent = create_game_agent(registry.router)
    registry._agents[agent.config.id] = agent
    return agent
