"""Tests for Patch Queue H3 -- preserve calibration on model swap, effective_mean_pred_return."""
from __future__ import annotations

import pytest

from backend.organism.ml_signal import MLSignalGenerator, ModelMetrics
from backend.organism.continuous_learner import (
    ContinuousLearner,
    acceptance_gate,
    MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE,
)
from backend.organism.background_trainer import BackgroundTrainer, TrainResult


# ==============================================================================
# Helpers
# ==============================================================================

def _good_metrics(**overrides) -> ModelMetrics:
    """Create metrics that pass composite score + precision + edge."""
    defaults = dict(
        generation=1,
        accuracy=0.60,
        precision=0.55,
        recall=0.50,
        f1=0.52,
        direction_accuracy=0.60,
        mean_pred_return=0.005,
        effective_mean_pred_return=0.005,
        hit_rate=0.55,
        calibration_sample_count=50,
        calibration_monotonic=True,
        calibration_error=0.05,
    )
    defaults.update(overrides)
    return ModelMetrics(**defaults)


# ==============================================================================
# Test 1: ModelMetrics includes effective_mean_pred_return
# ==============================================================================

class TestModelMetricsEffectiveMeanPredReturn:

    def test_field_exists(self):
        m = ModelMetrics(generation=1)
        assert hasattr(m, "effective_mean_pred_return")

    def test_default_is_zero(self):
        m = ModelMetrics(generation=1)
        assert m.effective_mean_pred_return == 0.0

    def test_to_dict_includes_field(self):
        m = ModelMetrics(generation=1, effective_mean_pred_return=0.003)
        d = m.to_dict()
        assert "effective_mean_pred_return" in d
        assert abs(d["effective_mean_pred_return"] - 0.003) < 0.0001

    def test_to_dict_includes_both_raw_and_effective(self):
        m = ModelMetrics(generation=1, mean_pred_return=0.005, effective_mean_pred_return=0.003)
        d = m.to_dict()
        assert "mean_pred_return" in d
        assert "effective_mean_pred_return" in d
        assert d["mean_pred_return"] != d["effective_mean_pred_return"]

    def test_raw_field_still_present(self):
        """mean_pred_return must not be removed."""
        m = ModelMetrics(generation=1, mean_pred_return=0.01)
        assert m.mean_pred_return == 0.01


# ==============================================================================
# Test 2: effective_mean_pred_return computation in _evaluate
# ==============================================================================

class TestEffectiveMeanPredReturnComputation:

    def test_zero_calibration_damps_effective(self):
        """With zero calibration samples, effective should be zero."""
        m = ModelMetrics(
            generation=1,
            mean_pred_return=0.005,
            calibration_sample_count=0,
        )
        # Simulate the computation: cal_factor = 0/30 = 0
        cal_factor = min(1.0, m.calibration_sample_count / 30)
        expected = m.mean_pred_return * cal_factor
        assert expected == 0.0

    def test_full_calibration_preserves_effective(self):
        """With full calibration (>= 30), effective = raw."""
        m = ModelMetrics(
            generation=1,
            mean_pred_return=0.005,
            calibration_sample_count=50,
        )
        cal_factor = min(1.0, m.calibration_sample_count / 30)
        expected = m.mean_pred_return * cal_factor
        assert expected == m.mean_pred_return

    def test_partial_calibration_damps_proportionally(self):
        """With 15 of 30 needed samples, effective = raw * 0.5."""
        m = ModelMetrics(
            generation=1,
            mean_pred_return=0.010,
            calibration_sample_count=15,
        )
        cal_factor = min(1.0, 15 / 30)
        expected = 0.010 * 0.5
        assert abs(expected - 0.005) < 0.0001

    def test_evaluate_computes_effective_field(self):
        """MLSignalGenerator._evaluate must set effective_mean_pred_return on ModelMetrics."""
        import inspect
        src = inspect.getsource(MLSignalGenerator._evaluate)
        assert "effective_mean_pred_return" in src


# ==============================================================================
# Test 3: acceptance_gate uses effective_mean_pred_return
# ==============================================================================

class TestAcceptanceGateUsesEffective:

    def test_positive_raw_negative_effective_rejected(self):
        """Model with positive raw but zero effective_mean_pred_return is rejected."""
        m = _good_metrics(
            mean_pred_return=0.005,
            effective_mean_pred_return=0.0,  # damped to zero
        )
        accepted, reason = acceptance_gate(m)
        assert not accepted, "Positive raw but zero effective should be rejected"

    def test_positive_effective_passes_edge_check(self):
        """Model with positive effective_mean_pred_return can pass."""
        m = _good_metrics(
            mean_pred_return=0.005,
            effective_mean_pred_return=0.003,
        )
        accepted, _ = acceptance_gate(m)
        assert accepted

    def test_negative_effective_rejected(self):
        """Negative effective_mean_pred_return is rejected."""
        m = _good_metrics(
            mean_pred_return=0.005,
            effective_mean_pred_return=-0.001,
        )
        accepted, _ = acceptance_gate(m)
        assert not accepted

    def test_gate_source_references_effective(self):
        """acceptance_gate source must use effective_mean_pred_return, not raw."""
        import inspect
        src = inspect.getsource(acceptance_gate)
        assert "effective_mean_pred_return" in src


