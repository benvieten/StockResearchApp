# CLAUDE.md — Stock Research Multi-Agent App

Personal stock research tool. 6 parallel AI agents (fundamental, technical, quant, sector, sentiment, synthesis) via LangGraph. FastAPI + SSE backend, React + Tailwind frontend. All data from free public sources.

---

## Running Locally
```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
cd frontend && npm run dev   # → http://localhost:5173
```
Test a single agent: `python -m backend.agents.{name} AAPL`

---

## Current Status (2026-04-03)

Pipeline is fully built and working end-to-end.

**Built:** 6-agent LangGraph pipeline · market regime detection · regime-aware weights · trader profile · LLM signal caching (all 5 specialist agents) · analyst price targets + short interest + Fear & Greed in synthesis/sentiment · Piotroski F-Score + accruals in fundamental · backtest prediction store · stock screener (Reddit + yfinance + Yahoo trending) · watchlist endpoint · beginner UI

**Pending:**
1. Backtest UI — `/backtest/{ticker}` endpoint + inline track record widget
2. Local model integration — Ollama (RTX 3060: Qwen2.5-14B; M4 Pro: Qwen2.5-32B+) for Haiku agents
3. SQLite migration — when screener + backtest data needs cross-querying

---

## Code Rules

- Python 3.13, `async/await`, Pydantic v2 (`model_validate()`), type hints everywhere
- HTTP: `httpx.AsyncClient` only — never `requests` or `httpx.get()`
- Logging: `structlog` only — never `print()` or stdlib logging
- Format: `black` · Lint: `ruff`
- Never hardcode model names — always `model_router.get_model(agent_name)`; assignments in `config.yaml`
- Structured outputs: Anthropic native tool-use — not `instructor`
- Retries: `tenacity` `stop_after_attempt(4)`, `wait_exponential(multiplier=2, min=2, max=16) + wait_random(-0.5, 0.5)`
- Each agent: `async def run(ticker: str) -> {SignalModel}` + `if __name__ == "__main__":` CLI
- No `ta` library — use `pandas-ta`
- No bare `Exception` catches
- Never commit `cache/` or `backtest/`

---

## Critical Gotchas

- **LangGraph reducer**: use `Annotated[list, operator.add]` for list fields across parallel nodes
- **Pre-compute**: compute all ratios/indicators before the LLM call — never pass raw statements
- **yfinance nulls**: always null-check before division
- **SSE**: frontend must use `fetch()` + `getReader()` — not `EventSource` (GET only)
- **Agent failures**: return `[{"agent": name, "signal": None}]` not `[]`
- **Reddit**: requires `User-Agent` + `Accept` + `Accept-Language` headers or gets 403
- **Schema version**: bump `cache.schema_version` in `config.yaml` when data shape changes

---

## Key Config

- Models: Haiku → fundamental, technical, quant · Sonnet → sector, sentiment, synthesis
- Cache: `./cache/{ticker}_{source}_{YYYY-MM-DD}_v{schema_version}.json` (schema_version=2)
- Signal cache: `{ticker}_signal_{agent}` — busts daily
- Synthesis verdicts: ≥0.75 strong_buy · ≥0.60 buy · ≥0.40 hold · ≥0.25 sell · <0.25 strong_sell
- Watchlist: `recommended_horizon` (short_term/medium_term/long_term) used to group results
- Backtest: `backtest/predictions_YYYY-MM-DD.jsonl` — one record per `run_research()` call

---

## Data Sources

- **Reddit**: `/search.json?q={ticker}&sort=new` (sentiment) · `/hot.json` (screener) · 1s delay between subs
- **News**: Google News RSS `feedparser` · Finviz scrape (fallback to Google if 403)
- **Market**: `yfinance` for OHLCV, financials, analyst targets, short interest
- **Screener**: Yahoo trending + yfinance `most_actives/day_gainers/undervalued_large_caps` + Reddit hot
- **Macro**: `fear-greed` PyPI library (CNN Fear & Greed Index)
- **StockTwits**: unreliable — do not use

---

## Stack

`anthropic` · `langgraph` · `langchain-anthropic` · `fastapi` · `uvicorn[standard]` · `sse-starlette` · `yfinance` · `pandas-ta` · `httpx` · `pydantic>=2.0` · `pydantic-settings` · `pyyaml` · `tenacity` · `structlog` · `feedparser` · `beautifulsoup4` · `fear-greed`
