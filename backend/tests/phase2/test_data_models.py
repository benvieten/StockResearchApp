"""
Phase 2 — Pydantic schemas: core/data_models.py

Tests validate that all signal models:
  - Accept valid data without raising
  - Reject invalid types/values with ValidationError
  - Contain the required reasoning and data_quality fields
  - Have correct field types and ranges

No network calls — pure schema validation.
"""

import pytest
from pydantic import ValidationError

pytestmark = [pytest.mark.phase2, pytest.mark.unit]


class TestTechnicalSignal:
    def test_valid_bullish(self):
        from backend.core.data_models import TechnicalSignal
        signal = TechnicalSignal(
            reasoning="EMA 20 crossed above EMA 50. RSI at 58.",
            direction="bullish",
            confidence=0.72,
            key_levels={"support": 185.0, "resistance": 198.0},
            indicator_summary="Uptrend intact with moderate momentum.",
            raw_indicators={"ema_20": 191.0, "rsi_14": 58.0},
            data_quality="full",
        )
        assert signal.direction == "bullish"
        assert 0.0 <= signal.confidence <= 1.0

    def test_invalid_direction_raises(self):
        from backend.core.data_models import TechnicalSignal
        with pytest.raises(ValidationError):
            TechnicalSignal(
                reasoning="test",
                direction="very_bullish",   # not a valid Literal
                confidence=0.5,
                key_levels={},
                indicator_summary="",
                raw_indicators={},
                data_quality="full",
            )

    def test_confidence_out_of_range_raises(self):
        from backend.core.data_models import TechnicalSignal
        with pytest.raises(ValidationError):
            TechnicalSignal(
                reasoning="test",
                direction="bullish",
                confidence=1.5,   # > 1.0
                key_levels={},
                indicator_summary="",
                raw_indicators={},
                data_quality="full",
            )

    def test_has_reasoning_field(self):
        from backend.core.data_models import TechnicalSignal
        fields = TechnicalSignal.model_fields
        assert "reasoning" in fields, "TechnicalSignal must have a 'reasoning' field"

    def test_has_data_quality_field(self):
        from backend.core.data_models import TechnicalSignal
        fields = TechnicalSignal.model_fields
        assert "data_quality" in fields


class TestFundamentalSignal:
    def test_valid_signal(self):
        from backend.core.data_models import FundamentalSignal
        signal = FundamentalSignal(
            reasoning="P/E of 32 is elevated but margins are expanding.",
            quality_score=0.68,
            valuation_verdict="overvalued",
            key_flags=["high PE", "strong FCF"],
            metrics={"pe": 32.1, "gross_margin": 0.43},
            data_quality="full",
        )
        assert 0.0 <= signal.quality_score <= 1.0

    def test_invalid_valuation_verdict_raises(self):
        from backend.core.data_models import FundamentalSignal
        with pytest.raises(ValidationError):
            FundamentalSignal(
                reasoning="test",
                quality_score=0.5,
                valuation_verdict="neutral",   # not a valid Literal
                key_flags=[],
                metrics={},
                data_quality="full",
            )

    def test_quality_score_out_of_range_raises(self):
        from backend.core.data_models import FundamentalSignal
        with pytest.raises(ValidationError):
            FundamentalSignal(
                reasoning="test",
                quality_score=-0.1,   # < 0.0
                valuation_verdict="fair",
                key_flags=[],
                metrics={},
                data_quality="full",
            )

    def test_partial_data_quality_accepted(self):
        from backend.core.data_models import FundamentalSignal
        signal = FundamentalSignal(
            reasoning="Some fields were missing.",
            quality_score=0.4,
            valuation_verdict="fair",
            key_flags=["incomplete data"],
            metrics={"pe": None},
            data_quality="partial",
        )
        assert signal.data_quality == "partial"


class TestQuantSignal:
    def test_valid_signal(self):
        from backend.core.data_models import QuantSignal
        signal = QuantSignal(
            composite_score=0.61,
            factor_breakdown={
                "momentum": 0.72,
                "quality": 0.68,
                "value": 0.45,
                "low_vol": 0.59,
            },
            data_quality="full",
        )
        assert 0.0 <= signal.composite_score <= 1.0

    def test_composite_out_of_range_raises(self):
        from backend.core.data_models import QuantSignal
        with pytest.raises(ValidationError):
            QuantSignal(
                composite_score=1.1,
                factor_breakdown={},
                data_quality="full",
            )


class TestSentimentSignal:
    def test_valid_signal(self):
        from backend.core.data_models import SentimentSignal
        signal = SentimentSignal(
            reasoning="Reddit is cautiously bullish; StockTwits skews bearish.",
            raw_score=0.2,
            adjusted_score=0.15,
            bot_risk="low",
            source_breakdown={"reddit": 0.3, "stocktwits": -0.1, "news": 0.4},
            narrative_themes=["earnings beat", "buyback program", "macro headwinds"],
            mention_volume=342,
            data_quality="full",
        )
        assert -1.0 <= signal.raw_score <= 1.0
        assert -1.0 <= signal.adjusted_score <= 1.0

    def test_invalid_bot_risk_raises(self):
        from backend.core.data_models import SentimentSignal
        with pytest.raises(ValidationError):
            SentimentSignal(
                reasoning="test",
                raw_score=0.0,
                adjusted_score=0.0,
                bot_risk="extreme",   # not a valid Literal
                source_breakdown={},
                narrative_themes=[],
                mention_volume=0,
                data_quality="full",
            )

    def test_adjusted_score_out_of_range_raises(self):
        from backend.core.data_models import SentimentSignal
        with pytest.raises(ValidationError):
            SentimentSignal(
                reasoning="test",
                raw_score=0.0,
                adjusted_score=1.5,   # > 1.0
                bot_risk="low",
                source_breakdown={},
                narrative_themes=[],
                mention_volume=0,
                data_quality="full",
            )


class TestFinalReport:
    def test_valid_report(self):
        from backend.core.data_models import FinalReport
        report = FinalReport(
            ticker="AAPL",
            verdict="buy",
            conviction="medium",
            narrative="Apple continues to demonstrate strong fundamentals...",
            bull_case=["Strong FCF", "Services growth"],
            bear_case=["High valuation", "China risk"],
            conflicts=["Technical bullish but fundamentals overvalued"],
            signal_scores={"fundamental": 0.65, "technical": 0.72},
            generated_at="2026-03-18T12:00:00Z",
        )
        assert report.ticker == "AAPL"
        assert report.verdict == "buy"

    def test_invalid_verdict_raises(self):
        from backend.core.data_models import FinalReport
        with pytest.raises(ValidationError):
            FinalReport(
                ticker="AAPL",
                verdict="maybe",   # not a valid Literal
                conviction="medium",
                narrative="",
                bull_case=[],
                bear_case=[],
                conflicts=[],
                signal_scores={},
                generated_at="2026-03-18T12:00:00Z",
            )

    def test_model_dump_json_is_valid(self):
        import json
        from backend.core.data_models import FinalReport
        report = FinalReport(
            ticker="AAPL",
            verdict="hold",
            conviction="low",
            narrative="Mixed signals.",
            bull_case=["FCF positive"],
            bear_case=["High PE"],
            conflicts=[],
            signal_scores={},
            generated_at="2026-03-18T12:00:00Z",
        )
        dumped = report.model_dump_json()
        parsed = json.loads(dumped)
        assert parsed["ticker"] == "AAPL"
