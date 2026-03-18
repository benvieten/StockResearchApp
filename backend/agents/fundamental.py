"""
Fundamental agent.

Pre-computes all financial ratios from raw yfinance data, then calls
claude-haiku to score quality and determine valuation verdict.

Usage:
    python -m backend.agents.fundamental AAPL
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

import structlog
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random

from backend.core.config import get_config
from backend.core.data_models import FundamentalSignal
from backend.data.price import get_financials

log = structlog.get_logger()

load_dotenv()
_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


# ── Pure ratio computation (unit-tested independently) ─────────────────────────


def compute_ratios(financials: dict) -> dict:
    """
    Compute all financial ratios from raw yfinance data.

    Returns a dict with all ratios plus a 'data_quality' key.
    Any None input field sets data_quality='partial'.
    No NaN values are ever returned — missing ratios are None.
    """
    has_nulls = False

    def _first(lst: list | None) -> float | None:
        nonlocal has_nulls
        if lst is None:
            has_nulls = True
            return None
        val = lst[0] if lst else None
        if val is None:
            has_nulls = True
        return val

    def _safe_div(a: float | None, b: float | None) -> float | None:
        nonlocal has_nulls
        if a is None or b is None:
            has_nulls = True
            return None
        if b == 0:
            return None
        return a / b

    rev = financials.get("revenue") or []
    revenue_0 = _first(rev)
    revenue_1 = rev[1] if len(rev) > 1 else None
    if revenue_1 is None:
        has_nulls = True

    gross_profit_0 = _first(financials.get("gross_profit"))
    operating_income_0 = _first(financials.get("operating_income"))
    net_income_0 = _first(financials.get("net_income"))
    ebitda_0 = _first(financials.get("ebitda"))
    total_debt_0 = _first(financials.get("total_debt"))
    total_equity_0 = _first(financials.get("total_equity"))
    fcf_0 = _first(financials.get("free_cash_flow"))

    market_cap = financials.get("market_cap")
    enterprise_value = financials.get("enterprise_value")
    price = financials.get("price")
    trailing_pe = financials.get("trailing_pe")
    book_value = financials.get("book_value_per_share")

    if market_cap is None:
        has_nulls = True
    if enterprise_value is None:
        has_nulls = True
    if trailing_pe is None:
        has_nulls = True

    # ── Ratios ─────────────────────────────────────────────────────────────────

    pe = trailing_pe  # use yfinance trailing PE directly

    pb = _safe_div(price, book_value)

    # P/S using most recent annual revenue (annualise if using quarterly)
    ps = _safe_div(market_cap, revenue_0) if revenue_0 else None
    if ps is None:
        has_nulls = True

    ev_ebitda = _safe_div(enterprise_value, ebitda_0)

    gross_margin = _safe_div(gross_profit_0, revenue_0)
    operating_margin = _safe_div(operating_income_0, revenue_0)
    net_margin = _safe_div(net_income_0, revenue_0)

    # Period-over-period revenue growth (annual or quarterly depending on source)
    if revenue_0 is not None and revenue_1 is not None and revenue_1 != 0:
        revenue_growth_qoq = (revenue_0 - revenue_1) / revenue_1
    else:
        revenue_growth_qoq = None
        has_nulls = True

    # YoY is same formula for annual data
    revenue_growth_yoy = revenue_growth_qoq

    debt_to_equity = _safe_div(total_debt_0, total_equity_0)
    roe = _safe_div(net_income_0, total_equity_0)
    fcf_yield = _safe_div(fcf_0, market_cap)

    return {
        "pe": pe,
        "pb": pb,
        "ps": ps,
        "ev_ebitda": ev_ebitda,
        "gross_margin": gross_margin,
        "operating_margin": operating_margin,
        "net_margin": net_margin,
        "revenue_growth_qoq": revenue_growth_qoq,
        "revenue_growth_yoy": revenue_growth_yoy,
        "debt_to_equity": debt_to_equity,
        "roe": roe,
        "fcf_yield": fcf_yield,
        "data_quality": "partial" if has_nulls else "full",
    }


# ── LLM call ───────────────────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=16) + wait_random(-0.5, 0.5),
    reraise=True,
)
async def _call_llm(model: str, ratios: dict, ticker: str) -> FundamentalSignal:
    client = _get_client()
    data_quality = ratios.pop("data_quality", "full")

    prompt = f"""You are a fundamental equity analyst. Analyse {ticker} using these pre-computed financial ratios:

{_fmt_ratios(ratios)}

Your task:
1. Assess overall financial quality (0.0 = very poor, 1.0 = excellent)
2. Determine valuation verdict: undervalued / fair / overvalued
3. List key positive flags (e.g. strong FCF, expanding margins)
4. List key negative flags (e.g. high leverage, shrinking revenue)
5. Write a brief reasoning (2-4 sentences)

Be precise. Use the numbers given — do not invent ratios."""

    schema = FundamentalSignal.model_json_schema()
    schema.pop("$defs", None)
    schema.pop("title", None)

    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[{"name": "submit", "description": "Submit the fundamental signal", "input_schema": schema}],
        tool_choice={"type": "tool", "name": "submit"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use":
            data = dict(block.input)
            data["data_quality"] = data_quality
            data.setdefault("metrics", {k: v for k, v in ratios.items()})
            return FundamentalSignal.model_validate(data)

    raise ValueError("No tool_use block in fundamental LLM response")


def _fmt_ratios(ratios: dict) -> str:
    lines = []
    for k, v in ratios.items():
        if v is None:
            lines.append(f"  {k}: N/A")
        elif isinstance(v, float):
            lines.append(f"  {k}: {v:.4f}")
        else:
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


# ── Public async entry point ───────────────────────────────────────────────────


async def run(ticker: str) -> FundamentalSignal:
    cfg = get_config()
    model = cfg.anthropic.models["fundamental"]

    log.info("fundamental_agent_start", ticker=ticker, model=model)
    financials = await get_financials(ticker)
    ratios = compute_ratios(financials)

    signal = await _call_llm(model, ratios, ticker)
    log.info("fundamental_agent_done", ticker=ticker, verdict=signal.valuation_verdict)
    return signal


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import json

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        signal = await run(ticker)
        print(signal.model_dump_json(indent=2))

    asyncio.run(main())
