"""
Token usage and cost tracking.

Appends one JSON record per LLM call to usage/usage_YYYY-MM-DD.jsonl.
Ollama calls are recorded with cost=0.0 (local inference is free).

Public API:
    log_usage(agent, model, backend, input_tokens, output_tokens, ticker="")
    get_daily_summary(date_str=None) -> dict
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import structlog

log = structlog.get_logger()

# Pricing per million tokens (USD) — update when Anthropic changes rates.
# https://www.anthropic.com/pricing
_PRICES: dict[str, tuple[float, float]] = {
    # model_id: (input_$/M, output_$/M)
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}

_USAGE_DIR = Path("usage")
_lock = threading.Lock()


def _cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in _PRICES:
        return 0.0
    in_price, out_price = _PRICES[model]
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


def log_usage(
    agent: str,
    model: str,
    backend: str,
    input_tokens: int,
    output_tokens: int,
    ticker: str = "",
) -> None:
    """Append one usage record to today's JSONL file. Never raises."""
    cost = _cost(model, input_tokens, output_tokens)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "agent": agent,
        "model": model,
        "backend": backend,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
    }
    try:
        _USAGE_DIR.mkdir(exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = _USAGE_DIR / f"usage_{date_str}.jsonl"
        with _lock:
            with path.open("a") as f:
                f.write(json.dumps(record) + "\n")
        log.debug(
            "usage_logged",
            agent=agent,
            ticker=ticker,
            cost_usd=cost,
            total_tokens=input_tokens + output_tokens,
        )
    except Exception as exc:
        log.warning("usage_log_failed", error=str(exc))


def get_daily_summary(date_str: str | None = None) -> dict:
    """
    Return a usage summary for *date_str* (YYYY-MM-DD, defaults to today UTC).

    Response shape:
        {
          "date": "2026-04-05",
          "calls": 12,
          "total_tokens": 34567,
          "total_cost_usd": 0.142,
          "by_agent": {
            "synthesis": {
              "calls": 2, "input_tokens": 8000, "output_tokens": 3000,
              "cost_usd": 0.069, "model": "claude-sonnet-4-6"
            },
            ...
          }
        }
    """
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    path = _USAGE_DIR / f"usage_{date_str}.jsonl"
    if not path.exists():
        return {
            "date": date_str,
            "calls": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "by_agent": {},
        }

    records: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    total_cost = 0.0
    total_tokens = 0
    by_agent: dict[str, dict] = {}

    for r in records:
        total_cost += r["cost_usd"]
        total_tokens += r["input_tokens"] + r["output_tokens"]
        agent = r["agent"]
        if agent not in by_agent:
            by_agent[agent] = {
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "model": r["model"],
            }
        by_agent[agent]["calls"] += 1
        by_agent[agent]["input_tokens"] += r["input_tokens"]
        by_agent[agent]["output_tokens"] += r["output_tokens"]
        by_agent[agent]["cost_usd"] = round(
            by_agent[agent]["cost_usd"] + r["cost_usd"], 6
        )

    return {
        "date": date_str,
        "calls": len(records),
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "by_agent": by_agent,
    }
