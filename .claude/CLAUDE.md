# CLAUDE.md — Stock Research Multi-Agent App

This file is read automatically by Claude Code at startup. Follow every instruction here for the duration of this project. These rules are not suggestions.

---

## What This Project Is

A multi-agent stock research application. Six specialized agents run in parallel via LangGraph, each producing a structured signal on a given stock ticker. A synthesis agent combines those signals into a final investment opinion. The backend is FastAPI. The frontend is React. All LLM calls go through Anthropic only. All data comes from free sources — no paid API keys exist in this project.

Full build instructions and phase-by-phase validation checkpoints are in `README.md`. Read it before building anything.

---

## Project Structure

```
stock-research-app/
├── backend/
│   ├── agents/          # One file per agent
│   ├── core/            # graph.py, model_router.py, data_models.py, config.py
│   ├── data/            # price.py, news.py, reddit.py, stocktwits.py
│   └── main.py          # FastAPI entrypoint
├── frontend/
│   ├── src/
│   │   ├── components/  # One file per UI component
│   │   └── App.jsx
│   └── package.json
├── cache/               # Local JSON cache — never commit this
├── config.yaml          # Model assignments, weights, cache settings
├── pyproject.toml       # Makes `pip install -e .` work
├── requirements.txt
├── README.md
└── CLAUDE.md            # This file
```

---

## Non-Negotiable Rules

### Build Order
Follow the phases in `README.md` exactly. The order is:
1. Data layer (`backend/data/`)
2. Pydantic schemas + model router (`backend/core/data_models.py`, `backend/core/model_router.py`)
3. Agents one at a time: Fundamental → Technical → Quant → Sector → Sentiment → Synthesis
4. LangGraph graph (`backend/core/graph.py`)
5. FastAPI backend (`backend/main.py`)
6. React frontend (`frontend/`)

**Do not scaffold or stub future phases while working on an earlier one.** Complete each phase, validate it, then move on.

### Tests After Every Phase
Run `make test-phaseN` after completing each phase. All tests in that phase must pass before proceeding. Fix failures immediately — do not skip.

### Validation Before Proceeding
Every phase has a `make validate-phaseN` command. Do not start the next phase until the current one passes with real, non-empty data for `AAPL`.

### Test Ticker
Use `AAPL` as the default ticker for all development and testing.

---

## Config Files Already Exist — Do Not Recreate

`config.yaml`, `requirements.txt`, `requirements.lock`, `pytest.ini`, `Makefile`, `.pre-commit-config.yaml`, `.env.example`, and `pyproject.toml` are already written and committed. Do not overwrite them unless explicitly fixing a bug in them.

---

## Cost & API Usage Rules

### Caching
- Every external data fetch must check `./cache/{ticker}_{source}_{YYYY-MM-DD}_v1.json` before making a network call
- If a valid cache entry exists for today, return it — do not re-fetch
- Write to cache immediately after every successful fetch
- This applies to: yfinance, Google News RSS, Finviz, Reddit, StockTwits
- The `cache/` directory is gitignored — do not commit it

### LLM Calls
- **Never hardcode a model name anywhere in the codebase.** Always call `model_router.get_model(agent_name)` to get the assigned model
- Model assignments live in `config.yaml` and nowhere else
- Current model IDs:
  - Haiku agents (technical, fundamental, quant): `claude-haiku-4-5-20251001`
  - Sonnet agents (sector, sentiment, synthesis): `claude-sonnet-4-6`
- Do not upgrade a Haiku agent to Sonnet without explicitly changing `config.yaml`
- When testing a single agent, run `python -m backend.agents.{name} AAPL` — do not trigger the full pipeline

### Structured Outputs
Use Anthropic native structured outputs — **do not use the `instructor` library**:
```python
from anthropic import Anthropic
client = Anthropic()
response = client.messages.parse(
    model=model_router.get_model("fundamental"),
    max_tokens=1024,
    messages=[{"role": "user", "content": prompt}],
    response_model=FundamentalSignal,
)
signal = response.parsed
```

### Retries & Rate Limits
- Wrap every Anthropic API call with `tenacity`:
  ```python
  from tenacity import retry, stop_after_attempt, wait_exponential, wait_random
  @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=16) + wait_random(-0.5, 0.5))
  ```
- Add `asyncio.sleep(1)` between Reddit subreddit requests
- If Finviz or Reddit returns empty or blocks, log the failure, mark signal as `data_quality: "partial"`, and continue — never crash the pipeline over a single data source

---

## Code Conventions

