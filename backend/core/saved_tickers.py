"""
Personal watchlist store.

Persists user-saved tickers in the same SQLite database as backtest
predictions. The user_id column defaults to "default" for the current
single-user setup — when auth is added, pass the real user ID instead.

Public API:
    add_ticker(ticker, user_id="default") -> bool   # True if newly added
    remove_ticker(ticker, user_id="default") -> bool # True if existed
    get_tickers(user_id="default") -> list[dict]
    is_saved(ticker, user_id="default") -> bool
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import structlog

log = structlog.get_logger()

_DB_PATH = Path("backtest") / "predictions.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_tickers (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  TEXT    NOT NULL DEFAULT 'default',
    ticker   TEXT    NOT NULL,
    added_at TEXT    NOT NULL,
    UNIQUE(user_id, ticker)
);
CREATE INDEX IF NOT EXISTS idx_saved_user ON saved_tickers(user_id);
"""


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def add_ticker(ticker: str, user_id: str = "default") -> bool:
    """
    Add *ticker* to *user_id*'s watchlist.
    Returns True if added, False if it was already there.
    """
    try:
        conn = _connect()
        conn.execute(
            "INSERT OR IGNORE INTO saved_tickers(user_id, ticker, added_at) VALUES (?, ?, ?)",
            (user_id, ticker.upper(), datetime.now(timezone.utc).isoformat()),
        )
        added = conn.total_changes > 0
        conn.commit()
        conn.close()
        if added:
            log.info("watchlist_ticker_added", ticker=ticker, user_id=user_id)
        return added
    except Exception as exc:
        log.warning("watchlist_add_failed", ticker=ticker, error=str(exc))
        return False


def remove_ticker(ticker: str, user_id: str = "default") -> bool:
    """
    Remove *ticker* from *user_id*'s watchlist.
    Returns True if it existed and was removed, False otherwise.
    """
    try:
        conn = _connect()
        conn.execute(
            "DELETE FROM saved_tickers WHERE user_id = ? AND ticker = ?",
            (user_id, ticker.upper()),
        )
        removed = conn.total_changes > 0
        conn.commit()
        conn.close()
        if removed:
            log.info("watchlist_ticker_removed", ticker=ticker, user_id=user_id)
        return removed
    except Exception as exc:
        log.warning("watchlist_remove_failed", ticker=ticker, error=str(exc))
        return False


def get_tickers(user_id: str = "default") -> list[dict]:
    """Return all saved tickers for *user_id*, most recently added first."""
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT ticker, added_at FROM saved_tickers WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("watchlist_get_failed", error=str(exc))
        return []


def is_saved(ticker: str, user_id: str = "default") -> bool:
    """Return True if *ticker* is in *user_id*'s watchlist."""
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT 1 FROM saved_tickers WHERE user_id = ? AND ticker = ?",
            (user_id, ticker.upper()),
        ).fetchone()
        conn.close()
        return row is not None
    except Exception as exc:
        log.warning("watchlist_is_saved_failed", ticker=ticker, error=str(exc))
        return False
