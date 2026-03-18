You are building a stock research application from scratch. Read the `README.md` in the project root before writing a single line of code — it contains the build order, cost rules, caching requirements, and critical bug warnings that govern every decision you make in this project.

The `config.yaml`, `requirements.txt`, `.env.example`, `.pre-commit-config.yaml`, `.gitignore`, `pytest.ini`, and `Makefile` are already created. Do not recreate them. Read `config.yaml` before touching any model names or weights.

A full test suite already exists in `backend/tests/` organized by phase. **Run the relevant tests after completing each phase and fix all failures before moving on.** The tests are the validation checkpoint — not just the standalone CLI commands.

---

## Core Rules — Non-Negotiable

- **Follow the build order in the README exactly.** Complete and validate each phase before starting the next. Do not scaffold the entire project upfront.
- **Use `AAPL` as the test ticker throughout.** Every module you build must return real, non-empty data for AAPL before you move on.
- **Cache everything.** Every external data fetch must check `/cache/{ticker}_{source}_{date}_v1.json` first. The `_v1` suffix is the schema version — read it from `config.yaml`. Only fetch live data if no valid cache entry exists for today.
- **Never hardcode a model name.** Every LLM call must go through `model_router.get_model(agent_name)`. Model assignments live in `config.yaml` only.
- **Each agent must be independently runnable** via `python -m backend.agents.{name} AAPL` and print valid JSON to stdout before you wire it into the graph.
- **Do not run the full 6-agent pipeline** to test a single agent. Test in isolation to minimize API costs.
- **Pre-compute every ratio and indicator before any LLM call.** Never ask an LLM to compute or recall a number. Pass a completed dict. This is the primary hallucination defense.
- **Null-check every yfinance field.** yfinance returns `None` for missing data without warning. Always use `.get()` with a default. If a required field is `None`, mark `data_quality: "partial"` and continue.
- **Run tests after every phase.** Tests are in `backend/tests/phase{N}/`. Use `make test-phase1`, `make test-unit`, etc. Fix all failures before proceeding. Pure unit tests (`make test-unit`) run with no I/O and should always pass.

---

## Stack

- **Orchestration:** LangGraph with `Annotated[list, operator.add]` reducers on all parallel-written state fields (see Phase 4)
- **Backend:** FastAPI with Server-Sent Events for progress streaming via `sse-starlette`
- **Frontend:** React 18 + Vite + Tailwind CSS, dark mode only
- **LLM Provider:** Anthropic only — use the `anthropic` SDK directly (not `langchain-anthropic` for LLM calls)
- **Structured outputs:** Use `client.messages.parse(response_model=YourPydanticModel, ...)` for every agent LLM call — schema is enforced at token generation level, no JSON parsing needed
- **Model routing:** Haiku for Fundamental, Technical, Quant — Sonnet for Sector, Sentiment, Synthesis — read from `config.yaml`
- **Retry logic:** Use `tenacity` `@retry` decorator with `wait_exponential` + `wait_random` — no manual backoff loops
- **Logging:** Use `structlog` throughout — no `print()` statements
- **Config:** Use `pydantic-settings` in `core/config.py` for typed access to `config.yaml`

---

## Libraries Already in `requirements.txt`

Do not add duplicates. Key libraries and their purpose:

| Library | Purpose |
|---|---|
| `anthropic` | Anthropic SDK — use `client.messages.parse()` for structured outputs |
| `langgraph` | Graph orchestration |
| `langchain-anthropic` | Only needed if LangGraph requires it internally |
| `pandas-ta` | Technical indicators — use instead of `ta`. API: `df.ta.rsi()`, `df.ta.ema()` etc. |
| `tenacity` | Retry with exponential backoff: `@retry(wait=wait_exponential(multiplier=2, max=30) + wait_random(-0.5, 0.5), stop=stop_after_attempt(4))` |
| `structlog` | Structured logging — configure once in `main.py`, use `log = structlog.get_logger()` |
| `diskcache` | Thread-safe disk cache for concurrent agent writes |
| `pydantic-settings` | Typed config loading from `config.yaml` |
| `python-dotenv` | Load `.env` for `ANTHROPIC_API_KEY` |
| `httpx` | All HTTP requests — not `requests` |