### Python
- Python 3.11+ (project uses 3.13.3)
- Use `async/await` throughout — all agent functions and data fetchers must be async
- Pydantic v2 for all data models — use `model_validate()`, not `parse_obj()`
- Type hints on every function signature
- Each agent module: `async def run(ticker: str) -> {SignalModel}`
- Each data module: `async def get_ohlcv(ticker: str) -> dict`
- Use `httpx.AsyncClient` for all HTTP requests — not `requests`, not `httpx.get()`
- Format with `black`, lint with `ruff`
- Logging: use `structlog` — not `print()`, not stdlib `logging` directly

### Standalone Agent CLI
Every agent must be runnable from the command line and print valid JSON:
```bash
python -m backend.agents.fundamental AAPL
# prints: {"quality_score": 0.72, "valuation_verdict": "fair", ...}
```
Implement with `if __name__ == "__main__":` using `asyncio.run()` and `sys.argv[1]` for the ticker.

### Configuration
- All configurable values live in `config.yaml` — no magic numbers or hardcoded model strings
- Load config once at startup via `get_config()` in `core/config.py` using `pydantic-settings`
- Do not re-read the file on every request

### Error Handling
- Use specific exception types — do not catch bare `Exception` unless you re-raise or log full traceback
- If an agent fails entirely, synthesis must note the missing signal and proceed — never propagate an agent exception to the API layer
- FastAPI endpoints must return: `{"error": str, "ticker": str, "phase": str}`

---

## Critical Bug Prevention

### LangGraph Reducer (Most Common Silent Bug)
**ALWAYS** use `Annotated[list, operator.add]` for any list field accumulated across parallel nodes. Without this, parallel agent nodes silently overwrite each other's output:
```python
import operator
from typing import Annotated, TypedDict

class ResearchState(TypedDict):
    ticker: str
    raw_data: dict
    agent_signals: Annotated[list, operator.add]  # ← REQUIRED
    final_report: dict | None
```
A test in `backend/tests/phase4/test_graph.py` asserts this at import time.

### Pre-Computation Rule
**Always compute all financial ratios, technical indicators, and quant scores BEFORE the LLM call.** Pass computed numbers to the LLM — never raw financial statements. This prevents hallucination of ratio calculations.

### yfinance Null-Check Rule
**Always null-check every yfinance field before computing ratios.** Many fields return `None` for valid tickers. Division by None crashes silently in some contexts. Pattern:
```python
pe = (price / eps) if eps and eps != 0 else None
```

### SSE POST Limitation
The frontend must use `fetch()` + `response.body.getReader()` for SSE — **not** `EventSource`. The native `EventSource` API only supports GET requests; our SSE endpoint is POST.

---

## Library Stack

| Purpose | Library |
|---------|---------|
| LLM calls | `anthropic` (native structured outputs) |
| Agent orchestration | `langgraph`, `langchain-anthropic` |
| API server | `fastapi`, `uvicorn[standard]`, `sse-starlette` |
| Market data | `yfinance` |
| News parsing | `feedparser`, `beautifulsoup4` |
| HTTP client | `httpx` |
| Data processing | `pandas`, `numpy` |
| Technical indicators | `pandas-ta` (NOT the `ta` library) |
| Data validation | `pydantic>=2.0` |
| Config loading | `pydantic-settings` |
| Config file | `pyyaml` |
| Env vars | `python-dotenv` |
| Retry logic | `tenacity` |
| Logging | `structlog` |
| Cache | `diskcache` |
| Formatting | `black`, `ruff` |
| Testing | `pytest`, `pytest-asyncio` |

---

## Data Layer Specifics

### yfinance Quirks
- `ticker.financials` returns columns as dates — always sort and take the most recent 4–8 quarters
- Some tickers return `None` for certain financial fields — always null-check before computing ratios
- Rate limit is soft but real — add a short delay if fetching data for multiple tickers in sequence

### Reddit Public API
- Endpoint: `https://www.reddit.com/r/{sub}/search.json?q={ticker}&sort=new&limit=50`
- Must include a browser-like `User-Agent` header — Reddit blocks the default Python UA
- Subreddits: `wallstreetbets`, `stocks`, `investing`, `SecurityAnalysis`
- Sleep 1 second between each subreddit request
- Extract: `title`, `selftext`, `score`, `upvote_ratio`, `num_comments`, `author`, `author_fullname`, account `created_utc`, post `created_utc`, `subreddit`

### StockTwits
- Endpoint: `https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json`
- No auth required
- `sentiment` field is `{"basic": "Bullish"}`, `{"basic": "Bearish"}`, or absent — handle all three

