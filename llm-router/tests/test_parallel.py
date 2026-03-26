"""Tests for parallel execution functionality."""

import pytest
import asyncio
from llm_router import LLMRouter, RouterConfig, ProviderConfig
from llm_router.parallel import ParallelExecutor, ParallelConfig, parallel_map
from tests.conftest import MockProvider


class TestParallelExecutor:
    """Tests for ParallelExecutor class."""

    @pytest.fixture
    def router_for_parallel(self):
        """Create router with multiple mock providers for parallel testing."""
        config = RouterConfig(
            providers={
                "provider1": ProviderConfig(api_key="key", models=["model1"], priority=1),
                "provider2": ProviderConfig(api_key="key", models=["model2"], priority=2),
                "provider3": ProviderConfig(api_key="key", models=["model3"], priority=3),
            }
        )
        router = LLMRouter(config)
        router._providers["provider1"] = MockProvider(name="provider1", models=["model1"])
        router._providers["provider2"] = MockProvider(name="provider2", models=["model2"])
        router._providers["provider3"] = MockProvider(name="provider3", models=["model3"])
        return router

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_models(self, router_for_parallel):
        """Broadcast should send prompt to all specified models."""
        executor = ParallelExecutor(router_for_parallel)

        results = await executor.broadcast(
            prompt="Hello",
            models=["model1", "model2", "model3"],
            max_tokens=50,
        )

        assert len(results) == 3
        assert all(r.success for r in results)
        # Each result should come from different provider
        contents = [r.content for r in results]
        assert any("provider1" in c for c in contents)
        assert any("provider2" in c for c in contents)
        assert any("provider3" in c for c in contents)

    @pytest.mark.asyncio
    async def test_broadcast_with_system_prompt(self, router_for_parallel):
        """Broadcast should include system prompt."""
        executor = ParallelExecutor(router_for_parallel)

        results = await executor.broadcast(
            prompt="Hello",
            models=["model1"],
            system_prompt="You are a test assistant.",
        )

        provider = router_for_parallel._providers["provider1"]
        # Check system prompt was included
        messages = provider.last_messages
        assert any(m["role"] == "system" for m in messages)

    @pytest.mark.asyncio
    async def test_map_executes_different_tasks(self, router_for_parallel):
        """Map should execute different tasks in parallel."""
        executor = ParallelExecutor(router_for_parallel)

        tasks = [
            {"agent_id": "agent1", "model": "model1", "messages": [{"role": "user", "content": "Task 1"}]},
            {"agent_id": "agent2", "model": "model2", "messages": [{"role": "user", "content": "Task 2"}]},
            {"agent_id": "agent3", "model": "model3", "messages": [{"role": "user", "content": "Task 3"}]},
        ]

        results = await executor.map(tasks)

        assert len(results) == 3
        assert all(r.success for r in results)
        # Check agent IDs are preserved
        agent_ids = {r.agent_id for r in results}
        assert agent_ids == {"agent1", "agent2", "agent3"}

    @pytest.mark.asyncio
    async def test_map_respects_max_concurrent(self, router_for_parallel):
        """Map should limit concurrent requests."""
        # Add delay to providers to track concurrency
        for p in router_for_parallel._providers.values():
            p.response_delay = 0.1

        executor = ParallelExecutor(
            router_for_parallel,
            ParallelConfig(max_concurrent=2)
        )

        tasks = [
            {"agent_id": f"agent{i}", "model": f"model{(i % 3) + 1}",
             "messages": [{"role": "user", "content": f"Task {i}"}]}
            for i in range(6)
        ]

        import time
        start = time.time()
        results = await executor.map(tasks)
        elapsed = time.time() - start

        assert len(results) == 6
        # With 6 tasks, max 2 concurrent, and 0.1s delay each
        # Should take at least 0.3s (3 batches)
        assert elapsed >= 0.25

    @pytest.mark.asyncio
    async def test_map_handles_errors(self, router_for_parallel):
        """Map should handle errors gracefully - failover kicks in."""
        # Make all providers fail to test error handling
        for p in router_for_parallel._providers.values():
            p.should_fail = True

        executor = ParallelExecutor(
            router_for_parallel,
            ParallelConfig(return_errors=True)
        )

        tasks = [
            {"agent_id": "agent1", "model": "model1", "messages": [{"role": "user", "content": "OK"}]},
        ]

        results = await executor.map(tasks)

        assert len(results) == 1
        # Should have error since all providers fail
        assert results[0].error is not None
        assert results[0].success is False

    @pytest.mark.asyncio
    async def test_map_fail_fast_mode(self, router_for_parallel):
        """Fail fast mode should raise on first error when all providers fail."""
        # Make all providers fail to ensure error is raised
        for p in router_for_parallel._providers.values():
            p.should_fail = True

        # Disable failover so error propagates
        router_for_parallel.config.failover_enabled = False

        executor = ParallelExecutor(
            router_for_parallel,
            ParallelConfig(fail_fast=True)
        )

        tasks = [
            {"agent_id": "agent1", "model": "model1", "messages": [{"role": "user", "content": "Fail"}]},
        ]

        with pytest.raises(Exception):
            await executor.map(tasks)

    @pytest.mark.asyncio
    async def test_race_returns_first_successful(self, router_for_parallel):
        """Race should return first successful response."""
        # Make provider1 slower
        router_for_parallel._providers["provider1"].response_delay = 0.1
        # provider2 should win

        executor = ParallelExecutor(router_for_parallel)

        result = await executor.race(
            prompt="Race test",
            models=["model1", "model2", "model3"],
        )

        assert result.success
        # provider2 should win (no delay)
        assert "provider2" in result.content

    @pytest.mark.asyncio
    async def test_race_all_fail_raises_error(self, router_for_parallel):
        """Race should raise error if all providers fail."""
        for p in router_for_parallel._providers.values():
            p.should_fail = True

        executor = ParallelExecutor(router_for_parallel)

        with pytest.raises(Exception) as exc_info:
            await executor.race(
                prompt="test",
                models=["model1", "model2"],
            )
        assert "failed" in str(exc_info.value).lower()


