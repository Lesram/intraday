# Track PP v9 — Chaos / Fault-Injection (NEW LENS)

**Branch**: `rc-1.5-curated` @ `ccba97f` (rebased from `db1a3fc` per prompt; see `git status` snapshot).
**Method**: Code review (read-only) + targeted production-container inspection (`docker exec`-readonly only). No mutations to brain, DB, or broker.
**Output**: 6 chaos-shaped findings, severity-tagged, with recommended drills for V10.

---

## F-PP-1 — `save_essential_state` is the dominant on-disk save path and has NO crash-consistency between files (Critical)

**Code**: `backend/organism/brain_persistence.py:680-783` (`save_essential_state`), called from `live_engine.py:6184` whenever the walk-forward gate blocks the full save.

**Live behavior** (verified via `docker exec intra-api-1 ls /app/organism_brain/`):
- Container running 2 hours, brain mtimes are *current* (06:11 today) — saves are happening.
- **`/app/organism_brain/backups/` does NOT exist**. The `backups/` directory is only created by `save()` (the full atomic-swap path, lines 280, 1898). Because the walk-forward gate (`live_engine.py:6172-6178`, regression_threshold=0.95) blocks full saves whenever recent Sharpe regresses, every routine save in production goes through `save_essential_state` → no backup is ever created.
- "Last 5 brain snapshots safety net" advertised in the docstring (line 18) is non-existent in production.

**Crash-consistency gap**:
- `save_essential_state` writes 7-9 separate files in sequence (`trade_history.csv`, `learning_state.json`, `evaluation_event_history.json`, `equity_curve.csv`, `extra_counters.json`, `governance_state.json`, `regime_state.json`, `ml_state.json`, `manifest.json`).
- **Per-file** atomic-replace was added by Wave-19 (`_write_json` line 2035) for JSON, and Audit-H H-8 (line 1404) for `trade_history.csv`. Good.
- **But `equity_curve.csv` (line 1423), `epoch_metrics.csv` (line 1438), and `reference_feats.csv` (line 1316) use direct `df.to_csv()` — NOT atomic.** SIGKILL or OOM mid-write will leave a truncated file. On next boot, `_load_equity_curve` will either fail (excepted at `load()` line 241 → "starting fresh") or load a half-truncated equity_curve, polluting the peak_equity / drawdown calculations.
- **No inter-file consistency guarantee**: SIGKILL between writing `trade_history.csv` (newest 482 trades) and `manifest.json` (still says 481 trades) leaves the brain self-inconsistent. Audit-D BUG-D class.

**Blast radius**: After a hard restart, the system can lose accumulated trade history, regress to fresh state, or load a self-inconsistent brain (manifest claims trained but equity_curve is partial). The `load()` exception handler returns False ("starting fresh") with NO fallback to `backups/` directory — and that directory is empty anyway.

**Severity**: Critical (data loss / brain regression to fresh organism state).

---

## F-PP-2 — `load()` fails closed with no auto-restore from backups; backup directory is empty in production (Critical)

**Code**: `backend/organism/brain_persistence.py:201-245` (`load`), `1898-1924` (`_create_backup`).

```python
except Exception as e:
    logger.error("Failed to load brain: %s — starting fresh", e)
    print(f"  ⚠️  Brain load failed ({e}) — starting fresh")
    self._loaded = False
    return False
```

**Failure mode**: any single file in the brain dir being corrupted (truncated `manifest.json`, malformed JSON, missing `learning_state.json`) → load() throws → caller sees `False` → engine starts as a *fresh* organism. Per CLAUDE.md state: 161 generations / 482 trades / ML-trained classifier+regressor + 79 features ALL gone. The "backup safety net" is referenced but never consulted by `load()`.

**Live confirmation**: `docker exec intra-api-1 ls /app/organism_brain/backups/` → "No such file or directory" — production has no backups. The fall-back is a void.

**Severity**: Critical — first-ever disk corruption / OOM-kill mid-save would wipe the trained brain with no recovery.

**Recommended drill (V10)**:
1. SIGKILL the API container 50× during a 5-minute window in scratch and verify load() succeeds each time.
2. Truncate `equity_curve.csv` to 0 bytes manually and verify load() falls back to backup, not fresh start.
3. Add a `_load_with_fallback` that walks `backups/` newest-first if primary load fails.

---

## F-PP-3 — Alert dispatch silently drops bursts and does NOT escalate Slack 5xx to PagerDuty (High)

**Code**: `backend/infra/alerting.py`.