---

## Data Sources — Free Only, No API Keys

| Source | What to fetch | Reliability | Notes |
|---|---|---|---|
| `yfinance` | OHLCV (1Y daily), income statement, balance sheet, cash flow, company info | Fragile — null-check everything | `.info` fields vary by ticker; `.financials` columns are `pd.Timestamp` — convert with `str(c.date())` |
| Google News RSS | Headlines: `https://news.google.com/rss/search?q={ticker}+stock` | Most reliable | Parse with `feedparser` |
| Finviz | News table: `https://finviz.com/quote.ashx?t={ticker}` | Blocks at scale | Fallback only — if 403 or empty, log and continue with Google News |
| Reddit JSON API | `https://www.reddit.com/r/{sub}/search.json?q={ticker}&sort=new&limit=50` | Works at low volume | Browser `User-Agent` header required; `time.sleep(1)` between subs |
| StockTwits | `https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json` | Stable | No key needed; `sentiment` field is `{"basic": "Bullish"}`, `{"basic": "Bearish"}`, or absent |
| SEC EDGAR XBRL | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` | Official, reliable | Fallback if yfinance returns incomplete financials; no auth; 10 req/sec |

---

## Phase 1 — Data Layer

Build `backend/data/` first. Each module must be runnable standalone and return real, non-empty data for AAPL.

**`price.py`**
- Fetch via `yfinance`: 1Y daily OHLCV, quarterly income statement, balance sheet, cash flow statement, company info dict
- Null-check every field. If a financial field is `None`, log it with `structlog` at WARNING level and exclude it from the returned dict — do not propagate `None` into ratio computation
- Cache all outputs with schema version suffix: `AAPL_ohlcv_2026-03-18_v1.json`, `AAPL_financials_2026-03-18_v1.json`, etc.
- Include `fetched_at` ISO timestamp in every cached result
- Expose: `async def get_ohlcv(ticker: str) -> dict`, `async def get_financials(ticker: str) -> dict`, `async def get_company_info(ticker: str) -> dict`
- If yfinance fails and a recent cache entry exists (within `ttl_hours`), return it with a `stale: true` flag rather than raising

**`news.py`**
- Fetch Google News RSS using `feedparser`; scrape Finviz as fallback (if Finviz returns 403 or empty table, log and skip)
- Return unified list: `{"headline": str, "source": str, "timestamp": str, "url": str}`
- Cache as `AAPL_news_2026-03-18_v1.json`

**`reddit.py`**
- Query all 4 subreddits sequentially with `time.sleep(1)` between each
- Browser `User-Agent` header required — Reddit blocks the default Python UA immediately
- Extract per post: `title`, `selftext`, `score`, `upvote_ratio`, `num_comments`, `author`, `author_created_utc`, `post_created_utc`, `subreddit`
- Cache as `AAPL_reddit_2026-03-18_v1.json`

**`stocktwits.py`**
- Fetch public stream; handle all three sentiment states: `"Bullish"`, `"Bearish"`, absent
- Extract: `body`, `sentiment` (or `null`), `created_at`, `user.followers`, `user.following`
- Cache as `AAPL_stocktwits_2026-03-18_v1.json`

**Validation checkpoint:** `python -m backend.data.price AAPL` returns real data and writes to `/cache` before proceeding.

---

## Phase 2 — Schemas, Config, and Model Router

**`core/config.py`**
- Use `pydantic-settings` to load `config.yaml` into a typed `AppConfig` model
- Expose a `get_config()` function that reads once and caches the result — do not re-read the file on every call

**`core/data_models.py`**

Define these Pydantic v2 models. Every LLM-produced signal model must include a `reasoning: str` field immediately before its primary score field — this enforces chain-of-thought output and reduces hallucination on interpretation tasks:

```python
from pydantic import BaseModel
from typing import Literal

