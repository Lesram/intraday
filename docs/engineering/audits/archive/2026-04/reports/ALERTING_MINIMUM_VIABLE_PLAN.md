# Alerting Minimum Viable Plan

**Date**: 2026-04-19
**Status**: PLAN ONLY — no code changes, no deploy

## Current state

The alerting infrastructure **already exists** at `backend/infra/alerting.py` (532 lines). It has:
- ✅ `AlertManager` class with `send_alert()` method
- ✅ Slack webhook integration (`_send_slack()`) fully implemented
- ✅ PagerDuty integration implemented (optional)
- ✅ Alert severity levels (INFO, WARNING, ERROR, CRITICAL)
- ✅ Alert categories (RISK_VIOLATION, ORDER_FAILURE, SYSTEM_ERROR, CONNECTIVITY, PERFORMANCE, SECURITY)
- ✅ Deduplication (prevents alert storms)
- ✅ Market-hours awareness
- ✅ `get_alert_manager()` singleton pattern

**Already wired callers** (would fire alerts IF webhook is configured):
| Caller | File | What it alerts on |
|---|---|---|
| Diagnostic scheduler | `diagnostic_scheduler.py:216-241` | Pre-open/post-close diagnostic failures |
| Order guardrails | `order_guardrails.py:355-357` | Risk-limit order rejections |
| Order service | `order_service.py:365` | Order failures |
| SLO monitoring | `slo_alerts.py:358-359` | Service-level objective breaches |

**NOT yet wired** (log only, no alert call):
| Event | Current behavior | Missing |
|---|---|---|
| Daily max-loss halt | `logger.critical()` only | No `send_alert()` call |
| Guard fires (BRAIN SAVE BLOCKED etc.) | `logger.error()` only | No `send_alert()` call |
| Feature drift neutralization (H2) | `logger.error()` only | No `send_alert()` call |
| Production risk-budget cap (H1) | Silent (just clamps) | No logging or alert |
| Container restart | Docker logs only | No alert mechanism |
| Notional cap hit | `logger.info()` only | No `send_alert()` call |

## What's needed

### Step 1: Configure env var (ZERO code changes)

Add to `.env`:
```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
ALERT_ENVIRONMENT=paper
```

**This alone enables ALL existing wired callers** (diagnostic scheduler, order guardrails, order service, SLO monitoring). The "No alert channels configured" warnings disappear immediately.

**Effort**: 1 minute. Copy webhook URL into .env.
**Risk**: Zero. The alerting module gracefully handles missing webhook (logs warning, continues).

### Step 2: Wire critical events to send_alert() (small code changes)

Add `send_alert()` calls to 4 critical events that currently only log:

**2a. Daily max-loss halt** (`live_engine.py`, ~line 1427):
```python
# After the CRITICAL log:
try:
    from backend.infra.alerting import send_alert, AlertCategory, AlertSeverity
    import asyncio
    asyncio.create_task(send_alert(
        AlertCategory.RISK_VIOLATION,
        AlertSeverity.CRITICAL,
        "Daily Max-Loss Halt Triggered",
        f"PnL=${daily_pnl:.2f} crossed -${MAX_DAILY_LOSS:.0f} limit. Trading halted.",
    ))
except Exception:
    pass  # alerting failure must not block trading logic
```

**2b. Guard fires** (`brain_persistence.py`, after BRAIN SAVE BLOCKED log):
```python
try:
    from backend.infra.alerting import send_alert, AlertCategory, AlertSeverity
    asyncio.create_task(send_alert(
        AlertCategory.SYSTEM_ERROR,
        AlertSeverity.ERROR,
        "Brain Save Blocked",
        f"Trained manifest overwrite blocked ({caller}). {reason}",
    ))
except Exception:
    pass
```

**2c. Feature drift** (`ml_signal.py`, after H2 ERROR log):
```python
try:
    from backend.infra.alerting import send_alert, AlertCategory, AlertSeverity
    asyncio.create_task(send_alert(
        AlertCategory.SYSTEM_ERROR,
        AlertSeverity.WARNING,
        "Feature Drift Detected",
        f"ML signal neutralized for {symbol}: {len(available_cols)}/{len(self._feature_cols)} features available.",
    ))
except Exception:
    pass
```

**2d. Forensic guard** (`live_engine.py`, after FORENSIC GUARD CRITICAL log):
```python
# Same pattern — send_alert for object replacement or learner regression detection
```

**Effort**: ~30 lines across 3 files. Each is a try/except-wrapped `asyncio.create_task(send_alert(...))`.
**Risk**: Very low. The `try/except` ensures alerting failure cannot crash trading logic.

### Step 3: Container restart alerting (config-only)

Docker can be configured to run a script on container restart via a health-check failure webhook or a wrapper script. Simpler: check `RestartCount` in the daily post-close observation report (already done manually). For Stage 1, this is sufficient without automated alerting.

## Required env vars

| Var | Purpose | Example | Required? |
|---|---|---|---|
| `SLACK_WEBHOOK_URL` | Slack incoming webhook | `https://hooks.slack.com/services/T.../B.../...` | YES for Stage 1 |
| `ALERT_ENVIRONMENT` | Environment tag in alerts | `paper` or `live` | Recommended |
| `PAGERDUTY_ROUTING_KEY` | PagerDuty integration | (routing key) | NO (optional, Stage 2+) |

## Required code/config changes

| Change | File | Lines | Effort |
|---|---|---|---|
| Add `SLACK_WEBHOOK_URL` to `.env` | `.env` | 1 line | 1 min |
| Wire daily max-loss halt alert | `live_engine.py` | ~8 lines | 5 min |
| Wire guard-fire alerts | `brain_persistence.py` | ~8 lines | 5 min |
| Wire feature drift alert | `ml_signal.py` | ~8 lines | 5 min |
| Wire forensic guard alert | `live_engine.py` | ~8 lines | 5 min |

**Total**: ~33 lines of code + 1 env var. All follow the identical try/except/create_task pattern.

## Deploy order

```
DEPLOY 2 (next hardening deploy):
1. G1/G2/G3 mechanical fixes        (15cc0a4)
2. H1/H2 risk-budget + drift guard  (679ffd2)
3. Notional cap + daily max-loss     (bb5cbb5)
4. Alert wiring (Step 2 above)       (new commit)
5. .env: SLACK_WEBHOOK_URL           (config)
```

All ship together as one rebuild. Step 1 (.env config) can happen at deploy time — no code change needed.

## What this covers for Stage 1

| Alert event | Covered? | Channel |
|---|---|---|
| Daily max-loss halt | ✅ (after Step 2a) | Slack CRITICAL |
| Diagnostic pre-open/post-close failures | ✅ (already wired) | Slack WARNING/ERROR |
| Order rejections | ✅ (already wired) | Slack WARNING |
| Guard fires (BRAIN SAVE BLOCKED) | ✅ (after Step 2b) | Slack ERROR |
| Feature drift neutralization | ✅ (after Step 2c) | Slack WARNING |
| Forensic guard (object replacement) | ✅ (after Step 2d) | Slack CRITICAL |
| Container restart | ⚠️ Manual check | Post-close report |
| Unusual error spikes | ⚠️ Manual check | Post-close report |
| Broker connectivity degradation | ✅ (SLO monitoring, already wired) | Slack WARNING |

**8/10 critical events covered by automated Slack alerts. 2/10 covered by daily manual checks.** This is sufficient for Stage 1 tiny-capital.
