# Track Z4 v7 — Closure Regression Sweep (Waves 20-22)

Verify every fix shipped in waves 20-22 still holds; same-class scans clean.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d44eace`.

## Scope

| Wave | Findings | Commit |
|---|---|---|
| 20a | V-T-1 (order_service._trip dispatch_alert), V-T-2 (bg_trainer.get_result dispatch_alert) | 643ba6d |
| 20b | live_engine:6265 + X-2/3/4/8 (wall-clock leaks via _now_fn/_time_fn) | 643ba6d |
| 20c | X-1 (replay_simulator eager load_dotenv) | 643ba6d |
| 20d | X-5/X-6 (replay attr-loop _now_fn vs _time_fn fix; promotion_controller dropped) | 643ba6d |
| 20e | V-T-3 (ORGANISM_EXITS_SKIPPED_NO_DATA HELP/emission alignment) | 643ba6d |
| 21 | V-T-4 (outbox alerts), V-T-6 (C1 watchdog alert), V-T-7 (orphan adoption alert), T2 hypothesis pin in requirements.txt, U-1/U-2 marker backfill, Wave-18 behavioral test backfill (8 tests) | 8430bf6 |
| 22 | V-T-5 (DB startup CRITICAL alert), V-T-9 (feature_engineer + performance log demotion), X-7 (brain_dir defense + ORGANISM_REPLAY_MODE), regime.py:589 (DriftDetector now_fn), CI determinism smoke (6 tests) | 3baefb4 |

## Method

1. **Per-finding verification**: for each closed ID, run a verification grep.
   - V-T-1: `grep "Wave-20a" backend/services/order_service.py` ≥1; absence of live `get_running_loop()` call inside `_trip`.
   - V-T-2: `grep "Wave-20a" backend/organism/background_trainer.py` ≥1.
   - V-T-3: `grep "Wave-20e" backend/organism/live_engine.py` ≥1; HELP text now says "Safety-net exits" not "Exit checks fell back".
   - X-1: `grep "load_dotenv" backend/organism/replay_simulator.py` shows eager call at module level.
   - X-2/3/4/8: route through `_now_fn`/`_time_fn`; `grep "datetime.now(UTC)" backend/organism/live_engine.py` should show only display sites.
   - X-7: `grep "ORGANISM_REPLAY_MODE" backend/organism/live_engine.py` ≥1.
   - V-T-4..V-T-7: alert wiring sites use `dispatch_alert_from_thread`.
   - V-T-9: `grep "self.logger.info" backend/features/feature_engineering.py` should be 0 hits.
   - regime.py:589: `DriftDetector.__init__` accepts `now_fn`.

2. **Same-bug-class scan**:
   - `grep -rn "asyncio.run(send_alert\|asyncio.run(_emit\|_aio.run(_emit" backend/` — should be 0 (all alert sites moved to dispatcher).
   - `grep -rn "datetime.now(UTC)\|datetime.utcnow()" backend/organism/` — should reveal only display sites.
   - `grep -rn "time.time()" backend/organism/` — should show no decision-affecting calls.
   - `grep -rn 'opts\["timeout"\]' backend/data/alpaca_client.py` — wave-18 timeout wrapper still present.
   - `grep -rn "round(t.pnl, 2)" backend/` — should be 0 in writer paths (B-T-2 still closed).

3. **Test suite**: run touched suites
   (alert_cross_thread_dispatch, replay_clock_injection, rc_1_5_curated, ferrari_v1_fixes, replay_simulator_errors, numerical_properties_v6, remediation_wave_a, audit_patch_queue_j6, j6b, algorithm_improvements, wave18_behavioral_backfill, ci_determinism_smoke). Expect ≥165 pass.

4. **Brain coherence**: gen=168, trades=498, ml_is_trained=true unchanged.

5. **Live in-container check**: probe `/metrics` endpoint, the alert-dispatcher
   from a synthetic worker thread, and the `cumulative_pnl reconciles` startup log.

## Output

`artifacts/audit/v7_reports/track_z4_closure_regression.md` with:
- Per-finding verification table
- Same-bug-class scan deltas
- Test-suite delta
- "Regressions found: N" + TL;DR

## Quality bar

Expect 0-2 regressions.

End with one-paragraph summary.
