"""
Tests for Patch Queue D3 -- two targeted fixes in self_evolution.py.

Fix 1: _normalize_alpha_weights holds alpha_weight_ml fixed
Fix 2: _evolve_breakout_weights requires brk_avg_pnl > 0 for boost
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from backend.organism.continuous_learner import TradeRecord
from backend.organism.self_evolution import EvolutionEngine, EvolvedParams


# ---- Helpers ----------------------------------------------------------------

def _make_trade(**overrides) -> TradeRecord:
    """Create a TradeRecord with sensible defaults, applying overrides."""
    defaults = dict(
        symbol="AAPL",
        direction=1.0,
        entry_price=100.0,
        exit_price=99.0,
        entry_bar=0,
        exit_bar=10,
        shares=10,
        pnl=-10.0,
        exit_reason="stop",
        predicted_return=0.01,
        actual_return=-0.01,
        confidence=0.5,
        is_exploration=False,
        entry_source="",
        regime_at_entry="trending_up",
        regime_at_exit="trending_up",
        mfe=1.0,
        mae=-0.5,
        bars_held_at_exit=10,
        time_in_trade_seconds=600.0,
    )
    defaults.update(overrides)
    return TradeRecord(**defaults)


def _make_engine() -> EvolutionEngine:
    return EvolutionEngine()


# =============================================================================
# Fix 1 -- _normalize_alpha_weights holds ML weight fixed
# =============================================================================

class TestMlWeightFixedDuringNormalization:
    """Verify that alpha_weight_ml is not moved by normalization after
    momentum/regime weight changes."""

    def test_ml_weight_unchanged_after_momentum_boost(self):
        """When momentum is boosted (high dir_accuracy), alpha_weight_ml
        must remain exactly at its original value."""
        engine = _make_engine()
        params = EvolvedParams()
        original_ml = params.alpha_weight_ml

        # Trades with high directional accuracy -> momentum boost
        trades = [
            _make_trade(
                direction=1.0,
                actual_return=0.02,   # correct direction
                pnl=20.0,
            )
            for _ in range(10)
        ]

        changes: dict[str, str] = {}
        engine._evolve_signal_weights(params, trades, changes)

        assert params.alpha_weight_ml == original_ml, (
            f"alpha_weight_ml drifted from {original_ml} to "
            f"{params.alpha_weight_ml} after momentum boost"
        )

    def test_ml_weight_unchanged_after_momentum_reduce(self):
        """When momentum is reduced (low dir_accuracy), alpha_weight_ml
        must remain exactly at its original value."""
        engine = _make_engine()
        params = EvolvedParams()
        original_ml = params.alpha_weight_ml

        # Trades with low directional accuracy -> momentum reduce
        trades = [
            _make_trade(
                direction=1.0,
                actual_return=-0.02,  # wrong direction
                pnl=-20.0,
            )
            for _ in range(10)
        ]

        changes: dict[str, str] = {}
        engine._evolve_signal_weights(params, trades, changes)

        assert params.alpha_weight_ml == original_ml, (
            f"alpha_weight_ml drifted from {original_ml} to "
            f"{params.alpha_weight_ml} after momentum reduce"
        )

    def test_alpha_weights_sum_to_one(self):
        """After signal weight evolution, all 5 alpha weights must sum
        to 1.0 (within floating point tolerance)."""
        engine = _make_engine()
        params = EvolvedParams()

        # High dir accuracy -> triggers momentum boost path
        trades = [
            _make_trade(
                direction=1.0,
                actual_return=0.02,
                pnl=20.0,
            )
            for _ in range(10)
        ]

        changes: dict[str, str] = {}
        engine._evolve_signal_weights(params, trades, changes)

        total = (
            params.alpha_weight_ml
            + params.alpha_weight_volume
            + params.alpha_weight_momentum
            + params.alpha_weight_breakout
            + params.alpha_weight_regime
        )
        assert math.isclose(total, 1.0, abs_tol=1e-9), (
            f"Alpha weights sum to {total}, expected 1.0"
        )

    def test_alpha_weights_sum_to_one_after_reduce(self):
        """After momentum reduce path, weights still sum to 1.0."""
        engine = _make_engine()
        params = EvolvedParams()

        # Low dir accuracy -> triggers momentum reduce + regime boost
        trades = [
            _make_trade(
                direction=1.0,
                actual_return=-0.02,
                pnl=-20.0,
            )
            for _ in range(10)
        ]

        changes: dict[str, str] = {}
        engine._evolve_signal_weights(params, trades, changes)

        total = (
            params.alpha_weight_ml
            + params.alpha_weight_volume
            + params.alpha_weight_momentum
            + params.alpha_weight_breakout
            + params.alpha_weight_regime
        )
        assert math.isclose(total, 1.0, abs_tol=1e-9), (
            f"Alpha weights sum to {total}, expected 1.0"
        )


# =============================================================================
# Fix 2 -- _evolve_breakout_weights requires brk_avg_pnl > 0 for boost
# =============================================================================

class TestBreakoutBoostRequiresPositivePnl:
    """Verify that breakout weight boost is blocked when breakout trades
    have negative average PnL, even if they lose less than non-breakout."""

    def test_no_boost_when_breakout_avg_pnl_negative(self):
        """breakout avg pnl = -10, non-breakout avg pnl = -50.
        brk_avg_pnl > non_brk_avg * 1.5 is true (-10 > -75) but since
        brk_avg_pnl < 0, no boost should occur."""
        engine = _make_engine()
        params = EvolvedParams()

        # 5 breakout trades: losing but less than non-breakout
        trades = [
            _make_trade(entry_source="breakout", pnl=-10.0)
            for _ in range(5)
        ]
        # 5 non-breakout trades: losing badly
        trades += [
            _make_trade(entry_source="alpha", pnl=-50.0)
            for _ in range(5)
        ]

        changes: dict[str, str] = {}
        engine._evolve_breakout_weights(params, trades, changes)

        # Should NOT get a boost -- breakout_weights key should either
        # be absent or say "reduce", never "boost"
        if "breakout_weights" in changes:
            assert "boost" not in changes["breakout_weights"], (
                "Breakout weights were boosted despite negative brk_avg_pnl"
            )

    def test_boost_when_breakout_avg_pnl_positive(self):
        """breakout avg pnl = +30, non-breakout avg pnl = +5,
        win_rate > 0.5 -- boost should occur."""
        engine = _make_engine()
        params = EvolvedParams()

        # 5 breakout trades: profitable, all winners
        trades = [
            _make_trade(entry_source="breakout", pnl=30.0)
            for _ in range(5)
        ]
        # 5 non-breakout trades: slightly profitable
        trades += [
            _make_trade(entry_source="alpha", pnl=5.0)
            for _ in range(5)
        ]

        changes: dict[str, str] = {}
        engine._evolve_breakout_weights(params, trades, changes)

        assert "breakout_weights" in changes, (
            "Expected breakout weight boost when brk_avg_pnl is positive "
            "and outperforms non-breakout"
        )
        assert "boost" in changes["breakout_weights"], (
            "Expected 'boost' in changes message"
        )

    def test_reduction_when_breakout_losing(self):
        """breakout avg pnl very negative -- should trigger reduction
        or at minimum no boost."""
        engine = _make_engine()
        params = EvolvedParams()

        # 5 breakout trades: heavily losing
        trades = [
            _make_trade(entry_source="breakout", pnl=-80.0)
            for _ in range(5)
        ]
        # 3 non-breakout trades: slightly positive
        trades += [
            _make_trade(entry_source="alpha", pnl=10.0)
            for _ in range(3)
        ]

        changes: dict[str, str] = {}
        engine._evolve_breakout_weights(params, trades, changes)

        # Must NOT boost
        if "breakout_weights" in changes:
            assert "boost" not in changes["breakout_weights"], (
                "Breakout weights boosted despite heavy losses"
            )
        # Should reduce since brk_avg_pnl < 0
        assert "breakout_weights" in changes, (
            "Expected breakout weight reduction when brk_avg_pnl is "
            "very negative"
        )
        assert "reduce" in changes["breakout_weights"], (
            "Expected 'reduce' in changes message for losing breakout trades"
        )
