# Stock Research Multi-Agent App

A multi-agent stock research application that produces comprehensive investment opinions using LangGraph orchestration, FastAPI backend, and a React frontend. All data is sourced from free APIs only. LLM calls are powered by Anthropic and routed intelligently by task complexity.

---

## ⚠️ Read Before Building — Cost & Rate Limit Awareness

This app makes LLM API calls to Anthropic on every research run. During development, costs and rate limits can accumulate quickly if not managed carefully. **Strictly follow these rules throughout the entire build:**

### Caching — Mandatory During Development
- **All external data fetches must be cached locally** in the `/cache` directory as JSON, keyed by `{ticker}_{source}_{date}_v{schema_version}.json`
- Include a `schema_version` suffix in every cache key (current: `v1`). Increment it whenever the shape of what you fetch changes — otherwise stale cache entries silently feed the wrong data to agents
- On each run, check the cache first. Only fetch fresh data if no cache entry exists for today's date
- Always write the fetch timestamp into every cached result. Pass it to the LLM in the prompt so it can caveat time-sensitive analysis
- This applies to: yfinance data, Reddit posts, StockTwits messages, Google News RSS, and Finviz scrapes
- **Never re-fetch data you already have.** A single ticker run should only hit external sources once per day

### LLM Calls — Use the Model Router, Always
- **Never hardcode a model name inside an agent.** Every agent must call `model_router.get_model(agent_name)` to retrieve its assigned model
- Cheap models (`claude-haiku-4-5`) are assigned to Technical, Fundamental, and Quant agents — do not upgrade these without a deliberate config change
- Capable models (`claude-sonnet-4-6`) are reserved for Sentiment, Sector, and Synthesis agents only
- During development and testing, prefer running individual agents in isolation rather than the full pipeline to minimize token usage
- Do not run the full 6-agent pipeline repeatedly to test a single agent's output

### Rate Limits
- Anthropic enforces per-minute and per-day token limits depending on your tier. Use `tenacity` with exponential backoff and jitter — do not retry in a tight loop
- Reddit's public JSON API has a soft rate limit of approximately 1 request per second. Add `time.sleep(1)` between subreddit calls
- Finviz will block rapid repeated scraping. Cache aggressively and do not scrape the same ticker more than once per day
- StockTwits limits unauthenticated requests — cache the response immediately on first fetch

---

## ⚠️ Critical Bugs to Prevent — Read Before Phase 4

These are the most common silent failures found across real multi-agent LangGraph projects. Fix them before they bite.

### 1. LangGraph Parallel State — Silent Data Loss

**The #1 undetected bug in multi-agent LangGraph systems.** Without a reducer annotation, when parallel agents write to the same state key, the last agent to finish wins and all others' results are silently discarded. No error is thrown.

Every field that parallel agents write to **must** use an append reducer:

```python
from typing import Annotated
import operator

class ResearchState(TypedDict):
    ticker: str
    agent_signals: Annotated[list, operator.add]  # REQUIRED — without this, agents overwrite each other
```

Each parallel agent must return a list, not a single value:

```python
async def fundamental_agent(state: ResearchState) -> dict:
    signal = await run(state["ticker"])
    return {"agent_signals": [{"agent": "fundamental", "signal": signal}]}  # note: list
```

The synthesis node reads the accumulated list after all parallel agents complete.

### 2. SSE — Native `EventSource` Won't Work for POST

The browser's native `EventSource` API does not support POST requests with a JSON body. Since your SSE endpoint needs a ticker in the request body, `EventSource` silently fails. Use `fetch()` with a manual `getReader()` loop on the frontend, or install `@microsoft/fetch-event-source`.

```js
// WRONG — EventSource cannot POST
const es = new EventSource('/research/stream')

// RIGHT — fetch with manual reader
const res = await fetch('/research/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ ticker })
})
const reader = res.body.getReader()
```

### 3. SSE — Nginx Buffers the Entire Stream

