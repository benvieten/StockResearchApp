"""
Phase 3 — Synthesis agent: pure logic unit tests.

All functions tested here are deterministic with no LLM or network calls:
  - normalise_signals
  - compute_composite
  - score_to_verdict
  - score_to_conviction
  - check_full_consensus
  - apply_profile_adjustments
  - select_weights
"""

import pytest

pytestmark = [pytest.mark.phase3, pytest.mark.unit]


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def normalise():
    from backend.agents.synthesis import normalise_signals

    return normalise_signals


@pytest.fixture
def composite():
    from backend.agents.synthesis import compute_composite

    return compute_composite


@pytest.fixture
def verdict():
    from backend.agents.synthesis import score_to_verdict

    return score_to_verdict


@pytest.fixture
def conviction():
    from backend.agents.synthesis import score_to_conviction

    return score_to_conviction


@pytest.fixture
def consensus():
    from backend.agents.synthesis import check_full_consensus

    return check_full_consensus


@pytest.fixture
def adjust_weights():
    from backend.agents.synthesis import apply_profile_adjustments

    return apply_profile_adjustments


@pytest.fixture
def select():
    from backend.agents.synthesis import select_weights

    return select_weights


@pytest.fixture
def thresholds():
    from backend.core.config import get_config

    return get_config().synthesis


@pytest.fixture
def default_weights():
    from backend.core.config import get_config

    return dict(get_config().signal_weights)


@pytest.fixture
def regime_weights():
    from backend.core.config import get_config

    return get_config().regime_signal_weights


def _make_fund(quality: float = 0.7):
    from backend.core.data_models import FundamentalSignal

    return FundamentalSignal(
        reasoning="test",
        quality_score=quality,
        valuation_verdict="fair",
        key_flags=[],
        metrics={},
        data_quality="full",
    )


def _make_tech(direction: str = "bullish", confidence: float = 0.8):
    from backend.core.data_models import TechnicalSignal

    return TechnicalSignal(
        reasoning="test",
        direction=direction,
        confidence=confidence,
        key_levels={"support": 100.0, "resistance": 120.0},
        indicator_summary="test",
        raw_indicators={},
        data_quality="full",
    )


def _make_quant(composite: float = 0.6):
    from backend.core.data_models import QuantSignal

    return QuantSignal(
        composite_score=composite, factor_breakdown={}, data_quality="full"
    )


def _make_sector(perf: str = "outperforming"):
    from backend.core.data_models import SectorSignal

    return SectorSignal(
        reasoning="test",
        sector="Technology",
        relative_performance=perf,
        sector_etf="XLK",
        peer_comparison={},
        data_quality="full",
    )


def _make_sentiment(score: float = 0.4):
    from backend.core.data_models import SentimentSignal

    return SentimentSignal(
        reasoning="test",
        raw_score=score,
        adjusted_score=score,
        bot_risk="low",
        source_breakdown={},
        narrative_themes=["growth"],
        mention_volume=10,
        data_quality="full",
    )


def _make_analyst(upside: float | None = 0.15, rec_mean: float | None = None):
    from backend.core.data_models import AnalystData

    return AnalystData(upside_to_mean=upside, recommendation_mean=rec_mean)


def _make_profile(
    risk="moderate", horizon="medium_term", goal="growth", exp="intermediate"
):
    from backend.core.data_models import TraderProfile

    return TraderProfile(
        risk_tolerance=risk, time_horizon=horizon, goal=goal, experience=exp
    )


def _make_regime(regime: str = "bull", confidence: float = 0.80, vix: float = 15.0):
    from backend.core.regime import RegimeSignal

    return RegimeSignal(
        regime=regime,
        confidence=confidence,
        vix=vix,
        adx=None,
        ema200_slope=None,
        spy_vs_ema200=None,
    )


# ── normalise_signals ──────────────────────────────────────────────────────────


