# Stock Research Multi-Agent App

A multi-agent stock research application that produces comprehensive investment opinions using LangGraph orchestration, FastAPI backend, and a React frontend. All data is sourced from free APIs only. LLM calls are powered by Anthropic and routed intelligently by task complexity.

---

## ⚠️ Read Before Building — Cost & Rate Limit Awareness

This app makes LLM API calls to Anthropic on every research run. During development, costs and rate limits can accumulate quickly if not managed carefully. **Strictly follow these rules throughout the entire build:**

### Caching — Mandatory During Development
- **All external data fetches must be cached locally** in the `/cache` directory as JSON, keyed by `{ticker}_{source}_{date}.json`
- On each run, check the cache first. Only fetch fresh data if no cache entry exists for today's date
- This applies to: yfinance data, Reddit posts, StockTwits messages, Google News RSS, and Finviz scrapes
- **Never re-fetch data you already have.** A single ticker run should only hit external sources once per day

### LLM Calls — Use the Model Router, Always
- **Never hardcode a model name inside an agent.** Every agent must call `model_router.get_model(agent_name)` to retrieve its assigned model
- Cheap models (`claude-haiku-3-5`) are assigned to Technical, Fundamental, and Quant agents — do not upgrade these without a deliberate config change
- Capable models (`claude-sonnet-4-5`) are reserved for Sentiment, Sector, and Synthesis agents only
- During development and testing, prefer running individual agents in isolation rather than the full pipeline to minimize token usage
- Do not run the full 6-agent pipeline repeatedly to test a single agent's output

### Rate Limits
- Anthropic enforces per-minute and per-day token limits depending on your tier. If you hit a rate limit, implement **exponential backoff with jitter** — do not retry immediately in a tight loop
- Reddit's public JSON API has a soft rate limit of approximately 1 request per second. Add a `time.sleep(1)` between subreddit calls
- Finviz will block rapid repeated scraping. Cache aggressively and do not scrape the same ticker more than once per day
- StockTwits limits unauthenticated requests — cache the response immediately on first fetch

---

## Build Order — Iterative, Layer by Layer

**Do not skip ahead. Each layer must be working and validated with real data before the next begins.**

### Phase 1 — Data Layer
Build and validate all data modules in `backend/data/`. Each module must be runnable standalone and return real, non-empty data for the test ticker `AAPL`.

- [ ] `price.py` — yfinance OHLCV, financials, balance sheet, cash flow, company info
- [ ] `news.py` — Google News RSS + Finviz scraper
- [ ] `reddit.py` — Reddit public JSON API across 4 subreddits
- [ ] `stocktwits.py` — StockTwits public stream

**Validation:** run `python -m backend.data.price AAPL` and confirm real data is returned and written to `/cache`.

---

### Phase 2 — Pydantic Schemas & Model Router
Before writing any agent logic, define all data contracts and the model router.

- [ ] `core/data_models.py` — define `TechnicalSignal`, `FundamentalSignal`, `QuantSignal`, `SectorSignal`, `SentimentSignal`, `FinalReport` as Pydantic models
- [ ] `core/model_router.py` — implement `ModelRouter` class that reads `config.yaml` and returns the correct Anthropic model and client per agent
- [ ] `config.yaml` — set model assignments, signal weights, and caching settings

**Validation:** instantiate the router and confirm it returns the correct model string for each agent name.

---

### Phase 3 — Agents (One at a Time)
Build agents one at a time. Each must be independently testable via CLI before moving to the next.

- [ ] `agents/fundamental.py` — start here, most stable data source
- [ ] `agents/technical.py`
- [ ] `agents/quant.py`
- [ ] `agents/sector.py`
- [ ] `agents/sentiment.py` — build bot detection heuristics last within this agent
- [ ] `agents/synthesis.py` — build only after all 5 above are producing valid output

**Validation:** `python -m backend.agents.fundamental AAPL` must print a valid `FundamentalSignal` JSON to stdout.

---

