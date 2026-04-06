"""
FastAPI backend for the Stock Research Multi-Agent App.

Endpoints:
    GET  /health                   — liveness check
    POST /research                 — blocking full pipeline, returns FinalReport
    POST /research/stream          — SSE streaming with per-agent progress events

SSE notes:
    - Use fetch() + response.body.getReader() on the frontend — NOT EventSource.
      Native EventSource only supports GET; this endpoint is POST.
    - X-Accel-Buffering: no is set to prevent nginx from buffering the stream.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager

import structlog
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, field_validator
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random

from backend.core.config import get_config
from backend.core.data_models import TraderProfile
from backend.core.graph import run_research, stream_research
from backend.core.model_router import get_model_router
from backend.core.backtest import get_last_prediction, get_ticker_history
from backend.core.saved_tickers import add_ticker, get_tickers, is_saved, remove_ticker
from backend.core.usage import get_daily_summary
from backend.data.price import get_analyst_data
from backend.data.screener import get_candidates

load_dotenv()
log = structlog.get_logger()

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


# ── Lifespan ───────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup")
    yield
    log.info("shutdown")


# ── App ────────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="Stock Research API",
    version="1.0.0",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app)

_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / response models ──────────────────────────────────────────────────


class ResearchRequest(BaseModel):
    ticker: str
    trader_profile: TraderProfile | None = None

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not _TICKER_RE.match(v):
            raise ValueError(
                f"Invalid ticker '{v}'. Must be 1-5 uppercase letters (e.g. AAPL)."
            )
        return v


class ExplainSimpleRequest(BaseModel):
    ticker: str
    verdict: str
    conviction: str
    narrative: str
    bull_case: list[str]
    bear_case: list[str]
    conflicts: list[str]
    signal_scores: dict[str, float]


# ── Routes ─────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/research")
async def research(req: ResearchRequest) -> dict:
    """
    Blocking endpoint — runs the full 6-agent pipeline and returns the
    complete FinalReport as JSON. Suitable for non-streaming clients.
    """
    log.info("research_request", ticker=req.ticker)
    try:
        report = await run_research(req.ticker, trader_profile=req.trader_profile)
        return report.model_dump()
    except Exception as exc:
        log.error("research_failed", ticker=req.ticker, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail={"error": str(exc), "ticker": req.ticker, "phase": "pipeline"},
        )


@app.post("/research/stream")
async def research_stream(req: ResearchRequest) -> StreamingResponse:
    """
    SSE streaming endpoint — yields one JSON event per line as agents complete.

    Event types:
        {"type": "agent_start",    "agent": "<name>"}
        {"type": "agent_complete", "agent": "<name>", "signal": {...}}
        {"type": "agent_error",    "agent": "<name>", "error": "<msg>"}
        {"type": "done",           "ticker": "<ticker>"}
        {"type": "error",          "error": "<msg>", "ticker": "<ticker>"}

    Frontend usage (fetch + getReader — NOT EventSource):
        const res = await fetch('/research/stream', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ ticker })
        })
        const reader = res.body.getReader()
    """
    ticker = req.ticker
    log.info("stream_request", ticker=ticker)

    async def event_generator():
        try:
            async for event in stream_research(
                ticker, trader_profile=req.trader_profile
            ):
                data = json.dumps(event, default=str)
                yield f"data: {data}\n\n"
        except Exception as exc:
            log.error("stream_generator_error", ticker=ticker, error=str(exc))
            error_event = json.dumps(
                {"type": "error", "error": str(exc), "ticker": ticker}
            )
            yield f"data: {error_event}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/backtest/{ticker}")
async def backtest_ticker(ticker: str) -> dict:
    """
    Return all saved predictions for a ticker, with outcome data for matured ones.

    Response shape:
        {
          "ticker": "AAPL",
          "predictions": [
            {
              "verdict": "hold",
              "conviction": "low",
              "composite_score": 0.42,
              "horizon": "medium_term",
              "price_at_prediction": 249.12,
              "predicted_at": "2026-03-18T22:30:04+00:00",
              "status": "matured",          // or "pending"
              "elapsed_days": 16,
              "target_days": 60,
              "current_price": 261.50,      // matured only
              "actual_return": 0.049        // matured only; null if price unavailable
            },
            ...
          ]
        }
    """
    ticker = ticker.strip().upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")
    predictions = await asyncio.to_thread(get_ticker_history, ticker)
    return {"ticker": ticker, "predictions": predictions}


@app.get("/watchlist/tickers")
async def watchlist_tickers() -> dict:
    """
    Return today's agent-discovered ticker candidates.
    Calls the screener (cached daily) — instant on repeat requests.
    """
    tickers = await get_candidates()
    return {"tickers": tickers}


@app.post("/watchlist")
async def run_watchlist() -> dict:
    """
    Discover today's candidate tickers via the screener, run each through
    the full research pipeline, and return results grouped by recommended_horizon.

    Discovery is cached daily — only the LLM analysis costs tokens on first run.
    Tickers run with a concurrency semaphore to avoid overwhelming the API.
    """
    cfg = get_config()
    tickers = await get_candidates()
    max_concurrent = cfg.watchlist.max_concurrent
    log.info("watchlist_start", tickers=tickers, max_concurrent=max_concurrent)

    sem = asyncio.Semaphore(max_concurrent)

    async def _run_one(ticker: str) -> dict | None:
        async with sem:
            try:
                report = await run_research(ticker)
                return report.model_dump()
            except Exception as exc:
                log.error("watchlist_ticker_failed", ticker=ticker, error=str(exc))
                return None

    results = await asyncio.gather(*[_run_one(t) for t in tickers])

    grouped: dict[str, list[dict]] = {
        "short_term": [],
        "medium_term": [],
        "long_term": [],
    }
    for report in results:
        if report is None:
            continue
        horizon = report.get("recommended_horizon", "medium_term")
        grouped.setdefault(horizon, []).append(report)

    # Sort each bucket by composite signal score (best first)
    def _score(r: dict) -> float:
        scores = r.get("signal_scores", {})
        return sum(scores.values()) / len(scores) if scores else 0.0

    for bucket in grouped.values():
        bucket.sort(key=_score, reverse=True)

    log.info(
        "watchlist_done",
        short=len(grouped["short_term"]),
        medium=len(grouped["medium_term"]),
        long=len(grouped["long_term"]),
    )
    return grouped


_EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "verdict_explained": {"type": "string"},
        "bull_simple": {"type": "string"},
        "bear_simple": {"type": "string"},
        "bottom_line": {"type": "string"},
    },
    "required": [
        "summary",
        "verdict_explained",
        "bull_simple",
        "bear_simple",
        "bottom_line",
    ],
}


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=16) + wait_random(-0.5, 0.5),
    reraise=True,
)
async def _call_explain_llm(model: str, prompt: str) -> dict:
    client = _get_client()
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[
            {
                "name": "submit",
                "description": "Submit the simple explanation",
                "input_schema": _EXPLAIN_SCHEMA,
            }
        ],
        tool_choice={"type": "tool", "name": "submit"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return dict(block.input)
    raise ValueError("No tool_use block returned from explain-simple LLM")


@app.post("/research/explain-simple")
async def explain_simple(req: ExplainSimpleRequest) -> dict:
    """
    Takes a completed FinalReport and returns a plain-English 'explain for dummies'
    version using Claude Haiku. Funny, simple, zero jargon.
    """
    log.info("explain_simple_request", ticker=req.ticker, verdict=req.verdict)

    scores_text = "\n".join(
        f"  - {k.capitalize()}: {round(v * 100)}%" for k, v in req.signal_scores.items()
    )
    bull = "\n".join(f"  - {b}" for b in req.bull_case)
    bear = "\n".join(f"  - {b}" for b in req.bear_case)
    conflicts = (
        "\n".join(f"  - {c}" for c in req.conflicts) if req.conflicts else "  - None"
    )

    prompt = f"""You are explaining a stock research report to someone who:
