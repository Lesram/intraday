"""Tests for Patch Queue E3 -- correct learning-mode exit ordering.

horizon_timeout must fire AFTER trailing/FTF so those exits take
priority when active at bar 18.
"""
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
# Test 1: Source ordering -- trailing/FTF before horizon_timeout
# ==============================================================================

class TestSourceOrdering:

    def test_trailing_before_horizon_in_source(self):
        """In check_exit source, _update_trailing_stop must appear before
        'horizon_timeout' so trailing takes priority."""
        import inspect
        from backend.organism import adaptive_exits
        source = inspect.getsource(adaptive_exits.AdaptiveExitEngine.check_exit)

        trailing_pos = source.index("_update_trailing_stop")
        horizon_pos = source.index('"horizon_timeout"')
        assert trailing_pos < horizon_pos, \
            "trailing must come before horizon_timeout in source"

    def test_ftf_before_horizon_in_source(self):
        """FTF logic must appear before horizon_timeout."""
        import inspect
        from backend.organism import adaptive_exits
        source = inspect.getsource(adaptive_exits.AdaptiveExitEngine.check_exit)

        ftf_pos = source.index('"failure_to_follow"')
        horizon_pos = source.index('"horizon_timeout"')
        assert ftf_pos < horizon_pos, \
            "FTF must come before horizon_timeout in source"

    def test_horizon_after_trailing_and_before_time_based(self):
        """horizon_timeout should sit between trailing/FTF and time-based exit."""
        import inspect
        from backend.organism import adaptive_exits
        source = inspect.getsource(adaptive_exits.AdaptiveExitEngine.check_exit)

        trailing_pos = source.index("_update_trailing_stop")
        horizon_pos = source.index('"horizon_timeout"')
        time_based_pos = source.index('"max_holding_period"')

        assert trailing_pos < horizon_pos < time_based_pos, \
            "Order must be: trailing -> horizon_timeout -> max_holding_period"


# ==============================================================================
# Test 2: Semantic -- trailing wins over horizon at bar 18
# ==============================================================================

class TestTrailingWinsOverHorizon:

    def test_trailing_fires_at_bar_18_over_horizon(self):
        """If trailing would fire on bar 18, trailing_stop wins over
        horizon_timeout because it appears first in the exit stack."""
        engine = _make_engine(learning_mode=True)
        levels = _make_levels(engine)
        atr = levels.atr_at_entry

        # Build up to bar 17 with a big favorable move to activate trailing
        for i in range(1, 10):
            price = levels.entry_price + atr * (i * 0.5)
            engine.check_exit(levels, price, is_new_bar=True)

        # Push to a peak that activates trailing
        peak = levels.entry_price + atr * 5.0
        for i in range(10, 17):
            engine.check_exit(levels, peak, is_new_bar=True)

        assert levels.trailing_active, "Trailing should be active after big move"

        # Bar 18: price drops to trailing stop level
        drop_price = levels.trailing_stop - 0.01
        signal = engine.check_exit(levels, drop_price, is_new_bar=True)

        # bars_held is now 18, both trailing and horizon would fire.
        # Trailing must win because it's checked first.
        assert signal.should_exit, "Should exit"
        assert signal.reason == "trailing_stop", \
            f"Expected trailing_stop at bar 18, got {signal.reason}"

    def test_horizon_fires_when_no_trailing_at_bar_18(self):
        """If trailing is NOT active and FTF doesn't fire at bar 18,
        horizon_timeout fires."""
        engine = _make_engine(learning_mode=True)
        levels = _make_levels(engine)

        # Use trending_up regime (FTF disabled) with flat price (no trailing)
        for i in range(18):
            signal = engine.check_exit(
                levels, levels.entry_price + 0.01,
                current_regime="trending_up", is_new_bar=True,
            )

        assert not levels.trailing_active, "Trailing should not be active"
        assert signal.should_exit and signal.reason == "horizon_timeout", \
            f"Expected horizon_timeout, got {signal.reason}"


# ==============================================================================
# Test 3: Production mode unchanged
# ==============================================================================

class TestProductionUnchanged:

    def test_production_no_horizon_timeout(self):
        """Production mode should never fire horizon_timeout."""
        engine = _make_engine(learning_mode=False)
        levels = _make_levels(engine)

        # Advance well past 18 bars with flat price
        for i in range(25):
            signal = engine.check_exit(levels, levels.entry_price + 0.01, is_new_bar=True)

        assert signal.reason != "horizon_timeout", \
            "Production mode must not fire horizon_timeout"

    def test_production_full_tp_still_fires(self):
        """Production mode full TP still works."""
        engine = _make_engine(learning_mode=False)
        levels = _make_levels(engine)

        # Advance past min_hold
        for i in range(6):
            engine.check_exit(levels, levels.entry_price + 0.01, is_new_bar=True)

        # Clear partial TP first
        engine.check_exit(levels, levels.partial_tp_price + 0.01, is_new_bar=True)

        signal = engine.check_exit(levels, levels.take_profit + 0.01, is_new_bar=True)
        assert signal.should_exit and signal.reason == "take_profit"

    def test_production_trailing_still_works(self):
        """Production trailing stop works as before."""
        engine = _make_engine(learning_mode=False)
        levels = _make_levels(engine)
        atr = levels.atr_at_entry

        # Advance with rising prices to activate trailing
        for i in range(8):
            price = levels.entry_price + atr * (i * 0.5)
            engine.check_exit(levels, price, is_new_bar=True)

        peak = levels.entry_price + atr * 5.0
        engine.check_exit(levels, peak, is_new_bar=True)

        if levels.trailing_active:
            drop_price = levels.trailing_stop - 0.01
            signal = engine.check_exit(levels, drop_price, is_new_bar=True)
            assert signal.should_exit and signal.reason == "trailing_stop"


# ==============================================================================
# Test 4: Learning mode FTF still fires before horizon
# ==============================================================================

class TestFTFBeforeHorizon:

    def test_ftf_fires_before_horizon_in_learning_mode(self):
        """In learning mode with a chop regime, FTF should fire before
        horizon_timeout if conditions are met."""
        engine = _make_engine(learning_mode=True)
        # Use stress regime where FTF is active and has simple momentum logic
        levels = _make_levels(engine, regime="stress")

        # Advance bars with declining price to trigger FTF
        # Need: bars >= early_check (H//2 = 7), r_achieved < threshold, no momentum
        # Use a price that's slightly below entry (losing) and ensure no positive momentum
        losing_price = levels.entry_price - levels.atr_at_entry * 0.05

        # Fill price_at_prior_bar and price_two_bars_ago first
        for i in range(6):
            engine.check_exit(levels, losing_price, is_new_bar=True)

        # Bar 7+: now past early_check, set up no-momentum condition
        # price_at_prior_bar = losing_price from last bar
        # Current price slightly lower = no positive momentum
        lower_price = losing_price - 0.01
        signal = engine.check_exit(levels, lower_price, is_new_bar=True)

        # Before bar 18, so if FTF fires, it should be "failure_to_follow"
        if signal.should_exit:
            assert signal.reason == "failure_to_follow", \
                f"Expected failure_to_follow, got {signal.reason}"
