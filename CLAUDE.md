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
│   ├── core/            # graph.py, model_router.py, data_models.py
│   ├── data/            # price.py, news.py, reddit.py, stocktwits.py
│   └── main.py          # FastAPI entrypoint
├── frontend/
│   ├── src/
│   │   ├── components/  # One file per UI component
│   │   └── App.jsx
│   └── package.json
├── cache/               # Local JSON cache — never commit this
├── config.yaml          # Model assignments, weights, cache settings
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
3. Agents one at a time, in this order: Fundamental → Technical → Quant → Sector → Sentiment → Synthesis
4. LangGraph graph (`backend/core/graph.py`)
5. FastAPI backend (`backend/main.py`)
6. React frontend (`frontend/`)

**Do not scaffold or stub future phases while working on an earlier one.** Complete each phase, validate it with real data, then move on.

### Validation Before Proceeding
Every phase has a validation command. Do not start the next phase until the current one passes. If something is not returning real, non-empty data for `AAPL`, fix it before moving forward.

### Test Ticker
Use `AAPL` as the default ticker for all development and testing. Write code that returns real data — no mocks, no hardcoded placeholder responses.

---

## Cost & API Usage Rules

These rules exist to prevent runaway Anthropic API costs during development. Follow them without exception.

### Caching
- Every external data fetch must check `/cache/{ticker}_{source}_{YYYY-MM-DD}.json` before making a network call
- If a valid cache entry exists for today, return it — do not re-fetch
- Write to cache immediately after every successful fetch
- This applies to: yfinance, Google News RSS, Finviz, Reddit, StockTwits
- The `cache/` directory is gitignored — do not commit it

### LLM Calls
- **Never hardcode a model name anywhere in the codebase.** Always call `model_router.get_model(agent_name)` to get the assigned model
- Model assignments live in `config.yaml` and nowhere else
- Haiku is assigned to: `technical`, `fundamental`, `quant`
- Sonnet is assigned to: `sector`, `sentiment`, `synthesis`
- Do not upgrade a Haiku agent to Sonnet without explicitly changing `config.yaml`
- When testing a single agent, run it in isolation via `python -m backend.agents.{name} AAPL` — do not trigger the full pipeline to test one agent

### Retries & Rate Limits
- Wrap every Anthropic API call in exponential backoff: base delay 2s, max 4 attempts, jitter ±0.5s
- Add `time.sleep(1)` between Reddit subreddit requests
- If Finviz or Reddit returns empty or blocks the request, log the failure, mark the signal as `data_quality: "partial"`, and continue — never crash the pipeline over a single data source

---

## Code Conventions

### Python
- Python 3.11+
- Use `async/await` throughout the backend — all agent functions and data fetchers must be async
- Pydantic v2 for all data models — use `model_validate()`, not `parse_obj()`
- Type hints on every function signature
- Each agent module must expose a single async entry point: `async def run(ticker: str) -> {SignalModel}`
- Each data module must expose clean async functions: e.g. `async def get_ohlcv(ticker: str) -> dict`
- Use `httpx` for all HTTP requests — not `requests`
- Format with `black`, lint with `ruff`

### Standalone Agent CLI
Every agent must be runnable from the command line and print valid JSON:
```bash
python -m backend.agents.fundamental AAPL
# prints: {"quality_score": 0.72, "valuation_verdict": "fair", ...}
```
Implement this with a `if __name__ == "__main__"` block using `asyncio.run()` and `sys.argv[1]` for the ticker.

### Configuration
- All configurable values live in `config.yaml` — no magic numbers or hardcoded model strings in agent or router code
- Load config once at startup via a `get_config()` function in `core/config.py` — do not re-read the file on every request

### Error Handling
- Use specific exception types — do not catch bare `Exception` unless you re-raise or log with full traceback
- If an agent fails entirely, the synthesis agent must note the missing signal and proceed with available data — it must never propagate an agent exception up to the API layer
- FastAPI endpoints must return structured error responses: `{"error": str, "ticker": str, "phase": str}`

---

## Data Layer Specifics

### yfinance Quirks
- `ticker.financials` returns columns as dates — always sort and take the most recent 4–8 quarters
- Some tickers return `None` for certain financial fields — always null-check before computing ratios
- Rate limit is soft but real — add a short delay if fetching data for multiple tickers in sequence

### Reddit Public API
- Endpoint: `https://www.reddit.com/r/{sub}/search.json?q={ticker}&sort=new&limit=50`
- Must include a browser-like `User-Agent` header — Reddit blocks the default Python `requests` UA
- Subreddits to query: `wallstreetbets`, `stocks`, `investing`, `SecurityAnalysis`
- Sleep 1 second between each subreddit request
- Extract from each post: `title`, `selftext`, `score`, `upvote_ratio`, `num_comments`, `author`, `author_fullname`, account `created_utc` from author profile if available, post `created_utc`, `subreddit`

### StockTwits
- Endpoint: `https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json`
- No auth required
- The `sentiment` field on each message is either `{"basic": "Bullish"}`, `{"basic": "Bearish"}`, or absent — handle all three cases

### Google News RSS
- URL: `https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en`
- Parse with `feedparser`
- Each entry has: `title`, `link`, `published`, `source.title`

