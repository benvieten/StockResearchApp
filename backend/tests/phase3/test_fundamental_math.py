"""
Phase 3 — Fundamental agent: pure ratio computation unit tests.

These tests run against the ratio-computation functions directly —
no LLM calls, no network, no fixtures required.
They will fail until agents/fundamental.py exposes the compute_ratios() function.

These are the most important tests in the suite: they catch the class of bugs
where None fields from yfinance flow into ratio formulas and produce NaN or crashes.
"""

import math
import pytest

pytestmark = [pytest.mark.phase3, pytest.mark.unit]


@pytest.fixture
def compute():
    """Import the ratio computation function from the fundamental agent."""
    from backend.agents.fundamental import compute_ratios

    return compute_ratios


class TestRatioComputation:
    def test_pe_ratio_computed(self, compute, sample_financials_clean):
        ratios = compute(sample_financials_clean)
        assert "pe" in ratios
        assert ratios["pe"] == pytest.approx(sample_financials_clean["trailing_pe"])

    def test_gross_margin_computed(self, compute, sample_financials_clean):
        ratios = compute(sample_financials_clean)
        assert "gross_margin" in ratios
        # gross_profit / revenue (most recent quarter)
        expected = (
            sample_financials_clean["gross_profit"][0]
            / sample_financials_clean["revenue"][0]
        )
        assert ratios["gross_margin"] == pytest.approx(expected, rel=1e-3)

    def test_operating_margin_computed(self, compute, sample_financials_clean):
        ratios = compute(sample_financials_clean)
        assert "operating_margin" in ratios
        assert 0.0 < ratios["operating_margin"] < 1.0

    def test_net_margin_computed(self, compute, sample_financials_clean):
        ratios = compute(sample_financials_clean)
        assert "net_margin" in ratios
        assert 0.0 < ratios["net_margin"] < 1.0

    def test_debt_to_equity_computed(self, compute, sample_financials_clean):
        ratios = compute(sample_financials_clean)
        assert "debt_to_equity" in ratios
        expected = (
            sample_financials_clean["total_debt"][0]
            / sample_financials_clean["total_equity"][0]
        )
        assert ratios["debt_to_equity"] == pytest.approx(expected, rel=1e-3)

    def test_roe_computed(self, compute, sample_financials_clean):
        ratios = compute(sample_financials_clean)
        assert "roe" in ratios
        assert ratios["roe"] > 0

    def test_revenue_growth_qoq(self, compute, sample_financials_clean):
        ratios = compute(sample_financials_clean)
        assert "revenue_growth_qoq" in ratios
        # AAPL revenue[0]=400B, revenue[1]=385B: growth = (400-385)/385
        expected = (
            sample_financials_clean["revenue"][0]
            - sample_financials_clean["revenue"][1]
        ) / sample_financials_clean["revenue"][1]
        assert ratios["revenue_growth_qoq"] == pytest.approx(expected, rel=1e-3)

    def test_fcf_yield_computed(self, compute, sample_financials_clean):
        ratios = compute(sample_financials_clean)
        assert "fcf_yield" in ratios
        expected = (
            sample_financials_clean["free_cash_flow"][0]
            / sample_financials_clean["market_cap"]
        )
        assert ratios["fcf_yield"] == pytest.approx(expected, rel=1e-3)


class TestRatioComputationWithNulls:
    """
    These tests verify that None fields from yfinance don't crash ratio computation.
    Each test checks a specific field that yfinance commonly returns as None.
    """

    def test_none_pe_does_not_crash(self, compute, sample_financials_partial):
        ratios = compute(sample_financials_partial)
        # pe should be None or absent — not a crash
        pe = ratios.get("pe")
        assert pe is None or (isinstance(pe, float) and not math.isnan(pe))

    def test_none_ebitda_skips_ev_ebitda(self, compute, sample_financials_partial):
        ratios = compute(sample_financials_partial)
        # EV/EBITDA cannot be computed without EBITDA — should be None
        assert ratios.get("ev_ebitda") is None

    def test_none_gross_profit_skips_gross_margin(
        self, compute, sample_financials_partial
    ):
        ratios = compute(sample_financials_partial)
        gm = ratios.get("gross_margin")
        # With None gross_profit, gross_margin must be None (not NaN, not crash)
        assert gm is None or (isinstance(gm, float) and not math.isnan(gm))

    def test_no_nan_values_in_output(self, compute, sample_financials_partial):
        ratios = compute(sample_financials_partial)
        for key, val in ratios.items():
            if isinstance(val, float):
                assert not math.isnan(val), f"NaN found in ratios['{key}']"

    def test_data_quality_partial_when_fields_missing(
        self, compute, sample_financials_partial
    ):
        ratios = compute(sample_financials_partial)
        assert (
            ratios.get("data_quality") == "partial"
        ), "compute_ratios() must set data_quality='partial' when any input field is None"

    def test_data_quality_full_when_complete(self, compute, sample_financials_clean):
        ratios = compute(sample_financials_clean)
        assert ratios.get("data_quality") == "full"


