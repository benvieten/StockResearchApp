"""
Data module: reddit.py

Fetches posts from Reddit's public JSON API across 4 subreddits.
Uses a browser-like User-Agent to avoid bot detection.
Sleeps between subreddit requests to respect rate limits.

Usage:
    python -m backend.data.reddit AAPL
"""

from __future__ import annotations

import asyncio
import sys

import httpx
import structlog

from backend.core.config import get_config
from backend.data._cache import load_cache, save_cache

log = structlog.get_logger()

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ── Public async API ───────────────────────────────────────────────────────────


async def get_reddit_posts(ticker: str) -> list[dict]:
    """Return posts mentioning ticker from all configured subreddits."""
    cached = load_cache(ticker, "reddit")
    if cached is not None:
        return cached

    cfg = get_config()
    subreddits: list[str] = cfg.data_sources.reddit_subreddits
    limit: int = cfg.data_sources.reddit_limit
    delay: float = cfg.rate_limits.reddit_delay_seconds

    log.info("fetching_reddit", ticker=ticker, subreddits=subreddits)
    all_posts: list[dict] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT}, timeout=20
    ) as client:
        for i, sub in enumerate(subreddits):
            if i > 0:
                await asyncio.sleep(delay)
            try:
                posts = await _fetch_subreddit(client, sub, ticker, limit)
                all_posts.extend(posts)
                log.info("reddit_subreddit_fetched", subreddit=sub, count=len(posts))
            except Exception as exc:
                log.warning("reddit_subreddit_failed", subreddit=sub, error=str(exc))

    save_cache(ticker, "reddit", all_posts)
    return all_posts


# ── Internal helpers ───────────────────────────────────────────────────────────


async def _fetch_subreddit(
    client: httpx.AsyncClient, subreddit: str, ticker: str, limit: int
) -> list[dict]:
    url = (
        f"https://www.reddit.com/r/{subreddit}/search.json"
        f"?q={ticker}&sort=new&limit={limit}&restrict_sr=on"
    )
    resp = await client.get(url)
    resp.raise_for_status()
    data = resp.json()

    posts = []
    for child in data.get("data", {}).get("children", []):
        p: dict = child.get("data", {})
        posts.append(
            {
                "title": p.get("title", ""),
                "selftext": p.get("selftext", ""),
                "score": int(p.get("score", 0)),
                "upvote_ratio": p.get("upvote_ratio"),
                "num_comments": int(p.get("num_comments", 0)),
                "author": p.get("author", ""),
                # Reddit includes author account age on some endpoints;
                # it may be None if the account is suspended or shadowbanned.
                "author_created_utc": p.get("author_created_utc"),
                "post_created_utc": p.get("created_utc"),
                "subreddit": p.get("subreddit", subreddit),
            }
        )
    return posts


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import json

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        posts = await get_reddit_posts(ticker)
        print(f"Total posts: {len(posts)}")
        print(json.dumps(posts[:3], indent=2, default=str))

    asyncio.run(main())
