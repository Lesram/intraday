# Track UU v9 — Error Handling Consistency

**Branch**: `rc-1.5-curated` @ `ccba97f`
**Method**: AST + grep, read-only.
**Scope**: `backend/**/*.py` (270 modules, excluding tests / `__pycache__`).

---

## 1. Census (AST `ast.ExceptHandler` walk)

| Metric                                            | Count |
|---------------------------------------------------|------:|
| Total `except` handlers                           | 1,487 |
| Bare `except:` (no type)                          | **0** |
| `except ...: pass` (single-stmt swallow)          |   161 |
| `except ...: logger.debug(...)` (debug-only)      |    35 |
| `except ...: logger.info(...)` (info-only)        |     2 |
| `except ...: logger.warning(...)` (warn-only)     |   116 |
| Top exception type: `Exception`                   | 1,065 |
| `ImportError`                                     |    72 |
| `HTTPException`                                   |    55 |
| `ValueError`                                      |    44 |
| Tuple `(TypeError, ValueError)` / vice versa      |    51 |
| `asyncio.CancelledError`                          |    19 |

**Bare-except count = 0** — confirming that prior cycles' style fixes held. This track therefore looks at the *next* failure mode: `except ...: pass`.

### `except ...: pass` distribution by subsystem

| Subsystem                     | pass-handlers |
|-------------------------------|--------------:|
| `backend/organism/`           |            51 |
| `backend/api/`                |            41 |
| `backend/infra/`              |            18 |
| `backend/config/`             |             9 |
| `backend/services/`           |             7 |
| `backend/integrations/`       |             6 |
| `backend/ml/`                 |             6 |
| `backend/risk/`               |             5 |
| Other (features/models/data/…)|            18 |
| **Total**                     |       **161** |

### Logger formatting consistency inside handlers

Of 797 logger.* calls inside `except` blocks, **513 use f-strings** and 131 use `%s/%d` lazy formatting. f-strings are eagerly evaluated — when the log level is filtered out (DEBUG/INFO in production), the format work still happens. More importantly, structured-log aggregators that key on the message template see **644 distinct templates instead of one** for the same logical event. This is a Tier-3 cosmetic finding but it's the lint rule v10 should add.

---

## 2. Tier 1 findings (BLOCKERS — document, do not fix in V9)

### UU-1 (Tier 1) — Daily-max-loss circuit-breaker alert dispatch is silently swallowed
**File**: `backend/organism/live_engine.py:2048-2057`

```python
2034   if MAX_DAILY_LOSS > 0:
2035       daily_pnl = equity - self._daily_starting_equity
2036       if daily_pnl <= -MAX_DAILY_LOSS:
2037           self.governance.halt_trading()
...
2048           try:
2049               from backend.infra.alerting import send_alert, ...
2050               import asyncio as _aio
2051               _aio.create_task(send_alert(
2052                   AlertCategory.RISK_VIOLATION, AlertSeverity.CRITICAL,
2053                   "Daily Max-Loss Halt",
2054                   f"PnL=${daily_pnl:.2f} crossed -${MAX_DAILY_LOSS:.0f}. ...",
2055               ))
2056           except Exception:
2057               pass                                  # ← silent
```

**Why it's Tier 1**: This is the day's most-critical operational alert. The halt itself happens before the alert (so the trade-blocking semantics are correct), but a failure to dispatch is silently lost. If the import fails, or `create_task` raises (no running loop in a thread), the operator never sees a Slack page even though the *next* compliance audit-row block (lines 2060-2083) does log on failure. Asymmetric handling between two adjacent blocks for the same event.

