"""
Synthesis agent.

Receives all five agent signals, computes a weighted composite score,
then calls claude-sonnet to produce a final investment opinion with
bull/bear case and conflict identification.

Usage:
    python -m backend.agents.synthesis AAPL
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
from backend.core.data_models import (
    FinalReport,
    FundamentalSignal,
    QuantSignal,
    SectorSignal,
    SentimentSignal,
    TechnicalSignal,
)

log = structlog.get_logger()

load_dotenv()
_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


# ── Score normalisation ────────────────────────────────────────────────────────


def normalise_signals(
    fundamental: FundamentalSignal | None,
    technical: TechnicalSignal | None,
    quant: QuantSignal | None,
    sector: SectorSignal | None,
    sentiment: SentimentSignal | None,
) -> dict[str, float]:
    """
    Map each agent's primary metric to a normalised [0, 1] score.

    Missing (None) signals default to 0.5 (neutral) and are included
    so signal_scores always lists all five agents.

    - fundamental: quality_score (already [0, 1])
    - technical:   confidence × direction_sign (bullish=1, bearish=0, neutral=0.5)
    - quant:       composite_score (already [0, 1])
    - sector:      relative_performance mapped to 0.75 / 0.5 / 0.25
    - sentiment:   adjusted_score remapped from [-1, 1] to [0, 1]
    """
    # Technical direction weighting
    if technical is not None:
        direction_map = {"bullish": 1.0, "neutral": 0.5, "bearish": 0.0}
        direction_val = direction_map[technical.direction]
        tech_score = 0.5 + (direction_val - 0.5) * technical.confidence
    else:
        tech_score = 0.5

    # Sector relative performance
    if sector is not None:
        perf_map = {"outperforming": 0.75, "inline": 0.5, "underperforming": 0.25}
        sector_score = perf_map[sector.relative_performance]
    else:
        sector_score = 0.5

    # Sentiment: remap [-1, 1] → [0, 1]
    sentiment_score = (sentiment.adjusted_score + 1.0) / 2.0 if sentiment is not None else 0.5

    return {
        "fundamental": fundamental.quality_score if fundamental is not None else 0.5,
        "technical": tech_score,
        "quant": quant.composite_score if quant is not None else 0.5,
        "sector": sector_score,
        "sentiment": sentiment_score,
    }


def compute_composite(signal_scores: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted average of signal scores. Missing weights default to 0."""
    total_weight = 0.0
    weighted_sum = 0.0
    for name, score in signal_scores.items():
        w = weights.get(name, 0.0)
        weighted_sum += score * w
        total_weight += w
    if total_weight == 0:
        return 0.5
    return weighted_sum / total_weight


def score_to_verdict(score: float, thresholds: object) -> str:
    """Map composite score to verdict string using config thresholds."""
    if score >= thresholds.strong_buy_threshold:
        return "strong_buy"
    if score >= thresholds.buy_threshold:
        return "buy"
    if score >= thresholds.hold_threshold:
        return "hold"
    if score >= thresholds.sell_threshold:
        return "sell"
    return "strong_sell"


def score_to_conviction(score: float) -> str:
    """High conviction for extreme scores, low for scores near 0.5."""
    distance = abs(score - 0.5)
    if distance >= 0.20:
        return "high"
    if distance >= 0.10:
        return "medium"
    return "low"


