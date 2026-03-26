"""Main LLM router implementation."""

from typing import Any, AsyncGenerator
import asyncio
import time
from dataclasses import dataclass, field
from llm_router.config import RouterConfig, ProviderConfig, load_config
from llm_router.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChunk,
    ModelInfo,
    ModelList,
)
from llm_router.providers.base import BaseProvider
from llm_router.providers.openai import OpenAIProvider
from llm_router.providers.anthropic import AnthropicProvider
from llm_router.providers.openai_compatible import OpenAICompatibleProvider


@dataclass
class ProviderStats:
    """Statistics for a provider."""
    requests: int = 0
    successes: int = 0
    failures: int = 0
    total_latency: float = 0.0
    last_request_time: float = 0.0

    @property
    def avg_latency(self) -> float:
        return self.total_latency / self.successes if self.successes > 0 else 0.0

    @property
    def success_rate(self) -> float:
        return self.successes / self.requests if self.requests > 0 else 1.0


class LLMRouter:
    """
    Main router class that manages multiple LLM providers.

    Routes requests to appropriate providers based on model name,
    with failover support.
    """

    def __init__(self, config: RouterConfig | None = None):
        """
        Initialize the router.

        Args:
            config: Router configuration. If None, loads from default path.
        """
        self.config = config or load_config()
        self._providers: dict[str, BaseProvider] = {}
        self._model_to_provider: dict[str, str] = {}
        self._stats: dict[str, ProviderStats] = {}
        self._lock = asyncio.Lock()
        self._initialize_providers()

    def _initialize_providers(self) -> None:
        """Initialize provider instances from configuration."""
        for name, provider_config in self.config.providers.items():
            if not provider_config.enabled:
                continue

            provider = self._create_provider(name, provider_config)
            if provider:
                self._providers[name] = provider
                self._stats[name] = ProviderStats()

                # Build model to provider mapping
                for model in provider_config.models:
                    self._model_to_provider[model] = name

    def _create_provider(
        self,
        name: str,
        config: ProviderConfig
    ) -> BaseProvider | None:
        """Create a provider instance based on name and configuration."""
        provider_class: type[BaseProvider]

        if name == "openai":
            provider_class = OpenAIProvider
        elif name == "anthropic":
            provider_class = AnthropicProvider
        elif name in ["openrouter", "zai"]:
            provider_class = OpenAICompatibleProvider
        else:
            # Check if base_url is provided for generic OpenAI-compatible
            if config.base_url:
                provider_class = OpenAICompatibleProvider
            else:
                return None

        try:
            return provider_class(
                api_key=config.api_key,
                base_url=config.base_url,
                models=config.models,
                **config.extra,
            )
        except Exception as e:
            print(f"Warning: Failed to initialize provider '{name}': {e}")
            return None

    def _get_provider_for_model(self, model: str) -> str | None:
        """
        Determine which provider to use for a given model.

        Args:
            model: Model identifier

        Returns:
            Provider name or None if no match found
        """
        # Check exact match first
        if model in self._model_to_provider:
            return self._model_to_provider[model]

        # Check prefix match (e.g., "gpt-4-turbo" matches "gpt-*")
        for pattern, provider in self._model_to_provider.items():
            if pattern.endswith("*"):
                prefix = pattern[:-1]
                if model.startswith(prefix):
                    return provider
            elif model.startswith(pattern):
                return provider

        # Check if provider supports the model directly
        for name, provider in self._providers.items():
            if provider.supports_model(model):
                return name

        # Return default provider
        return self.config.default_provider

    def _get_provider_with_load_balance(
        self,
        model: str,
        strategy: str = "priority"
    ) -> str | None:
        """
        Get provider using load balancing strategy.

        Args:
            model: Model identifier
            strategy: One of "priority", "round_robin", "least_connections", "random"

        Returns:
            Provider name or None
        """
        providers = self._get_failover_providers(model)

        if not providers:
            return None

        if strategy == "priority" or len(providers) == 1:
            return providers[0]

        if strategy == "round_robin":
            # Simple round robin based on request count
            min_requests = float('inf')
            selected = providers[0]
            for p in providers:
                stats = self._stats.get(p, ProviderStats())
                if stats.requests < min_requests:
                    min_requests = stats.requests
                    selected = p
            return selected

        if strategy == "least_connections":
            # Select provider with fewest active requests (best success rate)
            best_rate = -1
            selected = providers[0]
            for p in providers:
                stats = self._stats.get(p, ProviderStats())
                rate = stats.success_rate
                if rate > best_rate:
                    best_rate = rate
                    selected = p
            return selected

        if strategy == "random":
            import random
            return random.choice(providers)

        return providers[0]

    async def _record_stats(
        self,
        provider_name: str,
        success: bool,
        latency: float
    ) -> None:
        """Record request statistics."""
        async with self._lock:
            stats = self._stats.get(provider_name)
            if stats:
                stats.requests += 1
                stats.last_request_time = time.time()
                if success:
                    stats.successes += 1
                    stats.total_latency += latency
                else:
                    stats.failures += 1

    def get_stats(self) -> dict[str, dict]:
        """Get statistics for all providers."""
        return {
            name: {
                "requests": stats.requests,
                "successes": stats.successes,
                "failures": stats.failures,
                "avg_latency": round(stats.avg_latency, 3),
                "success_rate": round(stats.success_rate, 3),
            }
            for name, stats in self._stats.items()
        }

    def _get_failover_providers(self, model: str) -> list[str]:
        """
        Get list of providers to try for failover.

        Args:
            model: Model identifier

        Returns:
            List of provider names in priority order
        """
        primary = self._get_provider_for_model(model)

        # Get all providers sorted by priority
        all_providers = sorted(
            self._providers.keys(),
            key=lambda p: self.config.providers.get(p, ProviderConfig()).priority
        )

        # Put primary provider first
        if primary and primary in all_providers:
            all_providers.remove(primary)
            all_providers.insert(0, primary)

        return all_providers

    async def chat(
        self,
        messages: list[dict],
        model: str,
        load_balance: str | None = None,
        **kwargs
    ) -> ChatCompletionResponse:
        """
        Send a chat completion request with automatic routing and failover.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model identifier
            load_balance: Optional strategy ("priority", "round_robin",
                         "least_connections", "random")
            **kwargs: Additional parameters

        Returns:
            ChatCompletionResponse

        Raises:
            Exception: If all providers fail
        """
        if load_balance:
            primary = self._get_provider_with_load_balance(model, load_balance)
            providers_to_try = [primary] if primary else []
            if primary:
                # Add other providers as failover
                all_providers = self._get_failover_providers(model)
                for p in all_providers:
                    if p != primary and p not in providers_to_try:
                        providers_to_try.append(p)
        else:
            providers_to_try = self._get_failover_providers(model)

        last_error = None

        for provider_name in providers_to_try:
            provider = self._providers.get(provider_name)
            if not provider:
                continue

            start_time = time.time()
            try:
                response = await provider.chat(messages, model, **kwargs)
                latency = time.time() - start_time
                await self._record_stats(provider_name, True, latency)
                return response
            except Exception as e:
                latency = time.time() - start_time
                await self._record_stats(provider_name, False, latency)
                last_error = e
                if not self.config.failover_enabled:
                    raise
                print(f"Provider '{provider_name}' failed: {e}. Trying next...")

        raise Exception(f"All providers failed. Last error: {last_error}")

    async def stream(
        self,
        messages: list[dict],
        model: str,
        **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Stream chat completion responses with automatic routing.

        Note: Failover is not supported during streaming.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model identifier
            **kwargs: Additional parameters

        Yields:
            ChatCompletionChunk objects
        """
        provider_name = self._get_provider_for_model(model)

        if not provider_name or provider_name not in self._providers:
            raise Exception(f"No provider available for model: {model}")

        provider = self._providers[provider_name]

        async for chunk in provider.stream_chat(messages, model, **kwargs):
            yield chunk

    def get_models(self) -> ModelList:
        """
        Get list of all available models across providers.

        Returns:
            ModelList containing all available models
        """
        models = []

        for provider_name, provider in self._providers.items():
            for model_id in provider.get_models():
                models.append(ModelInfo(
                    id=model_id,
                    owned_by=provider_name,
                ))

        return ModelList(data=models)

    async def is_available(self) -> bool:
        """Check if any provider is available."""
        for provider in self._providers.values():
            if await provider.is_available():
                return True
        return False

    @classmethod
    def from_config(cls, config_path: str) -> "LLMRouter":
        """
        Create a router from a configuration file.

        Args:
            config_path: Path to YAML configuration file

        Returns:
            Configured LLMRouter instance
        """
        config = load_config(config_path)
        return cls(config)