class TechnicalSignal(BaseModel):
    reasoning: str                              # chain-of-thought before verdict
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float                           # 0.0 to 1.0
    key_levels: dict                            # {"support": float, "resistance": float}
    indicator_summary: str
    raw_indicators: dict
    data_quality: Literal["full", "partial"]

class FundamentalSignal(BaseModel):
    reasoning: str
    quality_score: float                        # 0.0 to 1.0
    valuation_verdict: Literal["overvalued", "fair", "undervalued"]
    key_flags: list[str]
    metrics: dict                               # all computed ratios
    data_quality: Literal["full", "partial"]

class QuantSignal(BaseModel):
    composite_score: float                      # 0.0 to 1.0
    factor_breakdown: dict                      # {"momentum": float, "quality": float, "value": float, "low_vol": float}
    data_quality: Literal["full", "partial"]

class SectorSignal(BaseModel):
    reasoning: str
    sector: str
    sector_trend: Literal["outperforming", "inline", "underperforming"]
    competitive_positioning: str
    macro_flags: list[str]
    peer_comparison: dict
    data_quality: Literal["full", "partial"]

class SentimentSignal(BaseModel):
    reasoning: str
    raw_score: float                            # -1.0 to 1.0
    adjusted_score: float                       # after bot discount
    bot_risk: Literal["low", "medium", "high"]
    source_breakdown: dict                      # {"reddit": float, "stocktwits": float, "news": float}
    narrative_themes: list[str]
    mention_volume: int
    data_quality: Literal["full", "partial"]

class FinalReport(BaseModel):
    ticker: str
    verdict: Literal["strong_buy", "buy", "hold", "sell", "strong_sell"]
    conviction: Literal["low", "medium", "high"]
    narrative: str
    bull_case: list[str]
    bear_case: list[str]
    conflicts: list[str]                        # where agents materially disagreed
    signal_scores: dict
    generated_at: str
```

**`core/model_router.py`**

```python
from anthropic import Anthropic

class ModelRouter:
    def __init__(self, config: AppConfig):
        self._config = config
        self._client = Anthropic()              # reads ANTHROPIC_API_KEY from env

    def get_model(self, agent_name: str) -> str:
        return self._config.anthropic.models[agent_name]

    @property
    def client(self) -> Anthropic:
        return self._client
```

**Validation checkpoint:** Instantiate `ModelRouter` and assert it returns the correct model string for each of the 6 agent names. No API calls needed.

---

## Phase 3 — Agents

Build in order. Each must pass standalone validation before the next begins.

**LLM call pattern for all agents (use this exactly):**
```python
from tenacity import retry, wait_exponential, wait_random, stop_after_attempt

@retry(
    wait=wait_exponential(multiplier=2, min=2, max=30) + wait_random(-0.5, 0.5),
    stop=stop_after_attempt(4),
    reraise=True
)
async def _call_llm(client: Anthropic, model: str, prompt: str, response_model: type) -> BaseModel:
    return client.messages.parse(
        model=model,
        max_tokens=1024,
        response_model=response_model,
        messages=[{"role": "user", "content": prompt}]
    )
