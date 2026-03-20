# Hidden Markov Model — Market Regime Detection (Phase 2)

This document captures the design decisions and implementation plan for replacing the
Phase 1 threshold-based regime classifier with a proper Hidden Markov Model. Read the
Phase 1 implementation first (`backend/core/regime.py`) to understand what the HMM
will slot-replace.

---

## Why an HMM Over Thresholds

The threshold classifier (Phase 1) uses hard rules — VIX level, EMA200 slope, ADX — to
assign a binary or ternary regime label. This works well in clearly trending or clearly
ranging markets, but it lags at **transition points** because every input indicator is
itself a lagging measure of price.

An HMM solves this differently. It learns the statistical fingerprint of each hidden
market state from historical data and then infers, at any given moment, the probability
distribution over those states. The output is not "bull" — it is "71% bull, 22%
transitional, 7% bear." That probability vector is far more useful to downstream agents
than a hard label because:

- The synthesis agent can **interpolate** between weight presets rather than hard-switching
- The technical agent can **hedge its interpretation** of ambiguous indicator readings
- Regime transitions are detected **earlier** — the model's confidence in the current
  state drops before the price action makes the shift obvious

---

## Architecture

### Hidden States

Use **3 states**: bull, bear, transitional. Two states is too coarse — it forces
sideways/consolidating markets to be misclassified as one extreme. Four or more states
increases the risk of overfitting to historical idiosyncrasies.

Initial label assignment after training (see Ambiguity section below):
- State with highest mean return + lowest variance → **bull**
- State with lowest (most negative) mean return → **bear**
- Remaining state → **transitional**

### Observation Features (per trading day)

| Feature | Construction | Rationale |
|---|---|---|
| Log return | `log(close_t / close_t-1)` on SPY | Core market signal |
| 20-day realized volatility | Rolling std of log returns × sqrt(252) | Volatility distinguishes regimes |
| VIX level (normalized) | `VIX / 50` capped at 1.0 | Fear gauge, orthogonal to price |
| 200-day EMA distance | `(price - EMA200) / EMA200` | Trend position |

All four features are available free via yfinance (SPY + ^VIX). Do not use ticker-level
features for the regime model — the regime describes the **market environment**, not the
individual stock.

### Model Type

Use a **Gaussian HMM** with full covariance matrices (not diagonal). The `hmmlearn`
library implements this directly:

```python
from hmmlearn import hmm
model = hmm.GaussianHMM(n_components=3, covariance_type="full", n_iter=200)
```

Full covariance captures correlations between features (e.g., high VIX co-occurs with
negative returns and high realized vol). Diagonal covariance would miss this.

---

## Training

### Data Source

Train exclusively on SPY + ^VIX daily data fetched via yfinance. Use **5 years** of
history (approximately 1,260 trading days). This window is long enough to include
multiple regime cycles (2020 COVID crash and recovery, 2022 bear market, 2023–2024
bull) without being so long that pre-2018 market microstructure pollutes the model.

```python
import yfinance as yf
spy = yf.download("SPY", period="5y", auto_adjust=True)
vix = yf.download("^VIX", period="5y", auto_adjust=True)
```

### Training Cadence

Retrain **once per day** at application startup (or on first request if startup is
lazy). Cache the fitted model to disk using `joblib.dump` / `joblib.load` so subsequent
requests within the same day skip retraining. Use the existing `diskcache` or a simple
pickle file at `./cache/hmm_model_{YYYY-MM-DD}.pkl`.

Retraining takes approximately 200–500ms on a laptop with 1,260 rows × 4 features —
acceptable at startup, unacceptable per-request.

### State Label Ambiguity

HMMs do not know which learned state corresponds to "bull." After training, resolve
labels by inspecting the means matrix:

```python
# model.means_ is shape (n_components, n_features)
# Feature 0 is log return — sort states by their mean log return
state_order = model.means_[:, 0].argsort()  # ascending: bear, transitional, bull
label_map = {state_order[0]: "bear", state_order[1]: "transitional", state_order[2]: "bull"}
```

Re-run this mapping every time the model is retrained, since state indices can flip
between runs.

---

## Inference

### Getting the Current Regime

To classify today's regime, run the **forward algorithm** on the last 60 trading days
of observations (not just today — the HMM needs recent sequence context to be
confident). Use `model.predict_proba()` from hmmlearn and take the last row:

```python
probs = model.predict_proba(recent_obs_60_days)
today_probs = probs[-1]  # shape (3,) — one probability per state
# Re-map state indices to labels using label_map from training
regime_probs = {label_map[i]: float(today_probs[i]) for i in range(3)}
# e.g. {"bull": 0.71, "transitional": 0.22, "bear": 0.07}
```

Use 60 days of context, not just the last 1–5 days. The forward algorithm accumulates
evidence across the sequence — more context gives a more stable estimate. 60 days
balances recency with stability.

### Output Contract

The HMM module should expose the same interface as the Phase 1 threshold classifier
so that agents require no changes:

```python
# Phase 1 output (threshold classifier)
RegimeSignal(
    regime="bull",               # hard label
    confidence=0.85,             # how certain the thresholds are
    vix=18.4,
    adx=32.1,
    ema200_slope=0.0012,
)

# Phase 2 output (HMM) — extends RegimeSignal
RegimeSignal(
    regime="bull",               # dominant label (argmax of probs)
    confidence=0.71,             # probability of dominant state
    vix=18.4,
    adx=32.1,
    ema200_slope=0.0012,
    # New fields added by HMM:
    regime_probs={"bull": 0.71, "transitional": 0.22, "bear": 0.07},
    model_source="hmm",          # vs "threshold" in Phase 1
)
```

