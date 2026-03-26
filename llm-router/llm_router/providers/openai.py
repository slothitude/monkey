"""OpenAI provider implementation."""

import time
from typing import Any, AsyncGenerator
from openai import AsyncOpenAI
from llm_router.providers.base import BaseProvider
from llm_router.models import (
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatMessage,
    Usage,
)


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI API."""

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    async def chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs
    ) -> ChatCompletionResponse:
        """Send a chat completion request to OpenAI."""
        client = self._get_client()

        # Build request parameters
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        # Add optional parameters
        for key in ["temperature", "top_p", "max_tokens", "stop",
                    "presence_penalty", "frequency_penalty", "user"]:
            if key in kwargs and kwargs[key] is not None:
                params[key] = kwargs[key]

        response = await client.chat.completions.create(**params)

        # Convert to our response format
        return ChatCompletionResponse(
            id=response.id or f"chatcmpl-{model}",
            object="chat.completion",
            created=response.created or int(time.time()),
            model=response.model or model,
            choices=[
                ChatCompletionChoice(
                    index=choice.index or 0,
                    message=ChatMessage(
                        role=choice.message.role,
                        content=choice.message.content or "",
                    ),
                    finish_reason=choice.finish_reason,
                )
                for choice in response.choices
            ],
            usage=Usage(
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
                total_tokens=response.usage.total_tokens if response.usage else 0,
            ),
        )

    async def stream_chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Stream chat completion responses from OpenAI."""
        client = self._get_client()

        # Build request parameters
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        # Add optional parameters
        for key in ["temperature", "top_p", "max_tokens", "stop",
                    "presence_penalty", "frequency_penalty", "user"]:
            if key in kwargs and kwargs[key] is not None:
                params[key] = kwargs[key]

        stream = await client.chat.completions.create(**params)

        chunk_id = None
        created = int(time.time())

        async for chunk in stream:
            if chunk_id is None:
                chunk_id = chunk.id or f"chatcmpl-{model}"

            # Convert delta to our format
            choices = []
            for choice in chunk.choices:
                delta = {}
                if choice.delta:
                    if choice.delta.role:
                        delta["role"] = choice.delta.role
                    if choice.delta.content:
                        delta["content"] = choice.delta.content
                choices.append({
                    "index": choice.index or 0,
                    "delta": delta,
                    "finish_reason": choice.finish_reason,
                })

            yield ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=chunk.model or model,
                choices=choices,
            )