If you run behind nginx (local dev proxy, any deployment), nginx buffers the entire SSE stream and delivers it all at once at the end — defeating live progress updates entirely. Add this header to every SSE response:

```python
headers = {
    "X-Accel-Buffering": "no",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
}
```

### 4. Pre-Compute All Ratios Before Any LLM Call

Never ask an LLM to compute a financial ratio. When an LLM is told "revenue was $X, compute gross margin," it fabricates a plausible-looking cost figure. This is well-documented in the financial LLM hallucination literature (ArXiv 2311.15548).

The structural defense: pre-compute every ratio in Python before calling the LLM. Pass the completed dict. The LLM can only hallucinate its interpretation of `{"gross_margin": 0.43}` — not the number itself.

This rule applies to: all ratio computations in the Fundamental agent, all indicator values in the Technical agent, and all factor scores in the Quant agent.

### 5. yfinance Null Fields — Always Check

yfinance returns `None` for missing data without warning. The rate of missing fields increased significantly in 2024–2025. A single unchecked `.get()` that returns `None` fed into a ratio formula will crash the agent or produce `NaN`.

Rule: null-check every field before computing any ratio. If a required field is `None`, mark the signal `data_quality: "partial"` and continue with available data.

---

## Build Order — Iterative, Layer by Layer

**Do not skip ahead. Each layer must be working and validated with real data before the next begins.**

### Phase 1 — Data Layer
Build and validate all data modules in `backend/data/`. Each module must be runnable standalone and return real, non-empty data for the test ticker `AAPL`.

- [ ] `price.py` — yfinance OHLCV, financials, balance sheet, cash flow, company info
- [ ] `news.py` — Google News RSS + Finviz scraper (Finviz is fallback only — if blocked, log and continue)
- [ ] `reddit.py` — Reddit public JSON API across 4 subreddits
- [ ] `stocktwits.py` — StockTwits public stream

**Validation:** run `python -m backend.data.price AAPL` and confirm real data is returned and written to `/cache`.

---

### Phase 2 — Pydantic Schemas & Model Router
Before writing any agent logic, define all data contracts and the model router.

- [ ] `core/data_models.py` — define `TechnicalSignal`, `FundamentalSignal`, `QuantSignal`, `SectorSignal`, `SentimentSignal`, `FinalReport` as Pydantic v2 models. Include a `reasoning` field (string) in each signal model before the final score field — this forces the LLM into a chain-of-thought pattern and reduces hallucination on interpretation tasks
- [ ] `core/model_router.py` — implement `ModelRouter` class that reads `config.yaml` and returns the correct Anthropic client per agent
- [ ] `core/config.py` — implement `get_config()` using `pydantic-settings` for typed config access
- [ ] `config.yaml` — set model assignments, signal weights, and caching settings

**Validation:** instantiate the router and confirm it returns the correct model string for each agent name.

---

### Phase 3 — Agents (One at a Time)
Build agents one at a time. Each must be independently testable via CLI before moving to the next.

All agent LLM calls must use the native Anthropic structured output API:
```python
signal = client.messages.parse(
    model=model_router.get_model("fundamental"),
    response_model=FundamentalSignal,
    messages=[...]
)
```
This enforces schema at the token generation level — the model cannot produce schema-violating output. No JSON parsing, no validation failures.

- [ ] `agents/fundamental.py` — start here, most stable data source
- [ ] `agents/technical.py`
- [ ] `agents/quant.py` — no LLM call, pure computation
- [ ] `agents/sector.py`
- [ ] `agents/sentiment.py` — build bot detection heuristics last within this agent
- [ ] `agents/synthesis.py` — build only after all 5 above are producing valid output

**Validation:** `python -m backend.agents.fundamental AAPL` must print a valid `FundamentalSignal` JSON to stdout.

---

### Phase 4 — LangGraph Orchestration
Wire all agents into the graph only after every agent passes standalone validation.

