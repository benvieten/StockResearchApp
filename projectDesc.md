
You are building a stock research application from scratch. Read the `README.md` in the project root before writing a single line of code — it contains the build order, cost rules, and caching requirements that govern every decision you make in this project.

## Core Rules — Non-Negotiable

- **Follow the build order in the README exactly.** Complete and validate each phase before starting the next. Do not scaffold the entire project upfront.
- **Use `AAPL` as the test ticker throughout.** Every module you build must return real, non-empty data for AAPL before you move on.
- **Cache everything.** Every external data fetch must check `/cache/{ticker}_{source}_{date}.json` first. Only fetch live data if no valid cache entry exists for today.
- **Never hardcode a model name.** Every LLM call must go through `model_router.get_model(agent_name)`. Read the model assignments from `config.yaml`.
- **Each agent must be independently runnable** via `python -m backend.agents.{name} AAPL` and print a valid JSON output to stdout before you wire it into the graph.
- **Do not run the full 6-agent pipeline** to test a single agent. Test agents in isolation to minimize API costs.

---

## Stack

- **Orchestration:** LangGraph
- **Backend:** FastAPI with Server-Sent Events for progress streaming
- **Frontend:** React with a dark-mode financial dashboard aesthetic
- **LLM Provider:** Anthropic only — use `langchain-anthropic` and the Anthropic SDK
- **Model routing:** Haiku for Technical, Fundamental, Quant agents — Sonnet for Sector, Sentiment, Synthesis agents — configured in `config.yaml`

---

## Data Sources — Free Only, No API Keys

| Source | What to fetch | Notes |
|---|---|---|
| `yfinance` | OHLCV (1Y daily), income statement, balance sheet, cash flow, company info, built-in news | No key needed |
| Google News RSS | Headlines: `https://news.google.com/rss/search?q={ticker}+stock` | Parse with `feedparser` |
| Finviz | News table scrape: `https://finviz.com/quote.ashx?t={ticker}` | Use `BeautifulSoup` + browser `User-Agent` header |
| Reddit JSON API | `https://www.reddit.com/r/{sub}/search.json?q={ticker}&sort=new&limit=50` for subs: `wallstreetbets`, `stocks`, `investing`, `SecurityAnalysis` | Browser `User-Agent` header, `time.sleep(1)` between requests |
| StockTwits | `https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json` | No key needed |

---

## Phase 1 — Data Layer

Build `backend/data/` first. Each module must be runnable standalone.

**`price.py`**
- Fetch via `yfinance`: 1Y daily OHLCV, quarterly income statement, balance sheet, cash flow statement, company info dict, and recent news headlines
- Cache all outputs separately: `AAPL_ohlcv_2024-01-01.json`, `AAPL_financials_2024-01-01.json`, etc.
- Expose clean functions: `get_ohlcv(ticker)`, `get_financials(ticker)`, `get_company_info(ticker)`, `get_news(ticker)`

**`news.py`**
- Fetch Google News RSS using `feedparser`
- Scrape Finviz news table with `BeautifulSoup` — target the `news-table` element, extract headline, source, and timestamp
- Return a unified list of `{"headline": str, "source": str, "timestamp": str, "url": str}` dicts
- Cache combined output as `AAPL_news_2024-01-01.json`

**`reddit.py`**
- Query all 4 subreddits sequentially with a 1-second delay between each
- For each post extract: title, selftext, score, upvote_ratio, num_comments, author name, author account created timestamp, post created timestamp, subreddit
- Cache as `AAPL_reddit_2024-01-01.json`

**`stocktwits.py`**
- Fetch the public stream for the ticker
- Extract: message body, sentiment tag (Bullish/Bearish/null), created timestamp, user follower count, user following count
- Cache as `AAPL_stocktwits_2024-01-01.json`

**Validation checkpoint:** Run each module standalone and confirm real data is returned and cached before proceeding.

---

## Phase 2 — Schemas & Model Router

**`core/data_models.py`**

Define these Pydantic v2 models:

