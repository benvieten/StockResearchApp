# CLAUDE.md — Stock Research Multi-Agent App

This file is read automatically by Claude Code at startup. Follow every instruction here. These rules are not suggestions.

---

## App Vision

A personal stock research tool that does in seconds what would normally take hours. Two core modes:

1. **Analyze on demand** — enter any ticker, get a multi-dimensional verdict from 6 parallel AI agents (fundamental quality, technical setup, quant factors, sector positioning, sentiment) synthesized into a single clear opinion tailored to your trader profile
2. **Discover automatically** — an agent-curated watchlist that surfaces momentum plays, quality compounders, and event-driven setups from live Reddit, news, and market data every day — no static lists, no manual curation

**North star constraints:**
- All data from free public sources — no paid APIs, ever
- All analysis reflects the market *today*, not a cached snapshot from weeks ago
- Moving toward fully local LLMs (Ollama on M4 Pro + RTX 3060) so nothing costs money and nothing leaves the machine

---

## What This Project Is

Six specialized agents run in parallel via LangGraph, each producing a structured signal on a given ticker. A synthesis agent combines those signals into a final investment opinion adjusted for market regime and trader profile. Backend is FastAPI + SSE. Frontend is React + Tailwind. All LLM calls go through Anthropic (transitioning to local Ollama).

---

## Project Structure

```
stock-research-app/
├── backend/
│   ├── agents/          # One file per agent
│   ├── core/            # graph.py, model_router.py, data_models.py, config.py, regime.py
│   ├── data/            # price.py, news.py, reddit.py, screener.py (planned)
│   └── main.py          # FastAPI entrypoint
├── frontend/
│   ├── src/
│   │   ├── components/  # One file per UI component
│   │   └── App.tsx
│   └── package.json
├── cache/               # Local JSON cache — never commit this
├── config.yaml          # Model assignments, weights, cache settings
├── pyproject.toml
└── .claude/CLAUDE.md    # This file
```

---

## Non-Negotiable Rules

### Build Order
1. Data layer (`backend/data/`)
2. Pydantic schemas + model router
3. Agents: Fundamental → Technical → Quant → Sector → Sentiment → Synthesis
4. LangGraph graph
5. FastAPI backend
6. React frontend

Do not scaffold future phases while working on an earlier one.

### Tests & Validation
- Run `make test-phaseN` after each phase. Fix failures immediately — do not skip.
- Use `AAPL` as the default test ticker.

### Config Files Already Exist — Do Not Recreate
`config.yaml`, `requirements.txt`, `pytest.ini`, `Makefile`, `.pre-commit-config.yaml`, `.env.example`, `pyproject.toml`

---

## Cost & API Usage Rules

### Caching
- Every external fetch checks `./cache/{ticker}_{source}_{YYYY-MM-DD}_v1.json` first
- Write to cache after every successful fetch
- Applies to: yfinance, Google News RSS, Finviz, Reddit
- `cache/` is gitignored — never commit it

### LLM Calls
- **Never hardcode a model name.** Always call `model_router.get_model(agent_name)`
- Model assignments live in `config.yaml` only
- Current models: Haiku agents (technical, fundamental, quant): `claude-haiku-4-5-20251001` · Sonnet agents (sector, sentiment, synthesis): `claude-sonnet-4-6`
- When testing a single agent: `python -m backend.agents.{name} AAPL`

### Structured Outputs
Use Anthropic native tool-use structured outputs — **not** the `instructor` library.

### Retries
Wrap every Anthropic call with `tenacity`: `stop_after_attempt(4)`, `wait_exponential(multiplier=2, min=2, max=16) + wait_random(-0.5, 0.5)`

---

## Code Conventions

- Python 3.13, `async/await` throughout, Pydantic v2 (`model_validate()`), type hints everywhere
- HTTP: `httpx.AsyncClient` only — not `requests`, not `httpx.get()`
- Logging: `structlog` — not `print()`, not stdlib logging
- Format: `black` · Lint: `ruff`
- Each agent: `async def run(ticker: str) -> {SignalModel}` + `if __name__ == "__main__":` CLI

---

## Critical Bug Prevention

### LangGraph Reducer
**Always** use `Annotated[list, operator.add]` for list fields accumulated across parallel nodes — without it they silently overwrite each other.

### Pre-Computation Rule
Compute all ratios and indicators **before** the LLM call. Never pass raw financial statements to the LLM.

### yfinance Null-Check
Always null-check before division: `pe = (price / eps) if eps and eps != 0 else None`

### SSE POST Limitation
Frontend must use `fetch()` + `response.body.getReader()` — **not** `EventSource` (GET only).

### uvicorn --reload
Always start with `--reload`. Without it, code changes are invisible to the running process.

---

## Library Stack

