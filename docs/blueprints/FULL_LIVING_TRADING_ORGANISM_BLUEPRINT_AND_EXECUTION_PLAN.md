# FULL LIVING Trading Organism — Blueprint + Execution Plan

Date: 2026-02-07

This document defines the **full end-state** “living trading organism”: a production-grade system that continuously senses markets, generates hypotheses, trains models, validates them via walk-forward evaluation, promotes only those that pass strict gates, monitors drift/performance in production, and adapts under bounded, auditable guardrails.

It is written to be actionable for this repository (FastAPI backend + strategy engine + outbox execution pipeline + Alpaca integrations).

---

## 0) Reality Check (So We Build the Right Thing)

### 0.1 “Perfect” is not a valid engineering target
Markets are non-stationary. Any promise of “rerun until perfect” is mathematically and operationally unsafe.

**Production definition of “perfect enough”** is:
- The system **improves** under continuous evaluation,
- It **does not blow up** under adverse conditions,
- It is **auditable, reversible, and bounded**, and
- It reliably **refuses** to trade when uncertainty/risk is high.

So the organism’s objective is:
- **Converge toward better policies** under changing conditions,
- **Avoid overfitting**, and
- **Preserve deterministic execution safety**.

### 0.2 Living ≠ Self-modifying execution
The execution layer must remain deterministic and conservative.

A “living organism” means:
- It learns **policy** (weights/gates/params/models),
- It does **not** mutate execution semantics in uncontrolled ways.

---

## 1) End-State Capabilities (What “FULL LIVING” Means)

### 1.1 The organism operates as a closed loop
A continuous loop that runs on schedules + event triggers:

1) **Sense**: ingest bars/quotes/trades + account fills + metadata
2) **Understand**: compute versioned features + regime probabilities + uncertainty
3) **Decide**: generate signals, combine strategies via a policy, produce target exposures
4) **Act**: deterministic execution engine → risk gate → outbox → broker
5) **Observe**: realized fills, slippage, PnL attribution, risk metrics, violations
6) **Learn**:
   - fast bounded updates (intraday) for weights/vol-targeting
   - batch retraining (nightly/weekly) for models/parameters
7) **Validate**: walk-forward tests, stress tests, leakage checks, stability checks
8) **Promote/Rollback**: safe deployment patterns (shadow → canary → ramp)
9) **Monitor**: drift, calibration, regime churn, performance decay, incident triggers

### 1.2 Autonomy levels (explicit)
Define autonomy as levels so we can ship safely:

- **L0**: fixed rules, no learning
- **L1**: bounded weight adaptation (bandit-like), audit snapshots, manual promotion for model changes
- **L2**: automated nightly candidate generation + automated acceptance gates + automatic promotion to *shadow*
- **L3**: automated promotion to *paper execute* (with kill switches + strict risk caps)
- **L4**: automated promotion to *limited live* with tiny risk budget + rollback
- **L5**: fully autonomous live promotion within hard governance constraints

**Target for “tomorrow readiness” is L1 (already started).**
**Target for “FULL LIVING organism” is L3/L4** (L5 is usually not appropriate without human governance).

---

## 2) Non-Negotiable Guardrails (The “Immune System”)

These constraints exist to prevent runaway adaptation, feedback loops, and catastrophic trading.

### 2.1 Deterministic execution invariants (do not change dynamically)
- Exposure netting semantics
- Flip throttles
- Max-risk-per-bar limiting
- RiskManager gating logic
- Order submission pipeline (outbox + idempotency)

### 2.2 Hard portfolio risk limits (must be enforced every run)
- Max notional exposure per symbol
- Max leverage / gross exposure cap
- Max sector/cluster exposure (optional early; required later)
- Max daily turnover
- Max order rate / max #orders per bar
- Drawdown kill switch + cooldown timer
- “Uncertainty kill” (when calibration/drift is bad, force exposure to 0)

### 2.3 Change budget (rate-limit adaptation)
- Weights can only change by $\Delta w$ per update
- Parameters only change by $\Delta p$ per day/week
- Regime model updates only via batch promotion
- Gating changes require minimum hold time to avoid regime whipsaw

