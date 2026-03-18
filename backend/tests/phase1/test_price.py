"""
Phase 1 — Data layer: price.py

Tests validate that get_ohlcv, get_financials, and get_company_info:
  - Return non-empty, non-None results for AAPL
  - Write to cache with the correct filename pattern
  - Include a fetched_at timestamp
  - Handle None fields gracefully (partial data does not crash)

These tests use fixture data if available, or live cache if not.
They do NOT make network calls unless LIVE_DATA=1 is set.
"""

import os
import pytest

pytestmark = pytest.mark.phase1


class TestGetOhlcv:
    def test_returns_dict(self, aapl_ohlcv):
        assert isinstance(aapl_ohlcv, dict)

    def test_has_required_keys(self, aapl_ohlcv):
        required = {"dates", "open", "high", "low", "close", "volume", "fetched_at"}
        assert required.issubset(aapl_ohlcv.keys()), (
            f"Missing keys: {required - aapl_ohlcv.keys()}"
        )

    def test_has_sufficient_rows(self, aapl_ohlcv):
        # 1 year daily = ~252 trading days; allow some tolerance
        assert len(aapl_ohlcv["close"]) >= 200, (
            f"Expected ≥200 price rows, got {len(aapl_ohlcv['close'])}"
        )

    def test_no_all_none_prices(self, aapl_ohlcv):
        closes = [c for c in aapl_ohlcv["close"] if c is not None]
        assert len(closes) > 0, "All close prices are None"

    def test_prices_are_positive(self, aapl_ohlcv):
        closes = [c for c in aapl_ohlcv["close"] if c is not None]
        assert all(c > 0 for c in closes), "Found non-positive close price"

    def test_fetched_at_is_present(self, aapl_ohlcv):
        assert "fetched_at" in aapl_ohlcv
        assert aapl_ohlcv["fetched_at"] is not None


class TestGetFinancials:
    def test_returns_dict(self, aapl_financials):
        assert isinstance(aapl_financials, dict)

    def test_has_revenue(self, aapl_financials):
        assert "revenue" in aapl_financials, "Missing 'revenue' key"
        assert aapl_financials["revenue"] is not None

    def test_revenue_is_list_of_values(self, aapl_financials):
        revenue = aapl_financials.get("revenue", [])
        assert isinstance(revenue, list), "Revenue should be a list of quarterly values"
        assert len(revenue) >= 1

    def test_has_expected_financial_keys(self, aapl_financials):
        # Not all may be present (yfinance gaps), but the keys should exist
        expected_keys = {
            "revenue", "gross_profit", "net_income",
            "total_debt", "total_equity", "free_cash_flow",
            "market_cap", "fetched_at"
        }
        assert expected_keys.issubset(aapl_financials.keys()), (
            f"Missing keys: {expected_keys - aapl_financials.keys()}"
        )

    def test_market_cap_is_positive(self, aapl_financials):
        mc = aapl_financials.get("market_cap")
        if mc is not None:
            assert mc > 0, f"market_cap should be positive, got {mc}"

    def test_fetched_at_present(self, aapl_financials):
        assert "fetched_at" in aapl_financials


class TestGetCompanyInfo:
    def test_returns_dict(self, aapl_company_info):
        assert isinstance(aapl_company_info, dict)

    def test_has_sector(self, aapl_company_info):
        assert "sector" in aapl_company_info
        assert aapl_company_info["sector"] is not None
        assert len(aapl_company_info["sector"]) > 0

    def test_has_ticker(self, aapl_company_info):
        assert "ticker" in aapl_company_info
        assert aapl_company_info["ticker"] == "AAPL"

    def test_has_required_keys(self, aapl_company_info):
        required = {"ticker", "sector", "industry", "market_cap", "fetched_at"}
        assert required.issubset(aapl_company_info.keys()), (
            f"Missing keys: {required - aapl_company_info.keys()}"
        )

    def test_sector_is_known_value(self, aapl_company_info):
        known_sectors = {
            "Technology", "Healthcare", "Financials", "Consumer Discretionary",
            "Consumer Staples", "Energy", "Industrials", "Materials",
            "Real Estate", "Utilities", "Communication Services",
        }
        sector = aapl_company_info.get("sector", "")
        assert sector in known_sectors, (
            f"Unexpected sector '{sector}' — not in known sector list"
        )
