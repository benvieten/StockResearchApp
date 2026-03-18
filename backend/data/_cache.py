"""
Shared cache helpers for all data modules.

Cache key format: {ticker}_{source}_{YYYY-MM-DD}_v{schema_version}.json
All paths are relative to the project root so they're consistent regardless
of the working directory.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# Resolve project root relative to this file: backend/data/_cache.py → ../../..
_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _get_cache_dir() -> Path:
    from backend.core.config import get_config

    cfg_dir = get_config().cache.directory
    p = Path(cfg_dir)
    return p if p.is_absolute() else (_PROJECT_ROOT / p).resolve()


def _schema_version() -> int:
    from backend.core.config import get_config

    return get_config().cache.schema_version


def _cache_enabled() -> bool:
    from backend.core.config import get_config

    return get_config().cache.enabled


def _cache_path(ticker: str, source: str) -> Path:
    today = date.today().isoformat()
    v = _schema_version()
    return _get_cache_dir() / f"{ticker}_{source}_{today}_v{v}.json"


def load_cache(ticker: str, source: str) -> Any | None:
    """Return cached data if a valid entry exists for today, else None."""
    if not _cache_enabled():
        return None
    path = _cache_path(ticker, source)
    if path.exists():
        log.debug("cache_hit", ticker=ticker, source=source, path=str(path))
        return json.loads(path.read_text(encoding="utf-8"))
    log.debug("cache_miss", ticker=ticker, source=source)
    return None


def save_cache(ticker: str, source: str, data: Any) -> None:
    """Write data to today's cache file."""
    if not _cache_enabled():
        return
    cache_dir = _get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(ticker, source)
    path.write_text(json.dumps(data, default=str, ensure_ascii=False), encoding="utf-8")
    log.debug("cache_write", ticker=ticker, source=source, path=str(path))
