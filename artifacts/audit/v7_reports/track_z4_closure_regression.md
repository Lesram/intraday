# Track Z4 v7 — Closure Regression Sweep (Waves 20-22)

**Repo**: /Users/marselkei/VS/intra
**Branch**: rc-1.5-curated @ `d44eace`
**Container**: intra-api-1 (Up 22 min, healthy)
**Run date**: 2026-05-02 (UTC tick from container: 2026-05-03T04:00Z)
**Method**: Read-only verification per prompt v7 track_z4_closure_regression_waves20_22.md.

## TL;DR

**Regressions found: 0** of the closures shipped in waves 20a / 20b / 20c / 20d / 20e / 21 / 22. Every per-finding marker grep produced ≥1 hit at the expected site, the same-bug-class scans came back clean (0 stray `asyncio.run(send_alert)`/`asyncio.run(_emit)`/`_aio.run(_emit)` matches; 0 `self.logger.info` in `feature_engineering.py`; the only remaining `time.time()` site in `live_engine.py` is now an in-comment forensic note next to the wave-20b clock-injection fix), the touched test bundle ran 167/167 green (≥165 bar), and brain coherence is gen=168 / total_trades=498 / ml_is_trained=true matching the prompt's expectation. Live container probes confirmed (a) the V-T-3 HELP text now reads "Safety-net exits…" not "Exit checks fell back…", (b) the cross-thread alert dispatcher round-trips a coroutine from a synthetic worker thread, and (c) the `cumulative_pnl reconciles` startup log fires as expected.

---

## 1. Per-finding verification table

| Wave | Finding | Site / grep | Status | Evidence |
|---|---|---|---|---|
| 20a | V-T-1 | `backend/services/order_service.py:364` Wave-20a marker; no live `get_running_loop()` inside `_trip` (only in-comment); `dispatch_alert_from_thread` used at line 378-389 | PASS | `_trip` rebuilt around `dispatch_alert_from_thread`; the two remaining `get_running_loop`/`asyncio.run` hits in this file are in the deprecated sync `submit_order()` (lines 989/1026), out of V-T-1 scope |
| 20a | V-T-2 | `backend/organism/background_trainer.py:435` Wave-20a marker; `dispatch_alert_from_thread` at line 446 | PASS | "ML Retrain Failed" alert now dispatched from any caller thread |
| 20b | live_engine clock injection | `_now_fn`/`_time_fn` defined at line 695-696; tick fix at 1505 (`Wave-20b X-2`); 3958 (`Wave-20b X-2`); 6365 (`Wave-20b W-finding/X-4`) | PASS | The remaining `datetime.now(UTC)` calls in `organism/live_engine.py` (lines 696 default, 2150 in-comment, 5859/5868 inside `force_save_brain` display payload) are all permitted display sites |
| 20c | X-1 | `backend/organism/replay_simulator.py:34-45` eager `load_dotenv()` at module scope | PASS | Eager call confirmed — `_load_dotenv()` invoked unconditionally inside `try:` at module init |
| 20d | X-5 / X-6 | `backend/organism/replay_simulator.py:537-565` Wave-20d block | PASS | Explicit `_now_fn_components`/`_time_fn_components` mapping; `promotion_controller` removed from the loop; brain added to `_now_fn` set |
| 20e | V-T-3 HELP alignment | `backend/organism/live_engine.py:121-132` Wave-20e marker; HELP="Safety-net exits triggered when no features were available (15%-loss broker-price-only fallback)" | PASS | Live `/metrics` returns identical HELP text; emission site at line 2109 is the `safety_net_no_features` branch only |
| 21 | V-T-4 outbox alerts | `backend/infra/outbox_worker.py:163-186` Wave-21 marker, `dispatch_alert_from_thread` wired | PASS | Outbox loop errors fire `Outbox Dispatcher Error` WARNING |
| 21 | V-T-6 C1 watchdog | `backend/organism/live_engine.py:4402-4423` Wave-21 marker | PASS | "C1 Watchdog: System Inert" CRITICAL alert wired |
| 21 | V-T-7 orphan adoption | `backend/organism/live_engine.py:5348-5377` Wave-21 marker | PASS | "Orphan Position Adopted" INFO alert wired |
| 21 | T2 hypothesis pin | `requirements.txt:72-76` Wave-21 marker, `hypothesis>=6.70.0` | PASS | Pin in place |
| 21 | U-1 / U-2 marker backfill | `backend/organism/live_engine.py:4708, 4833` (`V5 U-1 / Wave-19` and `V5 U-2 / Wave-19`) | PASS | Both markers routed through `self._now_fn()` |
| 21 | Wave-18 behavioral test backfill | `tests/test_wave18_behavioral_backfill.py` | PASS | 8 tests collected and pass under the consolidated run |
| 22 | V-T-5 DB startup CRITICAL | `backend/api/lifespan.py:120-150` Wave-22 marker | PASS | CRITICAL alert dispatched on startup DB init failure regardless of env |
| 22 | V-T-9 feature_engineer / perf log demotion | `backend/features/feature_engineering.py:161, 353, 914, 941` Wave-22 markers; `backend/utils/logger.py:458` perf marker | PASS | `grep "self.logger.info" backend/features/feature_engineering.py` returns 0 hits |
| 22 | X-7 brain_dir defense + ORGANISM_REPLAY_MODE | `backend/organism/live_engine.py:523-547` Wave-22 marker; `backend/organism/replay_simulator.py:50` sets env | PASS | Replay-mode guard refuses production brain dir without override |
| 22 | regime.py:589 DriftDetector now_fn | `backend/organism/regime.py:584-594` `now_fn` parameter, default lambda for live use | PASS | Constructor signature accepts `now_fn`; `_now_fn` used in `check_drift` at line 602 |
| 22 | CI determinism smoke | `tests/test_ci_determinism_smoke.py` | PASS | 6 tests collected, all pass |

