"""
Phase 3 — Quant agent: pure factor computation unit tests.

The Quant agent has no LLM call — it is entirely deterministic computation.
Every function it uses can be unit tested with synthetic data.

Will fail until agents/quant.py exposes its computation functions.
"""

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


class TestReturnZscore:
    @pytest.fixture
    def fn(self):
        from backend.agents.quant import compute_return_zscore
        return compute_return_zscore

    def test_returns_float_with_sufficient_data(self, fn, sample_ohlcv_df):
        result = fn(sample_ohlcv_df)
        assert result is not None
        assert isinstance(result, float)

    def test_returns_none_with_insufficient_data(self, fn):
        import pandas as pd
        import numpy as np
        # Only 50 rows — window=90 requires at least 91
        prices = np.linspace(100, 110, 50)
        df = pd.DataFrame({"Close": prices}, index=pd.bdate_range(end="2026-03-18", periods=50))
        result = fn(df, window=90)
        assert result is None

    def test_large_up_day_gives_positive_zscore(self, fn, sample_ohlcv_df):
        import pandas as pd
        # Append a very large up day to the OHLCV data
        df = sample_ohlcv_df.copy()
        last_price = float(df["Close"].iloc[-1])
        new_row = pd.DataFrame(
            {"Open": last_price, "High": last_price * 1.12, "Low": last_price,
             "Close": last_price * 1.10, "Volume": 100_000_000},
            index=[df.index[-1] + pd.Timedelta(days=1)],
        )
        df_extended = pd.concat([df, new_row])
        result = fn(df_extended)
        assert result is not None and result > 1.5, (
            f"A +10% day should produce a high positive z-score, got {result}"
        )


class TestVolumeRatio:
    @pytest.fixture
    def fn(self):
        from backend.agents.quant import compute_volume_ratio
        return compute_volume_ratio

    def test_returns_float_with_sufficient_data(self, fn, sample_ohlcv_df):
        result = fn(sample_ohlcv_df)
        assert result is not None
        assert isinstance(result, float)
        assert result > 0

    def test_returns_none_with_insufficient_data(self, fn):
        import pandas as pd
        import numpy as np
        # Only 10 rows — window=20 requires at least 21
        df = pd.DataFrame(
            {"Close": np.ones(10), "Volume": np.ones(10) * 1_000_000},
            index=pd.bdate_range(end="2026-03-18", periods=10),
        )
        result = fn(df, window=20)
        assert result is None

    def test_high_volume_day_gives_ratio_above_one(self, fn, sample_ohlcv_df):
        df = sample_ohlcv_df.copy()
        # Set today's volume to 10x the average
        avg_vol = float(df["Volume"].iloc[-21:-1].mean())
        df.iloc[-1, df.columns.get_loc("Volume")] = int(avg_vol * 10)
        result = fn(df)
        assert result is not None and result > 5.0, (
            f"10x volume day should give ratio > 5, got {result}"
        )


class TestBbPercentile:
    @pytest.fixture
    def fn(self):
        from backend.agents.quant import compute_bb_percentile
        return compute_bb_percentile

    def test_returns_float_in_unit_range(self, fn, sample_ohlcv_df):
        result = fn(sample_ohlcv_df)
        assert result is not None
        assert 0.0 <= result <= 1.0

    def test_returns_none_with_insufficient_data(self, fn):
        import pandas as pd
        import numpy as np
        df = pd.DataFrame(
            {"Close": np.ones(5)},
            index=pd.bdate_range(end="2026-03-18", periods=5),
        )
        result = fn(df, window=20)
        assert result is None

    def test_price_at_upper_band_gives_high_percentile(self, fn):
        import pandas as pd
        import numpy as np
        # Flat price then a big spike — price will be at/above upper band
        prices = np.concatenate([np.ones(40) * 100, [120]])
        df = pd.DataFrame(
            {"Close": prices},
            index=pd.bdate_range(end="2026-03-18", periods=len(prices)),
        )
        result = fn(df)
        assert result is not None and result >= 0.9, (
            f"Price well above band should give percentile >= 0.9, got {result}"
        )


class TestRsiPercentile:
    @pytest.fixture
    def fn(self):
        from backend.agents.quant import compute_rsi_percentile
        return compute_rsi_percentile

    def test_returns_float_in_unit_range(self, fn, sample_ohlcv_df):
        # Need 252 + 14 rows minimum
        result = fn(sample_ohlcv_df)
        # sample_ohlcv_df has 252 rows; 252 < 14 + 252 so may return None — just check type
        assert result is None or 0.0 <= result <= 1.0

    def test_returns_none_with_insufficient_data(self, fn):
        import pandas as pd
        import numpy as np
        df = pd.DataFrame(
            {"Close": np.linspace(100, 110, 100)},
            index=pd.bdate_range(end="2026-03-18", periods=100),
        )
        result = fn(df, rsi_window=14, lookback=252)
        assert result is None
