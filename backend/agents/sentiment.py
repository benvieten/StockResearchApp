"""
Sentiment agent.

Applies bot detection heuristics to Reddit posts, then calls claude-sonnet
to score sentiment across all sources and identify narrative themes.

Usage:
    python -m backend.agents.sentiment AAPL
"""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict

import structlog
from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random

from backend.core.data_models import SentimentSignal
from backend.core.model_router import get_model_router
from backend.core.usage import log_usage
from backend.data._cache import load_cache, save_cache
from backend.data.fear_greed import get_fear_greed
from backend.data.news import get_news
from backend.data.price import get_short_interest
from backend.data.reddit import get_reddit_posts

log = structlog.get_logger()

load_dotenv()
_client: AsyncAnthropic | None = None

# Bot detection thresholds
_MIN_ACCOUNT_AGE_DAYS = 30
_SUSPICIOUS_UPVOTE_RATIO = 0.55
_SUSPICIOUS_MIN_SCORE = 100
_SPAM_WINDOW_SECONDS = 6 * 3600  # 6-hour window for burst detection
_SPAM_POST_THRESHOLD = 3

# Hype spike thresholds.
# Data collection ceiling: ~200 Reddit posts (50/sub × 4 subs) + ~30 news = ~230 max.
# A mention_volume near the ceiling means all sources are saturated —
# the stock is being discussed everywhere, which is historically a top signal.
_HYPE_VOLUME_MEDIUM = 80  # elevated but not unusual for large-caps
_HYPE_VOLUME_HIGH = 140  # most sources returning near-max results
_HYPE_VOLUME_EXTREME = 200  # essentially full saturation across all sources


def compute_hype_factor(mention_volume: int, adjusted_score: float) -> float:
    """
    Return a compression factor [0.0, 0.45] to apply to a bullish adjusted_score
    when mention volume is abnormally high.

    Rationale (from r/ai_trading thread): crowd euphoria at high mention volume
    is a contrary indicator — the information is already priced in and retail
    sentiment peaks near market tops. We only discount bullish extremes;
    fear spikes (negative scores) are not discounted because panic is a
    more reliable signal than euphoria.

    The factor is zero when:
    - adjusted_score <= 0.25 (neutral or bearish — no discount applies)
    - mention_volume < _HYPE_VOLUME_MEDIUM (normal activity)

    Returns a factor f such that new_score = adjusted_score * (1 - f).
    """
    if adjusted_score <= 0.25:
        return 0.0

    if mention_volume >= _HYPE_VOLUME_EXTREME:
        base = 0.45
    elif mention_volume >= _HYPE_VOLUME_HIGH:
        base = 0.30
    elif mention_volume >= _HYPE_VOLUME_MEDIUM:
        base = 0.15
    else:
        return 0.0

    # Scale the discount by how bullish the score is — a score of 0.9 gets
    # a larger discount than a score of 0.3, because crowd overreaction is
    # more dangerous at extremes.
    bullish_intensity = (adjusted_score - 0.25) / 0.75  # 0.0 → 1.0
    return round(base * bullish_intensity, 4)


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


# ── Bot heuristics (unit-tested independently) ─────────────────────────────────


