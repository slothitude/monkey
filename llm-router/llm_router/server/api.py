"""FastAPI server providing OpenAI-compatible API and Universal Agent Platform."""

import json
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
import time
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from llm_router import LLMRouter
from llm_router.config import load_config, ProviderConfig
from llm_router.models import ChatCompletionRequest, ChatCompletionResponse
from pydantic import BaseModel

from llm_router.parallel import ParallelExecutor, ParallelConfig

# Agent Framework
from llm_router.agent_framework import (
    AgentRegistry,
    AgentConfig,
    Agent,
    AgentStatus,
    AgentType,
)

# Orchestrator
from llm_router.orchestrator import (
    WorkflowRegistry,
    WorkflowConfig,
    WorkflowMode,
    WorkflowStatus,
    WorkflowExecution,
)

# Tools
from llm_router.tools import get_tool_registry, ToolDefinition

# Telegram
from llm_router.telegram_bot import TelegramBot, TelegramConfig, BotStatus

# Agent Builder imports
from llm_router.agent_builder.skills import (
    generate_skill,
    get_available_templates as get_skill_templates,
    get_template as get_skill_template,
    SKILL_TEMPLATES,
    SkillCategory,
)
from llm_router.agent_builder.extensions import (
    generate_extension,
    get_available_templates as get_extension_templates,
    get_template as get_extension_template,
    EXTENSION_TEMPLATES,
    ExtensionType,
)
from llm_router.agent_builder.prompts import (
    generate_prompt,
    get_available_templates as get_prompt_templates,
    get_template as get_prompt_template,
    PROMPT_TEMPLATES,
    PromptStyle,
)


# Global instances
router: LLMRouter | None = None
agent_registry: AgentRegistry | None = None
workflow_registry: WorkflowRegistry | None = None
telegram_bot: TelegramBot | None = None
config_path: str = "config.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    global router, agent_registry, workflow_registry, telegram_bot

    # Initialize router
    router = LLMRouter(load_config(config_path))

    # Initialize agent registry
    agent_registry = AgentRegistry(router)

    # Register built-in tools
    tool_registry = get_tool_registry()
    for tool_name in tool_registry.get_functions():
        agent_registry.register_tool(tool_name, tool_registry.get(tool_name).function)

    # Initialize workflow registry
    workflow_registry = WorkflowRegistry(agent_registry)

    yield

    # Cleanup
    if telegram_bot and telegram_bot.status == BotStatus.RUNNING:
        await telegram_bot.stop()

    router = None
    agent_registry = None
    workflow_registry = None


