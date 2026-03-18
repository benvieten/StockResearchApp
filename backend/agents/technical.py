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

from backend.core.config import get_config
from backend.core.data_models import TechnicalSignal
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
    Support/resistance derived from lowest low / highest high of last 20 candles.
    """
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # EMAs
    ema_20 = float(ta.ema(close, length=20).iloc[-1])
    ema_50 = float(ta.ema(close, length=50).iloc[-1])
    ema_200 = float(ta.ema(close, length=200).iloc[-1])

    # RSI
    rsi_14 = float(ta.rsi(close, length=14).iloc[-1])

    # MACD — columns: MACD_{fast}_{slow}_{signal}, MACDh_..., MACDs_...
    macd_df = ta.macd(close)
    macd_cols = list(macd_df.columns)
    macd_val = float(macd_df[macd_cols[0]].iloc[-1])    # MACD line
    macd_hist = float(macd_df[macd_cols[1]].iloc[-1])   # histogram
    macd_signal = float(macd_df[macd_cols[2]].iloc[-1]) # signal line

    # Bollinger Bands — columns: BBL, BBM, BBU, BBB, BBP
    bb_df = ta.bbands(close, length=20)
    bb_cols = list(bb_df.columns)
    bb_lower = float(bb_df[bb_cols[0]].iloc[-1])
    bb_mid = float(bb_df[bb_cols[1]].iloc[-1])
    bb_upper = float(bb_df[bb_cols[2]].iloc[-1])

    # ATR
    atr_14 = float(ta.atr(high, low, close, length=14).iloc[-1])

    # OBV
    obv = float(ta.obv(close, volume).iloc[-1])

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
async def _call_llm(model: str, indicators: dict, ticker: str) -> TechnicalSignal:
    client = _get_client()
    current_price = indicators.get("ema_20", 0)  # proxy for current price

    prompt = f"""You are a technical analyst. Analyse {ticker} using these computed indicators:

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
- indicator_summary: 2-3 sentence description of the technical picture
- reasoning: your step-by-step reasoning"""

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


async def run(ticker: str) -> TechnicalSignal:
    cfg = get_config()
    model = cfg.anthropic.models["technical"]

    log.info("technical_agent_start", ticker=ticker, model=model)
    ohlcv = await get_ohlcv(ticker)
    df = _ohlcv_to_df(ohlcv)
    indicators = compute_indicators(df)

    signal = await _call_llm(model, indicators, ticker)
    log.info("technical_agent_done", ticker=ticker, direction=signal.direction)
    return signal


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import json

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        signal = await run(ticker)
        print(signal.model_dump_json(indent=2))

    asyncio.run(main())