```

**Prompt structure for all agents (follow this order):**
1. Role: "You are a [domain] analyst. Analyze only the data provided — do not use recalled knowledge for specific numbers."
2. Data block: the pre-computed dict of metrics/indicators
3. Task: explicit step-by-step instructions
4. Quality rule: "If any required input field was missing or null, set `data_quality` to `partial` and lower your confidence score proportionally."

### Agent 1 — Fundamental (`agents/fundamental.py`)
- Call `get_financials()` and `get_company_info()` from the data layer
- **Pre-compute in Python** (never in the LLM): P/E, P/S, P/B, EV/EBITDA, gross margin, operating margin, net margin, revenue growth QoQ/YoY, debt-to-equity, FCF yield, ROE
- Null-check every input before computing each ratio — skip and log any ratio whose inputs are `None`
- Pass the completed ratio dict to Haiku via `client.messages.parse(response_model=FundamentalSignal, ...)`
- Return a valid `FundamentalSignal`
- Standalone: `python -m backend.agents.fundamental AAPL`

### Agent 2 — Technical (`agents/technical.py`)
- Call `get_ohlcv()` from the data layer
- Use `pandas-ta` to compute: EMA 20/50/200 (`df.ta.ema(length=20)`), RSI 14 (`df.ta.rsi()`), MACD (`df.ta.macd()`), Bollinger Bands (`df.ta.bbands()`), ATR 14 (`df.ta.atr()`), OBV (`df.ta.obv()`)
- Derive support/resistance from lowest low and highest high of last 20 candles
- Pass computed indicator dict to Haiku via `client.messages.parse(response_model=TechnicalSignal, ...)`
- Return a valid `TechnicalSignal`
- Standalone: `python -m backend.agents.technical AAPL`

### Agent 3 — Quant (`agents/quant.py`)
- No LLM call — pure computation
- Use `get_ohlcv()` for price data; fetch SPY OHLCV via the same function for benchmarking
- Momentum: compute 3M/6M/12M returns for ticker and SPY; score = percentile rank of ticker vs SPY
- Quality: normalize ROE and inverse debt-to-equity to 0–1, average them
- Value: earnings yield = 1/PE, normalize to 0–1 using bounds from `config.yaml` (`quant.earnings_yield_min/max`)
- Low-vol: 90-day annualized realized volatility (std of daily log returns × √252), inverted and normalized
- Composite = equal-weighted average of the 4 factor scores
- Return a valid `QuantSignal`
- Standalone: `python -m backend.agents.quant AAPL`

### Agent 4 — Sector (`agents/sector.py`)
- Get sector from `get_company_info()`; map to ETF using `config.yaml` `sector_etf_map`
- Fetch ETF and SPY OHLCV; compute 1M/3M/6M relative performance in Python before LLM
- Fetch 3–5 hardcoded peers; compute their P/E, revenue growth, margins via yfinance
- Pass pre-computed relative performance dict and peer comparison dict to Sonnet
- Return a valid `SectorSignal`
- Standalone: `python -m backend.agents.sector AAPL`

### Agent 5 — Sentiment (`agents/sentiment.py`)
- Ingest Reddit, StockTwits, and news from data layer
- Apply bot detection heuristics to Reddit **before** any LLM call:
  - Account age < 30 days at post time → `bot_flag: true`
  - Same author, 3+ posts about same ticker in 24h → `bot_flag: true`
  - `upvote_ratio < 0.55` AND `score > 100` → `suspicious_flag: true`
  - Today's mention count > (mean + 2×std) of cached historical daily counts → `spike_flag: true`
- Pass flagged and clean content as separate fields in the prompt
- Ask Sonnet to: score each source independently (−1 to +1), assess bot risk, identify top 3 narrative themes, produce an adjusted score that discounts flagged content proportional to bot_risk
- Return a valid `SentimentSignal`
- Standalone: `python -m backend.agents.sentiment AAPL`

### Agent 6 — Synthesis (`agents/synthesis.py`)
- Accepts all 5 signals; loads weights from `config.yaml`
- Map each signal's primary score to 0–1 scale before LLM call:
  - Technical: `confidence` (direction flips sign — bearish = 1 − confidence)
  - Fundamental: `quality_score`
  - Quant: `composite_score`
  - Sector: `outperforming → 1.0`, `inline → 0.5`, `underperforming → 0.0`
  - Sentiment: `adjusted_score` remapped from −1:1 to 0:1
- Compute weighted composite in Python, then pass all 5 full signal objects + composite to Sonnet
- Map composite to verdict using thresholds from `config.yaml` (`synthesis.*_threshold`)
- Prompt must explicitly ask for a `conflicts` list — agents that materially disagreed (e.g. strong technicals but weak fundamentals)
- Return a valid `FinalReport`
- Standalone: `python -m backend.agents.synthesis AAPL` (loads cached agent outputs if available)

---

## Phase 4 — LangGraph Graph (`core/graph.py`)

**This is the phase most likely to have silent bugs. Follow the state schema exactly.**

```python
from typing import Annotated, TypedDict
import operator
from langgraph.graph import StateGraph
from langgraph.config import get_stream_writer

