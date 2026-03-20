"""
Technical agent.

Computes all indicators using pandas-ta, then calls claude-haiku to
determine trend direction and confidence.

Usage:
    python -m backend.agents.technical AAPL
"""

from __future__ import annotations

import asyncio
import sys

import pandas as pd
import pandas_ta as ta
import structlog
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random

from backend.core.data_models import TechnicalSignal
from backend.core.model_router import get_model_router
from backend.core.regime import RegimeSignal, get_regime
from backend.data.price import get_ohlcv

log = structlog.get_logger()

load_dotenv()
_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


# ── Indicator computation (unit-tested independently) ─────────────────────────


def compute_indicators(df: pd.DataFrame) -> dict:
    """
    Compute all technical indicators from an OHLCV DataFrame.

    Returns the most-recent value for each indicator as a flat dict.
    Any indicator that cannot be computed (insufficient data or all-NaN series)
    is returned as None. Support/resistance derived from lowest low / highest
    high of last 20 candles.
    """
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    def _last(series: pd.Series | None) -> float | None:
        """Return the last non-NaN value from a series, or None if unavailable."""
        if series is None or series.empty or series.isna().all():
            return None
        val = series.iloc[-1]
        return float(val) if not pd.isna(val) else None

    # EMAs
    ema_20 = _last(ta.ema(close, length=20))
    ema_50 = _last(ta.ema(close, length=50))
    ema_200 = _last(ta.ema(close, length=200))

    # RSI
    rsi_14 = _last(ta.rsi(close, length=14))

    # MACD — use column-name prefix matching, not positional index.
    # pandas-ta returns MACD_{f}_{s}_{sig}, MACDh_{f}_{s}_{sig}, MACDs_{f}_{s}_{sig}
    macd_df = ta.macd(close)
    macd_val = macd_hist = macd_signal = None
    if macd_df is not None:
        macd_col = next((c for c in macd_df.columns if c.startswith("MACD_")), None)
        macdh_col = next((c for c in macd_df.columns if c.startswith("MACDh_")), None)
        macds_col = next((c for c in macd_df.columns if c.startswith("MACDs_")), None)
        macd_val = _last(macd_df[macd_col]) if macd_col else None
        macd_hist = _last(macd_df[macdh_col]) if macdh_col else None
        macd_signal = _last(macd_df[macds_col]) if macds_col else None

    # Bollinger Bands — use column-name prefix matching.
    # pandas-ta returns BBL_{n}_{std}, BBM_{n}_{std}, BBU_{n}_{std}, ...
    bb_df = ta.bbands(close, length=20)
    bb_lower = bb_mid = bb_upper = None
    if bb_df is not None:
        bbl_col = next((c for c in bb_df.columns if c.startswith("BBL_")), None)
        bbm_col = next((c for c in bb_df.columns if c.startswith("BBM_")), None)
        bbu_col = next((c for c in bb_df.columns if c.startswith("BBU_")), None)
        bb_lower = _last(bb_df[bbl_col]) if bbl_col else None
        bb_mid = _last(bb_df[bbm_col]) if bbm_col else None
        bb_upper = _last(bb_df[bbu_col]) if bbu_col else None

    # ATR
    atr_14 = _last(ta.atr(high, low, close, length=14))

    # OBV
    obv = _last(ta.obv(close, volume))

    # Support / resistance from last 20 candles
    last_20 = df.iloc[-20:]
    support = float(last_20["Low"].min())
    resistance = float(last_20["High"].max())

    return {
        "ema_20": ema_20,
        "ema_50": ema_50,
        "ema_200": ema_200,
        "rsi_14": rsi_14,
        "macd": macd_val,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_mid": bb_mid,
        "atr_14": atr_14,
        "obv": obv,
        "support": support,
        "resistance": resistance,
    }


def _ohlcv_to_df(ohlcv: dict) -> pd.DataFrame:
    """Convert the cached OHLCV dict to a pandas DataFrame."""
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