Three failure-mode chains compound:
1. **AlertDeduplicator** (line 75-122) hashes `(category, severity, title)` over a 5-minute window. A burst of N "Order Failure" alerts collapses to **one** Slack post. In a real incident (broker 5xx burst, 10 positions failing exits), the operator sees a single ":x: Order Failure" message and may not realize 10 orders are stuck.
2. **AlertRateLimiter** (line 125-149): 30 alerts/min cap → silently returns False. `logger.warning(f"Alert rate limit exceeded ({self._max}/min)")` is the only signal, and it goes to logs only.
3. **`_send_slack` (line 364-380)**: on `response.status_code != 200`, just logs error and returns False. **No retry, no fallback to PagerDuty, no DLQ.** The alert is gone:
```python
else:
    logger.error(f"Slack alert failed: {response.status_code} - {response.text}")
    return False
```

**Compare** with `alpaca_stream._process_update_queue` (line 357-414) which retries 3× then writes to `_dlq_path` — alert-dispatch has neither.

**Worst-case**: a Slack outage during a daily-max-loss event (line 2047-2057) means the only alert about the trading halt is dropped. The audit log row in `fire_audit_log` is best-effort too (line 671 swallows). Operator only learns post-hoc by checking logs.

**Severity**: High — repeats the V5/V6/V7 "alert silent-drop" bug class that V8 OO flagged. The fixes were in dispatcher *plumbing* (cross-thread loop ref) but the *delivery* layer still has no retry/DLQ.

---

## F-PP-4 — DB-down at startup is silent in `development` (which is what paper actually runs as) — organism boots but flies blind (Critical for paper, by-design for prod)

**Code**: `backend/api/lifespan.py:118-158`.

```python
if env in ("production", "prod", "staging"):
    raise RuntimeError(f"Database init failed in {env}: {e}") from e
logger.warning("Database init failed, continuing (dev only)", error=str(e))
app.state.sessionmaker = None
app.state.db_sessionmaker = None
```

Per CLAUDE.md: **paper compose runs `APP_ENVIRONMENT=development`** (gotcha documented). Therefore in actual paper deploy:
- DB init failure does NOT fail-fast.
- `sessionmaker = None`.
- `_has_db = False` gates **most** background services, but **NOT `ENABLE_ORGANISM_SCHEDULER`** (line 290-298 — no `_has_db` check).
- `Alpaca stream` IS gated by `_has_db` (line 302). So if DB down → no WS stream → no fill notifications.
- Reconciliation IS gated (line 320). So if DB down → no auto-reconciliation.
- Outbox worker IS gated (line 165). So orders won't reach broker (outbox dispatch dies).
- But the organism *scheduler tick loop* still runs (line 290-298). Tick code calls `_positions_service.get_all_positions()` which goes through Alpaca REST — that might still work, but `fire_audit_log_threadsafe` silently drops every audit row (line 652-657).

**Net behavior in dev/paper with DB down**: the organism keeps ticking (logs look OK at INFO), no audit trail, no trade DB rows, no alerts because alerter has no main-loop ref if startup didn't complete. There IS a CRITICAL alert dispatched at line 134-146, but per F-PP-3 if Slack is also down, it's gone.

**Wave-22 partially fixed this** by emitting the CRITICAL alert regardless of env, but the engine still proceeds. There is no "halt the engine if no DB in non-prod" guard.

**Severity**: Critical — the "happy logs, broken accounting" failure shape is the exact V5 reconciliation-pollution post-mortem class.

---

## F-PP-5 — Universe scanner cache has no TTL and no failure circuit-breaker (High)

**Code**: `backend/organism/market_scanner.py:372-452` (`scan`).

```python
if not all_scanned:
    logger.warning("Scanner: no stocks passed initial filters")
    self._last_scan_time = time.time()
    return self._cached_candidates  # ← stale forever
```

Failure modes:
1. **Alpaca movers/screener API returns empty**: returns the cached candidate list with NO age limit. If first-ever scan succeeded with 50 names, then API breaks for hours, we trade a stale 50-name universe. No alert fires.
2. **3 concurrent fetches all fail** (line 401-404): each `Exception` is logged at WARNING and the batch is skipped. If all three fail, `all_scanned` is empty → cached return path.
3. **No consecutive-failure counter**: 1 failure = N failures. There's no "if 5 scans in a row failed, alert + halt entries" gate. Compare `scheduler.py` which DOES track `consecutive_errors` for tick-level failures (line 354-360).

The tick-level invocation (live_engine.py:1779-1780) also swallows scanner exceptions to a WARNING log:
```python
except Exception as e:
    logger.warning("Market scan failed: %s", e)
```

