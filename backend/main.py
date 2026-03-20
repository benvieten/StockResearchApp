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

import json
import re
from contextlib import asynccontextmanager

import structlog
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random

from backend.core.data_models import TraderProfile
from backend.core.graph import run_research, stream_research
from backend.core.model_router import get_model_router

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
            async for event in stream_research(ticker, trader_profile=req.trader_profile):
                data = json.dumps(event, default=str)
                yield f"data: {data}\n\n"
        except Exception as exc:
            log.error("stream_generator_error", ticker=ticker, error=str(exc))
            error_event = json.dumps({"type": "error", "error": str(exc), "ticker": ticker})
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


_EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "verdict_explained": {"type": "string"},
        "bull_simple": {"type": "string"},
        "bear_simple": {"type": "string"},
        "bottom_line": {"type": "string"},
    },
    "required": ["summary", "verdict_explained", "bull_simple", "bear_simple", "bottom_line"],
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
        tools=[{"name": "submit", "description": "Submit the simple explanation", "input_schema": _EXPLAIN_SCHEMA}],
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
    conflicts = "\n".join(f"  - {c}" for c in req.conflicts) if req.conflicts else "  - None"

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
        raise HTTPException(status_code=500, detail={"error": str(exc), "ticker": req.ticker, "phase": "explain_simple"})
