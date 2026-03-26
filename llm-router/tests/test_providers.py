"""Tests for provider implementations."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from llm_router.providers.base import BaseProvider
from llm_router.providers.openai import OpenAIProvider
from llm_router.providers.anthropic import AnthropicProvider
from llm_router.providers.openai_compatible import OpenAICompatibleProvider
from llm_router.models import ChatCompletionResponse, ChatCompletionChoice, ChatMessage


class ConcreteProvider(BaseProvider):
    """Concrete implementation for testing abstract base."""

    async def chat(self, messages, model, **kwargs):
        from llm_router.models import ChatCompletionResponse, ChatCompletionChoice, ChatMessage
        return ChatCompletionResponse(
            model=model,
            choices=[ChatCompletionChoice(message=ChatMessage(role="assistant", content="test"))]
        )

    async def stream_chat(self, messages, model, **kwargs):
        from llm_router.models import ChatCompletionChunk
        yield ChatCompletionChunk(model=model, choices=[{"delta": {"content": "test"}}])


class TestBaseProvider:
    """Tests for BaseProvider abstract class."""

    def test_supports_model_with_no_models_configured(self):
        """Should return True for any model when no models specified."""
        provider = ConcreteProvider(api_key="test")
        assert provider.supports_model("any-model") is True

    def test_supports_model_with_models_configured(self):
        """Should return True only for configured models."""
        provider = ConcreteProvider(api_key="test", models=["gpt-4", "gpt-3.5-turbo"])
        assert provider.supports_model("gpt-4") is True
        assert provider.supports_model("unknown-model") is False

    async def test_is_available_with_api_key(self):
        """Should be available when API key is set."""
        provider = ConcreteProvider(api_key="test-key")
        assert await provider.is_available() is True

    async def test_is_available_without_api_key(self):
        """Should not be available when API key is missing."""
        provider = ConcreteProvider(api_key=None)
        assert await provider.is_available() is False

    def test_get_models(self):
        """Should return configured models."""
        provider = ConcreteProvider(api_key="test", models=["model1", "model2"])
        assert provider.get_models() == ["model1", "model2"]


class TestOpenAIProvider:
    """Tests for OpenAI provider."""

    def test_initialization(self):
        """Should initialize with API key."""
        provider = OpenAIProvider(api_key="test-key")
        assert provider.api_key == "test-key"

    @pytest.mark.asyncio
    async def test_chat_creates_response(self):
        """Should create valid response."""
        provider = OpenAIProvider(api_key="test-key")

        with patch.object(provider, "_get_client") as mock_client:
            mock_response = MagicMock()
            mock_response.id = "test-id"
            mock_response.model = "gpt-4"
            mock_response.created = 1234567890
            mock_response.choices = [
                MagicMock(
                    index=0,
                    message=MagicMock(role="assistant", content="Hello!"),
                    finish_reason="stop",
                )
            ]
            mock_response.usage = MagicMock(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            )

            mock_async_client = AsyncMock()
            mock_async_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_async_client

            response = await provider.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model="gpt-4",
            )

            assert isinstance(response, ChatCompletionResponse)
            assert response.model == "gpt-4"
            assert response.choices[0].message.content == "Hello!"


class TestAnthropicProvider:
    """Tests for Anthropic provider."""

    def test_initialization(self):
        """Should initialize with API key."""
        provider = AnthropicProvider(api_key="test-key")
        assert provider.api_key == "test-key"

    def test_convert_messages(self):
        """Should convert OpenAI format to Anthropic format."""
        provider = AnthropicProvider(api_key="test-key")

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "How are you?"},
        ]

        system, converted = provider._convert_messages(messages)

        assert system == "You are helpful."
        assert len(converted) == 3
        assert converted[0]["role"] == "user"
        assert converted[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_chat_creates_response(self):
        """Should create valid response."""
        provider = AnthropicProvider(api_key="test-key")

        with patch.object(provider, "_get_client") as mock_client:
            mock_content = MagicMock()
            mock_content.text = "Hello from Claude!"

            mock_response = MagicMock()
            mock_response.model = "claude-3-opus"
            mock_response.content = [mock_content]
            mock_response.stop_reason = "end_turn"
            mock_response.usage = MagicMock(
                input_tokens=10,
                output_tokens=5,
            )

            mock_async_client = AsyncMock()
            mock_async_client.messages.create = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_async_client

            response = await provider.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-3-opus",
            )

            assert isinstance(response, ChatCompletionResponse)
            assert "Claude" in response.choices[0].message.content


class TestOpenAICompatibleProvider:
    """Tests for OpenAI-compatible provider."""

    def test_initialization_requires_base_url(self):
        """Should require base_url."""
        with pytest.raises(ValueError):
            OpenAICompatibleProvider(api_key="test-key")

    def test_initialization_with_base_url(self):
        """Should initialize with base_url."""
        provider = OpenAICompatibleProvider(
            api_key="test-key",
            base_url="https://api.example.com/v1"
        )
        assert provider.base_url == "https://api.example.com/v1"

    def test_get_headers(self):
        """Should generate correct headers."""
        provider = OpenAICompatibleProvider(
            api_key="test-key",
            base_url="https://api.example.com/v1"
        )
        headers = provider._get_headers()

        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json"

    def test_get_headers_with_extra(self):
        """Should include extra headers."""
        provider = OpenAICompatibleProvider(
            api_key="test-key",
            base_url="https://api.example.com/v1",
            headers={"X-Custom": "value"}
        )
        headers = provider._get_headers()

        assert headers["X-Custom"] == "value"

    @pytest.mark.asyncio
    async def test_chat_makes_http_request(self):
        """Should make HTTP POST request."""
        provider = OpenAICompatibleProvider(
            api_key="test-key",
            base_url="https://api.example.com/v1"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "test-id",
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Response"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

            response = await provider.chat(
                messages=[{"role": "user", "content": "Hi"}],
                model="test-model",
            )

            assert isinstance(response, ChatCompletionResponse)
            assert response.choices[0].message.content == "Response"