class ResearchState(TypedDict):
    ticker: str
    agent_signals: Annotated[list, operator.add]   # REQUIRED reducer — parallel agents append here
    final_report: FinalReport | None
```

Without `Annotated[list, operator.add]`, parallel agents silently overwrite each other — last writer wins, no error thrown.

Each parallel agent node must:
1. Call `get_stream_writer()` and emit a start event
2. Run its logic
3. Emit a complete event with the signal
4. Return `{"agent_signals": [{"agent": "name", "signal": signal}]}` — a list, not a scalar

```python
async def fundamental_agent(state: ResearchState) -> dict:
    writer = get_stream_writer()
    writer({"type": "agent_start", "agent": "fundamental", "ticker": state["ticker"]})
    signal = await run_fundamental(state["ticker"])
    writer({"type": "agent_complete", "agent": "fundamental", "signal": signal.model_dump()})
    return {"agent_signals": [{"agent": "fundamental", "signal": signal}]}
```

Synthesis node reads from `state["agent_signals"]` after all 5 accumulate:
```python
async def synthesis_node(state: ResearchState) -> dict:
    signals = {s["agent"]: s["signal"] for s in state["agent_signals"]}
    report = await run_synthesis(signals)
    return {"final_report": report}
```

Graph topology: fan out agents 1–5 in parallel from the start node; synthesis node depends on all 5. Use `max_concurrency` in run config.

Expose: `async def run_research(ticker: str) -> FinalReport`

**Validation checkpoint:** `run_research("AAPL")` returns a complete `FinalReport` with all 5 signals in `agent_signals`.

---

## Phase 5 — FastAPI Backend (`backend/main.py`)

Endpoints:
```
POST /research          — triggers full pipeline, returns FinalReport JSON
GET  /research/{ticker} — returns cached report if run today, else triggers fresh run
GET  /research/{ticker}/stream — SSE endpoint, emits agent events
GET  /health            — returns {"status": "ok"}
```

**SSE endpoint requirements:**
- Must include `X-Accel-Buffering: no` header — without this, nginx buffers the entire stream
- Required headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`
- Wrap the SSE generator in try/except — `StreamingResponse` does not propagate generator exceptions to the client automatically. Catch exceptions and yield `data: {"error": "..."}\n\n`
- Use `graph.stream(..., stream_mode=["custom", "updates"])` to capture `get_stream_writer()` events

```python
@app.get("/research/{ticker}/stream")
async def stream_research(ticker: str):
    async def event_generator():
        try:
            async for event in graph.astream(
                {"ticker": ticker},
                stream_mode=["custom", "updates"]
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            log.error("stream_error", ticker=ticker, error=str(e))
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    )
```

- Ticker validation: regex `^[A-Z]{1,5}$`, return 422 for anything else
- CORS for `http://localhost:5173`
- Use lifespan context manager for startup (initialize model router, ensure cache dir exists)
- All route handlers must be `async def`

**Validation checkpoint:** `uvicorn backend.main:app --reload`, confirm all endpoints respond via curl.

---

## Phase 6 — React Frontend (`frontend/`)

Bootstrap: `npm create vite@latest frontend -- --template react`, then install Tailwind and Recharts.