def apply_bot_heuristics(posts: list[dict]) -> list[dict]:
    """
    Apply three bot/manipulation detection rules to Reddit posts.

    Each returned post has all original fields plus:
    - bot_flag: True if account is new or author is spamming
    - suspicious_flag: True if upvote pattern looks manipulated

    Rules:
    1. Account age < 30 days at post time → bot_flag = True
    2. 3+ posts from same author within 6h → bot_flag = True for all
    3. upvote_ratio < 0.55 AND score > 100 → suspicious_flag = True
    """
    results: list[dict] = []

    # Pass 1: per-post rules
    for post in posts:
        result = dict(post)
        result["bot_flag"] = False
        result["suspicious_flag"] = False

        # Rule 1: account age
        author_utc = post.get("author_created_utc")
        post_utc = post.get("post_created_utc")
        if author_utc is not None and post_utc is not None:
            age_days = (post_utc - author_utc) / 86400.0
            if age_days < _MIN_ACCOUNT_AGE_DAYS:
                result["bot_flag"] = True

        # Rule 3: suspicious voting pattern
        ratio = post.get("upvote_ratio")
        score = post.get("score", 0)
        if (
            ratio is not None
            and ratio < _SUSPICIOUS_UPVOTE_RATIO
            and score > _SUSPICIOUS_MIN_SCORE
        ):
            result["suspicious_flag"] = True

        results.append(result)

    # Pass 2: spam burst detection — group by author, find 3+ posts in 6h window
    author_indices: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for i, post in enumerate(posts):
        author = post.get("author", "")
        post_utc = post.get("post_created_utc")
        if author and post_utc is not None:
            author_indices[author].append((i, float(post_utc)))

    for author, idx_times in author_indices.items():
        if len(idx_times) < _SPAM_POST_THRESHOLD:
            continue
        sorted_posts = sorted(idx_times, key=lambda x: x[1])
        # Sliding window: check every consecutive triple
        for j in range(len(sorted_posts) - _SPAM_POST_THRESHOLD + 1):
            earliest_t = sorted_posts[j][1]
            latest_t = sorted_posts[j + _SPAM_POST_THRESHOLD - 1][1]
            if (latest_t - earliest_t) <= _SPAM_WINDOW_SECONDS:
                for k in range(j, j + _SPAM_POST_THRESHOLD):
                    idx = sorted_posts[k][0]
                    results[idx]["bot_flag"] = True

    return results


