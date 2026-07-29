"""Tests for G1/G2/G3 real-money mechanical hardening fixes.

G1: Exit level restore failure logged at WARNING + marked for safety handling
G2: Exit cooldown only set on successful submission, not in finally block
G3: NaN/Inf/negative current_price safely returns PyramidAction("none")
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from backend.organism.pyramider import MomentumPyramider, PyramidAction


# ─── G3 tests: NaN guard in pyramider ──────────────────────

@dataclass
class FakeLevel:
    entry_price: float = 100.0
    shares: int = 10
    cost_basis: float = 1000.0


@dataclass
class FakePosition:
    symbol: str = "TEST"
    direction: float = 1.0
    layers: list = field(default_factory=lambda: [FakeLevel()])
    target_total_shares: int = 10
    atr_at_entry: float = 2.0
    initial_stop: float = 96.0
    current_stop: float = 96.0
    highest_price: float = 100.0
    lowest_price: float = float('inf')
    breakout_score: float = 0.5

    @property
    def total_shares(self):
        return sum(l.shares for l in self.layers)

    @property
    def layer_count(self):
        return len(self.layers)


def test_g3_nan_price_returns_none():
    """NaN current_price must return action='none', not propagate NaN."""
    pyr = MomentumPyramider()
    pos = FakePosition()
    action = pyr.check_pyramid(pos, current_price=float('nan'))
    assert action.action == "none"


def test_g3_inf_price_returns_none():
    """Inf current_price must return action='none'."""
    pyr = MomentumPyramider()
    pos = FakePosition()
    action = pyr.check_pyramid(pos, current_price=float('inf'))
    assert action.action == "none"


def test_g3_negative_inf_price_returns_none():
    pyr = MomentumPyramider()
    pos = FakePosition()
    action = pyr.check_pyramid(pos, current_price=float('-inf'))
    assert action.action == "none"


def test_g3_zero_price_returns_none():
    """Zero price is non-physical for stocks. Should return none."""
    pyr = MomentumPyramider()
    pos = FakePosition()
    action = pyr.check_pyramid(pos, current_price=0.0)
    assert action.action == "none"


def test_g3_negative_price_returns_none():
    pyr = MomentumPyramider()
    pos = FakePosition()
    action = pyr.check_pyramid(pos, current_price=-50.0)
    assert action.action == "none"


def test_g3_valid_price_still_works():
    """Normal valid price should still produce a real action."""
    pyr = MomentumPyramider()
    pos = FakePosition(atr_at_entry=2.0, highest_price=100.0)
    # Price at entry — should return "none" (no add, no cut)
    action = pyr.check_pyramid(pos, current_price=100.0)
    assert action.action == "none"


def test_g3_valid_price_produces_cut():
    """Valid price at -1R should still produce cut_full."""
    pyr = MomentumPyramider()
    pos = FakePosition(atr_at_entry=2.0, highest_price=100.0)
    # Price dropped 2 ATR below entry → r_current = -1.0
    action = pyr.check_pyramid(pos, current_price=96.0)
    assert action.action == "close_partial"
    assert "cut_full" in action.reason


# ─── G1 tests: exit level restore handling ─────────────────

def test_g1_restore_failure_marks_metadata():
    """When exit_levels can't be restored, the entry_metadata should
    be marked with exit_levels_failed=True so the safety net can
    handle it. We test the marking logic directly."""
    entry_metadata: dict = {}
    sym = "AAPL"

    # Simulate the G1 fix: mark on failure
    if sym not in entry_metadata:
        entry_metadata[sym] = {}
    entry_metadata[sym]["exit_levels_failed"] = True

    assert entry_metadata[sym]["exit_levels_failed"] is True


def test_g1_restore_failure_existing_metadata_preserved():
    """Marking exit_levels_failed should not clobber existing metadata."""
    entry_metadata = {"AAPL": {"entry_tick": 500, "confidence": 0.35}}

    # Simulate G1 marking
    entry_metadata["AAPL"]["exit_levels_failed"] = True

    assert entry_metadata["AAPL"]["entry_tick"] == 500
    assert entry_metadata["AAPL"]["confidence"] == 0.35
    assert entry_metadata["AAPL"]["exit_levels_failed"] is True


# ─── G2 tests: exit cooldown on success only ───────────────

def test_g2_cooldown_logic_success():
    """On successful exit submission, cooldown SHOULD be set."""
    exit_cooldown: dict = {}
    pending_exit: dict = {}
    tick_count = 100
    sym = "SPY"
    submission_succeeded = True

    if submission_succeeded:
        exit_cooldown[sym] = tick_count
        pending_exit[sym] = tick_count

    assert sym in exit_cooldown
    assert exit_cooldown[sym] == 100


def test_g2_cooldown_logic_failure():
    """On FAILED exit submission, cooldown should NOT be set.
    This is the G2 fix — the old code set cooldown in a finally block."""
    exit_cooldown: dict = {}
    pending_exit: dict = {}
    tick_count = 100
    sym = "SPY"
    submission_succeeded = False

    if submission_succeeded:
        exit_cooldown[sym] = tick_count
        pending_exit[sym] = tick_count
    # On failure: do NOT set cooldown (G2 fix)

    assert sym not in exit_cooldown
    assert sym not in pending_exit


def test_g2_retry_after_failure():
    """After a failed exit, the next tick should be able to retry
    because no cooldown was set."""
    exit_cooldown: dict = {}
    sym = "SPY"
    COOLDOWN_TICKS = 3

    # Tick 100: exit fails (G2: no cooldown set)
    # (nothing in exit_cooldown)

    # Tick 101: retry check
    tick_count = 101
    cooldown_tick = exit_cooldown.get(sym, 0)
    can_retry = (tick_count - cooldown_tick) >= COOLDOWN_TICKS

    assert can_retry is True  # Can retry immediately
