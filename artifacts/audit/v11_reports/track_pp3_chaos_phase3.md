# V11 Track PP3 — Chaos Phase 3 (Real SIGKILL + Network Partition)

**Date:** 2026-05-03
**Repo:** `/Users/marselkei/VS/intra` @ branch `main` (worktree). Working changes only — nothing committed.
**Sandbox:** `/tmp/pp3_sandbox/` — all chaos drills run against `/tmp/pp3_sandbox/brain_test/` (a copy of `organism_brain/`); production never touched.
**Python:** `./venv/bin/python` (Python 3.12).
**Subject under test:** Wave-41 atomic-write / Wave-51 backup-on-essential-save / Wave-46 TT-2 watchdog / Wave-56 forensic snapshot + .tmp sweep / V10 PP2-1 outer-block SELECT 1 / V10 PP-4 ALLOW_NO_DB gating.

## Verdict per drill

| # | Drill | Status | Wall measurement |
|---|-------|--------|------------------|
| 1 | SIGKILL during atomic save (kills BEFORE save body — import phase) | PASS | HEAD untouched at all 4 timings (50/150/300/600ms) |
| 1b | SIGKILL during atomic save (kills INSIDE save body, slow-patched) | PASS | gen=168 preserved; trials at 0.5s/1.5s killed mid-save, trials at 2.5s/3.5s completed cleanly |
| 2 | Corrupt manifest with 5 backups → fallback | PASS | Restored gen=168, 498 trades from backup; `corrupt_head_*` snapshot captured |
| 3 | Repeated SIGKILL stress (10x) | PASS | Manual `.tmp` orphan dropped before each kill is swept on next save (10/10) |
| 4 | WW-1 backup cadence verification | PASS | interval=3600 → 1 backup over 5 calls; interval=0 → 5 backups (capped at MAX_BACKUPS) |
| 5 | TT-2 watchdog drill against hung mock | PASS | Watchdog fired at 0.503s (budget 0.5s); counter→1; degraded LiveTickResult; alert dispatched |
| 6 | PP2-1 outer-block SELECT 1 + ALLOW_NO_DB | PASS | dev w/o ALLOW_NO_DB → PP-4 RuntimeError; dev+ALLOW_NO_DB=1 → warn_continue; production → fail-fast regardless |
| 7 | Network partition: broker timeout (sleep 30s) | PASS via tick watchdog | `submit_order` has NO internal timeout; 30s tick watchdog is sole defense |
| 8 | Disk-full mid-save (2 MB tmpfs, ~16-30 MB payload) | PASS | OSError caught & logged; HEAD manifest preserved; load() returns gen=168; no `.tmp` orphans |
| 9 | SIGTERM during save | PASS (equivalent to SIGKILL) | rc=-15; HEAD preserved; cleanup behavior identical to SIGKILL — no SIGTERM handler in `brain_persistence.py` |
| 10 | Audit-chain integrity post-restart | NOT EXECUTED (LIVE-DB) | `ComplianceAuditService.verify_chain_integrity` confirmed present and DB-backed via static inspection (`backend/services/audit_service.py:386`); execution forbidden by sandbox-only rule |

## Findings

### PP3-1 (LOW, cosmetic) — `.tmp_save/` staging directory and `.brain.lock` file are not cleaned up after a SIGKILL'd save until the *next* save runs

**Evidence:** Drill 1b trials 1-2; manual reproduction in `/tmp/pp3_sandbox/brain_test/` showed `.tmp_save/` containing partially-written `ml_classifier.joblib`, `ml_regressor.joblib`, `ml_state.json` plus a 0-byte `.brain.lock` after SIGKILL.

The orphan-sweep in `OrganismBrain.save` (`backend/organism/brain_persistence.py:399-407`, V10 PP2-3 / Wave-56) only removes `*.tmp` *files* directly under `brain_dir/`; it does not touch the `.tmp_save/` staging *subdirectory* or stale `.brain.lock`. Both ARE handled correctly when the next `save()` runs:

- `.tmp_save` removed at line 491-492 (`if tmp_dir.exists(): shutil.rmtree(tmp_dir)`)
- `.brain.lock` is reusable because POSIX flock is FD-scoped — kernel releases on process death, so `_BrainLock.acquire()` succeeds on the next attempt.

**Why LOW:** No correctness impact. HEAD survives, atomic swap untouched, next save self-heals. But `load()` between the SIGKILL and the next save will see a brain dir with leftover staging files. If an operator does forensic exec into the container right after a SIGKILL crash to inspect state, they'll see what looks like a partial save. Drill 1b confirmed `load_after_ok=true, load_after_gen=168, tmp_save_dir_after_load=true` — the load doesn't choke on it but doesn't clean it either.

**Suggested fix:** Extend the wave-56 sweep to also `shutil.rmtree(brain_dir / ".tmp_save", ignore_errors=True)` and unlink stale `.brain.lock` (or at minimum sweep them in `load()` after a successful load).

**File/line:** `backend/organism/brain_persistence.py:395-407`.

### PP3-2 (LOW, observability) — Tick-watchdog timeout error message renders sub-second thresholds as `0s`

**Evidence:** Drill 5 with `_TICK_WATCHDOG_SECONDS=0.5` produced `result.errors = ["TT-2: tick watchdog timeout (0s)"]` because `f"{self._TICK_WATCHDOG_SECONDS:.0f}s"` truncates 0.5 → 0.

