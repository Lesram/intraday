"""Audit 2026-06-09 finding 3.4 — EOD flatten failure escalation.

Previously, positions still open past 16:00 ET produced only a
``logger.warning``. Now the engine must: persist an overnight flag file,
fire a CRITICAL alert (once per session), and force-exit flagged symbols
at the next session open.

These tests exercise the helper methods directly (the engine monolith is
too heavy to construct end-to-end here) plus structural wiring guards.
"""

import inspect
import json

import pytest

from backend.organism.live_engine import OrganismLiveEngine


class _EngineShim:
    """Minimal stand-in carrying just what the helpers need."""

    def __init__(self, tmp_path):
        class _Brain:
            brain_dir = tmp_path
        self.brain = _Brain()

    _overnight_flag_path = OrganismLiveEngine._overnight_flag_path
    _record_unflattened_positions = OrganismLiveEngine._record_unflattened_positions
    _load_overnight_flag = OrganismLiveEngine._load_overnight_flag
    _clear_overnight_flag = OrganismLiveEngine._clear_overnight_flag


@pytest.fixture
def shim(tmp_path):
    return _EngineShim(tmp_path)


def test_record_persists_flag_file(shim, monkeypatch):
    alerts = []
    import backend.infra.alerting as alerting

    monkeypatch.setattr(
        alerting, "dispatch_alert_from_thread", lambda f: alerts.append(f) or True
    )

    shim._record_unflattened_positions(
        ["NVDA", "QQQ", "NVDA"], "2026-06-09", "2026-06-09T20:01:00Z"
    )

    p = shim._overnight_flag_path()
    assert p.is_file()
    data = json.loads(p.read_text())
    assert data["session_date"] == "2026-06-09"
    assert data["symbols"] == ["NVDA", "QQQ"]  # deduped, sorted
    assert len(alerts) == 1, "CRITICAL alert must be dispatched"


def test_alert_fires_once_per_session(shim, monkeypatch):
    alerts = []
    import backend.infra.alerting as alerting

    monkeypatch.setattr(
        alerting, "dispatch_alert_from_thread", lambda f: alerts.append(f) or True
    )

    shim._record_unflattened_positions(["NVDA"], "2026-06-09", "t0")
    shim._record_unflattened_positions(["NVDA"], "2026-06-09", "t1")  # same session
    assert len(alerts) == 1

    shim._record_unflattened_positions(["NVDA"], "2026-06-10", "t2")  # next session
    assert len(alerts) == 2


def test_load_and_clear_roundtrip(shim, monkeypatch):
    import backend.infra.alerting as alerting

    monkeypatch.setattr(alerting, "dispatch_alert_from_thread", lambda f: True)

    assert shim._load_overnight_flag() is None
    shim._record_unflattened_positions(["AMD"], "2026-06-09", "t0")
    date, syms = shim._load_overnight_flag()
    assert date == "2026-06-09" and syms == ["AMD"]
    shim._clear_overnight_flag()
    assert shim._load_overnight_flag() is None


def test_corrupt_flag_returns_none(shim):
    shim._overnight_flag_path().write_text("{not json")
    assert shim._load_overnight_flag() is None


# ── Structural wiring guards ─────────────────────────────────────────


def test_past_close_branch_escalates():
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert "_record_unflattened_positions(" in src, (
        "the >=16:00 branch must escalate, not warning-only"
    )


def test_morning_force_exit_wired():
    # The logic lives in an extracted helper (W100 LOC ceiling); the tick
    # loop must call it and the helper must use the flag lifecycle.
    tick_src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert "_force_exit_overnight_stragglers(" in tick_src
    helper_src = inspect.getsource(
        OrganismLiveEngine._force_exit_overnight_stragglers
    )
    assert "overnight_force_exit" in helper_src
    assert "_load_overnight_flag()" in helper_src
    assert "_clear_overnight_flag()" in helper_src


def test_force_exit_only_on_later_session():
    src = inspect.getsource(
        OrganismLiveEngine._force_exit_overnight_stragglers
    )
    assert "_today_et > _ov_date" in src, (
        "forced exit must only run on a LATER session than the failed flatten "
        "(same-session re-entry into the flatten window must not trigger it)"
    )
