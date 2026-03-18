"""
Phase 3 — Quant agent: pure factor computation unit tests.

The Quant agent has no LLM call — it is entirely deterministic computation.
Every function it uses can be unit tested with synthetic data.

Will fail until agents/quant.py exposes its computation functions.
"""

import math
import pytest
import numpy as np

pytestmark = [pytest.mark.phase3, pytest.mark.unit]


@pytest.fixture
def compute_momentum():
    from backend.agents.quant import compute_momentum_score
    return compute_momentum_score


@pytest.fixture
def compute_quality():
    from backend.agents.quant import compute_quality_score
    return compute_quality_score


@pytest.fixture
def compute_value():
    from backend.agents.quant import compute_value_score
    return compute_value_score


@pytest.fixture
def compute_low_vol():
    from backend.agents.quant import compute_low_vol_score
    return compute_low_vol_score


@pytest.fixture
def compute_composite():
    from backend.agents.quant import compute_composite_score
    return compute_composite_score


class TestMomentumScore:
    def test_outperformer_scores_high(self, compute_momentum):
        # Ticker returned 30%, SPY returned 10% — ticker outperformed
        score = compute_momentum(
            ticker_returns={"3m": 0.15, "6m": 0.22, "12m": 0.30},
            spy_returns={"3m": 0.05, "6m": 0.08, "12m": 0.10},
        )
        assert score > 0.5, f"Outperformer should score > 0.5, got {score}"

    def test_underperformer_scores_low(self, compute_momentum):
        score = compute_momentum(
            ticker_returns={"3m": -0.05, "6m": -0.10, "12m": -0.08},
            spy_returns={"3m": 0.05, "6m": 0.08, "12m": 0.10},
        )
        assert score < 0.5, f"Underperformer should score < 0.5, got {score}"

    def test_score_in_unit_range(self, compute_momentum):
        score = compute_momentum(
            ticker_returns={"3m": 0.10, "6m": 0.15, "12m": 0.20},
            spy_returns={"3m": 0.05, "6m": 0.10, "12m": 0.15},
        )
        assert 0.0 <= score <= 1.0

    def test_equal_performance_near_midpoint(self, compute_momentum):
        score = compute_momentum(
            ticker_returns={"3m": 0.10, "6m": 0.10, "12m": 0.10},
            spy_returns={"3m": 0.10, "6m": 0.10, "12m": 0.10},
        )
        assert 0.3 <= score <= 0.7, (
            f"Equal performance should score near 0.5, got {score}"
        )


class TestQualityScore:
    def test_high_roe_low_debt_scores_high(self, compute_quality):
        score = compute_quality(roe=0.45, debt_to_equity=0.5)
        assert score > 0.7

    def test_low_roe_high_debt_scores_low(self, compute_quality):
        score = compute_quality(roe=0.02, debt_to_equity=4.0)
        assert score < 0.4

    def test_none_roe_returns_partial_score(self, compute_quality):
        # Should not crash — should return a degraded score or None
        result = compute_quality(roe=None, debt_to_equity=1.0)
        assert result is None or (0.0 <= result <= 1.0)

    def test_none_debt_to_equity_returns_partial(self, compute_quality):
        result = compute_quality(roe=0.30, debt_to_equity=None)
        assert result is None or (0.0 <= result <= 1.0)

    def test_score_in_unit_range(self, compute_quality):
        score = compute_quality(roe=0.20, debt_to_equity=1.5)
        assert 0.0 <= score <= 1.0


class TestValueScore:
    def test_low_pe_scores_high(self, compute_value):
        # Low PE = high earnings yield = better value
        score = compute_value(pe=8.0)
        assert score > 0.7

    def test_high_pe_scores_low(self, compute_value):
        score = compute_value(pe=80.0)
        assert score < 0.3

    def test_none_pe_returns_none(self, compute_value):
        result = compute_value(pe=None)
        assert result is None

    def test_score_in_unit_range(self, compute_value):
        score = compute_value(pe=25.0)
        assert 0.0 <= score <= 1.0

    def test_negative_pe_returns_none(self, compute_value):
        # Negative PE (loss-making company) should not produce a meaningful value score
        result = compute_value(pe=-10.0)
        assert result is None or result == 0.0


class TestLowVolScore:
    def test_low_vol_stock_scores_high(self, compute_low_vol, sample_ohlcv_df):
        # Create a low-volatility price series
        low_vol_prices = sample_ohlcv_df["Close"] * (1 + np.random.normal(0, 0.002, len(sample_ohlcv_df)))
        low_vol_df = sample_ohlcv_df.copy()
        low_vol_df["Close"] = low_vol_prices
        score = compute_low_vol(low_vol_df)
        assert score > 0.5

    def test_high_vol_stock_scores_low(self, compute_low_vol, sample_ohlcv_df):
        high_vol_prices = sample_ohlcv_df["Close"] * (1 + np.random.normal(0, 0.04, len(sample_ohlcv_df)))
        high_vol_df = sample_ohlcv_df.copy()
        high_vol_df["Close"] = abs(high_vol_prices)
        score = compute_low_vol(high_vol_df)
        assert score < 0.5

    def test_score_in_unit_range(self, compute_low_vol, sample_ohlcv_df):
        score = compute_low_vol(sample_ohlcv_df)
        assert 0.0 <= score <= 1.0


class TestCompositeScore:
    def test_equal_weights_averages_correctly(self, compute_composite):
        score = compute_composite(
            momentum=0.8,
            quality=0.6,
            value=0.4,
            low_vol=0.2,
        )
        assert score == pytest.approx(0.5, rel=1e-3)

    def test_all_ones_returns_one(self, compute_composite):
        assert compute_composite(1.0, 1.0, 1.0, 1.0) == pytest.approx(1.0)

    def test_all_zeros_returns_zero(self, compute_composite):
        assert compute_composite(0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)

    def test_none_factor_excluded_from_average(self, compute_composite):
        # If quality is None (couldn't compute), remaining 3 factors should average
        score = compute_composite(momentum=1.0, quality=None, value=1.0, low_vol=1.0)
        assert score == pytest.approx(1.0), (
            "None factors should be excluded from average, not treated as 0"
        )

    def test_result_in_unit_range(self, compute_composite):
        score = compute_composite(0.6, 0.7, 0.5, 0.8)
        assert 0.0 <= score <= 1.0
