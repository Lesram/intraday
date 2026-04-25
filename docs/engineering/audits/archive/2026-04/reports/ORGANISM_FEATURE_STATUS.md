# Organism Feature Status

**Date**: 2026-04-23 | **Live**: `ce06d41` | **HEAD**: `33d6138` | **Brain**: gen 115, 370 trades

This replaces the prior summary with an evidence-based classification, including why each feature matters *now* and what to do with it.

---

## Status legend
- **LIVE & EFFECTIVE** — running, wired, consumed, doing its job
- **LIVE BUT WEAK / PARTIAL** — running but contributing less than spec implies
- **LIVE BUT BYPASSED** — running but dominated/overridden downstream
- **DORMANT** — code instantiated but never called on live path
- **DEAD / LEGACY** — code exists, no execution path, flag-only residue
- **UNKNOWN** — cannot be fully verified without dynamic inspection

---

## 1. Continuous learning

- **Status**: **LIVE & EFFECTIVE**
- **Evidence**: `continuous_learner.py` instantiated at `live_engine.py:345`; `record_trade()` invoked at line ~1108/3910 after every fill; `retrain()` invoked at line 4279 every ~60 bars; manifest shows `retrain_count=115`, `drift_events=0`.
- **Why it matters now**: This is the spine. Every trade updates state, every epoch re-trains ML. Evolution reads its outputs.
- **Action**: **KEEP**.

## 2. Feature generation (79 features)

- **Status**: **LIVE & EFFECTIVE**
- **Evidence**: `ml_features.py:457` rows; `ml_state.json:82` lists all 79 columns; `manifest.json:feature_count=79`.
- **Action**: **KEEP**. Feature drift guard at HEAD (`679ffd2`) not yet live; deploy with hardening bundle.

## 3. ML training (XGB classifier + regressor)

- **Status**: **LIVE & EFFECTIVE**
- **Evidence**: `ml_signal.py` imports `XGBClassifier, XGBRegressor` with `_HAS_XGB=True`; evolved XGB params in `evolved_params.json` (n_est=177, max_depth=3, lr=0.04); in-process training via `continuous_learner.retrain()`; async via `background_trainer.py`.
- **Current metrics** (`ml_state.json`): is_trained=true, accuracy=0.617, precision=0.515, recall=0.715, F1=0.599.
- **Action**: **KEEP**. Calibration persistence (I-10, P2) is the one fix.

## 4. Model acceptance / rejection

- **Status**: **LIVE & EFFECTIVE**
- **Evidence**: Shared `acceptance_gate()` at `continuous_learner.py:40–141` applied by both sync learner retrain AND async `background_trainer.py:137–162`. Rollback on reject at line 348–357 (restores prior `_clf`, `_reg`, `_is_trained`).
- **Criteria**: composite = 0.4·hit_rate + 0.3·accuracy + 0.6·(dir_acc−0.5); precision ≥ 0.45; calibration monotonicity; min_score=0.25 (mature) / 0.35 (immature).
- **Action**: **KEEP**.

## 5. Model use in confidence

- **Status**: **LIVE & EFFECTIVE (production branch active)**
- **Evidence**: `live_engine.py:2170–2184` has both learning and production formulas; trade count 370 > 200 → production blend `0.50·ML + 0.30·breakout + 0.20·tension` is currently active.
- **Note**: `alpha_scanner` computes its own composite and zeroes ML in learning mode independently — authority split (I-08, P1).
- **Action**: **KEEP**. Consolidate authority into `ml_signal._compute_effective_confidence`.

## 6. Self-evolution

