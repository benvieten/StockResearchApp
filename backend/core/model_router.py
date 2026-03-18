"""
ModelRouter — resolves agent names to Anthropic model IDs from config.yaml.

Never hardcode a model name. Always call model_router.get_model(agent_name).
Model assignments live exclusively in config.yaml under anthropic.models.
"""

from __future__ import annotations

from dotenv import load_dotenv
from anthropic import Anthropic

from backend.core.config import AppConfig


class ModelRouter:
    def __init__(self, config: AppConfig) -> None:
        load_dotenv()
        self.config = config
        self.client = Anthropic()

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
