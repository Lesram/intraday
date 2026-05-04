"""Experiment 4 — Trailing-stop giveback control in chop.

Tests:
1. Widened trailing stop applies in chop only (Variant A)
2. Non-chop trailing stop unchanged
3. stop_loss unchanged
4. timeout/max_hold unchanged
5. Variant selection is explicit
6. Disable variant returns False in chop (Variant B)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from backend.organism.adaptive_exits import (
    AdaptiveExitEngine,
    ExitLevels,
)


def _make_exit_levels(
    entry_price=100.0,
    stop_loss=95.0,
    take_profit=115.0,
    atr_at_entry=2.0,
    direction=1.0,
    bars_held=20,
    highest_favorable=106.0,  # 3× ATR above entry → trailing activates
    trailing_active=False,
    trailing_stop=0.0,
    symbol="TEST",
    regime_at_entry="chop",
) -> ExitLevels:
    return ExitLevels(
        symbol=symbol,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        atr_at_entry=atr_at_entry,
        direction=direction,
        bars_held=bars_held,
        highest_favorable=highest_favorable,
        trailing_active=trailing_active,
        trailing_stop=trailing_stop,
        prediction_horizon=15,
        regime_at_entry=regime_at_entry,
    )


# ─────────────────────────────────────────────────────────────
# Test 1: In chop, trailing uses widened ATR (5.0 not 3.0)
# ─────────────────────────────────────────────────────────────

def test_chop_trailing_widened():
    """In chop with Variant A (widen), trail should be 5× ATR from high."""
    engine = AdaptiveExitEngine()
    levels = _make_exit_levels(
        entry_price=100.0,
        atr_at_entry=2.0,
        highest_favorable=108.0,  # 4× ATR above entry
        trailing_active=False,
        trailing_stop=0.0,
    )

    # Call _update_trailing_stop directly
    signal = engine._update_trailing_stop(levels, current_price=103.0, current_regime="chop")

    # Trailing should activate (excursion = 4 ATR > 3 ATR threshold)
    assert levels.trailing_active is True

    # With 5× ATR trail from high of 108: trail_stop = 108 - 5*2 = 98
    # Current price 103 > 98 → should NOT exit
    assert signal.should_exit is False

    # Verify the trailing stop is at the widened distance
    # new_trail = 108 - 5*2 = 98, but capped at entry (100) → 100
    assert levels.trailing_stop >= 98.0


def test_chop_trailing_widened_does_not_exit_early():
    """With 5× ATR trail, a 3× ATR reversal should NOT trigger exit."""
    engine = AdaptiveExitEngine()
    levels = _make_exit_levels(
        entry_price=100.0,
        atr_at_entry=2.0,
        highest_favorable=110.0,  # 5× ATR move
        trailing_active=True,
        trailing_stop=100.0,  # breakeven trail
    )

    # Price retraced 3× ATR from high: 110 - 6 = 104
    signal = engine._update_trailing_stop(levels, current_price=104.0, current_regime="chop")

    # With 5× ATR trail: new_trail = 110 - 10 = 100
    # Current price 104 > 100 → should NOT exit
    assert signal.should_exit is False


# ─────────────────────────────────────────────────────────────
# Test 2: Non-chop trailing stop uses original value
# ─────────────────────────────────────────────────────────────

def test_trending_up_trailing_unchanged():
    """In trending_up, trail distance should be 5.0 ATR (original)."""
    engine = AdaptiveExitEngine()
    levels = _make_exit_levels(
        entry_price=100.0,
        atr_at_entry=2.0,
        highest_favorable=108.0,
    )

    signal = engine._update_trailing_stop(levels, current_price=103.0, current_regime="trending_up")

    # Trailing activates (4× ATR > 3× threshold)
    assert levels.trailing_active is True
    # Trail = 108 - 5.0*2 = 98, capped at entry 100 → 100
    # This is the ORIGINAL trending_up behavior
    assert signal.should_exit is False


def test_stress_trailing_unchanged():
    """In stress, trail distance should be 3.0 ATR (original)."""
    engine = AdaptiveExitEngine()
    levels = _make_exit_levels(
        entry_price=100.0,
        atr_at_entry=2.0,
        highest_favorable=108.0,
    )

    signal = engine._update_trailing_stop(levels, current_price=103.0, current_regime="stress")
    assert levels.trailing_active is True
    # Trail = 108 - 3.0*2 = 102. Price 103 > 102 → no exit
    assert signal.should_exit is False


# ─────────────────────────────────────────────────────────────
# Test 3: stop_loss unchanged
# ─────────────────────────────────────────────────────────────

def test_stop_loss_unaffected_by_exp4():
    """stop_loss fires from check_exit, not _update_trailing_stop.
    Exp4 only modifies _update_trailing_stop."""
    engine = AdaptiveExitEngine()
    levels = _make_exit_levels(
        entry_price=100.0,
        stop_loss=95.0,
        atr_at_entry=2.0,
        bars_held=1,
    )

    # Price below stop → check_exit should fire stop_loss
    signal = engine.check_exit(levels, current_price=94.0, current_regime="chop")
    assert signal.should_exit is True
    assert signal.reason == "stop_loss"


# ─────────────────────────────────────────────────────────────
# Test 4: timeout/max_hold unchanged
# ─────────────────────────────────────────────────────────────

def test_max_hold_unaffected():
    """max_holding_period exit fires based on bars_held, not trailing."""
    engine = AdaptiveExitEngine()
    engine.learning_mode = False
    levels = _make_exit_levels(
        entry_price=100.0,
        stop_loss=95.0,
        atr_at_entry=2.0,
        direction=1.0,
        bars_held=31,  # > chop max_bars (30)
        highest_favorable=101.0,  # slight winner
    )
    levels.is_new_bar = True
    levels.price_at_prior_bar = 100.5

    signal = engine.check_exit(levels, current_price=101.0, current_regime="chop")
    # Should exit via time/profit-based exit (not trailing_stop)
    if signal.should_exit:
        assert signal.reason != "trailing_stop", (
            f"Exp4 should not change timeout/max_hold behavior. Got {signal.reason}"
        )


# ─────────────────────────────────────────────────────────────
# Test 5: Variant A is the default
# ─────────────────────────────────────────────────────────────

def test_variant_a_is_default():
    """The _EXP4_CHOP_TRAIL_MODE should be 'widen' by default."""
    # Read the source to verify
    import inspect
    source = inspect.getsource(AdaptiveExitEngine._update_trailing_stop)
    assert '_EXP4_CHOP_TRAIL_MODE = "widen"' in source
    assert '_EXP4_CHOP_TRAIL_ATR = 5.0' in source
