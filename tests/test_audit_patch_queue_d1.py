"""
Tests for Patch Queue D1 -- three targeted fixes.

Fix 1: _evolve_breakout_periods uses entry_source instead of confidence proxy
Fix 2: ModelMetrics history roundtrip restores all fields
Fix 3: _validate_new_model includes economic side-constraint (mean_pred_return)
"""

from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
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


# ─── Helpers ──────────────────────────────────────────────────────────

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
    )
    defaults.update(overrides)
    return TradeRecord(**defaults)


def _make_model_metrics(**overrides) -> ModelMetrics:
    defaults = dict(
        generation=1,
        accuracy=0.6,
        precision=0.65,
        recall=0.55,
        f1=0.60,
        direction_accuracy=0.62,
        mean_pred_return=0.002,
        hit_rate=0.55,
        feature_importance_top10=[("feat_a", 0.3), ("feat_b", 0.2)],
    )
    defaults.update(overrides)
    # V12 W88 (post-cleanup): the gate checks
    # ``effective_mean_pred_return > 0`` (the calibration-damped edge),
    # not ``mean_pred_return``.  Pre-W88 this fixture left
    # ``effective_mean_pred_return`` at its default 0.0, so the gate
    # always rejected with `eff_mean_pred_return=0.0000`.  Default it
    # to mean_pred_return unless explicitly overridden — that mirrors
    # the production behavior at maturity (system_calibration mature
    # → effective ≈ mean).
    defaults.setdefault("effective_mean_pred_return", defaults["mean_pred_return"])
    return ModelMetrics(**defaults)


# ═══════════════════════════════════════════════════════════════════════
#  Fix 1: _evolve_breakout_periods uses entry_source
# ═══════════════════════════════════════════════════════════════════════

class TestEvolveBreakoutPeriods:
    """Verify that _evolve_breakout_periods selects trades by entry_source."""

    def _make_engine(self) -> EvolutionEngine:
        return EvolutionEngine()

    def test_breakout_trade_low_confidence_included(self):
        """Trade with confidence=0.3 but entry_source='breakout' IS included."""
        engine = self._make_engine()
        params = EvolvedParams()
        changes: dict[str, str] = {}

        # 6 breakout trades with low confidence, all losing
        trades = [
            _make_trade(confidence=0.3, entry_source="breakout", pnl=-20.0,
                        entry_bar=0, exit_bar=20)
            for _ in range(6)
        ]

        engine._evolve_breakout_periods(params, trades, changes)

        # Should have been included (6 > 5 threshold) and since avg_pnl < 0
        # the periods should have changed
        assert "breakout_periods" in changes

    def test_alpha_trade_high_confidence_excluded(self):
        """Trade with confidence=0.9 but entry_source='alpha' is EXCLUDED."""
        engine = self._make_engine()
        params = EvolvedParams()
        changes: dict[str, str] = {}

        # 6 alpha trades with high confidence -- should NOT count as breakout
        trades = [
            _make_trade(confidence=0.9, entry_source="alpha", pnl=-20.0)
            for _ in range(6)
        ]

        engine._evolve_breakout_periods(params, trades, changes)

        # Only 0 breakout trades found, below threshold of 5 -> no change
        assert "breakout_periods" not in changes

    def test_mixed_entry_source_behavior(self):
        """Mixed trades: only breakout-sourced trades affect breakout evolution."""
        engine = self._make_engine()
        params = EvolvedParams()
        changes: dict[str, str] = {}

        trades = (
            # 3 alpha trades (high conf, should be excluded)
            [_make_trade(confidence=0.9, entry_source="alpha", pnl=-10.0)
             for _ in range(3)]
            # 6 breakout trades (low conf, should be included, losing)
            + [_make_trade(confidence=0.4, entry_source="breakout", pnl=-15.0,
                           entry_bar=0, exit_bar=8)
               for _ in range(6)]
        )

        engine._evolve_breakout_periods(params, trades, changes)

        # 6 breakout trades found (>5) and losing -> periods should change
        assert "breakout_periods" in changes

    def test_backward_compat_no_entry_source(self):
        """Trades without entry_source fall back to confidence > 0.6 heuristic."""
        engine = self._make_engine()
        params = EvolvedParams()
        changes: dict[str, str] = {}

        # Old-style trades: no entry_source, high confidence
        trades = [
            _make_trade(confidence=0.8, entry_source="", pnl=-30.0,
                        entry_bar=0, exit_bar=20)
            for _ in range(6)
        ]

        engine._evolve_breakout_periods(params, trades, changes)

        # Should be included via fallback heuristic
        assert "breakout_periods" in changes

    def test_backward_compat_low_conf_no_source_excluded(self):
        """Old trades with low confidence and no entry_source are excluded."""
        engine = self._make_engine()
        params = EvolvedParams()
        changes: dict[str, str] = {}

        trades = [
            _make_trade(confidence=0.4, entry_source="", pnl=-30.0)
            for _ in range(6)
        ]

        engine._evolve_breakout_periods(params, trades, changes)
        assert "breakout_periods" not in changes