```python
class TechnicalSignal(BaseModel):
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float  # 0.0 to 1.0
    key_levels: dict   # {"support": float, "resistance": float}
    indicator_summary: dict
    raw_indicators: dict

class FundamentalSignal(BaseModel):
    quality_score: float  # 0.0 to 1.0
    valuation_verdict: Literal["overvalued", "fair", "undervalued"]
    key_flags: list[str]  # e.g. ["negative FCF", "high debt"]
    metrics: dict         # all computed ratios

class QuantSignal(BaseModel):
    composite_score: float  # 0.0 to 1.0
    factor_breakdown: dict  # {"momentum": float, "quality": float, "value": float, "low_vol": float}

class SectorSignal(BaseModel):
    sector: str
    sector_trend: Literal["outperforming", "inline", "underperforming"]
    competitive_positioning: str
    macro_flags: list[str]
    peer_comparison: dict

class SentimentSignal(BaseModel):
    raw_score: float      # -1.0 to 1.0
    adjusted_score: float # after bot discount
    bot_risk: Literal["low", "medium", "high"]
    source_breakdown: dict  # {"reddit": float, "stocktwits": float, "news": float}
    narrative_themes: list[str]
    mention_volume: int

class FinalReport(BaseModel):
    ticker: str
    verdict: Literal["strong_buy", "buy", "hold", "sell", "strong_sell"]
    conviction: Literal["low", "medium", "high"]
    narrative: str
    bull_case: list[str]
    bear_case: list[str]
    conflicts: list[str]
    signal_scores: dict
    generated_at: str
```

**`core/model_router.py`**

```python
class ModelRouter:
    def __init__(self, config_path="config.yaml"):
        # load config, initialize one ChatAnthropic client per model tier
        pass

    def get_model(self, agent_name: str) -> ChatAnthropic:
        # return the correct client for this agent based on config
        pass
```

**`config.yaml`** — create this in the project root:

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

**Validation checkpoint:** Instantiate `ModelRouter` and assert it returns the correct model string for each of the 6 agent names.

---

## Phase 3 — Agents

Build in this order. Each agent must pass standalone validation before the next begins.

### Agent 1 — Fundamental (`agents/fundamental.py`)
- Call `get_financials(ticker)` and `get_company_info(ticker)` from the data layer
- Compute these metrics from raw financial statement data: P/E, P/S, P/B, EV/EBITDA, gross margin, operating margin, net margin, revenue growth QoQ and YoY, debt-to-equity, FCF yield, ROE
- Use the Haiku model to interpret the computed metrics and produce qualitative flags
- Return a valid `FundamentalSignal`
- Standalone: `python -m backend.agents.fundamental AAPL` prints `FundamentalSignal` JSON

### Agent 2 — Technical (`agents/technical.py`)
- Call `get_ohlcv(ticker)` from the data layer
- Use the `ta` library to compute: EMA 20/50/200, RSI(14), MACD, Bollinger Bands, ATR(14), OBV
- Identify support and resistance using recent swing highs/lows
- Use the Haiku model to interpret indicators and produce a directional signal
- Return a valid `TechnicalSignal`
- Standalone: `python -m backend.agents.technical AAPL`

### Agent 3 — Quant (`agents/quant.py`)
- Use `get_ohlcv()` and `get_financials()` data
- Compute: 3M/6M/12M price return, compare against SPY returns for the same periods to get momentum percentile
- Compute quality score from ROE and debt-to-equity ranks
- Compute value score from earnings yield (1/PE) normalized
- Compute low-vol score from 90-day realized volatility (lower vol = higher score)
- Combine into composite using equal weights across 4 factors
- No LLM call needed for this agent — pure computation
- Return a valid `QuantSignal`
- Standalone: `python -m backend.agents.quant AAPL`

### Agent 4 — Sector (`agents/sector.py`)
- Get sector and industry from `get_company_info()`
- Map sector to its benchmark ETF (e.g. Technology → XLK, Healthcare → XLV, Energy → XLE, etc.)
- Fetch ETF and SPY OHLCV via `get_ohlcv()`, compute 1M/3M/6M relative performance
- Identify 3–5 peer tickers from the same industry using company info or a hardcoded peer map
- Fetch peer P/E, revenue growth, and margins via yfinance
- Use the Sonnet model to reason about macro tailwinds/headwinds and competitive positioning
- Return a valid `SectorSignal`
- Standalone: `python -m backend.agents.sector AAPL`

### Agent 5 — Sentiment (`agents/sentiment.py`)
- Ingest Reddit posts, StockTwits messages, and news headlines from the data layer
- Apply these bot detection heuristics to Reddit data before scoring:
  - Flag posts from accounts created less than 30 days before the post
  - Flag authors with 3+ posts about the same ticker within 24 hours
  - Flag posts with upvote_ratio < 0.55 and score > 100 (coordinated downvote suppression or upvote manipulation)
  - Compute a mention volume spike: if today's mention count is more than 2 standard deviations above the mean of cached historical counts, flag as spike
- Pass flagged vs clean content separately to the Sonnet model
- Ask the model to: score sentiment for each source (−1 to +1), assess bot risk level, identify the top 3 narrative themes, and produce an adjusted score that discounts flagged content
- Return a valid `SentimentSignal`
- Standalone: `python -m backend.agents.sentiment AAPL`

