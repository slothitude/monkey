"""FastAPI server providing OpenAI-compatible API."""

import json
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any
import time
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from llm_router import LLMRouter
from llm_router.config import load_config
from llm_router.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from pydantic import BaseModel
from llm_router.parallel import ParallelExecutor, ParallelConfig

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


# Global router instance
router: LLMRouter | None = None
config_path: str = "config.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    global router
    router = LLMRouter(load_config(config_path))
    yield
    router = None


app = FastAPI(
    title="LLM Router",
    description="OpenAI-compatible API router for multiple LLM providers",
    version="0.1.0",
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    r = get_router()
    available = await r.is_available()
    return {
        "status": "healthy" if available else "degraded",
        "providers": list(r._providers.keys()),
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
    # Calculate success rate for each provider
    result = {}
    for name, s in stats.items():
        result[name] = {
            **s,
            "success_rate": s.get("success_rate", 1.0) if s.get("requests", 0) > 0 else 1.0
        }
    return result


# GUI endpoints
@app.get("/", response_class=HTMLResponse)
async def gui():
    """Serve the GUI."""
    static_path = Path(__file__).parent / "static" / "index.html"
    if static_path.exists():
        return HTMLResponse(content=static_path.read_text(encoding="utf-8"), status_code=200)
    return HTMLResponse(content="<h1>GUI not found</h1>", status_code=404)


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


class ParallelRequest(BaseModel):
    mode: str = "broadcast"  # broadcast or race
    prompt: str
    system_prompt: str | None = None
    models: list[str]
    max_concurrent: int = 5
    max_tokens: int = 500


# Agent Builder request models
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
        # Broadcast mode
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
                "latency": total_latency / len(data.models),  # Approximate
            })

    return {"results": results}


# Agent Builder endpoints
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


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: str | None = Header(default=None),
):
    """Handle chat completion requests (OpenAI-compatible)."""
    r = get_router()

    # Convert messages to dict format
    messages = [msg.model_dump(exclude_none=True) for msg in request.messages]

    # Build kwargs from request
    kwargs: dict[str, Any] = {}
    for key in ["temperature", "top_p", "max_tokens", "stop",
                "presence_penalty", "frequency_penalty", "user"]:
        value = getattr(request, key, None)
        if value is not None:
            kwargs[key] = value

    # Handle any extra fields
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

    # Get config path from args or use default
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
