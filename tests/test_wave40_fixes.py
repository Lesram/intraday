"""V8 / Wave-40 (2026-05-03): tests for HH R-1 stages 1 + 1.1 + 1.2 extraction.

Wave-40 extracts the three earliest entry-blocker stages (governance
halt, warmup, stale data) from `_live_tick_inner` into a dedicated
helper `_stage_check_entry_blockers`. This is unblocked by wave-39's
`entries_blocked` uplift to `self._entries_blocked`.

Locks the regressions for:
- HH R-1 stages 1 / 1.1 / 1.2 — extracted as a unit because they
  share `self._entries_blocked` with short-circuit ordering between
  them.

Run with: ./venv/bin/python -m pytest tests/test_wave40_fixes.py -v
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace


def _entry_blocker_engine(
    *,
    halted: bool = False,
    entries_blocked: bool = False,
    tick: int = 10,
    warmup: int = 5,
    stale: bool = False,
):
    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine.governance = SimpleNamespace(is_trading_halted=halted)
    engine._entries_blocked = entries_blocked
    engine._last_entries_blocked_reason = ""
    engine._tick_count = tick
    engine._WARMUP_TICKS = warmup
    engine._data_stale = stale
    return engine


def test_wave40_stage_helper_method_exists():
    """OrganismLiveEngine._stage_check_entry_blockers must exist."""
    from backend.organism.live_engine import OrganismLiveEngine
    assert hasattr(OrganismLiveEngine, "_stage_check_entry_blockers"), (
        "Wave-40 regression: _stage_check_entry_blockers helper "
        "removed. Stages 1/1.1/1.2 went back to inline code."
    )
    assert hasattr(OrganismLiveEngine, "_evaluate_entry_blocker_gate"), (
        "P7.2 regression: _evaluate_entry_blocker_gate decision boundary "
        "removed. Gate behavior is no longer directly testable."
    )


def test_wave40_stage_helper_called_from_tick_inner():
    """The tick inner must invoke the new stage helper exactly once."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    n = src.count("self._stage_check_entry_blockers(")
    assert n == 1, (
        f"Wave-40 regression: _stage_check_entry_blockers invoked "
        f"{n} time(s) (expected exactly 1)."
    )


def test_wave40_entry_blocker_gate_allows_clear_state():
    """No halt, no warmup, and fresh data leaves entries unblocked."""
    engine = _entry_blocker_engine()

    gate = engine._evaluate_entry_blocker_gate()

    assert gate.blocked is False
    assert gate.reason == ""
    assert engine._entries_blocked is False
    assert engine._last_entries_blocked_reason == ""


def test_wave40_entry_blocker_gate_governance_precedes_warmup_and_stale():
    """Operator halt wins even when warmup and stale-data are also true."""
    engine = _entry_blocker_engine(halted=True, tick=1, warmup=5, stale=True)

    gate = engine._evaluate_entry_blocker_gate()

    assert gate.blocked is True
    assert gate.reason == "governance_halt"
    assert gate.activity_type == "governance"
    assert "blocking new entries" in gate.activity_message
    assert "exits still active" in gate.error_message


def test_wave40_entry_blocker_gate_warmup_precedes_stale():
    """Warmup wins over stale-data when governance is not halted."""
    engine = _entry_blocker_engine(tick=5, warmup=5, stale=True)

    gate = engine._evaluate_entry_blocker_gate()

    assert gate.blocked is True
    assert gate.reason == "warmup"
    assert gate.activity_type == "skip"
    assert "tick 5/5" in gate.activity_message
    assert gate.error_message == ""


def test_wave40_entry_blocker_gate_stale_after_warmup():
    """Stale-data blocks entries only after warmup has cleared."""
    engine = _entry_blocker_engine(tick=6, warmup=5, stale=True)

    gate = engine._evaluate_entry_blocker_gate()

    assert gate.blocked is True
    assert gate.reason == "stale_data"
    assert gate.activity_type == "skip"
    assert "Stale data" in gate.activity_message
    assert gate.error_message == ""


def test_wave40_stage_helper_applies_governance_gate_to_tick_result():
    """The stage helper still mutates tick result state for a hard halt."""
    from backend.organism.live_engine import LiveTickResult

    engine = _entry_blocker_engine(halted=True)
    result = LiveTickResult()

    engine._stage_check_entry_blockers(result, "2026-05-05T16:00:00Z")

    assert engine._entries_blocked is True
    assert engine._last_entries_blocked_reason == "governance_halt"
    assert result.errors == ["Trading halted by governance — exits still active"]
    assert len(result.activity) == 1
    assert result.activity[0].event_type == "governance"
    assert "blocking new entries" in result.activity[0].message
    assert result.activity[0].timestamp == "2026-05-05T16:00:00Z"


def test_wave40_stage_helper_noops_for_prior_block_without_halt():
    """Prior entry blocks are preserved unless governance halt overrides."""
    from backend.organism.live_engine import LiveTickResult

    engine = _entry_blocker_engine(
        entries_blocked=True,
        tick=1,
        warmup=5,
        stale=True,
    )
    engine._last_entries_blocked_reason = "daily_max_loss"
    result = LiveTickResult()

    engine._stage_check_entry_blockers(result, "2026-05-05T16:00:00Z")

    assert engine._entries_blocked is True
    assert engine._last_entries_blocked_reason == "daily_max_loss"
    assert result.errors == []
    assert result.activity == []


def test_wave40_inline_governance_check_removed():
    """The original inline governance/warmup/stale-data block must be
    gone from `_live_tick_inner` (now lives in the helper)."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    # Count GOVERNANCE CHECK marker comments in the inner function.
    n = src.count("# 1. GOVERNANCE CHECK")
    assert n == 0, (
        "Wave-40 regression: inline GOVERNANCE CHECK block still in "
        "_live_tick_inner. Extraction reverted."
    )
