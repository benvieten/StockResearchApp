"""
Shared fixtures for all test phases.

Fixture loading priority:
  1. backend/tests/fixtures/{ticker}_{source}.json  — pre-generated, committed
  2. cache/{ticker}_{source}_{today}_v1.json        — today's live cache
  3. Any cache/{ticker}_{source}_*.json             — most recent cache entry
  4. Raise pytest.skip() with a clear message if nothing found

Run `make fixtures` after Phase 1 is validated to populate fixtures/ from real data.
Fixtures are committed to the repo so tests always have data to run against.
"""

import json
import os
from datetime import date, datetime
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CACHE_DIR = Path(__file__).parent.parent.parent / "cache"
TEST_TICKER = "AAPL"


def _load_fixture(name: str) -> dict:
    """
    Load a fixture by logical name (e.g. "ohlcv", "financials").
    Falls back to cache if fixture file not yet generated.
    """
    fixture_path = FIXTURES_DIR / f"{TEST_TICKER}_{name}.json"
    if fixture_path.exists():
        return json.loads(fixture_path.read_text())

    # Fall back to cache — find most recent matching file
    today = date.today().isoformat()
    candidates = sorted(
        CACHE_DIR.glob(f"{TEST_TICKER}_{name}_*.json"), reverse=True
    )
    if candidates:
        return json.loads(candidates[0].read_text())

    pytest.skip(
        f"No fixture or cache found for '{name}'. "
        f"Run `make fixtures` after Phase 1 is validated, "
        f"or run `python -m backend.data.price {TEST_TICKER}` to populate cache."
    )


# ── Data layer fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def aapl_ohlcv() -> dict:
    return _load_fixture("ohlcv")


@pytest.fixture(scope="session")
def aapl_financials() -> dict:
    return _load_fixture("financials")


@pytest.fixture(scope="session")
def aapl_company_info() -> dict:
    return _load_fixture("company_info")


@pytest.fixture(scope="session")
def aapl_news() -> list:
    return _load_fixture("news")


@pytest.fixture(scope="session")
def aapl_reddit() -> list:
    return _load_fixture("reddit")


@pytest.fixture(scope="session")
def aapl_stocktwits() -> list:
    return _load_fixture("stocktwits")


# ── Agent signal fixtures ──────────────────────────────────────────────────────
# These are populated by running `make validate-phase3` and saving outputs.
# Synthesis tests depend on all five being present.

@pytest.fixture(scope="session")
def aapl_fundamental_signal() -> dict:
    return _load_fixture("signal_fundamental")


@pytest.fixture(scope="session")
def aapl_technical_signal() -> dict:
    return _load_fixture("signal_technical")


@pytest.fixture(scope="session")
def aapl_quant_signal() -> dict:
    return _load_fixture("signal_quant")


@pytest.fixture(scope="session")
def aapl_sector_signal() -> dict:
    return _load_fixture("signal_sector")


@pytest.fixture(scope="session")
def aapl_sentiment_signal() -> dict:
    return _load_fixture("signal_sentiment")


# ── Minimal synthetic data for pure unit tests ─────────────────────────────────
# These never hit the network and never depend on fixtures.

@pytest.fixture
def sample_financials_clean() -> dict:
    """A fully populated financials dict — no None fields."""
    return {
        "revenue": [400_000_000_000, 385_000_000_000, 390_000_000_000, 375_000_000_000],
        "gross_profit": [170_000_000_000, 162_000_000_000, 165_000_000_000, 158_000_000_000],
        "operating_income": [115_000_000_000, 109_000_000_000, 112_000_000_000, 105_000_000_000],
        "net_income": [96_000_000_000, 90_000_000_000, 93_000_000_000, 88_000_000_000],
        "ebitda": [125_000_000_000, 119_000_000_000, 122_000_000_000, 114_000_000_000],
        "total_debt": [110_000_000_000, 115_000_000_000],
        "total_equity": [56_000_000_000, 50_000_000_000],
        "free_cash_flow": [99_000_000_000, 92_000_000_000],
        "market_cap": 3_000_000_000_000,
        "enterprise_value": 3_050_000_000_000,
        "shares_outstanding": 15_500_000_000,
        "price": 193.60,
        "trailing_pe": 32.1,
        "book_value_per_share": 3.61,
    }