- Has never invested before
- Thinks "bull" and "bear" are just animals
- Gets confused by words like "P/E ratio", "MACD", or "quantitative"
- Needs everything explained like they are 12 years old

The stock is: {req.ticker}
The verdict is: {req.verdict.replace("_", " ").upper()}
Conviction level: {req.conviction}

Here is the expert analysis you need to simplify:

Narrative: {req.narrative}

Reasons it might go UP:
{bull}

Reasons it might go DOWN:
{bear}

Where the experts disagreed:
{conflicts}

Expert scores (higher = better):
{scores_text}

Your job:
1. summary: Write 3-4 sentences explaining what this stock is, what the verdict means, and why — using ZERO finance jargon. Use simple analogies (like comparing the stock to a lemonade stand, a popular kid at school, a car, etc). Be a little funny but keep it genuinely useful.
2. verdict_explained: One sentence explaining what {req.verdict.replace("_", " ")} means in plain English (e.g. "Hold means: keep it if you have it, but don't buy more right now.")
3. bull_simple: The top reason to be optimistic, in one sentence a kid could understand.
4. bear_simple: The top reason to be worried, in one sentence a kid could understand.
5. bottom_line: One punchy sentence that is the absolute simplest take. Make it slightly funny.

Do NOT use these words: P/E, MACD, RSI, EMA, quant, composite, conviction, sentiment, fundamental, technical, valuation, equity, bullish, bearish, metric, indicator, thesis."""

    try:
        model = get_model_router().get_model("explain_simple")
        result = await _call_explain_llm(model, prompt)
        log.info("explain_simple_done", ticker=req.ticker)
        return result
    except Exception as exc:
        log.error("explain_simple_failed", ticker=req.ticker, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail={"error": str(exc), "ticker": req.ticker, "phase": "explain_simple"},
        )


@app.get("/usage")
async def usage(date: str | None = None) -> dict:
    """
    Return token usage and cost summary for a given date (YYYY-MM-DD).
    Defaults to today UTC when no date is provided.

    Response shape:
        {
          "date": "2026-04-05",
          "calls": 12,
          "total_tokens": 34567,
          "total_cost_usd": 0.142,
          "by_agent": {
            "synthesis": {
              "calls": 2, "input_tokens": 8000, "output_tokens": 3000,
              "cost_usd": 0.069, "model": "claude-sonnet-4-6"
            },
            ...
          }
        }
    """
    return await asyncio.to_thread(get_daily_summary, date)


# ── Saved tickers (personal watchlist) ────────────────────────────────────────
#
# user_id defaults to "default" for the current single-user setup.
# When auth is added, read user_id from the JWT/session instead.

_DEFAULT_USER = "default"


@app.get("/saved-tickers")
async def saved_tickers_list() -> dict:
    """Return the current user's saved tickers, most recently added first."""
    tickers = await asyncio.to_thread(get_tickers, _DEFAULT_USER)
    return {"tickers": tickers}


