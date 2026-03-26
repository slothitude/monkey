"""Example usage of the LLM Router SDK."""

import asyncio
from llm_router import LLMRouter, load_config


async def main():
    # Method 1: Load from config file
    # router = LLMRouter.from_config("config.yaml")

    # Method 2: Use environment variables
    router = LLMRouter(load_config())

    # List available models
    print("Available models:")
    models = router.get_models()
    for model in models.data:
        print(f"  - {model.id} (provider: {model.owned_by})")
    print()

    # Example chat completion
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello! What's 2+2?"},
    ]

    # Non-streaming example
    print("Non-streaming response:")
    try:
        response = await router.chat(
            messages=messages,
            model="gpt-4",  # Will route to OpenAI provider
            max_tokens=100,
        )
        print(f"Response: {response.choices[0].message.content}")
        print(f"Tokens used: {response.usage.total_tokens}")
    except Exception as e:
        print(f"Error: {e}")
    print()

    # Streaming example
    print("Streaming response:")
    try:
        async for chunk in router.stream(
            messages=messages,
            model="gpt-4",
            max_tokens=100,
        ):
            for choice in chunk.choices:
                if "content" in choice.get("delta", {}):
                    print(choice["delta"]["content"], end="", flush=True)
        print()
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