### 2.4 Human governance hooks (even for autonomous modes)
- “Freeze adaptation” switch (weights/params/models)
- “Disable strategy” switch
- “Global stop trading” switch
- Mandatory audit logs for every promotion/rollback

---

## 3) Architecture Overview (Modules and Data Flow)

### 3.1 High-level diagram
```mermaid
graph TD
  A[Market + Account Data] --> B[Ingestion]
  B --> C[Feature Pipeline (Versioned)]
  C --> D[Regime + Forecast Models]
  D --> E[Policy Engine (Weights/Gates/Params)]
  E --> F[Strategy Engine (Deterministic)]
  F --> G[Risk Gate]
  G --> H[Order Service + Outbox]
  H --> I[Broker Execution]
  I --> J[Fill/Slippage/PnL Attribution]
  J --> K[Monitoring + Drift Detection]
  K --> L[Nightly Training + Walk-forward Eval]
  L --> M[Model/Policy Registry]
  M --> E
```

### 3.2 Core stores (what must be persisted)
To be “living” safely, you must store enough to reproduce decisions.

**Minimum**:
- Market bars (raw)
- Strategy signals (pre-net)
- Policy decisions (weights/gates/params used)
- Engine outputs (final exposure targets)
- Orders, fills, cancels
- Snapshot of active model/policy versions

**Next**:
- Features (versioned)
- Regime probabilities
- Forecast outputs + uncertainty + calibration score
- Backtest artifacts + evaluation reports

### 3.3 Registry design (the organism’s memory)
You need 3 registries:

1) **Feature Pipeline Registry**: feature-set version IDs
2) **Model Registry**: trained model artifacts + metadata + evaluation results
3) **Policy Registry**: weight/gate/parameter packages + promotion history

Promotion is always from registry → runtime.

---

## 4) Data & Feature System (Online/Offline Parity)

### 4.1 Data sources
- **Market**: OHLCV bars (multiple timeframes), quotes (optional), corporate actions policy
- **Execution**: orders, fills, slippage, fees
- **Diagnostics**: latency, missing bars, market halts, symbol status

### 4.2 Versioned feature pipeline
A living system fails if offline/backtest features differ from online features.

Rules:
- One feature library used by backtest + live
- Feature config is versioned and stored
- Any feature change triggers a new backtest baseline

Suggested feature groups:
- Trend: slopes, moving-average gaps, breakout distance
- Mean-reversion: z-scores, Bollinger position/width
- Volatility: ATR, realized vol, vol-of-vol
- Liquidity: volume anomalies, spread proxies
- Regime: trend strength + volatility regime + chop score

### 4.3 Data QA gates (prevents garbage learning)
Before training or policy updates:
- Missing bars threshold
- Outlier detection for price/volume
- Calendar alignment (session boundaries)
- Corporate action handling consistency

---

## 5) Backtesting & Walk-Forward Evaluation (The “Time Machine”)

### 5.1 Requirements
A FULL living organism must evaluate changes without leakage:
- Strict chronological splits
- Purged/embargoed CV where needed
- Same feature pipeline as live
- Realistic costs: spreads/slippage/fees

### 5.2 Evaluation modes
- **Replay backtest**: event-driven simulation on bars
- **Paper replay**: run strategy against recorded data but through real execution stack in dry_run
- **Shadow live**: compute decisions live, do not trade, compare counterfactuals

### 5.3 Walk-forward protocol (default)
For each day $t$:
- Train on window $[t-N, t-k]$
- Validate on window $[t-k, t]$
- Roll forward and aggregate metrics

Outputs:
- Distribution of returns, drawdowns, turnover
- Stability of parameters/weights
- Sensitivity to costs

### 5.4 Stress tests (mandatory)
- High-vol periods
- Gap/down-limit days
- Low-liquidity regimes
- “Regime flip” sequences
- Symbol delist/halts (robust handling)

---

## 6) Learning System (Two-Speed Brain)

### 6.1 Fast learning (intraday): bounded policy adaptation
Purpose: adapt allocation without overfitting.

Mechanism:
- Treat each strategy (or strategy×regime) as an “arm”
- Update **scores** from realized outcomes
- Convert scores → weights with clamping + max-delta

Constraints:
- Must be reversible (snapshots)
- Must never bypass risk constraints

