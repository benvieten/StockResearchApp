"""
Loads config.yaml once at startup and exposes it via get_config().

All configurable values live in config.yaml — never hardcode model names,
cache paths, or thresholds anywhere else. get_config() is a thread-safe
singleton: the file is read exactly once per process.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import yaml
from pydantic import BaseModel

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


class AnthropicConfig(BaseModel):
    models: dict[str, str] = {}


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    models: dict[str, str] = {}


class CacheConfig(BaseModel):
    enabled: bool = True
    directory: str = "./cache"
    ttl_hours: int = 24
    schema_version: int = 1


class RateLimitsConfig(BaseModel):
    reddit_delay_seconds: float = 1.0
    anthropic_retry_max_attempts: int = 4
    anthropic_retry_base_delay_seconds: float = 2.0
    anthropic_retry_jitter_seconds: float = 0.5


class DataSourcesConfig(BaseModel):
    reddit_subreddits: list[str] = [
        "wallstreetbets",
        "stocks",
        "investing",
        "SecurityAnalysis",
    ]
    reddit_limit: int = 50


class QuantConfig(BaseModel):
    earnings_yield_min: float = 0.0
    earnings_yield_max: float = 0.15
    volatility_window_days: int = 90
    momentum_windows_months: list[int] = [3, 6, 12]


class SynthesisConfig(BaseModel):
    strong_buy_threshold: float = 0.75
    buy_threshold: float = 0.60
    hold_threshold: float = 0.40
    sell_threshold: float = 0.25


class ScreenerConfig(BaseModel):
    top_n: int = 15
    min_market_cap_millions: int = 500
    min_avg_volume: int = 500_000
    screener_queries: list[str] = [
        "most_actives",
        "day_gainers",
        "undervalued_large_caps",
    ]


class WatchlistConfig(BaseModel):
    max_concurrent: int = 2


class AppConfig(BaseModel):
    anthropic: AnthropicConfig = AnthropicConfig()
    ollama: OllamaConfig = OllamaConfig()
    signal_weights: dict[str, float] = {}
    regime_signal_weights: dict[str, dict[str, float]] = {}
    cache: CacheConfig = CacheConfig()
    rate_limits: RateLimitsConfig = RateLimitsConfig()
    data_sources: DataSourcesConfig = DataSourcesConfig()
    sector_etf_map: dict[str, str] = {}
    quant: QuantConfig = QuantConfig()
    synthesis: SynthesisConfig = SynthesisConfig()
    screener: ScreenerConfig = ScreenerConfig()
    watchlist: WatchlistConfig = WatchlistConfig()


_config: AppConfig | None = None
_lock = threading.Lock()


def get_config() -> AppConfig:
    """Return the singleton AppConfig, loading config.yaml on first call.

    OLLAMA_BASE_URL env var overrides ollama.base_url from config.yaml,
    so Docker deployments can point to host.docker.internal without
    changing the config file.
    """
    global _config
    if _config is None:
        with _lock:
            if _config is None:
                raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
                _config = AppConfig.model_validate(raw)
                ollama_url = os.environ.get("OLLAMA_BASE_URL")
                if ollama_url:
                    _config.ollama.base_url = ollama_url
    return _config
