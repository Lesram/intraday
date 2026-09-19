"""Tests for Patch Queue C1 — directional returns, calibration, regime restore."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest
import numpy as np


# -- Fix 1: Directional-return consistency --


class TestDirectionalReturnConsistency:
    """Profitable shorts must contribute positive signed return everywhere."""

    def _make_short_trade(self, pnl=100.0, actual_return=-0.05, idx=0):
        """A profitable short: direction=-1, price fell, pnl positive."""
        from backend.organism.continuous_learner import TradeRecord
        # Add small variance so std != 0 and sharpe can be computed
        noise = (idx % 5) * 0.002
        return TradeRecord(
            symbol="TEST", direction=-1.0,
            entry_price=100.0, exit_price=95.0,
            entry_bar=0, exit_bar=10, shares=20,
            pnl=pnl + idx, exit_reason="take_profit",
            predicted_return=-0.05, actual_return=actual_return - noise,
            confidence=0.7,
        )

    def _make_long_trade(self, pnl=100.0, actual_return=0.05, idx=0):
        """A profitable long."""
        from backend.organism.continuous_learner import TradeRecord
        noise = (idx % 5) * 0.002
        return TradeRecord(
            symbol="TEST", direction=1.0,
            entry_price=100.0, exit_price=105.0,
            entry_bar=0, exit_bar=10, shares=20,
            pnl=pnl + idx, exit_reason="take_profit",
            predicted_return=0.05, actual_return=actual_return + noise,
            confidence=0.7,
        )

    def test_profitable_short_improves_sharpe_in_attribution(self):
        """Profitable short trade must contribute positive to sharpe_proxy."""
        from backend.organism.ml_signal import MLSignalGenerator
        from backend.organism.continuous_learner import ContinuousLearner

        sig_gen = MLSignalGenerator()
        learner = ContinuousLearner(sig_gen)

        # Add only profitable short trades (with slight variance for sharpe calc)
        for i in range(15):
            learner.record_trade(self._make_short_trade(idx=i))

        attr = learner.compute_attribution()
        assert attr["sharpe_proxy"] > 0, \
            f"Profitable shorts should yield positive sharpe, got {attr['sharpe_proxy']}"

    def test_profitable_long_positive_sharpe(self):
        """Sanity: profitable longs also positive."""
        from backend.organism.ml_signal import MLSignalGenerator
        from backend.organism.continuous_learner import ContinuousLearner

        sig_gen = MLSignalGenerator()
        learner = ContinuousLearner(sig_gen)
        for i in range(15):
            learner.record_trade(self._make_long_trade(idx=i))
        attr = learner.compute_attribution()
        assert attr["sharpe_proxy"] > 0

    def test_walk_forward_gate_profitable_shorts_positive(self):
        """Profitable shorts must not hurt walk_forward_gate Sharpe."""
        from backend.organism.brain_persistence import OrganismBrain
        brain = OrganismBrain.__new__(OrganismBrain)
        brain._manifest = {"best_sharpe": 0}  # no baseline

        trades = [self._make_short_trade(idx=i) for i in range(15)]
        passed, reason = brain.walk_forward_gate(trades)
        assert passed is True
        # Current sharpe should be positive in the reason string
        assert "current=" in reason
        # Extract the sharpe value
        import re
        match = re.search(r"current=([-\d.]+)", reason)
        if match:
            current_sharpe = float(match.group(1))
            assert current_sharpe > 0, \
                f"Walk-forward gate should see positive sharpe for profitable shorts, got {current_sharpe}"

    def test_evolve_xgb_profitable_short_counts_as_correct(self):
        """Profitable short must be counted as correct in _evolve_xgb_hyperparams."""
        from backend.organism.self_evolution import EvolutionEngine, EvolvedParams

        evo = EvolutionEngine(min_trades=5)
        params = EvolvedParams()

        trades = [self._make_short_trade(idx=i) for i in range(20)]
        changes = {}
        evo._evolve_xgb_hyperparams(params, trades, changes)

        # With 100% correct trades, accuracy should be >= 0.60
        # which triggers the "increase capacity" branch
        # We can verify by checking that xgb params were adjusted
        assert "xgb_hyperparams" in changes or params.xgb_n_estimators >= 200

    def test_correct_direction_property_works_for_shorts(self):
        """TradeRecord.correct_direction must be True for profitable shorts."""
        trade = self._make_short_trade(pnl=100.0, actual_return=-0.05)
        # direction=-1, actual_return=-0.05: direction<0 and actual_return<0 -> True
        assert trade.correct_direction is True

    def test_correct_direction_property_works_for_losing_shorts(self):
        """TradeRecord.correct_direction must be False for losing shorts."""
        from backend.organism.continuous_learner import TradeRecord
        trade = TradeRecord(
            symbol="TEST", direction=-1.0,
            entry_price=100.0, exit_price=105.0,
            entry_bar=0, exit_bar=10, shares=20,
            pnl=-100.0, exit_reason="stop_loss",
            predicted_return=-0.05, actual_return=0.05,
            confidence=0.7,
        )
        assert trade.correct_direction is False


# -- Fix 2: ML calibration persistence --


class TestMLCalibrationPersistence:
    """Verify ML calibration state survives brain save/load."""

    def test_save_load_roundtrip_preserves_calibration(self, tmp_path):
        """Calibration counts and map must survive save/load."""
        from backend.organism.brain_persistence import OrganismBrain
        from backend.organism.ml_signal import MLSignalGenerator
        import json

        brain_dir = tmp_path / "brain"
        brain = OrganismBrain(brain_dir=brain_dir)

        sig_gen = MLSignalGenerator()
        # Record some calibration data
        sig_gen.record_prediction_outcome(0.8, True)
        sig_gen.record_prediction_outcome(0.8, True)
        sig_gen.record_prediction_outcome(0.8, False)
        sig_gen.record_prediction_outcome(0.3, True)
        sig_gen.record_prediction_outcome(0.3, False)

        original_counts = [list(c) for c in sig_gen._calibration_counts]

        # Create minimal learner stub
        class _Stub:
            class state:
                generation = 1
                total_bars_seen = 50
                total_trades = 5
                cumulative_pnl = 0.0
                best_sharpe = 0.0
                best_generation = 0
                retrain_count = 0
                drift_events = 0
                generation_accuracies = []
                model_metrics = []
            _bars_since_retrain = 0
            _reference_features = None

        brain.save(
            signal_gen=sig_gen,
            learner=_Stub(),
            equity_curve=[100000.0],
            all_trades=[],
            epoch_metrics=[],
            peak_equity=100000.0,
            evolved_params={},
        )

        # Verify calibration was persisted in ml_state.json
        ml_state = json.loads((brain_dir / "ml_state.json").read_text())
        assert "calibration" in ml_state, "calibration key must be in saved ml_state"
        assert ml_state["calibration"]["counts"] == original_counts

        # Load into new brain and verify calibration is in ml_state
        brain2 = OrganismBrain(brain_dir=brain_dir)
        brain2.load()
        assert brain2.ml_state.get("calibration") is not None

        # Since no trained models exist, apply_to_signal_generator returns
        # False early (no clf/reg). Verify that when models ARE present,
        # calibration restore path works by calling load_calibration directly.
        sig_gen2 = MLSignalGenerator()
        sig_gen2.load_calibration(brain2.ml_state["calibration"])
        assert sig_gen2._calibration_counts == original_counts, \
            f"Calibration counts not preserved: {sig_gen2._calibration_counts} != {original_counts}"

    def test_old_brain_without_calibration_loads_cleanly(self, tmp_path):
        """Brain saved without calibration field must still load."""
        from backend.organism.brain_persistence import OrganismBrain
        from backend.organism.ml_signal import MLSignalGenerator
        import json

        brain_dir = tmp_path / "brain"
        brain_dir.mkdir(parents=True)

        # Write minimal ml_state without calibration field
        ml_state = {
            "generation": 1,
            "feature_cols": [],
            "xgb_params": {},
            "is_trained": False,
            "train_window": 200,
        }
        (brain_dir / "ml_state.json").write_text(json.dumps(ml_state))
        (brain_dir / "manifest.json").write_text(json.dumps({
            "version": 2, "generation": 1,
        }))

        brain = OrganismBrain(brain_dir=brain_dir)
        brain.load()

        sig_gen = MLSignalGenerator()
        # Should not raise
        brain.apply_to_signal_generator(sig_gen)
        # Calibration should be at defaults
        assert len(sig_gen._calibration_counts) == 5


# -- Fix 3: Regime detector persistence roundtrip --


class TestRegimeDetectorPersistence:
    """Verify all saved regime fields are restored."""

    def test_roundtrip_preserves_all_fields(self):
        from backend.organism.regime import RegimeDetector

        det = RegimeDetector(
            sma_period=100,
            vol_lookback=40,
            trend_threshold=0.05,
            churn_window=30,
            smoothing_alpha=0.5,
        )
        det._history = ["trending_up", "chop", "high_vol"]
        det._smoothed_probs = {"trending_up": 0.4, "chop": 0.3, "high_vol": 0.3}

        saved = det.to_persistence_dict()

        det2 = RegimeDetector()  # defaults
        det2.from_persistence_dict(saved)

        assert det2._sma_period == 100
        assert det2._vol_lookback == 40
        assert det2._trend_threshold == 0.05
        assert det2._churn_window == 30
        assert det2._alpha == 0.5
        assert det2._history == ["trending_up", "chop", "high_vol"]
        assert det2._smoothed_probs == {"trending_up": 0.4, "chop": 0.3, "high_vol": 0.3}

    def test_partial_restore_backward_compat(self):
        """Old persistence data without new fields still works."""
        from backend.organism.regime import RegimeDetector

        det = RegimeDetector(vol_lookback=99)
        old_data = {
            "history": ["unknown"],
            "smoothed_probs": {},
            "sma_period": 200,
            "smoothing_alpha": 0.2,
            # No vol_lookback, trend_threshold, churn_window
        }
        det.from_persistence_dict(old_data)

        assert det._sma_period == 200
        assert det._alpha == 0.2
        assert det._history == ["unknown"]
        # vol_lookback should remain at constructor value (not overwritten)
        assert det._vol_lookback == 99


# -- Fix 4: Telemetry docstring contract --


class TestTelemetryContract:
    """Verify telemetry docstring no longer claims 'no DB storage'."""

    def test_docstring_does_not_claim_no_db(self):
        from backend.organism import decision_telemetry
        doc = decision_telemetry.__doc__
        assert "no DB storage" not in doc, \
            "Docstring should not claim 'no DB storage' -- DB persistence exists via TickTelemetry"
        assert "TickTelemetry" in doc, \
            "Docstring should mention the TickTelemetry DB persistence path"