# ── LLM call ───────────────────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=16) + wait_random(-0.5, 0.5),
    reraise=True,
)
async def _call_llm(
    model: str,
    ticker: str,
    fundamental: FundamentalSignal | None,
    technical: TechnicalSignal | None,
    quant: QuantSignal | None,
    sector: SectorSignal | None,
    sentiment: SentimentSignal | None,
    signal_scores: dict[str, float],
    verdict: str,
    conviction: str,
) -> FinalReport:
    client = _get_client()

    def _pct(v: float) -> str:
        return f"{v * 100:.1f}%"

    fundamental_flags = ", ".join(fundamental.key_flags[:4]) if fundamental else "unavailable"
    peer_top = sorted(sector.peer_comparison.items(), key=lambda x: x[1], reverse=True)[:3] if sector else []
    peer_str = ", ".join(f"{t}: {_pct(r)}" for t, r in peer_top) or "none"

    fund_text = (
        f"  Verdict: {fundamental.valuation_verdict} | Quality: {fundamental.quality_score:.2f}\n"
        f"  Key flags: {fundamental_flags}\n"
        f"  Reasoning: {fundamental.reasoning}"
    ) if fundamental else "  DATA UNAVAILABLE — signal failed"

    tech_text = (
        f"  Direction: {technical.direction} | Confidence: {technical.confidence:.2f}\n"
        f"  Summary: {technical.indicator_summary}"
    ) if technical else "  DATA UNAVAILABLE — signal failed"

    quant_text = (
        f"  Composite: {quant.composite_score:.2f}\n"
        f"  Factors: momentum={quant.factor_breakdown.get('momentum')}, "
        f"quality={quant.factor_breakdown.get('quality')}, "
        f"value={quant.factor_breakdown.get('value')}, low_vol={quant.factor_breakdown.get('low_vol')}"
    ) if quant else "  DATA UNAVAILABLE — signal failed"

    sector_text = (
        f"  Sector: {sector.sector} | ETF: {sector.sector_etf}\n"
        f"  Relative performance: {sector.relative_performance}\n"
        f"  Top peers: {peer_str}"
    ) if sector else "  DATA UNAVAILABLE — signal failed"

    sent_text = (
        f"  Raw: {sentiment.raw_score:.2f} → Adjusted: {sentiment.adjusted_score:.2f} (bot risk: {sentiment.bot_risk})\n"
        f"  Themes: {', '.join(sentiment.narrative_themes[:4])}\n"
        f"  Reasoning: {sentiment.reasoning}"
    ) if sentiment else "  DATA UNAVAILABLE — signal failed"

    prompt = f"""You are a senior equity analyst synthesising multiple research signals for {ticker}.

=== AGENT SIGNALS ===

FUNDAMENTAL (score {signal_scores['fundamental']:.2f})
{fund_text}

TECHNICAL (score {signal_scores['technical']:.2f})
{tech_text}

QUANT (score {signal_scores['quant']:.2f})
{quant_text}

SECTOR (score {signal_scores['sector']:.2f})
{sector_text}

SENTIMENT (score {signal_scores['sentiment']:.2f})
{sent_text}

=== COMPOSITE ===
Pre-computed verdict: {verdict} | Conviction: {conviction}
Signal scores: {', '.join(f'{k}={v:.2f}' for k, v in signal_scores.items())}

Your task — synthesise all signals into a final investment opinion:
1. narrative: 3-5 sentence investment thesis (substantive, not generic)
2. bull_case: 3-5 bullet points supporting a positive view
3. bear_case: 3-5 bullet points supporting a negative view
4. conflicts: list any significant disagreements between agents (e.g. bullish technical but bearish sentiment)
   — if agents agree, return an empty list

Use the pre-computed verdict and conviction — do not change them.
Focus your narrative on the *why*, not just restating the scores."""

    schema = FinalReport.model_json_schema()
    schema.pop("$defs", None)
    schema.pop("title", None)

    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        tools=[{"name": "submit", "description": "Submit the final report", "input_schema": schema}],
        tool_choice={"type": "tool", "name": "submit"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use":
            data = dict(block.input)
            data["ticker"] = ticker
            data["verdict"] = verdict
            data["conviction"] = conviction
            data["signal_scores"] = signal_scores
            data["generated_at"] = datetime.now(timezone.utc).isoformat()
            return FinalReport.model_validate(data)

    raise ValueError("No tool_use block in synthesis LLM response")


# ── Public async entry point ───────────────────────────────────────────────────


async def run(
    ticker: str,
    fundamental: FundamentalSignal | None,
    technical: TechnicalSignal | None,
    quant: QuantSignal | None,
    sector: SectorSignal | None,
    sentiment: SentimentSignal | None,
) -> FinalReport:
    cfg = get_config()
    model = cfg.anthropic.models["synthesis"]

    log.info("synthesis_agent_start", ticker=ticker, model=model)

    signal_scores = normalise_signals(fundamental, technical, quant, sector, sentiment)
    composite = compute_composite(signal_scores, cfg.signal_weights)
    verdict = score_to_verdict(composite, cfg.synthesis)
    conviction = score_to_conviction(composite)

    report = await _call_llm(
        model, ticker, fundamental, technical, quant, sector, sentiment,
        signal_scores, verdict, conviction,
    )
    log.info("synthesis_agent_done", ticker=ticker, verdict=verdict, conviction=conviction)
    return report


# ── CLI (runs full pipeline to get signals) ────────────────────────────────────


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        from backend.agents import fundamental, technical, quant, sector, sentiment

        fund_sig, tech_sig, quant_sig, sect_sig, sent_sig = await asyncio.gather(
            fundamental.run(ticker),
            technical.run(ticker),
            quant.run(ticker),
            sector.run(ticker),
            sentiment.run(ticker),
        )
        report = await run(ticker, fund_sig, tech_sig, quant_sig, sect_sig, sent_sig)
        print(report.model_dump_json(indent=2))

    asyncio.run(main())
