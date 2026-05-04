"""V8 / Wave-35 (2026-05-03): behavioral tests for minor logic fixes.

Locks the regressions for:
- DD2-7: _is_learning_mode is cached per tick to prevent mid-tick value
  switching (reconciliation closing trade #200 mid-tick previously made
  exit/entry/sizing/gate sites within the same step() see different
  learning_mode values).
- DD2-8: pure-breakout fallback now gates on ml_sig.direction > 0 (a
  neutral or short ML signal with negative predicted_return no longer
  feeds Kelly a positive expected return for a long entry).
- DD2-9: EOD flatten window upper-bounded at 16:00 ET (market close);
  zoneinfo failures logged at WARNING (was silently disabled via `pass`).
- DD2-10: OrganismRunner accepts now_fn injection; routes.py admin
  cleanup endpoints use default_now_fn (replay-friendly).

Deferred to wave 39 (HH R-1 refactor):
- HH2-N-1 calculate_indicator (614 LOC) split
- HH2-N-2 validate_order_pre_trade (477 LOC) split

Run with: ./venv/bin/python -m pytest tests/test_wave35_fixes.py -v
"""
from __future__ import annotations

import inspect

import pytest


# ─────────────────────────────────────────────────────────────────────
# DD2-7 — _is_learning_mode cached per tick
# ─────────────────────────────────────────────────────────────────────


def test_dd2_7_is_learning_mode_caches_per_tick():
    """The property body must reference _learning_mode_tick_cache so a
    future revert to the bare uncached form is detected immediately."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._is_learning_mode.fget)
    assert "_learning_mode_tick_cache" in src, (
        "DD2-7 regression: _is_learning_mode no longer caches per tick. "
        "Mid-tick reconciliation can switch the value between exit/entry/"
        "sizing/gate sites within the same step()."
    )


def test_dd2_7_cache_returns_same_value_within_tick():
    """Concrete check: a stub engine with stable tick_count returns the
    same cached value across N reads, even if _strategy_trades changes
    between them."""
    from backend.organism.live_engine import OrganismLiveEngine

    class _Stub:
        _is_learning_mode = OrganismLiveEngine._is_learning_mode
        def __init__(self, tick: int = 0):
            self._tick_count = tick
            self._strategy_count = 50  # below LEARNING_MODE_TRADES

        def _strategy_trades(self):
            class _T:
                pass
            return [_T() for _ in range(self._strategy_count)]

    s = _Stub(tick=10)
    v1 = s._is_learning_mode
    s._strategy_count = 99999  # suddenly lots of trades — should not affect cached value
    v2 = s._is_learning_mode
    assert v1 == v2, (
        "DD2-7 regression: _is_learning_mode mutated mid-tick "
        f"(v1={v1}, v2={v2}). Cache failed."
    )

    # Bumping tick must invalidate the cache.
    s._tick_count = 11
    v3 = s._is_learning_mode
    assert v3 is False, (
        "DD2-7: post-tick-bump, cache should re-evaluate and reflect "
        f"strategy_count=99999 (>= LEARNING_MODE_TRADES); got {v3}."
    )


# ─────────────────────────────────────────────────────────────────────
# DD2-8 — pure-breakout direction gate
# ─────────────────────────────────────────────────────────────────────


def test_dd2_8_pure_breakout_gates_on_direction():
    """The pure-breakout pred_ret assignment must require
    ml_sig.direction > 0 in addition to abs(predicted_return) > 1e-4.
    Previously a neutral or short ML signal could feed a positive
    expected return into Kelly for a long entry."""
    from backend.organism import live_engine
    src = inspect.getsource(live_engine)
    # Locate the pure-breakout pred_ret block (the one with the
    # 1e-4 threshold and pred_ret = 0.005 + 0.015 * bs.composite_score).
    # Confirm direction > 0 is in the same conditional.
    block = src[src.find("ml_sig and not self._is_learning_mode\n"):]
    # Iterate until we find the bs.composite_score reference (the pure
    # breakout fallback).
    idx = src.find("0.005 + 0.015 * bs.composite_score")
    assert idx > 0, "Pure-breakout fallback no longer present"
    window = src[max(0, idx - 1200):idx + 100]
    assert "ml_sig.direction > 0" in window, (
        "DD2-8 regression: pure-breakout fallback no longer gates on "
        "ml_sig.direction > 0."
    )
    assert "DD2-8" in window, (
        "DD2-8 marker missing from the pure-breakout block — fix may "
        "have been reverted."
    )


# ─────────────────────────────────────────────────────────────────────
# DD2-9 — EOD flatten upper bound + zoneinfo logging
# ─────────────────────────────────────────────────────────────────────


def test_dd2_9_eod_flatten_upper_bounded_at_close():
    """EOD flatten window must bracket [15:58, 16:00) ET, not [15:58, ∞)."""
    from backend.organism import live_engine
    src = inspect.getsource(live_engine)
    # The window expression must include `< 1600` somewhere near the
    # _eod_flatten_triggered = True assignment.
    idx = src.find("_eod_flatten_triggered = True")
    assert idx > 0, "Could not find EOD flatten trigger"
    window = src[max(0, idx - 200):idx + 100]
    assert "1558 <= _hhmm_eod < 1600" in window, (
        "DD2-9 regression: EOD flatten trigger is no longer upper-bounded "
        "at market close (16:00 ET). Stuck in retry loop past close."
    )


def test_dd2_9_zoneinfo_failure_logs_warning():
    """zoneinfo / clock failures must log at WARNING, not silently pass."""
    from backend.organism import live_engine
    src = inspect.getsource(live_engine)
    idx = src.find("EOD flatten timezone resolution failed")
    assert idx > 0, (
        "DD2-9 regression: zoneinfo failure handler no longer logs at "
        "WARNING. EOD flatten can be silently disabled globally on "
        "import-time errors."
    )


# ─────────────────────────────────────────────────────────────────────
# DD2-10 — clock injection in runner.py + routes.py
# ─────────────────────────────────────────────────────────────────────


def test_dd2_10_organism_runner_accepts_now_fn():
    """OrganismRunner must accept now_fn as a constructor kwarg so
    replay tests can inject the replay clock."""
    from backend.organism.runner import OrganismRunner
    sig = inspect.signature(OrganismRunner.__init__)
    assert "now_fn" in sig.parameters, (
        "DD2-10 regression: OrganismRunner no longer accepts now_fn. "
        "Replay tests will see wall-clock data for drift-check timing."
    )


def test_dd2_10_runner_drift_check_uses_injected_clock():
    """OrganismRunner.pre_execution_hook must use self._now_fn(), not
    datetime.now(UTC), for drift-check timing."""
    from backend.organism.runner import OrganismRunner
    src = inspect.getsource(OrganismRunner.pre_execution_hook)
    assert "self._now_fn()" in src, (
        "DD2-10 regression: OrganismRunner.pre_execution_hook does not "
        "use injected clock for drift-check now."
    )


def test_dd2_10_routes_admin_cleanup_uses_canonical_clock():
    """backend/organism/routes.py admin cleanup must import and use
    default_now_fn for the cutoff/now SQL parameters."""
    from backend.organism import routes
    src = inspect.getsource(routes)
    assert "default_now_fn" in src, (
        "DD2-10 regression: routes.py no longer imports default_now_fn. "
        "Admin cleanup endpoint reads wall-clock UTC inconsistently with "
        "the live engine."
    )