# ═══════════════════════════════════════════════════════════════════════
#  Fix 2: ModelMetrics history roundtrip fidelity
# ═══════════════════════════════════════════════════════════════════════

class TestModelMetricsRoundtrip:
    """Verify that save -> load preserves all ModelMetrics fields."""

    def test_model_metrics_roundtrip_all_fields(self):
        """All fields in ModelMetrics survive a save/restore cycle."""
        from backend.organism.brain_persistence import OrganismBrain

        with tempfile.TemporaryDirectory() as tmp:
            brain = OrganismBrain(brain_dir=tmp)

            # Build a fake learner with model_metrics
            mm = _make_model_metrics(
                generation=3,
                accuracy=0.72,
                precision=0.68,
                recall=0.59,
                f1=0.63,
                direction_accuracy=0.71,
                mean_pred_return=0.0045,
                hit_rate=0.61,
                feature_importance_top10=[("vol", 0.4), ("rsi", 0.25)],
            )

            learner = SimpleNamespace(
                state=LearningState(
                    generation=3,
                    model_metrics=[mm],
                ),
                trade_history=[],
                _bars_since_retrain=5,
            )

            # Save
            brain._save_model_metrics_history(Path(tmp), learner)
            # Save a minimal ml_state.json so the round-trip load works
            ml_state_path = Path(tmp) / "ml_state.json"
            ml_state = json.loads(ml_state_path.read_text())

            # Now simulate load via apply_to_learner
            brain2 = OrganismBrain(brain_dir=tmp)
            brain2.ml_state = ml_state
            brain2.learning_state = {
                "generation": 3,
            }

            target_learner = SimpleNamespace(
                state=LearningState(),
                trade_history=[],
                _bars_since_retrain=0,
            )
            brain2.trade_history = []
            brain2.apply_to_learner(target_learner)

            restored = target_learner.state.model_metrics
            assert len(restored) == 1
            r = restored[0]
            assert r.generation == 3
            assert abs(r.accuracy - 0.72) < 1e-6
            assert abs(r.precision - 0.68) < 1e-6
            assert abs(r.recall - 0.59) < 1e-6
            assert abs(r.f1 - 0.63) < 1e-6
            assert abs(r.direction_accuracy - 0.71) < 1e-6
            assert abs(r.mean_pred_return - 0.0045) < 1e-6
            assert abs(r.hit_rate - 0.61) < 1e-6

    def test_model_metrics_backward_compat(self):
        """Old saved data missing precision/recall/f1 loads with defaults."""
        from backend.organism.brain_persistence import OrganismBrain

        with tempfile.TemporaryDirectory() as tmp:
            brain = OrganismBrain(brain_dir=tmp)

            # Simulate old-format ml_state with missing fields
            brain.ml_state = {
                "model_metrics_history": [
                    {
                        "generation": 1,
                        "accuracy": 0.55,
                        "direction_accuracy": 0.60,
                        "hit_rate": 0.52,
                        "feature_importance_top10": [],
                        # precision, recall, f1, mean_pred_return intentionally absent
                    }
                ]
            }
            brain.learning_state = {"generation": 1}
            brain.trade_history = []

            target_learner = SimpleNamespace(
                state=LearningState(),
                trade_history=[],
                _bars_since_retrain=0,
            )
            brain.apply_to_learner(target_learner)

            r = target_learner.state.model_metrics[0]
            assert r.precision == 0.0
            assert r.recall == 0.0
            assert r.f1 == 0.0
            assert r.mean_pred_return == 0.0
            assert abs(r.accuracy - 0.55) < 1e-6