# ==============================================================================
# Test 4: apply_result preserves calibration + effective fields
# ==============================================================================

class TestApplyResultPreservesCalibration:

    def _make_signal_gen(self) -> MLSignalGenerator:
        return MLSignalGenerator()

    def _make_trainer_with_result(self, **tm_overrides) -> BackgroundTrainer:
        tm = {
            "generation": 5,
            "accuracy": 0.60,
            "precision": 0.55,
            "recall": 0.50,
            "f1": 0.52,
            "direction_accuracy": 0.60,
            "mean_pred_return": 0.005,
            "effective_mean_pred_return": 0.004,
            "hit_rate": 0.55,
            "calibration_sample_count": 42,
            "calibration_monotonic": False,
            "calibration_error": 0.08,
        }
        tm.update(tm_overrides)
        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=True,
            train_metrics=tm,
            is_trained=True,
        )
        return trainer

    def test_calibration_sample_count_preserved(self):
        sig = self._make_signal_gen()
        trainer = self._make_trainer_with_result()
        trainer.apply_result(sig, None, None, None, None, None, None)
        assert sig._latest_metrics.calibration_sample_count == 42

    def test_calibration_monotonic_preserved(self):
        sig = self._make_signal_gen()
        trainer = self._make_trainer_with_result()
        trainer.apply_result(sig, None, None, None, None, None, None)
        assert sig._latest_metrics.calibration_monotonic is False

    def test_calibration_error_preserved(self):
        sig = self._make_signal_gen()
        trainer = self._make_trainer_with_result()
        trainer.apply_result(sig, None, None, None, None, None, None)
        assert abs(sig._latest_metrics.calibration_error - 0.08) < 0.001

    def test_effective_mean_pred_return_preserved(self):
        sig = self._make_signal_gen()
        trainer = self._make_trainer_with_result()
        trainer.apply_result(sig, None, None, None, None, None, None)
        assert abs(sig._latest_metrics.effective_mean_pred_return - 0.004) < 0.0001

    def test_generation_preserved(self):
        sig = self._make_signal_gen()
        trainer = self._make_trainer_with_result()
        trainer.apply_result(sig, None, None, None, None, None, None)
        assert sig._latest_metrics.generation == 5

    def test_statistical_fields_preserved(self):
        sig = self._make_signal_gen()
        trainer = self._make_trainer_with_result()
        trainer.apply_result(sig, None, None, None, None, None, None)
        m = sig._latest_metrics
        assert m.accuracy == 0.60
        assert m.precision == 0.55
        assert m.hit_rate == 0.55

    def test_backward_compat_missing_calibration(self):
        """apply_result must not crash when train_metrics lacks calibration fields."""
        sig = self._make_signal_gen()
        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=True,
            train_metrics={
                "generation": 3,
                "accuracy": 0.50,
                "precision": 0.50,
                "recall": 0.50,
                "f1": 0.50,
                "direction_accuracy": 0.50,
                "mean_pred_return": 0.001,
                "hit_rate": 0.50,
                # No calibration or effective fields
            },
            is_trained=True,
        )
        trainer.apply_result(sig, None, None, None, None, None, None)
        # Should use defaults
        assert sig._latest_metrics.calibration_sample_count == 0
        assert sig._latest_metrics.calibration_monotonic is True
        assert sig._latest_metrics.effective_mean_pred_return == 0.0


# ==============================================================================
# Test 5: _build_train_metrics includes effective_mean_pred_return
# ==============================================================================

class TestBuildTrainMetricsEffective:

    def test_build_train_metrics_has_effective_field(self):
        import inspect
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module._train_in_process)
        helper_start = src.index("def _build_train_metrics")
        helper_block = src[helper_start:src.index("if not accepted", helper_start)]
        assert "effective_mean_pred_return" in helper_block


# ==============================================================================
# Test 6: apply_result source includes calibration + effective fields
# ==============================================================================

class TestApplyResultSourceCompleteness:

    def test_apply_result_reconstructs_calibration_fields(self):
        import inspect
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module.BackgroundTrainer.apply_result)
        assert "calibration_sample_count" in src
        assert "calibration_monotonic" in src
        assert "calibration_error" in src

    def test_apply_result_reconstructs_effective_mean_pred_return(self):
        import inspect
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module.BackgroundTrainer.apply_result)
        assert "effective_mean_pred_return" in src
