"""Configuration management for LLM router."""

from pathlib import Path
from typing import Any, Optional
import os
import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class ProviderConfig(BaseModel):
    """Configuration for a single provider."""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    models: list[str] = []
    enabled: bool = True
    priority: int = 100  # Lower = higher priority for failover
    extra: dict[str, Any] = {}


class RouterConfig(BaseModel):
    """Main router configuration."""
    providers: dict[str, ProviderConfig] = {}
    default_provider: Optional[str] = None
    failover_enabled: bool = True
    timeout: int = 60


class Settings(BaseSettings):
    """Application settings from environment variables."""
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    zai_api_key: Optional[str] = None
    config_path: str = "config.yaml"

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


def load_config(config_path: Optional[str] = None) -> RouterConfig:
    """Load configuration from YAML file or environment variables."""
    settings = Settings()

    path = Path(config_path or settings.config_path)

    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {"providers": {}}

    # Fill in API keys from environment if not in config
    providers = data.get("providers", {})

    if "openai" in providers and not providers["openai"].get("api_key"):
        providers["openai"]["api_key"] = settings.openai_api_key
    if "anthropic" in providers and not providers["anthropic"].get("api_key"):
        providers["anthropic"]["api_key"] = settings.anthropic_api_key
    if "openrouter" in providers and not providers["openrouter"].get("api_key"):
        providers["openrouter"]["api_key"] = settings.openrouter_api_key
    if "zai" in providers and not providers["zai"].get("api_key"):
        providers["zai"]["api_key"] = settings.zai_api_key

    data["providers"] = {
        name: ProviderConfig(**cfg) for name, cfg in providers.items()
    }

    return RouterConfig(**data)


def get_default_config() -> dict:
    """Generate a default configuration template."""
    return {
        "providers": {
            "openai": {
                "api_key": "${OPENAI_API_KEY}",
                "models": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
                "priority": 1
            },
            "anthropic": {
                "api_key": "${ANTHROPIC_API_KEY}",
                "models": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
                "priority": 2
            },
            "openrouter": {
                "api_key": "${OPENROUTER_API_KEY}",
                "base_url": "https://openrouter.ai/api/v1",
                "models": ["openrouter/auto"],
                "priority": 3
            },
            "zai": {
                "api_key": "${ZAI_API_KEY}",
                "base_url": "https://api.zai.coding/v1",
                "models": ["zai-coding"],
                "priority": 4
            }
        },
        "default_provider": "openai",
        "failover_enabled": True,
        "timeout": 60
    }