This matches what we already started implementing as L1.

### 6.2 Slow learning (nightly/weekly): batch training and parameter search
Purpose: improve models/params with proper validation.

Components:
- Candidate generation: new model fits, new parameter sets
- Walk-forward evaluation
- Acceptance gates
- Registry write
- Promotion pipeline

### 6.3 What “go backwards and rerun” should mean
Not an infinite loop chasing perfection.

It should mean:
- When drift/performance decay is detected, the system automatically:
  1) expands training window selection,
  2) re-evaluates multiple prior regimes,
  3) selects the best *robust* candidate,
  4) promotes only if it passes gates.

---

## 7) Policy Engine (The Organism’s “Cortex”)

### 7.1 Outputs (contract)
Policy produces one of:
- (preferred) per-strategy exposures + weights + diagnostics
- or a net exposure target per symbol

And always includes:
- confidence
- active regime label/probabilities
- parameter package ID
- model/policy version IDs

### 7.2 Decision decomposition (for audit)
Every decision must be attributable:
- What features drove regime detection
- Which model forecast contributed and how
- Which strategies contributed and with what weight
- Why risk reduced/increased (vol targeting, uncertainty shrinkage)

### 7.3 Regime-conditioned policies
Instead of one global weight vector:
- maintain weights per regime bucket
- smooth weights across similar regimes
- enforce “regime churn penalty” (avoid constant switching)

### 7.4 Parameter adaptation model
- Fast: rules (vol targeting, confidence shrink)
- Slow: walk-forward tuning

---

## 8) Acceptance Gates (How We Prevent Overfitting)

### 8.1 Minimum metrics
A candidate can only be promoted if it improves a weighted score:

- Risk-adjusted return (Sharpe/Sortino)
- Max drawdown
- Tail risk / CVaR proxy
- Turnover (penalize)
- Stability of weights/params (penalize oscillation)
- Cost sensitivity (robust under higher slippage)

### 8.2 Statistical and robustness checks
- Block bootstrap confidence intervals
- Reality check vs baseline (don’t accept tiny improvements)
- Parameter sensitivity check (local perturbations)
- Leakage checks (feature alignment, time indexing)

### 8.3 Safety gates
- No NaNs
- No extreme exposures
- No increase in flip frequency beyond cap
- No increased correlation concentration

---

## 9) Promotion + Rollback Pipeline (Safe Deployment)

### 9.1 Stages
1) **Shadow**: compute/log only
2) **Paper execute**: trade paper with strict caps
3) **Canary**: tiny risk budget subset of universe
4) **Ramp**: gradually increase budget if stable

### 9.2 Automatic rollback triggers
- Drawdown breach
- Slippage anomaly
- Drift + calibration collapse
- Latency / missing data
- Regime churn explosion

Rollback behavior:
- revert to last-known-good policy package
- freeze adaptation
- reduce exposure to zero until stable

---

## 10) Monitoring & Telemetry (The Nervous System)

### 10.1 What to monitor continuously
- Feature drift (population stability index / simple distribution shifts)
- Forecast calibration and residual drift
- Regime churn rate
- Strategy contribution / attribution
- Turnover + slippage + fill rates
- Order rejection/cancel rates
- Latency and data quality

### 10.2 Alerts
- High drift + declining performance
- Repeated gate failures (training pipeline broken)
- Excessive turnover
- Stale policy snapshot (learning stopped)

---

## 11) Mapping to This Repository (Concrete Components)

This repo already has:
- FastAPI app factory + lifespan
- Deterministic `StrategyEngine`
- `OrderService.plan_and_submit` + outbox worker
- Multi-strategy runner + scheduler
- Breakout scanner + routes
- Initial bounded “living policy” layer (L1)

To reach FULL living organism, add these major subsystems:

1) **Feature Store + Versioned Pipelines**
2) **Backtest/Walk-forward Runner** integrated with the same strategies/policy
3) **Training Orchestrator** (nightly/weekly jobs)
4) **Model Registry + Policy Registry**
5) **Promotion Controller** (shadow/canary/ramp)
6) **Attribution Engine** using fills/positions (not proxy)
7) **Drift/Calibration Monitors** + alerting

---

