# Track YY — Observability Completeness (V10)

**Repo:** `/Users/marselkei/VS/intra`  **Branch:** `rc-1.5-curated`  **HEAD:** `c0481033d8c2db10dd4b92c9832da2fc17667e7a`
**Mode:** Read-only AST + grep + read.

## Method

1. AST-walk `backend/**.py` (excluding `test`/`__pycache__`) for `logger.{error,critical,warning}` calls.
2. For each `logger.critical` site, scan a 30-line window AND the whole file for `send_alert` / `dispatch_alert_from_thread` to score "alert-wired vs silent".
3. Enumerate `Counter|Gauge|Histogram|Summary` definitions and verify each "must-have" critical event has a counter.
4. Map every `AuditAction` enum value to its emit sites (compliance reachability).
5. Inspect health endpoints (`/health`, `/livez`, `/readyz`, `/api/v1/health/*`) for what they actually check.
6. Cross-check `AlertSeverity` → channel routing in `backend/infra/alerting.py` against the YY spec.
7. Tally broad `except Exception` blocks that log-and-swallow without alerting or re-raising.

### Census

| level | count |
|---|---|
| critical | **16** |
| error | **473** |
| warning | **497** |
| **total** | **986** |

Eager `f"..."` payload form: **531** sites. Lazy `%s` form: **275**. Eager:lazy ≈ 1.93:1. Drift since V9 UU census (513:131) — net **+18 eager / +144 lazy** as wave-41 PP-3 / UU-1 hardening introduced more lazy structured logs alongside legacy f-strings.

---

## Finding YY-1 — Six of sixteen `logger.critical` sites have NO alert dispatch in their file

**Severity:** **HIGH** — repeats the V5 S-J3-1 / V9 PP / V9 UU-1 "operator paging silently broken" pattern, but in code-paths that wave-41/wave-21 didn't touch.

Critical sites whose **entire enclosing module** never calls `send_alert` / `dispatch_alert_from_thread` (verified via file-wide grep, not just window):

| Site | Event | File-level alert dispatch? |
|---|---|---|
| `backend/organism/governance.py:263` | `DRAWDOWN KILL SWITCH TRIGGERED` | **No** |
| `backend/services/risk_manager.py:677` | `EMERGENCY STOP triggered by ...` | **No** |
| `backend/services/risk_manager.py:723` | `EMERGENCY STOP executed: ...` | **No** |
| `backend/api/routes/risk.py:292` | `EMERGENCY STOP triggered: user=...` | **No** |
| `backend/monitoring/slo_monitor.py:179` | `Circuit breaker OPENED due to ...` | **No** |
| `backend/monitoring/slo_monitor.py:329` | `SLO ALERT: ...` (already-classified critical) | **No** |