### Phase 4 — LangGraph Orchestration
Wire all agents into the graph only after every agent passes standalone validation.

- [ ] `core/graph.py` — define `ResearchState`, parallel execution of agents 1–5, synthesis node as dependent step
- [ ] Expose `run_research(ticker: str) -> FinalReport` async function

**Validation:** call `run_research("AAPL")` directly in a test script and confirm a complete `FinalReport` is returned.

---

### Phase 5 — FastAPI Backend
- [ ] `main.py` — implement `POST /research`, `GET /research/{ticker}`, `GET /health`, CORS config, and SSE progress streaming

**Validation:** `uvicorn backend.main:app --reload`, then `curl -X POST localhost:8000/research -d '{"ticker":"AAPL"}'` returns a full report.

---

### Phase 6 — React Frontend
- [ ] Ticker input and submit button
- [ ] Live agent progress tracker via SSE (5 agents, each showing waiting / running / complete)
- [ ] Final report dashboard: scorecard, per-agent expandable sections, sentiment breakdown with bot-risk indicator, synthesis narrative
- [ ] Dark-mode financial dashboard aesthetic

**Validation:** full end-to-end run from the UI returns and renders a complete report for `AAPL`.

---

## Project Structure

```
stock-research-app/
├── backend/
│   ├── agents/
│   │   ├── technical.py
│   │   ├── sentiment.py
│   │   ├── sector.py
│   │   ├── fundamental.py
│   │   ├── quant.py
│   │   └── synthesis.py
│   ├── core/
│   │   ├── graph.py
│   │   ├── model_router.py
│   │   ├── data_models.py
│   │   └── cache.py
│   ├── data/
│   │   ├── price.py
│   │   ├── news.py
│   │   ├── reddit.py
│   │   └── stocktwits.py
│   └── main.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   └── App.jsx
│   └── package.json
├── cache/
├── config.yaml
├── requirements.txt
└── README.md
```

---

## Configuration (`config.yaml`)

```yaml
anthropic:
  models:
    technical: "claude-haiku-3-5-20241022"
    fundamental: "claude-haiku-3-5-20241022"
    quant: "claude-haiku-3-5-20241022"
    sector: "claude-sonnet-4-5-20251001"
    sentiment: "claude-sonnet-4-5-20251001"
    synthesis: "claude-sonnet-4-5-20251001"

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

rate_limits:
  reddit_delay_seconds: 1.0
  anthropic_retry_max_attempts: 4
  anthropic_retry_base_delay_seconds: 2
```

---

## Data Sources (Free, No API Keys Required)

| Source | Data | Module |
|---|---|---|
| `yfinance` | Price, OHLCV, financials, company info | `data/price.py` |
| Google News RSS | News headlines | `data/news.py` |
| Finviz | News headlines (scraped) | `data/news.py` |
| Reddit JSON API | Social sentiment (WSB, stocks, investing) | `data/reddit.py` |
| StockTwits Public API | Social sentiment + tagged signals | `data/stocktwits.py` |

---

## Agent Overview

| Agent | Model Tier | Primary Signal | Output Schema |
|---|---|---|---|
| Technical | Haiku | Chart indicators, trend, levels | `TechnicalSignal` |
| Fundamental | Haiku | Valuation, margins, quality | `FundamentalSignal` |
| Quant | Haiku | Multi-factor composite score | `QuantSignal` |
| Sector | Sonnet | Macro context, competition | `SectorSignal` |
| Sentiment | Sonnet | Social + news sentiment, bot risk | `SentimentSignal` |
| Synthesis | Sonnet | Final verdict + narrative | `FinalReport` |

---

## Requirements

```
# backend/requirements.txt
fastapi
uvicorn
langgraph
langchain-anthropic
yfinance
pandas
numpy
ta
beautifulsoup4
httpx
pydantic
pyyaml
sse-starlette
```

---

## Development Test Ticker

Use **`AAPL`** as the default ticker throughout all development and testing phases. Write code that fetches and processes real data — no mocks or placeholder logic.