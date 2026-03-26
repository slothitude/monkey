"""Anthropic provider implementation."""

import time
import uuid
from typing import Any, AsyncGenerator
from anthropic import AsyncAnthropic
from llm_router.providers.base import BaseProvider
from llm_router.models import (
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatMessage,
    Usage,
)


class AnthropicProvider(BaseProvider):
    """Provider for Anthropic API (Claude models)."""

    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)
        self._client: AsyncAnthropic | None = None

    def _get_client(self) -> AsyncAnthropic:
        """Get or create the Anthropic client."""
        if self._client is None:
            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    def _convert_messages(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        """
        Convert OpenAI-style messages to Anthropic format.

        Returns:
            Tuple of (system_prompt, converted_messages)
        """
        system = None
        converted = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                system = content
            elif role == "user":
                converted.append({"role": "user", "content": content})
            elif role == "assistant":
                converted.append({"role": "assistant", "content": content})

        return system, converted

    async def chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs
    ) -> ChatCompletionResponse:
        """Send a chat completion request to Anthropic."""
        client = self._get_client()

        system, converted_messages = self._convert_messages(messages)

        # Build request parameters
        params: dict[str, Any] = {
            "model": model,
            "messages": converted_messages,
        }

        if system:
            params["system"] = system

        # Map OpenAI params to Anthropic params
        if "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
            params["max_tokens"] = kwargs["max_tokens"]
        else:
            params["max_tokens"] = 4096  # Default

        if "temperature" in kwargs and kwargs["temperature"] is not None:
            params["temperature"] = kwargs["temperature"]

        if "top_p" in kwargs and kwargs["top_p"] is not None:
            params["top_p"] = kwargs["top_p"]

        if "stop" in kwargs and kwargs["stop"] is not None:
            params["stop_sequences"] = kwargs["stop"]

        response = await client.messages.create(**params)

        # Extract text content
        text_content = ""
        for block in response.content:
            if hasattr(block, "text"):
                text_content += block.text

        # Convert to OpenAI-compatible response format
        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
            object="chat.completion",
            created=int(time.time()),
            model=response.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(
                        role="assistant",
                        content=text_content,
                    ),
                    finish_reason="stop" if response.stop_reason == "end_turn" else response.stop_reason,
                )
            ],
            usage=Usage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            ),
        )

    async def stream_chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Stream chat completion responses from Anthropic."""
        client = self._get_client()

        system, converted_messages = self._convert_messages(messages)

        # Build request parameters
        params: dict[str, Any] = {
            "model": model,
            "messages": converted_messages,
        }

        if system:
            params["system"] = system

        if "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
            params["max_tokens"] = kwargs["max_tokens"]
        else:
            params["max_tokens"] = 4096

        if "temperature" in kwargs and kwargs["temperature"] is not None:
            params["temperature"] = kwargs["temperature"]

        if "top_p" in kwargs and kwargs["top_p"] is not None:
            params["top_p"] = kwargs["top_p"]

        if "stop" in kwargs and kwargs["stop"] is not None:
            params["stop_sequences"] = kwargs["stop"]

        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        created = int(time.time())

        async with client.messages.stream(**params) as stream:
            # Send initial role chunk
            yield ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[{
                    "index": 0,
                    "delta": {"role": "assistant"},
                    "finish_reason": None,
                }],
            )

            async for text in stream.text_stream:
                yield ChatCompletionChunk(
                    id=chunk_id,
                    created=created,
                    model=model,
                    choices=[{
                        "index": 0,
                        "delta": {"content": text},
                        "finish_reason": None,
                    }],
                )

            # Send final chunk
            yield ChatCompletionChunk(
                id=chunk_id,
                created=created,
                model=model,
                choices=[{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }],
            )