class TestPiotroskiFScore:
    """
    Piotroski F-Score: 9 binary signals, sum 0-9.
    Returns None if fewer than 5 signals are computable.
    """

    def test_high_quality_company_scores_high(self, compute):
        """A profitable, low-debt, growing company should score >= 6."""
        financials = {
            "revenue": [100_000_000, 85_000_000, 80_000_000, 75_000_000],
            "gross_profit": [60_000_000, 50_000_000, 48_000_000, 44_000_000],
            "operating_income": [30_000_000, 24_000_000, 22_000_000, 20_000_000],
            "net_income": [20_000_000, 15_000_000, 14_000_000, 12_000_000],
            "ebitda": [35_000_000, 28_000_000],
            "total_debt": [10_000_000, 15_000_000],  # F5: leverage falling ✓
            "total_equity": [80_000_000, 70_000_000],
            "total_assets": [100_000_000, 95_000_000],
            "current_assets": [60_000_000, 50_000_000],  # F6: current ratio improving ✓
            "current_liabilities": [20_000_000, 20_000_000],
            "free_cash_flow": [25_000_000, 18_000_000],
            "operating_cash_flow": [28_000_000, 20_000_000],
            "market_cap": 500_000_000,
            "enterprise_value": 510_000_000,
            "price": 50.0,
            "trailing_pe": 25.0,
            "book_value_per_share": 8.0,
            "shares_outstanding": 10_000_000,
        }
        ratios = compute(financials)
        score = ratios.get("piotroski_score")
        assert score is not None, "Piotroski score should be computable with full data"
        assert score >= 6, f"High-quality company should score >= 6, got {score}"

    def test_distressed_company_scores_low(self, compute):
        """A loss-making, high-debt, declining company should score <= 3."""
        financials = {
            "revenue": [50_000_000, 70_000_000, 75_000_000, 80_000_000],  # declining
            "gross_profit": [10_000_000, 20_000_000, 22_000_000, 25_000_000],
            "operating_income": [-5_000_000, -3_000_000, -2_000_000, -1_000_000],
            "net_income": [
                -10_000_000,
                -8_000_000,
                -7_000_000,
                -5_000_000,
            ],  # F1: negative ROA ✗
            "ebitda": [-2_000_000, 1_000_000],
            "total_debt": [90_000_000, 70_000_000],  # F5: leverage rising ✗
            "total_equity": [20_000_000, 30_000_000],
            "total_assets": [120_000_000, 110_000_000],
            "current_assets": [15_000_000, 20_000_000],  # F6: current ratio falling ✗
            "current_liabilities": [25_000_000, 30_000_000],
            "free_cash_flow": [-8_000_000, -5_000_000],
            "operating_cash_flow": [-7_000_000, -4_000_000],  # F2: negative OCF ✗
            "market_cap": 30_000_000,
            "enterprise_value": 120_000_000,
            "price": 3.0,
            "trailing_pe": None,
            "book_value_per_share": 2.0,
            "shares_outstanding": 10_000_000,
        }
        ratios = compute(financials)
        score = ratios.get("piotroski_score")
        assert (
            score is not None
        ), "Piotroski score should be computable even for distressed company"
        assert score <= 3, f"Distressed company should score <= 3, got {score}"

    def test_returns_none_when_insufficient_signals(self, compute):
        """Fewer than 5 computable signals → score must be None, not a low int."""
        financials = {
            "revenue": [100_000_000],  # only 1 period — most Piotroski fields need 2
            "gross_profit": [None],
            "operating_income": [None],
            "net_income": [None],
            "ebitda": None,
            "total_debt": None,
            "total_equity": None,
            "total_assets": None,
            "current_assets": None,
            "current_liabilities": None,
            "free_cash_flow": None,
            "operating_cash_flow": None,
            "market_cap": None,
            "enterprise_value": None,
            "price": 5.0,
            "trailing_pe": None,
            "book_value_per_share": None,
            "shares_outstanding": None,
        }
        ratios = compute(financials)
        score = ratios.get("piotroski_score")
        assert (
            score is None
        ), f"Piotroski score must be None when < 5 signals computable, got {score}"

    def test_score_in_valid_range(self, compute, sample_financials_clean):
        ratios = compute(sample_financials_clean)
        score = ratios.get("piotroski_score")
        if score is not None:
            assert 0 <= score <= 9, f"Piotroski score must be 0-9, got {score}"

    def test_accruals_ratio_negative_means_high_quality(self, compute):
        """
        Negative accruals ratio = OCF > Net Income = earnings are cash-backed = GOOD.
        This is the sign-interpretation bug caught on PL.
        """
        financials = {
            "revenue": [100_000_000, 90_000_000],
            "gross_profit": [60_000_000, 55_000_000],
            "operating_income": [30_000_000, 27_000_000],
            "net_income": [
                10_000_000,
                8_000_000,
            ],  # net income < OCF → negative accruals
            "ebitda": [35_000_000, 30_000_000],
            "total_debt": [20_000_000, 25_000_000],
            "total_equity": [70_000_000, 65_000_000],
            "total_assets": [100_000_000, 95_000_000],
            "current_assets": [50_000_000, 45_000_000],
            "current_liabilities": [15_000_000, 14_000_000],
            "free_cash_flow": [20_000_000, 15_000_000],
            "operating_cash_flow": [25_000_000, 18_000_000],  # OCF > net income
            "market_cap": 300_000_000,
            "enterprise_value": 310_000_000,
            "price": 30.0,
            "trailing_pe": 30.0,
            "book_value_per_share": 7.0,
            "shares_outstanding": 10_000_000,
        }
        ratios = compute(financials)
        accruals = ratios.get("accruals_ratio")
        assert accruals is not None
        assert (
            accruals < 0
        ), "When OCF > Net Income, accruals_ratio must be negative (high earnings quality)"


