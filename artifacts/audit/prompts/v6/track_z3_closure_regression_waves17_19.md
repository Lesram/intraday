# Track Z3 v6 — Closure Regression Sweep (Waves 17-19)

Verify every fix shipped in waves 17-19 still holds in the running container,
AND scan for new instances of the same bug class.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `3f660f4`.

## Scope (waves 17-19)

| Wave | Findings closed | Commit |
|---|---|---|
| 17a | S-J3-1 (cross-thread alert dispatch) | 9bcbe8b |
| 17b | U-RF4 + U-3/U-4/U-5 (replay clock-injection: live_engine.py:2064 + RegimeDetector + GovernanceController) | 08ee62f |
| 17c | S-WS-GAP-1 (gap-fill terminal id repop) | 610aeb0 |
| 17d | B-T-2 (cumulative_pnl 6dp + load-time reconciliation) | 610aeb0 |
| 18 | B-T-1 (DB-replay direction), S-NET-CB-1 (broker circuit breaker), S-NET-T-1 (alpaca-py timeouts), S-OUTBOX-1 (lease 30min), B-T-7 (Kelly atr_var refuse-to-size), B-T-3 (_safe_int_qty helper) | a42ca5f |
| 19 | U-1, U-2, U-6, U-7 (remaining bypass sites), B-T-4 (streaming_data_provider time_fn), B-T-5 (walk_forward Sharpe std=0), S-CLK-1 (drawdown monotonic), S-DISK-1 (atomic JSON writes) | 0ea2695 |

## Method

1. **Per-finding verification**: for each closed ID, run a verification grep / curl /
   file-check / pytest. Examples:
   - **S-J3-1**: `docker logs intra-api-1 | grep "Main event loop captured"` ≥1.
     `grep "dispatch_alert_from_thread" backend/` ≥3 (the 3 patched sites).
     Run `pytest tests/test_alert_cross_thread_dispatch.py -q` → 4/4.
   - **U-RF4**: `grep "self._now_fn().astimezone(UTC).strftime" backend/organism/live_engine.py` ≥1 at the bar-boundary site.
   - **U-3**: `grep "self._now_fn()" backend/organism/regime.py` ≥5 (the 5 RegimeDetector sites).
   - **U-4**: `grep "self._now_fn()" backend/organism/governance.py` ≥3.
   - **U-6**: `grep "self._now_fn()" backend/organism/promotion.py` ≥4.
   - **U-7**: `grep "self._now_fn()" backend/organism/continuous_learner.py` ≥2.
   - **S-WS-GAP-1**: `grep "S-WS-GAP-1" backend/integrations/alpaca_stream.py` ≥1; behavioral test in `tests/test_remediation_wave_a.py`.
   - **B-T-2**: `docker logs intra-api-1 | grep "cumulative_pnl reconciles"` should show one log line at startup with drift in tolerance. Verify CSV pnl rows now use 6dp by inspecting the most recent trade row.
   - **B-T-1**: `grep "_en_side\b\|_direction" backend/organism/live_engine.py` near the DB-replay path; assert the hard-coded `direction=1.0` is gone.
   - **S-NET-CB-1**: `grep "get_or_create_circuit_breaker" backend/integrations/alpaca_broker.py` ≥1; `grep "alpaca_broker_http" backend/` ≥1.
   - **S-NET-T-1**: `grep "_one_request" backend/data/alpaca_client.py` should show the wrapper.
   - **S-OUTBOX-1**: `grep "_CLAIM_LEASE_SECONDS = 1800" backend/infra/outbox.py` ≥1.
   - **B-T-7**: `grep "_ATR_VAR_MIN" backend/organism/kelly_sizer.py` ≥1.
   - **B-T-3**: `grep "_safe_int_qty" backend/organism/live_engine.py` ≥1.
   - **U-1, U-2**: `grep "datetime.now(UTC)" backend/organism/live_engine.py` should show no idempotency-key sites left (telemetry direct calls remain — out of scope for U-1/U-2 which were idempotency-key only? — verify by reading the prompts).
   - **B-T-4**: `grep "self._time_fn()" backend/organism/streaming_data_provider.py` ≥6.
   - **B-T-5**: `grep "len(daily_pnls) <= 1" backend/organism/walk_forward.py` ≥1; assert no `std=1.0` fallback remains.
   - **S-CLK-1**: `grep "_drawdown_triggered_monotonic" backend/organism/governance.py` ≥3.
   - **S-DISK-1**: `grep "tmp_path.replace(path)" backend/organism/brain_persistence.py` in `_write_json` body.

2. **Same-bug-class scan**:
   - `grep -rn "asyncio.create_task(send_alert" backend/` outside `dispatch_alert_from_thread` should be 0 (S-J3-1 class).
   - `grep -rn "datetime.now(UTC)\|datetime.utcnow()" backend/organism/` should reveal only display sites (telemetry, log timestamps) — not decision-affecting calls.
   - `grep -rn "time.time()" backend/organism/` should show no decision-affecting calls.
   - `grep -rn "max(.*1e-6)" backend/organism/` (B-T-7 class).
   - `grep -rn "round(t.pnl, 2)" backend/` (B-T-2 class).
   - `grep -rn "open(.*\"w\"" backend/organism/brain_persistence.py` outside the atomic helper (S-DISK-1 class).
   - `grep -rn "direction=1.0" backend/organism/` (B-T-1 class — hard-coded direction).

3. **Test suite delta**: run the full curated subset
   (test_rc_1_5_curated, ferrari, replay_simulator_errors, algorithm_improvements,
   audit_patch_queue_j6, j6b, remediation_wave_a, alert_cross_thread_dispatch,
   replay_clock_injection, quote_manager_extended/comprehensive,
   cache_service_extended/comprehensive, redis_ha). Expect ≥260 pass; report
   any new failures.

4. **Brain coherence check**: snapshot manifest now; should match
   gen=168, trades=498, ml_is_trained=true (or have moved forward via total_runs only).

5. **Deploy artifacts**: confirm wave 17a, 17b, 17cd, 18, 19 deploy bundles
   exist with PRE/POST snapshots.

## Output

`artifacts/audit/v6_reports/track_z3_closure_regression.md` with:
- Per-finding verification table (ID × command × verdict × notes)
- Same-bug-class scan results (pattern × current count × delta from fix-commit baseline)
- Test-suite delta
- Brain-coherence delta
- Any regression discovered
- "Regressions found: N" + TL;DR

## Constraints

Read-only. `docker exec` reads, `curl` no-mutation, `pytest` ok.

## Quality bar

Expect 0-2 regressions. >2 means waves 17-19 didn't hold and an emergency wave
is needed before further audit work.

End with one-paragraph summary.
