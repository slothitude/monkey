# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

This is a multi-project workspace containing:

| Project | Language | Description |
|---------|----------|-------------|
| `llm-router/` | Python 3.10+ | Universal Agent Platform - unified LLM router with agent framework, workflow orchestration, and Telegram integration |
| `pi-mono/` | TypeScript | Pi coding agent monorepo with AI, agent-core, TUI, and web-ui packages |
| `cchips/` | Docker | Docker deployment configurations for the platform |

---

## llm-router (Python) - Universal Agent Platform

### Commands

```bash
# Installation
pip install -e .

# Run server
llm-router                                    # Start with GUI at http://localhost:8000
python -m llm_router.server.api               # Alternative entry point
uvicorn llm_router.server.api:app --reload    # Development mode

# MCP server (for Claude Code integration)
python -m llm_router.mcp_server               # Start MCP server on stdio

# Game agent
python -m llm_router.game_agent play --url http://localhost:8888   # Play a game
python -m llm_router.game_agent learn                              # Learn visual templates

# Testing
pytest tests/ -v                              # Run all tests
pytest tests/test_router.py -v                # Run specific test file
pytest tests/ --cov=llm_router --cov-report=html  # With coverage

# Docker
cd cchips && docker-compose up --build        # Build and run container
```

### Architecture

```
llm_router/
├── __init__.py          # Public API exports (LLMRouter, ParallelExecutor)
├── router.py            # Core router with failover, load balancing, stats
├── config.py            # YAML config loading with env var substitution
├── models.py            # Pydantic models (OpenAI-compatible)
├── parallel.py          # Broadcast, map, race patterns for multi-model execution
├── agent_framework.py   # Universal agent framework with agentic tool-calling loop
├── orchestrator.py      # DAG/sequential/parallel workflow orchestration
├── worker_pool.py       # Dynamic worker agents with skill-based task delegation
├── mcp_server.py        # MCP server (stdio) exposing 40+ tools to Claude Code
├── mcp_worker.py        # MCP bridge wrapping async worker pool ops for MCP protocol
├── telegram_bot.py      # Telegram bot integration for agent control
├── providers/
│   ├── base.py          # Abstract BaseProvider class
│   ├── openai.py        # OpenAI provider implementation
│   ├── anthropic.py     # Anthropic provider implementation
│   └── openai_compatible.py  # Generic OpenAI-compatible (OpenRouter, NVIDIA, etc.)
├── server/
│   ├── api.py           # FastAPI server with all endpoints
│   └── static/          # Web dashboard and game gallery UI
├── tools/
│   ├── __init__.py      # ToolRegistry singleton with auto-registration
│   ├── builtin.py       # Built-in tools (web_search, file_ops, code_exec, api_call)
│   ├── godot_tools.py   # Godot project/scene/script creation and web export
│   ├── godot_assets.py  # Kenney.nl asset browser, sprite/sound generation
│   ├── godot_debug.py   # Project validation and scene debugging
│   ├── godot_templates.py # Pre-built game templates (pong, platformer, shooter, etc.)
│   ├── godot_hunyuan.py # Hunyuan3D integration for 3D asset generation
│   ├── ai_art.py        # AI-generated sprites and textures
│   ├── itchio_tools.py  # Butler CLI for itch.io publishing
│   ├── blender_workflow.py  # Blender Python API integration
│   ├── mixamo_workflow.py   # Adobe Mixamo animation tools
│   ├── godot_screenshot.py  # Visual feedback: screenshot capture and comparison
│   ├── godot_juice.py       # Game juice effects (camera shake, hit flash, squash/stretch)
│   ├── godot_difficulty.py  # Parameterized difficulty curves (linear/exponential/step/sigmoid)
│   ├── godot_design.py      # Game design prompt templates and design review
│   └── game_library.py  # Game metadata and library management
├── game_agent/          # Autonomous game-playing agent
│   ├── browser.py       # Browser automation via Playwright
│   ├── player.py        # Game player logic
│   ├── cli.py           # CLI: play, learn, detect commands
│   ├── vision/          # Fast visual template matching
│   ├── decision/        # Rules engine and state machine
│   └── improvement/     # Q-learning with replay buffer
└── agent_builder/       # Pi agent component generators
    ├── skills.py        # SKILL.md generator with templates
    ├── extensions.py    # TypeScript extension generator
    └── prompts.py       # System prompt generator
```