# ── LLM call ───────────────────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=16) + wait_random(-0.5, 0.5),
    reraise=True,
)
async def _call_llm(
    model: str,
    ticker: str,
    clean_posts: list[dict],
    flagged_posts: list[dict],
    news_headlines: list[str],
    mention_volume: int,
    short_interest: dict | None = None,
    fear_greed: dict | None = None,
) -> SentimentSignal:
    client = _get_client()

    clean_text = "\n".join(
        f"- [{p['subreddit']}] {p['title']}: {p['selftext'][:200]}"
        for p in clean_posts[:30]
    )
    flagged_text = "\n".join(f"- [FLAGGED] {p['title']}" for p in flagged_posts[:10])
    news_text = "\n".join(f"- {h}" for h in news_headlines[:20])

    # ── Short interest block ──────────────────────────────────────────────────
    if short_interest:
        si_float = short_interest.get("short_percent_of_float")
        si_ratio = short_interest.get("short_ratio")
        si_float_str = f"{si_float * 100:.1f}%" if si_float is not None else "n/a"
        si_ratio_str = f"{si_ratio:.1f} days" if si_ratio is not None else "n/a"
        # Contextualise: >20% float is very high, >10% elevated, <5% low
        if si_float is not None:
            if si_float > 0.20:
                si_context = "VERY HIGH — strong institutional bearish conviction; significant short-squeeze risk"
            elif si_float > 0.10:
                si_context = "ELEVATED — notable short interest; bears have a meaningful position"
            elif si_float > 0.05:
                si_context = "MODERATE — typical range, no strong signal either way"
            else:
                si_context = "LOW — little institutional short positioning"
        else:
            si_context = "unavailable"
        short_text = (
            f"  Short % of float: {si_float_str} ({si_context})\n"
            f"  Days to cover: {si_ratio_str}"
        )
    else:
        short_text = "  DATA UNAVAILABLE"

    # ── Fear & Greed block ────────────────────────────────────────────────────
    if fear_greed:
        fg_score = fear_greed.get("score")
        fg_rating = fear_greed.get("rating", "unknown")
        fg_history = fear_greed.get("history", {})
        fg_score_str = f"{fg_score:.0f}/100" if fg_score is not None else "n/a"
        history_str = ", ".join(
            f"{k}={v:.0f}" for k, v in fg_history.items() if v is not None
        )
        fg_text = (
            f"  Current: {fg_score_str} — {fg_rating.title()}\n"
            f"  History: {history_str}\n"
            f"  Note: scores <25=extreme fear, 25-44=fear, 45-55=neutral, 56-75=greed, >75=extreme greed"
        )
    else:
        fg_text = "  DATA UNAVAILABLE"

    # Classify mention volume so the LLM understands the hype context
    if mention_volume >= _HYPE_VOLUME_EXTREME:
        volume_label = f"{mention_volume} — EXTREME (near data-collection ceiling; full market saturation)"
    elif mention_volume >= _HYPE_VOLUME_HIGH:
        volume_label = (
            f"{mention_volume} — HIGH (most sources returning near-maximum results)"
        )
    elif mention_volume >= _HYPE_VOLUME_MEDIUM:
        volume_label = (
            f"{mention_volume} — ELEVATED (above typical for this data window)"
        )
    else:
        volume_label = f"{mention_volume} — NORMAL"

    prompt = f"""You are a market sentiment analyst. Analyse sentiment for {ticker}.

=== REDDIT POSTS (clean, title-matched only, {len(clean_posts)} total) ===
{clean_text or 'No clean Reddit posts found.'}

=== REDDIT POSTS (bot-flagged, {len(flagged_posts)} total) ===
{flagged_text or 'None flagged.'}

=== NEWS HEADLINES ({len(news_headlines)} total) ===
{news_text or 'No news found.'}

=== SHORT INTEREST (institutional positioning — money on the line) ===
{short_text}

=== CNN FEAR & GREED INDEX (market-wide sentiment composite) ===
{fg_text}

Total mention volume: {volume_label}

=== HYPE RISK GUIDANCE ===
High mention volume combined with uniformly bullish sentiment is a CONTRARY indicator,
not a confirming one. Retail crowd sentiment peaks near market tops — the information
is likely already priced in. Apply the following discipline:
- If volume is HIGH or EXTREME and sentiment skews strongly bullish (>0.5), set
  adjusted_score lower than raw_score to reflect crowd-overreaction risk.
- Uniformly bullish content with little dissent is MORE suspicious than mixed content.
- Fear/negative sentiment spikes are generally more informative than euphoria spikes
  and should NOT be discounted in the same way.
- Short interest and Fear & Greed are harder signals than social media — weight them
  more heavily. Very high short float (>15%) combined with bullish social posts often
  signals a short-squeeze setup rather than genuine organic optimism.

Your task:
1. raw_score: unweighted aggregate sentiment [-1.0 bearish to 1.0 bullish]
2. adjusted_score: discount for (a) bot/flagged content AND (b) crowd-overreaction
   when volume is elevated and sentiment is uniformly bullish. Short interest and
   Fear & Greed should anchor this score — social media is noisy, money is not.
3. bot_risk: "low" / "medium" / "high" — your assessment of manipulation risk
4. source_breakdown: score per source (reddit, news, short_interest, fear_greed) as dict
5. narrative_themes: 3-6 key themes dominating discussion
6. mention_volume: total mentions across all sources
7. reasoning: 2-4 sentences — cite short interest and Fear & Greed explicitly when
   they conflict with or confirm social media sentiment

If adjusted_score < raw_score, explain both the bot discount and/or hype discount in reasoning."""

    schema = SentimentSignal.model_json_schema()
    schema.pop("$defs", None)
    schema.pop("title", None)

    response = await client.messages.create(
        model=model,
        max_tokens=1536,
        tools=[
            {
                "name": "submit",
                "description": "Submit the sentiment signal",
                "input_schema": schema,
            }
        ],
        tool_choice={"type": "tool", "name": "submit"},
        messages=[{"role": "user", "content": prompt}],
    )
    log_usage(
        agent="sentiment",
        model=model,
        backend="anthropic",
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        ticker=ticker,
    )

    for block in response.content:
        if block.type == "tool_use":
            data = dict(block.input)
            data["mention_volume"] = mention_volume
            has_partial = len(news_headlines) == 0 or (
                len(clean_posts) == 0 and len(flagged_posts) == 0
            )
            data.setdefault("data_quality", "partial" if has_partial else "full")
            return SentimentSignal.model_validate(data)

    raise ValueError("No tool_use block in sentiment LLM response")