## 12) Execution Plan (Phased, With Deliverables)

### Phase 0 — Hardening the existing L1 loop (1–2 days)
Goal: ensure the current bounded policy loop is safe, reproducible, and observable.

Deliverables:
- Persisted snapshots with version IDs and config hashes
- Policy change budget enforced everywhere
- Metrics: regime churn, weight deltas, turnover proxy
- Runbook: how to freeze/rollback

Tasks:
- Add explicit “policy package id” into decision logs
- Add endpoint to fetch current policy snapshot and recent history
- Add kill switch env flags and verify they override schedulers

### Phase 1 — True attribution from fills/positions (3–7 days)
Goal: learning is driven by **realized execution outcomes**, not price-close proxies.

Deliverables:
- Attribution tables/events per strategy × symbol × time
- Slippage and fee attribution
- Realized vs expected returns per strategy

Tasks:
- Implement a PnL attribution service that ingests fills and reconstructs position changes
- Store per-trade outcomes keyed by strategy source
- Compute reward signals: net PnL, drawdown impact, turnover penalty

### Phase 2 — Feature store + online/offline parity (1–2 weeks)
Goal: same feature code path for live and backtests.

Deliverables:
- Versioned feature configs
- Stored feature snapshots for training windows
- QA checks integrated into pipeline

Tasks:
- Create `backend/features/` module with pure functions + configs
- Add “feature pipeline version” to all logs and training runs

### Phase 3 — Walk-forward backtest runner (1–2 weeks)
Goal: validate any candidate policy/model before promotion.

Deliverables:
- Walk-forward evaluator producing HTML/JSON reports
- Baseline comparisons and gates

Tasks:
- Build an event-driven backtest harness that calls the same strategy interfaces
- Implement costs/slippage model and sensitivity testing

### Phase 4 — Training orchestrator + registry (2–4 weeks)
Goal: autonomous nightly candidate generation and evaluation.

Deliverables:
- Nightly job that trains candidates, evaluates, and writes to registry
- Registry schema: model artifacts + metrics + lineage

Tasks:
- Implement job runner (cron/APS scheduler/Arq/Celery—choose one consistent with current infra)
- Add artifact storage (local filesystem first, then S3/MinIO)

### Phase 5 — Promotion controller (1–2 weeks)
Goal: automatic promotion to shadow/paper with rollback.

Deliverables:
- Promotion state machine
- Canary/ramp logic
- Automatic rollback triggers

Tasks:
- Add “active policy pointer” to DB
- Ensure runtime always reads active policy package at start of tick

### Phase 6 — Regime-conditioned ensembles + robust optimization (ongoing)
Goal: mature learning without instability.

Deliverables:
- Per-regime models
- Conservative meta-policy for blending
- Strong monitoring and governance

---

## 13) Operational Runbooks (How We Run It Day-to-Day)

### 13.1 Schedules
- Intraday: compute signals, apply bounded weight updates, execute (paper/live)
- Nightly: attribution, drift checks, candidate generation, walk-forward evaluation
- Weekly: stress tests, risk constraint review, broader hyperparameter search

### 13.2 Incident playbooks
- Drift alert: freeze adaptation + reduce exposure + run forced evaluation
- Performance decay: rollback to last-known-good + increase validation strictness
- Data outage: stop trading + mark symbols stale

---

## 14) Definition of Done (When We Can Claim “FULL LIVING”)

You can credibly call it a FULL living organism when:
- Every production decision is reproducible from stored data + version IDs
- Learning uses fill-based attribution with costs
- Nightly pipeline trains candidates and runs walk-forward evaluation automatically
- Candidates are promoted only via acceptance gates
- Rollback is automatic and tested
- Monitoring detects drift, calibration collapse, and regime churn
- The system can run unattended for long periods without silent failure

---

## 15) Immediate Next Actions (If You Want This Started Now)

1) Implement **fill-based attribution** (Phase 1) — this is the biggest step-change in “real learning.”
2) Implement **nightly evaluator** that can score current policy vs baseline.
3) Add **promotion state machine** (shadow → paper) with rollback.

If you confirm you want me to proceed, I can start Phase 1 in-code (schemas + attribution service + tests) while keeping existing live paper readiness intact.
