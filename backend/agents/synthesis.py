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

from backend.core.config import SynthesisConfig, get_config
from backend.core.data_models import (
    FinalReport,
    FundamentalSignal,
    QuantSignal,
    SectorSignal,
    SentimentSignal,
    TechnicalSignal,
    TraderProfile,
)
from backend.core.model_router import get_model_router
from backend.core.regime import RegimeSignal, get_regime

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


def apply_profile_adjustments(weights: dict[str, float], profile: TraderProfile) -> dict[str, float]:
    """
    Apply trader-profile multipliers on top of the regime-selected weights,
    then renormalise to sum to 1.0.

    Multipliers are applied additively per dimension (risk, horizon, goal) so
    that each dimension makes a proportional shift rather than compounding
    exponentially. The renormalisation step keeps all weights positive and
    summing to 1 regardless of input.
    """
    w = dict(weights)

    # ── Risk tolerance ────────────────────────────────────────────────────────
    if profile.risk_tolerance == "conservative":
        w["fundamental"] *= 1.25   # trust quality metrics more
        w["technical"]   *= 0.80   # reduce reliance on momentum signals
        w["sentiment"]   *= 0.65   # crowd sentiment is noise for conservative traders
    elif profile.risk_tolerance == "aggressive":
        w["technical"]   *= 1.25   # momentum and timing matter more
        w["sentiment"]   *= 1.20   # crowd flow is an edge for aggressive traders
        w["fundamental"] *= 0.85   # willing to accept higher valuation risk

    # ── Time horizon ──────────────────────────────────────────────────────────
    if profile.time_horizon == "long_term":
        w["fundamental"] *= 1.20   # earnings quality compounds over time
        w["technical"]   *= 0.70   # short-term chart noise is irrelevant
        w["sentiment"]   *= 0.70   # Reddit sentiment doesn't matter in 3 years
    elif profile.time_horizon == "short_term":
        w["technical"]   *= 1.35   # chart setups drive near-term price action
        w["sentiment"]   *= 1.25   # retail flow matters over days to weeks
        w["fundamental"] *= 0.65   # fundamentals take time to be priced in

    # ── Goal ──────────────────────────────────────────────────────────────────
    if profile.goal == "income":
        w["fundamental"] *= 1.15   # dividend sustainability lives in fundamentals
        w["sentiment"]   *= 0.80
    elif profile.goal == "preservation":
        w["fundamental"] *= 1.30   # balance-sheet strength is paramount
        w["sector"]      *= 1.10   # defensive sector positioning matters
        w["technical"]   *= 0.70
        w["sentiment"]   *= 0.55
    elif profile.goal == "speculation":
        w["technical"]   *= 1.25
        w["sentiment"]   *= 1.35   # hype and narrative drive speculative moves
        w["quant"]       *= 1.15   # momentum factor is key for spec plays
        w["fundamental"] *= 0.60   # valuation rarely matters for speculative names

    # ── Renormalise ───────────────────────────────────────────────────────────
    total = sum(w.values())
    if total == 0:
        return weights  # guard against degenerate case
    return {k: v / total for k, v in w.items()}


def select_weights(regime: RegimeSignal, cfg_weights: dict[str, float], regime_weights: dict[str, dict[str, float]]) -> dict[str, float]:
    """
    Return the appropriate signal weight dict for the current market regime.

    Falls back to the default cfg_weights if:
    - regime_weights is empty (not configured)
    - the regime label has no preset
    - regime confidence is below 0.55 (too uncertain to deviate from default)
    """
    if not regime_weights or regime.confidence < 0.55:
        return cfg_weights
    preset = regime_weights.get(regime.regime)
    if preset is None:
        return cfg_weights
    return preset


def score_to_verdict(score: float, thresholds: SynthesisConfig) -> str:
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


