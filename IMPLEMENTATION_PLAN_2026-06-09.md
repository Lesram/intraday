# Implementation Plan — Audit Remediation & Edge Program
**Date:** 2026-06-09 · Companion to `AUDIT_2026-06-09_FULL_PLATFORM.md` · Phases map to the go-live gates (report §9).

> **STATUS (2026-06-10): ALL PHASES EXECUTED — see `PHASE_COMPLETION_REPORT_2026-06-10.md`.** Phases 0–2 fully complete and tested (96 new tests + 267 regression, green). Phase 3 code + experiment harness complete; full experiment runs are a one-command overnight job on the host (`python scripts/edge_experiments.py`). Phase 4 safe subset done; settings consolidation and live_engine decomposition deferred to a supervised maintenance window. 3.4 (ORB at scale) blocked on a market-data subscription decision.
>
> **STATUS (2026-06-09): Phase 0 COMPLETE.** All six fixes (0.1–0.6) implemented and tested — 44 new tests in `tests/test_audit_0_*.py`, all green, no regressions in related suites. 0.6 root cause identified: load() ran lockless against save()'s non-atomic file-by-file swap; fixed with shared locking + a `.save_complete` sentinel. NOTE for operator: `.env` now sets `TRADING_EXECUTION_MODE=paper` explicitly (missing env var now fails closed to shadow) and `ORGANISM_MAX_DAILY_LOSS=1100` (was 5500). Restart the backend to pick these up, and run the full test suite on the host (some tests need postgres/alembic/macOS paths unavailable in the audit sandbox).

**Ground rules for every change:** (1) 62 test files pin source via `inspect.getsource` — run the full suite after each edit to `live_engine.py`/settings and update guard markers in the same commit; (2) every fix lands with a test that fails on the old behavior; (3) no change to live trading behavior without a replay run before/after.

---

## Phase 0 — Safety-critical fixes (Gate 0, ~3–5 working days)

**0.1 Secure the multi-strategy live path** — `backend/api/routes/multi_strategy_live.py:31`
- Add `Depends(require_admin)` to `run-once` (same pattern as `organism/routes.py:40`).
- Wire the kill switch: in `services/multi_strategy_live_runner.py`, check `governance.halt_trading` state before `plan_and_submit` (`:240`) — halt must cover *every* execution path.
- Tests: unauthenticated POST → 401/403; halted governance → no order submitted.

**0.2 Same-holdout model promotion in production** — `backend/organism/background_trainer.py:143–167`
- Persist old clf/reg artifacts (joblib paths already exist in `organism_brain/`) and pass them to the worker; score both models on the new model's cached val set via `evaluate_external_clf_reg` (`ml_signal.py:329–354`), mirroring the sync path (`continuous_learner.py:491–556`).
- Where artifacts are unavailable, call `acceptance_gate(..., allow_relative=False)` — absolute bar only. Flip the default of `allow_relative` (`continuous_learner.py:43`) to `False`.
- Tests: stale-baseline promotion rejected; same-holdout path promotes only on identical val data.

**0.3 Fail-closed risk defaults** — `backend/organism/live_engine.py:235–236`, `backend/config/settings.py:458`
- At engine start, if execution mode is `execute` and (`MAX_DAILY_LOSS<=0` or `MAX_NOTIONAL_PER_TRADE<=0`): refuse to start (hard error), don't trade unguarded.
- Change `trading_execution_mode` fallback: missing/unrecognized env → `shadow`, never `execute`.
- Set `ORGANISM_MAX_DAILY_LOSS=1100` (≈1% of equity) in `.env` and `.env.production.template`.
- Tests: startup aborts with breakers at 0 in execute mode; missing env → shadow.

**0.4 EOD flatten escalation** — `live_engine.py:2281–2291, 3146–3178`
- On flatten failure: keep retrying past 16:00 (extended-hours close or queue market-on-open), emit a CRITICAL alert through `backend/infra` alerting (Slack/page), and persist an `overnight_position` flag.
- On next session start: if flag set, force-exit at open before any new entries.
- Tests: simulated broker reject during 15:58–16:00 → alert fired + retry persisted + next-open exit.

**0.5 Pyramid gating + idempotency keys** — `live_engine.py:3368–3416, 5571–5584`
- Route adds through `_passes_entry_gates` (liquidity/fitness/sector), not just ban + global block.
- Extend idempotency keys with intent (`entry|pyramid|exit`), side, and qty.
- Tests: sector-capped symbol can't receive adds; same-tick entry+pyramid both survive dedup.

**0.6 Root-cause brain corruption** — `organism_brain/corrupt_head_20260609_*`
- Diff the 5 snapshots against backups to identify the failing writer; convert all brain writes to atomic write-temp-fsync-rename with a checksum in `manifest.json`; verify checksum on load.
- Test: kill -9 during save → next load recovers cleanly, no corrupt head.

**Exit criterion:** all six landed, full test suite green, one clean paper session.

## Phase 1 — Honest instrumentation (Gate 1, ~1–2 weeks)

**1.1 Costed replay defaults** — `replay_simulator.py:88–135, 344–356, 807`
- Default `next_bar_open` fills; add per-symbol-class half-spread (ETFs ~0.5bps, large-cap ~1bps, rest ~2.5bps) + slippage + commission; CLI flags to override. Re-baseline: rerun `backtest_exp5` and record the costed numbers.

