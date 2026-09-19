# Error Handling Discipline

**Date:** 2026-05-03 (V10 wave-57)
**Status:** ruff config shipped; backlog grandfathered via per-file-ignores.

V9 UU and V10 UU2 audits documented a long-standing pattern of cargo-cult
exception handling that masks real failures.  V5 S-J3-1 took 4 audit
rounds to surface because of this.  Wave-57 ships the lint rule that
prevents new code from joining the pile.

## The pattern

```python
# BAD — cargo-cult
try:
    do_something()
except Exception:
    pass
```

This swallows every error including `KeyboardInterrupt` (when subclassed
broadly), `MemoryError`, `SystemExit`, and the actual failure that
operators need to know about.

## The rules (ruff)

| Rule | What it catches |
|---|---|
| `S110` | `try/except/pass` — the V9 UU-4 cargo-cult shape |
| `S112` | `try/except/continue` — the same shape inside loops |
| `BLE001` | `except Exception` — too-broad exception spec |
| `G004` | logging-f-string — eager string formatting in log handlers |
| `TRY401` | `logger.error("...", exc)` — should use `.exception()` for traceback |
| `LOG007` | `logger.error()` without `exc_info=True` in an `except` block |

## How to comply

### Instead of `try/except/pass`:

```python
# GOOD — log at appropriate level
try:
    do_something()
except SomeSpecificError as e:
    logger.warning("do_something failed (continuing): %s", e)
```

### Instead of `except Exception`:

```python
# GOOD — name the exceptions you actually expect
try:
    do_something()
except (ValueError, KeyError) as e:
    logger.error("do_something parse error: %s", e)
```

### Instead of f-strings in handlers:

```python
# BAD — evaluates the format even at INFO level
logger.error(f"Failed: {expensive_computation()}")

# GOOD — lazy %-style
logger.error("Failed: %s", expensive_computation())
```

### Instead of `logger.error("...", exc)`:

```python
# BAD
try:
    do_something()
except Exception as e:
    logger.error("Failed: %s", e)

# GOOD — captures full traceback
try:
    do_something()
except Exception as e:
    logger.exception("Failed")  # implicit exc_info
    # OR
    logger.error("Failed", exc_info=True)
```

## Grandfather ratchet

The existing 158 pass-only handlers + 459 f-string-in-handler usages are
grandfathered via per-file-ignores in `pyproject.toml`.  Files in the
ignore list:

- `backend/organism/live_engine.py`
- `backend/organism/brain_persistence.py`
- `backend/integrations/alpaca_stream.py`
- `backend/services/audit_service.py`
- `backend/api/socketio_server.py`
- `backend/services/realtime_risk_analytics.py`
- `backend/ml/ensemble_model.py`

Tests are exempt globally (test code legitimately catches everything).

**New files** in `backend/` get no exemption — they must comply from
day one.

**Removing a file from the ignore list** is the V11+ cleanup goal.
Aim: one file per audit cycle.

## Helpful patterns

### Best-effort with mandatory log

```python
def fire_audit_log_threadsafe(...) -> None:
    """V8 Wave-30: best-effort.  Errors logged + swallowed."""
    try:
        ...
    except Exception as e:
        logger.warning("BB-10: audit log fire failed: %s", e)
```

This is the V8/V9 canonical pattern for "we want to ship even if
secondary path fails."  `logger.warning` is the floor; nothing silently
disappears.

### Cross-thread alert dispatch

```python
from backend.infra.alerting import (
    AlertCategory, AlertSeverity, send_alert,
    dispatch_alert_from_thread,
)
ok = dispatch_alert_from_thread(
    lambda: send_alert(...)
)
if not ok:
    logger.warning("alert dropped (no main loop ref)")
```

Use this everywhere instead of `asyncio.create_task(send_alert(...))`
in worker-thread context.  The V5 S-J3-1 / wave-41 PP-3 / wave-52 YY-1
fixes all converge on this pattern.

## Future directions

- **V11**: surgical cleanup of one file per cycle from the ignore list.
- **V11+**: extend the lint set to forbid `asyncio.create_task(send_alert(...))`
  pattern via a custom AST hook in `scripts/ci/post_edit_verify`.
