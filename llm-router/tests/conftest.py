"""Shared fixtures for LLM router tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from llm_router import LLMRouter, RouterConfig, ProviderConfig
from llm_router.models import (
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatMessage,
    Usage,
)
from llm_router.providers.base import BaseProvider
from typing import AsyncGenerator


class MockProvider(BaseProvider):
    """Mock provider for testing without real API calls."""

    def __init__(
        self,
        name: str = "mock",
        api_key: str = "test-key",
        models: list[str] = None,
        should_fail: bool = False,
        response_delay: float = 0,
        **kwargs
    ):
        super().__init__(api_key=api_key, models=models or ["mock-model"], **kwargs)
        self.name = name
        self.should_fail = should_fail
        self.response_delay = response_delay
        self.call_count = 0
        self.last_messages = None
        self.last_kwargs = None

    async def chat(self, messages: list[dict], model: str, **kwargs) -> ChatCompletionResponse:
        """Mock chat that returns a predictable response."""
        import asyncio
        import time

        self.call_count += 1
        self.last_messages = messages
        self.last_kwargs = kwargs

        if self.response_delay:
            await asyncio.sleep(self.response_delay)

        if self.should_fail:
            raise Exception(f"Mock provider {self.name} failed")

        # Create response based on input
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "test")
        return ChatCompletionResponse(
            id=f"mock-{self.name}-{self.call_count}",
            model=model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(
                        role="assistant",
                        content=f"Response from {self.name}: {user_msg[:50]}",
                    ),
                    finish_reason="stop",
                )
            ],
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )

    async def stream_chat(
        self, messages: list[dict], model: str, **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Mock streaming chat."""
        import asyncio

        self.call_count += 1
        self.last_messages = messages

        if self.should_fail:
            raise Exception(f"Mock provider {self.name} failed")

        content = f"Stream from {self.name}"
        for word in content.split():
            yield ChatCompletionChunk(
                id=f"mock-stream-{self.name}",
                model=model,
                choices=[{
                    "index": 0,
                    "delta": {"content": word + " "},
                    "finish_reason": None,
                }],
            )
            await asyncio.sleep(0.01)

        # Final chunk
        yield ChatCompletionChunk(
            id=f"mock-stream-{self.name}",
            model=model,
            choices=[{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }],
        )


@pytest.fixture
def mock_provider():
    """Create a basic mock provider."""
    return MockProvider(name="test", models=["test-model"])


@pytest.fixture
def failing_provider():
    """Create a mock provider that always fails."""
    return MockProvider(name="failing", should_fail=True)


@pytest.fixture
def router_with_mock():
    """Create a router with a single mock provider."""
    config = RouterConfig(
        providers={
            "mock": ProviderConfig(
                api_key="test-key",
                models=["test-model", "test-*"],
                priority=1,
            )
        },
        default_provider="mock",
        failover_enabled=True,
    )
    router = LLMRouter(config)
    # Replace real provider with mock
    router._providers["mock"] = MockProvider(name="mock", models=["test-model", "test-*"])
    router._stats["mock"] = router._stats.get("mock", type('Stats', (), {'requests': 0, 'successes': 0, 'failures': 0, 'total_latency': 0.0})())
    return router


@pytest.fixture
def router_with_multiple_mocks():
    """Create a router with multiple mock providers for failover testing."""
    from llm_router.router import ProviderStats

    config = RouterConfig(
        providers={
            "primary": ProviderConfig(
                api_key="test-key",
                models=["primary-model"],
                priority=1,
            ),
            "secondary": ProviderConfig(
                api_key="test-key",
                models=["secondary-model"],
                priority=2,
            ),
            "tertiary": ProviderConfig(
                api_key="test-key",
                models=["tertiary-model"],
                priority=3,
            ),
        },
        default_provider="primary",
        failover_enabled=True,
    )
    router = LLMRouter(config)
    router._providers["primary"] = MockProvider(name="primary", models=["primary-model"])
    router._providers["secondary"] = MockProvider(name="secondary", models=["secondary-model"])
    router._providers["tertiary"] = MockProvider(name="tertiary", models=["tertiary-model"])
    # Initialize stats for each provider
    router._stats["primary"] = ProviderStats()
    router._stats["secondary"] = ProviderStats()
    router._stats["tertiary"] = ProviderStats()
    return router


@pytest.fixture
def router_with_failing_primary():
    """Create a router where the primary provider fails."""
    config = RouterConfig(
        providers={
            "failing": ProviderConfig(
                api_key="test-key",
                models=["fail-model"],
                priority=1,
            ),
            "working": ProviderConfig(
                api_key="test-key",
                models=["work-model"],
                priority=2,
            ),
        },
        default_provider="failing",
        failover_enabled=True,
    )
    router = LLMRouter(config)
    router._providers["failing"] = MockProvider(name="failing", should_fail=True, models=["fail-model"])
    router._providers["working"] = MockProvider(name="working", models=["work-model"])
    return router


@pytest.fixture
def sample_messages():
    """Sample chat messages for testing."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, world!"},
    ]


@pytest.fixture
def sample_request():
    """Sample chat completion request."""
    from llm_router.models import ChatCompletionRequest
    return ChatCompletionRequest(
        model="test-model",
        messages=[ChatMessage(role="user", content="Test message")],
        temperature=0.7,
        max_tokens=100,
    )