@pytest.fixture
def sample_financials_partial() -> dict:
    """A financials dict with some None fields — simulates yfinance gaps."""
    return {
        "revenue": [400_000_000_000, 385_000_000_000],
        "gross_profit": [170_000_000_000, None],   # missing field
        "operating_income": [None, None],            # all missing
        "net_income": [96_000_000_000, 90_000_000_000],
        "ebitda": None,                              # entirely absent
        "total_debt": [110_000_000_000],
        "total_equity": [56_000_000_000],
        "free_cash_flow": [99_000_000_000],
        "market_cap": 3_000_000_000_000,
        "enterprise_value": None,
        "shares_outstanding": 15_500_000_000,
        "price": 193.60,
        "trailing_pe": None,
        "book_value_per_share": 3.61,
    }


@pytest.fixture
def sample_reddit_posts() -> list:
    """Synthetic Reddit posts covering all bot detection edge cases."""
    base_time = datetime(2026, 3, 18, 12, 0, 0).timestamp()
    return [
        # Clean post — new account but upvotes fine
        {
            "title": "AAPL earnings look solid",
            "selftext": "Revenue beat expectations this quarter.",
            "score": 450,
            "upvote_ratio": 0.92,
            "num_comments": 87,
            "author": "user_clean",
            "author_created_utc": base_time - (60 * 86400),  # 60 days old — clean
            "post_created_utc": base_time,
            "subreddit": "stocks",
        },
        # Bot flag: account < 30 days old at post time
        {
            "title": "Buy AAPL now!!",
            "selftext": "This is going to moon.",
            "score": 210,
            "upvote_ratio": 0.88,
            "num_comments": 14,
            "author": "user_new_account",
            "author_created_utc": base_time - (15 * 86400),  # 15 days old — flagged
            "post_created_utc": base_time,
            "subreddit": "wallstreetbets",
        },
        # Suspicious flag: high score but low upvote ratio (manipulation)
        {
            "title": "AAPL to $300",
            "selftext": "Technical analysis shows breakout.",
            "score": 500,
            "upvote_ratio": 0.48,   # below 0.55 threshold
            "num_comments": 320,
            "author": "user_suspicious",
            "author_created_utc": base_time - (180 * 86400),
            "post_created_utc": base_time,
            "subreddit": "investing",
        },
        # Same author spam — 3 posts within 24h (see posts below)
        {
            "title": "AAPL bull run incoming",
            "selftext": "I'm all in.",
            "score": 12,
            "upvote_ratio": 0.72,
            "num_comments": 3,
            "author": "user_spammer",
            "author_created_utc": base_time - (90 * 86400),
            "post_created_utc": base_time - 3600,   # 1h ago
            "subreddit": "stocks",
        },
        {
            "title": "AAPL breaking out today",
            "selftext": "Look at the chart.",
            "score": 8,
            "upvote_ratio": 0.68,
            "num_comments": 1,
            "author": "user_spammer",
            "author_created_utc": base_time - (90 * 86400),
            "post_created_utc": base_time - 7200,   # 2h ago
            "subreddit": "stocks",
        },
        {
            "title": "AAPL is the play",
            "selftext": "Trust me.",
            "score": 5,
            "upvote_ratio": 0.60,
            "num_comments": 0,
            "author": "user_spammer",
            "author_created_utc": base_time - (90 * 86400),
            "post_created_utc": base_time - 10800,  # 3h ago — triggers spam flag
            "subreddit": "stocks",
        },
    ]


@pytest.fixture
def sample_ohlcv_df():
    """Minimal OHLCV DataFrame sufficient for indicator computation."""
    import numpy as np
    import pandas as pd

    n = 252  # 1 year of trading days
    rng = np.random.default_rng(42)
    prices = 150 + np.cumsum(rng.normal(0, 1.5, n))
    dates = pd.bdate_range(end="2026-03-18", periods=n)
    return pd.DataFrame(
        {
            "Open": prices * (1 - rng.uniform(0, 0.005, n)),
            "High": prices * (1 + rng.uniform(0, 0.01, n)),
            "Low": prices * (1 - rng.uniform(0, 0.01, n)),
            "Close": prices,
            "Volume": rng.integers(50_000_000, 150_000_000, n),
        },
        index=dates,
    )
