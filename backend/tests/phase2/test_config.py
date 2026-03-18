"""
Phase 2 — Config: core/config.py

Tests validate that AppConfig loads correctly from config.yaml
and that all expected keys are present and typed correctly.
No network calls — pure config validation.
"""

import pytest

pytestmark = [pytest.mark.phase2, pytest.mark.unit]

EXPECTED_AGENTS = {"fundamental", "technical", "quant", "sector", "sentiment", "synthesis"}
HAIKU_AGENTS = {"fundamental", "technical", "quant"}
SONNET_AGENTS = {"sector", "sentiment", "synthesis"}


class TestConfigLoads:
    def test_get_config_returns_object(self):
        from backend.core.config import get_config
        cfg = get_config()
        assert cfg is not None

    def test_get_config_is_singleton(self):
        from backend.core.config import get_config
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2, "get_config() should return the same instance each call"


class TestModelAssignments:
    def test_all_agents_have_model(self):
        from backend.core.config import get_config
        cfg = get_config()
        for agent in EXPECTED_AGENTS:
            assert agent in cfg.anthropic.models, f"No model assigned for agent '{agent}'"
            assert cfg.anthropic.models[agent], f"Model for '{agent}' is empty"

    def test_haiku_agents_use_haiku(self):
        from backend.core.config import get_config
        cfg = get_config()
        for agent in HAIKU_AGENTS:
            model = cfg.anthropic.models[agent]
            assert "haiku" in model.lower(), (
                f"Agent '{agent}' should use Haiku, got '{model}'"
            )

    def test_sonnet_agents_use_sonnet(self):
        from backend.core.config import get_config
        cfg = get_config()
        for agent in SONNET_AGENTS:
            model = cfg.anthropic.models[agent]
            assert "sonnet" in model.lower(), (
                f"Agent '{agent}' should use Sonnet, got '{model}'"
            )


class TestSignalWeights:
    def test_weights_sum_to_one(self):
        from backend.core.config import get_config
        cfg = get_config()
        total = sum(cfg.signal_weights.values())
        assert abs(total - 1.0) < 1e-6, (
            f"Signal weights must sum to 1.0, got {total}"
        )

    def test_all_weights_positive(self):
        from backend.core.config import get_config
        cfg = get_config()
        for agent, weight in cfg.signal_weights.items():
            assert weight > 0, f"Weight for '{agent}' must be positive, got {weight}"


class TestCacheConfig:
    def test_cache_directory_is_set(self):
        from backend.core.config import get_config
        cfg = get_config()
        assert cfg.cache.directory is not None
        assert len(cfg.cache.directory) > 0

    def test_schema_version_is_positive_int(self):
        from backend.core.config import get_config
        cfg = get_config()
        assert isinstance(cfg.cache.schema_version, int)
        assert cfg.cache.schema_version >= 1


class TestSynthesisThresholds:
    def test_thresholds_are_ordered(self):
        from backend.core.config import get_config
        cfg = get_config()
        s = cfg.synthesis
        assert s.sell_threshold < s.hold_threshold < s.buy_threshold < s.strong_buy_threshold, (
            "Synthesis thresholds must be strictly increasing: sell < hold < buy < strong_buy"
        )

    def test_thresholds_in_unit_range(self):
        from backend.core.config import get_config
        cfg = get_config()
        for name, val in vars(cfg.synthesis).items():
            if isinstance(val, float):
                assert 0.0 <= val <= 1.0, f"Threshold '{name}' = {val} out of [0, 1] range"