class TestOllamaStringCoercion:
    """
    Covers the PL bug: Ollama echoes '(not available)' as a string in metrics dict.
    The _call_llm function must coerce these to None before Pydantic validation.
    """

    def test_string_metrics_coerced_to_none(self):
        """Simulate the exact data shape returned by Ollama with string values."""
        from backend.core.data_models import FundamentalSignal

        raw_data = {
            "reasoning": "PL shows strong revenue growth but negative margins.",
            "quality_score": 0.3,
            "valuation_verdict": "overvalued",
            "key_flags": ["high revenue growth", "negative margins"],
            "metrics": {
                "pe_ratio": "(not available)",  # Ollama echoing our prompt text
                "ps_ratio": 40.36,
                "gross_margin": 0.56,
                "debt_to_equity": "(not available)",  # another string
                "net_margin": -0.80,
            },
            "data_quality": "partial",
        }
        # Apply the same coercion logic as _call_llm
        raw_data["metrics"] = {
            k: (None if isinstance(v, str) else v)
            for k, v in raw_data["metrics"].items()
        }
        signal = FundamentalSignal.model_validate(raw_data)
        assert signal.metrics["pe_ratio"] is None
        assert signal.metrics["debt_to_equity"] is None
        assert signal.metrics["ps_ratio"] == pytest.approx(40.36)

    def test_na_string_coerced_to_none(self):
        """Ollama might also return 'N/A' (old format before the prompt fix)."""
        from backend.core.data_models import FundamentalSignal

        raw_data = {
            "reasoning": "Analysis complete.",
            "quality_score": 0.5,
            "valuation_verdict": "fair",
            "key_flags": ["mixed signals"],
            "metrics": {"pe_ratio": "N/A", "ps_ratio": 20.0},
            "data_quality": "partial",
        }
        raw_data["metrics"] = {
            k: (None if isinstance(v, str) else v)
            for k, v in raw_data["metrics"].items()
        }
        signal = FundamentalSignal.model_validate(raw_data)
        assert signal.metrics["pe_ratio"] is None
