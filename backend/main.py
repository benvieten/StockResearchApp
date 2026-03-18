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
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from backend.core.graph import run_research, stream_research

load_dotenv()
log = structlog.get_logger()

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


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

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.strip().upper()
        if not _TICKER_RE.match(v):
            raise ValueError(
                f"Invalid ticker '{v}'. Must be 1-5 uppercase letters (e.g. AAPL)."
            )
        return v


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
        report = await run_research(req.ticker)
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
            async for event in stream_research(ticker):
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
