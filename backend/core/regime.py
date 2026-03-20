"""
Market regime classifier — Phase 1 (threshold-based).

Classifies the current market environment as bull / bear / transitional using
three independent signals computed from free yfinance data:

  1. VIX level          — fear gauge; high VIX = stress
  2. SPY EMA-200 slope  — price trend direction (annualised)
  3. ADX on SPY         — trend strength (direction-agnostic)

Output: RegimeSignal with a hard label + confidence score.

This module exposes the same interface that the Phase 2 HMM classifier will
use, so downstream agents require no changes when the HMM is introduced.
See docs/HMM_IMPLEMENTATION.md for the Phase 2 design.

Usage:
    python -m backend.core.regime
"""

from __future__ import annotations

import asyncio
from datetime import date

import pandas as pd
import pandas_ta as ta
import structlog
import yfinance as yf
from pydantic import BaseModel

from backend.data._cache import load_cache, save_cache

log = structlog.get_logger()

# ── Thresholds (tunable without code changes via config if desired) ─────────────

_VIX_LOW = 18.0      # below → low fear, consistent with bull
_VIX_HIGH = 28.0     # above → elevated fear, consistent with bear / stress

_ADX_TRENDING = 25.0  # above → market is trending (strong trend)
_ADX_WEAK = 15.0      # below → directionless / ranging

_EMA_SLOPE_BULL = 0.0003   # annualised daily slope threshold for "rising EMA200"
_EMA_SLOPE_BEAR = -0.0003  # below → "falling EMA200"


# ── Output model ───────────────────────────────────────────────────────────────


class RegimeSignal(BaseModel):
    regime: str           # "bull" | "bear" | "transitional"
    confidence: float     # 0.0–1.0; how many signals agree
    vix: float | None
    adx: float | None
    ema200_slope: float | None  # annualised daily EMA-200 slope on SPY
    spy_vs_ema200: float | None  # (SPY_price - EMA200) / EMA200
    model_source: str = "threshold"
    # Placeholder for Phase 2 HMM — always None in Phase 1
    regime_probs: dict[str, float] | None = None
    as_of: str = ""      # ISO date string


# ── Data fetching ──────────────────────────────────────────────────────────────


