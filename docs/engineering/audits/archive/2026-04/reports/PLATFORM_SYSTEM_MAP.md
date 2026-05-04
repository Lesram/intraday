# Platform System Map

**Date**: 2026-04-23
**Live commit**: `ce06d41` | **HEAD**: `33d6138` | **Worktree**: 4 files dirty (backward reverts)
**Scope**: Every subsystem, its purpose, primary files, status, and downstream consumers.

---

## Subsystem status legend
- **LIVE EFFECTIVE** — running, consumed by downstream, matches spec
- **LIVE PARTIAL** — running, but either divergent in worktree, not fully wired, or weakened
- **DORMANT** — code exists, not invoked in live path
- **DEAD** — code exists but all execution paths removed; flag-only residue
- **UNKNOWN** — not fully verifiable from static read

---

## 1. Live execution loop

- **Purpose**: Drive one tick per `ORGANISM_TICK_INTERVAL_SECONDS` (=10s) across the whole strategy stack.
- **Files**: `backend/organism/live_engine.py` (4990 L), `scheduler.py`, `runner.py`.
- **Status**: **LIVE EFFECTIVE**
- **Entry**: `scheduler.start()` → `live_engine.live_tick()` → `_live_tick_inner()`
- **12 phases** (in order):
  1. Governance halt check (`live_engine.py:1246`)
  2. Warmup gate
  3. Stale-data gate (120s threshold)
  4. EOD entry block (15:45 ET no new entries, 15:58 ET force flatten)
  5. Market scan (every 30 ticks; injects top 20 into universe)
  6. Fetch bars + compute features
  7. Regime detect
  8. Exit processing + `_reconcile_closes()` → TradeRecord (line 3688)
  9. Pyramid checks on existing positions
  10. Entry scanning (breakout + alpha + market scanner)
  11. Kelly sizing + submission
  12. Reconciliation + periodic `brain.save_essential_state()`
- **Downstream consumers**: Alpaca (orders), database (orders/trades), brain_persistence (state)
- **Gotchas**: step numbering references "improve9" comments; a `_route_exploration` block remains (routing but not executing — dead code).

---

## 2. Persistence / brain durability

- **Purpose**: Durably persist runtime truth (trades, learning state, manifest) AND promotion-gated artifacts (ML joblib, evolved_params) with wipe protection.
- **Files**: `backend/organism/brain_persistence.py` (1869 L), `organism_brain/*`.
- **Status**: **LIVE EFFECTIVE** (post Full Patch F)
- **Writes under `organism_brain/`**:
  - `trade_history.csv` (append/rebuild)
  - `learning_state.json` (authoritative total_trades, cumulative_pnl)
  - `evaluation_event_history.json`
  - `equity_curve.csv`, `extra_counters.json`, `governance_state.json`, `regime_state.json`
  - `ml_state.json` (feature config only, NOT weights)
  - `manifest.json` via `_write_manifest_guarded()` (atomic, guarded)
  - Promotion-gated: `ml_classifier.joblib`, `ml_regressor.joblib`, `evolved_params.json`
- **Guards**:
  - **F1/F2** (commit `eaa4b2f`, `3a694ee`): single `_write_manifest_guarded()` helper for `save_essential_state()` and `save()`
  - **F-lite** (`3528162`): extends guard to essential-state
  - **F3** (`9e7c9a9`): break-glass reset + suspicious-write instrumentation + read-back invariant
  - **F4** (`7d36b61`): forensic guard + bypass audit
- **Force-save admin**: `POST /organism/save?force=true` (admin-auth) — writes ML joblib bypassing walk-forward
- **Downstream consumers**: continuous_learner, ml_signal, self_evolution, governance on restore

---

## 3. Organism brain state (disk snapshot)

