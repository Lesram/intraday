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


def test_yy_5_readyz_checks_brain_and_tick(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from backend.api.routes import health
    from backend.organism import scheduler as scheduler_module

    sched = SimpleNamespace(
        is_running=True, _stop=asyncio.Event(), _tick_interval=10,
        _engine=SimpleNamespace(_initialized=True, brain=SimpleNamespace(_loaded=False)),
        _readiness_started_at=100.0, _readiness_last_loop_at=990.0,
        _readiness_tick_expected_since=500.0, _readiness_last_tick_completed_at=900.0,
    )
    state = SimpleNamespace(organism_scheduler=sched)
    monkeypatch.setattr(scheduler_module, "_is_market_tick_window", lambda: True)
    checks, result = health._runtime_check(state, 1000.0)
    assert checks["brain_loaded"] is False
    assert result.state == "brain_unloaded"
    sched._engine.brain._loaded = True
    checks, result = health._runtime_check(state, 1000.0)
    assert checks["tick_recent"] is False
    assert result.state == "tick_stale"
    sched._readiness_last_tick_completed_at = 990.0
    checks, result = health._runtime_check(state, 1000.0)
    assert all(checks.values())
    assert result.state == "tick_recent"
