"""
Backtesting store: track predictions and check outcomes.

At analysis time, save_prediction() records:
  - ticker, verdict, conviction, composite score
  - closing price at prediction time
  - timestamp

check_outcomes() scans saved predictions and, for those past the target
horizon (30/60/90 days), fetches the current price and computes actual return.

Storage: SQLite database at backtest/predictions.db (gitignored).
Existing JSONL files (backtest/predictions_YYYY-MM-DD.jsonl) are migrated
automatically on first run and left in place as a backup.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import structlog
import yfinance as yf

log = structlog.get_logger()

_BACKTEST_DIR = Path("backtest")
_DB_PATH = _BACKTEST_DIR / "predictions.db"

# Horizon → days mapping (matches recommended_horizon values)
_HORIZON_DAYS = {
    "short_term": 30,
    "medium_term": 60,
    "long_term": 90,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker           TEXT    NOT NULL,
    verdict          TEXT    NOT NULL,
    conviction       TEXT    NOT NULL,
    composite_score  REAL,
    horizon          TEXT,
    price_at_prediction REAL,
    predicted_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ticker       ON predictions(ticker);
CREATE INDEX IF NOT EXISTS idx_predicted_at ON predictions(predicted_at);

CREATE TABLE IF NOT EXISTS migrations (
    name  TEXT PRIMARY KEY,
    ran_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    """Open a connection to the predictions DB, creating it if needed."""
    _BACKTEST_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _migrate_jsonl(conn: sqlite3.Connection) -> None:
    """
    Import any existing JSONL prediction files into SQLite.
    Runs at most once (tracked in the migrations table).
    """
    migration_name = "import_jsonl_v1"
    row = conn.execute(
        "SELECT name FROM migrations WHERE name = ?", (migration_name,)
    ).fetchone()
    if row:
        return  # already done

    jsonl_files = sorted(_BACKTEST_DIR.glob("predictions_*.jsonl"))
    if not jsonl_files:
        # Nothing to migrate — mark as done and return
        conn.execute(
            "INSERT INTO migrations(name, ran_at) VALUES (?, ?)",
            (migration_name, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return

    imported = 0
    for jsonl_path in jsonl_files:
        for line in jsonl_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                conn.execute(
                    """
                    INSERT INTO predictions
                        (ticker, verdict, conviction, composite_score,
                         horizon, price_at_prediction, predicted_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rec["ticker"],
                        rec["verdict"],
                        rec["conviction"],
                        rec.get("composite_score"),
                        rec.get("horizon"),
                        rec.get("price_at_prediction"),
                        rec["predicted_at"],
                    ),
                )
                imported += 1
            except Exception as exc:
                log.warning("backtest_migrate_row_failed", error=str(exc))

    conn.execute(
        "INSERT INTO migrations(name, ran_at) VALUES (?, ?)",
        (migration_name, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    log.info("backtest_jsonl_migrated", imported=imported, files=len(jsonl_files))


def _get_conn() -> sqlite3.Connection:
    """Return a connection, running one-time JSONL migration if needed."""
    conn = _connect()
    _migrate_jsonl(conn)
    return conn


def get_last_prediction(ticker: str) -> dict | None:
    """Return the most recent prediction row for *ticker*, or None."""
    try:
        conn = _get_conn()
        row = conn.execute(
            """
            SELECT ticker, verdict, conviction, composite_score,
                   horizon, price_at_prediction, predicted_at
            FROM predictions
            WHERE ticker = ?
            ORDER BY predicted_at DESC
            LIMIT 1
            """,
            (ticker,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as exc:
        log.warning("backtest_last_prediction_failed", ticker=ticker, error=str(exc))
        return None


def save_prediction(
    ticker: str,
    verdict: str,
    conviction: str,
    composite_score: float | None,
    horizon: str | None,
    price_at_prediction: float | None,
) -> None:
    """
    Insert one prediction record into the SQLite database.

    Non-blocking: any write error is logged and swallowed so it never
    interrupts the main pipeline.
    """
    try:
        conn = _get_conn()
        conn.execute(
            """
            INSERT INTO predictions
                (ticker, verdict, conviction, composite_score,
                 horizon, price_at_prediction, predicted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                verdict,
                conviction,
                composite_score,
                horizon,
                price_at_prediction,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
        log.info("backtest_prediction_saved", ticker=ticker, verdict=verdict)
    except Exception as exc:
        log.warning("backtest_save_failed", ticker=ticker, error=str(exc))


def check_outcomes(min_days_elapsed: int = 25) -> list[dict]:
    """
    Return outcomes for all predictions whose horizon has elapsed
    (or is within min_days_elapsed of elapsing).

    For each mature prediction, fetches the current price from yfinance
    and computes actual_return = (current - entry) / entry.
    """
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM predictions ORDER BY predicted_at"
        ).fetchall()
        conn.close()
    except Exception as exc:
        log.warning("backtest_check_outcomes_failed", error=str(exc))
        return []

    now = datetime.now(timezone.utc)
    outcomes: list[dict] = []

    for row in rows:
        try:
            rec = dict(row)
            predicted_at = datetime.fromisoformat(rec["predicted_at"])
            horizon = rec.get("horizon") or "medium_term"
            target_days = _HORIZON_DAYS.get(horizon, 60)
            elapsed = (now - predicted_at).days

            if elapsed < (target_days - min_days_elapsed):
                continue

            entry_price = rec.get("price_at_prediction")
            if not entry_price:
                continue

            ticker = rec["ticker"]
            try:
                info = yf.Ticker(ticker).info or {}
                current_price = info.get("currentPrice") or info.get(
                    "regularMarketPrice"
                )
            except Exception:
                current_price = None

            actual_return = (
                (current_price - entry_price) / entry_price
                if current_price and entry_price and entry_price > 0
                else None
            )

            outcomes.append(
                {
                    **rec,
                    "elapsed_days": elapsed,
                    "target_days": target_days,
                    "current_price": current_price,
                    "actual_return": actual_return,
                    "outcome_checked_at": now.isoformat(),
                }
            )
        except Exception as exc:
            log.warning("backtest_outcome_parse_failed", error=str(exc))

    return outcomes


def get_ticker_history(ticker: str) -> list[dict]:
    """
    Return all saved predictions for *ticker* (most recent first).

    Each record includes:
      - All original prediction fields
      - status: "matured" | "pending"
      - elapsed_days, target_days
      - current_price, actual_return  (matured only; None if price unavailable)
    """
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM predictions WHERE ticker = ? ORDER BY predicted_at DESC",
            (ticker,),
        ).fetchall()
        conn.close()
    except Exception as exc:
        log.warning("backtest_history_failed", ticker=ticker, error=str(exc))
        return []

    now = datetime.now(timezone.utc)
    records: list[dict] = []

    for row in rows:
        try:
            rec = dict(row)
            predicted_at = datetime.fromisoformat(rec["predicted_at"])
            horizon = rec.get("horizon") or "medium_term"
            target_days = _HORIZON_DAYS.get(horizon, 60)
            elapsed = (now - predicted_at).days
            is_mature = elapsed >= (target_days - 5)

            if is_mature and rec.get("price_at_prediction"):
                entry_price = rec["price_at_prediction"]
                try:
                    info = yf.Ticker(ticker).info or {}
                    current_price = info.get("currentPrice") or info.get(
                        "regularMarketPrice"
                    )
                except Exception:
                    current_price = None

                actual_return = (
                    (current_price - entry_price) / entry_price
                    if current_price and entry_price and entry_price > 0
                    else None
                )
                records.append(
                    {
                        **rec,
                        "status": "matured",
                        "elapsed_days": elapsed,
                        "target_days": target_days,
                        "current_price": current_price,
                        "actual_return": actual_return,
                    }
                )
            else:
                records.append(
                    {
                        **rec,
                        "status": "pending",
                        "elapsed_days": elapsed,
                        "target_days": target_days,
                    }
                )
        except Exception as exc:
            log.warning("backtest_history_parse_failed", ticker=ticker, error=str(exc))

    return records