# ═══════════════════════════════════════════════════════════════════════
#  Fix 3: _validate_new_model economic side-constraint
# ═══════════════════════════════════════════════════════════════════════

class TestValidateNewModelEconomic:
    """Verify that _validate_new_model enforces mean_pred_return > 0."""

    def _make_learner(self) -> ContinuousLearner:
        sig_gen = MLSignalGenerator.__new__(MLSignalGenerator)
        sig_gen._clf = None
        sig_gen._reg = None
        sig_gen._is_trained = False
        sig_gen._latest_metrics = None
        sig_gen._feature_cols = []
        sig_gen.generation = 0

        learner = ContinuousLearner(signal_generator=sig_gen)
        return learner

    def test_acceptance_rejects_negative_edge(self):
        """Good accuracy but mean_pred_return < 0 -> rejected."""
        learner = self._make_learner()

        metrics = _make_model_metrics(
            accuracy=0.65,
            hit_rate=0.60,
            direction_accuracy=0.70,
            mean_pred_return=-0.001,  # negative edge
        )

        # No old model -> still rejected because of negative edge
        result, _reason = learner._validate_new_model({}, metrics, old_clf=None)
        assert result is False

    def test_acceptance_accepts_positive_edge(self):
        """Good accuracy and mean_pred_return > 0 -> accepted."""
        learner = self._make_learner()

        metrics = _make_model_metrics(
            accuracy=0.65,
            hit_rate=0.60,
            direction_accuracy=0.70,
            mean_pred_return=0.003,  # positive edge
        )

        result, _reason = learner._validate_new_model({}, metrics, old_clf=None)
        assert result is True

    def test_poor_model_rejected(self):
        """Very low scores -> rejected even with positive edge."""
        learner = self._make_learner()

        metrics = _make_model_metrics(
            accuracy=0.10,
            hit_rate=0.10,
            direction_accuracy=0.40,
            mean_pred_return=0.001,
        )

        # score = 0.10*0.4 + 0.10*0.3 + max(0.40-0.5,0)*0.6 = 0.04+0.03+0 = 0.07
        # 0.07 < 0.25 threshold
        result, _reason = learner._validate_new_model({}, metrics, old_clf=None)
        assert result is False

    def test_improved_model_accepted(self):
        """Model that beats old by threshold with positive edge -> accepted."""
        learner = self._make_learner()

        # Set up old metrics in state
        old_mm = _make_model_metrics(
            accuracy=0.50,
            hit_rate=0.50,
            direction_accuracy=0.55,
            mean_pred_return=0.001,
        )
        learner.state.model_metrics.append(old_mm)

        # New model is better
        new_mm = _make_model_metrics(
            accuracy=0.65,
            hit_rate=0.62,
            direction_accuracy=0.70,
            mean_pred_return=0.004,
        )

        # old_score = 0.50*0.4 + 0.50*0.3 + max(0.05,0)*0.6 = 0.20+0.15+0.03 = 0.38
        # new_score = 0.62*0.4 + 0.65*0.3 + max(0.20,0)*0.6 = 0.248+0.195+0.12 = 0.563
        # improvement = 0.563 - 0.38 = 0.183 > 0.05 threshold
        old_clf = object()  # non-None to trigger comparison path
        result, _reason = learner._validate_new_model({}, new_mm, old_clf=old_clf)
        assert result is True

    def test_improved_but_negative_edge_rejected(self):
        """Model improves on score but has negative mean_pred_return -> rejected."""
        learner = self._make_learner()

        old_mm = _make_model_metrics(
            accuracy=0.50,
            hit_rate=0.50,
            direction_accuracy=0.55,
            mean_pred_return=0.001,
        )
        learner.state.model_metrics.append(old_mm)

        new_mm = _make_model_metrics(
            accuracy=0.65,
            hit_rate=0.62,
            direction_accuracy=0.70,
            mean_pred_return=-0.001,  # negative edge
        )

        old_clf = object()
        result, _reason = learner._validate_new_model({}, new_mm, old_clf=old_clf)
        assert result is False
