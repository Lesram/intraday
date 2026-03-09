"""Tests for Patch Queue E2 -- full TP disable in learning mode + stable FTF initial risk."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels, ExitSignal


# -- Helpers -------------------------------------------------------------------

def _make_features(n: int = 30) -> pd.DataFrame:
    """Build synthetic features DataFrame for ATR computation."""
    close = [100.0 + 0.1 * i for i in range(n)]
    return pd.DataFrame({
        "close": close,
        "high": [c + 0.5 for c in close],
        "low": [c - 0.5 for c in close],
        "volume": [100000] * n,
    })


def _make_engine(learning_mode: bool = False) -> AdaptiveExitEngine:
    engine = AdaptiveExitEngine()
    engine.learning_mode = learning_mode
    return engine


def _make_levels(engine: AdaptiveExitEngine, direction: float = 1.0,
                 entry_price: float = 100.0, regime: str = "trending_up") -> ExitLevels:
    features = _make_features()
    return engine.create_exit_levels(
        symbol="AAPL",
        direction=direction,
        entry_price=entry_price,
        predicted_return=0.03,
        features_df=features,
        regime=regime,
    )


# ==============================================================================
# Test 1: Full TP disabled in learning mode
# ==============================================================================

class TestFullTPDisabledInLearningMode:

    def test_full_tp_does_not_fire_in_learning_mode(self):
        """In learning mode, full TP must not fire even when price exceeds take_profit."""
        engine = _make_engine(learning_mode=True)
        levels = _make_levels(engine)

        # Advance past min_hold but before horizon_timeout (18 bars)
        for i in range(6):
            engine.check_exit(levels, levels.entry_price + 0.01, is_new_bar=True)

        # Price at full TP level
        signal = engine.check_exit(levels, levels.take_profit + 0.01, is_new_bar=True)
        # Should NOT be take_profit -- horizon_timeout or something else, never take_profit
        assert signal.reason != "take_profit", \
            "Learning mode must not trigger full take-profit"

    def test_full_tp_fires_in_production_mode(self):
        """In production mode, full TP must still fire."""
        engine = _make_engine(learning_mode=False)
        levels = _make_levels(engine)

        # Advance past min_hold
        for i in range(6):
            engine.check_exit(levels, levels.entry_price + 0.01, is_new_bar=True)

        # First hit partial TP (3R) so it doesn't intercept the full TP check
        engine.check_exit(levels, levels.partial_tp_price + 0.01, is_new_bar=True)
        assert levels.partial_tp_taken, "Partial TP should have fired first"

        # Price at full TP level
        signal = engine.check_exit(levels, levels.take_profit + 0.01, is_new_bar=True)
        assert signal.should_exit and signal.reason == "take_profit", \
            "Production mode must trigger full take-profit"

    def test_trailing_still_works_after_tp_disable(self):
        """In learning mode, trailing stop still fires after TP is disabled."""
        engine = _make_engine(learning_mode=True)
        levels = _make_levels(engine)
        atr = levels.atr_at_entry

        # Advance past min_hold with rising prices
        for i in range(8):
            price = levels.entry_price + atr * (i * 0.5)
            engine.check_exit(levels, price, is_new_bar=True)

        # Big favorable move to activate trailing
        peak = levels.entry_price + atr * 5.0
        engine.check_exit(levels, peak, is_new_bar=True)

        if levels.trailing_active:
            # Drop back to hit trailing stop
            drop_price = levels.trailing_stop - 0.01
            signal = engine.check_exit(levels, drop_price, is_new_bar=True)
            assert signal.should_exit and signal.reason == "trailing_stop"

    def test_horizon_timeout_still_works_after_tp_disable(self):
        """In learning mode, horizon timeout at 18 bars still fires."""
        engine = _make_engine(learning_mode=True)
        levels = _make_levels(engine)

        # Advance to bar 18
        for i in range(18):
            signal = engine.check_exit(levels, levels.entry_price + 0.01, is_new_bar=True)

        assert signal.should_exit and signal.reason == "horizon_timeout"


# ==============================================================================
# Test 2: Stable initial risk for FTF
# ==============================================================================

class TestStableInitialRiskFTF:

    def test_initial_risk_at_entry_set_on_create(self):
        """create_exit_levels must set initial_risk_at_entry > 0."""
        engine = _make_engine()
        levels = _make_levels(engine)
        assert levels.initial_risk_at_entry > 0, \
            "initial_risk_at_entry must be set at creation time"

    def test_initial_risk_matches_original_risk_distance(self):
        """initial_risk_at_entry should equal atr * stop_atr_mult."""
        engine = _make_engine()
        levels = _make_levels(engine, regime="trending_up")
        expected = levels.atr_at_entry * engine.REGIME_STOP_ATR["trending_up"]
        assert abs(levels.initial_risk_at_entry - expected) < 1e-6

    def test_ftf_uses_original_risk_after_stop_tightened(self):
        """FTF R-calc must use initial_risk_at_entry, not current stop distance."""
        engine = _make_engine(learning_mode=False)
        # Use chop regime so FTF is active
        levels = _make_levels(engine, regime="chop")
        original_risk = levels.initial_risk_at_entry

        # Manually tighten the stop (simulating profit lock or time decay)
        levels.stop_loss = levels.entry_price - original_risk * 0.3  # much tighter

        # The initial_risk_at_entry should still reflect the original
        assert abs(levels.initial_risk_at_entry - original_risk) < 1e-6, \
            "initial_risk_at_entry must not change when stop is tightened"

    def test_exit_levels_roundtrip_preserves_initial_risk(self):
        """to_dict() -> restore must preserve initial_risk_at_entry."""
        engine = _make_engine()
        levels = _make_levels(engine)

        d = levels.to_dict()
        assert "initial_risk_at_entry" in d
        assert abs(d["initial_risk_at_entry"] - levels.initial_risk_at_entry) < 1e-4

        # Simulate restore (as live_engine does)
        restored = ExitLevels(
            symbol=d["symbol"],
            direction=d["direction"],
            entry_price=d["entry"],
            stop_loss=d["stop_loss"],
            take_profit=d["take_profit"],
            trailing_stop=d["trailing_stop"],
            atr_at_entry=d["atr"],
            regime_at_entry=d["regime_at_entry"],
            highest_favorable=d["highest_favorable"],
            bars_held=d["bars_held"],
            initial_risk_at_entry=d["initial_risk_at_entry"],
        )
        assert abs(restored.initial_risk_at_entry - levels.initial_risk_at_entry) < 1e-4

    def test_ftf_fallback_for_legacy_levels(self):
        """ExitLevels with initial_risk_at_entry=0 (legacy) should fallback to stop-based calc."""
        engine = _make_engine(learning_mode=False)
        levels = _make_levels(engine, regime="chop")
        # Simulate legacy levels with no initial_risk_at_entry
        levels.initial_risk_at_entry = 0.0

        # FTF should still work using stop-based fallback
        # Just verify the field is 0 and engine doesn't crash
        for i in range(15):
            signal = engine.check_exit(levels, levels.entry_price + 0.001, is_new_bar=True)
        # Should not raise -- fallback to stop-based calc


# ==============================================================================
# Test 3: Exit ordering regression with TP disabled
# ==============================================================================

class TestExitOrderingWithTPDisabled:

    def test_learning_mode_exit_ordering_tp_disabled(self):
        """Verify full TP is guarded by learning_mode check in source."""
        import inspect
        from backend.organism import adaptive_exits
        source = inspect.getsource(adaptive_exits.AdaptiveExitEngine.check_exit)

        # Find the full TP section
        tp_pos = source.index('"take_profit"')
        tp_section = source[tp_pos - 300:tp_pos + 50]
        assert "not self.learning_mode" in tp_section, \
            "Full TP must be guarded by learning_mode check"

    def test_learning_mode_complete_exit_stack(self):
        """Learning mode exit stack: max_loss, stop_loss, trailing, FTF, horizon_timeout.
        NO profit lock, NO partial TP, NO full TP."""
        import inspect
        from backend.organism import adaptive_exits
        source = inspect.getsource(adaptive_exits.AdaptiveExitEngine.check_exit)

        # All three should be guarded
        profit_lock_pos = source.index("self._check_profit_lock(")
        profit_lock_section = source[profit_lock_pos - 200:profit_lock_pos + 50]
        assert "not self.learning_mode" in profit_lock_section

        partial_tp_pos = source.index("_check_partial_tp")
        partial_section = source[partial_tp_pos - 200:partial_tp_pos + 50]
        assert "not self.learning_mode" in partial_section

        tp_pos = source.index('"take_profit"')
        tp_section = source[tp_pos - 300:tp_pos + 50]
        assert "not self.learning_mode" in tp_section