### Core Concepts

#### Agent Framework

Create any type of AI agent with custom tools, prompts, and behavior:

```python
from llm_router.agent_framework import AgentRegistry, AgentConfig

registry = AgentRegistry(router)

# Create an agent
agent = registry.create_agent(AgentConfig(
    name="Research Agent",
    description="Searches web and summarizes findings",
    agent_type="research",
    model="claude-sonnet-4-6-20250929",
    tools=["web_search", "api_call"],
    system_prompt="You are a research assistant...",
    memory_enabled=True
))

# Execute agent
result = await registry.execute("agent-id", "What is the latest AI news?")
```

#### Workflow Orchestration

Multi-agent workflows with DAG, sequential, and parallel modes:

```python
from llm_router.orchestrator import WorkflowConfig, WorkflowMode

workflow = registry.create_workflow(WorkflowConfig(
    name="Research Pipeline",
    mode=WorkflowMode.SEQUENTIAL,
    nodes=[
        {"id": "search", "agent_id": "researcher"},
        {"id": "summarize", "agent_id": "summarizer"},
    ]
))

result = await registry.execute(workflow.id, "What is quantum computing?")
```

#### Built-in Tools

| Tool | Description | Category |
|------|-------------|----------|
| `web_search` | Search the web (SearXNG, Brave) | research |
| `url_fetch` | Fetch and extract web page content | research |
| `file_read` | Read file contents | file_ops |
| `file_write` | Write to files | file_ops |
| `file_list` | List directory contents | file_ops |
| `code_exec` | Execute code (Python, JS, Bash) | execution |
| `api_call` | Make HTTP requests | network |
| `db_query` | Execute SQL queries | database |

#### Game Development Tools

Registered as Godot tools via `tools/godot_tools.py`. The MCP server exposes 40+ tools including project creation, scene building, script generation, web export, asset management, AI art generation, and itch.io publishing.

#### Worker Pool and MCP Integration

Workers are persistent agents with specialized skills, stored in `./data/workers/workers.json`. The MCP server (`mcp_server.py`) bridges Claude Code to the router by exposing tools like `delegate_task`, `analyze_task`, `spawn_worker`, `execute_skill`, `list_workers`, and `list_skills`. MCP workers wrap async operations with sync functions for stdio protocol compatibility.

### API Endpoints

#### Agents
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/agents` | GET | List all agents |
| `/v1/agents` | POST | Create agent |
| `/v1/agents/{id}` | GET | Get agent config |
| `/v1/agents/{id}` | PUT | Update agent |
| `/v1/agents/{id}` | DELETE | Delete agent |
| `/v1/agents/{id}/execute` | POST | Execute agent with prompt |
| `/v1/agents/{id}/stream` | GET | SSE execution stream |

#### Workflows
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/orchestrate` | GET | List all workflows |
| `/v1/orchestrate` | POST | Create workflow |
| `/v1/orchestrate/{id}` | GET | Get workflow |
| `/v1/orchestrate/{id}` | DELETE | Delete workflow |
| `/v1/orchestrate/{id}/execute` | POST | Execute workflow |
| `/v1/orchestrate/{id}/stream` | GET | SSE real-time updates |

#### Tools
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/tools` | GET | List available tools |
| `/v1/tools/{name}` | GET | Get tool definition |

#### Providers
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/providers` | GET | List providers |
| `/v1/providers` | POST | Register provider |
| `/v1/providers/{name}/models` | GET | Get available models |
| `/v1/providers/{name}` | DELETE | Remove provider |

