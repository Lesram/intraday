# Track YY v10 — Observability Completeness (NEW LENS)

V9 PP/UU surfaced "operator paging silently broken" pattern (V5 S-J3-1 redux). **YY enumerates every operator-facing event and verifies it surfaces somewhere.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `35a1fe9`.

## Method

### 1. logger.error / logger.critical site enumeration

```
./venv/bin/python - <<'PY'
import ast, pathlib

sites = []
for p in pathlib.Path("backend").rglob("*.py"):
    if "test" in str(p) or "__pycache__" in str(p):
        continue
    try:
        tree = ast.parse(p.read_text())
    except Exception:
        continue
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "logger"
            and node.func.attr in ("error", "critical", "warning")):
            sites.append((str(p), node.lineno, node.func.attr))

print(f"Total sites: {len(sites)}")
print(f"  critical: {sum(1 for _,_,l in sites if l == 'critical')}")
print(f"  error: {sum(1 for _,_,l in sites if l == 'error')}")
print(f"  warning: {sum(1 for _,_,l in sites if l == 'warning')}")

# Sample 20 critical sites.
for s in [(p, l, lvl) for p, l, lvl in sites if lvl == "critical"][:20]:
    print(f"  {s[2].upper()}: {s[0]}:{s[1]}")
PY
```

### 2. Alert-channel coverage

For each `logger.critical` site, verify there's an accompanying `send_alert` or `dispatch_alert_from_thread` call within the same function/block. Sites that log CRITICAL but don't dispatch an alert = silent CRITICAL.

### 3. Prometheus metric coverage

```
grep -rn "Counter\|Gauge\|Histogram\|Summary" backend/ --include='*.py' | grep -v test | head -30
```

For each metric name, identify where it's incremented/observed. Identify metrics that are DEFINED but never .inc()'d / .observe()'d.

### 4. Critical-events-without-metric audit

Specific events that should ALWAYS have a metric:
- daily_max_loss_halt fired
- drawdown_kill fired
- governance_halt set
- brain_save_blocked
- circuit_breaker_tripped (any)
- broker_reconnect_attempted
- ml_retrain_failed

For each, find the metric counter; if missing, file as finding.

### 5. Health-check completeness

`/api/v1/system/health`, `/healthz`, `/livez`, `/readyz` — what do they each check?
- Liveness: process up.
- Readiness: DB reachable + brain loaded + main loop running.
- Health: all components healthy.

Identify any health endpoint that returns 200 even when a critical subsystem (DB, broker, brain) is degraded.

### 6. Tracing completeness

Are tick boundaries traced (OpenTelemetry / Jaeger)? Are key spans named? Are span attributes propagated for correlation?

### 7. Alerts-without-runbook

For each AlertCategory enum value, is there a runbook entry (in docs/) describing operator response? Identify alerts with no runbook.

### 8. Audit-log completeness for compliance events

Compliance events that MUST land in `audit_logs`:
- USER_LOGIN, USER_LOGIN_FAILED (verified V8 BB-10)
- ORDER_SUBMITTED, ORDER_FILLED, ORDER_CANCELED
- POSITION_OPEN, POSITION_CLOSE
- RISK_LIMIT_BREACH (verified V8 BB-10 daily-loss)
- USER_LOGOUT (added wave-42)

For each, verify:
- A code site exists that emits this AuditAction.
- The site is reachable (per V8 BB-10 + V9 BB3 reach verification).

### 9. Slack vs PagerDuty severity routing

For each AlertSeverity:
- INFO: log only.
- WARNING: Slack only (production), nothing in dev.
- ERROR: Slack + PagerDuty.
- CRITICAL: Slack + PagerDuty + log.critical fallback.

Verify each severity correctly routes (post-wave-41 PP-3 escalation logic).

### 10. Log structure consistency

V9 UU census noted 513 eager f-strings vs 131 lazy. Identify logger calls with multi-line / unstructured payloads that hurt log search:

```
grep -rn 'logger\.\(error\|critical\|warning\)(f"' backend/ --include='*.py' | head -10
```

For each, propose a structured replacement.

## Output

`artifacts/audit/v10_reports/track_yy_observability_completeness.md` with:
- logger.critical site catalog (~20 sites)
- Alert-channel coverage table
- Prometheus metric coverage
- Critical-events-without-metric findings
- Health-check completeness
- Audit-log completeness for compliance events
- Severity routing audit
- Recommended runbook + structured-log gaps

Quality bar: 2-5 findings. **First-time lens; expect 3-5 surfaced**.