**SSE consumption — do NOT use native `EventSource`:**

The browser's native `EventSource` API does not support POST requests with a JSON body. Use `fetch()` with a manual reader:

```js
const res = await fetch(`/research/${ticker}/stream`, {
  method: 'GET',
  headers: { Accept: 'text/event-stream' }
})
const reader = res.body.getReader()
const decoder = new TextDecoder()

while (true) {
  const { done, value } = await reader.read()
  if (done) break
  const lines = decoder.decode(value).split('\n')
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const event = JSON.parse(line.slice(6))
      // update agent state
    }
  }
}
```

**Components:**

`TickerInput` — centered input, large ticker field, submit button with pulsing animation on submit

`AgentProgressTracker` — 5 rows (one per agent), each with name, status badge (waiting / running / complete), spinner or checkmark — updates in real time from SSE events

`ScoreCard` — verdict badge (green = buy, red = sell, grey = hold), conviction chip, horizontal bar breakdown of each agent's weighted score contribution

`AgentDetail` — expandable accordion per agent, structured output as readable key-value pairs (not raw JSON), `data_quality: "partial"` surfaced as a warning badge

`SentimentBreakdown` — Reddit / StockTwits / News scores as gauges, bot-risk badge (green/yellow/red), narrative themes as tags

`SynthesisNarrative` — narrative paragraphs, bull/bear cases side-by-side, conflicts list with warning icon

**Styling:**
- Dark mode only — background `#0f1117`, card `#1a1d27`, accent `#00d4aa`
- Tailwind CSS for all layout — no CSS modules, no styled-components
- Recharts for score visualizations
- Bloomberg terminal meets modern SaaS aesthetic

**Validation checkpoint:** Submit `AAPL`, confirm live progress updates, confirm full report renders.

---

## Error Handling Throughout

- Use `tenacity` `@retry` on every Anthropic API call — not manual try/sleep loops
- If a data source fails (Finviz 403, Reddit empty), log with `structlog` at WARNING, set `data_quality: "partial"` on the signal, and continue — never crash the pipeline over one source
- If an agent fails entirely, synthesis must note the missing signal and proceed with available data — never propagate an agent exception to the API layer
- FastAPI endpoints return structured errors: `{"error": str, "ticker": str, "phase": str}`
- Never catch bare `Exception` without logging the full traceback via `structlog`

---

## Testing — Run After Every Phase

A test suite exists in `backend/tests/` organized by phase. Tests act as the automated validation checkpoint for each phase. Do not proceed to the next phase until the relevant tests pass.

### Test commands (use the Makefile)

```bash
make test-unit      # Pure computation tests — no I/O, always runnable, always fast
make test-phase1    # Data layer schema validation (requires fixtures or live cache)
make test-phase2    # Config, schema, and model router tests (no I/O)
make test-phase3    # Agent output validation (requires fixtures)
make test-phase4    # Full pipeline + graph structure (requires API key)
make test           # All tests except phase4
```

### What each phase's tests validate

**Phase 1 (`make test-phase1`)** — validates that every data module returns the correct structure: required keys present, no empty lists, values are correct types. Skips cleanly if no fixture data exists yet.

**Phase 2 (`make test-phase2`)** — validates Pydantic schemas reject invalid inputs, config loads correctly with correct model assignments, weights sum to 1.0, synthesis thresholds are ordered. All pure unit tests, runnable immediately.

**Phase 3 unit tests (`make test-unit`)** — the most important tests in the suite. Validates:
- `compute_ratios()` in the Fundamental agent handles None fields without crashing or producing NaN
- `compute_indicators()` in the Technical agent returns all required keys with valid ranges
- All four Quant factor functions produce scores in [0, 1] and handle None inputs gracefully
- `apply_bot_heuristics()` in the Sentiment agent correctly applies all three heuristics with exact boundary conditions