**1.2 Walk-forward on the live scanners** — `walk_forward.py`
- Replace the legacy strategy set (`:39–46, 312–318`) with adapters that drive `ReplayEngine` over the organism scanners, so walk-forward validates what actually trades. Keep its purged slicing and cost model.

**1.3 Live edge monitor**
- New module + dashboard route: rolling 100-trade corr(predicted_return, actual_return), corr(confidence, correct), expectancy, PF — by entry_source and regime, from `trade_history.csv`/DB. Alert when corr ≤ 0 over a full window. (This is the §6 finding made permanent.)

**1.4 Startup config assert** — `live_engine.py` init
- Assert `LIVE_TIMEFRAME` matches enabled strategies' granularity (intraday scanners require `1Min`); log the full runtime risk snapshot (breakers, mode, timeframe) at start; fail on mismatch.

## Phase 2 — ML methodology repairs (parallel with Phase 1, ~1 week)

- **2.1** Purge/embargo in `_temporal_split` (`ml_signal.py:765–803`): drop H bars at the boundary.
- **2.2** Realized-correlation acceptance gate: new model must show corr(pred, actual) > 0 on the holdout *and* the live rolling window must be > 0 for the incumbent to stay (`continuous_learner.py:96–155`).
- **2.3** Route retrained artifacts through `PromotionController` shadow→canary (`promotion.py:349–395`) instead of direct swap (`background_trainer.py:585–596`).
- **2.4** Fix or retire `ensemble_model.py` scaler-on-all-data leakage (`:516–523`) — recommend retiring the path; it's secondary.
- **2.5** Evolution guardrails (`self_evolution.py:928–991, 554`): shorts re-enable requires ≥100 trades + Gate-2-style evidence, not a 10-trade EMA; sizing-scale changes pass a portfolio risk recheck before apply.

## Phase 3 — Edge program (Gate 2 evidence, starts after 1.1–1.2; ~2–6 weeks)

Ordered by expected value per unit effort, using data you already have:

- **3.1 Exit-logic experiment (highest priority).** A/B in costed replay: current stop/trail stack vs (a) time-based + retracement-fraction exits, (b) wider stops + partial scale-outs at 1R. Success metric: recover a meaningful share of the −$1,115 active-exit drag and cut the 63% MFE giveback. ~2–3 days once 1.1 lands.
- **3.2 Chop stand-down.** Regime gate that blocks alpha-composite entries in `chop`; replay + 20-session shadow. Your data: 364 chop trades ≈ $0 gross (negative net) — this is volume you pay costs on for nothing.
- **3.3 EOD cleanup.** Restrict continuation engine to SPY/QQQ (matches the literature); delete the single-name reversal engine; 60-session shadow with Gate 2 criteria.
- **3.4 ORB at proper scale (the medium-term edge bet).** Build the full-market minute-bar pipeline (needs a data subscription decision), daily in-play filter (top-20 by RV/news from ~1000 names), convex exits (trail to EOD, no fixed target). Implement Phase-C simulation from `ORB_PROMOTION_CRITERIA.md` honestly — measure, don't borrow the paper's Sharpe. ~3–4 weeks including data plumbing.
- **3.5 Mean-reversion: park it.** Net-negative after costs (report §7). Revisit only if 3.1's exit work changes the cost/edge ratio; do not re-tune parameters on the same windows again.

Each experiment graduates only via Gate 2: ≥60 sessions, net expectancy > 0 with t ≥ 2 after costs, PF ≥ 1.3, stable across two sub-periods.

## Phase 4 — Structural debt (background work, no gate dependency)

- **4.1** Consolidate the dual settings systems into one (`config/base_settings.py` vs `config/settings.py`); delete shadowed flat modules (`backend/database.py`, `backend/infra/repositories.py`), empty packages, stale env backups. Make `requirements.lock` authoritative in Docker builds.
- **4.2** Decompose `live_engine.py` along the five seams (Entry/Exit orchestrators, LearningManager, BrainPersistence, FeatureFeeder) — one seam per PR, updating structural-guard tests in lockstep, replay-diff before/after each.
- **4.3** Repo hygiene: move 30 root status reports to `docs/archive/`, prune `organism_brain_archive/` to 7 days (`scripts/cleanup_safe.sh` exists).

## Sequencing summary

```
Week 1      Phase 0 (all six fixes)                      → Gate 0 ✓
Weeks 2–3   Phase 1 (instrumentation) + Phase 2 (ML)     → Gate 1 ✓
Weeks 3–8   Phase 3 experiments (3.1 → 3.2 → 3.3, 3.4 in parallel)
Ongoing     Phase 4 structural debt
Go-live     Only when a strategy passes Gate 2 and the book passes Gates 3–4
```

Honest caveat on timelines: Phases 0–2 are deterministic engineering and will land on schedule. Phase 3 is research — the gates guarantee you won't go live on noise, but not that an edge will be found by a given date. The exit-logic and chop fixes (3.1, 3.2) are the most likely near-term wins because they're supported by your own trade data rather than hope.