class TestNormaliseSignals:
    def test_all_signals_present_returns_six_keys(self, normalise):
        scores = normalise(
            _make_fund(),
            _make_tech(),
            _make_quant(),
            _make_sector(),
            _make_sentiment(),
            _make_analyst(),
        )
        assert set(scores.keys()) == {
            "fundamental",
            "technical",
            "quant",
            "sector",
            "sentiment",
            "analyst",
        }

    def test_all_none_signals_returns_neutral(self, normalise):
        scores = normalise(None, None, None, None, None, None)
        for k, v in scores.items():
            assert v == pytest.approx(
                0.5
            ), f"All-None signals must default to 0.5, got {k}={v}"

    def test_fundamental_quality_score_passed_through(self, normalise):
        scores = normalise(_make_fund(quality=0.8), None, None, None, None)
        assert scores["fundamental"] == pytest.approx(0.8)

    def test_bullish_tech_high_confidence_near_one(self, normalise):
        scores = normalise(None, _make_tech("bullish", 1.0), None, None, None)
        assert scores["technical"] == pytest.approx(1.0)

    def test_bearish_tech_high_confidence_near_zero(self, normalise):
        scores = normalise(None, _make_tech("bearish", 1.0), None, None, None)
        assert scores["technical"] == pytest.approx(0.0)

    def test_neutral_tech_always_midpoint(self, normalise):
        for conf in [0.0, 0.5, 1.0]:
            scores = normalise(None, _make_tech("neutral", conf), None, None, None)
            assert scores["technical"] == pytest.approx(
                0.5
            ), f"Neutral direction with confidence={conf} should always give 0.5"

    def test_outperforming_sector_gives_0_75(self, normalise):
        scores = normalise(None, None, None, _make_sector("outperforming"), None)
        assert scores["sector"] == pytest.approx(0.75)

    def test_underperforming_sector_gives_0_25(self, normalise):
        scores = normalise(None, None, None, _make_sector("underperforming"), None)
        assert scores["sector"] == pytest.approx(0.25)

    def test_sentiment_remapped_from_minus1_to_1(self, normalise):
        # raw adjusted_score=1.0 → normalised=1.0; -1.0 → 0.0; 0.0 → 0.5
        assert normalise(None, None, None, None, _make_sentiment(1.0))[
            "sentiment"
        ] == pytest.approx(1.0)
        assert normalise(None, None, None, None, _make_sentiment(-1.0))[
            "sentiment"
        ] == pytest.approx(0.0)
        assert normalise(None, None, None, None, _make_sentiment(0.0))[
            "sentiment"
        ] == pytest.approx(0.5)

    def test_analyst_upside_score_clamped_to_unit_range(self, normalise):
        # Very high upside (e.g. 200%) → clamped to 1.0
        scores = normalise(None, None, None, None, None, _make_analyst(upside=2.0))
        assert scores["analyst"] == pytest.approx(1.0)
        # Very negative upside → clamped to 0.0
        scores = normalise(None, None, None, None, None, _make_analyst(upside=-2.0))
        assert scores["analyst"] == pytest.approx(0.0)

    def test_analyst_recommendation_mean_clamped(self, normalise):
        # rec_mean=1.0 (strong buy) → 1.0; rec_mean=5.0 (strong sell) → 0.0
        assert normalise(
            None, None, None, None, None, _make_analyst(upside=None, rec_mean=1.0)
        )["analyst"] == pytest.approx(1.0)
        assert normalise(
            None, None, None, None, None, _make_analyst(upside=None, rec_mean=5.0)
        )["analyst"] == pytest.approx(0.0)

    def test_analyst_with_target_but_no_rec_mean_does_not_crash(self):
        """
        Regression: SIDU had target_mean set but recommendation_mean=None.
        The synthesis prompt formatter must not crash with NoneType.__format__.
        """
        from backend.core.data_models import AnalystData

        analyst = AnalystData(
            current_price=5.50,
            target_mean=17.81,
            target_high=20.0,
            target_low=15.0,
            upside_to_mean=2.24,
            recommendation_key="buy",
            recommendation_mean=None,  # ← the crash case
            num_analysts=3,
        )

        # Build the analyst_text block the same way synthesis does
        def _price(v):
            return f"${v:.2f}" if v is not None else "n/a"

        def _pct_upside(v):
            return f"{v * 100:+.1f}%" if v is not None else "n/a"

        rec_mean_str = (
            f"{analyst.recommendation_mean:.1f}"
            if analyst.recommendation_mean is not None
            else "n/a"
        )
        try:
            text = (
                f"  Current price: {_price(analyst.current_price)}\n"
                f"  12-month targets: mean={_price(analyst.target_mean)}\n"
                f"  Upside to mean target: {_pct_upside(analyst.upside_to_mean)}\n"
                f"  Consensus: {analyst.recommendation_key or 'n/a'} "
                f"(mean={rec_mean_str}/5.0)\n"
                f"  Analyst count: {analyst.num_analysts or 'n/a'}"
            )
        except (TypeError, ValueError) as e:
            pytest.fail(
                f"Analyst text formatting crashed with None recommendation_mean: {e}"
            )
        assert "n/a" in text

    def test_all_scores_in_unit_range(self, normalise):
        scores = normalise(
            _make_fund(),
            _make_tech(),
            _make_quant(),
            _make_sector(),
            _make_sentiment(),
            _make_analyst(),
        )
        for k, v in scores.items():
            assert 0.0 <= v <= 1.0, f"Score {k}={v} out of [0, 1]"