These test the functions most likely to silently fail. Write them first and make them pass before calling the LLM.

**Phase 3 schema tests (`make test-phase3`)** — runs each agent against fixture data and validates the output matches its Pydantic schema. Requires `make fixtures` to be run after Phase 1 is validated.

**Phase 4 (`make test-phase4`)** — validates `ResearchState` uses `Annotated[list, operator.add]` reducer (the test fails if the reducer is missing, catching the silent data-loss bug before it manifests), and validates `run_research("AAPL")` returns a complete `FinalReport` with all 5 signals present.

### Fixture workflow

After Phase 1 is validated, run:
```bash
make fixtures
```
This populates `backend/tests/fixtures/` with real AAPL data so all subsequent tests run without network access. After Phase 3 is validated, run `make fixtures` again to also capture agent signal fixtures for the synthesis test.

Commit fixture files to the repo — they make the test suite self-contained.

### TDD workflow per phase

1. Write the code for the phase
2. Run `make test-unit` — these should pass immediately (no I/O)
3. Run the phase-specific tests (`make test-phaseN`)
4. Fix any failures before moving to the next phase
5. Run `make validate-phaseN` to run the standalone CLI validation

**The test for the LangGraph reducer (`test_graph.py::TestResearchStateSchema::test_agent_signals_has_reducer`) is particularly important.** It will fail if you forget `Annotated[list, operator.add]` on `agent_signals`, catching the silent data-loss bug before you waste time debugging why some agents' results disappear.

---

## Final File Structure

```
stock-research-app/
├── backend/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── fundamental.py
│   │   ├── technical.py
│   │   ├── quant.py
│   │   ├── sector.py
│   │   ├── sentiment.py
│   │   └── synthesis.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py          # pydantic-settings AppConfig + get_config()
│   │   ├── data_models.py
│   │   ├── model_router.py
│   │   ├── graph.py
│   │   └── cache.py
│   ├── data/
│   │   ├── __init__.py
│   │   ├── price.py
│   │   ├── news.py
│   │   ├── reddit.py
│   │   └── stocktwits.py
│   └── main.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── TickerInput.jsx
│   │   │   ├── AgentProgressTracker.jsx
│   │   │   ├── ScoreCard.jsx
│   │   │   ├── AgentDetail.jsx
│   │   │   ├── SentimentBreakdown.jsx
│   │   │   └── SynthesisNarrative.jsx
│   │   └── App.jsx
│   └── package.json
├── backend/
│   └── tests/
│       ├── conftest.py                        # shared fixtures, fixture loader
│       ├── generate_fixtures.py               # run once after Phase 1
│       ├── fixtures/                          # committed AAPL test data
│       ├── phase1/
│       │   ├── test_price.py
│       │   ├── test_news.py
│       │   ├── test_reddit.py
│       │   └── test_stocktwits.py
│       ├── phase2/
│       │   ├── test_config.py
│       │   ├── test_model_router.py
│       │   └── test_data_models.py
│       ├── phase3/
│       │   ├── test_fundamental_math.py       # unit — no I/O
│       │   ├── test_technical_indicators.py   # unit — no I/O
│       │   ├── test_quant_math.py             # unit — no I/O
│       │   ├── test_sentiment_heuristics.py   # unit — no I/O
│       │   └── test_agent_outputs.py          # integration — needs fixtures
│       └── phase4/
│           └── test_graph.py                  # integration — needs API key
├── cache/                     # gitignored
├── .env                       # gitignored — copy from .env.example
├── .env.example
├── .pre-commit-config.yaml
├── pytest.ini                 # already created — do not recreate
├── Makefile                   # already created — do not recreate
├── config.yaml                # already created — do not recreate
├── requirements.txt           # already created — do not recreate
└── README.md
```

---

Start with Phase 1. Read the README. Build `backend/data/price.py` first. Do not write any agent, graph, or API code until the data layer is complete and returning real cached data for AAPL.
