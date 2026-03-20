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
import pandas_ta as ta
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


def compute_value_score(
    pe: float | None,
    ey_min: float,
    ey_max: float,
) -> float | None:
    """
    Score value via earnings yield (1/PE), normalized to [ey_min, ey_max] range.

    Negative PE (loss-making company) → None.
    Very high PE → score near 0.0.
    Very low PE → score near 1.0.
    """
    if pe is None or pe <= 0:
        return None

    earnings_yield = 1.0 / pe
    score = (earnings_yield - ey_min) / (ey_max - ey_min)
    return max(0.0, min(1.0, score))


def compute_low_vol_score(df: pd.DataFrame, window: int) -> float:
    """
    Score low-volatility factor.

    Annualizes realized vol over `window` trading days, then maps:
    0% annualized vol → 1.0, 50%+ annualized vol → 0.0.
    """
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


# ── Statistical anomaly + mean-reversion metrics ───────────────────────────────


def compute_return_zscore(df: pd.DataFrame, window: int = 90) -> float | None:
    """
    Z-score of today's 1-day return vs the trailing 90-day return distribution.

    Interpretation:
    >  2.0  — unusually large up move (potential exhaustion / mean-reversion risk)
    < -2.0  — unusually large down move (potential oversold bounce)
    near 0  — today's move is statistically normal
    """
    returns = df["Close"].pct_change().dropna()
    if len(returns) < window + 1:
        return None
    sample = returns.iloc[-window:]
    today = float(returns.iloc[-1])
    mean = float(sample.mean())
    std = float(sample.std())
    if std == 0:
        return None
    return round((today - mean) / std, 4)


def compute_volume_ratio(df: pd.DataFrame, window: int = 20) -> float | None:
    """
    Today's volume divided by the trailing 20-day average volume.

    > 2.0 — high volume (confirms price move)
    < 0.5 — low volume (weak conviction behind the move)
    ~1.0  — normal activity
    """
    if "Volume" not in df.columns:
        return None
    vol = df["Volume"].dropna()
    if len(vol) < window + 1:
        return None
    avg = float(vol.iloc[-(window + 1):-1].mean())
    today = float(vol.iloc[-1])
    if avg == 0:
        return None
    return round(today / avg, 4)


def compute_bb_percentile(df: pd.DataFrame, window: int = 20) -> float | None:
    """
    Bollinger %B — where price sits within its 20-day Bollinger Band.

    0.0 = price at lower band (statistically cheap / oversold)
    0.5 = price at midline (mean)
    1.0 = price at upper band (statistically extended / overbought)

    Values outside [0, 1] are clamped — they indicate a breakout.
    """
    if len(df) < window:
        return None
    close = df["Close"]
    ma = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = ma + 2 * std
    lower = ma - 2 * std
    band_width = float(upper.iloc[-1]) - float(lower.iloc[-1])
    if band_width == 0:
        return None
    pct_b = (float(close.iloc[-1]) - float(lower.iloc[-1])) / band_width
    return round(max(0.0, min(1.0, pct_b)), 4)


def compute_rsi_percentile(df: pd.DataFrame, rsi_window: int = 14, lookback: int = 252) -> float | None:
    """
    RSI percentile rank — where today's RSI(14) sits within its own 252-day history.

    0.0 = RSI is at its yearly low (historically oversold)
    1.0 = RSI is at its yearly high (historically overbought)

    More stable than raw RSI because it accounts for the stock's own momentum
    character — a growth stock naturally runs hotter than a utility.
    """
    if len(df) < rsi_window + lookback:
        return None
    rsi_series = ta.rsi(df["Close"], length=rsi_window)
    if rsi_series is None:
        return None
    rsi_clean = rsi_series.dropna().iloc[-lookback:]
    if len(rsi_clean) < 10:
        return None
    today_rsi = float(rsi_clean.iloc[-1])
    pct = float((rsi_clean < today_rsi).sum()) / len(rsi_clean)
    return round(pct, 4)


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


def _compute_period_returns(df: pd.DataFrame, windows: list[int]) -> dict[str, float]:
    """Compute period returns from a Close price series for each month window."""
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

    cfg = get_config()
    ticker_returns = _compute_period_returns(df, cfg.quant.momentum_windows_months)
    spy_returns = _compute_period_returns(spy_df, cfg.quant.momentum_windows_months)

    momentum = compute_momentum_score(ticker_returns, spy_returns) if ticker_returns else None
    quality = compute_quality_score(ratios.get("roe"), ratios.get("debt_to_equity"))
    value = compute_value_score(ratios.get("pe"), cfg.quant.earnings_yield_min, cfg.quant.earnings_yield_max)
    low_vol = compute_low_vol_score(df, cfg.quant.volatility_window_days)
    composite = compute_composite_score(momentum, quality, value, low_vol)

    # Statistical anomaly + mean-reversion metrics — not part of composite score,
    # but passed through factor_breakdown so synthesis and technical agents have context.
    return_zscore = compute_return_zscore(df)
    volume_ratio = compute_volume_ratio(df)
    bb_percentile = compute_bb_percentile(df)
    rsi_percentile = compute_rsi_percentile(df)

    signal = QuantSignal(
        composite_score=composite,
        factor_breakdown={
            "momentum": momentum,
            "quality": quality,
            "value": value,
            "low_vol": low_vol,
            "return_zscore": return_zscore,
            "volume_ratio": volume_ratio,
            "bb_percentile": bb_percentile,
            "rsi_percentile": rsi_percentile,
        },
        data_quality=data_quality,
    )
    log.info("quant_agent_done", ticker=ticker, composite=composite,
             return_zscore=return_zscore, volume_ratio=volume_ratio)
    return signal


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        signal = await run(ticker)
        print(signal.model_dump_json(indent=2))

    asyncio.run(main())