# ── compute_composite ──────────────────────────────────────────────────────────


class TestComputeComposite:
    def test_weights_applied_correctly(self, composite):
        scores = {"a": 1.0, "b": 0.0}
        weights = {"a": 0.75, "b": 0.25}
        result = composite(scores, weights)
        assert result == pytest.approx(0.75)

    def test_missing_weight_defaults_to_zero(self, composite):
        scores = {"a": 1.0, "b": 1.0}
        weights = {"a": 1.0}  # b has no weight
        result = composite(scores, weights)
        assert result == pytest.approx(1.0)

    def test_empty_weights_returns_neutral(self, composite):
        result = composite({"a": 0.8}, {})
        assert result == pytest.approx(0.5)

    def test_result_in_unit_range(self, composite):
        scores = {"f": 0.6, "t": 0.7, "q": 0.5, "s": 0.8, "sent": 0.4}
        weights = {"f": 0.2, "t": 0.2, "q": 0.2, "s": 0.2, "sent": 0.2}
        result = composite(scores, weights)
        assert 0.0 <= result <= 1.0


# ── score_to_verdict ───────────────────────────────────────────────────────────


class TestScoreToVerdict:
    def test_strong_buy_above_threshold(self, verdict, thresholds):
        assert verdict(thresholds.strong_buy_threshold, thresholds) == "strong_buy"
        assert verdict(0.99, thresholds) == "strong_buy"

    def test_buy_in_range(self, verdict, thresholds):
        mid = (thresholds.buy_threshold + thresholds.strong_buy_threshold) / 2
        assert verdict(mid, thresholds) == "buy"

    def test_hold_in_range(self, verdict, thresholds):
        mid = (thresholds.hold_threshold + thresholds.buy_threshold) / 2
        assert verdict(mid, thresholds) == "hold"

    def test_sell_in_range(self, verdict, thresholds):
        mid = (thresholds.sell_threshold + thresholds.hold_threshold) / 2
        assert verdict(mid, thresholds) == "sell"

    def test_strong_sell_below_threshold(self, verdict, thresholds):
        assert verdict(thresholds.sell_threshold - 0.01, thresholds) == "strong_sell"
        assert verdict(0.0, thresholds) == "strong_sell"

    def test_all_verdicts_are_valid_literals(self, verdict, thresholds):
        valid = {"strong_buy", "buy", "hold", "sell", "strong_sell"}
        for score in [0.0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0]:
            v = verdict(score, thresholds)
            assert v in valid, f"score={score} produced invalid verdict '{v}'"


# ── score_to_conviction ────────────────────────────────────────────────────────


class TestScoreToConviction:
    def test_extreme_score_gives_high_conviction(self, conviction):
        assert conviction(0.9) == "high"
        assert conviction(0.1) == "high"

    def test_moderate_score_gives_medium_conviction(self, conviction):
        assert conviction(0.65) == "medium"
        assert conviction(0.35) == "medium"

    def test_near_midpoint_gives_low_conviction(self, conviction):
        assert conviction(0.5) == "low"
        assert conviction(0.55) == "low"

    def test_full_consensus_caps_high_at_medium(self, conviction):
        # Normally 0.9 → high, but with full_consensus it should be capped
        assert conviction(0.9, full_consensus=True) == "medium"

    def test_full_consensus_does_not_affect_low_or_medium(self, conviction):
        assert conviction(0.55, full_consensus=True) == "low"
        assert conviction(0.65, full_consensus=True) == "medium"


