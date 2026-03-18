"""
Quant agent — no LLM call. Pure factor computation.

Factors: momentum, quality, value, low_volatility.
Composite = equal-weighted average of available factors.

Usage:
    python -m backend.agents.quant AAPL
"""

from __future__ import annotations

import asyncio
import math
import sys

import pandas as pd
import structlog

from backend.core.config import get_config
from backend.core.data_models import QuantSignal
from backend.data.price import get_financials, get_ohlcv

log = structlog.get_logger()


# ── Factor computation functions (unit-tested independently) ───────────────────


def compute_momentum_score(
    ticker_returns: dict[str, float],
    spy_returns: dict[str, float],
) -> float:
    """
    Score momentum vs SPY across all available time windows.

    Uses a sigmoid on excess return so that:
    - Large outperformance → score near 1.0
    - Equal performance   → score near 0.5
    - Large underperformance → score near 0.0
    """
    scores = []
    for period in ticker_returns:
        tr = ticker_returns.get(period)
        sr = spy_returns.get(period)
        if tr is None or sr is None:
            continue
        excess = tr - sr
        # sigmoid with scale factor of 10 to map ±20% excess to ≈ [0.12, 0.88]
        period_score = 1.0 / (1.0 + math.exp(-excess * 10))
        scores.append(period_score)
    return sum(scores) / len(scores) if scores else 0.5


def compute_quality_score(
    roe: float | None,
    debt_to_equity: float | None,
) -> float | None:
    """
    Score quality from ROE and inverse debt-to-equity.

    Returns None only if both inputs are None.
    High ROE + low D/E → score near 1.0.
    """
    sub_scores = []

    if roe is not None:
        # Normalize ROE: cap at 50%, floor at 0%
        roe_score = min(max(roe, 0.0), 0.5) / 0.5
        sub_scores.append(roe_score)

    if debt_to_equity is not None:
        # Normalize D/E: 0 → 1.0, 5+ → 0.0
        de_score = max(0.0, 1.0 - debt_to_equity / 5.0)
        sub_scores.append(de_score)

    if not sub_scores:
        return None
    return sum(sub_scores) / len(sub_scores)


def compute_value_score(pe: float | None) -> float | None:
    """
    Score value via earnings yield (1/PE), normalized to [0%, 15%] range.

    Negative PE (loss-making company) → None.
    Very high PE → score near 0.0.
    Very low PE → score near 1.0.
    """
    cfg = get_config()
    ey_min = cfg.quant.earnings_yield_min   # 0.0
    ey_max = cfg.quant.earnings_yield_max   # 0.15

    if pe is None or pe <= 0:
        return None

    earnings_yield = 1.0 / pe
    score = (earnings_yield - ey_min) / (ey_max - ey_min)
    return max(0.0, min(1.0, score))


def compute_low_vol_score(df: pd.DataFrame) -> float:
    """
    Score low-volatility factor.

    Annualizes 90-day realized vol, then maps:
    0% annualized vol → 1.0, 50%+ annualized vol → 0.0.
    """
    cfg = get_config()
    window = cfg.quant.volatility_window_days

    returns = df["Close"].pct_change().dropna()
    sample = returns.iloc[-window:] if len(returns) >= window else returns
    daily_vol = float(sample.std())
    annual_vol = daily_vol * (252 ** 0.5)

    vol_max = 0.50
    score = max(0.0, min(1.0, 1.0 - annual_vol / vol_max))
    return score


def compute_composite_score(
    momentum: float | None,
    quality: float | None,
    value: float | None,
    low_vol: float | None,
) -> float:
    """
    Equal-weighted average of available factor scores.
    None factors are excluded (not treated as 0).
    """
    factors = [f for f in [momentum, quality, value, low_vol] if f is not None]
    if not factors:
        return 0.5
    return sum(factors) / len(factors)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _ohlcv_to_df(ohlcv: dict) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": ohlcv["open"],
            "High": ohlcv["high"],
            "Low": ohlcv["low"],
            "Close": ohlcv["close"],
            "Volume": ohlcv["volume"],
        },
        index=pd.to_datetime(ohlcv["dates"]),
    ).dropna()


def _compute_period_returns(df: pd.DataFrame) -> dict[str, float]:
    """Compute 3M / 6M / 12M returns from a Close price series."""
    cfg = get_config()
    windows = cfg.quant.momentum_windows_months  # [3, 6, 12]
    last_price = float(df["Close"].iloc[-1])
    returns = {}
    trading_days_per_month = 21
    for months in windows:
        lookback = months * trading_days_per_month
        if len(df) > lookback:
            past_price = float(df["Close"].iloc[-lookback - 1])
            if past_price and past_price > 0:
                returns[f"{months}m"] = (last_price - past_price) / past_price
    return returns


# ── Public async entry point ───────────────────────────────────────────────────


async def run(ticker: str) -> QuantSignal:
    log.info("quant_agent_start", ticker=ticker)

    ohlcv_task = asyncio.create_task(get_ohlcv(ticker))
    spy_task = asyncio.create_task(get_ohlcv("SPY"))
    financials_task = asyncio.create_task(get_financials(ticker))

    ohlcv, spy_ohlcv, financials = await asyncio.gather(
        ohlcv_task, spy_task, financials_task
    )

    df = _ohlcv_to_df(ohlcv)
    spy_df = _ohlcv_to_df(spy_ohlcv)

    # Import here to avoid circular dependency at module load time
    from backend.agents.fundamental import compute_ratios

    ratios = compute_ratios(financials)
    data_quality = ratios.get("data_quality", "full")

    ticker_returns = _compute_period_returns(df)
    spy_returns = _compute_period_returns(spy_df)

    momentum = compute_momentum_score(ticker_returns, spy_returns) if ticker_returns else None
    quality = compute_quality_score(ratios.get("roe"), ratios.get("debt_to_equity"))
    value = compute_value_score(ratios.get("pe"))
    low_vol = compute_low_vol_score(df)
    composite = compute_composite_score(momentum, quality, value, low_vol)

    signal = QuantSignal(
        composite_score=composite,
        factor_breakdown={
            "momentum": momentum,
            "quality": quality,
            "value": value,
            "low_vol": low_vol,
        },
        data_quality=data_quality,
    )
    log.info("quant_agent_done", ticker=ticker, composite=composite)
    return signal


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        signal = await run(ticker)
        print(signal.model_dump_json(indent=2))

    asyncio.run(main())