- **Purpose**: Cross-restart truth store
- **Files**: `organism_brain/` dir
- **Current values** (2026-04-23 19:57 UTC):
  - manifest.json: gen 115, 1184 runs, 370 trades, PnL −$619.75, Sharpe 3.44, ml_trained=true, 79 features
  - learning_state.json: retrain_count 115, drift_events 0, gen_accuracies_last4 [0.76, 0.61, 0.76, 0.57]
  - ml_state.json: is_trained=true, acc 0.617, precision 0.515, recall 0.715
  - evolved_params.json: Apr-15 mtime (STALE on disk; in-memory is gen 115)
  - governance_state.json: frozen=false, halted=false, drawdown_limit=0.20
- **Status**: **LIVE EFFECTIVE** (with disk-artifact staleness noted for evolved_params / ml joblib)

---

## 4. Continuous learner

- **Purpose**: Ingest every trade, gate retrains, track Sharpe/attribution
- **Files**: `continuous_learner.py`
- **Instantiation**: `live_engine.py:345` — `ContinuousLearner(signal_generator=self.signal_gen, retrain_every_n_bars=60, min_trades_for_eval=10)`
- **Call chain**:
  - `record_trade()` after every fill (`live_engine.py:~1108, 3910`)
  - `retrain(features_by_symbol)` every 60 bars (line 4279)
  - `compute_attribution()` after retrain (line 4287)
- **Status**: **LIVE EFFECTIVE**
- **Downstream consumers**: ml_signal (training), self_evolution (trade counts), brain_persistence (state)

---

## 5. ML training / evaluation / promotion

- **Purpose**: Classifier + regressor on 79 features, with acceptance-gated retraining
- **Files**: `ml_signal.py`, `ml_features.py`, `background_trainer.py`, `training.py`, `ensemble_models.py`, `promotion.py`
- **Status**: **LIVE EFFECTIVE**
- **Flow**:
  - `MLSignalGenerator.train()` fits XGBClassifier + XGBRegressor (rolling windows)
  - `acceptance_gate()` in `continuous_learner.py:44–141` — composite = 0.4·hit + 0.3·acc + 0.6·(dir_acc−0.5), precision ≥ 0.45, calibration monotonic
  - Rollback on reject: restores prior `_clf`, `_reg`, `_is_trained` (line 348–357)
  - Background trainer path: `background_trainer.py:55–162` applies same gate
- **Inference**: `predict_batch(features)` at `live_engine.py:2045`
- **Gotcha**: calibration map (`_compute_effective_confidence`) is instance-level, reset on retrain → one-epoch uncalibrated window after every swap (I-10, P2)

---

## 6. Walk-forward gate

- **Purpose**: Decide if a retrained model is promotion-eligible based on historical equity-curve performance
- **Files**: `walk_forward.py` (466 L)
- **Status**: **LIVE**
- **Input**: `learner.state.best_sharpe` (authoritative; commit `93593a2`)
- **Behavior**: Even when gate BLOCKS promotion, trades still persist (commit `007a977` / `3534346` "split persistence")

---

## 7. Confidence formula

- **Purpose**: Combine ML, breakout, tension signals into a single entry score
- **File**: `live_engine.py:2170–2184`
- **Status**: **LIVE (PRODUCTION BRANCH ACTIVE)** — 370 trades > 200 → production formula active
- **Formulas**:
  - Learning (trades < 200): `0.65·breakout + 0.35·tension` (ML zeroed)
  - Production (trades ≥ 200): `0.50·ml_conf + 0.30·breakout + 0.20·tension`
- **Gates**:
  - Learning baseline: 0.25
  - Production baseline: 0.40
  - Production defensive (chop, high_vol, trending_down): 0.45
- **Gotcha**: Confidence computed in one place, but `alpha_scanner` and `kelly_sizer` hold independent copies of weights/thresholds — **authority split** (I-08, P1)

---

## 8. Regime detection

- **Purpose**: Classify each bar as trending_up/down, chop, high_vol, low_vol, stress, unknown
- **File**: `regime.py` (682 L)
- **Status**: **LIVE EFFECTIVE**
- **Consumers**:
  - adaptive_exits (regime × ATR tables for stop/trail/tp/max_bars)
  - alpha_scanner (regime passed to scan)
  - self_evolution (regime for evolve())
  - live_engine (inverse-ETF suppression in chop — Exp2)
