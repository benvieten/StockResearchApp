"""
Phase 2 — Model router: core/model_router.py

Tests validate that ModelRouter returns the correct model string for each agent
and that the Anthropic client is initialized.
No API calls are made.
"""

import pytest

pytestmark = [pytest.mark.phase2, pytest.mark.unit]

EXPECTED_AGENTS = ["fundamental", "technical", "quant", "sector", "sentiment", "synthesis"]


@pytest.fixture(scope="module")
def router():
    from backend.core.config import get_config
    from backend.core.model_router import ModelRouter
    return ModelRouter(get_config())


class TestModelRouter:
    def test_instantiates(self, router):
        assert router is not None

    def test_get_model_returns_string_for_all_agents(self, router):
        for agent in EXPECTED_AGENTS:
            model = router.get_model(agent)
            assert isinstance(model, str), f"get_model('{agent}') returned non-string"
            assert len(model) > 0, f"get_model('{agent}') returned empty string"

    def test_get_model_unknown_agent_raises(self, router):
        with pytest.raises((KeyError, ValueError)):
            router.get_model("nonexistent_agent")

    def test_haiku_agents_return_haiku_model(self, router):
        for agent in ["fundamental", "technical", "quant"]:
            model = router.get_model(agent)
            assert "haiku" in model.lower(), (
                f"Expected Haiku model for '{agent}', got '{model}'"
            )

    def test_sonnet_agents_return_sonnet_model(self, router):
        for agent in ["sector", "sentiment", "synthesis"]:
            model = router.get_model(agent)
            assert "sonnet" in model.lower(), (
                f"Expected Sonnet model for '{agent}', got '{model}'"
            )

    def test_client_is_accessible(self, router):
        from anthropic import Anthropic
        assert isinstance(router.client, Anthropic)

    def test_model_strings_are_valid_claude_ids(self, router):
        """Model IDs must start with 'claude-' to be valid Anthropic model IDs."""
        for agent in EXPECTED_AGENTS:
            model = router.get_model(agent)
            assert model.startswith("claude-"), (
                f"Model ID for '{agent}' doesn't start with 'claude-': '{model}'"
            )
