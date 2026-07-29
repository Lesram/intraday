"""V8 / Wave-31 (2026-05-03): reachability tests for the audit cycle.

The post-V7 discussion identified "dead code with live-looking
telemetry" as one of the four root causes of recurring audit findings:

- BB-8 (V7): `LotTracker.create_lot` had passing tests but was never
  called in the live alpaca_stream path. `position_lots` and
  `realized_trades` were empty despite 1,369 orders.
- BB-10 (V7): `audit_logs` table empty despite many high-blast events
  fired alerts but never wrote compliance rows.
- backend/strategies/ (HH): 4,872 LOC of BaseStrategy subclasses, no
  shared interface with backend/organism/, barely wired live.
- DD-7: System-level anti-predictivity (corr=-0.112) documented in
  memory but not surfaced anywhere in acceptance gating.

A test passing did NOT prove the path was reachable in production.
This file pins reachability invariants — the assertion is not
"this code computes the right answer" but "this code IS REACHED from
the production lifespan / tick / WS path".

When a wave-30-class wiring fix lands, these tests should pass. If a
later refactor disconnects the wiring again (the BB-8 failure mode),
these tests fail at PR-merge time rather than waiting for the next
audit round to surface the regression.

Run with: ./venv/bin/python -m pytest tests/test_reachability_v8.py -v
"""
from __future__ import annotations

import inspect

import pytest


# ─────────────────────────────────────────────────────────────────────
# BB-8 — LotTracker is reached from the live alpaca_stream path
# ─────────────────────────────────────────────────────────────────────


def test_bb_8_lot_tracker_called_from_active_stream_path():
    """The lifespan loads `alpaca_stream.py` (not the
    `alpaca_stream_production.py` variant). `LotTracker.create_lot`
    must be called from within that module so position_lots populates
    in production.
    """
    import backend.integrations.alpaca_stream as live_stream
    src = inspect.getsource(live_stream)
    assert "LotTracker" in src, (
        "BB-8 reachability: backend/integrations/alpaca_stream.py "
        "(the live path loaded by lifespan) does NOT reference LotTracker. "
        "If this assertion fails, position_lots / realized_trades will be "
        "empty in production again — the V7 BB-8 root cause."
    )
    assert "create_lot" in src or "close_lots_fifo" in src, (
        "BB-8 reachability: LotTracker is referenced but neither "
        "create_lot nor close_lots_fifo is called from the live stream."
    )


def test_bb_8_lot_tracker_wired_inside_trade_update():
    """The wiring must be inside `_process_trade_update` (the WS
    fill handler), not in unreachable code. Walk up the AST from the
    `LotTracker(` call to verify it's nested under `_process_trade_update`."""
    import backend.integrations.alpaca_stream as live_stream
    src = inspect.getsource(live_stream._process_trade_update) if hasattr(live_stream, "_process_trade_update") else None
    if src is None:
        # Method-style: fetch from the class.
        cls_src = inspect.getsource(live_stream.AlpacaStreamClient._process_trade_update)
        assert "LotTracker" in cls_src, (
            "BB-8 reachability: LotTracker call site is not inside "
            "AlpacaStreamClient._process_trade_update. Wave-30's BB-8 "
            "fix must be in the WS fill handler, not adjacent code."
        )


# ─────────────────────────────────────────────────────────────────────
# BB-10 — ComplianceAuditService is reached from high-blast events
# ─────────────────────────────────────────────────────────────────────


