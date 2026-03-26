"""Example of parallel agent execution with LLM Router."""

import asyncio
from llm_router import LLMRouter, load_config
from llm_router.parallel import ParallelExecutor, ParallelConfig, parallel_map


async def example_broadcast():
    """
    Broadcast same prompt to multiple models in parallel.
    Useful for comparing responses or getting consensus.
    """
    router = LLMRouter(load_config())
    executor = ParallelExecutor(router)

    print("=== Broadcast: Same prompt to multiple models ===\n")

    results = await executor.broadcast(
        prompt="What is the capital of France? Answer in one word.",
        models=["gpt-4", "gpt-3.5-turbo", "claude-3-opus"],
        system_prompt="You are a helpful assistant. Be concise.",
        max_tokens=50,
    )

    for result in results:
        if result.success:
            print(f"  {result.model}: {result.content}")
        else:
            print(f"  {result.model}: ERROR - {result.error}")


async def example_map():
    """
    Map different agents to different models in parallel.
    Each agent can have different prompts and configurations.
    """
    router = LLMRouter(load_config())
    executor = ParallelExecutor(
        router,
        ParallelConfig(max_concurrent=5, return_errors=True)
    )

    print("\n=== Map: Different agents, different tasks ===\n")

    # Define multiple agent tasks
    tasks = [
        {
            "agent_id": "researcher",
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "List 3 benefits of exercise"}
            ],
            "metadata": {"role": "research"},
        },
        {
            "agent_id": "summarizer",
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Summarize: The quick brown fox jumps over the lazy dog."}
            ],
            "metadata": {"role": "summarize"},
        },
        {
            "agent_id": "coder",
            "model": "claude-3-opus",
            "messages": [
                {"role": "user", "content": "Write a Python function to add two numbers"}
            ],
            "metadata": {"role": "code"},
        },
    ]

    results = await executor.map(tasks, max_tokens=200)

    for result in results:
        print(f"  [{result.agent_id}] ({result.model}):")
        if result.success:
            content = result.content or ""
            # Show first 100 chars
            preview = content[:100] + "..." if len(content) > 100 else content
            print(f"    {preview}")
        else:
            print(f"    ERROR: {result.error}")


async def example_race():
    """
    Race multiple models - return the first response.
    Useful when you want the fastest answer.
    """
    router = LLMRouter(load_config())
    executor = ParallelExecutor(router)

    print("\n=== Race: First model to respond wins ===\n")

    try:
        result = await executor.race(
            prompt="What is 2 + 2?",
            models=["gpt-4", "gpt-3.5-turbo", "claude-3-haiku"],
            max_tokens=10,
        )
        print(f"  Winner: {result.model}")
        print(f"  Response: {result.content}")
    except Exception as e:
        print(f"  All models failed: {e}")


async def example_quick_parallel():
    """
    Quick one-liner for parallel execution.
    """
    router = LLMRouter(load_config())

    print("\n=== Quick parallel helper ===\n")

    results = await parallel_map(
        router,
        tasks=[
            {"agent_id": "a1", "model": "gpt-4", "messages": [{"role": "user", "content": "Say 'hello'"}]},
            {"agent_id": "a2", "model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "Say 'world'"}]},
        ],
        max_concurrent=5,
        max_tokens=20,
    )

    for r in results:
        print(f"  {r.agent_id}: {r.content}")


async def example_multi_agent_workflow():
    """
    Full multi-agent workflow example.
    Researcher -> Writer -> Reviewer pipeline.
    """
    router = LLMRouter(load_config())
    executor = ParallelExecutor(router)

    print("\n=== Multi-Agent Workflow ===\n")

    # Step 1: Research agents gather info in parallel
    print("Step 1: Research agents gathering information...")
    research_results = await executor.broadcast(
        prompt="What are the key features of Python? List 3.",
        models=["gpt-4", "claude-3-opus"],
        max_tokens=100,
    )

    # Combine research
    research_summary = "\n".join([
        r.content for r in research_results if r.success
    ])

    # Step 2: Writer creates content based on research
    print("Step 2: Writer creating content...")
    writer_result = await router.chat(
        messages=[
            {"role": "system", "content": "You are a technical writer."},
            {"role": "user", "content": f"Based on this research, write a brief intro to Python:\n{research_summary}"}
        ],
        model="gpt-4",
        max_tokens=200,
    )

    print(f"  Draft: {writer_result.choices[0].message.content[:150]}...")

    # Step 3: Reviewers check content in parallel
    print("Step 3: Reviewers checking content...")
    review_results = await executor.broadcast(
        prompt=f"Rate this intro (1-10): {writer_result.choices[0].message.content}",
        models=["gpt-3.5-turbo", "claude-3-haiku"],
        max_tokens=50,
    )

    for r in review_results:
        if r.success:
            print(f"  {r.model} rating: {r.content}")


async def main():
    """Run all examples."""
    await example_broadcast()
    await example_map()
    await example_race()
    await example_quick_parallel()
    await example_multi_agent_workflow()


if __name__ == "__main__":
    asyncio.run(main())