**Severity**: High — the Apr-9 AIA review specifically flagged "stocks-in-play" scanner reliability. Stale candidate list is exactly the silent corner-case it can hit.

---

## F-PP-6 — Stale-data gate uses aggregate `last_update_time`; partial WS failure (active symbols stop, background tickers continue) is invisible (High)

**Code**:
- `backend/organism/streaming_data_provider.py:67, 261, 286` — `last_update_time` is set on **any** symbol's update.
- `backend/organism/live_engine.py:1670-1688` — `_data_stale = staleness_s > self._DATA_STALE_THRESHOLD_S` — uses the aggregate.
- `backend/organism/streaming_data_provider.py:310-355` — `check_and_recover_stale_stream` only triggers when **ALL** tracked symbols stale (`stale_count < len(self._last_bar_ts)` returns False). Comment says "avoids false positives from a single missing symbol" — but inverts the failure mode.

**Failure shape**: Alpaca data stream silently stops sending bars for the actively-traded symbols (e.g. NVDA, COST) but continues sending updates for SPY/QQQ in the universe. `last_update_time` keeps refreshing. `_data_stale` stays False. The organism keeps making decisions on data frozen 30+ minutes ago for the symbols it actually cares about. No alert. No reconnect.

The `get_bar_age(symbol)` function (line 300) DOES exist — it returns per-symbol age — but the tick gate doesn't use it. The tick gate uses the global `last_update_time` only.

**Mitigation in code**: per-tick stale check at line 1654-1667 runs `check_and_recover_stale_stream` every 30 ticks (~5 min) but as noted that requires ALL symbols stale.

**Severity**: High — closely matches the V8 OO "we never knew this was broken" archetype. Hard to detect short of synthetic per-symbol staleness probes.

---

## Top-5 swallowed-exception sites (highest blast radius)

Search:
```
grep -rn "except Exception" backend/organism/ --include='*.py' | wc -l   → 225
grep -n  "except Exception:" backend/organism/live_engine.py             → 30 bare
```

The five most dangerous sites where the silenced error can corrupt state silently:

| # | File:Line | Context | Risk |
|---|---|---|---|
| 1 | `live_engine.py:3741` | `fresh_open = open_symbols` fallback when `_positions_service.get_all_positions()` fails right before submit | Stale broker view → duplicate entry on a symbol that just filled mid-tick. Partial-fill class bug. |
| 2 | `live_engine.py:4185-4186` | `# Telemetry must never break the tick loop` swallowing in `_persist_telemetry_to_db` / `_cleanup_old_telemetry` | Silent telemetry pipeline failure — operator dashboards look healthy while DB is silently empty. The wave-22 V-T-5 class. |
| 3 | `live_engine.py:4612` | Watchdog C1 alert dispatch in `_update_watchdog_state` silently swallows. Combined with F-PP-3, "no orders for 12h" alert can be lost. | The watchdog itself can fail invisibly. |
| 4 | `brain_persistence.py:400-407` | Atomic swap fallback inside `save()` — only fires on Python `Exception`, NOT SIGKILL. If process is killed between `shutil.move` calls, brain_dir is partially populated and `_load_manifest` may succeed against a stale-but-readable manifest from `.brain_old` (or fail outright). | Inter-process crash window during the file-shuffle. |
| 5 | `audit_service.py:671-677` (`fire_audit_log`) and `services/audit_service.py:711-712` (`fire_audit_log_threadsafe`) | "Best-effort: never let audit failure propagate to the caller." | Compliance audit row can drop silently — V5 reconciliation-pollution class precisely. The hash chain `verify_chain_integrity` (line 386-466) reports failure but does NOT halt the next write — the next `_get_last_hash` query orders by `ts DESC LIMIT 1` and writes a record extending the broken chain. So a single corruption silently propagates forward. |

---

## Other findings worth recording (below the 6-finding bar)

