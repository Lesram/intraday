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

import pytest


def test_wave40_stage_helper_method_exists():
    """OrganismLiveEngine._stage_check_entry_blockers must exist."""
    from backend.organism.live_engine import OrganismLiveEngine
    assert hasattr(OrganismLiveEngine, "_stage_check_entry_blockers"), (
        "Wave-40 regression: _stage_check_entry_blockers helper "
        "removed. Stages 1/1.1/1.2 went back to inline code."
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


def test_wave40_stage_helper_evaluates_governance_halt():
    """Stage 1 governance halt branch must be present in the helper."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._stage_check_entry_blockers)
    assert "governance_halt" in src, (
        "Wave-40 regression: stage 1 governance halt branch missing "
        "from helper."
    )
    assert "is_trading_halted" in src, (
        "Wave-40 regression: stage 1 doesn't consult "
        "governance.is_trading_halted."
    )


def test_wave40_stage_helper_evaluates_warmup_and_stale():
    """Stages 1.1 and 1.2 must short-circuit after governance halt."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._stage_check_entry_blockers)
    assert "warmup" in src and "_WARMUP_TICKS" in src, (
        "Wave-40 regression: stage 1.1 warmup gate missing."
    )
    assert "stale_data" in src and "_data_stale" in src, (
        "Wave-40 regression: stage 1.2 stale-data gate missing."
    )


def test_wave40_short_circuit_ordering_preserved():
    """The 3 stages must check `self._entries_blocked` before evaluating
    so a higher-precedence reason isn't overwritten by a lower one."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._stage_check_entry_blockers)
    # stages 1.1 and 1.2 both must have `not self._entries_blocked` guards.
    n = src.count("not self._entries_blocked")
    assert n >= 2, (
        f"Wave-40 regression: only {n} short-circuit guards in helper "
        "(expected >=2 for stages 1.1 and 1.2). Lower-precedence "
        "reasons may overwrite governance_halt or warmup."
    )


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