- **Gotcha**: PSI calculation wrapped in bare `except Exception: return 0.0` (hides regime-shift detection failures — P2)

---

## 9. Alpha scanner

- **Purpose**: Rank symbols by composite (ML + breakout + momentum + volume + regime) and return top-N
- **File**: `alpha_scanner.py`
- **Status**: **LIVE EFFECTIVE**
- **Parameters**: `ALPHA_TOP_N=5` (separate from `MAX_OPEN_POSITIONS=8`)
- **Learning mode**: zeroes ML weight when learning_mode=True OR model untrained
- **Consumers**: entry pipeline in `live_engine.py:2050+`
- **Gotcha**: duplicated learning-mode threshold definition with kelly_sizer

---

## 10. Adaptive exits

- **Purpose**: ATR-based stop, trailing, take-profit, failure-to-follow (FTF), horizon timeout, max_hold
- **File**: `adaptive_exits.py` (720 L)
- **Status**: **LIVE PARTIAL — WORKTREE DIVERGED**
  - HEAD (`33d6138`): contains Exp4 chop-trail widen logic (5× ATR in chop or disable)
  - Worktree: **Exp4 REVERTED** — matches container
  - Container (`ce06d41`): pre-Exp4 standard REGIME_TRAIL_ATR lookup
- **Regime tables** (hard-coded, 4 separate dicts with no cross-check):
  - `REGIME_STOP_ATR`: trending_up=3.5, trending_down=2.5, chop=2.5, high_vol=4.0, low_vol=3.0, stress=2.5, unknown=3.0
  - `REGIME_TRAIL_ATR`: trending_up=5.0, trending_down=3.5, chop=3.0, high_vol=4.5, low_vol=4.5, stress=3.0, unknown=4.0
  - `REGIME_TP_R`: trending_up=6.0, trending_down=3.0, chop=2.5, high_vol=3.0, low_vol=5.0, stress=2.0, unknown=4.0
  - `REGIME_MAX_BARS`: trending_up=0, trending_down=45, chop=30, high_vol=45, low_vol=0, stress=20, unknown=60
- **Consumers**: `_exit_levels` dict, `_reconcile_closes()`, exit event telemetry
- **THE EDGE LEAK LIVES HERE**: pyramid_cut premature exits + trailing-stop giveback ($195 / 5 sessions)

---

## 11. Pyramider

- **Purpose**: Momentum-based pyramiding (add leg on strength) + pyramid_cut (reduce leg on adverse excursion) + min-hold gate (Exp1A)
- **File**: `pyramider.py`
- **Status**: **LIVE PARTIAL — WORKTREE DIVERGED**
  - HEAD (`33d6138`): G3 NaN pyramid guard present (`math.isfinite(current_price)` early-return)
  - Worktree: **G3 REVERTED** — matches container
  - Container (`ce06d41`): no G3 — silent-failure risk if streaming data stale
- **Consumers**: called from `live_engine.py:1680–1740` per-position

---

## 12. Kelly / risk sizing

- **Purpose**: Convert confidence + fitness + equity + regime into share count
- **File**: `kelly_sizer.py` (682 L)
- **Status**: **LIVE**
- **Parameters**:
  - `risk_budget_learning=0.001` (0.10% equity)
  - `risk_budget_production=0.0025` (0.25% equity)
  - `_ML_CONFIDENCE_MIN=0.5` (hardcoded; no env override)
  - Drawdown scale floor (10%) applied at `max_drawdown_cutoff` (25%)
- **Gotchas**:
  - No validation that `drawdown_floor < max_drawdown_cutoff` (P2)
  - `_exploration_rejects` tracking list never acted on (P3)

---

## 13. Governance / drawdown / warmup

- **Purpose**: Kill switches, trading phase, warmup, adaptation freeze
- **File**: `governance.py` (250 L), `trading_phase.py`
- **Status**: **LIVE**
- **Current state** (`governance_state.json`):
  - frozen=false, trading_halted=false
  - drawdown_limit=0.20 (container env overrides 0.05 default — **I-02**)
  - drawdown_triggered_at=null
  - effective_cooldown_s=300