### Finviz Scraping
- URL: `https://finviz.com/quote.ashx?t={ticker}`
- Target the element with `id="news-table"`
- Each row contains date/time (sometimes only time if same day as previous row — carry forward the last seen date), headline text, and source
- Use a realistic `User-Agent` header. If blocked (403 or empty table), log and continue with just Google News

---

## Agent Specifics

### Fundamental Agent
Compute these ratios from raw yfinance financial statement data before passing to the LLM:
`P/E`, `P/S`, `P/B`, `EV/EBITDA`, `gross_margin`, `operating_margin`, `net_margin`, `revenue_growth_qoq`, `revenue_growth_yoy`, `debt_to_equity`, `fcf_yield`, `roe`

Pass the computed dict to Haiku and ask it to: score overall quality (0–1), determine valuation verdict, and list key positive and negative flags.

### Technical Agent
Use the `ta` library. Compute: `EMA_20`, `EMA_50`, `EMA_200`, `RSI_14`, `MACD`, `MACD_signal`, `BB_upper`, `BB_lower`, `ATR_14`, `OBV`. Derive support/resistance from the lowest low and highest high of the last 20 candles.

Pass computed indicators to Haiku and ask it to: determine trend direction, assign a confidence score, and summarize the indicator picture.

### Quant Agent
No LLM call. Pure computation:
- Momentum: compute 3M/6M/12M returns for the ticker and SPY. Score = percentile of ticker return vs SPY return (0 = underperformed, 1 = outperformed)
- Quality: normalize ROE and inverse debt-to-equity to 0–1 range, average them
- Value: earnings yield = 1/PE, normalize to 0–1 using a reasonable min/max (e.g. 0–15% range)
- Low-vol: compute 90-day realized volatility (annualized std of daily returns), invert and normalize
- Composite = equal-weighted average of the four factor scores

### Sector Agent
Hardcode a sector-to-ETF map:
```python
SECTOR_ETF_MAP = {
    "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
    "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Energy": "XLE", "Industrials": "XLI", "Materials": "XLB",
    "Real Estate": "XLRE", "Utilities": "XLU", "Communication Services": "XLC"
}
```
Fetch peer tickers from a hardcoded peer map (build a reasonable one for the 20 most common tickers; fall back to sector ETF holdings if ticker not in map).

### Sentiment Agent
Apply bot detection heuristics to Reddit data before any LLM call:
- Account age < 30 days at time of post → `bot_flag: true`
- Same author, 3+ posts about same ticker in 24h window → `bot_flag: true`
- `upvote_ratio < 0.55` AND `score > 100` → `suspicious_flag: true`
- Mention spike: today's count > (mean + 2*std) of cached historical daily counts → `spike_flag: true`

Pass flagged and clean content separately to Sonnet. Instruct it to score sentiment for each source independently, assess bot risk, identify narrative themes, and produce an adjusted score that discounts flagged content proportionally to the bot_risk level.

### Synthesis Agent
Load weights from `config.yaml`. Map each agent's primary score to a 0–1 scale:
- Technical: `confidence` (already 0–1, direction flips sign)
- Fundamental: `quality_score`
- Quant: `composite_score`
- Sector: map `outperforming/inline/underperforming` → `1.0/0.5/0.0`
- Sentiment: `adjusted_score` remapped from `−1:1` to `0:1`

Compute weighted composite. Pass all 5 full signal objects + composite score to Sonnet. Prompt it to identify where agents conflict (e.g. strong technicals but weak fundamentals) and explicitly call those out in the `conflicts` field.

Map composite score to verdict:
- `0.75–1.0` → `strong_buy`
- `0.60–0.75` → `buy`
- `0.40–0.60` → `hold`
- `0.25–0.40` → `sell`
- `0.0–0.25` → `strong_sell`

---

## LangGraph Graph

- Use `StateGraph` with `ResearchState` TypedDict
- Agents 1–5 fan out in parallel from a single `fetch_data` node that pre-loads all cached/fetched data into state
- Synthesis node is connected to all 5 agent nodes as a join
- Use LangGraph's streaming API to emit node completion events — the FastAPI SSE endpoint subscribes to these

---

## FastAPI Conventions

- All route handlers must be `async def`
- Use a lifespan context manager for startup/shutdown (initialize model router, warm cache directory)
- Validate ticker with a regex: `^[A-Z]{1,5}$` — return 422 for invalid tickers
- SSE endpoint uses `sse-starlette` — emit JSON-serialized events with `event` and `data` fields
- Do not use background tasks for the main research pipeline — await it directly in the POST handler so errors surface cleanly

---

## React Conventions

- Vite + React 18
- Tailwind CSS for all styling — no CSS modules, no styled-components
- Component files are PascalCase: `AgentProgressTracker.jsx`
- Use `fetch` with the native `EventSource` API for SSE — no third-party SSE libraries
- No global state manager needed — `useState` and prop drilling is fine for this app's complexity
- Dark mode only — do not implement a toggle

---

## What Not To Do

- Do not use `requests` — use `httpx`
- Do not use `openai` SDK — use `anthropic` or `langchain-anthropic`
- Do not hardcode any model name outside of `config.yaml`
- Do not mock data — always use real fetched/cached data
- Do not run the full pipeline to test a single agent
- Do not commit the `cache/` directory
- Do not add `print()` debug statements — use Python `logging` with appropriate levels
- Do not catch bare `Exception` without logging the full traceback
- Do not build the frontend until the FastAPI backend is fully validated