**Why a blocker (per track contract)**: Identical pattern to V5 S-J3-1 (alert silently dropped because `get_running_loop()` raised in worker thread, fixed via Wave-17a's `dispatch_alert_from_thread`). The forensic-guard call site at `live_engine.py:6107-6123` *does* use `dispatch_alert_from_thread`; this risk-violation site does not. This is the next instance of the same class of bug.

**Recommended fix (V10)**: Replace `try / asyncio.create_task / except: pass` with the canonical `dispatch_alert_from_thread(...)`. Log a warning when `ok is False`, mirroring lines 6118-6121.

---

### UU-2 (Tier 1) — Login audit-log dispatch silently swallows DB errors after rollback
**File**: `backend/api/routes/auth.py:289-294, 333-338`

```python
289   except Exception as _audit_err:
290       logger.warning("AA-H-3: login_failed audit failed: %s", _audit_err)
291       try:
292           await db.rollback()
293       except Exception:
294           pass            # ← rollback failure swallowed
```

(Same pattern at lines 333-338 for the *successful* login audit.)

**Why it's Tier 1**: SOX/SOC-2 compliance regimes treat authentication-event audit logs as **mandatory**. The outer except logs a `WARNING` (not ERROR), but if the rollback inside the recovery path *also* fails — e.g. the connection has been dropped — the session is left in a poisoned state and the next request on that session will fail with an opaque `InFailedSqlTransaction`. The next request looks unrelated to login and is hard to triage.

The successful-login branch (line 333) is more problematic: a token was issued, the user is now authenticated, but **no audit row was written and the operator is not paged**. A reviewer reading `audit_log` cannot reconstruct who logged in.

**Why a blocker**: Compliance-grade event with silent failure path. Documented but not fixed because the right fix is a canonical "audit-log-required" wrapper that the platform doesn't currently have (recommended V10 work — see §5).

---

## 3. Tier 2 findings (HIGH — alert / observability paths)

### UU-3 (Tier 2) — Brain-save-blocked alert path silently swallows
**File**: `backend/organism/brain_persistence.py:319-343`

When the brain refuses to save (because the trained-manifest-overwrite guard fires), the code dispatches an alert and releases the lock:

```python
338   except Exception:
339       pass
340   try:
341       lock.release()
342   except Exception:
343       pass
```

The save-blocked path itself is correct — `return` at line 344 prevents corruption. But the operator alert can vanish, *and* the lock-release failure can vanish. Lock-release failures specifically can compound: a stuck file lock survives the process and blocks the *next* save attempt. The lock-acquire site at line 286 already logs and returns when the lock can't be acquired — a stuck lock from this swallowed release would manifest there, but the chain of cause-and-effect is now invisible.

**Recommended fix (V10)**: Same `dispatch_alert_from_thread` substitution as UU-1, plus `logger.error("brain-save lock release failed: %s", exc)` at line 343.

### UU-4 (Tier 2) — Tick-loop telemetry write swallows broadly inside the hot path
**File**: `backend/organism/live_engine.py:4146, 4185-4186, 5917-5926`

The tick loop has multiple `except Exception: pass` swallow points specifically labelled "Telemetry must never break the tick loop" (line 4186 comment). This is *correct* design — a flaky telemetry DB must not stop trading. But the pattern leaks: the equity-curve append at line 4146 (in-memory deque, pure CPU) is wrapped in an identical `try / except: pass` for no reason — there is no error path in `list.append` or `del list[:n]` that warrants this. It is a *cargo-culted* version of the legitimate pattern and trains future authors that "wrap everything." Counter-evidence: site 5917 *does* increment a `_telemetry_write_errors` counter on the critical path and emits a `WARNING` — that is the right pattern.

**Recommended fix (V10)**: Tighten the `except Exception` at line 4146 to either remove the guard (in-memory list ops are exception-free for the inputs we feed) or scope it to `(IndexError, OverflowError)`. Audit the other 14 sites in `live_engine.py` for the same cargo-cult pattern.

---

## 4. Fail-open path inventory (what we *checked*, what we *found*)

| Path                                                  | Behavior on exception                                                                                      | Verdict          |
|-------------------------------------------------------|------------------------------------------------------------------------------------------------------------|------------------|
| `risk_manager._get_portfolio_value()`                 | Production: `raise ValueError("Trading blocked")`. Non-prod: warning + fallback. (lines 444-521)           | **fail-CLOSED**  |
| `live_engine._get_equity()` broker-error              | Falls back to last-known-good equity, watchdog escalates at streak>10/25 (lines 6361-6408)                 | fail-degraded, alerted |
| `infra.security.get_current_user()` JWT parse failure | Returns `None`; downstream `get_authenticated_user` raises 401. (lines 700-705)                            | fail-CLOSED      |
| `routes/auth.py` login audit failure                  | Logs warning, returns success token (already issued)                                                       | **fail-OPEN** for audit (UU-2) |
| `brain_persistence.save()` block path                 | Refuses save (correct), but alert can be silently dropped                                                  | **fail-OPEN** for alert (UU-3) |
| `live_engine` daily-max-loss alert                    | Halt happens, alert dispatch can be silently dropped                                                       | **fail-OPEN** for alert (UU-1) |
| `alpaca_stream` WS reconnect                          | Exponential backoff to 60s, max 10 attempts, then slow-retry cycle + critical alert (lines 905-1040)       | fail-degraded, alerted |
| `alpaca_stream._handle_trade_update` rollback         | DB rollback failure on lot-tracking errors swallowed (line 614-617)                                        | fail-OPEN (low blast radius — minor) |

The pattern is consistent: **risk gates fail closed, alert dispatchers fail open**. That is the right priority order, but the alert-dispatcher inconsistency (some sites use `dispatch_alert_from_thread`, others use `asyncio.create_task` + `except: pass`) is what enabled V5 S-J3-1 to live undetected for 4 audit rounds.

---

## 5. Retry / backoff inventory

| External call                                | Retry?                            | Backoff             | Max | Deadline            |
|----------------------------------------------|-----------------------------------|---------------------|----:|---------------------|
| Alpaca WS connect (`alpaca_stream`)          | yes                               | exponential, ×2     |  10 | 60 s cap, then slow-retry cycle + alert |
| Alpaca trade-update processing (line 359-393)| yes (3×)                          | exponential 0.5/1/2 |   3 | none                |
| OrderService submit                          | retries inside `OrderService` (out of scope) | — | — | — |
| Postgres `dispose_engine` on shutdown        | none — best-effort, log on failure| —                   |   1 | 2 s gather timeout  |
| `positions_service.get_total_portfolio_value()` | no retry; falls through to dynamic-create-service path | — | 1 | none |

Findings:
- **Alpaca trade-update retry has no deadline** — three attempts at 0.5/1/2s = ~3.5s blocking, acceptable.
- **Postgres dispose_engine has no per-operation deadline**, only the outer 2 s `asyncio.gather`. Acceptable for shutdown only.
- No retry on `_get_portfolio_value` — broker outage trips the production fail-closed branch on the first exception. Correct.

---

## 6. Recommended canonical pattern (proposal for V10 lint enforcement)

```python
# Canonical "non-fatal sub-task in critical path" pattern
try:
    do_optional_thing()
except Exception as exc:
    logger.warning(
        "<subsystem> <op> failed: %s",   # use %s, not f-string
        exc,
        exc_info=True,                   # required for non-cancellation paths
    )
    # explicit comment on WHY pass is OK here
```

**Lint rules to add (v10)**:
1. **No `except ...: pass`** without a `# noqa: BLE-PASS — <reason>` annotation. CI fails on un-annotated swallow sites.
2. **No f-string-as-first-arg-to-logger.<level>** inside an `except` block (use `%s`, lazy).
3. **`asyncio.create_task(send_alert(...))` inside `try/except: pass`** is a banned bigram — substitute `dispatch_alert_from_thread(...)` from `backend.infra.alerting`.
4. **Audit-log dispatch sites must use `fire_audit_log` with required-mode wrapper** that logs ERROR (not WARNING) on swallow and increments `audit_log_dispatch_failures_total` Prometheus counter so dashboards see the loss.

161 sites is too many to refactor in one pass. Stage the lint with a baseline file and ratchet down.

---

## 7. TL;DR

The codebase has zero bare `except:` clauses and well-designed risk-gate fail-closed semantics — but it has **161 `except ...: pass` swallow sites** with no consistent policy, and the *alert-dispatch* layer is the soft underbelly: critical events (daily-max-loss halt, brain-save-blocked, login audit) emit alerts that can be silently lost via `try/create_task/except: pass`, while a sibling site nine lines away uses `dispatch_alert_from_thread` and logs on failure. UU-1 and UU-2 are Tier 1 blockers that recreate the V5 S-J3-1 failure mode in adjacent code. UU-3 and UU-4 are Tier 2 hygiene findings on the same pattern. V10 should land the four lint rules in §6 with a baseline file, then ratchet down the 161 sites — starting with the eight in `live_engine.py` that touch entry/exit/halt logic.
