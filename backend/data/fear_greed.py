"""
Data module: fear_greed.py

Fetches the CNN Fear & Greed Index via the fear-greed library, which wraps
CNN's internal API (not scraping). The index is a composite of 7 signals:
  market_momentum_sp500, stock_price_strength, stock_price_breadth,
  put_call_options, market_volatility_vix, junk_bond_demand, safe_haven_demand

Cached daily — the index updates once per day.

Usage:
    python -m backend.data.fear_greed
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from backend.data._cache import load_cache, save_cache

log = structlog.get_logger()

_CACHE_KEY = "MARKET"   # not ticker-specific


async def get_fear_greed() -> dict:
    """Return the current CNN Fear & Greed Index, cached daily."""
    cached = load_cache(_CACHE_KEY, "fear_greed")
    if cached is not None:
        return cached

    log.info("fetching_fear_greed_index")
    data = await asyncio.to_thread(_fetch_fear_greed)
    save_cache(_CACHE_KEY, "fear_greed", data)
    return data


def _fetch_fear_greed() -> dict:
    import fear_greed  # imported here so the rest of the module loads without the package

    raw: dict = fear_greed.get()

    return {
        "score": raw.get("score"),
        "rating": raw.get("rating"),          # "extreme fear" / "fear" / "neutral" / "greed" / "extreme greed"
        "timestamp": raw.get("timestamp"),
        "history": raw.get("history", {}),    # {"1w": x, "1m": x, "3m": x, "6m": x, "1y": x}
        "indicators": raw.get("indicators", {}),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import json

    async def main() -> None:
        data = await get_fear_greed()
        print(json.dumps(data, indent=2, default=str))

    asyncio.run(main())