### Google News RSS
- URL: `https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en`
- Parse with `feedparser`
- Each entry: `title`, `link`, `published`, `source.title`

### Finviz Scraping
- URL: `https://finviz.com/quote.ashx?t={ticker}`
- Target `id="news-table"` — carry forward last seen date if only time is shown
- Use realistic `User-Agent`. If blocked (403 or empty table), log and continue with just Google News

---

## Agent Specifics

### Technical Agent
Use `pandas-ta` (not `ta`). Compute: `EMA_20`, `EMA_50`, `EMA_200`, `RSI_14`, `MACD`, `MACD_signal`, `BB_upper`, `BB_lower`, `ATR_14`, `OBV`. Derive support/resistance from lowest low and highest high of last 20 candles.

### Synthesis Agent
Map composite score to verdict:
- `0.75–1.0` → `strong_buy`
- `0.60–0.75` → `buy`
- `0.40–0.60` → `hold`
- `0.25–0.40` → `sell`
- `0.0–0.25` → `strong_sell`

---

## LangGraph Graph

- Use `StateGraph` with `ResearchState` TypedDict (with reducer — see Critical Bug Prevention above)
- Agents 1–5 fan out in parallel from a single `fetch_data` node
- Synthesis node joins all 5 agent nodes
- Use LangGraph's streaming API to emit node completion events

---

## FastAPI Conventions

- All route handlers must be `async def`
- Use lifespan context manager for startup/shutdown
- Validate ticker with regex: `^[A-Z]{1,5}$` — return 422 for invalid tickers
- SSE endpoint uses `sse-starlette` — emit JSON-serialized events
- Add `X-Accel-Buffering: no` header on SSE responses (required for nginx proxying)
- Do not use background tasks for the main pipeline — await it directly

---

## React Conventions

- Vite + React 18
- Tailwind CSS for all styling — no CSS modules, no styled-components
- Component files are PascalCase: `AgentProgressTracker.jsx`
- Use `fetch()` + `response.body.getReader()` for SSE — **NOT** native `EventSource`
- No global state manager — `useState` and prop drilling is fine
- Dark mode only — no toggle

---

## What Not To Do

- Do not use `requests` — use `httpx`
- Do not use `openai` SDK — use `anthropic` or `langchain-anthropic`
- Do not use the `instructor` library — use Anthropic native structured outputs
- Do not use the `ta` library — use `pandas-ta`
- Do not hardcode any model name outside of `config.yaml`
- Do not mock data — always use real fetched/cached data
- Do not run the full pipeline to test a single agent
- Do not commit the `cache/` directory
- Do not add `print()` debug statements — use `structlog`
- Do not catch bare `Exception` without logging the full traceback
- Do not build the frontend until the FastAPI backend is fully validated
- Do not skip `make test-phaseN` before moving to the next phase
- Do not recreate config files that already exist (`config.yaml`, `pytest.ini`, `Makefile`, etc.)

---

## Current Status (as of 2026-03-20)

The full pipeline is built and working end-to-end. All six phases are complete. The app runs locally with `uvicorn backend.main:app --reload --port 8000` and `npm run dev` in `frontend/`.

### What Has Been Built (Beyond the Original Phases)

#### Market Regime Detection (`backend/core/regime.py`)
- Phase 1 threshold-based classifier using SPY + VIX via yfinance
- Three signals: VIX level, EMA-200 slope, price vs EMA-200
- Output: `RegimeSignal` with `regime` ("bull"/"bear"/"transitional"), `confidence`, VIX, ADX
- Disk-cached daily (`SPY_regime_YYYY-MM-DD_v1.json`) — fast on repeat calls
- Emitted as first SSE event (`{"type": "regime", ...}`) before agents start
- Phase 2 HMM design documented in `docs/HMM_IMPLEMENTATION.md` — not yet implemented
- **IMPORTANT**: uvicorn must be started with `--reload` or restarted after code changes, otherwise the running process uses the old in-memory module

#### Regime-Aware Agent Weights (`config.yaml`, `backend/core/config.py`)
- `regime_signal_weights` in `config.yaml`: bull/bear/transitional presets
- Bull: technical 0.30, fundamental 0.25; Bear: fundamental 0.40, technical 0.15
- Applied in synthesis agent before profile adjustments

#### Trader Profile (`backend/core/data_models.py`, frontend)
- `TraderProfile` Pydantic model: `risk_tolerance`, `time_horizon`, `goal`, `experience`
- Frontend shows a 4-question form between ticker entry and analysis
- Profile sent in SSE request body; forwarded through graph to synthesis agent
- Weight multipliers applied per dimension, then renormalized
- Profile context injected into synthesis LLM prompt

