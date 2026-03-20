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

        Raises KeyError for unknown agent names so misconfiguration is
        caught immediately rather than silently falling back to a default.
        """
        models = self.config.anthropic.models
        if agent_name not in models:
            raise KeyError(
                f"No model configured for agent '{agent_name}'. "
                f"Available agents: {list(models.keys())}"
            )
        return models[agent_name]


_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    """Return the singleton ModelRouter, initialised from config on first call."""
    global _router
    if _router is None:
        _router = ModelRouter(get_config())
    return _router
