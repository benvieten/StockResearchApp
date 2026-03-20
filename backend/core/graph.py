"""
LangGraph research pipeline.

Five specialist agents (fundamental, technical, quant, sector, sentiment) fan
out in parallel from a single entry node, then join into the synthesis node
which produces the FinalReport.

ResearchState uses Annotated[list, operator.add] on agent_signals so that
parallel nodes accumulate results instead of silently overwriting each other.

Each node emits custom stream events via get_stream_writer() so the FastAPI
SSE endpoint can push real-time progress to the frontend.

Public API:
    report = await run_research("AAPL")
    async for event in stream_research("AAPL"):
        ...
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, AsyncIterator, TypedDict

import structlog
from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph

from backend.agents import fundamental, quant, sector, sentiment, technical
from backend.agents import synthesis as synthesis_agent
from backend.core.data_models import FinalReport, TraderProfile
from backend.core.regime import RegimeSignal, get_regime

log = structlog.get_logger()


# ── State schema ───────────────────────────────────────────────────────────────


class ResearchState(TypedDict):
    ticker: str
    # Annotated[list, operator.add] is REQUIRED — without it, parallel agent
    # nodes silently overwrite each other (LangGraph superstep behaviour).
    agent_signals: Annotated[list, operator.add]
    final_report: dict | None
    regime: RegimeSignal | None          # pre-fetched once, shared by technical + synthesis
    trader_profile: TraderProfile | None  # passed in from the request, forwarded to synthesis


# ── Node functions ─────────────────────────────────────────────────────────────


async def run_fundamental(state: ResearchState) -> dict:
    ticker = state["ticker"]
    writer = get_stream_writer()
    writer({"type": "agent_start", "agent": "fundamental"})
    try:
        signal = await fundamental.run(ticker)
        writer({"type": "agent_complete", "agent": "fundamental", "signal": signal.model_dump()})
        return {"agent_signals": [{"agent": "fundamental", "signal": signal}]}
    except Exception as exc:
        log.error("fundamental_agent_failed", ticker=ticker, error=str(exc))
        writer({"type": "agent_error", "agent": "fundamental", "error": str(exc)})
        return {"agent_signals": []}


async def run_technical(state: ResearchState) -> dict:
    ticker = state["ticker"]
    writer = get_stream_writer()
    writer({"type": "agent_start", "agent": "technical"})
    try:
        signal = await technical.run(ticker, regime=state.get("regime"))
        writer({"type": "agent_complete", "agent": "technical", "signal": signal.model_dump()})
        return {"agent_signals": [{"agent": "technical", "signal": signal}]}
    except Exception as exc:
        log.error("technical_agent_failed", ticker=ticker, error=str(exc))
        writer({"type": "agent_error", "agent": "technical", "error": str(exc)})
        return {"agent_signals": []}


async def run_quant(state: ResearchState) -> dict:
    ticker = state["ticker"]
    writer = get_stream_writer()
    writer({"type": "agent_start", "agent": "quant"})
    try:
        signal = await quant.run(ticker)
        writer({"type": "agent_complete", "agent": "quant", "signal": signal.model_dump()})
        return {"agent_signals": [{"agent": "quant", "signal": signal}]}
    except Exception as exc:
        log.error("quant_agent_failed", ticker=ticker, error=str(exc))
        writer({"type": "agent_error", "agent": "quant", "error": str(exc)})
        return {"agent_signals": []}


async def run_sector(state: ResearchState) -> dict:
    ticker = state["ticker"]
    writer = get_stream_writer()
    writer({"type": "agent_start", "agent": "sector"})
    try:
        signal = await sector.run(ticker)
        writer({"type": "agent_complete", "agent": "sector", "signal": signal.model_dump()})
        return {"agent_signals": [{"agent": "sector", "signal": signal}]}
    except Exception as exc:
        log.error("sector_agent_failed", ticker=ticker, error=str(exc))
        writer({"type": "agent_error", "agent": "sector", "error": str(exc)})
        return {"agent_signals": []}


async def run_sentiment(state: ResearchState) -> dict:
    ticker = state["ticker"]
    writer = get_stream_writer()
    writer({"type": "agent_start", "agent": "sentiment"})
    try:
        signal = await sentiment.run(ticker)
        writer({"type": "agent_complete", "agent": "sentiment", "signal": signal.model_dump()})
        return {"agent_signals": [{"agent": "sentiment", "signal": signal}]}
    except Exception as exc:
        log.error("sentiment_agent_failed", ticker=ticker, error=str(exc))
        writer({"type": "agent_error", "agent": "sentiment", "error": str(exc)})
        return {"agent_signals": []}


async def run_synthesis(state: ResearchState) -> dict:
    ticker = state["ticker"]
    writer = get_stream_writer()
    writer({"type": "agent_start", "agent": "synthesis"})

    signals: dict[str, Any] = {
        item["agent"]: item["signal"] for item in state["agent_signals"]
    }

    fund_sig = signals.get("fundamental")
    tech_sig = signals.get("technical")
    quant_sig = signals.get("quant")
    sect_sig = signals.get("sector")
    sent_sig = signals.get("sentiment")

    if not all([fund_sig, tech_sig, quant_sig, sect_sig, sent_sig]):
        missing = [
            name for name, sig in [
                ("fundamental", fund_sig), ("technical", tech_sig),
                ("quant", quant_sig), ("sector", sect_sig), ("sentiment", sent_sig),
            ] if sig is None
        ]
        log.warning("synthesis_missing_signals", ticker=ticker, missing=missing)

    try:
        report = await synthesis_agent.run(
            ticker, fund_sig, tech_sig, quant_sig, sect_sig, sent_sig,
            regime=state.get("regime"),
            trader_profile=state.get("trader_profile"),
        )
        writer({"type": "agent_complete", "agent": "synthesis", "signal": report.model_dump()})
        return {"final_report": report.model_dump()}
    except Exception as exc:
        log.error("synthesis_agent_failed", ticker=ticker, error=str(exc))
        writer({"type": "agent_error", "agent": "synthesis", "error": str(exc)})
        raise


# ── Graph construction ─────────────────────────────────────────────────────────


def _build_graph() -> Any:
    builder = StateGraph(ResearchState)

    builder.add_node("fundamental", run_fundamental)
    builder.add_node("technical", run_technical)
    builder.add_node("quant", run_quant)
    builder.add_node("sector", run_sector)
    builder.add_node("sentiment", run_sentiment)
    builder.add_node("synthesis", run_synthesis)

    # Fan-out: all 5 agents start in parallel
    builder.set_entry_point("fundamental")
    builder.set_entry_point("technical")
    builder.set_entry_point("quant")
    builder.set_entry_point("sector")
    builder.set_entry_point("sentiment")

    # Fan-in: all 5 converge on synthesis
    builder.add_edge("fundamental", "synthesis")
    builder.add_edge("technical", "synthesis")
    builder.add_edge("quant", "synthesis")
    builder.add_edge("sector", "synthesis")
    builder.add_edge("sentiment", "synthesis")

    builder.add_edge("synthesis", END)

    return builder.compile()


_graph = None


def _get_graph() -> Any:
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ── Public entry points ────────────────────────────────────────────────────────


async def run_research(ticker: str, trader_profile: TraderProfile | None = None) -> FinalReport:
    """
    Run the full multi-agent research pipeline for a ticker.

    Returns a FinalReport. Agent failures are logged and synthesis proceeds
    with available signals.
    """
    log.info("graph_start", ticker=ticker)
    graph = _get_graph()

    regime = await get_regime()
    log.info("graph_regime_fetched", ticker=ticker, regime=regime.regime, confidence=regime.confidence)

    initial_state: ResearchState = {
        "ticker": ticker,
        "agent_signals": [],
        "final_report": None,
        "regime": regime,
        "trader_profile": trader_profile,
    }

    final_state = await graph.ainvoke(initial_state)

    report_dict = final_state.get("final_report")
    if report_dict is None:
        raise RuntimeError(f"Pipeline produced no final report for {ticker}")

    report = FinalReport.model_validate(report_dict)
    log.info("graph_done", ticker=ticker, verdict=report.verdict)
    return report


async def stream_research(ticker: str, trader_profile: TraderProfile | None = None) -> AsyncIterator[dict]:
    """
    Run the pipeline and yield custom stream events as they are emitted.

    Yields dicts with at minimum: {"type": str, "agent": str, ...}
    Final event is always {"type": "done", "report": {...}} or
    {"type": "error", "error": str}.
    """
    log.info("graph_stream_start", ticker=ticker)
    graph = _get_graph()

    regime = await get_regime()
    log.info("graph_regime_fetched", ticker=ticker, regime=regime.regime, confidence=regime.confidence)

    initial_state: ResearchState = {
        "ticker": ticker,
        "agent_signals": [],
        "final_report": None,
        "regime": regime,
        "trader_profile": trader_profile,
    }

    # Emit regime immediately so the frontend can display it before agents start
    yield {"type": "regime", "regime": regime.model_dump()}

    try:
        final_state = None
        async for mode, payload in graph.astream(
            initial_state, stream_mode=["custom", "updates"]
        ):
            if mode == "custom":
                yield payload
            elif mode == "updates" and "synthesis" in payload:
                # Capture the final report from the synthesis node update
                final_state = payload["synthesis"]

        # Emit pipeline_complete with the final report for the frontend
        if final_state and final_state.get("final_report"):
            yield {
                "type": "pipeline_complete",
                "report": final_state["final_report"],
                "ticker": ticker,
            }
        else:
            yield {"type": "done", "ticker": ticker}
    except Exception as exc:
        log.error("graph_stream_error", ticker=ticker, error=str(exc))
        yield {"type": "error", "error": str(exc), "ticker": ticker}