#### Anti-Hype / Anti-Overfitting Features
- **Hype spike discount** in `sentiment.py`: mention volume tiers (100/175/240) compress bullish scores
- **Full consensus cap** in `synthesis.py`: if all agents agree direction, conviction capped at "medium"
- **Statistical anomaly metrics** in `quant.py`: `return_zscore`, `volume_ratio`, `bb_percentile`, `rsi_percentile` added to `factor_breakdown`

#### Beginner-Friendly UI
- **ExplainTab** (`frontend/src/components/ExplainTab.tsx`): static tab ("How to Read This") explaining all agents, verdicts, scores, regime, statistical metrics, and synthesis in plain English
- **DummiesMode** (`frontend/src/components/DummiesMode.tsx`): AI-generated "Explain Like I'm Dumb" toggle, calls `/api/research/explain-simple`
- **RegimeBadge**: bull=emerald, bear=red, transitional=amber in the report top bar
- **TraderProfileChip**: 4 purple pills showing selected profile in report header
- **Statistical Signals section** in QuantDetails: color-coded with hint text per metric

#### Display Fixes in `frontend/src/components/SignalCard.tsx`
- `KEY_LABELS` expanded with `_pct`-suffix keys, `fcf_yield`, `pe_ratio`, `pb_ratio`, `ps_ratio`
- `FRACTION_PCT_KEYS` set: known fraction keys (gross_margin, roe, etc.) auto-multiply by 100 and display with `%`
- `_pct`-suffix keys display with `%` directly
- `formatValue()` helper centralises all value formatting
- StockTwits filtered from sentiment `source_breakdown` display
- Synthesis card summary shows verdict + conviction instead of missing `composite_score`

### Pending Tasks
1. **Commit all changes** — run `git add` and `git commit` before switching devices
2. **Test after backend restart** — with `--reload`, verify regime badge appears in top bar for a fresh run
3. **LLM signal caching** — cache per-agent LLM outputs to `{ticker}_{agent}_signal_YYYY-MM-DD_v1.json`; eliminates repeat API costs for same-day re-runs
4. **Local model integration** — route Haiku agents to Ollama (Qwen2.5-14B on RTX 3060 or 32B on M4 Pro), keep Sonnet for synthesis

### Hardware Available for Local Models
- **Mac M4 Pro** (dev machine): unified memory, can run Qwen2.5-32B (24GB config) or Qwen2.5-72B (48GB config) via Ollama/MLX
- **Windows PC with RTX 3060 12GB**: can run Qwen2.5-14B comfortably; serve via Ollama over LAN
- Planned split: GPU machine handles Haiku-equivalent agents (fundamental, technical, quant), M4 Pro handles synthesis-equivalent

### Running Locally
```bash
# Backend (from project root)
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm run dev

# Open http://localhost:5173
```

### Key Files Modified Since Initial Build
| File | What Changed |
|------|-------------|
| `backend/core/regime.py` | New file — market regime classifier with disk cache |
| `backend/core/graph.py` | Added regime pre-fetch, trader_profile state, stream_research emits regime event first |
| `backend/core/data_models.py` | Added `TraderProfile` model |
| `backend/core/config.py` | Added `regime_signal_weights` config field |
| `backend/agents/synthesis.py` | Regime weights, profile adjustments, consensus cap, hype guidance in prompt |
| `backend/agents/sentiment.py` | Hype volume discount, bot risk prompt guidance |
| `backend/agents/technical.py` | Regime context injected into LLM prompt |
| `backend/agents/quant.py` | 4 statistical anomaly metrics added to factor_breakdown |
| `backend/main.py` | `ResearchRequest` accepts `trader_profile`; `/research/explain-simple` endpoint |
| `config.yaml` | `regime_signal_weights` added |
| `frontend/src/App.tsx` | Profile view added between hero and researching; regime state captured |
| `frontend/src/types.ts` | `TraderProfile`, `RegimeInfo`, regime SSE event type added |
| `frontend/src/components/ReportDashboard.tsx` | RegimeBadge, TraderProfileChip, tab switcher (Analysis / How to Read This) |
| `frontend/src/components/SignalCard.tsx` | Percentage formatting, expanded KEY_LABELS, synthesis summary fix |
| `frontend/src/components/ExplainTab.tsx` | New file — static beginner-friendly guide |
| `frontend/src/components/TraderProfileForm.tsx` | New file — 4-question profile form |
| `docs/HMM_IMPLEMENTATION.md` | New file — Phase 2 HMM design spec |
