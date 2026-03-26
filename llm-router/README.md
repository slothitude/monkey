# LLM Router

A unified LLM router supporting multiple providers with an OpenAI-compatible API.

## Features

- **Multiple Providers**: OpenAI, Anthropic, OpenRouter, zai coding, and any OpenAI-compatible API
- **Unified SDK**: Clean Python SDK for direct library usage
- **OpenAI-Compatible API**: Drop-in FastAPI server that mimics OpenAI's API
- **Streaming Support**: Async generators for consistent streaming across providers
- **Failover**: Automatic failover between providers on errors
- **Model Routing**: Route requests to providers based on model name patterns
- **Parallel Execution**: Run multiple agents in parallel with broadcast, map, and race patterns
- **Load Balancing**: Distribute requests across providers (priority, round-robin, least-connections, random)
- **Statistics**: Track provider performance and success rates
- **Pi Agent Builder**: Generate skills, extensions, and prompts for pi agents

## Pi Agent Builder

The Agent Builder feature helps you create pi agent components:

### Skills (SKILL.md)
Generate agent skills with triggers, behavior guidelines, and examples:

```bash
curl -X POST http://localhost:8000/v1/agent/skill \
  -H "Content-Type: application/json" \
  -d '{
    "name": "code-reviewer",
    "description": "Reviews code for bugs and security issues",
    "category": "code",
    "include_examples": true
  }'
```

### Extensions (.ts)
Generate TypeScript extensions for pi agents:

```bash
curl -X POST http://localhost:8000/v1/agent/extension \
  -H "Content-Type: application/json" \
  -d '{
    "name": "web-scraper",
    "description": "Scrapes content from web pages",
    "extension_type": "tool",
    "dependencies": ["zod", "@anthropic-ai/sdk"]
  }'
```

### Prompts (.md)
Generate structured prompts for agent behavior:

```bash
curl -X POST http://localhost:8000/v1/agent/prompt \
  -H "Content-Type: application/json" \
  -d '{
    "name": "technical-writer",
    "description": "Expert technical documentation writer",
    "style": "instructional",
    "capabilities": ["API documentation", "User guides", "README files"],
    "guidelines": ["Use simple language", "Include examples"]
  }'
```

### Web UI
Access the Agent Builder tab in the web interface at http://localhost:8000 to:
- Generate components visually
- Preview generated code
- Download or copy to clipboard
- Load from templates

## Installation

```bash
cd llm-router
pip install -e .
```

Or with requirements.txt:

```bash
pip install -r requirements.txt
```

## Docker

Run with Docker Compose:

```bash
# 1. Create config file
cp config.yaml.example config.yaml
# Edit config.yaml with your API keys

# 2. Create .env file (optional - for environment variables)
cp .env.example .env
# Edit .env with your API keys

# 3. Build and run
docker-compose up --build

# 4. Access the GUI
# Open http://localhost:8000
```

Or run with Docker directly:

```bash
# Build
docker build -t llm-router .

# Run
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -v $(pwd)/config.yaml:/app/data/config.yaml:ro \
  llm-router
```

Test the container:

```bash
curl http://localhost:8000/health
```

## Quick Start

1. **Configure API keys** (one of these methods):

   ```bash
   # Option A: Environment variables
   export OPENAI_API_KEY=sk-...
   export ANTHROPIC_API_KEY=sk-ant-...

   # Option B: Config file
   cp config.yaml.example config.yaml
   # Edit config.yaml with your API keys
   ```

2. **Start the server with GUI**:

   ```bash
   llm-router
   # or
   python -m llm_router.server.api
   ```

3. **Open the GUI**: http://localhost:8000

   The GUI provides:
   - **Chat**: Interactive chat with any model
   - **Parallel**: Broadcast prompts to multiple models simultaneously
   - **Providers**: View configured providers
   - **Stats**: Monitor provider performance
   - **Config**: Edit configuration live

## Configuration

