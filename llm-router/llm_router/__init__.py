"""
LLM Router - A unified router for multiple LLM providers.

Provides both an SDK for direct library usage and a FastAPI server
that acts as a drop-in OpenAI-compatible API.

Supports parallel agent execution with load balancing and failover.
"""

from llm_router.router import LLMRouter, ProviderStats
from llm_router.models import (
    ChatMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChunk,
    ModelInfo,
    ModelList,
)
from llm_router.config import load_config, RouterConfig, ProviderConfig
from llm_router.providers.base import BaseProvider
from llm_router.parallel import (
    ParallelExecutor,
    ParallelConfig,
    AgentResult,
    parallel_map,
)

__version__ = "0.1.0"

__all__ = [
    # Core
    "LLMRouter",
    "ChatMessage",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatCompletionChunk",
    "ModelInfo",
    "ModelList",
    # Config
    "load_config",
    "RouterConfig",
    "ProviderConfig",
    # Providers
    "BaseProvider",
    # Parallel execution
    "ParallelExecutor",
    "ParallelConfig",
    "AgentResult",
    "parallel_map",
    # Stats
    "ProviderStats",
]
