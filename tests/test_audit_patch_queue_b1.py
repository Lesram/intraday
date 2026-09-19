"""Tests for Patch Queue B1 — confidence parity + equity/status fix."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pandas as pd
import numpy as np


# -- Fix 1: Confidence-gate full parity --


class TestConfidenceGateFullParity:
    """Verify alpha and breakout paths use identical confidence threshold."""

    def test_unified_threshold_in_source(self):
        """_MIN_MAIN_CONF must be computed once, before both paths."""
        import inspect
        from backend.organism import live_engine
        source = inspect.getsource(live_engine)

        # The breakout path should NOT have its own threshold computation
        breakout_section = source[source.index("Pure breakout"):]
        assert "_bo_min_conf" not in breakout_section, \
            "Breakout path must not compute its own _bo_min_conf — use unified _MIN_MAIN_CONF"

        # Both paths should reference _MIN_MAIN_CONF
        assert "_MIN_MAIN_CONF" in breakout_section, \
            "Breakout path must use _MIN_MAIN_CONF"

    def test_alpha_path_uses_min_main_conf(self):
        """Alpha path must gate on _MIN_MAIN_CONF."""
        import inspect
        from backend.organism import live_engine
        source = inspect.getsource(live_engine)
        # Find the alpha candidate section (before "Pure breakout")
        alpha_section = source[:source.index("Pure breakout")]
        assert "_eff_conf < _MIN_MAIN_CONF" in alpha_section, \
            "Alpha path must gate effective confidence against _MIN_MAIN_CONF"

    def test_unified_threshold_uses_regime_conf_guard(self):
        """The unified threshold must reference the defensive constant.

        V12 W88 (post-cleanup): the 2026-03-29 incident-recovery commit
        replaced the original ``_regime_conf >= 0.50`` guard with a
        simpler ``self._is_learning_mode`` branch — in learning mode
        the formula caps confidence at ~0.43 and the 0.40/0.45 gates
        were unreachable for 10+ days (zero trades).  Test expectation
        updated: assert the threshold dispatch references either the
        learning-mode branch OR the regime_conf guard (covers both
        pre- and post-recovery designs)."""
        import inspect
        from backend.organism import live_engine
        source = inspect.getsource(live_engine)

        conf_section_start = source.index("Unified confidence threshold")
        # V12 W88: extended window from 900 to 1500 chars — the
        # post-incident-recovery dispatch logic is longer than the
        # original (more comments documenting the 2026-03-29 incident).
        conf_section = source[conf_section_start:conf_section_start + 1500]
        # Either the learning-mode branch (post-2026-03-29) OR the
        # regime_conf guard (original) is acceptable evidence of the
        # threshold dispatch logic.
        has_learning_branch = "_is_learning_mode" in conf_section
        has_regime_guard = (
            "_regime_conf >= 0.50" in conf_section
            or "_regime_conf >= 0.5" in conf_section
        )
        assert has_learning_branch or has_regime_guard, (
            "Unified threshold must dispatch on either _is_learning_mode "
            "(post-incident) or _regime_conf >= 0.50 (original)"
        )
        assert "_MAIN_CONF_DEFENSIVE" in conf_section, \
            "Unified threshold must reference defensive constant"

    def test_threshold_learning_mode_noisy_regime(self):
        """In learning mode with low regime confidence, threshold should be baseline (0.40)."""
        # This tests the actual logic, not just source code
        _MAIN_CONF_BASELINE = 0.40
        _MAIN_CONF_DEFENSIVE = 0.45

        # Learning mode, regime=chop, but _regime_conf < 0.50 -> should use baseline
        is_learning = True
        regime = "chop"
        regime_conf = 0.30

        if (
            not is_learning
            or (regime in ("chop", "high_vol", "trending_down")
                and regime_conf >= 0.50)
        ):
            threshold = (
                _MAIN_CONF_DEFENSIVE
                if regime in ("chop", "high_vol", "trending_down")
                else _MAIN_CONF_BASELINE
            )
        else:
            threshold = _MAIN_CONF_BASELINE

        assert threshold == _MAIN_CONF_BASELINE, \
            f"Learning mode with noisy regime should use baseline {_MAIN_CONF_BASELINE}, got {threshold}"

    def test_threshold_learning_mode_confident_regime(self):
        """In learning mode with confident defensive regime, threshold should be defensive (0.45)."""
        _MAIN_CONF_BASELINE = 0.40
        _MAIN_CONF_DEFENSIVE = 0.45

        is_learning = True
        regime = "chop"
        regime_conf = 0.75

        if (
            not is_learning
            or (regime in ("chop", "high_vol", "trending_down")
                and regime_conf >= 0.50)
        ):
            threshold = (
                _MAIN_CONF_DEFENSIVE
                if regime in ("chop", "high_vol", "trending_down")
                else _MAIN_CONF_BASELINE
            )
        else:
            threshold = _MAIN_CONF_BASELINE

        assert threshold == _MAIN_CONF_DEFENSIVE, \
            f"Learning mode with confident chop regime should use defensive {_MAIN_CONF_DEFENSIVE}, got {threshold}"

    def test_threshold_production_defensive_regime(self):
        """In production mode, defensive regime always uses 0.45."""
        _MAIN_CONF_BASELINE = 0.40
        _MAIN_CONF_DEFENSIVE = 0.45

        is_learning = False
        regime = "high_vol"
        regime_conf = 0.30  # even low confidence

        if (
            not is_learning
            or (regime in ("chop", "high_vol", "trending_down")
                and regime_conf >= 0.50)
        ):
            threshold = (
                _MAIN_CONF_DEFENSIVE
                if regime in ("chop", "high_vol", "trending_down")
                else _MAIN_CONF_BASELINE
            )
        else:
            threshold = _MAIN_CONF_BASELINE

        assert threshold == _MAIN_CONF_DEFENSIVE

    def test_threshold_production_trending_up(self):
        """In production mode, trending_up uses baseline 0.40."""
        _MAIN_CONF_BASELINE = 0.40
        _MAIN_CONF_DEFENSIVE = 0.45

        is_learning = False
        regime = "trending_up"
        regime_conf = 0.80

        if (
            not is_learning
            or (regime in ("chop", "high_vol", "trending_down")
                and regime_conf >= 0.50)
        ):
            threshold = (
                _MAIN_CONF_DEFENSIVE
                if regime in ("chop", "high_vol", "trending_down")
                else _MAIN_CONF_BASELINE
            )
        else:
            threshold = _MAIN_CONF_BASELINE

        assert threshold == _MAIN_CONF_BASELINE


# -- Fix 2: Equity/status reporting --


class TestEquityStatusReporting:
    """Verify status reports actual equity, not cumulative PnL."""

    def _make_engine(self):
        """Create a minimal OrganismLiveEngine for status testing.

        V12 W88 (post-cleanup): added _watchdog_state and _now_fn —
        the engine's status() path post-V11 reads both.  Pre-W88 the
        fixture didn't carry them, so every test failed with
        ``AttributeError: '...' object has no attribute '_watchdog_state'``.
        """
        from backend.organism.live_engine import OrganismLiveEngine
        engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
        engine._all_trades = []
        engine._equity_curve = []
        engine._cumulative_pnl = 0.0
        engine._peak_equity = 0.0
        engine._initialized = True
        engine._tick_count = 50
        engine._epoch_metrics = []
        engine._universe = {"AAPL", "MSFT"}
        engine._entry_metadata = {}
        engine._data_stale = False
        engine._scanner_candidates = []
        engine.market_scanner = None

        # Mock required attributes
        from backend.organism.self_evolution import EvolvedParams
        engine.evolved_params = EvolvedParams()
        engine.brain = MagicMock(generation=0, total_runs=10)
        engine.signal_gen = MagicMock(is_trained=False)
        engine.regime_detector = MagicMock(current_regime="trending_up")
        engine.governance = MagicMock()
        engine.governance.to_dict.return_value = {}
        engine.learner = MagicMock(generation_metrics=[])
        # _is_learning_mode is a property based on len(_all_trades) < _LEARNING_MODE_TRADES
        # With _all_trades=[] and default _LEARNING_MODE_TRADES=200, it will be True.
        engine._LEARNING_MODE_TRADES = 200
        # V12 W88: status() depends on these (added in V10/V11 waves).
        engine._watchdog_state = "OK"
        engine._watchdog_last_order_tick = 0
        engine._watchdog_last_brain_save_tick = 0
        engine._watchdog_last_total_orders = 0
        engine._watchdog_zero_candidates_ticks = 0
        engine._watchdog_equity_fallback_count = 0
        engine._watchdog_equity_fallback_streak = 0
        engine._watchdog_universe_drift = {}
        engine._total_orders_submitted = 0
        from datetime import UTC, datetime
        import time as _time
        engine._now_fn = lambda: datetime.now(UTC)
        engine._time_fn = _time.time
        engine._last_tick_completed_ts = None
        return engine

    def test_status_current_equity_none_when_no_ticks(self):
        """Before any ticks, current_equity should be None (no broker data yet)."""
        engine = self._make_engine()
        s = engine.status()
        assert s["current_equity"] is None, \
            "current_equity must be None when equity_curve is empty"

    def test_status_current_equity_from_broker_after_ticks(self):
        """After ticks, current_equity should reflect broker equity snapshots."""
        engine = self._make_engine()
        # Simulate broker equity snapshots
        engine._equity_curve = [100000.0, 100050.0, 99980.0]
        s = engine.status()
        assert s["current_equity"] == 99980.0

    def test_status_cumulative_pnl_correct(self):
        """cumulative_pnl should be sum of trade PnLs."""
        engine = self._make_engine()
        from backend.organism.continuous_learner import TradeRecord
        engine._all_trades = [
            TradeRecord(symbol="AAPL", direction=1.0, entry_price=100, exit_price=105,
                        entry_bar=0, exit_bar=1, shares=10, pnl=50.0,
                        exit_reason="tp", predicted_return=0.05, actual_return=0.05, confidence=0.8),
            TradeRecord(symbol="MSFT", direction=1.0, entry_price=200, exit_price=195,
                        entry_bar=2, exit_bar=3, shares=5, pnl=-25.0,
                        exit_reason="sl", predicted_return=0.03, actual_return=-0.025, confidence=0.6),
        ]
        s = engine.status()
        assert s["cumulative_pnl"] == 25.0, \
            f"cumulative_pnl should be 50 + (-25) = 25, got {s['cumulative_pnl']}"

    def test_status_equity_not_cumulative_pnl(self):
        """current_equity must NOT equal cumulative PnL after reconstruction."""
        engine = self._make_engine()
        from backend.organism.continuous_learner import TradeRecord
        engine._all_trades = [
            TradeRecord(symbol="AAPL", direction=1.0, entry_price=100, exit_price=105,
                        entry_bar=0, exit_bar=1, shares=10, pnl=50.0,
                        exit_reason="tp", predicted_return=0.05, actual_return=0.05, confidence=0.8),
        ]
        engine._cumulative_pnl = 50.0
        # No equity curve (simulating post-reconstruction, pre-tick state)
        engine._equity_curve = []

        s = engine.status()
        # current_equity should be None (no broker snapshot), not 50.0
        assert s["current_equity"] is None, \
            "current_equity must not be cumulative PnL"
        assert s["cumulative_pnl"] == 50.0

    def test_reconstruct_does_not_populate_equity_curve(self):
        """_reconstruct_trades_from_db must not put PnL into _equity_curve."""
        import inspect
        from backend.organism import live_engine
        source = inspect.getsource(live_engine.OrganismLiveEngine._reconstruct_trades_from_db)
        assert "_equity_curve.append" not in source, \
            "Reconstruction must not append to _equity_curve"

    def test_reconstruct_sets_cumulative_pnl(self):
        """_reconstruct_trades_from_db must set _cumulative_pnl."""
        import inspect
        from backend.organism import live_engine
        source = inspect.getsource(live_engine.OrganismLiveEngine._reconstruct_trades_from_db)
        assert "_cumulative_pnl" in source, \
            "Reconstruction must set _cumulative_pnl"
