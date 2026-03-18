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
            sample_financials_clean["revenue"][0] - sample_financials_clean["revenue"][1]
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

    def test_none_gross_profit_skips_gross_margin(self, compute, sample_financials_partial):
        ratios = compute(sample_financials_partial)
        gm = ratios.get("gross_margin")
        # With None gross_profit, gross_margin must be None (not NaN, not crash)
        assert gm is None or (isinstance(gm, float) and not math.isnan(gm))

    def test_no_nan_values_in_output(self, compute, sample_financials_partial):
        ratios = compute(sample_financials_partial)
        for key, val in ratios.items():
            if isinstance(val, float):
                assert not math.isnan(val), f"NaN found in ratios['{key}']"

    def test_data_quality_partial_when_fields_missing(self, compute, sample_financials_partial):
        ratios = compute(sample_financials_partial)
        assert ratios.get("data_quality") == "partial", (
            "compute_ratios() must set data_quality='partial' when any input field is None"
        )

    def test_data_quality_full_when_complete(self, compute, sample_financials_clean):
        ratios = compute(sample_financials_clean)
        assert ratios.get("data_quality") == "full"