def score_to_conviction(score: float, full_consensus: bool = False) -> str:
    """
    High conviction for extreme scores, low for scores near 0.5.

    If all agents agree direction (full_consensus=True), conviction is capped
    at "medium" regardless of the composite score. Unanimous agent agreement
    typically means the information is already priced in — the crowd has seen
    everything our agents see, so our edge is reduced.
    """
    distance = abs(score - 0.5)
    if distance >= 0.20:
        level = "high"
    elif distance >= 0.10:
        level = "medium"
    else:
        level = "low"

    if full_consensus and level == "high":
        return "medium"
    return level


def check_full_consensus(signal_scores: dict[str, float]) -> bool:
    """
    Return True if all available agent scores agree on the same directional half.

    'Agreement' means all scores are either > 0.60 (bullish) or all < 0.40
    (bearish). Scores in the 0.40–0.60 range are neutral and do not count
    toward consensus in either direction.
    """
    scores = [v for v in signal_scores.values() if v is not None]
    if len(scores) < 3:
        return False
    all_bullish = all(s > 0.60 for s in scores)
    all_bearish = all(s < 0.40 for s in scores)
    return all_bullish or all_bearish


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
    trader_profile: TraderProfile | None = None,
    full_consensus: bool = False,
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

    def _fmt(v: float | None, decimals: int = 2) -> str:
        return f"{v:.{decimals}f}" if v is not None else "n/a"

    quant_text = (
        f"  Composite: {quant.composite_score:.2f}\n"
        f"  Factors: momentum={_fmt(quant.factor_breakdown.get('momentum'))}, "
        f"quality={_fmt(quant.factor_breakdown.get('quality'))}, "
        f"value={_fmt(quant.factor_breakdown.get('value'))}, "
        f"low_vol={_fmt(quant.factor_breakdown.get('low_vol'))}\n"
        f"  Statistical: return_zscore={_fmt(quant.factor_breakdown.get('return_zscore'))} "
        f"(>2 extended, <-2 oversold), "
        f"volume_ratio={_fmt(quant.factor_breakdown.get('volume_ratio'))} "
        f"(1.0=normal), "
        f"bb_pct={_fmt(quant.factor_breakdown.get('bb_percentile'))} "
        f"(0=lower band, 1=upper), "
        f"rsi_pct={_fmt(quant.factor_breakdown.get('rsi_percentile'))} "
        f"(percentile rank in 1y history)"
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

    # ── Trader profile context block ──────────────────────────────────────────
    if trader_profile:
        _horizon_map = {
            "short_term": "Short-term (days to weeks)",
            "medium_term": "Medium-term (weeks to months)",
            "long_term": "Long-term (1+ years)",
        }
        _goal_map = {
            "growth": "Capital growth",
            "income": "Income / dividends",
            "preservation": "Capital preservation",
            "speculation": "High-risk speculation",
        }
        _risk_guidance = {
            "conservative": (
                "Bias your narrative toward downside risk and capital protection. "
                "If the verdict is borderline, lean toward 'hold' over 'buy'. "
                "Highlight risks prominently in the bear case."
            ),
            "moderate": (
                "Balance upside opportunity against downside risk. "
                "Present both sides evenhandedly."
            ),
            "aggressive": (
                "Highlight upside catalysts and momentum. "
                "This trader accepts higher drawdown risk in pursuit of returns. "
                "Be direct about the opportunity without softening the conviction."
            ),
        }
        _horizon_guidance = {
            "short_term": "Focus the narrative on near-term price catalysts (earnings, technicals, sentiment). Fundamentals are secondary unless they are an immediate catalyst.",
            "medium_term": "Balance near-term momentum with underlying business quality. Note any upcoming catalysts in the 1–12 month window.",
            "long_term": "Ground the narrative in business fundamentals and competitive positioning. Short-term volatility is noise — frame risk around permanent capital loss, not drawdowns.",
        }
        _exp_guidance = {
            "beginner": "Use plain language. Avoid jargon — if you must use a term like P/E, explain it in one clause.",
            "intermediate": "Standard financial language is fine. Briefly explain any specialist terminology.",
            "experienced": "Full financial vocabulary. Be concise — this reader doesn't need hand-holding.",
        }
        profile_block = f"""
=== TRADER PROFILE ===
Risk tolerance: {trader_profile.risk_tolerance.replace("_", " ").title()}
Time horizon:   {_horizon_map[trader_profile.time_horizon]}
Goal:           {_goal_map[trader_profile.goal]}
Experience:     {trader_profile.experience.title()}

Profile guidance (shape your narrative accordingly):
- Risk: {_risk_guidance[trader_profile.risk_tolerance]}
- Horizon: {_horizon_guidance[trader_profile.time_horizon]}
- Language: {_exp_guidance[trader_profile.experience]}
"""
    else:
        profile_block = ""

    prompt = f"""You are a senior equity analyst synthesising multiple research signals for {ticker}.
{profile_block}
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

=== CONSENSUS WARNING ===
{"ALL AGENTS AGREE on direction. This is a RED FLAG, not a green light. When every signal points the same way, the information is almost certainly already priced into the market — retail and institutional players have seen the same data. Unanimous consensus historically precedes disappointment. You MUST include this risk in the bear_case. The narrative should acknowledge that the setup looks crowded and that mean-reversion risk is elevated." if full_consensus else "Agents show some disagreement — this is normal. Note genuine conflicts in the conflicts list."}

=== SENTIMENT AS RISK GUIDANCE ===
High retail sentiment scores are a contrary indicator at extremes. If the sentiment
score is above 0.65, treat it as a warning that retail optimism may be excessive —
note this explicitly in the bear_case even if other signals are bullish.
Crowd sentiment peaks at market tops. The question is not "is sentiment bullish?"
but "is the market already pricing in that optimism?"

Your task — synthesise all signals into a final investment opinion:
1. narrative: 3-5 sentence investment thesis (substantive, not generic)
2. bull_case: 3-5 bullet points supporting a positive view
3. bear_case: 3-5 bullet points supporting a negative view — always include at least
   one risk related to consensus/sentiment if scores are uniformly high
4. conflicts: list any significant disagreements between agents
   — if full consensus, note "All agents agree — crowded setup, mean-reversion risk"

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
    regime: RegimeSignal | None = None,
    trader_profile: TraderProfile | None = None,
) -> FinalReport:
    cfg = get_config()
    model = get_model_router().get_model("synthesis")

    log.info("synthesis_agent_start", ticker=ticker, model=model)

    if regime is None:
        regime = await get_regime()

    # Step 1: select regime-conditioned weight preset
    weights = select_weights(regime, cfg.signal_weights, cfg.regime_signal_weights)

    # Step 2: apply trader-profile multipliers on top, then renormalise
    if trader_profile is not None:
        weights = apply_profile_adjustments(weights, trader_profile)

    log.info(
        "synthesis_weights_final",
        regime=regime.regime,
        confidence=round(regime.confidence, 3),
        profile=trader_profile.model_dump() if trader_profile else None,
        weights={k: round(v, 3) for k, v in weights.items()},
    )

    signal_scores = normalise_signals(fundamental, technical, quant, sector, sentiment)
    composite = compute_composite(signal_scores, weights)
    full_consensus = check_full_consensus(signal_scores)
    verdict = score_to_verdict(composite, cfg.synthesis)
    conviction = score_to_conviction(composite, full_consensus=full_consensus)

    if full_consensus:
        log.info("synthesis_full_consensus_detected", ticker=ticker,
                 scores={k: round(v, 3) for k, v in signal_scores.items()},
                 conviction_capped=conviction)

    report = await _call_llm(
        model, ticker, fundamental, technical, quant, sector, sentiment,
        signal_scores, verdict, conviction,
        trader_profile=trader_profile,
        full_consensus=full_consensus,
    )
    log.info(
        "synthesis_agent_done",
        ticker=ticker, verdict=verdict, conviction=conviction,
        regime=regime.regime,
        profile_risk=trader_profile.risk_tolerance if trader_profile else None,
    )
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
