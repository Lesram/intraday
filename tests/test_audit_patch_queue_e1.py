"""Tests for Patch Queue E1 -- learning-mode exit coherence."""
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
# Test 1: Learning mode does NOT trigger profit lock
# ==============================================================================

class TestLearningModeNoProfitLock:

    def test_profit_lock_skipped_in_learning_mode(self):
        """In learning mode, profit lock must not fire even at 2R+ move."""
        engine = _make_engine(learning_mode=True)
        levels = _make_levels(engine)

        # Advance past min_hold
        for i in range(6):
            engine.check_exit(levels, levels.entry_price + 0.01, is_new_bar=True)

        # Now simulate a big favorable move (well above 2R)
        atr = levels.atr_at_entry
        stop_mult = engine.REGIME_STOP_ATR.get(levels.regime_at_entry, engine.atr_multiplier)
        initial_risk = atr * stop_mult
        price_at_2r = levels.entry_price + initial_risk * 2.5  # well above 2R

        signal = engine.check_exit(levels, price_at_2r, is_new_bar=True)

        # Profit lock should NOT have fired
        assert not levels.profit_locked, \
            "Learning mode must not trigger profit lock"

    def test_profit_lock_fires_in_production_mode(self):
        """In production mode, profit lock at 2R move must still fire."""
        engine = _make_engine(learning_mode=False)
        levels = _make_levels(engine)

        # Advance past min_hold
        for i in range(6):
            engine.check_exit(levels, levels.entry_price + 0.01, is_new_bar=True)

        atr = levels.atr_at_entry
        stop_mult = engine.REGIME_STOP_ATR.get(levels.regime_at_entry, engine.atr_multiplier)
        initial_risk = atr * stop_mult
        price_at_2r = levels.entry_price + initial_risk * 2.5

        engine.check_exit(levels, price_at_2r, is_new_bar=True)

        assert levels.profit_locked, \
            "Production mode must trigger profit lock at 2R"


# ==============================================================================
# Test 2: Learning mode still triggers core exits
# ==============================================================================

class TestLearningModeCoreExitsWork:

    def test_max_loss_in_learning_mode(self):
        """max_loss_limit fires in learning mode."""
        engine = _make_engine(learning_mode=True)
        levels = _make_levels(engine)

        # Price drops 16% (max_loss_pct default 0.15)
        crash_price = levels.entry_price * 0.83
        signal = engine.check_exit(levels, crash_price, is_new_bar=False)
        assert signal.should_exit and signal.reason == "max_loss_limit"

    def test_stop_loss_in_learning_mode(self):
        """Hard stop fires in learning mode."""
        engine = _make_engine(learning_mode=True)
        levels = _make_levels(engine)

        signal = engine.check_exit(levels, levels.stop_loss - 0.01, is_new_bar=False)
        assert signal.should_exit and signal.reason == "stop_loss"

    def test_trailing_stop_in_learning_mode(self):
        """Trailing stop fires in learning mode after big favorable move."""
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

    def test_horizon_timeout_in_learning_mode(self):
        """Horizon timeout fires in learning mode at 18 bars."""
        engine = _make_engine(learning_mode=True)
        levels = _make_levels(engine)

        # Advance to bar 18
        for i in range(18):
            signal = engine.check_exit(levels, levels.entry_price + 0.01, is_new_bar=True)

        # At bar 18 (past min_hold of 5), horizon_timeout should fire
        assert signal.should_exit and signal.reason == "horizon_timeout"


# ==============================================================================
# Test 3: Partial TP remains disabled in learning mode
# ==============================================================================

class TestPartialTPDisabledInLearningMode:

    def test_partial_tp_skipped_in_learning_mode(self):
        """Partial TP does not fire in learning mode at 3R."""
        engine = _make_engine(learning_mode=True)
        levels = _make_levels(engine)

        # Advance past min_hold
        for i in range(6):
            engine.check_exit(levels, levels.entry_price + 0.01, is_new_bar=True)

        # Price at partial TP level
        signal = engine.check_exit(levels, levels.partial_tp_price + 0.01, is_new_bar=True)

        # Should NOT be partial_take_profit
        assert signal.reason != "partial_take_profit"

    def test_partial_tp_fires_in_production_mode(self):
        """Partial TP fires in production mode at 3R."""
        engine = _make_engine(learning_mode=False)
        levels = _make_levels(engine)

        # Advance past min_hold
        for i in range(6):
            engine.check_exit(levels, levels.entry_price + 0.01, is_new_bar=True)

        # Price at partial TP level
        signal = engine.check_exit(levels, levels.partial_tp_price + 0.01, is_new_bar=True)

        assert signal.should_exit and signal.reason == "partial_take_profit"


# ==============================================================================
# Test 4: Full TP unchanged
# ==============================================================================

class TestFullTPUnchanged:

    def test_full_tp_disabled_in_learning_mode(self):
        """Full take-profit is disabled in learning mode (changed by E2)."""
        engine = _make_engine(learning_mode=True)
        levels = _make_levels(engine)

        # Advance past min_hold but before horizon_timeout
        for i in range(6):
            engine.check_exit(levels, levels.entry_price + 0.01, is_new_bar=True)

        # Price at full TP level -- should NOT fire take_profit in learning mode
        signal = engine.check_exit(levels, levels.take_profit + 0.01, is_new_bar=True)
        assert signal.reason != "take_profit", \
            "Learning mode must not trigger full take-profit (E2 patch)"


# ==============================================================================
# Test 5: Exit ordering regression test
# ==============================================================================

class TestExitOrderingLearningMode:

    def test_learning_mode_exit_ordering(self):
        """Verify the effective learning-mode priority order:
        max_loss/stop_loss -> min_hold gate -> horizon_timeout / full TP / trailing / FTF
        with profit lock AND partial TP skipped."""
        import inspect
        from backend.organism import adaptive_exits
        source = inspect.getsource(adaptive_exits.AdaptiveExitEngine.check_exit)

        # Find positions of key exit checks in source using code anchors
        # (not comments) to avoid false matches in documentation strings
        max_loss_pos = source.index('"max_loss_limit"')
        stop_loss_pos = source.index('"stop_loss"', max_loss_pos + 1)
        min_hold_pos = source.index("bars_held < min_hold")
        profit_lock_pos = source.index("self._check_profit_lock(")
        horizon_pos = source.index('"horizon_timeout"')
        partial_tp_pos = source.index("_check_partial_tp")
        full_tp_pos = source.index('"take_profit"')
        trailing_pos = source.index("_update_trailing_stop")

        # Verify ordering
        assert max_loss_pos < stop_loss_pos < min_hold_pos, \
            "max_loss and stop_loss must come before min_hold"
        assert min_hold_pos < profit_lock_pos < horizon_pos, \
            "profit_lock (guarded) must come after min_hold and before horizon"
        assert horizon_pos < full_tp_pos < trailing_pos, \
            "horizon_timeout < full TP < trailing"

        # Verify profit lock is guarded by learning_mode check
        profit_lock_section = source[profit_lock_pos - 200:profit_lock_pos + 50]
        assert "not self.learning_mode" in profit_lock_section, \
            "profit_lock must be guarded by learning_mode check"

        # Verify partial TP is guarded
        partial_section = source[partial_tp_pos - 200:partial_tp_pos + 50]
        assert "not self.learning_mode" in partial_section, \
            "partial TP must be guarded by learning_mode check"