Sites that DO log `critical` but DO route through `send_alert`/dispatcher (sanity check — these are wired):
* `live_engine.py:2184` (DAILY MAX-LOSS HALT) — wave-41 UU-1 wired.
* `live_engine.py:4800` (C1 watchdog inert) — wave-21 wired.
* `live_engine.py:6300` (forensic guard: object-identity changed) — wave-17a wired.
* `alpaca_stream.py:1069` (`_emit_max_reconnect_alert` wraps the log).
* `alerting.py:303,323` (the alert layer's own last-resort logs after channel exhaustion).

Sites that log `critical` AND are in a file with *some* `send_alert` usage but the specific critical does NOT dispatch (silent within wired file):
* `live_engine.py:6351` — `FORENSIC GUARD: total_trades=0 but disk shows N` (regression-detection guard) — file has `send_alert` for the *prior* identity-changed guard, but this regression guard has none. The disk is being *protected* from a wipe, but the operator isn't paged that the in-memory learner regressed.
* `live_engine.py:6603` — `C2 WATCHDOG: Equity fallback streak>25 — broker API may be down` — sister of `C1` (4800) which wave-21 wired, but `C2` was overlooked.
* `alpaca_stream.py:957` — `Stream instability: %d reconnects > 10` — the *max-reconnects-reached* path 100 lines below has a wired alert; this *intermediate-instability* one does not (it must reach max for an alert to fire).
* `brain_persistence.py:1106` — `BRAIN MANIFEST READ-BACK INVARIANT FAILED` — the `_log_brain_save_blocked` path 700 lines above is wave-41-wired, but the post-write read-back invariant uses critical-log-only and returns `False`. A silent corruption-detection win.

**Operator impact:** at least four high-criticality conditions never reach Slack/PagerDuty:
1. **Drawdown-kill** firing — the *primary* portfolio safety event in the platform. Note the README.md banner ("DRAWDOWN KILL SWITCH TRIGGERED") implies it pages; it does not.
2. **Emergency-stop** triggered/executed — both `risk_manager.trigger_emergency_stop` and the API route handler page-only-via-log.
3. **Slo_monitor circuit-breaker** OPENED — only writes a Prometheus gauge + log.
4. **Slo_monitor SLO burn-rate** alerts already pre-classified as `severity=='critical'` — `health_check_loop` re-emits them as `logger.critical` instead of dispatching.

This is V5 S-J3-1 redux: wave-17a/21/41 fixed *some* call sites, missed others.

**Suggested fix:** wire each of the six call sites through `dispatch_alert_from_thread(lambda: send_alert(...))` with the existing wave-41 PP-3 fallback pattern. Categories: `RISK_VIOLATION` for drawdown/emergency-stop, `SYSTEM_ERROR` for circuit-breaker / SLO-burn / forensic regression / read-back invariant.

---

## Finding YY-2 — 17 of 19 `AuditAction` enum values have ZERO emit sites (compliance dead-code)

**Severity:** **HIGH** — direct compliance gap; user MEMORY notes "USER_LOGOUT (added wave-42)" and the YY method requires audit-log reachability per V8 BB-10.

Per AST search (`grep AuditAction\.<NAME>` outside `audit_service.py`):

| AuditAction | Emit sites | Status |
|---|---|---|
| `USER_LOGIN` | 2 (`api/routes/auth.py:330`) | wired |
| `USER_LOGIN_FAILED` | 1 (`api/routes/auth.py:280`) | wired |
| `RISK_LIMIT_BREACH` | 2 (`live_engine.py:2230, 2332`) | wired |
| `EMERGENCY_STOP_TRIGGERED` | **0** | **dead** |
| `EMERGENCY_STOP_RESOLVED` | **0** | **dead** |
| `ORDER_SUBMITTED` | **0** (only the docstring example in `audit_service.py:156`) | **dead** |
| `ORDER_ACCEPTED` / `ORDER_REJECTED` / `ORDER_FILLED` / `ORDER_CANCELLED` | **0** each | **dead** |
| `POSITION_OPENED` / `POSITION_CLOSED` / `POSITION_ADJUSTED` | **0** each | **dead** |
| `MODEL_DEPLOYED` / `MODEL_RETIRED` / `MODEL_PREDICTION` | **0** each | **dead** |
| `STRATEGY_STARTED` / `STRATEGY_STOPPED` / `STRATEGY_UPDATED` / `STRATEGY_ERROR` | **0** each | **dead** |
| `CONFIG_UPDATED` / `RISK_LIMIT_UPDATED` | **0** each | **dead** |
| `USER_LOGOUT` / `USER_CREATED` / `USER_UPDATED` / `USER_DISABLED` | **0** each | **dead** (USER_LOGOUT was claimed wired in MEMORY) |

The `audit_logs` table exists with full migration + index (`migrations/versions/706e00fe1a28_initial_migration_users_orders_.py:48-64`) and `services/audit_service.fire_audit_log` is fully implemented; nothing calls it from the order/position/model/strategy/config paths.

**Operator impact:** for an SEC/FINRA-style audit reconstruction, the `audit_logs` table contains only login attempts and 2 risk-breach types. Every order, every fill, every position-open/close, every emergency stop, every config change, every strategy lifecycle event is invisible from the compliance ledger. The DB is silent on these — not even at 0% sample, simply unwired.

**Reach-verify per V8 BB-10:** the only call sites that reach `fire_audit_log` are `live_engine.py:2228, 2330` (RISK_LIMIT_BREACH for daily-max-loss + drawdown). Everything in `services/order_service.py`, `services/risk_manager.py`, the order routes, the model lifecycle, etc., misses the path.

**Suggested fix:** highest-leverage emit sites:
* `services/order_service.py` order placement / fill webhook → `ORDER_SUBMITTED` / `ORDER_FILLED`.
* `services/risk_manager.py:trigger_emergency_stop` (line 666) → `EMERGENCY_STOP_TRIGGERED` (right beside the `logger.critical` from YY-1).
* `services/risk_manager.py:resolve_emergency_stop` → `EMERGENCY_STOP_RESOLVED`.
* `api/routes/auth.py` logout handler → `USER_LOGOUT` (MEMORY says wired, code says no).

---

## Finding YY-3 — Critical halt events lack dedicated Prometheus counters; bucketed under `ORGANISM_ENTRIES_BLOCKED`

**Severity:** **MEDIUM** — operators cannot Prometheus-distinguish halt causes; PromQL alert authors must scrape logs.

Per the YY method's "must-have-metric" list:

| Event | Dedicated metric? |
|---|---|
| daily_max_loss_halt fired | **No** — only counted in `ORGANISM_ENTRIES_BLOCKED` (live_engine.py:2712), shared with all other entry-block reasons |
| drawdown_kill fired | **No** — `governance.trigger_drawdown_kill` (line 263) only mutates state + emits `logger.critical`; no `Counter.inc()` |
| governance_halt set | **No** — `governance.halt_trading` (line 214) only sets a flag + warning log |
| brain_save_blocked | **No dedicated counter** — wired to alert (wave-41 UU-3) but no Prometheus surface for "denied saves over time" |
| circuit_breaker_tripped | Yes — `circuit_breaker_trips_total` (slo_monitor.py:80), labeled by `error_type` |
| broker_reconnect_attempted | Partial — `stream_reconnects_total` exists; `websocket_max_reconnects_total` defined lazily inside the function (alpaca_stream.py:1051) |
| ml_retrain_failed | **No counter** — see YY-4 below |

`ORGANISM_ENTRIES_BLOCKED` HELP text reads `"Ticks where new entries were blocked (halt/drawdown/insufficient data)"` — the increment site (line 2710) is reached for ANY truthy `_entries_blocked`, regardless of `_last_entries_blocked_reason`. A drawdown-kill, a daily-max-loss halt, and an `equity == 0` situation all increment the same counter and are indistinguishable in Prometheus.

The single label that would split them — `_last_entries_blocked_reason` (set at lines 2183, 2276, 1674, 2358 with values `daily_max_loss`, `drawdown_kill`, `governance_halt`) — exists in memory but is never attached to the metric.

**Suggested fix:** either add label `reason=` to `ORGANISM_ENTRIES_BLOCKED` or add three counters: `organism_drawdown_kill_total`, `organism_daily_max_loss_total`, `organism_governance_halt_total`. The code already has the strings; this is a 3-line patch.

---

## Finding YY-4 — `BackgroundTrainer` *training-failure* is silent; only *executor-exception* is alerted

**Severity:** **MEDIUM** — V8/V9 audits flagged ML signal correctness; this is the loop that produces those signals.

`backend/organism/background_trainer.py` has two distinct failure paths in `get_result()`:

* **Path A — executor-level exception** (line 432): `except Exception` around `self._future.result()`. This path was hardened in wave-20a (`V6 V-T-2`) with a full `dispatch_alert_from_thread → send_alert(SYSTEM_ERROR, WARNING, "ML Retrain Failed", ...)` block (line 440-460).
* **Path B — training-internal failure** (line 466-471): worker subprocess returned a dict with `"error"` key but no `"accepted"` key (i.e., the training subprocess caught an internal exception and returned it as a payload). This path emits **only** `logger.warning("BackgroundTrainer training failed: %s", raw["error"])` — no alert dispatch, no Prometheus counter.

So:
* If the executor crashes (rare, infra issue) → operator paged.
* If the training algorithm itself fails (more common — bad features, divergence, fit error) → operator never sees it; the engine continues to use the stale model.

There's also no `ml_retrain_failures_total` Prometheus counter (the "must-have" from the YY method list). The only training-related metric is implicit (`organism_direction_accuracy` Gauge), which goes flat *after* failure but doesn't tell you it failed.

Note: the user MEMORY warns `corr(confidence, correct_direction) = -0.112` (anti-predictive ML); a silent retrain-failure path is exactly the kind of bug that produces that signature — a model that fails to retrain stays anti-predictive forever, with no operator surface.

**Suggested fix:** mirror lines 440-460 immediately above line 472, and define a counter `ml_retrain_total` with label `outcome={success,executor_error,training_error,quality_rejected}` to give a single PromQL expression for "training health".

---

## Finding YY-5 — `/readyz` returns 200 even when brain is unloaded or main loop is stalled

**Severity:** **MEDIUM** — Kubernetes traffic routing decisions are based on `/readyz`. The current implementation in `backend/api/routes/health.py:119-195` (`get_readiness_status`) checks **only**:

1. `check_database_health()` — DB reachable in <100ms.
2. `check_broker_health()` — broker reachable in <200ms.

It does NOT check:

* **Brain loaded** (`live_engine._is_brain_loaded` / `signal_gen._is_trained`). A pod that came up after a brain-corruption restart can serve traffic before the brain is restored.
* **Main loop running** (`live_engine._tick_count` increasing, last-tick timestamp recent). A pod whose tick loop has died but FastAPI is still up will report ready=true.
* **Engine started** (`engine_started_event.is_set()`). Per V9 PP/UU, several routes raise 503 if the engine isn't started; readiness doesn't anticipate this.

The YY method spec says readiness must check "DB reachable + brain loaded + main loop running"; the code checks only the first.

There is also a *second* readiness implementation at `backend/infra/production.py:610` (`ProductionReadiness.readiness_check`) that uses `self._readiness == ReadinessStatus.READY and self.health.is_healthy()`, but `factory.py` wires `/readyz` through `create_health_endpoints()` (the lighter check), not through `production.readiness_check` (which the dedicated `/api/v1/health/ready` route at `api/health.py:96` uses). **Two readiness implementations exist; the cluster-facing one is the lighter of the two.**

**Suggested fix:** in `health.py:get_readiness_status`, add `await check_engine_loop_alive()` and `check_brain_loaded()` before the response. Single-source the implementation by routing both `/readyz` and `/api/v1/health/ready` through the same function.

---

## Severity-routing audit (alerting.py)

Method spec vs. code:

| Severity | Spec | Code (`alerting.py:281-307`) |
|---|---|---|
| INFO | log only | **Slack always** if webhook configured (line 285 unconditional). PagerDuty: never. |
| WARNING | Slack only (production) | Slack always; PagerDuty only if `environment == "production"` (line 292). |
| ERROR | Slack + PagerDuty | Slack always; PagerDuty always (line 291). |
| CRITICAL | Slack + PagerDuty + log fallback | Slack always; PagerDuty always; log-fallback if no channels OR delivery fails (lines 298-307, 322-327). Wave-41 PP-3 hardened this. |

**Drift from spec:** INFO-severity alerts go to Slack in dev/staging too. This is *more* lenient than spec, not less, so it's not a paging gap — it's signal-noise risk in dev channels. L-25 market-hours suppression at line 254 *does* suppress INFO/WARNING outside market hours, partially mitigating.

Critical bypass of dedup + rate-limit (line 251 `_is_critical`) is correctly implemented per wave-41 PP-3.

---

## Silent-error path baseline

AST scan: **283 broad `except Exception`** blocks log-and-swallow without `raise` and without an `send_alert`/`dispatch_alert_from_thread` call inside the handler. Top concentrations:

| File | Count |
|---|---|
| `models/ensemble_model.py` | 16 |
| `analytics/realtime_risk_analytics.py` | 16 |
| `api/socketio_server.py` | 15 |
| `integrations/alpaca_stream.py` | 12 |
| `integrations/alpaca_market_data_stream.py` | 12 |
| `ml/model_manager.py` | 12 |
| `data/social_sentiment.py` | 11 |
| `infra/users.py` / `organism/brain_persistence.py` / `risk/risk_manager.py` / `services/order_service.py` | 8 each |

Not all of these are bugs (some are legitimate "metrics-emit best-effort"), but it's a baseline for future tracks (V11) — particularly `services/order_service.py` and `risk/risk_manager.py` deserve targeted sweeps because a swallowed exception there silently mutates trading state.

---

## Runbook coverage

`docs/INCIDENT_RESPONSE_RUNBOOK.md` (330 lines) covers:
1. Drawdown Kill, 2. Data Feed Failure, 3. Broker Outage / Stream Disconnect, 4. Brain Corruption, 5. Manual Flat All, 6. Rollback, 7. Prometheus Alert Thresholds.

**No runbook entry for:** Daily Max-Loss Halt, Emergency Stop trigger/resolve, Circuit Breaker open, SLO burn-rate alert, Forensic Guard fire, Brain Manifest read-back fail, ML Retrain failure, C1/C2 Watchdog state. These align 1:1 with the unwired sites in YY-1 and YY-4 — no alert + no runbook = the operator gets nothing on either pager OR doc-search.

`docs/architecture/mapss.md:2603-2606` lists the AlertCategory enum but no runbook anchors per category.

---

## TL;DR

The platform's observability has **clean alert plumbing** (`alerting.py` is well-structured with dedup, rate-limit, market-hours suppression, severity routing, and a wave-41 critical-bypass + log-fallback) but **incomplete connections to that plumbing**: 6 of 16 `logger.critical` sites — including drawdown-kill, emergency-stop, circuit-breaker, and SLO burn — never call `send_alert`, so the most consequential portfolio events are pager-silent (V5 S-J3-1 redux in code paths that wave-17a/21/41 didn't reach). The compliance audit log is even more under-wired: only `USER_LOGIN`, `USER_LOGIN_FAILED`, and `RISK_LIMIT_BREACH` actually emit; **17 of 19** `AuditAction` enum values (every order, every position, every emergency stop, every config change, MEMORY-claimed `USER_LOGOUT`) have zero call sites — the `audit_logs` table is structurally ready but operationally unused. Halt-cause Prometheus counters are bucketed under one `organism_entries_blocked_total` (the differentiating reason exists in memory but isn't attached as a label), the BackgroundTrainer's *internal* training-failure path is alert-silent (only the executor-crash path is wired), and `/readyz` checks DB+broker but not brain-loaded or tick-loop-alive (with two competing readiness implementations, the cluster-facing one being the lighter). Five findings; YY-1 and YY-2 are the headline pager/compliance gaps and the cleanest pre-deploy patches.
