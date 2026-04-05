"""
ModelRouter — resolves agent names to Anthropic model IDs from config.yaml.

Never hardcode a model name. Always call get_model_router().get_model(agent_name).
Model assignments live exclusively in config.yaml under anthropic.models.
"""

from __future__ import annotations

from backend.core.config import AppConfig, get_config


class ModelRouter:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def get_model(self, agent_name: str) -> str:
        """Return the configured model ID for the given agent name.

        Checks ollama.models first, then anthropic.models.
        Raises KeyError for unknown agent names.
        """
        if agent_name in self.config.ollama.models:
            return self.config.ollama.models[agent_name]
        if agent_name in self.config.anthropic.models:
            return self.config.anthropic.models[agent_name]
        all_agents = list(self.config.ollama.models) + list(
            self.config.anthropic.models
        )
        raise KeyError(
            f"No model configured for agent '{agent_name}'. "
            f"Available agents: {all_agents}"
        )

    def get_backend(self, agent_name: str) -> str:
        """Return 'ollama' or 'anthropic' for the given agent name."""
        if agent_name in self.config.ollama.models:
            return "ollama"
        if agent_name in self.config.anthropic.models:
            return "anthropic"
        raise KeyError(f"No backend configured for agent '{agent_name}'")

    def get_ollama_base_url(self) -> str:
        """Return the configured Ollama base URL."""
        return self.config.ollama.base_url


_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    """Return the singleton ModelRouter, initialised from config on first call."""
    global _router
    if _router is None:
        _router = ModelRouter(get_config())
    return _router