- **Status**: **LIVE, NOW UNFROZEN**
- **Evidence**: `self_evolution.py` (1247 L); `EvolutionEngine(alpha=0.30, max_shift=0.20, min_trades=8)` at `live_engine.py:359`; `_EVOLUTION_FREEZE_TRADES=300`; current trades 370 ≥ 300 → `evolve()` is now running.
- **What it adapts**: signal weights, exit params, regime size scales, feature weights, symbol fitness, direction thresholds, breakout weights/periods, XGB hyperparams.
- **Caveat**: In learning phase (pre-300), evolution did bookkeeping-only restore (`live_engine.py:690–695`). That phase is over.
- **Action**: **KEEP**. Monitor first 100 post-unfreeze trades for evolved_params drift. Expect evolved_params.json rewrite on next save (Apr-15 stale mtime will refresh).

## 7. Evolved parameters application

- **Status**: **LIVE (memory) / STALE (disk)**
- **Evidence**: `evolved_params.json` mtime = Apr-15 (image-era); in-memory state is gen 115. Applied via `apply_evolved_params()` at `live_engine.py:4309–4320` pushing new weights into scanners, sizer, exit engine.
- **Gotcha**: "params_generation" version tag absent (P3 D17) — AdaptiveExitEngine may scale from stale base values after evolution freezes/unfreezes.
- **Action**: **KEEP**. Add version tag in future hardening pass.

## 8. Transfer knowledge / warm-start

- **Status**: **LIVE**
- **Evidence**: `TransferLearningEngine(brain_dir)` at `live_engine.py:382`; on restore: `load_knowledge()` + `warm_start_params()` at line 933–952; on shutdown: `record_run()` + `save_knowledge()` at line 4665–4672.
- **File**: `transfer_knowledge.json` — currently NOT PRESENT on disk (acceptable per PLATFORM_STATE_SNAPSHOT_APR23 §6); warm-start happens from historical run snapshots when available.
- **Action**: **KEEP**. Low-priority; optional safety net.

## 9. Walk-forward gating

- **Status**: **LIVE**
- **Evidence**: `walk_forward.py` (466 L); reads authoritative `learner.state.best_sharpe` (commit `93593a2`); split persistence ensures trades persist even when gate BLOCKS (commit `007a977`/`3534346`).
- **Action**: **KEEP**.

## 10. Regime adaptation

- **Status**: **LIVE & EFFECTIVE**
- **Evidence**: `RegimeDetector` classifies each bar; feeds alpha_scanner (line 2049), exit engine (line 1515), evolution (line 4306), inverse-ETF gate (line 2468–2474). Current universe state: chop is 96–97% of ticks.
- **Action**: **KEEP**.

## 11. Alpha ranking

- **Status**: **LIVE & EFFECTIVE**
- **Evidence**: `alpha_scanner.py`; `AlphaScanner(top_n=5)` at `live_engine.py:300`; per-tick scan at line 2049; `learning_mode` parameter zeros ML weight when learning OR ML untrained.
- **Action**: **KEEP**.

## 12. Pyramiding

- **Status**: **LIVE BUT WEAKENED — WORKTREE DIVERGED**
- **HEAD** (`33d6138`): G3 NaN pyramid guard present (`math.isfinite(current_price) or current_price <= 0 → return PyramidAction("none")`).
- **Worktree**: G3 REVERTED (matches live container).
- **Container** (`ce06d41`): no G3 — silent failure risk if streaming data goes NaN (NaN comparisons always False → pyramid silently disabled).
- **Why it matters now**: Inconsistent state between branch and worktree blocks deploys.
- **Action**: **FIX**. Decide whether to keep G3 or remove; resolve worktree. G3 is a defensive guard with very low cost; recommend KEEP and commit.

## 13. Exit adaptation

- **Status**: **LIVE BUT ACTIVELY DESTROYING EDGE**
- **Evidence**: `adaptive_exits.py` (720 L) with 4 regime tables (stop/trail/tp/max_bars). `_exit_levels` restored across restarts (H5, commit `2018999`). Trade data shows `pyramid_cut` is 100% losers; `timeout/max_hold` is ~100% winners — exits are cutting winners and forcing holds on losers.
- **Worktree diverged**: Exp4 chop-trail widen REVERTED — HEAD has it, worktree does not, container pre-dates.
- **Action**: **KEEP + REFORM**.
  1. Resolve worktree (commit revert OR restore to HEAD)
  2. Ship Exp4 (un-revert + deploy) as next algorithmic change
  3. Consider widening pyramid_cut adverse threshold in chop beyond what Exp1A already does

