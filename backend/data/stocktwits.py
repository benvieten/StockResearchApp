"""
Data module: stocktwits.py

Fetches messages from the StockTwits public API (no auth required).
Normalizes the sentiment field to "Bullish", "Bearish", or None —
absent sentiment is always serialized as None, never omitted.

Usage:
    python -m backend.data.stocktwits AAPL
"""

from __future__ import annotations

import asyncio
import sys

import httpx
import structlog

from backend.data._cache import load_cache, save_cache

log = structlog.get_logger()


# ── Public async API ───────────────────────────────────────────────────────────


async def get_stocktwits_messages(ticker: str) -> list[dict]:
    """Return StockTwits messages for ticker with normalized sentiment."""
    cached = load_cache(ticker, "stocktwits")
    if cached is not None:
        return cached

    log.info("fetching_stocktwits", ticker=ticker)
    messages = await _fetch_messages(ticker)
    save_cache(ticker, "stocktwits", messages)
    return messages


# ── Internal helpers ───────────────────────────────────────────────────────────


_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


async def _fetch_messages(ticker: str) -> list[dict]:
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT}, timeout=15
    ) as client:
        resp = await client.get(url)

    if resp.status_code == 403:
        log.warning(
            "stocktwits_blocked",
            ticker=ticker,
            status=403,
            note="StockTwits public API may require auth — returning empty list",
        )
        return []

    resp.raise_for_status()

    data = resp.json()
    messages = []
    for msg in data.get("messages", []):
        # Sentiment field: {"basic": "Bullish"} | {"basic": "Bearish"} | absent
        sentiment_raw = msg.get("entities", {}).get("sentiment")
        if sentiment_raw and isinstance(sentiment_raw, dict):
            sentiment: str | None = sentiment_raw.get("basic")
        else:
            sentiment = None

        messages.append(
            {
                "body": msg.get("body", ""),
                "sentiment": sentiment,  # always present — None when not tagged
                "created_at": msg.get("created_at", ""),
            }
        )

    log.info("stocktwits_fetched", ticker=ticker, count=len(messages))
    return messages


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import json

    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    async def main() -> None:
        messages = await get_stocktwits_messages(ticker)
        print(f"Total messages: {len(messages)}")
        print(json.dumps(messages[:5], indent=2))

    asyncio.run(main())
