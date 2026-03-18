"""
Pydantic v2 schemas for all agent signals and the final research report.

Rules:
- All score fields in [0, 1] range use ge/le constraints enforced at validation time.
- Sentiment scores use [-1, 1] (negative = bearish, positive = bullish).
- Every LLM-backed signal has a `reasoning` field (required) and `data_quality` field.
- QuantSignal has no LLM call — reasoning is optional.
- Literals define the allowed string values for categorical fields.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# ── Shared type aliases ────────────────────────────────────────────────────────

DataQuality = Literal["full", "partial"]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]      # [0, 1]
SentimentFloat = Annotated[float, Field(ge=-1.0, le=1.0)]  # [-1, 1]


# ── Agent signal models ────────────────────────────────────────────────────────


class TechnicalSignal(BaseModel):
    reasoning: str
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: UnitFloat
    key_levels: dict[str, float]
    indicator_summary: str
    raw_indicators: dict[str, float | None]
    data_quality: DataQuality


class FundamentalSignal(BaseModel):
    reasoning: str
    quality_score: UnitFloat
    valuation_verdict: Literal["undervalued", "fair", "overvalued"]
    key_flags: list[str]
    metrics: dict[str, float | None]
    data_quality: DataQuality


class QuantSignal(BaseModel):
    # No LLM call — pure computation, so reasoning is optional
    reasoning: str | None = None
    composite_score: UnitFloat
    factor_breakdown: dict[str, float | None]
    data_quality: DataQuality


class SectorSignal(BaseModel):
    reasoning: str
    sector: str                    # e.g. "Technology"
    relative_performance: Literal["outperforming", "inline", "underperforming"]
    sector_etf: str                # e.g. "XLK"
    peer_comparison: dict[str, float]   # ticker → 12M return
    data_quality: DataQuality


class SentimentSignal(BaseModel):
    reasoning: str
    raw_score: SentimentFloat       # unweighted aggregate: -1 (bearish) to 1 (bullish)
    adjusted_score: SentimentFloat  # after discounting bot-flagged content
    bot_risk: Literal["low", "medium", "high"]
    source_breakdown: dict[str, float]   # per-source scores
    narrative_themes: list[str]
    mention_volume: int
    data_quality: DataQuality


# ── Final output ───────────────────────────────────────────────────────────────


class FinalReport(BaseModel):
    ticker: str
    verdict: Literal["strong_buy", "buy", "hold", "sell", "strong_sell"]
    conviction: Literal["high", "medium", "low"]
    narrative: str
    bull_case: list[str]
    bear_case: list[str]
    conflicts: list[str]         # where agents disagree
    signal_scores: dict[str, float]  # normalized 0-1 score per agent
    generated_at: str
