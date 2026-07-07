# Phase 3 Task 3 (5c) — Selector routing design (implementation contract)

Governing acceptance: `INTRA_2.0_FINAL_BUILDOUT_PLAN.md` Task 3. This document
pins the line-level facts and the staged implementation so the work is
mechanical and reviewable.

## Engine facts (live_engine.py @ b518622, 7,707 lines)

**Production call sites (to be unified):**
- `_scan_entry_candidates` (2583–2625): the Phase-1 thin seam. Flag off ⇒
  inline `alpha_scanner.scan(...)`; flag on (`FRAMEWORK_ROUTING_ENABLED` +
  `DROP_ML_FROM_GATE`) ⇒ framework re-sources DIRECTION only, with the
  `FRAMEWORK SEAM MISMATCH` tripwire. Called at ~3967.
- ORB shadow scan (2892–2939) → `self._latest_orb_triggered`.
- EOD shadow scan (2945–2962) → `self._latest_eod_candidates` (PARKED — stays).
- MR shadow scan (2968–2987) → `self._latest_mr_candidates`.
- `breakout_scanner.scan` (~3957) → `breakout_signals`.

**cand_dicts convergence (shared downstream starts at sort, 4832):**
- Alpha build (~4164–4292): two-tier confidence gate — `_eff_conf =
  0.65*breakout + 0.35*min(tension,1)` when `DROP_ML_FROM_GATE and not
  learning` (else composite); reject `< _EXPL_CONF_GATE`; exploration-route
  (log-and-skip) `< _MIN_MAIN_CONF`; heuristic expected-return main-book rules.
  Dict: symbol, direction, predicted_return(+signed, ml_spoke,
  ml_raw_confidence), confidence, effective_confidence, breakout_score,
  expected_return_source, **ranking_score = c.composite_score**, exp3 fields.
- Pure breakout (4294–4395): cap `_MAX_PURE_BREAKOUT=2`, not-in-alpha,
  composite ≥ 0.55, shared `_passes_entry_gates`, `_bo_conf ≥ _MIN_MAIN_CONF`,
  production ML-negative veto, pred_ret = ML if (dir>0, |pr|>1e-4) else
  `0.005 + 0.015*composite`; **ranking_score = composite × conf**; forced
  direction 1.0.
- ORB live block (4397–~4560): flag `ORB_LIVE_ENABLED`, cap `_MAX_ORB_PER_TICK=2`,
  inverse-ETF translation (`_translated`), **ranking_score = composite ×
  rv_ratio**, extras orb_high/orb_low/orb_suggested_stop/rv_ratio,
  `entry_source_override = "orb_sip"|"orb_sip_inverse"`, `mark_fired`.
- EOD live block (4564–4713): flag `EOD_LIVE_ENABLED` — PARKED, leave as-is.
- MR live block (4721–4830): flag `MEAN_REVERSION_LIVE_ENABLED`,
  **ranking_score = composite × abs_distance_atr**, breakout_score=0.5,
  extras mr_vwap/mr_target_price/mr_stop_price/mr_distance_atr/mr_expected_r_r,
  `entry_source_override="mean_reversion"`, `mark_fired`.
- Shared tail (4832+): sort by ranking_score desc → open-slots cap →
  2-per-tick cap → hourly/burst caps → defensive filter → sizing (~4913).

## The two design decisions

**D1 — Stage the behavior change.** 5c lands in two commits:
- **Commit A (structural, provably inert):** `selector.scan_all()` produces
  per-strategy candidates; per-strategy ADAPTERS convert Candidate → the exact
  cand_dict each inline block builds today (same gates, same caps, same
  ranking_score formulas, same mark_fired/telemetry). Behind new env
  `ORGANISM_FRAMEWORK_ROUTING_V2` (default OFF). Acceptance: engine-level A/B
  replay flag-on vs flag-off is IDENTICAL (extends verify_seam_parity.py),
  because every adapter replicates its inline block and each strategy's
  live_routing flag mirrors its LIVE_ENABLED env default.
- **Commit B (the intended change, Task-4 adjacent):** ranking axis switches to
  the 5b-shipped confidence (flat ⇒ Task-4 declarative tie-break), attribution
  tags (strategy+regime) stamp every trade, non-routed strategies stream
  shadow-attribution rows into the forward corpus. Acceptance: per-strategy
  replay ↔ backtester trade-for-trade reconciliation (entered set, direction,
  size, exit reason) — the plan's Task-3 gate — NOT flag-on==off.

**D2 — Selector authority vs engine gates.** The selector owns candidate
PRODUCTION + regime eligibility (Rule A: live_routing gate). The engine keeps
ALL capital-safety gates (entry gates, caps, burst, risk budget, defensive
filter, sizing) — "everything downstream is shared and identical". Confidence
semantics under flat: the composite no longer gates entries by design;
caps/risk-budget/liquidity/fitness gates remain the binding constraints.

## Rule-A / flag mapping (Commit A parity requirement)

| strategy | framework live_routing | engine env today | routed-in-A? |
|---|---|---|---|
| momentum | true | (always on) | yes — via alpha adapter (direction authority as thin seam) |
| breakout | true | (always on, cap 2) | yes — pure-breakout adapter |
| mean_reversion | false | MEAN_REVERSION_LIVE_ENABLED=false | only if env true (adapter honors env, exactly like inline) |
| orb | false | ORB_LIVE_ENABLED=false | only if env true |
| eod | not registered | EOD_LIVE_ENABLED=false | NO — inline block stays until revival |

## Files
- `backend/organism/strategy_selector.py`: add `scan_all(features, regime, now)
  -> dict[strategy_name, list[Candidate]]` (live mode: all registered, tagged
  with routed/shadow per Rule A — shadow lists returned for attribution, never
  converted to cand_dicts).
- `backend/organism/live_engine.py`: `_scan_entry_candidates_v2()` +
  per-strategy `_adapt_<name>_candidate()` helpers OUTSIDE `_live_tick_inner`
  (LOC ceiling 2807 for `_live_tick_inner` respected); inline blocks branch on
  the v2 flag. Inline scanner deletion happens only after Commit B's
  reconciliation is green (plan: "keep briefly behind the flag, then delete").
- `scripts/verify_routing_v2_parity.py`: Commit-A gate (A/B identical).
- `scripts/verify_strategy_reconciliation.py`: Commit-B gate (replay ↔
  backtester per strategy).
- `tests/test_routing_v2.py`: candidate-level adapter equivalence probes +
  tripwire teeth.

## Why not one big cutover
The inline blocks embed 20+ audit-hardened micro-decisions (ML veto, pred_ret
floors, translated inverse ETFs, mark_fired bookkeeping). A single cutover that
also changes the ranking axis would make any replay diff unattributable —
structure change and behavior change must be separable evidence.
