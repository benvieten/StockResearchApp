"""
Data module: price.py

Fetches OHLCV data, financial statements, and company info from yfinance.
All three functions check the local cache before hitting the network.

Usage:
    python -m backend.data.price AAPL
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import structlog
import yfinance as yf

from backend.data._cache import load_cache, save_cache

log = structlog.get_logger()


# ── Public async API ───────────────────────────────────────────────────────────


async def get_ohlcv(ticker: str) -> dict:
    """Return 1-year daily OHLCV for ticker, served from cache when possible."""
    cached = load_cache(ticker, "ohlcv")
    if cached is not None:
        return cached

    log.info("fetching_ohlcv", ticker=ticker)
    data = await asyncio.to_thread(_fetch_ohlcv, ticker)
    save_cache(ticker, "ohlcv", data)
    return data


async def get_financials(ticker: str) -> dict:
    """Return key financial statement fields for ticker."""
    cached = load_cache(ticker, "financials")
    if cached is not None:
        return cached

    log.info("fetching_financials", ticker=ticker)
    data = await asyncio.to_thread(_fetch_financials, ticker)
    save_cache(ticker, "financials", data)
    return data


async def get_company_info(ticker: str) -> dict:
    """Return sector, industry, and other static company metadata."""
    cached = load_cache(ticker, "company_info")
    if cached is not None:
        return cached

    log.info("fetching_company_info", ticker=ticker)
    data = await asyncio.to_thread(_fetch_company_info, ticker)
    save_cache(ticker, "company_info", data)
    return data


# ── Sync fetch helpers (run in thread pool via asyncio.to_thread) ──────────────


def _fetch_ohlcv(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    hist = t.history(period="2y", interval="1d", auto_adjust=True)
    if hist.empty:
        raise ValueError(f"yfinance returned empty OHLCV for {ticker}")

    return {
        "dates": [str(d.date()) for d in hist.index],
        "open": [_float_or_none(v) for v in hist["Open"]],
        "high": [_float_or_none(v) for v in hist["High"]],
        "low": [_float_or_none(v) for v in hist["Low"]],
        "close": [_float_or_none(v) for v in hist["Close"]],
        "volume": [_int_or_none(v) for v in hist["Volume"]],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _fetch_financials(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info: dict = t.info or {}

    # Income statement — columns are dates; sort descending (most-recent first)
    income = t.financials
    if income is not None and not income.empty:
        income = income.sort_index(axis=1, ascending=False)
        revenue = _row_values(income, "Total Revenue")
        gross_profit = _row_values(income, "Gross Profit")
        operating_income = _row_values(income, "Operating Income")
        net_income = _row_values(income, "Net Income")
        ebitda = _row_values(income, "EBITDA")
    else:
        revenue = gross_profit = operating_income = net_income = ebitda = None

    # Balance sheet
    bs = t.balance_sheet
    if bs is not None and not bs.empty:
        bs = bs.sort_index(axis=1, ascending=False)
        total_debt = _row_values(bs, "Total Debt")
        total_equity = _row_values(bs, "Stockholders Equity")
    else:
        total_debt = total_equity = None

    # Cash flow
    cf = t.cashflow
    if cf is not None and not cf.empty:
        cf = cf.sort_index(axis=1, ascending=False)
        free_cash_flow = _row_values(cf, "Free Cash Flow")
    else:
        free_cash_flow = None

    return {
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_income": operating_income,
        "net_income": net_income,
        "ebitda": ebitda,
        "total_debt": total_debt,
        "total_equity": total_equity,
        "free_cash_flow": free_cash_flow,
        "market_cap": info.get("marketCap"),
        "enterprise_value": info.get("enterpriseValue"),
        "shares_outstanding": info.get("sharesOutstanding"),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "trailing_pe": info.get("trailingPE"),
        "book_value_per_share": info.get("bookValue"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _fetch_company_info(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info: dict = t.info or {}
    return {
        "ticker": ticker,
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": info.get("marketCap"),
        "employees": info.get("fullTimeEmployees"),
        "country": info.get("country"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Helpers ────────────────────────────────────────────────────────────────────


def _float_or_none(v: Any) -> float | None:
    if pd.isna(v):
        return None
    return float(v)


def _int_or_none(v: Any) -> int | None:
    if pd.isna(v):
        return None
    return int(v)


def _row_values(df: pd.DataFrame, row_name: str) -> list[float | None] | None:
    """Extract a named row from a yfinance financial DataFrame as a list."""
    if row_name not in df.index:
        return None
    return [_float_or_none(v) for v in df.loc[row_name]]


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import json

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        ohlcv = await get_ohlcv(ticker)
        financials = await get_financials(ticker)
        company_info = await get_company_info(ticker)
        print(
            json.dumps(
                {
                    "ohlcv_rows": len(ohlcv.get("close", [])),
                    "financials": financials,
                    "company_info": company_info,
                },
                indent=2,
                default=str,
            )
        )

    asyncio.run(main())
