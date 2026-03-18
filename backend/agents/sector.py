"""
Sector agent.

Fetches sector info from yfinance, computes 12-month returns vs sector ETF
and representative peers, then calls claude-sonnet to assess relative
performance.

Usage:
    python -m backend.agents.sector AAPL
"""

from __future__ import annotations

import asyncio
import sys

import structlog
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random

from backend.core.config import get_config
from backend.core.data_models import SectorSignal
from backend.data.price import get_company_info, get_ohlcv

log = structlog.get_logger()

load_dotenv()
_client: AsyncAnthropic | None = None

# Representative large-cap peers per sector for relative performance context
_SECTOR_PEERS: dict[str, list[str]] = {
    "Technology": ["MSFT", "GOOGL", "NVDA", "META", "ORCL"],
    "Healthcare": ["JNJ", "UNH", "ABBV", "MRK", "LLY"],
    "Financials": ["JPM", "BAC", "WFC", "GS", "MS"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
    "Consumer Staples": ["PG", "KO", "PEP", "WMT", "COST"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
    "Industrials": ["HON", "UPS", "CAT", "DE", "RTX"],
    "Materials": ["LIN", "APD", "ECL", "DD", "NEM"],
    "Real Estate": ["AMT", "PLD", "CCI", "EQIX", "SPG"],
    "Utilities": ["NEE", "DUK", "SO", "D", "AEP"],
    "Communication Services": ["META", "GOOGL", "NFLX", "DIS", "VZ"],
}


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


# ── Return computation ─────────────────────────────────────────────────────────


def compute_12m_return(ohlcv: dict) -> float | None:
    """
    Compute 12-month (252 trading days) price return from OHLCV dict.

    Returns None if fewer than 253 data points are available.
    """
    closes = ohlcv.get("close", [])
    # Need at least 253 points: today + 252 days back
    if len(closes) < 253:
        return None
    past_price = closes[-253]
    last_price = closes[-1]
    if past_price is None or past_price == 0:
        return None
    return (last_price - past_price) / past_price


# ── LLM call ───────────────────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=16) + wait_random(-0.5, 0.5),
    reraise=True,
)
async def _call_llm(
    model: str,
    ticker: str,
    sector: str,
    sector_etf: str,
    ticker_return: float | None,
    etf_return: float | None,
    peer_comparison: dict[str, float],
    data_quality: str,
) -> SectorSignal:
    client = _get_client()

    def _fmt_pct(v: float | None) -> str:
        return f"{v * 100:.1f}%" if v is not None else "N/A"

    peer_lines = "\n".join(
        f"  {t}: {_fmt_pct(r)}" for t, r in peer_comparison.items()
    )

    prompt = f"""You are a sector equity analyst. Evaluate {ticker}'s performance relative to its sector.

Sector: {sector}
Sector ETF: {sector_etf}

12-Month Returns:
  {ticker}: {_fmt_pct(ticker_return)}
  {sector_etf} (sector benchmark): {_fmt_pct(etf_return)}

Sector Peers (12-month returns):
{peer_lines or "  No peer data available."}

Your task:
1. relative_performance: "outperforming" / "inline" / "underperforming" vs the sector ETF
   - outperforming: ticker return > ETF return by >5pp
   - inline: within ±5pp of ETF return
   - underperforming: ticker return < ETF return by >5pp
   - If ETF return is unavailable, use peer median
2. reasoning: 2-3 sentences explaining the relative performance and any notable peer context
3. Confirm sector and sector_etf values from the data provided (do not modify them)
4. peer_comparison: return the dict of peer tickers and their returns as floats (not percentages)"""

    schema = SectorSignal.model_json_schema()
    schema.pop("$defs", None)
    schema.pop("title", None)

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[{"name": "submit", "description": "Submit the sector signal", "input_schema": schema}],
        tool_choice={"type": "tool", "name": "submit"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use":
            data = dict(block.input)
            # Ensure sector/ETF come from our computed data, not LLM hallucination
            data["sector"] = sector
            data["sector_etf"] = sector_etf
            data["peer_comparison"] = peer_comparison
            data["data_quality"] = data_quality
            return SectorSignal.model_validate(data)

    raise ValueError("No tool_use block in sector LLM response")


# ── Public async entry point ───────────────────────────────────────────────────


async def run(ticker: str) -> SectorSignal:
    cfg = get_config()
    model = cfg.anthropic.models["sector"]

    log.info("sector_agent_start", ticker=ticker, model=model)

    company_info = await get_company_info(ticker)
    sector = company_info.get("sector") or "Unknown"

    # Look up sector ETF from config
    sector_etf = cfg.sector_etf_map.get(sector, "SPY")

    # Get peers for this sector, excluding the ticker itself
    raw_peers = [p for p in _SECTOR_PEERS.get(sector, []) if p != ticker]
    peers = raw_peers[:4]  # limit to 4 peers to cap API calls

    # Fetch OHLCV for ticker, ETF, and peers concurrently
    all_tickers = [ticker, sector_etf] + peers
    ohlcv_results = await asyncio.gather(
        *[get_ohlcv(t) for t in all_tickers],
        return_exceptions=True,
    )

    ticker_ohlcv = ohlcv_results[0]
    etf_ohlcv = ohlcv_results[1]
    peer_ohlcvs = ohlcv_results[2:]

    ticker_return = (
        compute_12m_return(ticker_ohlcv)
        if not isinstance(ticker_ohlcv, Exception)
        else None
    )
    etf_return = (
        compute_12m_return(etf_ohlcv)
        if not isinstance(etf_ohlcv, Exception)
        else None
    )

    peer_comparison: dict[str, float] = {}
    for sym, result in zip(peers, peer_ohlcvs):
        if isinstance(result, Exception):
            log.warning("sector_peer_fetch_failed", peer=sym, error=str(result))
            continue
        ret = compute_12m_return(result)
        if ret is not None:
            peer_comparison[sym] = ret

    has_partial = (ticker_return is None or etf_return is None or not peer_comparison)
    data_quality = "partial" if has_partial else "full"

    signal = await _call_llm(
        model, ticker, sector, sector_etf,
        ticker_return, etf_return, peer_comparison, data_quality,
    )
    log.info(
        "sector_agent_done",
        ticker=ticker,
        sector=sector,
        relative_performance=signal.relative_performance,
    )
    return signal


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        signal = await run(ticker)
        print(signal.model_dump_json(indent=2))

    asyncio.run(main())