- [ ] `core/graph.py` — define `ResearchState` with `Annotated[list, operator.add]` reducer on all parallel-written fields (see Critical Bugs section above)
- [ ] Fan out agents 1–5 in parallel; synthesis node depends on all 5
- [ ] Each parallel agent node returns `{"agent_signals": [signal]}` — a list, not a scalar
- [ ] Synthesis node reads from `state["agent_signals"]` after all 5 accumulate
- [ ] Set `max_concurrency` in run config to protect against rate limit spikes
- [ ] Emit LangGraph stream events from each node using `get_stream_writer()` for SSE consumption
- [ ] Expose `async def run_research(ticker: str) -> FinalReport`

```python
from langgraph.config import get_stream_writer

async def fundamental_agent(state: ResearchState) -> dict:
    writer = get_stream_writer()
    writer({"type": "agent_start", "agent": "fundamental"})
    signal = await run(state["ticker"])
    writer({"type": "agent_complete", "agent": "fundamental", "signal": signal.model_dump()})
    return {"agent_signals": [{"agent": "fundamental", "signal": signal}]}
```

**Validation:** call `run_research("AAPL")` in a test script and confirm a complete `FinalReport` with all 5 signals populated.

---

### Phase 5 — FastAPI Backend
- [ ] `main.py` — implement `POST /research`, `GET /research/{ticker}`, `GET /research/{ticker}/stream`, `GET /health`
- [ ] SSE endpoint must include `X-Accel-Buffering: no` header (see Critical Bugs section)
- [ ] Wrap the SSE generator in a try/except and yield structured error events on failure — `StreamingResponse` does not propagate generator exceptions to the client automatically
- [ ] CORS for `http://localhost:5173`
- [ ] Ticker validation: regex `^[A-Z]{1,5}$`, return 422 for anything else

**Validation:** `uvicorn backend.main:app --reload`, then `curl -X POST localhost:8000/research -d '{"ticker":"AAPL"}'` returns a full report.

---

### Phase 6 — React Frontend
- [ ] Ticker input and submit button
- [ ] Live agent progress tracker via SSE — use `fetch()` + `getReader()` loop, NOT native `EventSource` (see Critical Bugs section)
- [ ] Final report dashboard: scorecard, per-agent expandable sections, sentiment breakdown with bot-risk indicator, synthesis narrative
- [ ] Dark-mode financial dashboard aesthetic

**Validation:** full end-to-end run from the UI returns and renders a complete report for `AAPL`.

---

## Project Structure

```
stock-research-app/
├── backend/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── technical.py
│   │   ├── sentiment.py
│   │   ├── sector.py
│   │   ├── fundamental.py
│   │   ├── quant.py
│   │   └── synthesis.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── model_router.py
│   │   ├── data_models.py
│   │   ├── config.py
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
├── cache/               # gitignored — never commit
├── .env                 # gitignored — copy from .env.example
├── .env.example
├── .pre-commit-config.yaml
├── config.yaml
├── requirements.txt
└── README.md
```

---

## Configuration (`config.yaml`)

```yaml
anthropic:
  models:
    technical: "claude-haiku-4-5-20251001"
    fundamental: "claude-haiku-4-5-20251001"
    quant: "claude-haiku-4-5-20251001"
    sector: "claude-sonnet-4-6"
    sentiment: "claude-sonnet-4-6"
    synthesis: "claude-sonnet-4-6"

signal_weights:
  fundamental: 0.30
  technical: 0.20
  sentiment: 0.20
  sector: 0.20
  quant: 0.10

cache:
  enabled: true
  directory: "./cache"
  ttl_hours: 24
  schema_version: 1  # increment when data shape changes

rate_limits:
  reddit_delay_seconds: 1.0
  anthropic_retry_max_attempts: 4
  anthropic_retry_base_delay_seconds: 2
  anthropic_retry_jitter_seconds: 0.5

synthesis:
  strong_buy_threshold: 0.75
  buy_threshold: 0.60
  hold_threshold: 0.40
  sell_threshold: 0.25
```

---

