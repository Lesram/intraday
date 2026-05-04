# Track WW v10 — Multi-Day Operational Soak (NEW LENS)

V8 OO recommended; V9 didn't ship. **WW exercises the platform under repeated restarts** to verify state survives. The audit cycle's history of "brain manifest gets reset on restart" bugs (V4 H-* findings) makes this lens a high-yield one.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `35a1fe9`.

**SCRATCH-ONLY.** Use a copy of `organism_brain/` for soak; never touch production.

## Method

### 1. 5x sequential restart soak

Setup:
```
cp -r organism_brain /tmp/ww_soak_brain
```

Sequence (run 5 times):
1. Snapshot `manifest.json` field values: `generation`, `total_trades`, `cumulative_pnl`, `best_sharpe`, `ml_is_trained`, `feature_count`, `peak_equity`.
2. Read brain via `OrganismBrain(brain_dir="/tmp/ww_soak_brain").load()`.
3. Modify trivially (e.g. add 1 to `total_trades`).
4. Save via `.save_essential_state(...)` (the path actually used).
5. Re-load. Compare snapshot to current.

Expected: every field invariant across the 5 cycles (modulo the 1-trade bump per cycle).

If any field resets to 0, NaN, or default: that's a state-loss finding.

### 2. Brain backup rotation

After 5 saves with `_create_backup` enabled, verify:
- `backups/` has rotation working (e.g. 5 most-recent).
- Oldest backups are deleted (no unbounded growth).

### 3. Atomicity under repeated SIGTERM

Sequence (3 times):
1. Spawn the live engine in a subprocess.
2. Send SIGTERM after 10s.
3. Verify graceful shutdown: brain saved cleanly, no `.tmp` files.

### 4. Pending-entry cleanup across restart

Pre-condition: brain has `pending_entry_order_ids = {"AAPL": "abc-123"}` in extra_counters.

Sequence:
1. Save brain.
2. Restart.
3. Load brain.
4. Verify `_pending_entry_order_ids` rehydrated.
5. After 30 ticks (well past TTL), verify expired entries cleared.

### 5. Exit-cooldown rehydration

Same pattern as #4 but for `_exit_cooldown` and `_pending_exit`.

### 6. Symbol-banned + circuit-breaker rehydration

V4 audit-D noted symbol_banned was wiped on restart. Verify it now persists:
- Save with `symbol_banned = {"AAPL": tick_500}`.
- Restart.
- Load.
- Verify `_symbol_banned["AAPL"] == 500`.

### 7. Daily counters + session_date

Verify daily_starting_equity and daily_loss_date persist across restart:
- Save with `daily_starting_equity = 100000.0` and `daily_loss_date = "2026-05-03"`.
- Restart.
- On the same calendar day, verify they survive.
- On a NEW calendar day, verify they reset properly.

### 8. ML state continuity

`signal_gen._clf`, `_reg`, `_calibration_map`, `_calibration_counts`:
- Save → restart → load.
- Verify is_trained stays True.
- Verify calibration_map is preserved (5-bin float array).

### 9. Evolution + fitness state

`evolved_params`, `symbol_fitness`, `symbol_trade_counts`:
- Verify these survive 5 restart cycles.

### 10. Concurrent-restart hazard

If two engine instances try to start against the same brain_dir simultaneously, the lock should prevent both.
- Spawn 2 subprocesses targeting the same brain_dir.
- Verify exactly one acquires the lock; other fails fast.

## Output

`artifacts/audit/v10_reports/track_ww_multi_day_soak.md` with:
- 5x restart invariant table (10 fields × 5 cycles)
- Backup rotation behavior
- SIGTERM atomicity
- Pending-entry / exit-cooldown / symbol-banned / daily-counters / ML-state continuity
- Concurrent-restart lock test

Quality bar: 2-4 findings. **First-time lens for multi-restart**; previous waves only tested single-restart.