- **Halts**:
  - Explicit `ORGANISM_HALT_TRADING=1` env
  - Active drawdown cooldown (triggered when portfolio PnL < −20%)
  - Governance freeze does NOT halt trading — only prevents adaptation
- **Gotcha**: No audit log on freeze/halt state transitions (P2)

---

## 14. Broker integration

- **Purpose**: Alpaca paper/live trading
- **Files**: `backend/integrations/alpaca_*`, usage throughout `live_engine.py`
- **Status**: **LIVE (paper mode)**
- **Account**: PA3RLEN7T0N4, paper=true, equity $111,529.48
- **Features**:
  - Stream client for order state + stale-fill detection (`_stream.is_order_terminal()` at line 1190)
  - Cost-weighted avg for pyramid entry_price (`d46e17a`)
  - Position snapshot for reconciliation fallback
- **Gotchas**: Alpaca historical bar timestamps lag 2–3 min (noted inline)

---

## 15. Scheduler / background jobs

| Scheduler | Role | Status | File |
|---|---|---|---|
| `scheduler.py` (388 L) | Main live-tick driver | LIVE | `scheduler.start()` |
| `nightly_scheduler.py` (158 L) | Pre-open + post-close diagnostics | LIVE | `start_organism_nightly_scheduler(app)` |
| `diagnostic_scheduler.py` (249 L) | Deep diagnostics + `_evaluate_and_alert()` | LIVE | Called by nightly + internal |
| `background_trainer.py` (591 L) | Async walk-forward ML training | LIVE (gated) | Called by live_engine periodic retrain |

- **Status**: **LIVE**
- **Overlap**: none — nightly runs outside live-tick window

---

## 16. Admin / API routes

- **Purpose**: Operator control surface (halt, freeze, save, rollback, tick, status)
- **File**: `backend/organism/routes.py` (865 L)
- **Status**: **LIVE**
- **All dangerous routes require `Depends(require_admin)`**

| Route | Method | Effect | Auth |
|---|---|---|---|
| `/organism/halt` | POST | sets `trading_halted=True` | ✓ admin |
| `/organism/resume` | POST | clears halt | ✓ admin |
| `/organism/freeze` | POST | prevents adaptation (not trading) | ✓ admin |
| `/organism/save?force=true` | POST | writes ML joblib bypassing walk-forward | ✓ admin |
| `/organism/rollback` | POST | revert to prior brain snapshot | ✓ admin |
| `/organism/tick` | POST | manually trigger one tick | ✓ admin |
| `/organism/status` | GET | snapshot | — |
| `/organism/attribution` | GET | attribution report | — |

- **Gotcha**: `/organism/train` result dict not typed; silent partial failures possible (P2)

---

## 17. Monitoring / watchdogs / alerting

- **Purpose**: Surface critical events to operator (Slack / webhook)
- **Files**: `backend/infra/alerting.py`, hook-in points: `diagnostic_scheduler.py:194+`, `brain_persistence.py:297+`, `ml_signal.py:357+`
- **Status**: **PARTIAL — wired at `33d6138`, NOT IN LIVE CONTAINER (`ce06d41` predates commit)**
- **Alert categories / severities**: CRITICAL, WARNING, INFO
- **Triggers**:
  - Guard fire (brain save block) → CRITICAL
  - Pre-open all-fail → CRITICAL
  - Feature drift detected → WARNING
- **Gotcha**: No URL set even at HEAD — `SLACK_WEBHOOK_URL` absent in `.env`

---

## 18. Deployment / runtime / env

- **Docker**: 3 containers via `docker-compose.paper.yml` with `env_file: .env`
- **Container runtime**: `intra-api-1` (built 2026-04-16T02:42Z), `intra-redis-1`, `trading_platform_db_paper`
- **Image fingerprint**: matches `ce06d41` on all 5 critical files
- **Environment resolution chain**:
  1. `.env` → docker-compose → container env (wins at runtime)
  2. code defaults in `backend/config.py` / module-level constants (if no env)
