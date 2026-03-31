"""
Data module: screener.py

Discovers candidate stock tickers from three free sources:
  1. Yahoo Finance trending (live HTTP endpoint, no auth)
  2. yfinance predefined screeners: most_actives, day_gainers, undervalued_large_caps
  3. Reddit hot post titles across configured subreddits (regex ticker extraction)

Candidates are scored by cross-source frequency, then validated via yfinance.info
to filter out ETFs, micro-caps, and illiquid names.

Result is cached daily — same-day repeat calls are instant.

Usage:
    python -m backend.data.screener
"""

from __future__ import annotations

import asyncio
import re
import sys
from collections import defaultdict
from typing import Any

import httpx
import structlog
import yfinance as yf

from backend.core.config import get_config
from backend.data._cache import load_cache, save_cache

log = structlog.get_logger()

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Exclusion list ──────────────────────────────────────────────────────────────
# All-caps words that look like tickers but aren't stocks we want to analyze.
_EXCLUDED: frozenset[str] = frozenset({
    # Common English / grammar
    "I", "A", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF", "IN",
    "IS", "IT", "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE",
    "ALL", "AND", "ARE", "BUT", "CAN", "DID", "FOR", "GET", "GOT", "HAD",
    "HAS", "HIM", "HIS", "HOW", "ITS", "LET", "MAY", "NEW", "NOT", "NOW",
    "OLD", "OUR", "OUT", "OWN", "PUT", "SAY", "SHE", "THE", "TOO", "TWO",
    "USE", "WAS", "WAY", "WHO", "WHY", "YET", "YOU", "ALSO", "BACK", "BEEN",
    "BOTH", "EACH", "EVEN", "FROM", "GOOD", "HAVE", "HIGH", "INTO", "JUST",
    "LAST", "LIKE", "LONG", "MADE", "MAKE", "MANY", "MORE", "MOST", "MUCH",
    "NEXT", "ONLY", "OVER", "SAID", "SOME", "SUCH", "TAKE", "THAN", "THAT",
    "THEM", "THEN", "THEY", "THIS", "TOOK", "VERY", "WELL", "WERE", "WHAT",
    "WHEN", "WITH", "WILL", "YEAR", "DAYS", "WEEK", "STILL",
    # Finance jargon
    "CEO", "CFO", "COO", "CTO", "IPO", "ETF", "USD", "GDP", "EPS", "TTM",
    "YTD", "QOQ", "YOY", "APR", "APY", "IRA", "ESG", "EV", "PE", "PB",
    "PS", "ATH", "ATL", "WSB", "DD", "TA", "FA", "DCA", "IMO", "TBH",
    "FOMO", "FUD", "YOLO", "HODL", "SEC", "FED", "IMF", "ECB", "CPI",
    "PCE", "FOMC", "BPS", "NAV", "AUM", "ROE", "ROA", "FCF",
    # Months / days
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
    "NOV", "DEC", "MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN",
    # Major ETFs / indices — we analyze individual equities, not funds
    "SPY", "QQQ", "VTI", "IWM", "DIA", "GLD", "SLV", "USO", "TLT", "HYG",
    "LQD", "BND", "AGG", "VEA", "VWO", "EFA", "EEM", "IAU",
    "XLK", "XLF", "XLV", "XLE", "XLI", "XLB", "XLY", "XLP", "XLRE", "XLU", "XLC",
    "ARKK", "ARKG", "ARKW", "ARKF", "ARKQ",
    # Crypto proxies
    "BTC", "ETH", "DOGE", "SHIB",
    # Misc
    "AI", "AR", "VR", "UK", "EU", "NY", "DC", "LA", "SF", "TV",
})

# Regex patterns for ticker extraction from free text
_DOLLAR_TICKER = re.compile(r"\$([A-Z]{1,5})\b")          # $AAPL — most reliable
_BARE_TICKER = re.compile(r"(?<![$/])\b([A-Z]{2,5})\b")   # AAPL in text — less reliable


# ── Public API ─────────────────────────────────────────────────────────────────