The `regime` and `confidence` fields are populated identically to Phase 1 — downstream
agents that only read those two fields work without modification. The new `regime_probs`
dict is consumed by the synthesis agent for soft weight interpolation.

---

## Effect on Downstream Agents

### Technical Agent

Phase 1 passes a single regime string to the LLM prompt. Phase 2 can pass the full
probability vector, enabling richer interpretation:

```
Market Regime: bull (71% confidence | transitional: 22% | bear: 7%)
```

The LLM can now say "RSI=68 is a momentum confirmation in a predominantly bull regime,
but the 22% transitional probability warrants watching for exhaustion."

### Synthesis Agent — Soft Weight Interpolation

Phase 1 selects one of three weight presets based on the hard regime label. Phase 2
can interpolate continuously:

```python
# Three weight presets (from config.yaml)
W_bull = {"fundamental": 0.25, "technical": 0.30, "quant": 0.15, "sector": 0.20, "sentiment": 0.10}
W_bear = {"fundamental": 0.40, "technical": 0.15, "quant": 0.20, "sector": 0.15, "sentiment": 0.10}
W_transitional = {"fundamental": 0.30, "technical": 0.20, "quant": 0.15, "sector": 0.20, "sentiment": 0.15}

# Soft interpolation using HMM probabilities
p = regime_probs  # {"bull": 0.71, "transitional": 0.22, "bear": 0.07}
blended_weights = {
    k: p["bull"] * W_bull[k] + p["transitional"] * W_transitional[k] + p["bear"] * W_bear[k]
    for k in W_bull
}
```

This eliminates the hard weight jump that occurs at regime boundaries in Phase 1.

---

## New Dependencies

Add to `requirements.txt`:

```
hmmlearn
joblib
scikit-learn  # hmmlearn depends on this; likely already present transitively
```

`hmmlearn` is pure Python / NumPy / scikit-learn. No paid services, no API keys.

---

## Failure Modes to Handle

| Failure | Mitigation |
|---|---|
| yfinance fails to fetch SPY/VIX training data | Fall back to Phase 1 threshold classifier; log warning |
| Saved model file is corrupt or missing | Retrain from scratch; if yfinance also fails, fall back to thresholds |
| HMM fails to converge (rare) | `hmmlearn` will still return a model; check `model.monitor_.converged` and log if False |
| State label flip between runs | Re-run label_map resolution on every load, not just on train |
| Extreme market event not in training window | HMM will assign high transitional probability — which is the correct conservative response |

---

## Files to Create / Modify

| File | Change |
|---|---|
| `backend/core/regime.py` | Replace threshold logic with HMM; preserve `get_regime()` interface |
| `backend/core/data_models.py` | Add `regime_probs: dict[str, float]` and `model_source: str` to `RegimeSignal` |
| `config.yaml` | Add `regime.hmm_training_days`, `regime.n_components`, `regime.context_days` |
| `requirements.txt` | Add `hmmlearn`, `joblib` |
| `cache/` | Store `hmm_model_{YYYY-MM-DD}.pkl` (gitignored already) |

No changes needed to `technical.py`, `synthesis.py`, or any other agent — the
`RegimeSignal` interface is backward-compatible.

---

## When to Implement Phase 2

The r/ai_trading community is explicit on this point:

> *"You need real market data and real results before ML adds any value. Throwing a
> neural net at bad data just gives you confident bad decisions."*
> — FilmFreak1082, r/ai_trading

> *"Start with solid math, prove it works live, THEN layer in ML where the data
> supports it. Not the other way around."*

The Phase 1 threshold classifier should be treated as the production system until all
three of the following criteria are met:

1. **Live verdict tracking** — at least 30 completed verdicts (buy/sell/hold) with
   known subsequent 30-day outcomes recorded. This is the minimum sample to
   distinguish skill from luck at p < 0.10.

2. **Phase 1 accuracy baseline** — the threshold classifier's regime labels are
   manually reviewed against actual SPY performance for the same periods. If bear
   regimes consistently preceded drawdowns and bull regimes preceded rallies, the
   baseline is validated. If not, the Phase 2 HMM will be trained on a broken signal
   and will learn to be wrong more confidently.

3. **Data pipeline stability** — yfinance fetching has been stable for at least 60
   days with no silent failures (null fields, schema changes, rate limit gaps). An
   HMM trained on patchy data learns the gaps, not the signal.

Do not start Phase 2 until all three are met.

---

## Validation Checklist (before merging Phase 2)

- [ ] Model converges (`model.monitor_.converged == True`) on 5y SPY data
- [ ] State labels are stable across 5 consecutive retraining runs (no flip)
- [ ] Regime for March 2020 classified as "bear" in backtested sequence
- [ ] Regime for Jan 2024 classified as "bull" in backtested sequence
- [ ] Soft weight interpolation sums to 1.0 for all regime_probs inputs
- [ ] Fallback to threshold classifier triggers correctly when yfinance is offline
- [ ] Model file cached correctly — second request in same day skips retraining
- [ ] `python -m backend.core.regime` prints valid JSON with all RegimeSignal fields
