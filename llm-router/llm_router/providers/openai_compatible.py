"""Generic OpenAI-compatible provider implementation."""

import time
import uuid
from typing import Any, AsyncGenerator
import httpx
from llm_router.providers.base import BaseProvider
from llm_router.models import (
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatMessage,
    Usage,
)


class OpenAICompatibleProvider(BaseProvider):
    """
    Generic provider for OpenAI-compatible APIs.
    Used for OpenRouter, zai coding, and other compatible services.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs
    ):
        super().__init__(api_key=api_key, base_url=base_url, **kwargs)
        if not self.base_url:
            raise ValueError("base_url is required for OpenAICompatibleProvider")

    def _get_headers(self) -> dict[str, str]:
        """Get request headers."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # Add any extra headers from config
        if "headers" in self.extra_config:
            headers.update(self.extra_config["headers"])
        return headers

    async def chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs
    ) -> ChatCompletionResponse:
        """Send a chat completion request."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        # Build request body
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        # Add optional parameters
        for key in ["temperature", "top_p", "max_tokens", "stop",
                    "presence_penalty", "frequency_penalty", "user"]:
            if key in kwargs and kwargs[key] is not None:
                body[key] = kwargs[key]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=body,
                headers=self._get_headers(),
                timeout=self.extra_config.get("timeout", 60),
            )
            response.raise_for_status()
            data = response.json()

        # Parse response
        choices = []
        for choice in data.get("choices", []):
            msg = choice.get("message", {})
            choices.append(ChatCompletionChoice(
                index=choice.get("index", 0),
                message=ChatMessage(
                    role=msg.get("role", "assistant"),
                    content=msg.get("content", ""),
                ),
                finish_reason=choice.get("finish_reason"),
            ))

        usage_data = data.get("usage", {})

        return ChatCompletionResponse(
            id=data.get("id", f"chatcmpl-{uuid.uuid4().hex[:8]}"),
            object=data.get("object", "chat.completion"),
            created=data.get("created", int(time.time())),
            model=data.get("model", model),
            choices=choices,
            usage=Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
        )

    async def stream_chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Stream chat completion responses."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        # Build request body
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        # Add optional parameters
        for key in ["temperature", "top_p", "max_tokens", "stop",
                    "presence_penalty", "frequency_penalty", "user"]:
            if key in kwargs and kwargs[key] is not None:
                body[key] = kwargs[key]

        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        created = int(time.time())

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                url,
                json=body,
                headers=self._get_headers(),
                timeout=self.extra_config.get("timeout", 60),
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or line == "data: [DONE]":
                        continue

                    if line.startswith("data: "):
                        line = line[6:]  # Remove "data: " prefix

                    if not line:
                        continue

                    try:
                        import json
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    choices = []
                    for choice in data.get("choices", []):
                        delta = choice.get("delta", {})
                        choices.append({
                            "index": choice.get("index", 0),
                            "delta": delta,
                            "finish_reason": choice.get("finish_reason"),
                        })

                    yield ChatCompletionChunk(
                        id=data.get("id", chunk_id),
                        created=data.get("created", created),
                        model=data.get("model", model),
                        choices=choices,
                    )
