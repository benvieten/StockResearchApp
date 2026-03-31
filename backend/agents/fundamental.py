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

from backend.core.data_models import FundamentalSignal
from backend.core.model_router import get_model_router
from backend.data._cache import load_cache, save_cache
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

    def _nth(lst: list | None, n: int) -> float | None:
        """Get nth element without affecting has_nulls — for optional Piotroski fields."""
        if lst is None or len(lst) <= n:
            return None
        return lst[n]

    def _opt_div(a: float | None, b: float | None) -> float | None:
        """Safe division without affecting has_nulls — for optional Piotroski fields."""
        if a is None or b is None or b == 0:
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

    # Piotroski fields — optional; missing fields degrade the score but not data_quality
    gross_profit_1 = _nth(financials.get("gross_profit"), 1)
    net_income_1 = _nth(financials.get("net_income"), 1)
    total_debt_1 = _nth(financials.get("total_debt"), 1)
    total_equity_1 = _nth(financials.get("total_equity"), 1)
    total_assets_0 = _nth(financials.get("total_assets"), 0)
    total_assets_1 = _nth(financials.get("total_assets"), 1)
    current_assets_0 = _nth(financials.get("current_assets"), 0)
    current_assets_1 = _nth(financials.get("current_assets"), 1)
    current_liabilities_0 = _nth(financials.get("current_liabilities"), 0)
    current_liabilities_1 = _nth(financials.get("current_liabilities"), 1)
    ocf_0 = _nth(financials.get("operating_cash_flow"), 0)

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

    # ── Piotroski F-Score (0–9) ─────────────────────────────────────────────────
    # Each signal is 1 if condition met, 0 otherwise, None if data unavailable.
    # Score is sum of available signals; None if fewer than 5 signals computable.
    roa_0 = _opt_div(net_income_0, total_assets_0)
    roa_1 = _opt_div(net_income_1, total_assets_1)
    # OCF / Total Assets
    ocf_ta = _opt_div(ocf_0, total_assets_0)
    # Change in ROA
    delta_roa = (roa_0 - roa_1) if (roa_0 is not None and roa_1 is not None) else None
    # Accruals ratio: (Net Income - OCF) / Total Assets
    accruals_ratio = (
        (net_income_0 - ocf_0) / total_assets_0
        if (net_income_0 is not None and ocf_0 is not None and total_assets_0 is not None and total_assets_0 != 0)
        else None
    )
    # Change in leverage (lower = better)
    lev_0 = _opt_div(total_debt_0, total_assets_0)
    lev_1 = _opt_div(total_debt_1, total_assets_1)
    delta_lev = (lev_0 - lev_1) if (lev_0 is not None and lev_1 is not None) else None
    # Change in current ratio
    cr_0 = _opt_div(current_assets_0, current_liabilities_0)
    cr_1 = _opt_div(current_assets_1, current_liabilities_1)
    delta_cr = (cr_0 - cr_1) if (cr_0 is not None and cr_1 is not None) else None
    # Change in gross margin
    gm_0 = _opt_div(gross_profit_0, revenue_0)
    gm_1 = _opt_div(gross_profit_1, revenue_1)
    delta_gm = (gm_0 - gm_1) if (gm_0 is not None and gm_1 is not None) else None
    # Change in asset turnover
    at_0 = _opt_div(revenue_0, total_assets_0)
    at_1 = _opt_div(revenue_1, total_assets_1)
    delta_at = (at_0 - at_1) if (at_0 is not None and at_1 is not None) else None
    # Change in shares (dilution check) — skip: not worth adding another yfinance field
    # Assemble 9 binary signals
    signals = [
        (1 if roa_0 > 0 else 0) if roa_0 is not None else None,       # F1: positive ROA
        (1 if ocf_ta > 0 else 0) if ocf_ta is not None else None,      # F2: positive OCF/Assets
        (1 if delta_roa > 0 else 0) if delta_roa is not None else None, # F3: ROA improving
        (1 if accruals_ratio < 0 else 0) if accruals_ratio is not None else None,  # F4: OCF > NI
        (1 if delta_lev < 0 else 0) if delta_lev is not None else None, # F5: leverage falling
        (1 if delta_cr > 0 else 0) if delta_cr is not None else None,   # F6: liquidity improving
        None,                                                             # F7: no dilution (skipped)
        (1 if delta_gm > 0 else 0) if delta_gm is not None else None,  # F8: gross margin improving
        (1 if delta_at > 0 else 0) if delta_at is not None else None,  # F9: asset turnover improving
    ]
    available = [s for s in signals if s is not None]
    piotroski_score: int | None = sum(available) if len(available) >= 5 else None

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
        "piotroski_score": piotroski_score,
        "accruals_ratio": accruals_ratio,
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

Piotroski F-Score guidance (if provided): 0-2 = weak, 3-5 = average, 6-7 = good, 8-9 = excellent.
Accruals ratio guidance: negative = OCF exceeds net income (earnings quality is HIGH); positive = accruals-driven earnings (lower quality).

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
    cached = load_cache(ticker, "signal_fundamental")
    if cached is not None:
        log.info("fundamental_agent_cache_hit", ticker=ticker)
        return FundamentalSignal.model_validate(cached)

    model = get_model_router().get_model("fundamental")
    log.info("fundamental_agent_start", ticker=ticker, model=model)
    financials = await get_financials(ticker)
    ratios = compute_ratios(financials)

    signal = await _call_llm(model, ratios, ticker)
    save_cache(ticker, "signal_fundamental", signal.model_dump())
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
