"""Test script for LLM Router."""

import asyncio
from llm_router import LLMRouter, RouterConfig, ProviderConfig


async def test_router_without_api_keys():
    """Test router functionality without making actual API calls."""

    # Create a router with mock configuration
    config = RouterConfig(
        providers={
            "openai": ProviderConfig(
                api_key="test-key",
                models=["gpt-4", "gpt-3.5-turbo"],
                priority=1,
            ),
            "anthropic": ProviderConfig(
                api_key="test-key",
                models=["claude-3-opus"],
                priority=2,
            ),
        },
        default_provider="openai",
        failover_enabled=True,
    )

    router = LLMRouter(config)

    # Test model listing
    print("Testing model listing...")
    models = router.get_models()
    assert len(models.data) == 3, f"Expected 3 models, got {len(models.data)}"
    print(f"  Found {len(models.data)} models: {[m.id for m in models.data]}")

    # Test provider routing
    print("\nTesting provider routing...")
    assert router._get_provider_for_model("gpt-4") == "openai"
    assert router._get_provider_for_model("claude-3-opus") == "anthropic"
    assert router._get_provider_for_model("unknown") == "openai"  # default
    print("  Provider routing OK")

    # Test failover ordering
    print("\nTesting failover ordering...")
    failover_order = router._get_failover_providers("gpt-4")
    assert failover_order[0] == "openai", "OpenAI should be first for gpt-4"
    assert failover_order[1] == "anthropic", "Anthropic should be second"
    print(f"  Failover order: {failover_order}")

    print("\nAll tests passed!")


if __name__ == "__main__":
    asyncio.run(test_router_without_api_keys())
