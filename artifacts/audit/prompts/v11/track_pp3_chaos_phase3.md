# Track PP3 v11 — Chaos Phase 3 (Real SIGKILL + Network Partition)

V10 PP2 found PP2-1 (PP-4 wrong gating). Wave-51 fixed it. **PP3 actually executes SIGKILL drills + network partition simulations** to verify wave-41-51 atomic save / backup fallback / watchdog work end-to-end.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`.

**SCRATCH-ONLY.** All chaos drills run in `/tmp/pp3_sandbox/`. NEVER touch the live container or production state.

## Method

### 1. SIGKILL during atomic save

Setup:
```
mkdir -p /tmp/pp3_sandbox
cp -r organism_brain /tmp/pp3_sandbox/brain_test
```

Drill:
- Spawn a Python subprocess that calls `OrganismBrain.save(...)` with a real-sized payload.
- After 100ms, send SIGKILL.
- Check `/tmp/pp3_sandbox/brain_test/`:
  - manifest.json: full or untouched?
  - .tmp orphans: present?
- Subsequent `OrganismBrain(...).load()`: returns True (success), False (no backup), or restored from backup?

Expected post-wave-41 PP-1/PP-2: HEAD survives via atomic write OR backup fallback restores cleanly.

### 2. SIGKILL with 5 backups present

Setup with 5 prior backups in `/tmp/pp3_sandbox/brain_test/backups/`:
- Corrupt manifest.json (`echo "not json"`).
- Run `load()`.
- Verify: returns True, gen=N from latest backup, corrupt-HEAD captured to `corrupt_head_*` directory (wave-56 PP2-2).

### 3. Repeated SIGKILL stress (10x)

Loop: SIGKILL during save 10 times. Check that `.tmp` orphans are swept on next save() (wave-56 PP2-3).

### 4. WW-1 backup cadence verification

After 5 successive `save_essential_state()` calls within 1 hour, count backups/. Should be ≤ 1 (cadence-gated by WW1_BACKUP_INTERVAL_SECONDS).
After 5 calls spread over 5+ hours, count should be 5.

### 5. TT-2 watchdog drill against hung mock

Mock `_live_tick_inner` to `await asyncio.sleep(60)`. Set `_TICK_WATCHDOG_SECONDS=0.5`. Verify:
- `live_tick()` returns degraded LiveTickResult after ~0.5s.
- `_tick_watchdog_timeouts` increments.
- Operator alert dispatched (mock alerting backend, verify call).

### 6. PP2-1 outer-block SELECT 1 verification

Spin up uvicorn against an unreachable DB URL. Verify:
- With `ALLOW_NO_DB=1`: warns + continues.
- Without it: exits with PP-4 RuntimeError.

### 7. Network partition: broker timeout

Mock `submit_order` to sleep 30s. Verify the watchdog catches the tick before the broker call times out, OR the broker path has its own timeout.

### 8. Disk-full mid-save

Set up a small tmpfs of 100KB. Try `save()` with > 100KB payload. Expected: caught exception logged, in-memory state preserved.

### 9. Restart while writing

Spawn save() subprocess; send SIGTERM (graceful) at 100ms. Check:
- Save completes IF SIGTERM is intercepted by the lifespan shutdown handler.
- Otherwise SIGKILL would leave .tmp; SIGTERM should clean.

### 10. Audit chain integrity post-restart

After 3 restarts, query the live audit_logs hash chain via `verify_chain()`. Should remain valid.

## Output

`artifacts/audit/v11_reports/track_pp3_chaos_phase3.md` with PASS/FAIL per drill, severity tags.

Quality bar: 1-3 findings. Most should PASS (V10/V11-prep fixes are well-tested); FAILs reveal gaps.
