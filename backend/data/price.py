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

# Serialise all yfinance network calls to prevent concurrent session/crumb races.
# yfinance 1.x creates a new session per Ticker; concurrent sessions race to
# fetch a crumb and invalidate each other → HTTP 401 "Invalid Crumb".
_yf_sem = asyncio.Semaphore(1)


# ── Public async API ───────────────────────────────────────────────────────────


async def get_ohlcv(ticker: str) -> dict:
    """Return 1-year daily OHLCV for ticker, served from cache when possible."""
    cached = load_cache(ticker, "ohlcv")
    if cached is not None:
        return cached

    log.info("fetching_ohlcv", ticker=ticker)
    async with _yf_sem:
        data = await asyncio.to_thread(_fetch_ohlcv, ticker)
    save_cache(ticker, "ohlcv", data)
    return data


async def get_financials(ticker: str) -> dict:
    """Return key financial statement fields for ticker."""
    cached = load_cache(ticker, "financials")
    if cached is not None:
        return cached

    log.info("fetching_financials", ticker=ticker)
    async with _yf_sem:
        data = await asyncio.to_thread(_fetch_financials, ticker)
    save_cache(ticker, "financials", data)
    return data


async def get_company_info(ticker: str) -> dict:
    """Return sector, industry, and other static company metadata."""
    cached = load_cache(ticker, "company_info")
    if cached is not None:
        return cached

    log.info("fetching_company_info", ticker=ticker)
    async with _yf_sem:
        data = await asyncio.to_thread(_fetch_company_info, ticker)
    save_cache(ticker, "company_info", data)
    return data


async def get_short_interest(ticker: str) -> dict:
    """Return short interest metrics from yfinance (already in t.info — no extra network call)."""
    cached = load_cache(ticker, "short_interest")
    if cached is not None:
        return cached

    log.info("fetching_short_interest", ticker=ticker)
    async with _yf_sem:
        data = await asyncio.to_thread(_fetch_short_interest, ticker)
    save_cache(ticker, "short_interest", data)
    return data


async def get_analyst_data(ticker: str) -> dict:
    """Return Wall Street analyst price targets and consensus recommendation."""
    cached = load_cache(ticker, "analyst")
    if cached is not None:
        return cached

    log.info("fetching_analyst_data", ticker=ticker)
    async with _yf_sem:
        data = await asyncio.to_thread(_fetch_analyst_data, ticker)
    save_cache(ticker, "analyst", data)
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
        total_assets = _row_values(bs, "Total Assets")
        current_assets = _row_values(bs, "Current Assets")
        current_liabilities = _row_values(bs, "Current Liabilities")
    else:
        total_debt = total_equity = total_assets = None
        current_assets = current_liabilities = None

    # Cash flow
    cf = t.cashflow
    if cf is not None and not cf.empty:
        cf = cf.sort_index(axis=1, ascending=False)
        free_cash_flow = _row_values(cf, "Free Cash Flow")
        operating_cash_flow = _row_values(cf, "Operating Cash Flow")
    else:
        free_cash_flow = None
        operating_cash_flow = None

    return {
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_income": operating_income,
        "net_income": net_income,
        "ebitda": ebitda,
        "total_debt": total_debt,
        "total_equity": total_equity,
        "total_assets": total_assets,
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
        "free_cash_flow": free_cash_flow,
        "operating_cash_flow": operating_cash_flow,
        "market_cap": info.get("marketCap"),
        "enterprise_value": info.get("enterpriseValue"),
        "shares_outstanding": info.get("sharesOutstanding"),
        "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "trailing_pe": info.get("trailingPE"),
        "book_value_per_share": info.get("bookValue"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _fetch_short_interest(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info: dict = t.info or {}

    shares_short = info.get("sharesShort")
    short_float = info.get("shortPercentOfFloat")
    short_ratio = info.get("shortRatio")  # days-to-cover
    shares_outstanding = info.get("sharesOutstanding")

    # Compute short % of float as decimal if yfinance returns it as a fraction vs percent
    # yfinance returns shortPercentOfFloat as a decimal (e.g. 0.065 = 6.5%)
    short_float_pct = _float_or_none(short_float)

    return {
        "shares_short": int(shares_short) if shares_short else None,
        "short_percent_of_float": short_float_pct,
        "short_ratio": _float_or_none(short_ratio),
        "shares_outstanding": int(shares_outstanding) if shares_outstanding else None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _fetch_analyst_data(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info: dict = t.info or {}

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    target_mean = info.get("targetMeanPrice")
    target_high = info.get("targetHighPrice")
    target_low = info.get("targetLowPrice")
    target_median = info.get("targetMedianPrice")
    num_analysts = info.get("numberOfAnalystOpinions")
    recommendation_mean = info.get("recommendationMean")
    recommendation_key = info.get("recommendationKey")

    upside = None
    price_f = _float_or_none(price)
    target_mean_f = _float_or_none(target_mean)
    if price_f and target_mean_f and price_f > 0:
        upside = (target_mean_f - price_f) / price_f

    return {
        "current_price": price_f,
        "target_mean": target_mean_f,
        "target_high": _float_or_none(target_high),
        "target_low": _float_or_none(target_low),
        "target_median": _float_or_none(target_median),
        "num_analysts": int(num_analysts) if num_analysts else None,
        "recommendation_mean": _float_or_none(recommendation_mean),
        "recommendation_key": recommendation_key,
        "upside_to_mean": upside,
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