@app.get("/saved-tickers/details")
async def saved_tickers_details() -> dict:
    """
    Return saved tickers enriched with last analysis and current price.

    Response shape:
        {
          "tickers": [
            {
              "ticker": "AAPL",
              "added_at": "...",
              "last_verdict": "hold",
              "last_conviction": "low",
              "last_score": 0.50,
              "last_analyzed_at": "...",
              "price_at_analysis": 195.50,
              "current_price": 198.20,
              "price_change": 2.70,
              "price_change_pct": 0.0138
            },
            ...
          ]
        }
    """
    saved = await asyncio.to_thread(get_tickers, _DEFAULT_USER)

    async def _enrich(entry: dict) -> dict:
        ticker = entry["ticker"]
        last = await asyncio.to_thread(get_last_prediction, ticker)
        current_price: float | None = None
        try:
            analyst = await get_analyst_data(ticker)
            current_price = analyst.get("current_price")
        except Exception:
            pass

        price_at = last.get("price_at_prediction") if last else None
        price_change = (
            round(current_price - price_at, 4)
            if current_price is not None and price_at
            else None
        )
        price_change_pct = (
            round((current_price - price_at) / price_at, 6)
            if current_price is not None and price_at and price_at > 0
            else None
        )

        return {
            "ticker": ticker,
            "added_at": entry["added_at"],
            "last_verdict": last["verdict"] if last else None,
            "last_conviction": last["conviction"] if last else None,
            "last_score": last["composite_score"] if last else None,
            "last_analyzed_at": last["predicted_at"] if last else None,
            "price_at_analysis": price_at,
            "current_price": current_price,
            "price_change": price_change,
            "price_change_pct": price_change_pct,
        }

    results = await asyncio.gather(*[_enrich(e) for e in saved])
    return {"tickers": list(results)}


@app.post("/saved-tickers/{ticker}")
async def saved_tickers_add(ticker: str) -> dict:
    """Add a ticker to the current user's watchlist."""
    ticker = ticker.strip().upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")
    added = await asyncio.to_thread(add_ticker, ticker, _DEFAULT_USER)
    saved = await asyncio.to_thread(is_saved, ticker, _DEFAULT_USER)
    return {"ticker": ticker, "added": added, "saved": saved}


@app.delete("/saved-tickers/{ticker}")
async def saved_tickers_remove(ticker: str) -> dict:
    """Remove a ticker from the current user's watchlist."""
    ticker = ticker.strip().upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")
    removed = await asyncio.to_thread(remove_ticker, ticker, _DEFAULT_USER)
    return {"ticker": ticker, "removed": removed}