async def get_candidates(top_n: int | None = None) -> list[str]:
    """
    Return a filtered, scored list of ticker symbols discovered across all sources.
    Cached daily — repeat calls within the same calendar day are instant.

    Scoring (additive, not multiplicative):
        +3  per source that surfaces the ticker via a screener query (market-validated)
        +2  per Yahoo Finance trending appearance
        +2  per explicit $TICKER mention in Reddit
        +1  per bare CAPS mention in Reddit title (lower reliability)

    Validation applied to the top 2×top_n scored candidates:
        - quoteType must be "EQUITY"
        - marketCap ≥ configured min_market_cap_millions × 1e6
        - averageVolume ≥ configured min_avg_volume
    """
    cached = load_cache("MARKET", "screener")
    if cached is not None:
        log.debug("screener_cache_hit")
        return cached

    cfg = get_config()
    n = top_n or cfg.screener.top_n

    log.info("screener_start", top_n=n)

    # Run all discovery sources in parallel
    results = await asyncio.gather(
        _yahoo_trending(),
        _yfinance_screeners(cfg.screener.screener_queries),
        _reddit_hot_mentions(cfg.data_sources.reddit_subreddits),
        return_exceptions=True,
    )

    yahoo_trending: list[str]    = results[0] if not isinstance(results[0], Exception) else []
    screener_hits: dict[str, int] = results[1] if not isinstance(results[1], Exception) else {}
    reddit_mentions: dict[str, int] = results[2] if not isinstance(results[2], Exception) else {}

    if isinstance(results[0], Exception):
        log.warning("screener_yahoo_failed", error=str(results[0]))
    if isinstance(results[1], Exception):
        log.warning("screener_yfinance_failed", error=str(results[1]))
    if isinstance(results[2], Exception):
        log.warning("screener_reddit_failed", error=str(results[2]))

    # Build scored candidates dict
    scores: dict[str, int] = defaultdict(int)

    for ticker in yahoo_trending:
        scores[ticker] += 2

    for ticker, count in screener_hits.items():
        scores[ticker] += 3 * min(count, 2)   # up to 6 pts for appearing in multiple screeners

    for ticker, count in reddit_mentions.items():
        # dollar-sign mentions stored as negative (sentinel) — see _reddit_hot_mentions
        if count < 0:
            scores[ticker] += 2 * min(abs(count), 3)  # $TICKER callout: 2 pts each, cap 3
        else:
            scores[ticker] += min(count, 3)            # bare caps: 1 pt each, cap 3

    log.info(
        "screener_raw_scores",
        total_candidates=len(scores),
        top5=sorted(scores, key=lambda t: scores[t], reverse=True)[:5],
    )

    # Sort by score, take 2× candidates for validation headroom
    ordered = sorted(scores, key=lambda t: scores[t], reverse=True)[: n * 2]

    validated = await _validate_tickers(
        ordered,
        top_n=n,
        min_market_cap=cfg.screener.min_market_cap_millions * 1_000_000,
        min_avg_volume=cfg.screener.min_avg_volume,
    )

    log.info("screener_done", returned=len(validated), tickers=validated)
    save_cache("MARKET", "screener", validated)
    return validated


# ── Source: Yahoo Finance trending ─────────────────────────────────────────────


