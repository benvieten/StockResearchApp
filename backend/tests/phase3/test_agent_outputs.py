"""
Phase 3 — Agent output schema tests.

These tests run each agent against fixture data and validate the output
conforms to its Pydantic schema. They require:
  1. Cached fixture data in backend/tests/fixtures/ (run `make fixtures`)
  2. ANTHROPIC_API_KEY set in .env

Run with: pytest -m phase3 (skips automatically if fixtures are missing)
"""

import json
import pytest

pytestmark = pytest.mark.phase3


class TestFundamentalAgentOutput:
    async def test_returns_valid_schema(self, aapl_fundamental_signal):
        from backend.core.data_models import FundamentalSignal
        signal = FundamentalSignal.model_validate(aapl_fundamental_signal)
        assert signal is not None

    async def test_quality_score_in_range(self, aapl_fundamental_signal):
        from backend.core.data_models import FundamentalSignal
        signal = FundamentalSignal.model_validate(aapl_fundamental_signal)
        assert 0.0 <= signal.quality_score <= 1.0

    async def test_has_reasoning(self, aapl_fundamental_signal):
        from backend.core.data_models import FundamentalSignal
        signal = FundamentalSignal.model_validate(aapl_fundamental_signal)
        assert len(signal.reasoning) > 20, (
            "reasoning field is too short — LLM may not have reasoned before scoring"
        )

    async def test_metrics_contains_computed_ratios(self, aapl_fundamental_signal):
        from backend.core.data_models import FundamentalSignal
        signal = FundamentalSignal.model_validate(aapl_fundamental_signal)
        expected_ratio_keys = {"pe", "gross_margin", "net_margin", "debt_to_equity"}
        found = expected_ratio_keys & signal.metrics.keys()
        assert len(found) >= 2, (
            f"Expected at least 2 ratio keys in metrics, found: {found}"
        )


class TestTechnicalAgentOutput:
    async def test_returns_valid_schema(self, aapl_technical_signal):
        from backend.core.data_models import TechnicalSignal
        signal = TechnicalSignal.model_validate(aapl_technical_signal)
        assert signal is not None

    async def test_confidence_in_range(self, aapl_technical_signal):
        from backend.core.data_models import TechnicalSignal
        signal = TechnicalSignal.model_validate(aapl_technical_signal)
        assert 0.0 <= signal.confidence <= 1.0

    async def test_key_levels_have_support_and_resistance(self, aapl_technical_signal):
        from backend.core.data_models import TechnicalSignal
        signal = TechnicalSignal.model_validate(aapl_technical_signal)
        assert "support" in signal.key_levels
        assert "resistance" in signal.key_levels
        assert signal.key_levels["resistance"] >= signal.key_levels["support"]

    async def test_raw_indicators_not_empty(self, aapl_technical_signal):
        from backend.core.data_models import TechnicalSignal
        signal = TechnicalSignal.model_validate(aapl_technical_signal)
        assert len(signal.raw_indicators) > 0


class TestQuantAgentOutput:
    async def test_returns_valid_schema(self, aapl_quant_signal):
        from backend.core.data_models import QuantSignal
        signal = QuantSignal.model_validate(aapl_quant_signal)
        assert signal is not None

    async def test_composite_score_in_range(self, aapl_quant_signal):
        from backend.core.data_models import QuantSignal
        signal = QuantSignal.model_validate(aapl_quant_signal)
        assert 0.0 <= signal.composite_score <= 1.0

    async def test_factor_breakdown_has_all_factors(self, aapl_quant_signal):
        from backend.core.data_models import QuantSignal
        signal = QuantSignal.model_validate(aapl_quant_signal)
        expected = {"momentum", "quality", "value", "low_vol"}
        assert expected.issubset(signal.factor_breakdown.keys()), (
            f"Missing factors: {expected - signal.factor_breakdown.keys()}"
        )

    async def test_all_factors_in_unit_range(self, aapl_quant_signal):
        from backend.core.data_models import QuantSignal
        signal = QuantSignal.model_validate(aapl_quant_signal)
        for name, val in signal.factor_breakdown.items():
            if val is not None:
                assert 0.0 <= val <= 1.0, f"Factor '{name}' = {val} out of [0, 1]"


