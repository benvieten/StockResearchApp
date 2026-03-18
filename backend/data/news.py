"""
Data module: news.py

Fetches headlines from Google News RSS (primary) and Finviz (secondary).
Returns a unified, deduplicated list of news items.

Usage:
    python -m backend.data.news AAPL
"""

from __future__ import annotations

import asyncio
import sys

import feedparser
import httpx
import structlog
from bs4 import BeautifulSoup

from backend.data._cache import load_cache, save_cache

log = structlog.get_logger()

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ── Public async API ───────────────────────────────────────────────────────────


async def get_news(ticker: str) -> list[dict]:
    """Return a deduplicated list of news items for ticker."""
    cached = load_cache(ticker, "news")
    if cached is not None:
        return cached

    log.info("fetching_news", ticker=ticker)
    items: list[dict] = []

    google_items = await _fetch_google_news(ticker)
    items.extend(google_items)

    try:
        finviz_items = await _fetch_finviz_news(ticker)
        items.extend(finviz_items)
    except Exception as exc:
        log.warning("finviz_fetch_failed", ticker=ticker, error=str(exc))

    unique = _deduplicate(items)
    save_cache(ticker, "news", unique)
    return unique


# ── Source fetchers ────────────────────────────────────────────────────────────


async def _fetch_google_news(ticker: str) -> list[dict]:
    url = (
        f"https://news.google.com/rss/search"
        f"?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
    )
    feed = await asyncio.to_thread(feedparser.parse, url)
    items = []
    for entry in feed.get("entries", []):
        items.append(
            {
                "headline": entry.get("title", "").strip(),
                "source": (entry.get("source") or {}).get("title", "Google News"),
                "timestamp": entry.get("published", ""),
                "url": entry.get("link", ""),
            }
        )
    log.info("google_news_fetched", ticker=ticker, count=len(items))
    return items


async def _fetch_finviz_news(ticker: str) -> list[dict]:
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT}, timeout=15, follow_redirects=True
    ) as client:
        resp = await client.get(url)

    if resp.status_code == 403:
        log.warning("finviz_blocked", ticker=ticker, status=403)
        return []

    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find(id="news-table")
    if not table:
        log.warning("finviz_no_news_table", ticker=ticker)
        return []

    items = []
    last_date = ""
    for row in table.find_all("tr"):  # type: ignore[union-attr]
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        date_cell = cells[0].text.strip()
        # Finviz shows "Mar-17-24 09:45AM" on first row of a date,
        # then only "09:30AM" on subsequent rows of the same date.
        if " " in date_cell:
            last_date, time_str = date_cell.split(" ", 1)
        else:
            time_str = date_cell
        timestamp = f"{last_date} {time_str}".strip()

        link_tag = cells[1].find("a")
        if not link_tag:
            continue
        items.append(
            {
                "headline": link_tag.text.strip(),
                "source": "Finviz",
                "timestamp": timestamp,
                "url": link_tag.get("href", ""),
            }
        )

    log.info("finviz_news_fetched", ticker=ticker, count=len(items))
    return items


# ── Helpers ────────────────────────────────────────────────────────────────────


def _deduplicate(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique = []
    for item in items:
        key = item.get("headline", "").lower()[:80]
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import json

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        news = await get_news(ticker)
        print(f"Total items: {len(news)}")
        print(json.dumps(news[:5], indent=2))

    asyncio.run(main())