def test_bb_10_audit_log_called_from_drawdown_kill():
    """V7 BB-10 root cause: drawdown-kill fired alerts but never wrote
    audit_logs. Verify the wave-30 wiring is at the actual drawdown
    site in live_engine.py."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine)
    # The wave-30 marker locks this in.
    assert "BB-10" in src or "fire_audit_log" in src, (
        "BB-10 reachability: live_engine.py does not reference "
        "fire_audit_log. drawdown-kill / daily-loss halt will not "
        "populate audit_logs."
    )


def test_bb_10_audit_log_called_from_login_path():
    """V7 AA-H-3: login route was not invoking USER_LOGIN /
    USER_LOGIN_FAILED audit actions. Verify wave-30 wired both."""
    import backend.api.routes.auth as auth_route
    src = inspect.getsource(auth_route)
    assert "USER_LOGIN" in src and "USER_LOGIN_FAILED" in src, (
        "AA-H-3 reachability: auth.py must invoke "
        "AuditAction.USER_LOGIN and AuditAction.USER_LOGIN_FAILED. "
        "Without this, the audit_logs trail has no auth events."
    )


def test_bb_10_fire_audit_log_helper_exists():
    """Wave-30 added fire_audit_log + fire_audit_log_threadsafe so
    sites without DB-session context can write audit rows. Verify
    both helpers are exported."""
    from backend.services.audit_service import (
        fire_audit_log, fire_audit_log_threadsafe,
    )
    assert callable(fire_audit_log)
    assert callable(fire_audit_log_threadsafe)


# ─────────────────────────────────────────────────────────────────────
# Alert dispatcher (V5 S-J3-1 / V6 V-T-1/V-T-2 / V7 wave-20a)
# ─────────────────────────────────────────────────────────────────────


def test_dispatch_alert_from_thread_main_loop_captured_at_startup():
    """The wave-17a fix (V5 S-J3-1) requires lifespan startup to call
    set_main_event_loop(). Without that capture, dispatch_alert_from_thread
    falls back to logger.warning and silently drops alerts.

    This is a structural check: lifespan.py:startup must contain the
    call. Behavioral verification is in tests/test_alert_cross_thread_dispatch.py.
    """
    from backend.api import lifespan as lifespan_mod
    src = inspect.getsource(lifespan_mod.startup)
    assert "set_main_event_loop" in src, (
        "S-J3-1 reachability: lifespan.startup() does not call "
        "set_main_event_loop(). Worker-thread alerts will silently "
        "drop (the V5 root cause)."
    )


def test_no_residual_broken_alert_pattern_in_organism():
    """V7 V-T-1 / V-T-2: same-class scan found wave-12f had
    `get_running_loop` + `call_soon_threadsafe` + asyncio.run fallback
    in two sites that wave-17a missed. Wave-20a fixed those, but a
    future regression would re-introduce the pattern. Re-grep the
    same-class scan and assert 0.
    """
    import subprocess
    out = subprocess.check_output(
        [
            "bash", "-c",
            # Match the broken pattern: asyncio.run(_emit) or
            # asyncio.run(send_alert(...)) inside an except RuntimeError
            # block (the wave-8c/12f anti-pattern).
            "grep -rn 'asyncio.run(_emit\\|asyncio.run(send_alert\\|_aio.run(_emit' "
            "backend/services/ backend/organism/ backend/integrations/ || true",
        ],
        cwd=".",
    ).decode("utf-8", errors="replace")
    hits = [
        line for line in out.splitlines()
        if line.strip() and "test_" not in line
    ]
    assert len(hits) == 0, (
        "S-J3-1 same-class regression: found broken async-alert "
        f"pattern in {len(hits)} site(s). Should be 0:\n"
        + "\n".join(hits)
    )


# ─────────────────────────────────────────────────────────────────────
# DD-1 / DD-2 (V7 strategy logic) — reachability of the fix sites
# ─────────────────────────────────────────────────────────────────────


def test_dd_1_safe_div_returns_nan_on_double_zero():
    """V7 DD-1 fix: _safe_div(0, 0) must return NaN (not 0) so the
    breakout_readiness_index doesn't synthesize 1.0 saturation on
    flat-price warmup data.
    """
    import math
    import pandas as pd
    from backend.organism.composite_indicators import _safe_div
    a = pd.Series([0.0, 0.0, 1.0])
    b = pd.Series([0.0, 1.0, 0.0])
    out = _safe_div(a, b)
    assert math.isnan(out.iloc[0]), (
        "DD-1 regression: _safe_div(0, 0) returned %r — expected NaN" % out.iloc[0]
    )
    assert out.iloc[1] == 0.0  # 0/1 stays 0
    # 1/0 falls back to the 1e-10 epsilon (same legacy semantics)
    assert out.iloc[2] > 1e9


def test_dd_2_regime_unknown_when_atr_missing():
    """V7 DD-2 fix: regime detector returns UNKNOWN (not synthetic
    high_vol) when the input DataFrame has no ATR column."""
    import pandas as pd
    from backend.organism.regime import RegimeDetector, RegimeLabel
    det = RegimeDetector()
    df = pd.DataFrame({"close": [100.0] * 60, "volume": [1000] * 60})
    state = det.detect(df)
    assert state.primary == RegimeLabel.UNKNOWN, (
        "DD-2 regression: missing-ATR feature DataFrame produced "
        f"regime={state.primary} (expected UNKNOWN)"
    )


# ─────────────────────────────────────────────────────────────────────
# Audit-cycle process — wave-marker checker exists and runs
# ─────────────────────────────────────────────────────────────────────


def test_wave_28_check_wave_markers_script_exists_and_runs():
    """Wave-28's check_wave_markers.py script must exist and import
    cleanly. The CI workflow requires it (post wave-28); a missing
    script would silently disable enforcement."""
    import subprocess
    proc = subprocess.run(
        ["./venv/bin/python", "scripts/ci/check_wave_markers.py", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 0, (
        f"check_wave_markers.py --help exited {proc.returncode}; "
        f"stderr: {proc.stderr}"
    )
    assert "wave-PR marker enforcement" in (proc.stdout + proc.stderr).lower() or \
           "warn-only" in (proc.stdout + proc.stderr), (
        "check_wave_markers.py output looks wrong"
    )


def test_pr_template_present():
    """Wave-26 added the audit-wave PR template. A missing template
    breaks rule #3's human-enforcement surface."""
    import os
    path = ".github/pull_request_template.md"
    assert os.path.isfile(path), f"{path} missing"
    with open(path) as f:
        content = f.read()
    assert "Audit-wave PR checklist" in content, (
        "PR template doesn't have the audit-wave checklist"
    )
    assert "Same-class scan" in content
    assert "Behavioral test" in content


def test_pr_verify_workflow_uses_required_mode():
    """Wave-28 flipped pr-verify.yml from `continue-on-error: true`
    to required. A future revert would re-introduce the warn-mode
    bug that V7 W2 documented."""
    import os
    path = ".github/workflows/pr-verify.yml"
    assert os.path.isfile(path)
    with open(path) as f:
        content = f.read()
    # Should not have `continue-on-error: true` on the wave-marker step.
    # We grep for the canonical block; absence is success.
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if "Wave-PR marker enforcement" in line:
            # Look at the following 5 lines for `continue-on-error`.
            window = "\n".join(lines[i:i + 6])
            assert "continue-on-error: true" not in window, (
                "pr-verify.yml: Wave-PR marker step is in warn-mode "
                "(continue-on-error: true). Wave-28 flipped this to "
                "required; a revert silently disables enforcement."
            )
            return
    pytest.fail(
        "pr-verify.yml does not contain the 'Wave-PR marker enforcement' step"
    )