### Agent 6 — Synthesis (`agents/synthesis.py`)
- Accepts all 5 signals as input
- Load signal weights from `config.yaml`
- Compute a weighted composite score from each signal's primary numeric output
- Pass all 5 structured signals + the composite score to the Sonnet model
- Prompt the model to produce: a final verdict, conviction level, 4–6 paragraph narrative, 3–5 bull case points, 3–5 bear case points, and a list of conflicts where agents disagreed materially
- Return a valid `FinalReport`
- Standalone: `python -m backend.agents.synthesis AAPL` (loads cached agent outputs if available)

---

## Phase 4 — LangGraph Graph (`core/graph.py`)

```python
from typing import TypedDict
from langgraph.graph import StateGraph

class ResearchState(TypedDict):
    ticker: str
    technical: TechnicalSignal | None
    fundamental: FundamentalSignal | None
    quant: QuantSignal | None
    sector: SectorSignal | None
    sentiment: SentimentSignal | None
    final_report: FinalReport | None
```

- Define one node per agent
- Agents 1–5 must execute as **parallel branches** — use LangGraph's fan-out pattern so all 5 run concurrently
- Synthesis node depends on all 5 and runs only after they complete
- Implement exponential backoff with jitter on any node that calls the Anthropic API — base delay 2s, max 4 attempts, jitter ±0.5s
- Expose: `async def run_research(ticker: str) -> FinalReport`

**Validation checkpoint:** Call `run_research("AAPL")` in a test script and confirm a complete `FinalReport` is returned with all fields populated.

---

## Phase 5 — FastAPI Backend (`backend/main.py`)

```
POST /research
  Body: { "ticker": "AAPL" }
  Triggers full LangGraph pipeline
  Returns: FinalReport JSON

GET /research/{ticker}
  Returns cached FinalReport if run today, else triggers fresh run
  
GET /research/{ticker}/stream
  SSE endpoint — emits progress events as each agent completes:
  data: {"agent": "fundamental", "status": "complete", "signal": {...}}
  
GET /health
  Returns: { "status": "ok" }
```

- Enable CORS for `http://localhost:5173` (Vite default)
- For the SSE endpoint, emit an event when each agent node completes in the LangGraph graph — use LangGraph's streaming callbacks to capture node completion events
- Validate ticker symbols — reject anything that isn't 1–5 uppercase letters

**Validation checkpoint:** Start with `uvicorn backend.main:app --reload` and confirm all endpoints respond correctly via curl before building the frontend.

---

## Phase 6 — React Frontend (`frontend/`)

Bootstrap with Vite: `npm create vite@latest frontend -- --template react`

**Components to build:**

`TickerInput` — centered input with large ticker field and submit button, subtle pulsing animation on submit

`AgentProgressTracker` — appears immediately on submit, shows 5 rows (one per agent), each with: agent name, status badge (waiting / running / complete), and a checkmark or spinner — status updates in real time via SSE

`ScoreCard` — top of the report, shows: verdict badge (color-coded: green for buy, red for sell, grey for hold), conviction chip, and a horizontal bar breakdown showing each agent's weighted contribution to the final score

`AgentDetail` — expandable accordion section per agent showing their full structured output formatted as readable key-value pairs, not raw JSON

`SentimentBreakdown` — dedicated section showing Reddit / StockTwits / News scores as individual gauges, bot-risk level as a colored badge (green/yellow/red), and the top narrative themes as tags

`SynthesisNarrative` — full-width section at the bottom with the narrative paragraphs, bull case and bear case as side-by-side columns, and conflicts listed with a warning icon

**Styling:**
- Dark mode only — background `#0f1117`, card background `#1a1d27`, accent `#00d4aa`
- Use Tailwind CSS for layout and spacing
- Use Recharts for any score visualizations
- Financial dashboard feel — think Bloomberg terminal meets modern SaaS

**Validation checkpoint:** Submit `AAPL`, confirm the progress tracker updates live as agents complete, and confirm the full report renders correctly.

---

## Error Handling Throughout

- Wrap every Anthropic API call in try/except with exponential backoff
- If a data source fails (Finviz blocks, Reddit returns empty), log the failure, return a degraded but valid signal with a `data_quality: "partial"` flag, and continue — never crash the pipeline due to a single source failure
- If an agent fails entirely, the synthesis agent should note the missing signal and proceed with available data rather than throwing

---

## Final File Structure

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
│   │   └── data_models.py
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
├── cache/
├── config.yaml
├── requirements.txt
└── README.md
```

---

Start with Phase 1. Read the README. Build `backend/data/price.py` first. Do not write any agent, graph, or API code until the data layer is complete and returning real cached data for AAPL.

---

