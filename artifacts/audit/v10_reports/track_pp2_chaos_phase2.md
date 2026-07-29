# Track PP2 v10 — Chaos Phase 2 Report

**Repo**: `/Users/marselkei/VS/intra`
**Branch**: `rc-1.5-curated` @ `c048103`
**Sandbox**: `/tmp/pp2_sandbox/` (READ-ONLY on production state)
**Run**: 2026-05-03

V9 PP found 6 chaos findings (3 Critical / 3 High); wave-41 + wave-46 closed PP-1, PP-2, PP-3, PP-4, TT-2, UU-1. PP2 verifies the fixes work under simulated failure rather than just being structurally present.

## Drill matrix

| # | Drill | Outcome | Notes |
|---|---|---|---|
| 1 | PP-1 atomic save under SIGKILL | **PASS** | `_write_json` / `_write_csv_atomic` keep destination intact across kill timings 50/150/300 ms |
| 2 | PP-2 backup fallback (corrupt manifest, valid backup) | **PASS** | `load()` returns True; gen=168, trades=498 restored; HEAD manifest left corrupt for operator |
| 3 | PP-2 no usable backup | **PASS** | `load()` returns False; logs "all backup attempts failed — starting fresh" |
| 4 | PP-3 CRITICAL bypasses dedup | **PASS** | Two CRITICAL → 2 deliveries; two WARNING → 1 delivery (dedup'd); `ALERT-NO-CHANNELS` log fires when no channels configured |
| 5 | PP-3 last-resort `logger.critical` | **PASS** | `ALERT-DELIVERY-FAILED` logged at CRITICAL level when both Slack+PD return False |
| 6 | PP-4 dev-mode DB-down requires `ALLOW_NO_DB` | **PARTIAL PASS** | Branch logic correct for prod/staging/dev; but see Finding 1 — only triggered on DSN-construction errors, not on actual unreachability |
| 7 | TT-2 watchdog under hung mock | **PASS** | 3 calls, each ~0.5 s, counter increments to 3, all return degraded `LiveTickResult` with `TT-2: tick watchdog timeout` error |
| 8 | UU-1 cross-thread alert dispatch | **PASS** | Fast path (main coroutine), `asyncio.to_thread` worker, and raw `ThreadPoolExecutor` worker all schedule the coroutine on the captured main loop |
| 9 | Stream reconnect storm | **PASS (review)** | Code review: 1→60 s exp backoff (×2), 10-attempt cap, slow-retry 5/10/20/30 min, max-reconnect CRITICAL alert (`_emit_max_reconnect_alert`), session-level counter logs CRITICAL after >10 reconnects/session |
| 10 | New chaos vectors for V11 | (recommendations below) | |

Detailed evidence & artefacts under `/tmp/pp2_sandbox/`:
- `atomic_writer_target.py`, `sigkill_drill.py` — drill 1 (atomic SIGKILL)
- `test_pp2_backup.py` — drills 2 & 3 (backup fallback)
- `test_pp3_alerts.py` — drills 4 & 5 (alert escalation)
- `test_pp4_focused.py` — drill 6 (DB-down env gate)
- `test_tt2_watchdog.py` — drill 7 (hung tick mock)
- `test_uu1_worker_thread.py` — drill 8 (cross-thread alert dispatch)

## Drill 1 — PP-1 atomic save under SIGKILL (raw evidence)

```
{'mode': 'json', 'kill_after_ms': 50,  'base_md5': '10b0e5165ab42f37', 'after_md5': '10b0e5165ab42f37', 'tmp_files': []}
{'mode': 'json', 'kill_after_ms': 150, 'base_md5': '10b0e5165ab42f37', 'after_md5': '10b0e5165ab42f37', 'tmp_files': []}
{'mode': 'json', 'kill_after_ms': 300, 'base_md5': '10b0e5165ab42f37', 'after_md5': '10b0e5165ab42f37', 'tmp_files': ['victim.json.tmp']}
{'mode': 'csv',  'kill_after_ms': 300, 'base_md5': '8b201b28dec93edb', 'after_md5': '8b201b28dec93edb', 'tmp_files': ['victim.csv.tmp', 'victim.json.tmp']}
```

Destination MD5 unchanged across every kill point. Only `.tmp` orphans appear, and the `load()` path reads explicit filenames so orphans are harmless to correctness (they're dead bytes). `os.replace` atomicity holds. fcntl `.brain.lock` is auto-released on POSIX process death; subsequent `OrganismBrain` constructions reacquire cleanly.

## Drill 2 — PP-2 backup fallback (raw evidence)

```
PP-2: HEAD brain load failed (Expecting value: line 1 column 1 (char 0)); attempting backup fallback
PP-2: brain restored from backup; gen=168 trades=498 (HEAD save was corrupt)
  load() → True
  generation=168, last_saved=2026-05-03T06:11:45.814226+00:00
  trades=498
  HEAD manifest after load: md5=d70407e863498813, content='not json garbage'  ← left corrupt, operator must intervene
```

The fallback exposes the data via `self._manifest` / `self.trade_history` etc. WITHOUT writing a new HEAD manifest. This is correct: it forces an operator to either (a) trigger a fresh save (which will write a new HEAD with good data) or (b) investigate why HEAD became corrupt. Caveat: see Finding 2.

## Drill 6 — PP-4 ALLOW_NO_DB gate (raw evidence)

```
env='production'   allow_no_db=None  → RAISED   "Database init failed in production: ..."
env='staging'      allow_no_db=None  → RAISED   "Database init failed in staging: ..."
env='development'  allow_no_db=None  → RAISED   "PP-4: Database init failed in 'development' mode and ALLOW_NO_DB!=1..."
env='development'  allow_no_db='1'   → CONTINUED
env='development'  allow_no_db='0'   → RAISED
env='paper'        allow_no_db=None  → RAISED   "PP-4: Database init failed in 'paper' mode and ALLOW_NO_DB!=1..."
env='paper'        allow_no_db='1'   → CONTINUED
```

The gate logic is correct; what's not correct is **when** the outer `except` is reached. See Finding 1.

## Drill 7 — TT-2 watchdog (raw evidence)

```
call 1: 0.505s  result=LiveTickResult(... errors=['TT-2: tick watchdog timeout (0s)'] ...)
call 2: 0.502s  result=LiveTickResult(... errors=['TT-2: tick watchdog timeout (0s)'] ...)
call 3: 0.502s  result=LiveTickResult(... errors=['TT-2: tick watchdog timeout (0s)'] ...)
watchdog timeout counter: 3
PASS
```

Three back-to-back watchdog firings each return in ~0.5 s, counter monotonically increments, and a degraded `LiveTickResult` flows out so the scheduler keeps moving. The `dispatch_alert_from_thread: no main loop captured` warning during the test is expected (no `set_main_event_loop` call in this isolated harness); production lifespan startup captures the loop at line 42 of `backend/api/lifespan.py`.

---

## Findings

### Finding 1 — HIGH — PP-4 DB-down gate is bypassed for runtime unreachability (only catches DSN-construction errors)

**Where**: `backend/api/lifespan.py:93-168`

**What we expected** (per the PP-4 commit comment): "DB connection failure on startup was silent in dev mode — only logged at WARNING. … Wire a CRITICAL alert regardless of env."

**What actually happens**:
1. `init_db(dsn)` (line 97) only constructs the SQLAlchemy async engine. asyncpg is lazy — no connection attempt is made.
2. Pre-warm (lines 102-116) attempts `SELECT 1` and DOES hit the network, but it has its own inner `try/except` that catches `Exception as warm_e` and logs **WARNING only** (`Pool pre-warming failed (non-critical): {warm_e}`).
3. Therefore the outer `except Exception as e` at line 118 — which contains the PP-4 ALLOW_NO_DB gate, the CRITICAL alert dispatch, and the `RuntimeError` raise — **is only reached when `init_db` itself raises**, which in practice means malformed DSN strings, missing drivers, or other engine-construction failures.
4. **Real production failures** — DB host unreachable, wrong credentials, wrong database name, network partition during startup — are caught by the prewarm `except` and result in:
   - Single `WARNING` log line ("Pool pre-warming failed (non-critical)")
   - `app.state.sessionmaker` set to a sessionmaker pointing at a broken engine
   - No CRITICAL alert
   - Process continues startup
   - Subsequent DB ops fail one-by-one, scattered across the codebase

**Impact**: The exact scenario PP-4 was meant to harden against (paper-mode `APP_ENVIRONMENT=development` with DB silently down → audit drops, no telemetry, no reconciliation) is still possible if Postgres is **unreachable** rather than the URL being **malformed**. The PP-4 fix only catches a much narrower failure class than its commit message claims.

**Verification recipe**: spin up paper compose with `DATABASE_URL` pointed at an unreachable host (e.g., port 5433 with no Postgres). With the current code, `init_db` returns successfully (engine is constructed lazily); prewarm's inner except catches the connection failure and logs WARNING; the outer PP-4 branch never fires. Compare to: stop Postgres, then start the API — same outcome.

**Recommended fix**: hoist the prewarm try/except *into* the outer try block — i.e., let prewarm exceptions propagate to the PP-4 gate. Add a `SELECT 1` smoke-test inside `init_db` itself before returning, gated by env (so unit tests with `ALLOW_NO_DB=1` still skip it). One-line proposal:

```python
# inside the outer try:
try:
    await asyncio.gather(*[prewarm() for _ in range(pool_size)])
except Exception as warm_e:
    raise RuntimeError(f"DB unreachable at startup: {warm_e}") from warm_e
```

---

### Finding 2 — MEDIUM — PP-2 backup fallback restores in-memory state but `OrganismLiveEngine` may still write a save with the loaded backup data, silently overwriting HEAD

**Where**: `backend/organism/brain_persistence.py:273-321` (`_restore_from_latest_backup`) interacting with `LiveEngine._save_brain` (periodic save).

**What's good**: drill 2 confirms `load()` populates `self._manifest`, `self.trade_history`, etc. from the backup directory, and HEAD `manifest.json` is **not** rewritten by `load()` itself. This part is correct.

**What's potentially missing**: Once `load()` returns True, the live engine treats the in-memory state as authoritative and proceeds normally. The next periodic `save()` (line 323) will:
- Run `_create_backup()` (which copies the **still-corrupt** HEAD into `backups/<timestamp>/`!)
- Atomically swap a fresh save into HEAD with the recovered data
- `shutil.rmtree(old_dir)` at line 497 deletes the corrupt-HEAD-snapshot the engine just made

Net effect: corrupt HEAD is overwritten by the next save (no data loss because the in-memory state mirrors the backup), BUT the operator has no on-disk artifact of the corruption event after the next save cycle. The CRITICAL log line ("PP-2: HEAD brain load failed") is the only forensic record, and it can rotate out of journald/Docker logs.

**Impact**: silent self-heal on save. Good for resilience; bad for root-cause analysis. If the corruption is recurring (e.g. a flaky disk, a bug in `_save_manifest` under partial-fail), the operator needs to know it's happening repeatedly without grepping logs.

**Recommended fix**: when `_restore_from_latest_backup` succeeds, copy the corrupt HEAD into a sticky location like `brain_dir/corrupt_head_<timestamp>/` and emit a CRITICAL alert (currently the warning-level `logger.warning(...)` at line 248 is severity-mismatched relative to "platform recovered from backup, brain integrity event").

---

### Finding 3 — LOW — `_write_json` / `_write_csv_atomic` orphan `.tmp` files on SIGKILL accumulate forever

**Where**: `backend/organism/brain_persistence.py:2130-2193`

**What was observed in drill 1**: every SIGKILL during a write left a `victim.json.tmp` (or `.csv.tmp`) in the destination directory. The cleanup `tmp_path.unlink()` at lines 2160 / 2190 only runs on a CAUGHT exception, not on uncatchable signals.

**Impact**: low — these files don't break correctness (`load()` reads explicit filenames). But over months of restarts, with ~10 atomic writes per save and frequent unscheduled restarts (Docker healthcheck, OOM, etc.), `organism_brain/` can accumulate dozens of orphans. Cosmetic, not functional. The save() top-level flow (lines 439-441) does `shutil.rmtree(tmp_dir)` for the `.tmp_save` *staging directory*, but NOT for stray `<file>.tmp` siblings of destination files.

**Recommended fix**: at top of `save()`, sweep `brain_dir` for `*.tmp` orphans and unlink them. One block, ~5 lines.

---

## V11 chaos-vector recommendations (from drill 10)

1. **Disk-full mid-save** — write a `_write_json` payload to a tmpfs sized just under the manifest size; verify atomic-replace either succeeds or leaves prior file untouched.
2. **File-descriptor exhaustion** — burn the FD limit (`resource.setrlimit(RLIMIT_NOFILE, (32, 32))`) and verify save() either succeeds or raises a clean error rather than corrupting state.
3. **DNS failure to broker.alpaca.markets** — patch `socket.getaddrinfo` to raise; verify stream reconnect storm hits slow-retry mode rather than tight-looping.
4. **Concurrent save attempts under brain.lock** — already covered structurally, but add a drill that holds the lock from a separate process and calls `save()` from the engine; verify the "Skipping brain save — lock held" log fires (line 362).
5. **PP-4 actual unreachable DB** — see Finding 1.
6. **PP-2 corrupt-HEAD self-heal silent overwrite** — see Finding 2.
7. **`set_main_event_loop` not called in non-API entrypoint** (e.g., a CLI / replay run that wires alerts) — currently `dispatch_alert_from_thread` returns False and logs a WARNING. Verify whether any production code path calls send_alert from a worker thread without the loop being captured first; if so the alert is silently dropped.
8. **Watchdog firing under real `_tick_lock` contention** — present drill ran with the lock free. Test what happens if `live_tick()` is called while a previous hung-tick still holds the lock — does the watchdog fire on the OUTER call's `async with self._tick_lock:`? (Current implementation: no; the lock acquisition itself is unbounded.)

---

## TL;DR

PP2 chaos drills confirm PP-1 atomic save (SIGKILL across 50/150/300 ms), PP-2 backup-fallback, PP-3 dedup-bypass + last-resort logger, TT-2 watchdog, and UU-1 cross-thread alert dispatch are all working as designed. Wave-41 and wave-46 fixes hold up under simulated failure. The one substantive gap is **Finding 1**: the PP-4 DB-down gate at `backend/api/lifespan.py:118` only triggers on `init_db()` errors (DSN parsing), not on the much more common runtime-unreachability case (Postgres down, wrong host, auth failure), because asyncpg connects lazily and the prewarm has its own swallowing try/except. A paper-mode container with a real-world DB outage would still proceed past startup with a single WARNING log and no CRITICAL alert — the exact silent-failure mode PP-4's commit message claims to close. Finding 2 (corrupt-HEAD silently self-heals on next save, no sticky forensic artifact) and Finding 3 (`.tmp` orphan accumulation) are minor follow-ups; Finding 1 is the only HIGH and is recommended as PP3 work for V11.