app = FastAPI(
    title="Universal Agent Platform",
    description="OpenAI-compatible API router with universal agent framework, multi-agent workflows, and Telegram integration",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_router() -> LLMRouter:
    """Get the router instance or raise 503 if not available."""
    if router is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return router


def get_agent_registry() -> AgentRegistry:
    """Get the agent registry or raise 503 if not available."""
    if agent_registry is None:
        raise HTTPException(status_code=503, detail="Agent registry not initialized")
    return agent_registry


def get_workflow_registry() -> WorkflowRegistry:
    """Get the workflow registry or raise 503 if not available."""
    if workflow_registry is None:
        raise HTTPException(status_code=503, detail="Workflow registry not initialized")
    return workflow_registry


# ==================== Health & System ====================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    r = get_router()
    available = await r.is_available()
    return {
        "status": "healthy" if available else "degraded",
        "providers": list(r._providers.keys()),
        "agents": len(get_agent_registry().list_agents()),
        "workflows": len(get_workflow_registry().list_workflows()),
        "telegram": telegram_bot.status.value if telegram_bot else "stopped",
    }


@app.get("/v1/models")
async def list_models():
    """List available models (OpenAI-compatible)."""
    r = get_router()
    return r.get_models().model_dump()


@app.get("/v1/stats")
async def get_stats():
    """Get provider statistics (monitoring)."""
    r = get_router()
    stats = r.get_stats()
    result = {}
    for name, s in stats.items():
        result[name] = {
            **s,
            "success_rate": s.get("success_rate", 1.0) if s.get("requests", 0) > 0 else 1.0
        }
    return result


# ==================== GUI ====================

@app.get("/", response_class=HTMLResponse)
async def gui():
    """Serve the GUI."""
    static_path = Path(__file__).parent / "static" / "index.html"
    if static_path.exists():
        return HTMLResponse(content=static_path.read_text(encoding="utf-8"), status_code=200)
    return HTMLResponse(content="<h1>GUI not found</h1>", status_code=404)


# ==================== Config ====================

@app.get("/v1/config")
async def get_config():
    """Get current configuration."""
    try:
        config_file = Path(config_path)
        if config_file.exists():
            return {"config": config_file.read_text()}
        return {"config": "# No config file found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ConfigUpdate(BaseModel):
    config: str


@app.put("/v1/config")
async def update_config(data: ConfigUpdate):
    """Update configuration file."""
    try:
        config_file = Path(config_path)
        config_file.write_text(data.config)
        return {"success": True, "message": "Configuration saved. Restart server to apply."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Parallel Execution ====================

class ParallelRequest(BaseModel):
    mode: str = "broadcast"  # broadcast or race
    prompt: str
    system_prompt: str | None = None
    models: list[str]
    max_concurrent: int = 5
    max_tokens: int = 500


@app.post("/v1/parallel")
async def run_parallel(data: ParallelRequest):
    """Run parallel execution across multiple models."""
    r = get_router()
    executor = ParallelExecutor(r, ParallelConfig(max_concurrent=data.max_concurrent))

    messages = []
    if data.system_prompt:
        messages.append({"role": "system", "content": data.system_prompt})
    messages.append({"role": "user", "content": data.prompt})

    results = []

    if data.mode == "race":
        try:
            start = time.time()
            result = await executor.race(
                prompt=data.prompt,
                models=data.models,
                system_prompt=data.system_prompt,
                max_tokens=data.max_tokens,
            )
            latency = time.time() - start
            results.append({
                "model": result.model,
                "success": result.success,
                "content": result.content,
                "latency": latency,
            })
        except Exception as e:
            results.append({
                "model": "race",
                "success": False,
                "error": str(e),
            })
    else:
        start = time.time()
        agent_results = await executor.broadcast(
            prompt=data.prompt,
            models=data.models,
            system_prompt=data.system_prompt,
            max_tokens=data.max_tokens,
        )
        total_latency = time.time() - start

        for ar in agent_results:
            results.append({
                "model": ar.model,
                "success": ar.success,
                "content": ar.content,
                "error": str(ar.error) if ar.error else None,
                "latency": total_latency / len(data.models),
            })

    return {"results": results}


# ==================== Agent Management ====================

class AgentCreateRequest(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    agent_type: str = "custom"
    provider: str = "openai"
    model: str = "gpt-4"
    system_prompt: str = "You are a helpful AI assistant."
    tools: list[str] = []
    memory_enabled: bool = True
    max_tokens: int = 4096
    temperature: float = 0.7
    metadata: dict[str, Any] | None = None


class AgentUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    agent_type: str | None = None
    provider: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    memory_enabled: bool | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    metadata: dict[str, Any] | None = None


class AgentExecuteRequest(BaseModel):
    prompt: str
    system_override: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None


@app.get("/v1/agents")
async def list_agents():
    """List all agents."""
    registry = get_agent_registry()
    agents = registry.list_agents()
    return {
        "agents": [agent.to_dict() for agent in agents],
        "count": len(agents),
    }


@app.post("/v1/agents")
async def create_agent(data: AgentCreateRequest):
    """Create a new agent."""
    try:
        registry = get_agent_registry()

        # Map agent_type string to enum
        try:
            agent_type = AgentType(data.agent_type)
        except ValueError:
            agent_type = AgentType.CUSTOM

        config = AgentConfig(
            name=data.name,
            description=data.description,
            agent_type=agent_type,
            provider=data.provider,
            model=data.model,
            system_prompt=data.system_prompt,
            tools=data.tools,
            memory_enabled=data.memory_enabled if data.memory_enabled is not None else True,
            max_tokens=data.max_tokens or 4096,
            temperature=data.temperature if data.temperature is not None else 0.7,
            metadata=data.metadata or {},
        )
        # Only set ID if provided (otherwise use auto-generated)
        if data.id:
            config.id = data.id

        agent = registry.create_agent(config)
        return {"success": True, "agent": agent.to_dict()}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get agent by ID."""
    registry = get_agent_registry()
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return agent.to_dict()


@app.put("/v1/agents/{agent_id}")
async def update_agent(agent_id: str, data: AgentUpdateRequest):
    """Update an agent."""
    registry = get_agent_registry()
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    # Build updated config
    current = agent.config
    updates = data.model_dump(exclude_unset=True)

    config = AgentConfig(
        id=agent_id,
        name=updates.get("name", current.name),
        description=updates.get("description", current.description),
        agent_type=updates.get("agent_type", current.agent_type),
        provider=updates.get("provider", current.provider),
        model=updates.get("model", current.model),
        system_prompt=updates.get("system_prompt", current.system_prompt),
        tools=updates.get("tools", current.tools),
        memory_enabled=updates.get("memory_enabled", current.memory_enabled),
        max_tokens=updates.get("max_tokens", current.max_tokens),
        temperature=updates.get("temperature", current.temperature),
        metadata=updates.get("metadata", current.metadata),
    )

    updated_agent = registry.update_agent(agent_id, config)
    return {"success": True, "agent": updated_agent.to_dict()}


@app.delete("/v1/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete an agent."""
    registry = get_agent_registry()
    deleted = registry.delete_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    return {"success": True, "message": f"Agent '{agent_id}' deleted"}


@app.post("/v1/agents/{agent_id}/execute")
async def execute_agent(agent_id: str, data: AgentExecuteRequest):
    """Execute an agent with a prompt."""
    registry = get_agent_registry()

    try:
        execution = await registry.execute(
            agent_id,
            data.prompt,
            system_override=data.system_override,
            max_tokens=data.max_tokens,
            temperature=data.temperature,
        )
        return execution.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/agents/{agent_id}/stream")
async def stream_agent(agent_id: str, prompt: str = Query(...)):
    """Execute an agent with streaming response (SSE)."""
    registry = get_agent_registry()

    async def event_stream() -> AsyncGenerator[dict, None]:
        try:
            async for chunk in registry.execute_stream(agent_id, prompt):
                yield {"event": "chunk", "data": json.dumps({"content": chunk})}
            yield {"event": "done", "data": json.dumps({"status": "completed"})}
        except ValueError as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(event_stream())


@app.post("/v1/agents/{agent_id}/clear-memory")
async def clear_agent_memory(agent_id: str):
    """Clear an agent's memory."""
    registry = get_agent_registry()
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    agent.clear_memory()
    return {"success": True, "message": f"Memory cleared for agent '{agent_id}'"}


# ==================== Tool Management ====================

class ToolRegisterRequest(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    category: str = "custom"
    dangerous: bool = False
    examples: list[str] = []


@app.get("/v1/tools")
async def list_tools():
    """List all available tools."""
    tool_registry = get_tool_registry()
    tools = tool_registry.list_tools()
    return {
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "category": t.category,
                "dangerous": t.dangerous,
                "examples": t.examples,
            }
            for t in tools
        ],
        "count": len(tools),
    }


@app.get("/v1/tools/{tool_name}")
async def get_tool(tool_name: str):
    """Get tool definition."""
    tool_registry = get_tool_registry()
    tool = tool_registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": tool.parameters,
        "category": tool.category,
        "dangerous": tool.dangerous,
        "examples": tool.examples,
    }


# ==================== Workflow Orchestration ====================

class WorkflowCreateRequest(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    mode: str = "single"
    nodes: list[dict] = []
    edges: list[dict] = []
    input_prompt: str = ""
    max_parallel: int = 5
    timeout: int = 300
    metadata: dict[str, Any] | None = None


class WorkflowExecuteRequest(BaseModel):
    prompt: str
    max_tokens: int | None = None
    temperature: float | None = None


@app.get("/v1/orchestrate")
async def list_workflows():
    """List all workflows."""
    registry = get_workflow_registry()
    workflows = registry.list_workflows()
    return {
        "workflows": [wf.to_dict() for wf in workflows],
        "count": len(workflows),
    }


@app.post("/v1/orchestrate")
async def create_workflow(data: WorkflowCreateRequest):
    """Create a new workflow."""
    registry = get_workflow_registry()

    # Map mode string to enum
    try:
        mode = WorkflowMode(data.mode)
    except ValueError:
        mode = WorkflowMode.SINGLE

    config = WorkflowConfig(
        id=data.id or None,
        name=data.name,
        description=data.description,
        mode=mode,
        nodes=data.nodes,
        edges=data.edges,
        input_prompt=data.input_prompt,
        max_parallel=data.max_parallel,
        timeout=data.timeout,
        metadata=data.metadata or {},
    )

    workflow = registry.create_workflow(config)
    return {"success": True, "workflow": workflow.to_dict()}


@app.get("/v1/orchestrate/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get workflow by ID."""
    registry = get_workflow_registry()
    workflow = registry.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return workflow.to_dict()


@app.delete("/v1/orchestrate/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Delete a workflow."""
    registry = get_workflow_registry()
    deleted = registry.delete_workflow(workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return {"success": True, "message": f"Workflow '{workflow_id}' deleted"}


@app.post("/v1/orchestrate/{workflow_id}/execute")
async def execute_workflow(workflow_id: str, data: WorkflowExecuteRequest):
    """Execute a workflow."""
    registry = get_workflow_registry()

    try:
        execution = await registry.execute(
            workflow_id,
            data.prompt,
            max_tokens=data.max_tokens,
            temperature=data.temperature,
        )
        return execution.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/orchestrate/{workflow_id}/stream")
async def stream_workflow(workflow_id: str, prompt: str = Query(...)):
    """Execute a workflow with streaming updates (SSE)."""
    registry = get_workflow_registry()

    async def event_stream() -> AsyncGenerator[dict, None]:
        try:
            async for update in registry.execute_stream(workflow_id, prompt):
                yield {"event": update.get("type", "update"), "data": json.dumps(update)}
        except ValueError as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(event_stream())


@app.get("/v1/orchestrate/{workflow_id}/executions")
async def list_workflow_executions(workflow_id: str, limit: int = 20):
    """List executions for a workflow."""
    registry = get_workflow_registry()
    executions = registry.list_executions(workflow_id=workflow_id, limit=limit)
    return {
        "executions": [ex.to_dict() for ex in executions],
        "count": len(executions),
    }


@app.get("/v1/executions/{execution_id}")
async def get_execution(execution_id: str):
    """Get execution by ID."""
    registry = get_workflow_registry()
    execution = registry.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return execution.to_dict()


# ==================== Provider Registry ====================

class ProviderRegisterRequest(BaseModel):
    name: str
    api_key: str
    base_url: str | None = None
    models: list[str] = []
    enabled: bool = True
    priority: int = 100


@app.get("/v1/providers")
async def list_providers():
    """List all providers."""
    r = get_router()
    providers = []
    for name, config in r.config.providers.items():
        providers.append({
            "name": name,
            "enabled": config.enabled,
            "models": config.models,
            "priority": config.priority,
            "base_url": config.base_url,
        })
    return {"providers": providers, "count": len(providers)}


@app.post("/v1/providers")
async def register_provider(data: ProviderRegisterRequest):
    """Register a new provider (requires restart to apply)."""
    r = get_router()

    # Add to config
    r.config.providers[data.name] = ProviderConfig(
        api_key=data.api_key,
        base_url=data.base_url,
        models=data.models,
        enabled=data.enabled,
        priority=data.priority,
    )

    return {
        "success": True,
        "message": f"Provider '{data.name}' registered. Restart server to apply.",
        "provider": {
            "name": data.name,
            "enabled": data.enabled,
            "models": data.models,
        }
    }


@app.post("/v1/providers/validate")
async def validate_provider_credentials(data: ProviderRegisterRequest):
    """Validate provider credentials."""
    # This would test the credentials by making a simple API call
    # For now, just return success
    return {
        "valid": True,
        "message": "Credentials validation not implemented yet",
    }


@app.get("/v1/providers/{provider_name}/models")
async def get_provider_models(provider_name: str):
    """Get available models for a provider."""
    r = get_router()
    config = r.config.providers.get(provider_name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    return {"provider": provider_name, "models": config.models}


@app.delete("/v1/providers/{provider_name}")
async def remove_provider(provider_name: str):
    """Remove a provider (requires restart to apply)."""
    r = get_router()
    if provider_name not in r.config.providers:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")

    del r.config.providers[provider_name]
    return {"success": True, "message": f"Provider '{provider_name}' removed. Restart server to apply."}


# ==================== Telegram ====================

class TelegramConfigRequest(BaseModel):
    token: str
    allowed_users: list[int] = []
    admin_users: list[int] = []
    enable_photos: bool = True


@app.post("/v1/telegram/config")
async def configure_telegram(data: TelegramConfigRequest):
    """Configure the Telegram bot."""
    global telegram_bot

    if telegram_bot and telegram_bot.status == BotStatus.RUNNING:
        await telegram_bot.stop()

    config = TelegramConfig(
        token=data.token,
        allowed_users=data.allowed_users,
        admin_users=data.admin_users,
        enable_photos=data.enable_photos,
    )

    telegram_bot = TelegramBot(config, get_agent_registry(), get_workflow_registry())

    return {"success": True, "message": "Telegram bot configured"}


@app.get("/v1/telegram/status")
async def get_telegram_status():
    """Get Telegram bot status."""
    if not telegram_bot:
        return {"status": "not_configured", "message": "Telegram bot not configured"}

    return {
        "status": telegram_bot.status.value,
        "message": f"Bot is {telegram_bot.status.value}",
    }


@app.post("/v1/telegram/start")
async def start_telegram_bot():
    """Start the Telegram bot."""
    global telegram_bot

    if not telegram_bot:
        raise HTTPException(status_code=400, detail="Telegram bot not configured. Use /v1/telegram/config first.")

    if telegram_bot.status == BotStatus.RUNNING:
        return {"success": True, "message": "Telegram bot is already running"}

    try:
        await telegram_bot.start()
        return {"success": True, "message": "Telegram bot started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start Telegram bot: {str(e)}")


@app.post("/v1/telegram/stop")
async def stop_telegram_bot():
    """Stop the Telegram bot."""
    global telegram_bot

    if not telegram_bot:
        return {"success": True, "message": "Telegram bot not configured"}

    if telegram_bot.status != BotStatus.RUNNING:
        return {"success": True, "message": "Telegram bot is not running"}

    await telegram_bot.stop()
    return {"success": True, "message": "Telegram bot stopped"}


# ==================== Agent Builder ====================

class SkillRequest(BaseModel):
    name: str
    description: str
    category: str = "automation"
    custom_instructions: str | None = None
    include_examples: bool = True


class ExtensionRequest(BaseModel):
    name: str
    description: str
    extension_type: str = "tool"
    custom_code: str | None = None
    dependencies: list[str] | None = None


class PromptRequest(BaseModel):
    name: str
    description: str
    style: str = "instructional"
    role: str | None = None
    capabilities: list[str] | None = None
    guidelines: list[str] | None = None


@app.get("/v1/agent/templates")
async def list_agent_templates():
    """List available agent templates."""
    return {
        "skills": get_skill_templates(),
        "extensions": get_extension_templates(),
        "prompts": get_prompt_templates(),
    }


@app.get("/v1/agent/templates/{template_type}/{name}")
async def get_template(template_type: str, name: str):
    """Get a specific template by type and name."""
    if template_type == "skill":
        template = get_skill_template(name)
    elif template_type == "extension":
        template = get_extension_template(name)
    elif template_type == "prompt":
        template = get_prompt_template(name)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown template type: {template_type}")

    if template is None:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")

    return {"template": template}


@app.post("/v1/agent/skill")
async def create_skill(data: SkillRequest):
    """Generate a pi skill based on description."""
    try:
        category = SkillCategory(data.category)
    except ValueError:
        category = SkillCategory.AUTOMATION

    skill = generate_skill(
        name=data.name,
        description=data.description,
        category=category,
        custom_instructions=data.custom_instructions,
        include_examples=data.include_examples,
    )

    return {
        "success": True,
        "skill": {
            "name": skill.name,
            "description": skill.description,
            "category": skill.category.value,
            "content": skill.content,
            "triggers": skill.triggers,
            "examples": skill.examples,
        },
    }


@app.post("/v1/agent/extension")
async def create_extension(data: ExtensionRequest):
    """Generate a pi extension based on description."""
    try:
        ext_type = ExtensionType(data.extension_type)
    except ValueError:
        ext_type = ExtensionType.TOOL

    extension = generate_extension(
        name=data.name,
        description=data.description,
        extension_type=ext_type,
        custom_code=data.custom_code,
        dependencies=data.dependencies,
    )

    return {
        "success": True,
        "extension": {
            "name": extension.name,
            "description": extension.description,
            "type": extension.extension_type.value,
            "code": extension.code,
            "dependencies": extension.dependencies,
        },
    }


@app.post("/v1/agent/prompt")
async def create_prompt(data: PromptRequest):
    """Generate a pi prompt based on description."""
    try:
        style = PromptStyle(data.style)
    except ValueError:
        style = PromptStyle.INSTRUCTIONAL

    prompt = generate_prompt(
        name=data.name,
        description=data.description,
        style=style,
        role=data.role,
        capabilities=data.capabilities,
        guidelines=data.guidelines,
    )

    return {
        "success": True,
        "prompt": {
            "name": prompt.name,
            "description": prompt.description,
            "style": prompt.style.value,
            "content": prompt.content,
            "variables": prompt.variables,
        },
    }


# ==================== Chat Completions (OpenAI-compatible) ====================

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: str | None = Header(default=None),
):
    """Handle chat completion requests (OpenAI-compatible)."""
    r = get_router()

    messages = [msg.model_dump(exclude_none=True) for msg in request.messages]

    kwargs: dict[str, Any] = {}
    for key in ["temperature", "top_p", "max_tokens", "stop",
                "presence_penalty", "frequency_penalty", "user"]:
        value = getattr(request, key, None)
        if value is not None:
            kwargs[key] = value

    if hasattr(request, "__pydantic_extra__") and request.__pydantic_extra__:
        kwargs.update(request.__pydantic_extra__)

    if request.stream:
        return StreamingResponse(
            stream_response(r, messages, request.model, kwargs),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    try:
        response = await r.chat(messages, request.model, **kwargs)
        return JSONResponse(content=response.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def stream_response(
    r: LLMRouter,
    messages: list[dict],
    model: str,
    kwargs: dict[str, Any],
):
    """Generate SSE stream for chat completion."""
    try:
        async for chunk in r.stream(messages, model, **kwargs):
            data = json.dumps(chunk.model_dump())
            yield f"data: {data}\n\n"

        yield "data: [DONE]\n\n"
    except Exception as e:
        error_data = json.dumps({"error": str(e)})
        yield f"data: {error_data}\n\n"


def run_server():
    """Run the API server."""
    import uvicorn
    import sys

    global config_path
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    uvicorn.run(
        "llm_router.server.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    run_server()
