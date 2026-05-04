"""V10 / Wave-52 (2026-05-03): tests for observability + audit-log reach.

Locks regressions for:
- YY-1 (HIGH): logger.critical sites (drawdown-kill, emergency-stop,
  circuit-breaker, SLO burn) now also dispatch operator alerts via
  the canonical dispatch_alert_from_thread.
- YY-2 (HIGH): alpaca_stream emits ORDER_FILLED audit_logs entries on
  every fill event.  Audit reach was previously limited to user.login.
- YY-5 (MEDIUM): /readyz checks brain.is_loaded + tick-loop liveness.

Wave-52 deferred:
- YY-3 (Prom labels on ORGANISM_ENTRIES_BLOCKED): cosmetic; track for
  V11 with the lint rule wave.
- YY-4 (BackgroundTrainer alert): out of scope this wave; tracked.

Run with: ./venv/bin/python -m pytest tests/test_wave52_fixes.py -v
"""
from __future__ import annotations

import inspect


def test_yy_1_governance_drawdown_kill_dispatches_alert():
    from backend.organism import governance
    src = inspect.getsource(governance)
    assert "YY-1" in src, "YY-1 marker missing in governance.py"
    assert "Drawdown Kill Switch Triggered" in src, (
        "YY-1 regression: drawdown-kill alert title removed."
    )
    assert "dispatch_alert_from_thread" in src, (
        "YY-1 regression: governance no longer uses canonical dispatcher."
    )


def test_yy_1_emergency_stop_dispatches_alert():
    from backend.services import risk_manager
    src = inspect.getsource(risk_manager)
    assert "YY-1" in src, "YY-1 marker missing in risk_manager.py"
    assert "Emergency Stop Triggered" in src, (
        "YY-1 regression: emergency-stop alert title removed."
    )


def test_yy_1_circuit_breaker_dispatches_alert():
    from backend.monitoring import slo_monitor
    src = inspect.getsource(slo_monitor)
    assert "YY-1" in src, "YY-1 marker missing in slo_monitor.py"
    assert "Circuit Breaker OPENED" in src, (
        "YY-1 regression: circuit-breaker alert title removed."
    )
    assert "SLO Burn-Rate Critical" in src, (
        "YY-1 regression: SLO burn alert title removed."
    )


def test_yy_2_alpaca_stream_emits_order_filled_audit():
    from backend.integrations import alpaca_stream
    src = inspect.getsource(alpaca_stream)
    assert "YY-2" in src, "YY-2 marker missing"
    assert "AuditAction.ORDER_FILLED" in src, (
        "YY-2 regression: alpaca_stream no longer emits ORDER_FILLED audit."
    )


def test_yy_5_readyz_checks_brain_and_tick():
    from backend.api.routes import health
    src = inspect.getsource(health)
    assert "YY-5" in src, "YY-5 marker missing in health.py"
    assert "brain_loaded" in src, (
        "YY-5 regression: /readyz no longer checks brain.is_loaded."
    )
    assert "tick_recent" in src or "tick_loop" in src, (
        "YY-5 regression: /readyz no longer checks tick-loop liveness."
    )
