# Track V v6 — Telemetry Coverage Audit

V5's headline finding (S-J3-1) was that wave-8c's J-3 alert "fix" was
load-bearing-broken: alerts went to `logger.warning` and never reached
Slack/PagerDuty. The fix was in the code; the *behavior* was missing.

Track V generalizes: for every metric / alert / log-event the platform
declares, verify it actually fires at the right moment. Phantom telemetry
is more dangerous than no telemetry — it creates false confidence.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `3f660f4`.

## Files in scope

- `backend/organism/live_engine.py` — ORGANISM_* Prometheus metrics (12 of them)
- `backend/infra/alerting.py` — AlertManager + send_alert + dispatch_alert_from_thread
- `backend/observability/` — metrics, tracing
- `backend/api/factory.py`, `backend/api/routes/system.py` — `/metrics` endpoints
- All call sites that emit metrics or alerts

## Method

### 1. Prometheus metric inventory + emission audit

For each ORGANISM_* metric declared at module level in live_engine.py:87-136:

| Metric | Should fire when | Actual emission site | Tested? |
|---|---|---|---|
| ORGANISM_TICK_DURATION (Histogram) | every tick | `live_engine.py:?` | ? |
| ORGANISM_GENERATION (Gauge) | post-evolution | ? | ? |
| ORGANISM_DIRECTION_ACCURACY (Gauge) | post-eval | ? | ? |
| ORGANISM_SHARPE (Gauge) | post-eval | ? | ? |
| ORGANISM_TOTAL_TRADES (Gauge) | post-trade | ? | ? |
| ORGANISM_ORDERS_SUBMITTED (Counter) | per submit | ? | ? |
| ORGANISM_ERRORS (Counter) | per tick error | ? | ? |
| ORGANISM_HALTED_WITH_POSITIONS (Counter) | conditional | ? | ? |
| ORGANISM_EXITS_SKIPPED_NO_DATA (Counter) | conditional | ? | ? |
| ORGANISM_SECTOR_CAP_BLOCKED (Counter) | conditional | ? | ? |
| ORGANISM_SAFETY_NET_TRIGGERED (Counter) | conditional | ? | ? |
| ORGANISM_ENTRIES_BLOCKED (Counter) | conditional | ? | ? |

For each:
- Find the `.set()` / `.inc()` / `.observe()` call site.
- If 0 call sites: phantom (declared but never emitted) — bug.
- If call sites exist: are they on the actually-reachable path?
- Live-probe: hit `/api/v1/system/metrics` and grep the metric name. If it
  appears with value 0, has it ever incremented? Compare against logs.

### 2. Alert path coverage

For each `send_alert(...)` call in `backend/`:

| Site | Severity | Trigger condition | Reachable from worker thread? | Uses dispatch_alert_from_thread? |
|---|---|---|---|---|
| (enumerate via grep) | | | | |

The wave-17a fix introduced `dispatch_alert_from_thread`. Every alert from a
sync path that may be reached via `asyncio.to_thread` MUST use it. Sites that
use raw `_aio.create_task(send_alert(...))` from a sync path are bugs.

For each alert site:
- Find via grep.
- Trace upstream — is this site ever called from `to_thread`?
- If yes: must use `dispatch_alert_from_thread`.
- If no: raw `create_task` is fine but document.

Plus: verify that the captured main loop reference (post wave-17a)
actually persists and is reachable from `dispatch_alert_from_thread`.
Live-probe: synthesize a worker-thread alert from the running container's
shell and confirm it reaches the AlertManager.

### 3. Critical-event alert coverage matrix

For each high-blast event, verify the alert path is wired AND tested:

| Event | Alert wired? | Worker-thread-safe? | Test exists? |
|---|---|---|---|
| Drawdown-kill triggered | ? | ? | ? |
| Brain save failure | ? | ? | ? |
| Reconciliation orphan adopted | ? | ? | ? |
| ML retrain failure | ? | ? | ? |
| Broker submission 5xx burst | ? | ? | ? |
| Streaming WS disconnect > 60s | ? | ? | ? |
| Database connection failure | ? | ? | ? |
| Tick loop hang (no tick > 30s) | ? | ? | ? |
| Pyramid layer add failure | ? | ? | ? |
| Stop-out with negative giveback | ? | ? | ? |
| Forensic-guard object identity change | ? | ? | ? |
| Walk-forward Sharpe regression | ? | ? | ? |
| Daily max-loss halt | ? | ? | ? |
| Circuit breaker (technical) opens | ? | ? | ? |
| Outbox lease near-expiry | ? | ? | ? |

For each row: locate the trigger code, locate the alert call, check that an
end-to-end test exercises both. If trigger has no alert, bug. If alert has
no test, bug-adjacent (regression risk).

### 4. Log-level audit (sample 200 lines)

Sample 200 random lines from `docker logs intra-api-1` and triage each:
- INFO that should be DEBUG (noise)
- WARNING that should be ERROR (operator misses)
- ERROR that should be WARNING (false alarm)

Compute the noise/signal ratio. Surface the top 3 noisiest log emitters.

### 5. /metrics endpoint live verification

`curl -s http://localhost:8000/api/v1/system/metrics | head -200` →
- Count organism_* lines (should be ≥10 post wave-12e + 17a).
- For each, what's the current value? Compare against logged events.

Cross-check: if `ORGANISM_GENERATION` says 168 but
`organism_brain/manifest.json:generation == 168`, that's correct. If they
disagree, either the metric isn't being updated or the manifest isn't.

### 6. Trace coverage

V3 + V4 didn't audit OpenTelemetry trace coverage. For each tick-internal
operation (alpha_scan, ml_predict, kelly_size, submit_order):
- Is it inside a `trace_span`?
- If not, do we have any latency observability?

### 7. Phantom-metric regression test

Write a test that hits `/api/v1/system/metrics` and asserts every declared
`ORGANISM_*` metric appears in the response. This pins the wave-12e fix.

## Output

`artifacts/audit/v6_reports/track_v_telemetry_coverage.md` with:
- Metric × emission-site × tested? matrix
- Alert × thread-context × dispatch-pattern matrix
- Critical-event coverage matrix
- Log-level sample triage (200 lines)
- /metrics live snapshot
- Trace coverage gaps
- "Phantom items found: N" + TL;DR

## Constraints

Read-only. `docker logs`, `curl`, `pytest` ok.

## Quality bar

Expect 5-12 issues. Especially:
- Metric declared but never .inc()'d (phantom)
- Alert reachable from worker thread without dispatch_alert_from_thread (S-J3-1 class)
- Critical event with no alert wiring
- INFO log volume > 90% noise

End with a one-paragraph summary.