async def _yahoo_trending() -> list[str]:
    url = "https://query1.finance.yahoo.com/v1/finance/trending/US?count=20&lang=en-US"
    async with httpx.AsyncClient(headers={"User-Agent": _USER_AGENT}, timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    quotes = resp.json().get("finance", {}).get("result", [{}])[0].get("quotes", [])
    tickers = [
        q["symbol"] for q in quotes
        if re.match(r"^[A-Z]{1,5}$", q.get("symbol", ""))
        and q["symbol"] not in _EXCLUDED
    ]
    log.info("yahoo_trending_fetched", count=len(tickers), tickers=tickers[:5])
    return tickers


# ── Source: yfinance screeners ─────────────────────────────────────────────────


async def _yfinance_screeners(queries: list[str]) -> dict[str, int]:
    """Run each predefined screener query; return ticker→appearance_count."""
    counts: dict[str, int] = defaultdict(int)

    for query in queries:
        try:
            result: dict[str, Any] = await asyncio.to_thread(yf.screen, query, size=25)
            for quote in result.get("quotes", []):
                sym = quote.get("symbol", "")
                if re.match(r"^[A-Z]{1,5}$", sym) and sym not in _EXCLUDED:
                    counts[sym] += 1
            log.info("yfinance_screener_fetched", query=query, count=len(result.get("quotes", [])))
        except Exception as exc:
            log.warning("yfinance_screener_failed", query=query, error=str(exc))

    return dict(counts)


# ── Source: Reddit hot posts ────────────────────────────────────────────────────


async def _reddit_hot_mentions(subreddits: list[str]) -> dict[str, int]:
    """
    Fetch hot posts from each subreddit and extract ticker symbols.

    Returns ticker → count where:
        count < 0  means it was found via $TICKER pattern (explicit callout, higher weight)
        count > 0  means it was found as a bare ALL-CAPS word (lower weight)

    Both can coexist for the same ticker — the caller separates them.
    This encoding avoids two separate dicts.
    """
    dollar_counts: dict[str, int] = defaultdict(int)
    bare_counts: dict[str, int] = defaultdict(int)

    cfg = get_config()
    delay = cfg.rate_limits.reddit_delay_seconds

    async with httpx.AsyncClient(headers={"User-Agent": _USER_AGENT}, timeout=20) as client:
        for i, sub in enumerate(subreddits):
            if i > 0:
                await asyncio.sleep(delay)
            try:
                posts = await _fetch_hot_posts(client, sub)
                for post in posts:
                    text = post.get("title", "") + " " + post.get("selftext", "")[:500]
                    for m in _DOLLAR_TICKER.finditer(text):
                        t = m.group(1)
                        if t not in _EXCLUDED:
                            dollar_counts[t] += 1
                    for m in _BARE_TICKER.finditer(text):
                        t = m.group(1)
                        if t not in _EXCLUDED and len(t) >= 2:
                            bare_counts[t] += 1
                log.info("reddit_hot_fetched", subreddit=sub, posts=len(posts))
            except Exception as exc:
                log.warning("reddit_hot_failed", subreddit=sub, error=str(exc))

    # Merge: dollar-sign mentions stored as negative ints (sentinel for caller)
    combined: dict[str, int] = {}
    all_tickers = set(dollar_counts) | set(bare_counts)
    for t in all_tickers:
        if dollar_counts[t] > 0:
            combined[t] = -dollar_counts[t]   # negative = dollar-sign callout
        else:
            combined[t] = bare_counts[t]
    return combined


async def _fetch_hot_posts(client: httpx.AsyncClient, subreddit: str) -> list[dict]:
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=30"
    resp = await client.get(url)
    resp.raise_for_status()
    children = resp.json().get("data", {}).get("children", [])
    return [c.get("data", {}) for c in children]


# ── Validation ─────────────────────────────────────────────────────────────────


async def _validate_tickers(
    candidates: list[str],
    top_n: int,
    min_market_cap: float,
    min_avg_volume: int,
) -> list[str]:
    """
    Parallel-validate each candidate via yfinance.info.
    Keep only EQUITY type with sufficient size and liquidity.
    Return at most top_n validated tickers in score order.
    """
    sem = asyncio.Semaphore(5)  # limit concurrent yfinance calls

    async def _check(ticker: str) -> str | None:
        async with sem:
            try:
                info: dict = await asyncio.to_thread(
                    lambda: yf.Ticker(ticker).info
                )
                if info.get("quoteType") != "EQUITY":
                    return None
                mkt_cap = info.get("marketCap") or 0
                avg_vol  = info.get("averageVolume") or 0
                if mkt_cap < min_market_cap or avg_vol < min_avg_volume:
                    return None
                return ticker
            except Exception:
                return None

    results = await asyncio.gather(*[_check(t) for t in candidates])
    validated = [t for t in results if t is not None]

    log.info(
        "screener_validation_done",
        checked=len(candidates),
        passed=len(validated),
        filtered_out=len(candidates) - len(validated),
    )
    return validated[:top_n]


# ── CLI ────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import json

    async def main() -> None:
        # Pass --refresh to bust cache and re-discover
        if "--refresh" in sys.argv:
            from backend.data._cache import save_cache
            save_cache("MARKET", "screener", None)  # won't match load_cache since None != list

        candidates = await get_candidates()
        print(json.dumps(candidates, indent=2))

    asyncio.run(main())
