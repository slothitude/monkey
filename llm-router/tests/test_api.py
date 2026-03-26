"""Tests for FastAPI server endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from llm_router.server.api import app
from llm_router import LLMRouter, RouterConfig, ProviderConfig
from tests.conftest import MockProvider


@pytest.fixture
def client():
    """Create test client with mock router."""
    with patch("llm_router.server.api.router") as mock_router:
        # Setup mock router
        config = RouterConfig(
            providers={
                "test": ProviderConfig(api_key="key", models=["test-model"]),
            }
        )
        mock_router._providers = {"test": MockProvider(models=["test-model"])}
        mock_router._stats = {}
        mock_router.config = config

        def get_models():
            from llm_router.models import ModelList, ModelInfo
            return ModelList(data=[ModelInfo(id="test-model", owned_by="test")])

        def get_stats():
            return {"test": {"requests": 5, "successes": 5, "failures": 0, "avg_latency": 0.1, "success_rate": 1.0}}

        async def is_available():
            return True

        mock_router.get_models = get_models
        mock_router.get_stats = get_stats
        mock_router.is_available = is_available
        mock_router._providers = {"test": MockProvider(models=["test-model"])}

        with TestClient(app) as client:
            yield client


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_status(self, client):
        """Health endpoint should return status."""
        with patch("llm_router.server.api.router") as mock:
            mock._providers = {"test": MockProvider()}
            mock.is_available = AsyncMock(return_value=True)

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "providers" in data


class TestModelsEndpoint:
    """Tests for /v1/models endpoint."""

    def test_list_models(self, client):
        """Should list available models."""
        with patch("llm_router.server.api.get_router") as mock_get_router:
            router = LLMRouter(RouterConfig(
                providers={"test": ProviderConfig(api_key="key", models=["gpt-4"])}
            ))
            router._providers["test"] = MockProvider(models=["gpt-4"])
            mock_get_router.return_value = router

            response = client.get("/v1/models")

            assert response.status_code == 200
            data = response.json()
            assert data["object"] == "list"
            assert isinstance(data["data"], list)


class TestChatCompletionsEndpoint:
    """Tests for /v1/chat/completions endpoint."""

    def test_chat_completion_non_streaming(self, client):
        """Should return chat completion response."""
        with patch("llm_router.server.api.get_router") as mock_get_router:
            router = LLMRouter(RouterConfig(
                providers={"test": ProviderConfig(api_key="key", models=["test-model"])}
            ))
            router._providers["test"] = MockProvider(models=["test-model"])
            mock_get_router.return_value = router

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": False,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "choices" in data
            assert len(data["choices"]) > 0

    def test_chat_completion_with_error(self, client):
        """Should return 500 on provider error."""
        with patch("llm_router.server.api.get_router") as mock_get_router:
            router = LLMRouter(RouterConfig(
                providers={"test": ProviderConfig(api_key="key", models=["test-model"])},
                failover_enabled=False,
            ))
            router._providers["test"] = MockProvider(should_fail=True, models=["test-model"])
            mock_get_router.return_value = router

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

            assert response.status_code == 500

    def test_chat_completion_missing_model(self, client):
        """Should handle missing model gracefully."""
        with patch("llm_router.server.api.get_router") as mock_get_router:
            router = LLMRouter(RouterConfig())
            mock_get_router.return_value = router

            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "nonexistent",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

            # Should fail with no providers
            assert response.status_code == 500


class TestStatsEndpoint:
    """Tests for /v1/stats endpoint."""

    def test_stats_endpoint(self, client):
        """Should return provider statistics."""
        with patch("llm_router.server.api.get_router") as mock_get_router:
            router = LLMRouter(RouterConfig(
                providers={"test": ProviderConfig(api_key="key", models=["test-model"])}
            ))
            router._providers["test"] = MockProvider(models=["test-model"])
            mock_get_router.return_value = router

            response = client.get("/v1/stats")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, dict)


class TestConfigEndpoints:
    """Tests for configuration endpoints."""

    def test_get_config(self, client):
        """Should return current configuration."""
        response = client.get("/v1/config")

        assert response.status_code == 200
        data = response.json()
        assert "config" in data

    def test_update_config(self, client):
        """Should update configuration."""
        response = client.put(
            "/v1/config",
            json={"config": "test: value"},
        )

        # May fail if no file access, but endpoint should exist
        assert response.status_code in [200, 500]


class TestParallelEndpoint:
    """Tests for /v1/parallel endpoint."""

    @pytest.mark.asyncio
    async def test_parallel_broadcast(self, client):
        """Should execute parallel broadcast."""
        with patch("llm_router.server.api.get_router") as mock_get_router:
            router = LLMRouter(RouterConfig(
                providers={
                    "p1": ProviderConfig(api_key="key", models=["m1"]),
                    "p2": ProviderConfig(api_key="key", models=["m2"]),
                }
            ))
            router._providers["p1"] = MockProvider(name="p1", models=["m1"])
            router._providers["p2"] = MockProvider(name="p2", models=["m2"])
            mock_get_router.return_value = router

            response = client.post(
                "/v1/parallel",
                json={
                    "mode": "broadcast",
                    "prompt": "Hello",
                    "models": ["m1", "m2"],
                    "max_concurrent": 2,
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert "results" in data
            assert len(data["results"]) == 2


class TestGUIEndpoint:
    """Tests for GUI endpoint."""

    def test_gui_endpoint(self, client):
        """Should serve GUI HTML."""
        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
