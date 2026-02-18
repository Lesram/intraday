# Living Strategy System (Adaptive, Self-Correcting) — Blueprint & Action Plan

Date: 2026-02-06

This document captures a detailed plan to evolve the platform from fixed-rule strategies into a **living strategy system** that:

- Continuously ingests the most current market data
- Produces forecasts with uncertainty
- Detects regimes (trend/chop/high-vol/etc.)
- Dynamically adjusts **strategy weights**, **strategy enablement (rotation/gating)**, and **parameters** within strict guardrails
- Self-corrects when predictions are wrong (bias correction + confidence shrinkage + drift-triggered retraining)
- Preserves deterministic execution + safety controls (risk gate, throttles, outbox)

The goal is **adaptation without instability**.

---

## 1) Definitions

### 1.1 “Living” means
The system updates its behavior using new information:

- **Weights**: which strategies matter more *right now*
- **Rotation/gating**: which strategies are allowed to trade under a regime
- **Parameters**: thresholds/periods/position sizing multipliers
- **Confidence**: how much forecast/strategies should influence exposure

### 1.2 What must stay deterministic
To avoid runaway behavior, the following must be stable and auditable:

- Execution semantics (exposure netting, flip throttling, max risk per bar)
- Risk gating (RiskManager before order)
- Order submission pipeline (outbox + execution mode controls)
- Idempotency and audit logs

---

## 2) Current Platform State (As of 2026-02-06)

### 2.1 Strategy types
- Rule-based strategies in the framework produce BUY/SELL/HOLD + confidence.
- A deterministic execution layer (`StrategyEngine`) expects exposure targets and performs:
  - multi-source netting
  - throttling (flip prevention)
  - max-risk-per-bar limiting
  - risk gating

### 2.2 Multi-strategy live runner
The platform can run multiple strategies together and route them through the execution engine.
This is a good foundation for a living system because the execution layer is already centralized.

### 2.3 What is *not* automatic yet
- No persistent regime detection / regime-conditioned weights
- No daily/weekly parameter retuning pipeline with acceptance gates
- No drift detection / retraining trigger loop
- No strategy performance attribution loop feeding weight updates

---

## 3) Target End-State Architecture

Think of the system as three layers:

1) **Perception**: data → features → regime → forecast (with uncertainty)
2) **Policy**: strategy weights + gating + parameter selection + exposure recommendations
3) **Execution**: net exposures → throttle → risk gate → submit via outbox

Only layer (2) is “living.” Layer (3) should remain conservative and deterministic.

---

## 4) Guardrails (Non-Negotiable)

To prevent overfitting and instability:

### 4.1 Hard risk constraints
- Max exposure per symbol (and optionally per sector)
- Max turnover per symbol per day
- Max new risk per bar (already exists in engine)
- Max flips per day (additional cap)
- Portfolio drawdown kill switch + cooldown

### 4.2 Change budget (rate limits on adaptation)
- Weights can only change by Δw per update
- Parameters can only change by Δp per day/week
- Gating changes require a minimum hold time (avoid regime whipsaw)

### 4.3 Two-stage rollout
- **Shadow mode** (compute and log)
- **Execute mode** only after passing automatic acceptance checks

---

## 5) Data & Feature Foundation

### 5.1 Market data requirements
- Consistent OHLCV bars per timeframe (start with 1D or 5m depending on strategy horizon)
- Trading calendar awareness
- Corporate actions policy (raw vs adjusted)

### 5.2 Feature parity (online vs offline)
The exact same feature pipeline must run in:

- backtests / research
- paper/live signal generation

Feature groups:
- Trend: SMA/EMA slopes, breakouts, MACD
- Mean reversion: Bollinger position/width, z-score
- Volatility: ATR/ATR ratio, realized vol
- Liquidity/risk: volume anomalies, gaps
- Regime: trend strength + volatility regime

### 5.3 Store everything for audit
Persist:
- bars
- features (versioned)
- regimes
- forecasts
- decisions and weights/params used

---

## 6) Forecasting (Best Forecast, With Uncertainty)

### 6.1 Forecast targets
Choose explicit targets. Typical options:
- next-bar return distribution (μ, σ)
- probability of up/down move
- probability of continuation vs reversal

### 6.2 Pragmatic model approach
Start with a robust ensemble:
- linear baseline (fast, stable)
- tree/boosted model (nonlinear)
- optional: one model per regime

