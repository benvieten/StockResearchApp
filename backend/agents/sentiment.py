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

from backend.core.config import get_config
from backend.core.data_models import SentimentSignal
from backend.data.news import get_news
from backend.data.reddit import get_reddit_posts
from backend.data.stocktwits import get_stocktwits_messages

log = structlog.get_logger()

load_dotenv()
_client: AsyncAnthropic | None = None

# Bot detection thresholds
_MIN_ACCOUNT_AGE_DAYS = 30
_SUSPICIOUS_UPVOTE_RATIO = 0.55
_SUSPICIOUS_MIN_SCORE = 100
_SPAM_WINDOW_SECONDS = 6 * 3600   # 6-hour window for burst detection
_SPAM_POST_THRESHOLD = 3


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
        if ratio is not None and ratio < _SUSPICIOUS_UPVOTE_RATIO and score > _SUSPICIOUS_MIN_SCORE:
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
    stocktwits_msgs: list[dict],
    mention_volume: int,
) -> SentimentSignal:
    client = _get_client()

    clean_text = "\n".join(
        f"- [{p['subreddit']}] {p['title']}: {p['selftext'][:200]}"
        for p in clean_posts[:30]
    )
    flagged_text = "\n".join(
        f"- [FLAGGED] {p['title']}" for p in flagged_posts[:10]
    )
    news_text = "\n".join(f"- {h}" for h in news_headlines[:20])
    st_text = "\n".join(
        f"- [{m.get('sentiment', 'N/A')}] {m['body'][:120]}"
        for m in stocktwits_msgs[:20]
    ) if stocktwits_msgs else "StockTwits: no data available (API restricted)"

    prompt = f"""You are a market sentiment analyst. Analyse sentiment for {ticker}.

=== REDDIT POSTS (clean, {len(clean_posts)} total) ===
{clean_text or 'No clean Reddit posts found.'}

=== REDDIT POSTS (bot-flagged, {len(flagged_posts)} total) ===
{flagged_text or 'None flagged.'}

=== NEWS HEADLINES ({len(news_headlines)} total) ===
{news_text or 'No news found.'}

=== STOCKTWITS MESSAGES ===
{st_text}

Total mention volume: {mention_volume}

Your task:
1. raw_score: unweighted aggregate sentiment [-1.0 bearish to 1.0 bullish]
2. adjusted_score: same but discount flagged/bot content proportionally to bot_risk
3. bot_risk: "low" / "medium" / "high" — your assessment of manipulation risk
4. source_breakdown: score per source (reddit, news, stocktwits) as dict
5. narrative_themes: 3-6 key themes dominating discussion
6. mention_volume: total mentions across all sources
7. reasoning: 2-4 sentence analysis

If adjusted_score < raw_score (you discounted bots), explain why in reasoning."""

    schema = SentimentSignal.model_json_schema()
    schema.pop("$defs", None)
    schema.pop("title", None)

    response = await client.messages.create(
        model=model,
        max_tokens=1536,
        tools=[{"name": "submit", "description": "Submit the sentiment signal", "input_schema": schema}],
        tool_choice={"type": "tool", "name": "submit"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use":
            data = dict(block.input)
            data["mention_volume"] = mention_volume
            has_partial = len(stocktwits_msgs) == 0
            data.setdefault("data_quality", "partial" if has_partial else "full")
            return SentimentSignal.model_validate(data)

    raise ValueError("No tool_use block in sentiment LLM response")


# ── Public async entry point ───────────────────────────────────────────────────


async def run(ticker: str) -> SentimentSignal:
    cfg = get_config()
    model = cfg.anthropic.models["sentiment"]

    log.info("sentiment_agent_start", ticker=ticker, model=model)

    reddit_task = asyncio.create_task(get_reddit_posts(ticker))
    news_task = asyncio.create_task(get_news(ticker))
    st_task = asyncio.create_task(get_stocktwits_messages(ticker))

    reddit_posts, news_items, st_msgs = await asyncio.gather(
        reddit_task, news_task, st_task
    )

    flagged = apply_bot_heuristics(reddit_posts)
    clean = [p for p in flagged if not p["bot_flag"]]
    bots = [p for p in flagged if p["bot_flag"] or p["suspicious_flag"]]
    news_headlines = [item["headline"] for item in news_items]
    mention_volume = len(reddit_posts) + len(news_items) + len(st_msgs)

    signal = await _call_llm(
        model, ticker, clean, bots, news_headlines, st_msgs, mention_volume
    )
    log.info("sentiment_agent_done", ticker=ticker, bot_risk=signal.bot_risk)
    return signal


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        signal = await run(ticker)
        print(signal.model_dump_json(indent=2))

    asyncio.run(main())
