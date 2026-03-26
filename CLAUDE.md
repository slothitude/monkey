# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

This is a multi-project workspace containing:

| Project | Language | Description |
|---------|----------|-------------|
| `llm-router/` | Python 3.10+ | Unified LLM router with OpenAI-compatible API, parallel execution, and agent builder |
| `pi-mono/` | TypeScript | Pi coding agent monorepo with AI, agent-core, TUI, and web-ui packages |

---

## llm-router (Python)

### Commands

```bash
# Installation
pip install -e .

# Run server
llm-router                                    # Start with GUI at http://localhost:8000
python -m llm_router.server.api               # Alternative entry point
uvicorn llm_router.server.api:app --reload    # Development mode

# Testing
pytest tests/ -v                              # Run all tests
pytest tests/test_router.py -v                # Run specific test file
pytest tests/ --cov=llm_router --cov-report=html  # With coverage

# Docker
docker-compose up --build                     # Build and run container
```

### Architecture

```
llm_router/
├── __init__.py          # Public API exports (LLMRouter, ParallelExecutor)
├── router.py            # Core router with failover, load balancing, stats
├── config.py            # YAML config loading with env var substitution
├── models.py            # Pydantic models (OpenAI-compatible)
├── parallel.py          # Broadcast, map, race patterns for multi-model execution
├── providers/
│   ├── base.py          # Abstract BaseProvider class
│   ├── openai.py        # OpenAI provider implementation
│   ├── anthropic.py     # Anthropic provider implementation
│   └── openai_compatible.py  # Generic OpenAI-compatible (OpenRouter, etc.)
├── server/
│   ├── api.py           # FastAPI server with OpenAI-compatible endpoints
│   └── static/index.html # Web GUI (chat, parallel, agent builder, config)
└── agent_builder/       # Pi agent component generators
    ├── skills.py        # SKILL.md generator with templates
    ├── extensions.py    # TypeScript extension generator
    └── prompts.py       # System prompt generator
```

### Key Patterns

- **Provider Selection**: Model name patterns (e.g., `gpt-*`) map to providers via `_model_to_provider`
- **Failover**: Requests automatically retry with next provider on failure
- **Load Balancing**: `load_balance` param accepts: `priority`, `round_robin`, `least_connections`, `random`
- **Parallel Execution**: `ParallelExecutor` class provides `broadcast()`, `map()`, `race()` methods

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with provider status |
| `/v1/models` | GET | List available models |
| `/v1/chat/completions` | POST | Chat completions (streaming supported) |
| `/v1/parallel` | POST | Parallel execution across models |
| `/v1/agent/templates` | GET | List agent builder templates |
| `/v1/agent/skill` | POST | Generate pi skill |
| `/v1/agent/extension` | POST | Generate pi extension |
| `/v1/agent/prompt` | POST | Generate pi prompt |

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