## 14. Scheduler / promotions

- **Status**: **LIVE**
- **Evidence**: `scheduler.py`, `nightly_scheduler.py`, `diagnostic_scheduler.py`, `background_trainer.py` — all started; no overlap; admin-visible.
- **Action**: **KEEP**.

## 15. Governance / drawdown kill / freeze / halt

- **Status**: **LIVE**
- **Evidence**: `governance.py`; current state frozen=false, halted=false, drawdown_limit=0.20.
- **Caveat**: drawdown_kill_pct 0.20 runtime vs 0.05 code default (I-02, P0).
- **Action**: **KEEP + DECIDE** on canonical kill threshold.

## 16. Governance API (settings enforce frozen/halted)

- **Status**: **OFFLINE READY** (commit `c306074` at HEAD)
- **Action**: **DEPLOY with hardening bundle**.

## 17. Per-trade notional cap + daily max-loss circuit breaker

- **Status**: **OFFLINE READY, env-gated default-inert** (commit `bb5cbb5`)
- **Action**: **DEPLOY + set `ORGANISM_MAX_NOTIONAL` > 0 and `ORGANISM_MAX_DAILY_LOSS` > 0**. Without env set, code is no-op.

## 18. Feature drift guard (H2)

- **Status**: **OFFLINE READY** (commit `679ffd2`)
- **Action**: **DEPLOY with hardening bundle**.

## 19. Production risk-budget cap (H1)

- **Status**: **OFFLINE READY** (commit `679ffd2`)
- **Action**: **DEPLOY with hardening bundle**.

## 20. G1/G2 mechanical guards (exit-level restore warning + cooldown-on-success-only)

- **Status**: **OFFLINE READY** (commit `15cc0a4`)
- **Action**: **DEPLOY with hardening bundle**.

## 21. Slack / webhook alerting

- **Status**: **OFFLINE READY, URL MISSING** (commit `33d6138`)
- **Action**: **DEPLOY + set `SLACK_WEBHOOK_URL` in `.env`**.

## 22. Exploration execution

- **Status**: **DEAD / LEGACY**
- **Evidence**: Execution removed in improve9 (H1); but `ORGANISM_EXPLORATION_ENABLED` env flag still read at `live_engine.py:186`; `_route_exploration` routing at line 2241–2261 still flags candidates; comment at line 2624 confirms "removed".
- **Why it matters now**: Future maintainer sees flag, re-enables, finds no-op. Misleading.
- **Action**: **REMOVE**. Delete flag read, remove routing block, delete exploration-rejects tracking list.

## 23. Exp1A — chop-regime minimum-hold gate for pyramid_cut

- **Status**: **LIVE & EFFECTIVE** (commit `ab54b2f`)
- **Evidence**: On Apr-21 session, pyramid_cut share reduced 56% → 33%; 6 suppressions observed.
- **Action**: **KEEP**.

## 24. Exp2 — suppress inverse-ETF entries in chop

- **Status**: **LIVE & EFFECTIVE** (commit `d79cae0`)
- **Evidence**: 0 PSQ/SH trades in observation window post-Exp2 (down from 0%-wr trades −$28.54 in baseline).
- **Action**: **KEEP**.

## 25. Exp3 — confidence inversion side-by-side logging (observation only)

- **Status**: **LIVE, INSTRUMENTATION ONLY** (commit `ce06d41`)
- **Evidence**: No behavior change; logs only.
- **Action**: **KEEP running; DO NOT SHIP Exp3B** until more data. Apr-21 showed first session where ≥0.45 confidence bucket WON, weakening the inversion hypothesis.