| Purpose | Library |
|---------|---------|
| LLM | `anthropic` |
| Orchestration | `langgraph`, `langchain-anthropic` |
| API | `fastapi`, `uvicorn[standard]`, `sse-starlette` |
| Market data | `yfinance` |
| News | `feedparser`, `beautifulsoup4` |
| HTTP | `httpx` |
| Data | `pandas`, `numpy` |
| Indicators | `pandas-ta` (NOT `ta`) |
| Validation | `pydantic>=2.0`, `pydantic-settings` |
| Config | `pyyaml` |
| Retry | `tenacity` |
| Logging | `structlog` |
| Cache | `diskcache` |

---

## Data Layer

### Reddit
- Endpoint: `https://www.reddit.com/r/{sub}/search.json?q={ticker}&sort=new&limit=50`
- Browser-like `User-Agent` required — Reddit blocks the default Python UA
- Subreddits: `wallstreetbets`, `stocks`, `investing`, `SecurityAnalysis`
- Sleep 1s between subreddit requests

### StockTwits
- Endpoint: `https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json`
- **Unreliable — returns empty/blocked frequently.** Do not depend on it for core features.

### Google News RSS
- `https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en` via `feedparser`

### Finviz
- Scrape `id="news-table"` at `finviz.com/quote.ashx?t={ticker}`. If blocked (403), fall back to Google News only.

---

## Agent Specifics

### Technical
`pandas-ta`: EMA_20/50/200, RSI_14, MACD, BB_upper/lower, ATR_14, OBV. Support/resistance from 20-candle high/low.

### Synthesis
Verdict thresholds: ≥0.75 → strong_buy · ≥0.60 → buy · ≥0.40 → hold · ≥0.25 → sell · <0.25 → strong_sell

`FinalReport` includes `recommended_horizon` (short_term/medium_term/long_term) and `horizon_rationale` — set by synthesis LLM, used to sort the watchlist.

---

## FastAPI Conventions

- All handlers `async def`
- Ticker validation: `^[A-Z]{1,5}$` — 422 for invalid
- SSE: `X-Accel-Buffering: no` header required
- Do not use background tasks for the main pipeline

---

## React Conventions

- Vite + React 18, Tailwind CSS, dark mode only
- PascalCase component files
- SSE: `fetch()` + `getReader()` — never `EventSource`
- No global state manager

---

## What Not To Do

- No `requests` · No `openai` SDK · No `instructor` · No `ta` library
- No hardcoded model names outside `config.yaml`
- No mocked data · No `print()` debug · No bare `Exception` catches
- No frontend work until FastAPI backend is validated
- No committing `cache/`

---

## Current Status (as of 2026-03-27)

Full pipeline is built and working end-to-end.

### What's Built
- **6-agent pipeline**: Fundamental, Technical, Quant, Sector, Sentiment, Synthesis via LangGraph
- **Market regime detection** (`backend/core/regime.py`): SPY+VIX classifier, 3 regimes, disk-cached daily
- **Regime-aware weights**: bull/bear/transitional presets in `config.yaml`, applied before synthesis
- **Trader profile**: 4-dimension form (risk, horizon, goal, experience) → adjusts agent weights + LLM prompt
- **Anti-hype features**: hype spike discount in sentiment, full-consensus cap in synthesis
- **Statistical anomaly metrics**: return_zscore, volume_ratio, bb_percentile, rsi_percentile in quant
- **Watchlist feature**: `/watchlist` endpoint runs N tickers in parallel, groups results by `recommended_horizon`; `WatchlistView.tsx` shows 3-column layout (short/medium/long); `FinalReport` now includes `recommended_horizon` + `horizon_rationale`
- **Beginner UI**: ExplainTab (how-to guide), DummiesMode (ELI5 toggle), RegimeBadge, TraderProfileChips

### Pending
1. **Stock screener** (`backend/data/screener.py`) — replace hardcoded watchlist tickers with agent-discovered candidates from Reddit hot posts + yfinance screener + Google News (StockTwits excluded — unreliable)
2. **LLM signal caching** — cache per-agent outputs to `{ticker}_{agent}_signal_YYYY-MM-DD_v1.json`; eliminates repeat API costs for same-day re-runs
3. **Local model integration** — route Haiku agents to Ollama (RTX 3060: Qwen2.5-14B; M4 Pro: Qwen2.5-32B+); keep Anthropic only for synthesis fallback; add `ollama` backend type to `model_router.py`
4. **Commit current session changes**

### Hardware for Local Models
- **M4 Pro** (dev): Qwen2.5-32B (24GB) or 72B (48GB) via Ollama/MLX
- **RTX 3060 12GB** (Windows): Qwen2.5-14B via Ollama over LAN
- Split: GPU handles Haiku-equivalent agents; M4 handles synthesis-equivalent

### Running Locally
```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000   # backend
cd frontend && npm run dev                       # frontend → http://localhost:5173
```