---

## 2. Same-bug-class scan deltas

| Scan | Expected | Result |
|---|---|---|
| `grep -rn "asyncio.run(send_alert\|asyncio.run(_emit\|_aio.run(_emit" backend/` | 0 | **0 hits** |
| `grep -rn "datetime.now(UTC)\|datetime.utcnow()" backend/organism/` | only display/default sites | All hits are either component-default lambdas, comments, in `force_save_brain` payload (display only), or in modules out of scope for waves 20-22 (`scheduler.py`, `governance.py`, `attribution.py`, `training.py`, etc.); `live_engine.py` decision sites all route through `_now_fn`/`_time_fn` |
| `grep -rn "time.time()" backend/organism/` | no decision-affecting calls in `live_engine.py` | `live_engine.py` shows **only** the in-comment forensic note at line 1506 ("Wall-clock `time.time()` polluted every per-tick hash in replay") next to the Wave-20b fix; `background_trainer.py` and `market_scanner.py` retain `time.time()` but those are per-process ML retrain/scanner timing, not per-tick decision inputs (out of waves 20b/22 scope) |
| `grep -rn 'opts\["timeout"\]' backend/data/alpaca_client.py` | wave-18 wrapper present | `backend/data/alpaca_client.py:193` — present |
| `grep -rn "round(t.pnl, 2)" backend/` | 0 in writer paths | 1 hit at `backend/organism/brain_persistence.py:1334` — **in a docstring/comment**, not a writer call. B-T-2 still closed |
| `grep -n "self.logger.info" backend/features/feature_engineering.py` | 0 | **0 hits** |
| `dispatch_alert_from_thread` wiring inventory | ≥7 sites (V-T-1, V-T-2, V-T-4, V-T-5, V-T-6, V-T-7, plus pre-existing wave-17a sites) | 9 wired call-sites across `outbox_worker`, `background_trainer`, `brain_persistence`, `live_engine` (3), `ml_signal`, `lifespan`, `order_service` |

---

## 3. Test-suite delta

