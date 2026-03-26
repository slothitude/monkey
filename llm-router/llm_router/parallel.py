"""Parallel execution utilities for multi-agent workflows."""

import asyncio
from typing import Any, Callable, TypeVar
from dataclasses import dataclass, field
from llm_router import LLMRouter
from llm_router.models import ChatCompletionResponse

T = TypeVar("T")


@dataclass
class AgentResult:
    """Result from a single agent execution."""
    agent_id: str
    model: str
    response: ChatCompletionResponse | None = None
    error: Exception | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.error is None and self.response is not None

    @property
    def content(self) -> str | None:
        if self.response and self.response.choices:
            return self.response.choices[0].message.content
        return None


@dataclass
class ParallelConfig:
    """Configuration for parallel agent execution."""
    max_concurrent: int = 10  # Max concurrent requests
    fail_fast: bool = False  # Stop on first error
    return_errors: bool = True  # Include errors in results


class ParallelExecutor:
    """
    Execute multiple agent requests in parallel across providers.

    Example:
        executor = ParallelExecutor(router)

        # Run same prompt across multiple models
        results = await executor.broadcast(
            prompt="What is 2+2?",
            models=["gpt-4", "claude-3-opus", "gpt-3.5-turbo"]
        )

        # Run different prompts on different models
        results = await executor.map([
            {"agent_id": "agent1", "model": "gpt-4", "messages": [...]},
            {"agent_id": "agent2", "model": "claude-3-opus", "messages": [...]},
        ])
    """

    def __init__(self, router: LLMRouter, config: ParallelConfig | None = None):
        self.router = router
        self.config = config or ParallelConfig()

    async def broadcast(
        self,
        prompt: str,
        models: list[str],
        system_prompt: str | None = None,
        **kwargs
    ) -> list[AgentResult]:
        """
        Send the same prompt to multiple models in parallel.

        Args:
            prompt: The user message to send
            models: List of model identifiers to use
            system_prompt: Optional system message
            **kwargs: Additional parameters for all requests

        Returns:
            List of AgentResult objects, one per model
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        tasks = [
            {"agent_id": model, "model": model, "messages": messages}
            for model in models
        ]

        return await self.map(tasks, **kwargs)

    async def map(
        self,
        tasks: list[dict],
        **kwargs
    ) -> list[AgentResult]:
        """
        Execute multiple different agent tasks in parallel.

        Args:
            tasks: List of task dicts with keys:
                - agent_id: Unique identifier for this agent
                - model: Model to use
                - messages: Chat messages
                - metadata: Optional extra data
            **kwargs: Additional parameters for all requests

        Returns:
            List of AgentResult objects
        """
        semaphore = asyncio.Semaphore(self.config.max_concurrent)

        async def run_task(task: dict) -> AgentResult:
            async with semaphore:
                try:
                    response = await self.router.chat(
                        messages=task["messages"],
                        model=task["model"],
                        **kwargs
                    )
                    return AgentResult(
                        agent_id=task["agent_id"],
                        model=task["model"],
                        response=response,
                        metadata=task.get("metadata", {}),
                    )
                except Exception as e:
                    if self.config.fail_fast:
                        raise
                    return AgentResult(
                        agent_id=task["agent_id"],
                        model=task["model"],
                        error=e,
                        metadata=task.get("metadata", {}),
                    )

        results = await asyncio.gather(*[run_task(t) for t in tasks])
        return list(results)

    async def race(
        self,
        prompt: str,
        models: list[str],
        system_prompt: str | None = None,
        **kwargs
    ) -> AgentResult:
        """
        Race multiple models - return first successful response.

        Useful for getting the fastest response when model speed varies.

        Args:
            prompt: The user message to send
            models: List of model identifiers to race
            system_prompt: Optional system message
            **kwargs: Additional parameters

        Returns:
            First AgentResult to complete successfully
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        async def try_model(model: str) -> AgentResult:
            response = await self.router.chat(
                messages=messages,
                model=model,
                **kwargs
            )
            return AgentResult(
                agent_id=model,
                model=model,
                response=response,
            )

        # Create tasks for all models
        tasks = [asyncio.create_task(try_model(m)) for m in models]

        # Return first successful result
        for future in asyncio.as_completed(tasks):
            try:
                result = await future
                if result.success:
                    # Cancel remaining tasks
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    return result
            except Exception:
                continue

        # All failed
        raise Exception("All models failed in race")


async def parallel_map(
    router: LLMRouter,
    tasks: list[dict],
    max_concurrent: int = 10,
    **kwargs
) -> list[AgentResult]:
    """
    Quick helper for parallel execution without creating executor instance.

    Args:
        router: LLMRouter instance
        tasks: List of task dicts (see ParallelExecutor.map)
        max_concurrent: Max concurrent requests
        **kwargs: Additional parameters

    Returns:
        List of AgentResult objects
    """
    executor = ParallelExecutor(
        router,
        ParallelConfig(max_concurrent=max_concurrent)
    )
    return await executor.map(tasks, **kwargs)
