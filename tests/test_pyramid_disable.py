"""Task C: pyramiding kill-switch — disabled => full initial size + no adds."""
from __future__ import annotations

from backend.organism.pyramider import MomentumPyramider, PyramidPosition, PyramidLevel


def _pos():
    p = PyramidPosition(symbol="AAPL", direction=1.0, atr_at_entry=1.0)
    p.layers.append(PyramidLevel(shares=100, entry_price=100.0, bar_added=0, level=0))
    p.highest_price = 105.0
    return p


def test_disabled_enters_full_size():
    assert MomentumPyramider(enabled=False).initial_shares(100) == 100  # no 0.60 reduction
    assert MomentumPyramider(enabled=True).initial_shares(100) == 60     # default reduces


def test_disabled_never_adds_or_cuts():
    dis = MomentumPyramider(enabled=False)
    # Even at a +3R parabolic move (would normally add) -> no-op.
    assert dis.check_pyramid(_pos(), 130.0).action == "none"
    # Even at a -2R adverse move (would normally cut) -> no-op.
    assert dis.check_pyramid(_pos(), 98.0).action == "none"


def test_default_enabled_unchanged():
    # Back-compat: default ctor preserves prior behavior.
    p = MomentumPyramider()
    assert p.enabled is True
    assert p.initial_shares(100) == 60