async def _fetch_spy_vix() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch 1 year of daily SPY and VIX data via yfinance (sync wrapped)."""
    loop = asyncio.get_event_loop()

    def _download() -> tuple[pd.DataFrame, pd.DataFrame]:
        spy = yf.download("SPY", period="1y", auto_adjust=True, progress=False)
        vix = yf.download("^VIX", period="1y", auto_adjust=True, progress=False)
        return spy, vix

    spy_df, vix_df = await loop.run_in_executor(None, _download)
    return spy_df, vix_df


# ── Indicator computation ──────────────────────────────────────────────────────


def _compute_regime_indicators(
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame,
) -> dict[str, float | None]:
    """
    Compute the three regime signals from raw OHLCV DataFrames.

    Returns a dict with keys: vix, adx, ema200_slope, spy_vs_ema200.
    Any value that cannot be computed is None.
    """
    def _flatten(df: pd.DataFrame) -> pd.DataFrame:
        """Drop MultiIndex ticker level that yfinance 1.2 adds to single-ticker downloads."""
        if isinstance(df.columns, pd.MultiIndex):
            df = df.copy()
            df.columns = df.columns.get_level_values(0)
        return df

    # ── VIX — most recent close ───────────────────────────────────────────────
    vix_val: float | None = None
    if not vix_df.empty:
        vix_flat = _flatten(vix_df)
        close_col = "Close" if "Close" in vix_flat.columns else vix_flat.columns[0]
        raw = vix_flat[close_col].dropna()
        if not raw.empty:
            vix_val = float(raw.iloc[-1])

    # ── ADX on SPY ────────────────────────────────────────────────────────────
    adx_val: float | None = None
    if not spy_df.empty and len(spy_df) >= 14:
        df = _flatten(spy_df)

        adx_df = ta.adx(df["High"], df["Low"], df["Close"], length=14)
        if adx_df is not None:
            adx_col = next((c for c in adx_df.columns if c.startswith("ADX_")), None)
            if adx_col:
                series = adx_df[adx_col].dropna()
                if not series.empty:
                    adx_val = float(series.iloc[-1])

    # ── EMA-200 slope and position on SPY ─────────────────────────────────────
    ema200_slope: float | None = None
    spy_vs_ema200: float | None = None

    if not spy_df.empty and len(spy_df) >= 205:
        df = spy_df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df["Close"].dropna()
        ema200 = ta.ema(close, length=200)

        if ema200 is not None and not ema200.dropna().empty:
            ema_series = ema200.dropna()

            # Slope: compare last value to value 5 days ago, normalise by EMA level
            if len(ema_series) >= 6:
                e_now = float(ema_series.iloc[-1])
                e_5ago = float(ema_series.iloc[-6])
                if e_5ago and e_5ago != 0:
                    # Raw 5-day fractional change → annualise (252 trading days)
                    raw_slope = (e_now - e_5ago) / e_5ago
                    ema200_slope = raw_slope * (252 / 5)

            # Price vs EMA200 position
            last_price = float(close.iloc[-1])
            last_ema = float(ema200.dropna().iloc[-1])
            if last_ema and last_ema != 0:
                spy_vs_ema200 = (last_price - last_ema) / last_ema

    return {
        "vix": vix_val,
        "adx": adx_val,
        "ema200_slope": ema200_slope,
        "spy_vs_ema200": spy_vs_ema200,
    }


# ── Regime classification ──────────────────────────────────────────────────────


def classify_regime(indicators: dict[str, float | None]) -> tuple[str, float]:
    """
    Classify market regime from computed indicators.

    Each signal casts a vote: bull (+1), bear (-1), or neutral (0).
    Confidence = fraction of available signals that agree with the majority.

    Returns (regime_label, confidence).
    """
    vix = indicators["vix"]
    adx = indicators["adx"]
    slope = indicators["ema200_slope"]
    vs_ema = indicators["spy_vs_ema200"]

    votes: list[int] = []

    # ── VIX vote ──────────────────────────────────────────────────────────────
    if vix is not None:
        if vix < _VIX_LOW:
            votes.append(1)   # low fear → bull
        elif vix > _VIX_HIGH:
            votes.append(-1)  # elevated fear → bear
        else:
            votes.append(0)   # neutral zone

    # ── EMA200 slope vote ─────────────────────────────────────────────────────
    if slope is not None:
        if slope > _EMA_SLOPE_BULL:
            votes.append(1)
        elif slope < _EMA_SLOPE_BEAR:
            votes.append(-1)
        else:
            votes.append(0)

    # ── Price vs EMA200 vote ──────────────────────────────────────────────────
    if vs_ema is not None:
        if vs_ema > 0.02:       # SPY > 2% above EMA200 → bullish structure
            votes.append(1)
        elif vs_ema < -0.02:    # SPY > 2% below EMA200 → bearish structure
            votes.append(-1)
        else:
            votes.append(0)

    # ADX modulates confidence but doesn't cast a directional vote
    # (ADX is direction-agnostic — high ADX just means the trend is strong)
    adx_confidence_boost = 0.0
    if adx is not None and adx > _ADX_TRENDING:
        adx_confidence_boost = 0.10  # reward agreement when trend is confirmed
    elif adx is not None and adx < _ADX_WEAK:
        adx_confidence_boost = -0.05  # penalise when market is directionless

    if not votes:
        return "transitional", 0.5

    total = len(votes)
    bull_votes = votes.count(1)
    bear_votes = votes.count(-1)
    net = bull_votes - bear_votes

    # Determine dominant label
    if net > 0:
        label = "bull"
        raw_confidence = bull_votes / total
    elif net < 0:
        label = "bear"
        raw_confidence = bear_votes / total
    else:
        label = "transitional"
        raw_confidence = 0.5

    confidence = max(0.0, min(1.0, raw_confidence + adx_confidence_boost))
    return label, confidence


# ── Public async entry point ───────────────────────────────────────────────────


async def get_regime() -> RegimeSignal:
    """
    Fetch market data and return the current RegimeSignal.

    Falls back gracefully: if any data source fails, the remaining
    signals still cast votes. If all sources fail, returns transitional/0.5.
    """
    log.info("regime_classifier_start", source="threshold")

    cached = load_cache("SPY", "regime")
    if cached is not None:
        log.debug("regime_cache_hit")
        return RegimeSignal.model_validate(cached)

    try:
        spy_df, vix_df = await _fetch_spy_vix()
    except Exception as exc:
        log.warning("regime_fetch_failed", error=str(exc))
        return RegimeSignal(
            regime="transitional",
            confidence=0.5,
            vix=None,
            adx=None,
            ema200_slope=None,
            spy_vs_ema200=None,
            as_of=date.today().isoformat(),
        )

    indicators = _compute_regime_indicators(spy_df, vix_df)
    regime, confidence = classify_regime(indicators)

    log.info(
        "regime_classifier_done",
        regime=regime,
        confidence=round(confidence, 3),
        vix=indicators["vix"],
        adx=indicators["adx"],
    )

    signal = RegimeSignal(
        regime=regime,
        confidence=confidence,
        vix=indicators["vix"],
        adx=indicators["adx"],
        ema200_slope=indicators["ema200_slope"],
        spy_vs_ema200=indicators["spy_vs_ema200"],
        as_of=date.today().isoformat(),
    )
    save_cache("SPY", "regime", signal.model_dump())
    return signal


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    async def main() -> None:
        signal = await get_regime()
        print(signal.model_dump_json(indent=2))

    asyncio.run(main())
