# Universal Agent Platform - Docker Deployment

This directory contains Docker deployment configurations for the Universal Agent Platform.

## Quick Start

1. Copy the environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your API keys:
   ```bash
   OPENAI_API_KEY=sk-your-key
   ANTHROPIC_API_KEY=sk-ant-your-key
   ```

3. Start the platform:
   ```bash
   docker-compose up -d
   ```

4. Access the dashboard at http://localhost:8000

## Services

| Service | Port | Description |
|---------|------|-------------|
| llm-router | 8000 | Main API server with dashboard |
| searxng | 8888 | Privacy-focused search engine |
| redis | 6379 | Caching and session storage |

## Configuration

Edit `config.yaml` to:
- Enable/disable providers
- Configure models
- Set up workflow defaults
- Customize tool settings

## Telegram Bot

To enable Telegram bot:

1. Create a bot via [@BotFather](https://t.me/botfather)
2. Add the token to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=your-bot-token
   ```
3. Configure via API or dashboard:
   ```bash
   curl -X POST http://localhost:8000/v1/telegram/config \
     -H "Content-Type: application/json" \
     -d '{"token": "your-bot-token"}'
   ```
4. Start the bot:
   ```bash
   curl -X POST http://localhost:8000/v1/telegram/start
   ```

### Telegram Commands

| Command | Description |
|---------|-------------|
| /start | Welcome message |
| /agents | List available agents |
| /use <agent> | Select an agent |
| /run <agent> <prompt> | Execute agent |
| /workflow <mode> <agents...> | Run multi-agent workflow |
| /tools | List available tools |
| /clear | Clear conversation |

## API Endpoints

### Agents
- `GET /v1/agents` - List all agents
- `POST /v1/agents` - Create agent
- `GET /v1/agents/{id}` - Get agent
- `PUT /v1/agents/{id}` - Update agent
- `DELETE /v1/agents/{id}` - Delete agent
- `POST /v1/agents/{id}/execute` - Execute agent

### Workflows
- `GET /v1/orchestrate` - List workflows
- `POST /v1/orchestrate` - Create workflow
- `POST /v1/orchestrate/{id}/execute` - Execute workflow

### Tools
- `GET /v1/tools` - List available tools

### Providers
- `GET /v1/providers` - List providers

### Chat (OpenAI-compatible)
- `POST /v1/chat/completions` - Chat completions

## Health Check

```bash
curl http://localhost:8000/health
```

## Logs

```bash
docker-compose logs -f llm-router
```

## Stop

```bash
docker-compose down
```

## Rebuild

```bash
docker-compose up -d --build
```