## Data Sources

| Source | Data | Reliability | Module |
|---|---|---|---|
| `yfinance` | OHLCV, financials, company info | Fragile — pin version, null-check every field | `data/price.py` |
| Google News RSS | News headlines | Most reliable free news source | `data/news.py` |
| Finviz | News headlines (scraped) | Blocks at scale — fallback only | `data/news.py` |
| Reddit JSON API | Social sentiment | Works at low volume with browser User-Agent | `data/reddit.py` |
| StockTwits Public API | Social sentiment + tagged signals | Stable, ~60 req/min | `data/stocktwits.py` |
| SEC EDGAR XBRL API | Authoritative financials (fallback) | Free, official, no API key | `data/price.py` |

### yfinance Warnings
yfinance is an unofficial wrapper around Yahoo Finance that has broken repeatedly in 2024–2025. Treat every field as potentially `None`. Key rules:
- Always use `.get()` with a default, never direct dict key access on `.info`
- `.financials` columns are `pd.Timestamp` objects — convert: `df.columns = [str(c.date()) for c in df.columns]`
- Pin the yfinance version in `requirements.txt` and monitor its GitHub issues page
- On fetch failure, check if a recent cache entry exists and use it with a freshness warning rather than crashing

### SEC EDGAR XBRL API (Fallback for Fundamentals)
If yfinance returns incomplete financials, fall back to the official EDGAR XBRL API:
```
https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
```
Free, no authentication, 10 req/sec rate limit. More reliable than yfinance for balance sheet and income statement data.

---

## Agent Overview

| Agent | Model | Primary Signal | LLM Call |
|---|---|---|---|
| Fundamental | Haiku | Valuation, margins, quality | Yes — interprets pre-computed ratios |
| Technical | Haiku | Chart indicators, trend, levels | Yes — interprets pre-computed indicators |
| Quant | Haiku | Multi-factor composite score | No — pure computation |
| Sector | Sonnet | Macro context, competition | Yes — contextual reasoning |
| Sentiment | Sonnet | Social + news sentiment, bot risk | Yes — nuanced content analysis |
| Synthesis | Sonnet | Final verdict + narrative | Yes — cross-signal synthesis |

### Why Haiku for Computation Agents
Agents that receive a pre-computed dict of numbers and produce a structured score do not benefit from a larger model. Haiku is sufficient and the cost difference at scale is significant. Only agents requiring deep contextual judgment (Sector, Sentiment, Synthesis) need Sonnet.

### Prompt Engineering Rules (All Agents)
1. State that the agent analyzes only provided data — not recalled from training
2. Pass all pre-computed metrics as a structured dict before any narrative text
3. Use explicit step ordering: "First assess X. Then evaluate Y in context of X. Finally determine Z."
4. Include a `reasoning` field in the output schema before the final score — this enforces chain-of-thought
5. Instruct the model to set `data_quality: "partial"` and lower confidence when any input field was `None`
6. Do not use negative instructions like "don't hallucinate" — structural guardrails (pre-computed data + schema enforcement) are what actually prevent hallucination

---

## LangGraph Architecture

### State Schema
```python
from typing import Annotated, TypedDict
import operator

class ResearchState(TypedDict):
    ticker: str
    raw_data: dict                                    # pre-loaded by fetch_data node
    agent_signals: Annotated[list, operator.add]      # parallel agents append here
    final_report: FinalReport | None
```

The `Annotated[list, operator.add]` reducer is mandatory. Without it, parallel agents silently overwrite each other's results.

### Graph Topology
```
fetch_data
    ├── fundamental_agent ─┐
    ├── technical_agent   ─┤
    ├── quant_agent       ─┼── synthesis_agent
    ├── sector_agent      ─┤
    └── sentiment_agent   ─┘
```

### Data Pre-loading Strategy
Each agent fetches its own data from the cache rather than relying on a single `fetch_data` node that pre-loads everything. This means:
- If Reddit is slow, it does not delay the Fundamental agent
- Cache hits are instant regardless of which agent requests the data
- Agent failures are isolated — a slow data source only affects the agent that needs it

