"""
Backtesting store: track predictions and check outcomes.

At analysis time, save_prediction() records:
  - ticker, verdict, conviction, composite score
  - closing price at prediction time
  - timestamp

check_outcomes() scans saved predictions and, for those past the target
horizon (30/60/90 days), fetches the current price and computes actual return.
Returns a list of outcome dicts — caller decides how to display/export them.

Storage: one JSON-Lines file per day under backtest/predictions_YYYY-MM-DD.jsonl
All files live in backtest/ (gitignored).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import structlog
import yfinance as yf

log = structlog.get_logger()

_BACKTEST_DIR = Path(__file__).parent.parent.parent / "backtest"

# Horizon → days mapping (matches recommended_horizon values)
_HORIZON_DAYS = {
    "short_term": 30,
    "medium_term": 60,
    "long_term": 90,
}


def _ensure_dir() -> Path:
    _BACKTEST_DIR.mkdir(exist_ok=True)
    return _BACKTEST_DIR


def save_prediction(
    ticker: str,
    verdict: str,
    conviction: str,
    composite_score: float | None,
    horizon: str | None,
    price_at_prediction: float | None,
) -> None:
    """
    Append one prediction record to today's JSONL file.

    Non-blocking: any write error is logged and swallowed so it never
    interrupts the main pipeline.
    """
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        path = _ensure_dir() / f"predictions_{today}.jsonl"
        record = {
            "ticker": ticker,
            "verdict": verdict,
            "conviction": conviction,
            "composite_score": composite_score,
            "horizon": horizon,
            "price_at_prediction": price_at_prediction,
            "predicted_at": datetime.now(timezone.utc).isoformat(),
        }
        with path.open("a") as f:
            f.write(json.dumps(record) + "\n")
        log.info("backtest_prediction_saved", ticker=ticker, verdict=verdict)
    except Exception as exc:
        log.warning("backtest_save_failed", ticker=ticker, error=str(exc))


def check_outcomes(min_days_elapsed: int = 25) -> list[dict]:
    """
    Scan all prediction files and return outcomes for predictions whose
    horizon has elapsed (or is within min_days_elapsed of elapsing).

    For each mature prediction, fetches the current price from yfinance
    and computes actual_return = (current - entry) / entry.
    """
    bt_dir = _BACKTEST_DIR
    if not bt_dir.exists():
        return []

    now = datetime.now(timezone.utc)
    outcomes: list[dict] = []

    for jsonl_path in sorted(bt_dir.glob("predictions_*.jsonl")):
        for line in jsonl_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                predicted_at = datetime.fromisoformat(rec["predicted_at"])
                horizon = rec.get("horizon") or "medium_term"
                target_days = _HORIZON_DAYS.get(horizon, 60)
                elapsed = (now - predicted_at).days

                if elapsed < (target_days - min_days_elapsed):
                    continue  # not mature yet

                entry_price = rec.get("price_at_prediction")
                if not entry_price:
                    continue

                ticker = rec["ticker"]
                try:
                    t = yf.Ticker(ticker)
                    info = t.info or {}
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
    bt_dir = _BACKTEST_DIR
    if not bt_dir.exists():
        return []

    now = datetime.now(timezone.utc)
    records: list[dict] = []

    for jsonl_path in sorted(bt_dir.glob("predictions_*.jsonl")):
        for line in jsonl_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                if rec.get("ticker") != ticker:
                    continue
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
                log.warning(
                    "backtest_history_parse_failed", ticker=ticker, error=str(exc)
                )

    return sorted(records, key=lambda r: r.get("predicted_at", ""), reverse=True)