class TestSectorAgentOutput:
    async def test_returns_valid_schema(self, aapl_sector_signal):
        from backend.core.data_models import SectorSignal
        signal = SectorSignal.model_validate(aapl_sector_signal)
        assert signal is not None

    async def test_sector_is_non_empty(self, aapl_sector_signal):
        from backend.core.data_models import SectorSignal
        signal = SectorSignal.model_validate(aapl_sector_signal)
        assert len(signal.sector) > 0

    async def test_aapl_sector_is_technology(self, aapl_sector_signal):
        from backend.core.data_models import SectorSignal
        signal = SectorSignal.model_validate(aapl_sector_signal)
        assert "tech" in signal.sector.lower(), (
            f"AAPL sector should be Technology, got '{signal.sector}'"
        )

    async def test_peer_comparison_not_empty(self, aapl_sector_signal):
        from backend.core.data_models import SectorSignal
        signal = SectorSignal.model_validate(aapl_sector_signal)
        assert len(signal.peer_comparison) > 0


class TestSentimentAgentOutput:
    async def test_returns_valid_schema(self, aapl_sentiment_signal):
        from backend.core.data_models import SentimentSignal
        signal = SentimentSignal.model_validate(aapl_sentiment_signal)
        assert signal is not None

    async def test_scores_in_range(self, aapl_sentiment_signal):
        from backend.core.data_models import SentimentSignal
        signal = SentimentSignal.model_validate(aapl_sentiment_signal)
        assert -1.0 <= signal.raw_score <= 1.0
        assert -1.0 <= signal.adjusted_score <= 1.0

    async def test_adjusted_not_greater_than_raw_when_bots_present(self, aapl_sentiment_signal):
        from backend.core.data_models import SentimentSignal
        signal = SentimentSignal.model_validate(aapl_sentiment_signal)
        if signal.bot_risk in ("medium", "high") and signal.raw_score > 0:
            assert signal.adjusted_score <= signal.raw_score, (
                "adjusted_score should be <= raw_score when positive sentiment "
                "is discounted for bot risk"
            )

    async def test_has_narrative_themes(self, aapl_sentiment_signal):
        from backend.core.data_models import SentimentSignal
        signal = SentimentSignal.model_validate(aapl_sentiment_signal)
        assert len(signal.narrative_themes) >= 1

    async def test_mention_volume_positive(self, aapl_sentiment_signal):
        from backend.core.data_models import SentimentSignal
        signal = SentimentSignal.model_validate(aapl_sentiment_signal)
        assert signal.mention_volume >= 0


class TestSynthesisOutput:
    async def test_returns_valid_schema(
        self,
        aapl_fundamental_signal,
        aapl_technical_signal,
        aapl_quant_signal,
        aapl_sector_signal,
        aapl_sentiment_signal,
    ):
        from backend.core.data_models import FinalReport
        report = FinalReport(**_load_fixture("signal_synthesis"))
        assert report is not None

    async def test_conflicts_field_is_list(
        self,
        aapl_fundamental_signal,
        aapl_technical_signal,
        aapl_quant_signal,
        aapl_sector_signal,
        aapl_sentiment_signal,
    ):
        from backend.core.data_models import FinalReport
        report = FinalReport(**_load_fixture("signal_synthesis"))
        assert isinstance(report.conflicts, list), (
            "conflicts must be a list — synthesis must always enumerate agent disagreements"
        )

    async def test_has_bull_and_bear_case(self):
        from backend.core.data_models import FinalReport
        report = FinalReport(**_load_fixture("signal_synthesis"))
        assert len(report.bull_case) >= 1
        assert len(report.bear_case) >= 1

    async def test_narrative_is_substantial(self):
        from backend.core.data_models import FinalReport
        report = FinalReport(**_load_fixture("signal_synthesis"))
        assert len(report.narrative) > 100, (
            "narrative is too short — synthesis should produce a substantive analysis"
        )


def _load_fixture(name: str) -> dict:
    """Helper for synthesis test which needs direct fixture loading."""
    import json
    from pathlib import Path
    fixture_path = Path(__file__).parent.parent / "fixtures" / f"AAPL_{name}.json"
    if not fixture_path.exists():
        pytest.skip(f"Fixture not found: {fixture_path}")
    return json.loads(fixture_path.read_text())
