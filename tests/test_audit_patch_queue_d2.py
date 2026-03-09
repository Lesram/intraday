"""
Tests for Patch Queue D2 -- three targeted fixes.

Fix 1: _evolve_breakout_weights uses entry_source (not confidence proxy)
Fix 2: _evolve_signal_weights does not adapt alpha_weight_ml from confidence
Fix 3: _validate_new_model adds precision >= 0.45 quality constraint
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from backend.organism.continuous_learner import (
    ContinuousLearner,
    LearningState,
    TradeRecord,
)
from backend.organism.ml_signal import MLSignalGenerator, ModelMetrics
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


def _make_learner() -> ContinuousLearner:
    """ContinuousLearner with a minimal stub signal generator."""
    sig = SimpleNamespace(
        _clf=None, _reg=None, _is_trained=False,
        train=lambda fbs: None,
    )
    return ContinuousLearner(signal_generator=sig)  # type: ignore[arg-type]


def _make_metrics(**overrides) -> ModelMetrics:
    defaults = dict(
        generation=1,
        accuracy=0.60,
        precision=0.55,
        recall=0.50,
        f1=0.52,
        direction_accuracy=0.60,
        mean_pred_return=0.002,
        hit_rate=0.55,
    )
    defaults.update(overrides)
    return ModelMetrics(**defaults)


# =============================================================================
# Fix 1 -- _evolve_breakout_weights uses entry_source semantics
# =============================================================================

class TestBreakoutWeightsEntrySource:
    """Verify _evolve_breakout_weights identifies breakout trades
    by entry_source rather than confidence thresholds."""

    def test_breakout_weight_low_conf_entry_source_included(self):
        """A trade with low confidence but entry_source='breakout' should
        be counted as a breakout trade for weight evolution."""
        engine = _make_engine()
        params = EvolvedParams()
        orig_vol = params.breakout_weight_volume
        orig_squeeze = params.breakout_weight_squeeze

        # 5 breakout-sourced winning trades with LOW confidence
        trades = [
            _make_trade(
                confidence=0.3,
                entry_source="breakout",
                pnl=50.0,
            )
            for _ in range(5)
        ]
        # 3 non-breakout trades that lose
        trades += [
            _make_trade(
                confidence=0.8,
                entry_source="alpha",
                pnl=-30.0,
            )
            for _ in range(3)
        ]

        changes: dict[str, str] = {}
        engine._evolve_breakout_weights(params, trades, changes)

        # Breakout trades are profitable => weights should be boosted
        assert "breakout_weights" in changes, (
            "Expected breakout weight adaptation when breakout trades "
            "are identified by entry_source"
        )

    def test_breakout_weight_alpha_high_conf_excluded(self):
        """A trade with high confidence but entry_source='alpha' must NOT
        be counted as a breakout trade."""
        engine = _make_engine()
        params = EvolvedParams()

        # 5 alpha trades with very high confidence -- should NOT be
        # classified as breakout under entry_source semantics
        trades = [
            _make_trade(
                confidence=0.9,
                entry_source="alpha",
                pnl=50.0,
            )
            for _ in range(5)
        ]
        # 3 low-confidence non-breakout trades
        trades += [
            _make_trade(
                confidence=0.2,
                entry_source="alpha",
                pnl=-20.0,
            )
            for _ in range(3)
        ]

        changes: dict[str, str] = {}
        engine._evolve_breakout_weights(params, trades, changes)

        # No breakout trades found -> no adaptation
        assert "breakout_weights" not in changes, (
            "alpha trades with high confidence should not trigger "
            "breakout weight adaptation"
        )

    def test_breakout_weight_old_trade_fallback(self):
        """Old trades without entry_source should fall back to the
        confidence > 0.6 heuristic."""
        engine = _make_engine()
        params = EvolvedParams()

        # Old trades: entry_source="" (empty), confidence > 0.6 -> breakout
        trades = [
            _make_trade(
                confidence=0.75,
                entry_source="",
                pnl=40.0,
            )
            for _ in range(5)
        ]
        # Non-breakout old trades
        trades += [
            _make_trade(
                confidence=0.3,
                entry_source="",
                pnl=-30.0,
            )
            for _ in range(3)
        ]

        changes: dict[str, str] = {}
        engine._evolve_breakout_weights(params, trades, changes)

        # Fallback heuristic should classify confidence>0.6 as breakout
        assert "breakout_weights" in changes, (
            "Old trades without entry_source should fall back to "
            "confidence heuristic for breakout classification"
        )


# =============================================================================
# Fix 2 -- _evolve_signal_weights does not adapt ML weight from confidence
# =============================================================================

class TestSignalWeightsNoMLFromConfidence:
    """Verify _evolve_signal_weights does not change alpha_weight_ml
    based on confidence buckets."""

    def test_signal_weights_ml_not_adapted_from_confidence(self):
        """alpha_weight_ml must not be directly adapted based on
        confidence buckets.  Normalization may redistribute weights
        proportionally, but there must be no explicit ML adaptation
        (i.e., no 'alpha_weight_ml' key in the changes dict)."""
        engine = _make_engine()
        params = EvolvedParams()
        original_ml = params.alpha_weight_ml

        # Many high-confidence winning trades that would have
        # previously triggered ML weight boost
        trades = [
            _make_trade(
                confidence=0.9,
                pnl=100.0,
                actual_return=0.05,
                direction=1.0,
                entry_source="alpha",
            )
            for _ in range(20)
        ]
        # Some low-confidence losing trades
        trades += [
            _make_trade(
                confidence=0.2,
                pnl=-50.0,
                actual_return=-0.03,
                direction=1.0,
                entry_source="breakout",
            )
            for _ in range(10)
        ]

        changes: dict[str, str] = {}
        engine._evolve_signal_weights(params, trades, changes)

        # The key check: ML weight is never *directly* adapted
        assert "alpha_weight_ml" not in changes, (
            "alpha_weight_ml should not appear in changes -- "
            "confidence is not a reliable proxy for ML participation"
        )

    def test_signal_weights_momentum_still_adapts(self):
        """Momentum/regime weight adaptation should still work
        based on directional accuracy."""
        engine = _make_engine()
        params = EvolvedParams()
        original_momentum = params.alpha_weight_momentum

        # All trades have correct direction => high dir_accuracy => boost
        trades = [
            _make_trade(
                direction=1.0,
                actual_return=0.05,
                pnl=50.0,
                confidence=0.5,
            )
            for _ in range(20)
        ]

        changes: dict[str, str] = {}
        engine._evolve_signal_weights(params, trades, changes)

        assert "alpha_weight_momentum" in changes, (
            "Momentum weight should still be adapted based on "
            "directional accuracy"
        )
        assert params.alpha_weight_momentum != original_momentum


# =============================================================================
# Fix 3 -- _validate_new_model precision quality gate
# =============================================================================

class TestModelAcceptancePrecisionGate:
    """Verify that _validate_new_model requires precision >= 0.45
    in addition to mean_pred_return > 0."""

    def test_acceptance_positive_edge_weak_precision_rejected(self):
        """A model with positive mean_pred_return but precision < 0.45
        should be rejected."""
        learner = _make_learner()

        metrics = _make_metrics(
            mean_pred_return=0.003,   # positive edge
            precision=0.30,           # below 0.45 threshold
            accuracy=0.55,
            hit_rate=0.55,
            direction_accuracy=0.60,
        )

        # No old model => first-model path
        accepted = learner._validate_new_model({}, metrics, None)
        assert not accepted, (
            "Model with precision < 0.45 should be rejected "
            "even with positive mean_pred_return"
        )

    def test_acceptance_positive_edge_good_precision_accepted(self):
        """A model with positive mean_pred_return AND precision >= 0.45
        should be accepted (given reasonable score)."""
        learner = _make_learner()

        metrics = _make_metrics(
            mean_pred_return=0.003,
            precision=0.50,           # above 0.45
            accuracy=0.55,
            hit_rate=0.55,
            direction_accuracy=0.65,
        )

        # No old model => first-model path
        accepted = learner._validate_new_model({}, metrics, None)
        assert accepted, (
            "Model with precision >= 0.45 and positive edge "
            "should be accepted"
        )

    def test_acceptance_old_model_comparison_still_works(self):
        """When an old model exists, both quality_ok and the score
        comparison logic should still function together."""
        learner = _make_learner()

        # Set up an old model metric in state
        old_metrics = _make_metrics(
            generation=0,
            accuracy=0.50,
            hit_rate=0.45,
            direction_accuracy=0.55,
            mean_pred_return=0.001,
            precision=0.50,
        )
        learner.state.model_metrics.append(old_metrics)

        # New model: better score, positive edge, good precision
        new_metrics_good = _make_metrics(
            generation=1,
            accuracy=0.60,
            hit_rate=0.60,
            direction_accuracy=0.70,
            mean_pred_return=0.005,
            precision=0.55,
        )
        old_clf = SimpleNamespace()  # truthy old classifier
        accepted = learner._validate_new_model({}, new_metrics_good, old_clf)
        assert accepted, "Better model with quality_ok should be accepted"

        # New model: better score but low precision => rejected
        new_metrics_bad = _make_metrics(
            generation=2,
            accuracy=0.60,
            hit_rate=0.60,
            direction_accuracy=0.70,
            mean_pred_return=0.005,
            precision=0.40,  # below 0.45
        )
        rejected = learner._validate_new_model({}, new_metrics_bad, old_clf)
        assert not rejected, (
            "Model with low precision should be rejected even if "
            "score is better than old model"
        )