# ── check_full_consensus ───────────────────────────────────────────────────────


class TestCheckFullConsensus:
    def test_all_bullish_returns_true(self, consensus):
        scores = {"f": 0.75, "t": 0.80, "q": 0.70, "s": 0.65, "sent": 0.72}
        assert consensus(scores) is True

    def test_all_bearish_returns_true(self, consensus):
        scores = {"f": 0.25, "t": 0.20, "q": 0.35, "s": 0.30, "sent": 0.22}
        assert consensus(scores) is True

    def test_mixed_signals_returns_false(self, consensus):
        scores = {"f": 0.75, "t": 0.25, "q": 0.60, "s": 0.55, "sent": 0.70}
        assert consensus(scores) is False

    def test_neutral_scores_return_false(self, consensus):
        scores = {"f": 0.5, "t": 0.5, "q": 0.5}
        assert consensus(scores) is False

    def test_fewer_than_3_signals_returns_false(self, consensus):
        assert consensus({"f": 0.8, "t": 0.9}) is False


# ── apply_profile_adjustments ──────────────────────────────────────────────────


class TestApplyProfileAdjustments:
    def test_output_weights_sum_to_one(self, adjust_weights, default_weights):
        for risk in ["conservative", "moderate", "aggressive"]:
            for horizon in ["short_term", "medium_term", "long_term"]:
                profile = _make_profile(risk=risk, horizon=horizon)
                adjusted = adjust_weights(default_weights, profile)
                total = sum(adjusted.values())
                assert (
                    abs(total - 1.0) < 1e-9
                ), f"Weights don't sum to 1.0 for {risk}/{horizon}: {total}"

    def test_output_all_weights_positive(self, adjust_weights, default_weights):
        for risk in ["conservative", "moderate", "aggressive"]:
            profile = _make_profile(risk=risk)
            adjusted = adjust_weights(default_weights, profile)
            for k, v in adjusted.items():
                assert v >= 0.0, f"Weight for '{k}' went negative: {v}"

    def test_conservative_boosts_fundamental(self, adjust_weights, default_weights):
        baseline = _make_profile(risk="moderate")
        conservative = _make_profile(risk="conservative")
        w_base = adjust_weights(default_weights, baseline)
        w_cons = adjust_weights(default_weights, conservative)
        assert (
            w_cons["fundamental"] > w_base["fundamental"]
        ), "Conservative profile should increase fundamental weight vs moderate"

    def test_short_term_boosts_technical(self, adjust_weights, default_weights):
        baseline = _make_profile(horizon="medium_term")
        short = _make_profile(horizon="short_term")
        w_base = adjust_weights(default_weights, baseline)
        w_short = adjust_weights(default_weights, short)
        assert (
            w_short["technical"] > w_base["technical"]
        ), "Short-term horizon should increase technical weight"

    def test_long_term_boosts_fundamental(self, adjust_weights, default_weights):
        baseline = _make_profile(horizon="medium_term")
        long = _make_profile(horizon="long_term")
        w_base = adjust_weights(default_weights, baseline)
        w_long = adjust_weights(default_weights, long)
        assert (
            w_long["fundamental"] > w_base["fundamental"]
        ), "Long-term horizon should increase fundamental weight"


# ── select_weights ─────────────────────────────────────────────────────────────


class TestSelectWeights:
    def test_bull_regime_high_confidence_returns_bull_preset(
        self, select, default_weights, regime_weights
    ):
        regime = _make_regime("bull", confidence=0.80)
        result = select(regime, default_weights, regime_weights)
        assert result == regime_weights["bull"]

    def test_low_confidence_falls_back_to_default(
        self, select, default_weights, regime_weights
    ):
        regime = _make_regime("bull", confidence=0.40)  # below 0.55 threshold
        result = select(regime, default_weights, regime_weights)
        assert result == default_weights

    def test_empty_regime_weights_falls_back_to_default(self, select, default_weights):
        regime = _make_regime("bull", confidence=0.90)
        result = select(regime, default_weights, {})
        assert result == default_weights

    def test_bear_regime_returns_bear_preset(
        self, select, default_weights, regime_weights
    ):
        regime = _make_regime("bear", confidence=0.75)
        result = select(regime, default_weights, regime_weights)
        assert result == regime_weights["bear"]