#### Telegram
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/telegram/config` | POST | Configure bot |
| `/v1/telegram/status` | GET | Bot status |
| `/v1/telegram/start` | POST | Start bot |
| `/v1/telegram/stop` | POST | Stop bot |

#### Chat (OpenAI-compatible)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Chat completions (streaming supported) |
| `/v1/models` | GET | List available models |
| `/v1/parallel` | POST | Parallel execution across models |

### Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and help |
| `/agents` | List available agents |
| `/use <agent>` | Select an agent |
| `/run <agent> <prompt>` | Execute agent |
| `/workflow <mode> <agents...>` | Create multi-agent workflow |
| `/status` | Check status |
| `/tools` | List available tools |
| `/clear` | Clear conversation history |

### Key Patterns

- **Provider Selection**: Model name patterns (e.g., `gpt-*`) map to providers via `_model_to_provider`
- **Failover**: Requests automatically retry with next provider on failure
- **Load Balancing**: `load_balance` param accepts: `priority`, `round_robin`, `least_connections`, `random`
- **Parallel Execution**: `ParallelExecutor` class provides `broadcast()`, `map()`, `race()` methods
- **Agent Memory**: Persistent conversation memory with configurable max messages
- **Workflow DAG**: Topological sort ensures dependencies are respected
- **Tool Registry**: Singleton `ToolRegistry` auto-registers all tool modules on init; tools expose OpenAI-compatible definitions
- **Worker Pool**: Dynamic worker spawning with skill-based task delegation; workers persist to disk across restarts
- **MCP Protocol**: `mcp_server.py` is a stdio-based JSON-RPC server; `mcp_worker.py` bridges async worker pool ops to sync MCP handlers

### Games Directory

`llm-router/games/` contains multiple Godot game projects created with the tool system:
- `MyPlatformer/` - 2D platformer with Claude Chat editor plugin in `addons/claude_chat/`
- `SpaceInvaders/`, `SpaceShooter/`, `ZeldaGameBoy/`, `slothitude-pong/`, `dungeon-crawler-jam-2026/`, `sloth-forest/`
- Each game is a self-contained Godot 4.6 project

---

## cchips (Docker Deployment)

### Quick Start

```bash
cd cchips
cp .env.example .env
# Edit .env with your API keys
docker-compose up -d
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| llm-router | 8000 | Main API server with dashboard |
| searxng | 8888 | Privacy-focused search engine |
| redis | 6379 | Caching and session storage |

---

## pi-mono (TypeScript)

### Commands

```bash
# Installation
npm install

# Build all packages
npm run build

# Lint, format, type check (requires build first)
npm run check

# Run tests
./test.sh                    # All tests (skips LLM tests without API keys)
npx tsx ../../node_modules/vitest/dist/cli.js --run test/specific.test.ts  # Single test

# Run pi from source
./pi-test.sh
```

### Package Structure

| Package | Description |
|---------|-------------|
| `packages/ai` | Unified multi-provider LLM API (OpenAI, Anthropic, Google, etc.) |
| `packages/agent` | Agent runtime with tool calling and state management |
| `packages/coding-agent` | Interactive coding agent CLI |
| `packages/tui` | Terminal UI library with differential rendering |
| `packages/web-ui` | Web components for AI chat interfaces |
| `packages/mom` | Slack bot delegating to pi coding agent |
| `packages/pods` | CLI for managing vLLM deployments |

**Important**: See `pi-mono/AGENTS.md` for detailed development rules including:
- Adding a new LLM provider (required changes across multiple files)
- Changelog format and release process
- OSS weekend mode
- GitHub issue/PR workflow

### Release Process

All packages share the same version (lockstep versioning):
```bash
npm run release:patch    # Bug fixes and new features
npm run release:minor    # API breaking changes
```

### Code Quality Rules

- No `any` types unless absolutely necessary
- **NEVER use inline imports** - always use top-level imports
- Check `node_modules` for external API type definitions
- Never remove functionality without asking
- All keybindings must be configurable (no hardcoded key checks)

### Testing with tmux

```bash
tmux new-session -d -s pi-test -x 80 -y 24
tmux send-keys -t pi-test "cd /path/to/pi-mono && ./pi-test.sh" Enter
sleep 3 && tmux capture-pane -t pi-test -p
tmux send-keys -t pi-test "your prompt here" Enter
tmux kill-session -t pi-test
```

### Tests

Tests are located in `packages/*/test/` directories. Run from the package root:
```bash
cd packages/ai && npx tsx ../../node_modules/vitest/dist/cli.js --run test/stream.test.ts
```

---

## Git Workflow

- Only commit files YOU changed in THIS session
- Use `git add <specific-files>` - NEVER `git add -A` or `git add .`
- Never use destructive commands: `git reset --hard`, `git checkout .`, `git clean -fd`
- Include `fixes #<number>` in commit messages when applicable

## Style

- No emojis in commits, issues, PR comments, or code
- No fluff or cheerful filler text
- Keep answers short and concise