```
$ ./venv/bin/python -m pytest \
    tests/test_alert_cross_thread_dispatch.py \
    tests/test_replay_clock_injection.py \
    tests/test_rc_1_5_curated.py \
    tests/test_ferrari_v1_fixes.py \
    tests/test_replay_simulator_errors.py \
    tests/test_numerical_properties_v6.py \
    tests/test_remediation_wave_a.py \
    tests/test_audit_patch_queue_j6.py \
    tests/test_audit_patch_queue_j6b.py \
    tests/test_algorithm_improvements.py \
    tests/test_wave18_behavioral_backfill.py \
    tests/test_ci_determinism_smoke.py \
    --timeout=60 -q --tb=line
```

**Result**: `167 passed, 1 warning in 2.12s` — exceeds the ≥165 bar. 0 fails, 0 errors, 0 xfails turning red.

---

## 4. Brain coherence

Read-only via `docker exec intra-api-1`:

| Field | Expected | Observed |
|---|---|---|
| generation | 168 | **168** |
| total_trades | 498 | **498** |
| ml_is_trained | true | **true** (`ml_state.json` `is_trained=True`, 79 features) |
| Brain artifacts present | yes | `ml_classifier.joblib`, `ml_regressor.joblib`, `ml_state.json`, `learning_state.json`, `evolved_params.json`, `equity_curve.csv`, `trade_history.csv`, `governance_state.json`, `regime_state.json`, `evaluation_event_history.json`, `extra_counters.json`, `manifest.json`, `reference_feats.csv` all dated 2026-05-03T04:00Z |

---

## 5. Live in-container probes

| Probe | Result |
|---|---|
| `GET /metrics` for `organism_exits_skipped_no_data_total` | Counter present, `0.0`, HELP="Safety-net exits triggered when no features were available (15%-loss broker-price-only fallback)" — matches Wave-20e wording exactly |
| Synthetic worker-thread `dispatch_alert_from_thread` | Returned `{'ok': True, 'ran': True}` — coroutine from non-loop thread reached the captured main loop and executed |
| `cumulative_pnl reconciles` startup log | Present: `cumulative_pnl reconciles: state=-634.92 csv_sum=-634.90 drift=$0.02 within tolerance` (logger=`backend.organism.brain_persistence`, function=`apply_to_learner`, line=575) |
| DB init startup log | `Database initialized successfully` — V-T-5 alert path is wired but did not trigger (expected: only fires on failure) |

---

## 6. Out-of-scope but noted (no regression)

- `backend/services/order_service.py:989, 1026` — `asyncio.get_running_loop()` and `asyncio.run()` remain inside the deprecated sync `submit_order()` shim. This is **out of V-T-1 scope** (V-T-1 was the `_trip` site only) and the function is gated by a `DeprecationWarning`. Worth tracking for a future wave, but not a Z4 regression.
- `backend/organism/runner.py`, `governance.py`, `scheduler.py`, `attribution.py`, `training.py`, `walk_forward.py`, `feature_store.py`, `diagnostic_scheduler.py`, `diagnostics.py`, `promotion.py`, `routes.py` still call `datetime.now(UTC)` directly. Wave 20b scope was explicitly `live_engine.py` + the X-2/3/4/8 sites; Wave 22 added `regime.DriftDetector`. These remaining sites are **out of waves 20-22 scope** and not regressions.
- `monitoring/memory_monitoring.json` is the only working-tree change vs `d44eace` (unrelated to waves 20-22).

---

## Summary

All seven closure waves (20a / 20b / 20c / 20d / 20e / 21 / 22) verify clean: every documented marker is present at the expected line, no live `get_running_loop()`/`asyncio.run(send_alert)` anti-patterns survive in the closed sites, the V-T-3 Prometheus HELP text emits exactly the post-Wave-20e wording from a running container, the cross-thread alert dispatcher demonstrably forwards coroutines from a synthetic worker thread to the captured main loop, the `cumulative_pnl reconciles` startup log fires with `drift=$0.02 within tolerance`, the consolidated touched-suite run passes 167/167 (above the ≥165 quality bar), and brain state on disk matches the prompt's gen=168 / trades=498 / ml_is_trained=true expectation. **Regressions found: 0.**