### Streaming Events
Use `get_stream_writer()` from `langgraph.config` inside each node to emit progress events. The FastAPI SSE endpoint subscribes to these using `graph.stream(..., stream_mode=["custom", "updates"])`.

---

## Requirements

```
# Web framework & server
fastapi
uvicorn[standard]
sse-starlette

# LangGraph & LLM
langgraph
langchain-anthropic
anthropic

# Data sources
yfinance
feedparser
beautifulsoup4
httpx

# Data processing
pandas
numpy
pandas-ta          # replaces ta — more indicators, pandas extension API

# Pydantic & config
pydantic>=2.0
pydantic-settings  # typed config from config.yaml
pyyaml
python-dotenv

# Retry & resilience
tenacity           # replaces manual backoff loops — use @retry decorator

# Logging
structlog          # structured JSON logs — critical for diagnosing agent failures

# Cache
diskcache          # thread-safe disk cache — handles concurrent agent writes

# Dev / testing
black
ruff
pytest
pytest-asyncio
pre-commit
```

---

## Development Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install pre-commit hooks (auto-runs black + ruff on every commit)
pre-commit install

# 4. Set up environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# 5. Verify setup — run data layer for AAPL
python -m backend.data.price AAPL
```

---

## Testing Strategy

- **Unit tests** for all ratio computations (Fundamental agent math) — pure functions, no API calls
- **Integration tests** for data modules using cached fixtures — mock the network, use real cache files
- **Contract tests** for each agent's output against its Pydantic schema — run via `pytest -v`

Run tests with: `pytest backend/tests/ -v`

Do not write tests that depend on live network requests. All test data must come from fixtures in `backend/tests/fixtures/`.

---

## Research Findings and Architectural Decisions

### What the Best Production Systems Do

From analysis of open-source projects (TradingAgents, LangAlpha, MarketSenseAI) and academic research (MarketSenseAI achieved 125.9% vs 73.5% index return on S&P 100 over 2023-2024):

**Pre-computation is the primary hallucination defense.** Systems that pass raw financial statements to LLMs hallucinate specific numbers. Systems that pre-compute every ratio and pass a clean dict do not. This is structural, not prompt-based.

**Explicit conflict detection in synthesis.** Projects that used a simple weighted average of signal scores produced opaque verdicts — users got a number with no context. The `conflicts` field in `FinalReport` (where agents materially disagreed) is the most actionable output for an investor.

**Sequential vs parallel architecture.** MarketSenseAI uses sequential agents where each stage informs the next. Your architecture uses parallel fan-out, which is correct because your agents are genuinely independent — they all derive from raw data, not from each other's intermediate output.

**Adversarial synthesis (future enhancement).** TradingAgents runs a Bullish Researcher vs Bearish Researcher debate before synthesis rather than a direct weighted average. The debate format surfaces conflicts more reliably. Not needed for v1, but consider adding `synthesis_mode: "adversarial"` to `config.yaml` as a future option.

**RAG over financial documents (future enhancement).** MarketSenseAI's biggest differentiator is chunking and retrieving SEC filings and earnings call transcripts via RAG (Pinecone + LlamaIndex) rather than feeding full documents as context. Their findings: qualitative text moderated ~5% of signals from buy to hold by catching hidden risks that quantitative data missed. This is the most impactful v2 upgrade.

### What Does Not Work

- Asking LLMs to recall historical prices or compute ratios from memory — high hallucination rate, documented
- Negative prompt instructions ("don't hallucinate") — do not reduce hallucination, sometimes reduce output quality
- Running the full pipeline to test a single agent — high token cost, hard to debug
- Catching bare `Exception` without logging — masks which data source or agent failed

---

## Development Test Ticker

Use **`AAPL`** as the default ticker throughout all development and testing phases. Write code that fetches and processes real data — no mocks or placeholder logic.