- **Key runtime env**:
  - `APP_ENVIRONMENT=development` (NOT `paper` — memory gotcha)
  - `ALPACA_PAPER=true`
  - `ORGANISM_DRAWDOWN_KILL_PCT=0.20` (4× more permissive than code default 0.05 — **I-02**)
  - `ORGANISM_MAX_POSITIONS=8`
  - `ORGANISM_ALPHA_TOP_N=5`
  - `ORGANISM_EXPLORATION_ENABLED=false`
  - `ORGANISM_TICK_INTERVAL_SECONDS=10`
  - `ORGANISM_LIVE_TIMEFRAME=1Min`
- **Missing**:
  - `ORGANISM_MAX_NOTIONAL` (per-trade cap; commit `bb5cbb5`)
  - `ORGANISM_MAX_DAILY_LOSS` (circuit breaker; commit `bb5cbb5`)
  - `SLACK_WEBHOOK_URL` (alerting; commit `33d6138`)
- **Brain volume mount**: `./organism_brain:/app/organism_brain` (added 2026-03-31)

---

## 19. Test coverage

- **Test dir**: `tests/` — ~447 files
- **Covered subsystems**:
  - LiveEngine core (`test_organism_live_engine.py`)
  - Brain persistence (`test_organism_blueprint_persistence.py`, F1/F2/F-lite/F4 tests)
  - Governance (`test_h5_settings_governance.py`)
  - Diagnostic scheduler (`test_diagnostic_scheduler.py`)
  - Replay simulator (`test_replay_simulator.py`)
- **Command**: `./venv/bin/python -m pytest tests/ --timeout=15 -q --tb=line`
- **Known issue**: 4 flaky async tests (pass individually, fail in full suite — timing issues, per CLAUDE.md)
- **Status**: **LIVE, with known flakiness**

---

## 20. Cross-cutting: the 3-source config truth problem

Because `docker-compose.paper.yml` ships `env_file: .env` and code has module-level defaults, the authoritative value of any parameter depends on **which source wins**:

| Parameter | Code default | `.env` | docker-compose | Runtime wins | Note |
|---|---|---|---|---|---|
| drawdown_kill_pct | 0.05 | 0.20 | — | 0.20 | **I-02** |
| max_positions | 8 | 8 | — | 8 | consistent |
| alpha_top_n | 5 | 5 | — | 5 | consistent |
| tick_interval_seconds | 10 | 10 | — | 10 | consistent |
| exploration_enabled | false | false | — | false | consistent (but flag read is dead — I-09) |
| timeframe | 1Day | — | 1Min | 1Min | container-only |
| learning_mode_threshold | 200 | — | — | 200 | code default |
| evolution_freeze_until | 300 | — | — | 300 | code default |
| risk_budget_learning | 0.001 | — | — | 0.001 | code default |
| risk_budget_production | 0.0025 | — | — | 0.0025 | code default |

**Recommendation** (not a P0): create `docs/engineering/config_manifest.md` + startup validator that warns when env ≠ code default by >5%.

---

## 21. What is NOT in the platform today (and sometimes thought to be)

- **Shorting** — `ORGANISM_LONG_ONLY=true`; no short path active
- **Streaming data replacement for REST** — `ORGANISM_STREAMING_ENABLED=false` by default (check `.env`)
- **Market-making / passive orders** — not implemented
- **Options** — not implemented
- **Multi-timeframe fusion** — `multi_timeframe.py` exists but primary is `1Min`
- **Exploration execution** — removed in improve9; flag + routing still read but no-op (dead code, I-09)
- **Sector concentration cap (notional)** — only count-based (3/sector max); no % cap (real-money gap)
- **Position-loss auto-close** — stops only; no −$200/pos safety (real-money gap)
- **Daily max-loss auto-halt (live)** — code at HEAD `bb5cbb5` but env-gated default-off; not live in container
- **Sharded ML ensemble** — `ensemble_models.py` exists; not in primary inference path today

— End of Platform System Map —
