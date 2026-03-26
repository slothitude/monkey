"""Abstract base provider interface."""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator
from llm_router.models import ChatCompletionResponse, ChatCompletionChunk


class BaseProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        models: list[str] | None = None,
        **kwargs
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.models = models or []
        self.extra_config = kwargs

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs
    ) -> ChatCompletionResponse:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model identifier to use
            **kwargs: Additional provider-specific parameters

        Returns:
            ChatCompletionResponse in OpenAI-compatible format
        """
        pass

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Stream chat completion responses.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model identifier to use
            **kwargs: Additional provider-specific parameters

        Yields:
            ChatCompletionChunk objects
        """
        pass

    async def is_available(self) -> bool:
        """
        Check if the provider is available and configured.

        Returns:
            True if provider can be used, False otherwise
        """
        return self.api_key is not None

    def get_models(self) -> list[str]:
        """
        Get list of supported models.

        Returns:
            List of model identifiers
        """
        return self.models

    def supports_model(self, model: str) -> bool:
        """
        Check if this provider supports a given model.

        Args:
            model: Model identifier to check

        Returns:
            True if model is supported
        """
        if not self.models:
            return True  # If no models specified, assume all are supported
        return any(
            model == m or model.startswith(m.replace("*", ""))
            for m in self.models
        )
