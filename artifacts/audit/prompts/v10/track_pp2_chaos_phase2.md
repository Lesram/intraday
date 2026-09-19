# Track PP2 v10 — Chaos Phase 2

V9 PP found 6 chaos findings (3 Critical, 3 High); wave-41 closed PP-1 (atomic save), PP-2 (backup fallback), PP-3 (alert escalation), PP-4 (DB-down halt). Wave-46 closed TT-2 (tick watchdog). **PP2 verifies these fixes actually work under simulated failure** — not just that the code is in place.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `35a1fe9`.

**SCRATCH-ONLY for chaos drills.** Use a copy of `organism_brain/` in `/tmp/pp2_sandbox/` for SIGKILL drills; never touch production state.

## Method

### 1. PP-1 atomic save under SIGKILL

Setup:
```
mkdir -p /tmp/pp2_sandbox
cp -r organism_brain /tmp/pp2_sandbox/brain_test
```

Test:
- Build a minimal Python script that calls `OrganismBrain(brain_dir="/tmp/pp2_sandbox/brain_test").save(...)` with a large data set.
- Run it in a subprocess.
- After 100ms, send SIGKILL.
- After SIGKILL: check whether `manifest.json`, `equity_curve.csv`, `epoch_metrics.csv`, `reference_feats.csv` are either FULL or untouched (atomic).
- Look for any `.tmp` files left over.

Document: under SIGKILL, do we leave .tmp files orphaned? Does next load() pick up the previous-good state?

### 2. PP-2 backup fallback under simulated corruption

Setup:
- Take `/tmp/pp2_sandbox/brain_test/manifest.json`.
- Corrupt it (`echo "not json" > manifest.json`).
- Ensure backups/ has at least 1 valid snapshot.

Test:
- Call `OrganismBrain(...).load()`.
- Assert: returns True (backup loaded).
- Assert: `manifest.generation` matches the backup's generation.
- Assert: HEAD manifest is NOT silently overwritten — operator must know to recover.

### 3. PP-2 with no usable backup

Setup:
- Corrupt manifest.json.
- Move backups/ aside (or delete).

Test:
- Call `load()`.
- Assert: returns False, logs CRITICAL.
- Operator alert dispatched? (Verify via mock alerting.)

### 4. PP-3 alert escalation: CRITICAL bypasses dedup

Verify in code (already structurally tested wave-41) AND simulate:
- Build a stub AlertManager with a saturated dedup window (10 entries marked "send").
- Call `send_alert` with severity=CRITICAL.
- Assert it bypasses dedup and attempts delivery.

### 5. PP-3 last-resort logger.critical when ALL channels fail

Mock `_send_slack` and `_send_pagerduty` to both fail.
- Call `send_alert` with severity=CRITICAL.
- Assert `logger.critical("ALERT-DELIVERY-FAILED")` fires.

### 6. PP-4 dev-mode DB-down requires ALLOW_NO_DB

Verify lifespan startup behavior:
- With `APP_ENVIRONMENT=development` and DB unreachable: should raise.
- With `ALLOW_NO_DB=1`: should warn + continue.
- Sandbox: spin up uvicorn with bad DATABASE_URL, observe.

### 7. TT-2 tick watchdog under hung mock

Already structurally tested in wave-46. Concrete drill:
- Mock `_live_tick_inner` to sleep 60s.
- Set `_TICK_WATCHDOG_SECONDS` to 0.5.
- Call `live_tick()` 3 times.
- Assert: each returns degraded LiveTickResult within ~0.5s; counter increments.

### 8. UU-1 daily-max-loss alert under worker-thread context

Verify the wave-41 UU-1 fix works when called from a thread (not the main event loop):
- Use `asyncio.to_thread` to call a function that triggers the alert path.
- Assert dispatch_alert_from_thread captures the main loop ref.

### 9. Stream reconnect storm

The TT-2 finding said "1987s outlier co-located with WS keepalive timeouts." Drill:
- What is the stream reconnect backoff schedule?
- Under continuous reconnect failures, does the engine drop to a degraded mode?
- Is there a max-retry circuit breaker?

### 10. New chaos vectors V10 should test next round

Identify chaos drills not yet covered:
- Disk full mid-save (different from SIGKILL).
- File-descriptor exhaustion.
- DNS failure on broker.alpaca.markets.
- Race: two concurrent ticks (single-threaded async, but verify the lock holds).

## Output

`artifacts/audit/v10_reports/track_pp2_chaos_phase2.md` with per-drill outcomes (PASS / FAIL / SKIP), severity tags, and recommended drills for V11.

Quality bar: 1-3 findings. Drills should mostly PASS (V9 wave-41 fixes are well-tested); any FAIL is a NEW chaos finding.