### 6.3 Calibration
Forecasts must report uncertainty and be calibrated.
If calibration degrades:
- shrink confidence
- reduce forecast influence on weights/exposures

---

## 7) Living Policy Engine (Weights, Rotation, Parameters)

### 7.1 Strategy interface upgrades
Each strategy should expose:
- params schema (bounds + defaults)
- required features
- output: target_exposure in [-1, 1] + confidence + diagnostics

### 7.2 Two mixing modes

**A) Soft mixing (recommended first)**
- all strategies run
- weights vary with regime + performance + forecast confidence
- final exposure is netted via engine

**B) Rotation/gating (second step)**
- in a regime, only certain strategies are allowed

### 7.3 Parameter adaptation

Two-speed:
- **Fast (intraday)**: small rule-based adjustments from regime (vol targeting, exposure scaling)
- **Slow (daily/weekly)**: walk-forward parameter retuning with acceptance gates

### 7.4 Self-correction logic

Forecast correction:
- track residuals e_t = r_t - r̂_t
- correct bias
- shrink confidence on drift
- drift trigger → retrain

Policy correction:
- attribute PnL and forecast error to strategies and regimes
- reduce weights / gate strategies that underperform in regime
- cooldown and re-enable only after criteria

---

## 8) Execution Integration (Keep Safety Deterministic)

The policy engine must only output controlled intents:
- per-strategy exposures + confidence OR already netted exposure

Execution layer responsibilities:
- netting, throttling, max-risk-per-bar limiting
- risk gate
- order creation and outbox submission

Operational modes:
- shadow / dry_run / execute

---

## 9) Evaluation & Retraining Schedule

### 9.1 Nightly job (daily cadence)
- compute strategy + regime attribution
- update regime-conditioned weights (bounded, rate-limited)
- drift checks (features + residuals)
- propose parameter changes (candidate) if acceptance passes

### 9.2 Weekly job
- broader parameter search
- stress tests across volatile periods
- correlation/risk constraints review

### 9.3 Acceptance gates (automatic)
Promote candidate → current only if:
- improves risk-adjusted performance on validation window
- does not exceed turnover budget
- does not worsen drawdown beyond threshold
- passes sanity checks (no NaNs, stable outputs)

---

## 10) Monitoring, Audit, and Governance

Every run must log:
- regime label + confidence
- forecast outputs + uncertainty + calibration score
- strategy weights and parameter versions
- final exposures and engine throttles
- risk gate decisions
- order outcomes

Dashboards:
- drift (feature drift, residual drift)
- regime churn
- turnover and slippage
- per-strategy contribution

Kill switches:
- freeze adaptation (weights/params)
- disable per strategy
- global stop trading

---

## 11) Implementation Roadmap (Phased)

### Phase 1 (Immediate: foundation, 1–2 days)
- Add regime detector (simple: trend strength + volatility regime)
- Add dynamic weights in soft mixing mode (bounded changes)
- Add decision logs and attribution scaffolding
- Run in shadow mode to validate behavior

### Phase 2 (Short term: nightly adaptation, ~1 week)
- Nightly weight update loop (regime-conditioned)
- Drift detection and forecast confidence shrinkage
- Acceptance gates for weight changes

### Phase 3 (Parameter adaptation, ~2 weeks)
- Walk-forward parameter tuning pipeline
- Candidate promotion workflow (registry + gates)
- Rollout controls: gradual exposure ramp, rollback

### Phase 4 (Advanced: online learning, optional)
- Only if needed. Prefer batch retraining + strict gates.

---

## 12) Action Plan (Concrete Next Steps)

### 12.1 Decide the adaptation scope
- Per-symbol vs per-sector vs universe-wide

### 12.2 Choose cadence
- Intraday weights only, or nightly + intraday

### 12.3 Choose mixing style
- Soft mixing first (recommended) vs hard rotation

### 12.4 Build the minimum viable living loop
1) Persist features + forecasts + decisions
2) Implement regime detector
3) Implement bounded weight updates
4) Add attribution and drift metrics
5) Shadow for 1–2 sessions
6) Paper execute with strict limits

---

## 13) Notes / Constraints

- “Living” does not guarantee profitability; it increases the chance that the system remains aligned with current conditions.
- The biggest failure modes are:
  - overfitting to short windows
  - unstable parameter/weight oscillations
  - regime churn causing excessive turnover
  - hidden data leakage between offline and online computations

Guardrails and auditability are what make a living system production-grade.