- **Broker retry storm vs tick deadline**: `alpaca_broker.py:165-250` retries up to 3× with backoff `1, 2, 4, 8, 16` = 31s total. Tick timeout is 60s (`scheduler.py:329`). One degraded broker call during a 5xx burst eats half the tick budget; if a tick has 3 such calls (entry + 2 exits), it hits the 60s timeout and `asyncio.wait_for` cancels mid-execution. The cancellation point is unpredictable — could leave `_pending_exit` set, `_entry_metadata` half-written. Mitigation: circuit breaker exists (line 178-184) but only opens after threshold; the *first* burst still consumes the budget. The breaker `failure_threshold` is not visible without reading `infra/resilience.py`.
- **DST / timezone fallback drift**: `live_engine.py:1981-1987` and several siblings (1192-1198, 1165-1170, 2604-2608, 3719-3723) use `_now_fn().astimezone(ZoneInfo("America/New_York"))` with a UTC fallback in `except Exception`. If the container's tzdata is corrupt or `zoneinfo` cache is missing, the daily session date rolls at UTC midnight (8 PM ET) instead of 4 PM ET. Daily counters and `_symbol_banned` thus reset 4 hours late, leaking bans / counters into Day 2 evening trading.
- **Reconciliation grace = 3 ticks (~30s)**: `live_engine.py:5069`. A position whose entry order is still being acknowledged by the broker is exempt from "closed" detection. But there's no upper bound: an entry that was *rejected* but the rejection event was lost (WS gap, then gap-fill missed it) stays in `_entry_metadata` forever. Wave-17c gap-fill helps but only on reconnect-driven gaps, not on rejected-not-filled cases that happened during steady-state with WS up.
- **Brain lock file (`.brain.lock`) is a regular file with `_BrainLock`** — process-killed lock hold-over: needs verification that lock acquire after SIGKILL doesn't permanently block on a stale lock. (Live container shows `.brain.lock` is a 0-byte file — likely fine — but worth a drill.)

---

## Recommended chaos drills for V10

| Drill | Setup | Expected pass | Catches |
|---|---|---|---|
| **D1: SIGKILL during save_essential_state** | Scratch container, run engine 5 min, SIGKILL the API container 50× while save is in flight. | After every kill, `load()` returns True with consistent trade_count == manifest.total_trades. | F-PP-1 (inter-file consistency) |
| **D2: Truncate brain file** | `truncate -s 0 organism_brain/equity_curve.csv` and restart. | Engine loads from backup OR halts cleanly with critical alert (NOT "starting fresh"). | F-PP-2 (no auto-restore) |
| **D3: Slack 503 burst** | Mock SLACK_WEBHOOK_URL to a server that returns 503. Trigger 50 alerts. | DLQ file populated; PagerDuty receives escalation. | F-PP-3 |
| **D4: DB pause mid-tick** | `docker pause db_paper` for 3 minutes. | Organism halts entries within 60s; resumes cleanly when DB returns. Audit rows for the gap NOT silently dropped (replay buffer). | F-PP-4 |
| **D5: Movers API empty** | Mock `/v1beta1/screener/stocks/movers` to return `{"gainers": []}` for 30 min. | Alert fires after N consecutive empty scans; entries blocked or universe reverts to safe default (NOT cached-from-yesterday). | F-PP-5 |
| **D6: Per-symbol stream stall** | Inject a fault that drops bar updates for COST/NVDA only, while SPY continues. | `_data_stale` flips True and entries block within `_DATA_STALE_THRESHOLD_S`. | F-PP-6 |
| **D7: Audit hash chain break** | Manually corrupt one audit_log.hash_chain row. | Next `verify_chain_integrity` reports failure AND next write halts (or routes to a forensic path), NOT extends the broken chain. | Top-5 #5 |
| **D8: Alpaca 5xx burst during 3-position-exit cycle** | Mock broker to return 503 for 30s while tick has 3 exits. | Circuit breaker opens; `_pending_exit` correctly retried on next tick; no orphan / duplicate orders. | "Other findings" #1 |

---

## TL;DR

The platform's exception-handling style is excellent at *not crashing* but consistently fails the chaos test of *not losing state silently*. The biggest gap is the brain-persistence path: in production today (`docker exec` confirmed), the `backups/` safety-net directory **does not exist** because the walk-forward gate routes every routine save through `save_essential_state`, which writes 9 files in sequence with no inter-file atomicity, no backup creation, and no auto-recovery on partial corruption — a single SIGKILL or OOM mid-save can regress 161 generations / 482 trades to a fresh organism with the load-side fallback being literally "start over." Compounding this, the alert-dispatch layer still silently drops Slack 5xx bursts and dedups N failures into 1 ping (the V5/V6/V7 fix-didn't-fix bug class re-armed at a different layer), DB-down in `APP_ENVIRONMENT=development` (which is what paper actually runs as) lets the organism scheduler keep ticking with `sessionmaker=None` and no audit trail, and the universe scanner returns a TTL-less cached candidate list forever if the Alpaca movers API breaks. Six chaos drills (D1–D8 in the table above) would catch the real-world manifestations of these and align V9 with the V8 OO meta-audit's CHAOS-GAP recommendation.