# ── LLM call ───────────────────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=16) + wait_random(-0.5, 0.5),
    reraise=True,
)
async def _call_llm(
    model: str, indicators: dict, ticker: str, regime: RegimeSignal
) -> TechnicalSignal:
    client = _get_client()

    # Format regime context so the LLM can interpret indicators correctly
    regime_conf_pct = f"{regime.confidence * 100:.0f}%"
    regime_ctx = f"{regime.regime.upper()} ({regime_conf_pct} confidence)"
    if regime.vix is not None:
        regime_ctx += f" | VIX: {regime.vix:.1f}"
    if regime.adx is not None:
        regime_ctx += f" | ADX: {regime.adx:.1f}"

    prompt = f"""You are a technical analyst. Analyse {ticker} using these computed indicators:

=== MARKET REGIME (SPY-based) ===
{regime_ctx}

Regime guidance:
- BULL regime: RSI overbought (>70) is momentum confirmation, not a reversal warning.
  MACD crossovers above zero carry higher conviction. Dips toward EMA20/50 are buy signals.
- BEAR regime: RSI oversold (<30) may not hold; favour breakdown setups.
  Bounces toward EMA50/200 from below are likely resistance. Prioritise downside risk.
- TRANSITIONAL regime: Weight mean-reversion signals (Bollinger, RSI extremes) over
  trend-following signals (EMA crossovers, MACD). Reduce confidence in any directional call.

=== {ticker} INDICATORS ===
EMA 20: {indicators['ema_20']:.2f}
EMA 50: {indicators['ema_50']:.2f}
EMA 200: {indicators['ema_200']:.2f}
RSI 14: {indicators['rsi_14']:.1f}
MACD: {indicators['macd']:.4f}  Signal: {indicators['macd_signal']:.4f}  Hist: {indicators['macd_hist']:.4f}
Bollinger Upper: {indicators['bb_upper']:.2f}  Mid: {indicators['bb_mid']:.2f}  Lower: {indicators['bb_lower']:.2f}
ATR 14: {indicators['atr_14']:.2f}
OBV: {indicators['obv']:.0f}
Support: {indicators['support']:.2f}  Resistance: {indicators['resistance']:.2f}

Determine:
- direction: bullish / bearish / neutral
- confidence: 0.0 (no conviction) to 1.0 (very high conviction)
- key_levels: dict with "support" and "resistance" as floats
- indicator_summary: 2-3 sentence description of the technical picture, referencing the regime
- reasoning: your step-by-step reasoning, explaining how the regime shaped your interpretation"""

    schema = TechnicalSignal.model_json_schema()
    schema.pop("$defs", None)
    schema.pop("title", None)

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[{"name": "submit", "description": "Submit the technical signal", "input_schema": schema}],
        tool_choice={"type": "tool", "name": "submit"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use":
            data = dict(block.input)
            data["raw_indicators"] = {k: v for k, v in indicators.items()}
            data.setdefault("data_quality", "full")
            return TechnicalSignal.model_validate(data)

    raise ValueError("No tool_use block in technical LLM response")


# ── Public async entry point ───────────────────────────────────────────────────


async def run(ticker: str, regime: RegimeSignal | None = None) -> TechnicalSignal:
    model = get_model_router().get_model("technical")

    log.info("technical_agent_start", ticker=ticker, model=model)

    # Fetch OHLCV and regime concurrently; regime is optional (graph may pre-fetch it)
    if regime is None:
        ohlcv, regime = await asyncio.gather(get_ohlcv(ticker), get_regime())
    else:
        ohlcv = await get_ohlcv(ticker)

    df = _ohlcv_to_df(ohlcv)
    indicators = compute_indicators(df)

    signal = await _call_llm(model, indicators, ticker, regime)
    log.info("technical_agent_done", ticker=ticker, direction=signal.direction, regime=regime.regime)
    return signal


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import json

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        signal = await run(ticker)
        print(signal.model_dump_json(indent=2))

    asyncio.run(main())