1. Copy the example config:
```bash
cp config.yaml.example config.yaml
cp .env.example .env
```

2. Edit `.env` with your API keys:
```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

3. Optionally customize `config.yaml` for your needs.

## Usage

### SDK

```python
import asyncio
from llm_router import LLMRouter

async def main():
    router = LLMRouter.from_config("config.yaml")

    # Non-streaming
    response = await router.chat(
        messages=[{"role": "user", "content": "Hello!"}],
        model="gpt-4",
    )
    print(response.choices[0].message.content)

    # Streaming
    async for chunk in router.stream(
        messages=[{"role": "user", "content": "Hello!"}],
        model="gpt-4",
    ):
        for choice in chunk.choices:
            if "content" in choice.get("delta", {}):
                print(choice["delta"]["content"], end="")

asyncio.run(main())
```

### API Server

Start the server:
```bash
# Start with GUI
llm-router

# Or with uvicorn
uvicorn llm_router.server.api:app --reload --port 8000
```

Open http://localhost:8000 for the web GUI.

Make API requests:
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer test" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}'
```

### Parallel API

Run parallel requests via API:
```bash
curl -X POST http://localhost:8000/v1/parallel \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "broadcast",
    "prompt": "What is 2+2?",
    "models": ["gpt-4", "gpt-3.5-turbo", "claude-3-haiku"],
    "max_concurrent": 3
  }'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/v1/models` | GET | List available models |
| `/v1/stats` | GET | Provider statistics |
| `/v1/chat/completions` | POST | Chat completions (supports streaming) |

## Configuration Reference

```yaml
providers:
  openai:
    api_key: ${OPENAI_API_KEY}  # Or hardcoded
    models:
      - "gpt-4"
      - "gpt-*"  # Wildcard support
    enabled: true
    priority: 1  # Lower = higher priority for failover

  openrouter:
    api_key: ${OPENROUTER_API_KEY}
    base_url: "https://openrouter.ai/api/v1"
    models:
      - "anthropic/claude-3-opus"
    extra:
      headers:
        HTTP-Referer: "https://your-app.com"

default_provider: openai
failover_enabled: true
timeout: 60
```

## Parallel Agent Execution

Connect multiple agents in parallel:

```python
from llm_router import LLMRouter, ParallelExecutor

router = LLMRouter.from_config("config.yaml")
executor = ParallelExecutor(router)

# Broadcast same prompt to multiple models
results = await executor.broadcast(
    prompt="What is 2+2?",
    models=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"]
)

for result in results:
    print(f"{result.model}: {result.content}")

# Map different agents to different models
results = await executor.map([
    {"agent_id": "researcher", "model": "gpt-4", "messages": [...]},
    {"agent_id": "writer", "model": "claude-3-opus", "messages": [...]},
    {"agent_id": "reviewer", "model": "gpt-3.5-turbo", "messages": [...]},
])

# Race - first response wins
result = await executor.race(
    prompt="Quick question?",
    models=["gpt-4", "claude-3-haiku"]
)
```

## Load Balancing

Distribute requests across providers:

```python
# Round-robin distribution
response = await router.chat(
    messages=[...],
    model="gpt-4",
    load_balance="round_robin"  # or: priority, least_connections, random
)

# Get provider statistics
stats = router.get_stats()
# {'openai': {'requests': 10, 'successes': 9, 'failures': 1, 'avg_latency': 0.5, 'success_rate': 0.9}}
```

## Testing

Run the test suite:

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=llm_router --cov-report=html

# Run specific test file
pytest tests/test_router.py -v
```

Test structure:
```
tests/
├── conftest.py        # Shared fixtures (mock providers)
├── test_router.py     # Router core tests
├── test_parallel.py   # Parallel execution tests
├── test_api.py        # FastAPI endpoint tests
├── test_config.py     # Configuration tests
└── test_providers.py  # Provider implementation tests
```

## License

MIT