**Why LOW:** Production uses 30s, so the bug is invisible under prod config. Surfaces only in tests / future tuning where sub-second budgets get used. Both occurrences of `:.0f` formatting are inside `live_tick`'s timeout-error branch.

**File/line:** `backend/organism/live_engine.py:1646` and `1660` — `f"{self._TICK_WATCHDOG_SECONDS:.0f}s"`.

**Suggested fix:** Use `:.1f` or `:g` (or accept the 0s for non-fractional values explicitly).

### PP3-3 (LOW→MEDIUM, leak risk) — `submit_order` lacks an inner timeout; only the 30 s tick watchdog stops a hung broker call, and the underlying thread can't be cancelled

**Evidence:** Drill 7 `submit_order_has_wait_for: false`. The implementation at `backend/data/alpaca_client.py:513` is `order = await asyncio.to_thread(self.trading_client.submit_order, order_request)` with no `asyncio.wait_for` wrapper. When the tick watchdog fires at 30s, `asyncio.wait_for` cancels the awaiting coroutine, but `asyncio.to_thread` runs the underlying SDK call on the default thread-pool executor — that thread is **not** cancellable via Python primitives; the alpaca SDK's blocking REST call will continue on the OS thread until the SDK's own socket read times out.

**Why this matters:**
- A 25 s alpaca stall consumes a tick but does not trigger the watchdog (31s would). With a default scheduler interval of 10s, multiple ticks could pile up if `_tick_lock` is held.
- After watchdog fires at 30s, the orphaned thread keeps a connection / socket open and may eventually return an OrderResult that has nowhere to go (the awaiting coroutine was cancelled). This was the precise pattern of the wave-47 TT-4 fix for `_rate_limit()` blocking — a similar half-fix may be needed for the underlying SDK calls.
- The retry wrapper `_api_call_with_retry` (line 920) DOES detect timeout-flavored exceptions but is not wired into `submit_order`; only `cancel_order`, `get_account_status`, and `get_recent_orders` route through it (search of `_api_call_with_retry` callers confirms).

**Why LOW→MEDIUM:** Tick watchdog is the safety net and was verified to fire correctly. But on extended broker partition (alpaca data plane partial outage), threads accumulate. Production has not yet observed this — paper trading volume is low (~16 trades on the best day per memory note) so a single hung thread is harmless, but it's a real shape-of-the-iceberg gap that would amplify under stage-2/3 production volume.

**Suggested fix:** Wrap the alpaca thread call in `asyncio.wait_for` with an explicit timeout (e.g. 15s — sub-watchdog), and on timeout log a `TT-X: alpaca submit timeout` plus a thread-leak counter. Optionally route `submit_order` through `_api_call_with_retry` for parity with the other 3 paths.

**File/line:** `backend/data/alpaca_client.py:444-525` (`submit_order`); compare with `_api_call_with_retry` at line 920.

## Drills that PASSED unambiguously

- **Drill 1 / 1b / 3 (SIGKILL × atomic write):** `_write_json` (`brain_persistence.py:2221-2253`) and `_write_csv_atomic` (line 2257-2283) use the canonical `tmp_path` → `os.replace` POSIX-atomic pattern with fsync. SIGKILL kills the process before `os.replace` runs → reader sees prior-state file. No partial JSONs ever observed.
- **Drill 2 (corrupt-manifest fallback):** `_restore_from_latest_backup` (`brain_persistence.py:273-358`) walks `backups/` newest-first, attempts each. PP2-2 forensic snapshot dir is also created. The drill exercised exactly this path.
- **Drill 4 (WW-1 cadence):** `save_essential_state` cadence-gate at line 921-946 honored exactly. Cap at MAX_BACKUPS=5 enforced by `_create_backup` rotation.
- **Drill 5 (TT-2 watchdog):** `live_tick` at `live_engine.py:1617-1662` correctly wraps `_live_tick_inner` in `asyncio.wait_for`, increments `_tick_watchdog_timeouts`, dispatches alert via `dispatch_alert_from_thread`, returns degraded `LiveTickResult`.
- **Drill 6 (PP2-1 / PP-4):** `lifespan.py:111-187` correctly distinguishes `production`/`prod`/`staging` (always fail-fast) vs `development` (gated by `ALLOW_NO_DB=1`). All three test scenarios returned the correct verdict.
- **Drill 8 (disk-full):** Save's outer try/except catches `OSError [Errno 28]`, logs `Brain save failed: ...`, leaves HEAD untouched, no `.tmp` orphans (the inner `_write_json` cleans its own tmp on exception at line 2247-2253).

## Sandbox state (for reproducibility)

```
/tmp/pp3_sandbox/
├── brain_test/                    # working copy under test
├── _pristine_brain/               # snapshot for reset
├── _timing_brain/                 # one-off save timing test
├── _tinydisk.dmg                  # detached after drill 8
├── scripts/                       # 11 drill scripts
└── results/                       # 11 result JSONs
```

## Out-of-scope deliberately

- Drill 10 (live audit_logs verify_chain) is forbidden by sandbox-only rule — function presence and shape confirmed, but actual chain verification against prod PostgreSQL was skipped.
- ChaosMonkey-style continuous fault injection across full live_engine isn't part of PP3's drill list — those would belong in a future PP4-style track.

## Quality bar

3 findings, all LOW severity (one with MEDIUM ceiling under stage-2 volume). All wave-41/46/51/56 invariants verified end-to-end against real SIGKILL.
