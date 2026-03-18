"""
Phase 3 — Technical agent: indicator computation unit tests.

Tests run against the compute_indicators() function directly using a synthetic
OHLCV DataFrame — no LLM calls, no network, no cache required.

Will fail until agents/technical.py exposes compute_indicators().
"""

import pytest

pytestmark = [pytest.mark.phase3, pytest.mark.unit]


@pytest.fixture
def compute():
    from backend.agents.technical import compute_indicators
    return compute_indicators


@pytest.fixture
def indicators(compute, sample_ohlcv_df):
    return compute(sample_ohlcv_df)


class TestIndicatorKeys:
    REQUIRED_KEYS = {
        "ema_20", "ema_50", "ema_200",
        "rsi_14",
        "macd", "macd_signal", "macd_hist",
        "bb_upper", "bb_lower", "bb_mid",
        "atr_14",
        "obv",
        "support", "resistance",
    }

    def test_all_required_keys_present(self, indicators):
        missing = self.REQUIRED_KEYS - indicators.keys()
        assert not missing, f"Missing indicator keys: {missing}"


class TestEmaValues:
    def test_ema_20_is_float(self, indicators):
        assert isinstance(indicators["ema_20"], float)

    def test_ema_50_is_float(self, indicators):
        assert isinstance(indicators["ema_50"], float)

    def test_ema_200_is_float(self, indicators):
        assert isinstance(indicators["ema_200"], float)

    def test_ema_values_are_positive(self, indicators):
        for key in ["ema_20", "ema_50", "ema_200"]:
            assert indicators[key] > 0, f"{key} should be positive"

    def test_ema_ordering_roughly_correct(self, indicators, sample_ohlcv_df):
        """
        For a trending dataset, shorter EMAs should be closer to current price.
        This is a sanity check, not a strict ordering rule.
        """
        current_price = sample_ohlcv_df["Close"].iloc[-1]
        ema_20_dist = abs(indicators["ema_20"] - current_price)
        ema_200_dist = abs(indicators["ema_200"] - current_price)
        # EMA 20 should generally be closer to current price than EMA 200
        # (not always true in all market conditions, but true for our synthetic data)
        assert ema_20_dist <= ema_200_dist * 3, (
            "EMA 20 is suspiciously far from current price vs EMA 200"
        )


class TestRsi:
    def test_rsi_in_valid_range(self, indicators):
        assert 0.0 <= indicators["rsi_14"] <= 100.0, (
            f"RSI must be 0-100, got {indicators['rsi_14']}"
        )

    def test_rsi_is_float(self, indicators):
        assert isinstance(indicators["rsi_14"], float)


class TestBollingerBands:
    def test_upper_above_lower(self, indicators):
        assert indicators["bb_upper"] > indicators["bb_lower"], (
            "Bollinger upper band must be above lower band"
        )

    def test_mid_between_bands(self, indicators):
        assert indicators["bb_lower"] <= indicators["bb_mid"] <= indicators["bb_upper"], (
            "Bollinger mid band must be between upper and lower"
        )


class TestSupportResistance:
    def test_support_is_positive(self, indicators):
        assert indicators["support"] > 0

    def test_resistance_is_positive(self, indicators):
        assert indicators["resistance"] > 0

    def test_resistance_above_support(self, indicators):
        assert indicators["resistance"] >= indicators["support"], (
            "Resistance must be >= support"
        )


class TestAtr:
    def test_atr_is_positive(self, indicators):
        assert indicators["atr_14"] > 0, "ATR must be positive"


class TestObv:
    def test_obv_is_numeric(self, indicators):
        assert isinstance(indicators["obv"], (int, float))