# ── Public async entry point ───────────────────────────────────────────────────


async def run(ticker: str) -> SentimentSignal:
    cached = load_cache(ticker, "signal_sentiment")
    if cached is not None:
        log.info("sentiment_agent_cache_hit", ticker=ticker)
        return SentimentSignal.model_validate(cached)

    model = get_model_router().get_model("sentiment")
    log.info("sentiment_agent_start", ticker=ticker, model=model)

    results = await asyncio.gather(
        get_reddit_posts(ticker),
        get_news(ticker),
        get_short_interest(ticker),
        get_fear_greed(),
        return_exceptions=True,
    )
    reddit_posts = results[0] if not isinstance(results[0], BaseException) else []
    news_items = results[1] if not isinstance(results[1], BaseException) else []
    short_data = results[2] if not isinstance(results[2], BaseException) else None
    fg_data = results[3] if not isinstance(results[3], BaseException) else None
    if isinstance(results[3], BaseException):
        log.warning("fear_greed_fetch_failed", error=str(results[3]))
    if isinstance(results[0], BaseException):
        log.warning("reddit_fetch_failed", ticker=ticker, error=str(results[0]))
    if isinstance(results[1], BaseException):
        log.warning("news_fetch_failed", ticker=ticker, error=str(results[1]))

    # Only pass posts where the ticker appears in the title — body-only mentions
    # are typically tangential (watchlists, comparison posts) and introduce noise.
    ticker_upper = ticker.upper()
    title_matched = [
        p for p in reddit_posts if ticker_upper in p.get("title", "").upper()
    ]

    flagged = apply_bot_heuristics(title_matched)
    clean = [p for p in flagged if not p["bot_flag"]]
    bots = [p for p in flagged if p["bot_flag"] or p["suspicious_flag"]]
    news_headlines = [item["headline"] for item in news_items]
    mention_volume = len(title_matched) + len(news_items)

    log.info(
        "sentiment_reddit_filtered",
        ticker=ticker,
        total_posts=len(reddit_posts),
        title_matched=len(title_matched),
        clean=len(clean),
        bot_flagged=len(bots),
    )

    signal = await _call_llm(
        model,
        ticker,
        clean,
        bots,
        news_headlines,
        mention_volume,
        short_interest=short_data,
        fear_greed=fg_data,
    )

    # Mathematical guardrail: apply hype discount on top of whatever the LLM returned.
    # This ensures the discount is applied even if the LLM under-weighted it.
    hype_factor = compute_hype_factor(mention_volume, signal.adjusted_score)
    if hype_factor > 0:
        discounted = round(signal.adjusted_score * (1.0 - hype_factor), 4)
        log.info(
            "sentiment_hype_discount_applied",
            ticker=ticker,
            mention_volume=mention_volume,
            original_adjusted=signal.adjusted_score,
            hype_factor=hype_factor,
            discounted_score=discounted,
        )
        signal = signal.model_copy(
            update={"adjusted_score": max(-1.0, min(1.0, discounted))}
        )

    save_cache(ticker, "signal_sentiment", signal.model_dump())
    log.info(
        "sentiment_agent_done",
        ticker=ticker,
        bot_risk=signal.bot_risk,
        adjusted_score=signal.adjusted_score,
    )
    return signal


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        signal = await run(ticker)
        print(signal.model_dump_json(indent=2))

    asyncio.run(main())
