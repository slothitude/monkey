"""Telegram bot integration for controlling agents."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from enum import Enum

from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BotStatus(str, Enum):
    """Bot status."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class TelegramConfig:
    """Configuration for Telegram bot."""
    token: str
    allowed_users: list[int] = field(default_factory=list)  # Empty = all users
    admin_users: list[int] = field(default_factory=list)
    max_message_length: int = 4096
    rate_limit: int = 10  # Messages per minute per user
    enable_voice: bool = False
    enable_photos: bool = True


@dataclass
class UserSession:
    """Session state for a Telegram user."""
    user_id: int
    username: str | None = None
    current_agent: str | None = None
    conversation_history: list[dict] = field(default_factory=list)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    message_count: int = 0

    def add_message(self, role: str, content: str) -> None:
        """Add a message to history."""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
        # Keep last 20 messages
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]
        self.last_activity = datetime.utcnow()


class TelegramBot:
    """
    Telegram bot for controlling agents via Telegram.

    Commands:
        /start - Welcome message and help
        /agents - List available agents
        /use <agent> - Select an agent to use
        /run <agent> <prompt> - Execute agent with prompt
        /workflow <mode> <agents...> - Create multi-agent workflow
        /status [id] - Check execution status
        /cancel <id> - Cancel execution
        /tools - List available tools
        /clear - Clear conversation history
        /help - Show help

    Example:
        bot = TelegramBot(config, agent_registry, workflow_registry)
        await bot.start()

        # Later
        await bot.stop()
    """

    def __init__(
        self,
        config: TelegramConfig,
        agent_registry: Any,  # AgentRegistry
        workflow_registry: Any | None = None,  # WorkflowRegistry
    ):
        self.config = config
        self.agent_registry = agent_registry
        self.workflow_registry = workflow_registry
        self.status = BotStatus.STOPPED
        self._sessions: dict[int, UserSession] = {}
        self._bot = None
        self._application = None
        self._running_executions: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        """Start the Telegram bot."""
        try:
            from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

            self.status = BotStatus.STARTING

            # Build application
            self._application = (
                ApplicationBuilder()
                .token(self.config.token)
                .build()
            )

            # Register command handlers
            self._application.add_handler(CommandHandler("start", self._handle_start))
            self._application.add_handler(CommandHandler("help", self._handle_help))
            self._application.add_handler(CommandHandler("agents", self._handle_agents))
            self._application.add_handler(CommandHandler("use", self._handle_use))
            self._application.add_handler(CommandHandler("run", self._handle_run))
            self._application.add_handler(CommandHandler("workflow", self._handle_workflow))
            self._application.add_handler(CommandHandler("status", self._handle_status))
            self._application.add_handler(CommandHandler("cancel", self._handle_cancel))
            self._application.add_handler(CommandHandler("tools", self._handle_tools))
            self._application.add_handler(CommandHandler("clear", self._handle_clear))

            # Handle regular messages (for agent conversations)
            self._application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
            )

            # Handle photos (if enabled)
            if self.config.enable_photos:
                self._application.add_handler(
                    MessageHandler(filters.PHOTO, self._handle_photo)
                )

            # Start polling
            await self._application.initialize()
            await self._application.start()
            await self._application.updater.start_polling()

            self.status = BotStatus.RUNNING
            logger.info("Telegram bot started successfully")

        except ImportError:
            logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
            self.status = BotStatus.ERROR
            raise
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
            self.status = BotStatus.ERROR
            raise

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self._application:
            try:
                await self._application.updater.stop()
                await self._application.stop()
                await self._application.shutdown()
            except Exception as e:
                logger.error(f"Error stopping bot: {e}")

        # Cancel any running executions
        for task in self._running_executions.values():
            task.cancel()

        self.status = BotStatus.STOPPED
        logger.info("Telegram bot stopped")

    def _get_session(self, user_id: int, username: str | None = None) -> UserSession:
        """Get or create a user session."""
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession(user_id=user_id, username=username)
        return self._sessions[user_id]

    def _is_allowed(self, user_id: int) -> bool:
        """Check if user is allowed to use the bot."""
        if not self.config.allowed_users:
            return True
        return user_id in self.config.allowed_users

    def _is_admin(self, user_id: int) -> bool:
        """Check if user is an admin."""
        return user_id in self.config.admin_users

    async def _send_message(self, chat_id: int, text: str, parse_mode: str = "Markdown") -> None:
        """Send a message to a chat."""
        if not self._application:
            return

        # Split long messages
        if len(text) > self.config.max_message_length:
            chunks = []
            current = ""
            for line in text.split("\n"):
                if len(current) + len(line) + 1 > self.config.max_message_length:
                    chunks.append(current)
                    current = line
                else:
                    current += "\n" + line if current else line
            if current:
                chunks.append(current)

            for chunk in chunks:
                await self._application.bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode=parse_mode
                )
        else:
            await self._application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode
            )

    # Command Handlers

    async def _handle_start(self, update, context) -> None:
        """Handle /start command."""
        user_id = update.effective_user.id
        username = update.effective_user.username

        if not self._is_allowed(user_id):
            await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return

        session = self._get_session(user_id, username)

        welcome = (
            "Welcome to the Universal Agent Platform!\n\n"
            "I can help you interact with AI agents for various tasks.\n\n"
            "Commands:\n"
            "/agents - List available agents\n"
            "/use <agent> - Select an agent for conversation\n"
            "/run <agent> <prompt> - Execute an agent\n"
            "/workflow <mode> <agents...> - Create multi-agent workflow\n"
            "/tools - List available tools\n"
            "/clear - Clear conversation history\n"
            "/help - Show this help\n\n"
            "Just send me a message to chat with your selected agent!"
        )

        await update.message.reply_text(welcome)

    async def _handle_help(self, update, context) -> None:
        """Handle /help command."""
        await self._handle_start(update, context)

    async def _handle_agents(self, update, context) -> None:
        """Handle /agents command."""
        user_id = update.effective_user.id

        if not self._is_allowed(user_id):
            return

        agents = self.agent_registry.list_agents()

        if not agents:
            await update.message.reply_text("No agents available.")
            return

        lines = ["Available Agents:\n"]
        for agent in agents:
            lines.append(f"*{agent.name}* (`{agent.id}`)")
            if agent.config.description:
                lines.append(f"  {agent.config.description}")
            lines.append(f"  Model: {agent.config.model}")
            lines.append(f"  Tools: {', '.join(agent.config.tools) or 'none'}")
            lines.append("")

        await self._send_message(update.effective_chat.id, "\n".join(lines))

    async def _handle_use(self, update, context) -> None:
        """Handle /use command to select an agent."""
        user_id = update.effective_user.id

        if not self._is_allowed(user_id):
            return

        if not context.args:
            await update.message.reply_text("Usage: /use <agent_id>")
            return

        agent_id = context.args[0]
        agent = self.agent_registry.get_agent(agent_id)

        if not agent:
            await update.message.reply_text(f"Agent '{agent_id}' not found. Use /agents to list available agents.")
            return

        session = self._get_session(user_id)
        session.current_agent = agent_id
        session.conversation_history = []

        await update.message.reply_text(
            f"Now using agent *{agent.name}*.\n\n"
            f"Send me a message to start chatting, or use /run to execute a specific task.",
            parse_mode="Markdown"
        )

    async def _handle_run(self, update, context) -> None:
        """Handle /run command to execute an agent."""
        user_id = update.effective_user.id

        if not self._is_allowed(user_id):
            return

        if not context.args:
            await update.message.reply_text("Usage: /run <agent_id> <prompt>")
            return

        agent_id = context.args[0]
        prompt = " ".join(context.args[1:])

        if not prompt:
            await update.message.reply_text("Please provide a prompt. Usage: /run <agent_id> <prompt>")
            return

        agent = self.agent_registry.get_agent(agent_id)
        if not agent:
            await update.message.reply_text(f"Agent '{agent_id}' not found.")
            return

        # Execute agent
        await update.message.reply_text(f"Executing {agent.name}...")

        try:
            execution = await self.agent_registry.execute(agent_id, prompt)

            if execution.error:
                await update.message.reply_text(f"Error: {execution.error}")
            else:
                session = self._get_session(user_id)
                session.add_message("user", prompt)
                session.add_message("assistant", execution.response or "")
                await self._send_message(update.effective_chat.id, execution.response or "No response")

        except Exception as e:
            await update.message.reply_text(f"Execution failed: {str(e)}")

    async def _handle_workflow(self, update, context) -> None:
        """Handle /workflow command to create and run a multi-agent workflow."""
        user_id = update.effective_user.id

        if not self._is_allowed(user_id):
            return

        if not self.workflow_registry:
            await update.message.reply_text("Workflow orchestration is not enabled.")
            return

        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "Usage: /workflow <mode> <agent1> [agent2] ... <prompt>\n"
                "Modes: sequential, parallel\n"
                "Example: /workflow sequential researcher summarizer Summarize the latest AI news"
            )
            return

        mode = context.args[0].lower()
        prompt_parts = []
        agent_ids = []

        # Parse args - find where agent IDs end and prompt begins
        # Simple approach: last arg starting with non-letter is start of prompt
        for i, arg in enumerate(context.args[1:], 1):
            if arg.startswith("-") or " " in arg:
                prompt_parts = context.args[i+1:]
                break
            agent_ids.append(arg)
        else:
            # All remaining args are agent IDs, need a prompt
            await update.message.reply_text("Please provide a prompt after the agent IDs.")
            return

        prompt = " ".join(prompt_parts) if prompt_parts else " ".join(context.args[-1:])

        if not agent_ids:
            await update.message.reply_text("Please specify at least one agent.")
            return

        # Create workflow config
        from llm_router.orchestrator import WorkflowConfig, WorkflowMode

        mode_enum = WorkflowMode.SEQUENTIAL if mode == "sequential" else WorkflowMode.PARALLEL

        nodes = [{"id": f"node_{i}", "agent_id": aid} for i, aid in enumerate(agent_ids)]

        config = WorkflowConfig(
            name=f"Telegram Workflow {datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            mode=mode_enum,
            nodes=nodes,
        )

        try:
            workflow = self.workflow_registry.create_workflow(config)
            await update.message.reply_text(f"Created {mode} workflow with {len(agent_ids)} agents. Executing...")

            execution = await self.workflow_registry.execute(workflow.id, prompt)

            # Send results
            for node_id, result in execution.results.items():
                node = execution.nodes.get(node_id)
                agent_name = node.agent_id if node else node_id
                await self._send_message(
                    update.effective_chat.id,
                    f"*{agent_name}:*\n{result}",
                )

            if execution.errors:
                await update.message.reply_text(f"Errors: {', '.join(execution.errors)}")

        except Exception as e:
            await update.message.reply_text(f"Workflow failed: {str(e)}")

    async def _handle_status(self, update, context) -> None:
        """Handle /status command."""
        user_id = update.effective_user.id

        if not self._is_allowed(user_id):
            return

        if context.args:
            # Get specific execution status
            execution_id = context.args[0]
            # Would need to track executions by user - simplified for now
            await update.message.reply_text(f"Execution status tracking not yet implemented.")
        else:
            # Show general status
            agents = self.agent_registry.list_agents()
            session = self._get_session(user_id)

            status_text = (
                f"Status:\n"
                f"- Total agents: {len(agents)}\n"
                f"- Current agent: {session.current_agent or 'None'}\n"
                f"- Conversation length: {len(session.conversation_history)}\n"
            )

            await update.message.reply_text(status_text)

    async def _handle_cancel(self, update, context) -> None:
        """Handle /cancel command."""
        user_id = update.effective_user.id

        if not self._is_allowed(user_id):
            return

        if not context.args:
            await update.message.reply_text("Usage: /cancel <execution_id>")
            return

        execution_id = context.args[0]

        if execution_id in self._running_executions:
            self._running_executions[execution_id].cancel()
            await update.message.reply_text(f"Cancelled execution {execution_id}")
        else:
            await update.message.reply_text(f"Execution {execution_id} not found or already completed.")

    async def _handle_tools(self, update, context) -> None:
        """Handle /tools command."""
        user_id = update.effective_user.id

        if not self._is_allowed(user_id):
            return

        from llm_router.tools import get_tool_registry
        registry = get_tool_registry()
        tools = registry.list_tools()

        if not tools:
            await update.message.reply_text("No tools available.")
            return

        lines = ["Available Tools:\n"]
        for tool in tools:
            dangerous = " [!]" if tool.dangerous else ""
            lines.append(f"*{tool.name}*{dangerous}")
            lines.append(f"  {tool.description}")
            lines.append("")

        await self._send_message(update.effective_chat.id, "\n".join(lines))

    async def _handle_clear(self, update, context) -> None:
        """Handle /clear command."""
        user_id = update.effective_user.id

        if not self._is_allowed(user_id):
            return

        session = self._get_session(user_id)
        session.conversation_history = []

        await update.message.reply_text("Conversation history cleared.")

    async def _handle_message(self, update, context) -> None:
        """Handle regular text messages."""
        user_id = update.effective_user.id
        username = update.effective_user.username

        if not self._is_allowed(user_id):
            return

        session = self._get_session(user_id, username)
        message = update.message.text

        # Check if user has selected an agent
        if not session.current_agent:
            await update.message.reply_text(
                "Please select an agent first using /use <agent_id>\n"
                "Use /agents to see available agents."
            )
            return

        agent = self.agent_registry.get_agent(session.current_agent)
        if not agent:
            await update.message.reply_text(
                f"Agent '{session.current_agent}' not found. Please select a new agent."
            )
            session.current_agent = None
            return

        # Build context from conversation history
        session.add_message("user", message)

        try:
            # Execute with conversation context
            execution = await self.agent_registry.execute(
                session.current_agent,
                message,
                system_override=agent.config.system_prompt + "\n\nConversation context:\n" + session.get_context_for_prompt() if session.conversation_history else None
            )

            if execution.error:
                await update.message.reply_text(f"Error: {execution.error}")
            else:
                session.add_message("assistant", execution.response or "")
                await self._send_message(update.effective_chat.id, execution.response or "No response")

        except Exception as e:
            await update.message.reply_text(f"Failed to execute: {str(e)}")

    async def _handle_photo(self, update, context) -> None:
        """Handle photo messages for vision-capable agents."""
        user_id = update.effective_user.id

        if not self._is_allowed(user_id):
            return

        session = self._get_session(user_id)

        if not session.current_agent:
            await update.message.reply_text("Please select an agent first using /use <agent_id>")
            return

        # Get the photo
        photo = update.message.photo[-1]  # Get highest resolution
        caption = update.message.caption or "What's in this image?"

        # For now, just acknowledge - would need vision-capable model integration
        await update.message.reply_text(
            "Photo received. Vision capabilities require a vision-capable model. "
            "Your agent's current model may not support images."
        )


def create_telegram_bot(
    token: str,
    agent_registry: Any,
    workflow_registry: Any | None = None,
    allowed_users: list[int] | None = None,
    admin_users: list[int] | None = None,
) -> TelegramBot:
    """
    Create a Telegram bot instance.

    Args:
        token: Telegram bot token
        agent_registry: AgentRegistry instance
        workflow_registry: Optional WorkflowRegistry instance
        allowed_users: List of allowed user IDs (empty = all users)
        admin_users: List of admin user IDs

    Returns:
        Configured TelegramBot instance
    """
    config = TelegramConfig(
        token=token,
        allowed_users=allowed_users or [],
        admin_users=admin_users or [],
    )
    return TelegramBot(config, agent_registry, workflow_registry)
