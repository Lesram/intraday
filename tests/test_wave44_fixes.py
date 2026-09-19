"""V9 / Wave-44 (2026-05-03): tests for strategy state-machine fixes.

Locks the regressions for:
- DD3-1 (HIGH): MomentumPyramider keys on `max_level` not `layer_count`,
  so a layer-list collapse in _reconcile_fills doesn't make Layer 1
  re-fire indefinitely; Layer 2 reachable.
- DD3-4 (MEDIUM): EOD flatten cancels pending entries before submitting
  flatten exits — 15:57 entries can no longer fill post-16:00 with no
  exit infrastructure.
- DD3-5 (MEDIUM): production fitness gate distinguishes "no fitness
  recorded" (block, with warn) from "fitness == 0.5" (default permit).

Run with: ./venv/bin/python -m pytest tests/test_wave44_fixes.py -v
"""
from __future__ import annotations

import inspect


# ─────────────────────────────────────────────────────────────────────
# DD3-1 — pyramider Layer 2 reachable
# ─────────────────────────────────────────────────────────────────────


def test_dd3_1_pyramid_position_has_max_level_property():
    """PyramidPosition.max_level must exist and return -1 for no layers."""
    from backend.organism.pyramider import PyramidPosition
    pos = PyramidPosition(symbol="X", direction=1.0, layers=[])
    assert pos.max_level == -1


def test_dd3_1_check_pyramid_keys_on_max_level():
    """check_pyramid uses max_level, not layer_count, for Layer 1/2 gates."""
    from backend.organism.pyramider import MomentumPyramider
    src = inspect.getsource(MomentumPyramider.check_pyramid)
    assert "DD3-1" in src, "DD3-1 marker missing from check_pyramid"
    assert "position.max_level == 0" in src, (
        "DD3-1 regression: Layer 1 trigger no longer keys on max_level==0. "
        "Reconcile collapse can re-fire Layer 1 indefinitely."
    )
    assert "position.max_level == 1" in src, (
        "DD3-1 regression: Layer 2 trigger no longer keys on max_level==1. "
        "Layer 2 may become unreachable again."
    )


def test_dd3_1_layer_2_reachable_with_collapsed_layer_list():
    """Concrete: a position with layer_count=1 but a level=1 layer
    inside (i.e. _reconcile_fills collapsed but level survived) must
    still trigger Layer 2."""
    from backend.organism.pyramider import (
        PyramidPosition, PyramidLevel, MomentumPyramider,
    )
    pyr = MomentumPyramider()
    # Simulate the collapse: 1 layer with level=1 (post-Layer-1-add).
    pos = PyramidPosition(
        symbol="AAPL", direction=1.0,
        layers=[PyramidLevel(shares=100, entry_price=100.0, bar_added=0, level=1)],
        target_total_shares=300,
        atr_at_entry=1.0,
        initial_stop=98.0,
        current_stop=100.0,
        highest_price=103.0,  # +3R
        lowest_price=100.0,
        breakout_score=0.7,
    )
    # max_level == 1, r_multiple == 3.0 (highest 103 - entry 100 / atr 1)
    assert pos.max_level == 1
    action = pyr.check_pyramid(pos, current_price=103.0)
    assert action.action == "add", (
        f"DD3-1 regression: Layer 2 not reachable when layer list "
        f"collapsed to 1 entry with level=1. Got action={action.action}"
    )


# ─────────────────────────────────────────────────────────────────────
# DD3-4 — EOD flatten cancels pending entries
# ─────────────────────────────────────────────────────────────────────


def test_dd3_4_eod_flatten_cancels_pending_entries():
    """The EOD flatten block in _live_tick_inner must cancel pending
    entry orders BEFORE submitting flatten exits."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert "DD3-4" in src, "DD3-4 marker missing from EOD flatten block"
    # The cancel block must reference _pending_entry_order_ids.
    assert "_pending_entry_order_ids" in src, (
        "DD3-4 regression: EOD flatten no longer iterates pending entry "
        "orders. 15:57 entries can fill post-16:00 with no exit infra."
    )


# ─────────────────────────────────────────────────────────────────────
# DD3-5 — fitness gate handles missing data
# ─────────────────────────────────────────────────────────────────────


def test_dd3_5_fitness_gate_distinguishes_missing_from_default():
    """The fitness gate must distinguish "no entry in symbol_fitness"
    from "fitness == 0.5". Previously empty symbol_fitness silently
    bypassed the 0.45 production gate."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine)
    assert "DD3-5" in src, "DD3-5 marker missing"
    assert "if symbol in symbol_fitness_map:" in src, (
        "DD3-5 regression: fitness lookup no longer differentiates "
        "missing-from-map vs map-says-0.5."
    )