class TestParallelHelper:
    """Tests for parallel_map helper function."""

    @pytest.fixture
    def router(self):
        config = RouterConfig(
            providers={"test": ProviderConfig(api_key="key", models=["model"])}
        )
        router = LLMRouter(config)
        router._providers["test"] = MockProvider(models=["model"])
        return router

    @pytest.mark.asyncio
    async def test_parallel_map_helper(self, router):
        """parallel_map should work without creating executor."""
        results = await parallel_map(
            router,
            tasks=[
                {"agent_id": "a1", "model": "model", "messages": [{"role": "user", "content": "hi"}]},
                {"agent_id": "a2", "model": "model", "messages": [{"role": "user", "content": "hello"}]},
            ],
            max_concurrent=5,
        )

        assert len(results) == 2
        assert all(r.success for r in results)


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_success_property(self):
        """Success should be True when no error and has response."""
        from llm_router.parallel import AgentResult
        from llm_router.models import ChatCompletionResponse

        # Successful result
        result = AgentResult(
            agent_id="test",
            model="model",
            response=ChatCompletionResponse(
                model="model",
                choices=[],
            ),
        )
        assert result.success is True

        # Failed result
        result = AgentResult(
            agent_id="test",
            model="model",
            error=Exception("Failed"),
        )
        assert result.success is False

    def test_content_property(self):
        """Content should extract text from response."""
        from llm_router.parallel import AgentResult
        from llm_router.models import ChatCompletionResponse, ChatCompletionChoice, ChatMessage

        result = AgentResult(
            agent_id="test",
            model="model",
            response=ChatCompletionResponse(
                model="model",
                choices=[
                    ChatCompletionChoice(
                        message=ChatMessage(role="assistant", content="Hello world"),
                    )
                ],
            ),
        )
        assert result.content == "Hello world"

        # With no response
        result = AgentResult(agent_id="test", model="model")
        assert result.content is None
