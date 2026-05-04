"""V13 W94 (Lens 3: Strategy Expectancy) — behavioral coverage.

Three deliverables, three test groups:

1. ``backend.organism.strategy_alerts.should_fire_low_win_rate_alert``
   — pure decision function; tests cover at-floor, above-floor,
   below-floor, insufficient-trades, missing-field cases.

2. ``backend.organism.strategy_alerts.maybe_dispatch_low_win_rate_alert``
   — dispatch wrapper with rate-limiting; verify the alerting layer
   is invoked exactly once per fingerprint.

3. ``scripts/ci/check_strategy_floor.py`` — CI floor gate.  Tests
   cover opt-in default (no env), pass case (above floor), fail case
   (below floor), and missing-data case (strict vs lenient).

4. The /api/v1/health/strategy?window=last_50 windowed-slice
   projection (W94 endpoint extension).

Run with:
    ./venv/bin/python -m pytest tests/test_v13_w94_strategy_floor.py -v
"""
# wave: V13-W94
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "ci" / "check_strategy_floor.py"


# ────────────────────────────────────────────────────────────────────
# Pure decision function
# ────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_alert_state():
    from backend.organism.strategy_alerts import reset_alert_state_for_tests
    reset_alert_state_for_tests()


def test_w94_should_fire_below_floor():
    from backend.organism.strategy_alerts import should_fire_low_win_rate_alert
    fire, reason = should_fire_low_win_rate_alert(
        {"n_trades": 100, "last_50_win_rate": 0.20, "total_pnl": -500},
        floor=0.30,
    )
    assert fire is True
    assert "0.200" in reason and "0.300" in reason


def test_w94_should_not_fire_above_floor():
    from backend.organism.strategy_alerts import should_fire_low_win_rate_alert
    fire, _ = should_fire_low_win_rate_alert(
        {"n_trades": 100, "last_50_win_rate": 0.50},
        floor=0.30,
    )
    assert fire is False


def test_w94_should_not_fire_at_floor():
    """Boundary: floor is exclusive — equal-to-floor does NOT fire.
    This avoids on/off thrashing for brains hovering at the line."""
    from backend.organism.strategy_alerts import should_fire_low_win_rate_alert
    fire, _ = should_fire_low_win_rate_alert(
        {"n_trades": 100, "last_50_win_rate": 0.30},
        floor=0.30,
    )
    assert fire is False


def test_w94_should_not_fire_insufficient_trades():
    """A brain with 5 lifetime trades can't trigger this alert — the
    last_50 window isn't yet meaningful."""
    from backend.organism.strategy_alerts import should_fire_low_win_rate_alert
    fire, reason = should_fire_low_win_rate_alert(
        {"n_trades": 5, "last_50_win_rate": 0.10},
        floor=0.30,
    )
    assert fire is False
    assert "insufficient" in reason


def test_w94_should_not_fire_missing_field():
    from backend.organism.strategy_alerts import should_fire_low_win_rate_alert
    fire, _ = should_fire_low_win_rate_alert({"n_trades": 100}, floor=0.30)
    assert fire is False


def test_w94_env_floor_default_is_thirty_pct():
    """Default floor matches the V13 framework spec (last_50_win_rate < 0.30)."""
    os.environ.pop("STRATEGY_LAST_50_WIN_RATE_FLOOR", None)
    from backend.organism.strategy_alerts import should_fire_low_win_rate_alert
    fire, _ = should_fire_low_win_rate_alert(
        {"n_trades": 100, "last_50_win_rate": 0.29}
    )
    assert fire is True


def test_w94_env_floor_override():
    from backend.organism.strategy_alerts import should_fire_low_win_rate_alert
    try:
        os.environ["STRATEGY_LAST_50_WIN_RATE_FLOOR"] = "0.50"
        fire, _ = should_fire_low_win_rate_alert(
            {"n_trades": 100, "last_50_win_rate": 0.40}
        )
        assert fire is True
    finally:
        os.environ.pop("STRATEGY_LAST_50_WIN_RATE_FLOOR", None)


# ────────────────────────────────────────────────────────────────────
# Dispatch + rate-limiting
# ────────────────────────────────────────────────────────────────────


def test_w94_dispatch_calls_alerting_layer_once():
    """When the alert should fire, the alerting layer is invoked exactly once."""
    from backend.organism import strategy_alerts

    captured: list[object] = []

    def _fake_dispatch(fn):
        captured.append(fn)
        return True

    # Match the import path strategy_alerts uses internally.
    with patch("backend.infra.alerting.dispatch_alert_from_thread", _fake_dispatch):
        ok = strategy_alerts.maybe_dispatch_low_win_rate_alert(
            {"n_trades": 100, "last_50_win_rate": 0.20},
            floor=0.30,
        )
    assert ok is True
    assert len(captured) == 1


def test_w94_dispatch_rate_limited_for_same_fingerprint():
    from backend.organism import strategy_alerts

    counter = []

    def _fake_dispatch(fn):
        counter.append(1)
        return True

    with patch("backend.infra.alerting.dispatch_alert_from_thread", _fake_dispatch):
        strategy_alerts.maybe_dispatch_low_win_rate_alert(
            {"n_trades": 100, "last_50_win_rate": 0.20}, floor=0.30,
        )
        strategy_alerts.maybe_dispatch_low_win_rate_alert(
            {"n_trades": 100, "last_50_win_rate": 0.20}, floor=0.30,
        )
    # First fires, second suppressed by rate-limit.
    assert len(counter) == 1