## 26. Exp4 — chop trailing-stop giveback control (widen trail in chop)

- **Status**: **OFFLINE, REVERTED IN WORKTREE** (commit `b97f903`)
- **Evidence**: $195.21 of MFE destroyed by trailing-stop giveback in 5-session window — this is exactly what Exp4 targets.
- **Action**: **UN-REVERT + SHIP** as the next edge-moving change after hardening bundle deploy.

## 27. Take-profit exit in production mode

- **Status**: **LIVE & EFFECTIVE (new)**
- **Evidence**: Apr-21 session — XLE +$9.99 take_profit exit was the **first genuine TP exit** in observation history. Production-mode exit now available post-300.
- **Action**: **KEEP**. Monitor hit rate across more sessions.

## 28. Reconciliation hardening (stale-fill, cost-weighted avg, broker-sync pyramid preservation)

- **Status**: **LIVE** (`53cc1ad`, `d46e17a`, `2018999`)
- **Action**: **KEEP**.

## 29. Brain persistence — split write (trades survive gate block)

- **Status**: **LIVE** (`007a977`, `3534346`)
- **Action**: **KEEP**.

## 30. Full Patch F manifest guard

- **Status**: **LIVE** (`62256d7`, `3528162`, `eaa4b2f`, `3a694ee`, `9e7c9a9`, `7d36b61`, F-lite + F1-F4)
- **Action**: **KEEP**. This is the platform's durable spine.

---

## Summary table (what to do with each feature)

| Feature | Verdict | Action | Priority |
|---|---|---|---|
| Continuous learning | LIVE EFFECTIVE | Keep | — |
| Feature generation | LIVE EFFECTIVE | Keep | — |
| ML training | LIVE EFFECTIVE | Keep | — |
| Acceptance gate | LIVE EFFECTIVE | Keep | — |
| Confidence (prod) | LIVE EFFECTIVE | Keep + unify authority | P1 |
| Self-evolution | LIVE UNFROZEN | Keep + monitor | P2 |
| Evolved params apply | LIVE (disk stale) | Keep | — |
| Transfer knowledge | LIVE | Keep | — |
| Walk-forward gate | LIVE | Keep | — |
| Regime adaptation | LIVE | Keep | — |
| Alpha ranking | LIVE | Keep | — |
| Pyramiding | LIVE (G3 diverged) | **Fix worktree** | **P1** |
| Exit adaptation | LIVE but destroying edge | **Ship Exp4** | **P0 (edge)** |
| Scheduler | LIVE | Keep | — |
| Governance | LIVE | Decide kill_pct | P0 |
| Settings API enforce | OFFLINE READY | Ship | P1 |
| Per-trade/daily caps | OFFLINE INERT | **Ship + set envs** | **P1** |
| Drift guard H2 | OFFLINE READY | Ship | P1 |
| Prod risk-budget H1 | OFFLINE READY | Ship | P1 |
| G1/G2 mechanical | OFFLINE READY | Ship | P1 |
| Slack alerting | OFFLINE READY | **Ship + set URL** | **P1** |
| Exploration execution | DEAD | **Remove** | P1 |
| Exp1A chop min-hold | LIVE EFFECTIVE | Keep | — |
| Exp2 inverse-ETF chop | LIVE EFFECTIVE | Keep | — |
| Exp3 observation | LIVE observation | Keep; do NOT ship Exp3B yet | P2 |
| Exp4 chop trail widen | OFFLINE REVERTED | **Un-revert + ship** | **P0 (edge)** |
| Take-profit exit | LIVE NEW | Keep + monitor | — |
| Reconciliation hard | LIVE | Keep | — |
| Split persistence | LIVE | Keep | — |
| Manifest guard (F) | LIVE | Keep | — |

— End of Organism Feature Status —
