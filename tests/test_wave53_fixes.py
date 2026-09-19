"""V10 / Wave-53 (2026-05-03): tests for strategy persistence + pyramid layer collapse.

Locks regressions for:
- DD4-1 (HIGH): symbol_trade_counts + symbol_fitness now persist via
  extra_counters (essential save), not just evolved_params.json (full
  save promotion-gated).  Restart no longer wipes runtime growth.
- DD4-2 (HIGH): _reconcile_fills no longer collapses pyramid layers to
  a single layer with broker_avg.  L0's original entry_price is
  preserved so R-multiple math is correct; pyramid adds become a
  second PyramidLevel with the implied add-fill price.
- DD4-4 (LOW): MomentumPyramider.telemetry() exposes the previously
  write-only _pyramid_count / _max_layers_reached counters.

Wave-53 deferred:
- DD4-3 (MEDIUM, inverse-ETF regime flip refactor): multi-site change
  with replay-determinism implications; tracked for V11.

Run with: ./venv/bin/python -m pytest tests/test_wave53_fixes.py -v
"""
from __future__ import annotations

import inspect


def test_dd4_1_extra_counters_includes_symbol_trade_counts_runtime():
    """_build_extra_counters must include symbol_trade_counts_runtime
    + symbol_fitness_runtime so essential save persists them."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._build_extra_counters)
    assert "DD4-1" in src, "DD4-1 marker missing"
    assert "symbol_trade_counts_runtime" in src, (
        "DD4-1 regression: extra_counters no longer carries runtime counts."
    )
    assert "symbol_fitness_runtime" in src, (
        "DD4-1 regression: extra_counters no longer carries runtime fitness."
    )


def test_dd4_1_apply_to_learner_restores_counts_and_fitness():
    """apply_to_learner / hydrate restores from the runtime copies."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine)
    # The restore block must mention DD4-1 + the runtime-keyed fields.
    restore_idx = src.find("DD4-1: restored runtime")
    assert restore_idx > 0, (
        "DD4-1 regression: restore log line removed."
    )


def test_dd4_2_reconcile_preserves_l0_entry_price():
    """_reconcile_fills no longer sets entry_price = broker_avg on
    pyramid collapse.  L0 entry_price is preserved so R-multiple math
    works; an add-fill becomes a separate L1 PyramidLevel."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._reconcile_fills)
    assert "DD4-2" in src, "DD4-2 marker missing"
    # The collapse-to-single-layer-with-broker_avg shape must be gone.
    assert "entry_price=broker_avg," not in src, (
        "DD4-2 regression: _reconcile_fills still collapses to broker_avg."
    )
    # We must reference l0_entry (preserved) AND `add_fill` (computed).
    assert "l0_entry" in src and "add_fill" in src, (
        "DD4-2 regression: L0-entry preservation + add-fill computation missing."
    )


def test_dd4_4_pyramider_telemetry_exposes_counters():
    """MomentumPyramider.telemetry() returns the counter dict."""
    from backend.organism.pyramider import MomentumPyramider
    pyr = MomentumPyramider()
    t = pyr.telemetry()
    assert "pyramid_count_total" in t
    assert "max_layers_reached" in t
    assert t["pyramid_count_total"] == 0
    pyr._pyramid_count = 5
    pyr._max_layers_reached = 2
    t2 = pyr.telemetry()
    assert t2["pyramid_count_total"] == 5
    assert t2["max_layers_reached"] == 2