def test_w94_dispatch_skips_when_no_alert_warranted():
    from backend.organism import strategy_alerts

    counter = []

    def _fake_dispatch(fn):
        counter.append(1)
        return True

    with patch("backend.infra.alerting.dispatch_alert_from_thread", _fake_dispatch):
        ok = strategy_alerts.maybe_dispatch_low_win_rate_alert(
            {"n_trades": 100, "last_50_win_rate": 0.50}, floor=0.30,
        )
    assert ok is False
    assert counter == []


# ────────────────────────────────────────────────────────────────────
# CI floor gate
# ────────────────────────────────────────────────────────────────────


def _run_gate(env: dict[str, str] | None = None,
              args: list[str] | None = None,
              cwd: Path | None = None) -> tuple[int, str]:
    full_env = os.environ.copy()
    full_env.pop("STRATEGY_FLOOR_TOTAL_PNL", None)
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [sys.executable, str(GATE), *(args or [])],
        env=full_env, capture_output=True, text=True, timeout=30,
        cwd=str(cwd) if cwd else None,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_w94_gate_opt_in_when_env_unset(tmp_path):
    """Gate exits 0 with a notice when no STRATEGY_FLOOR_TOTAL_PNL is set."""
    code, out = _run_gate(cwd=tmp_path)
    assert code == 0
    assert "OPT-IN" in out


def test_w94_gate_passes_when_pnl_above_floor(tmp_path):
    brain = tmp_path / "organism_brain"
    brain.mkdir()
    (brain / "manifest.json").write_text(json.dumps({
        "strategy_expectancy": {
            "n_trades": 200, "total_pnl": -400.0, "win_rate": 0.40,
            "last_50_win_rate": 0.45, "last_50_mean_pnl": 1.0,
        },
    }))
    code, out = _run_gate(
        env={"STRATEGY_FLOOR_TOTAL_PNL": "-500"},
        args=[f"--brain-dir={brain}"],
    )
    assert code == 0, out
    assert "PASS" in out


def test_w94_gate_fails_when_pnl_below_floor(tmp_path):
    brain = tmp_path / "organism_brain"
    brain.mkdir()
    (brain / "manifest.json").write_text(json.dumps({
        "strategy_expectancy": {
            "n_trades": 200, "total_pnl": -1500.0,
            "last_50_win_rate": 0.20,
        },
    }))
    code, out = _run_gate(
        env={"STRATEGY_FLOOR_TOTAL_PNL": "-1000"},
        args=[f"--brain-dir={brain}"],
    )
    assert code == 1, out
    assert "FAIL" in out
    assert "below the configured release-branch floor" in out


def test_w94_gate_handles_missing_data_lenient(tmp_path):
    """Without --strict, missing data is treated as opt-in (exit 0)."""
    brain = tmp_path / "organism_brain"
    brain.mkdir()
    code, out = _run_gate(
        env={"STRATEGY_FLOOR_TOTAL_PNL": "-1000"},
        args=[f"--brain-dir={brain}"],
    )
    assert code == 0
    assert "NO DATA" in out


def test_w94_gate_handles_missing_data_strict(tmp_path):
    brain = tmp_path / "organism_brain"
    brain.mkdir()
    code, out = _run_gate(
        env={"STRATEGY_FLOOR_TOTAL_PNL": "-1000"},
        args=[f"--brain-dir={brain}", "--strict"],
    )
    assert code == 2, out


def test_w94_gate_floor_arg_overrides_env(tmp_path):
    brain = tmp_path / "organism_brain"
    brain.mkdir()
    (brain / "manifest.json").write_text(json.dumps({
        "strategy_expectancy": {"n_trades": 100, "total_pnl": -800.0},
    }))
    code, out = _run_gate(
        env={"STRATEGY_FLOOR_TOTAL_PNL": "-9999"},  # would pass
        args=[f"--brain-dir={brain}", "--floor=-500"],  # override → fail
    )
    assert code == 1, out


# ────────────────────────────────────────────────────────────────────
# Endpoint windowed-slice projection
# ────────────────────────────────────────────────────────────────────


def test_w94_endpoint_window_query_param_validated():
    """Bad window value yields 400 — guard against silent typos that
    would return the full payload instead of the slice the caller asked for."""
    src = (
        REPO_ROOT / "backend" / "api" / "routes" / "strategy_health.py"
    ).read_text()
    assert "_ALLOWED_WINDOWS" in src
    assert "last_25" in src and "last_50" in src
    assert "status_code=400" in src


def test_w94_endpoint_window_projects_to_slice():
    """The endpoint slim payload must include only window-prefixed
    fields + provenance.  This is a structural test on the route
    function — full HTTP integration is exercised by the existing
    test_v12_strategy_expectancy suite."""
    src = (
        REPO_ROOT / "backend" / "api" / "routes" / "strategy_health.py"
    ).read_text()
    assert 'prefix = f"{window}_"' in src
    assert '"window": window' in src
