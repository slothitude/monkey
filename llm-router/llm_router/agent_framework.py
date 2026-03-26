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
    ):
        self.config = config
        self.router = router
        self.tools = tools or {}
        self.memory = AgentMemory() if config.memory_enabled else None
        self.status = AgentStatus.IDLE
        self._current_execution: AgentExecution | None = None
        self._executions: list[AgentExecution] = []

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
        Execute the agent with a prompt.

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

            # System prompt
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

            # Call LLM
            response = await self.router.chat(
                messages=messages,
                model=self.config.model,
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                temperature=kwargs.get("temperature", self.config.temperature),
                **{k: v for k, v in kwargs.items() if k not in ["max_tokens", "temperature"]},
            )

            # Extract response
            content = response.choices[0].message.content if response.choices else ""
            execution.response = content
            execution.tokens_used = response.usage.total_tokens if response.usage else 0

            # Handle tool calls if present
            if hasattr(response, "tool_calls") and response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_result = await self._execute_tool(tool_call)
                    execution.tool_calls.append({
                        "name": tool_call.function.name if hasattr(tool_call, "function") else tool_call.get("name"),
                        "arguments": tool_call.function.arguments if hasattr(tool_call, "function") else tool_call.get("arguments"),
                        "result": tool_result,
                    })

            # Update memory
            if self.memory:
                self.memory.add_message("user", prompt)
                self.memory.add_message("assistant", content or "")

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
            if hasattr(tool_call, "function"):
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
            else:
                tool_name = tool_call.get("name")
                arguments = json.loads(tool_call.get("arguments", "{}"))

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
        self._tool_registry: dict[str, Callable] = {}

    def register_tool(self, name: str, func: Callable) -> None:
        """Register a global tool available to all agents."""
        self._tool_registry[name] = func

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
        for tool_name in config.tools:
            if tool_name in self._tool_registry:
                agent_tools[tool_name] = self._tool_registry[tool_name]

        agent = Agent(config, self.router, agent_tools)
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
        for tool_name in config.tools:
            if tool_name in self._tool_registry:
                agent_tools[tool_name] = self._tool_registry[tool_name]
        agent.tools = agent_tools

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
