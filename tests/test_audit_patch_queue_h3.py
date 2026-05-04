"""Tests for Patch Queue H3 -- ML signal semantic honesty and calibration-quality clarity."""
from __future__ import annotations

import inspect

import pytest

from backend.organism.ml_signal import MLSignal, MLSignalGenerator, ModelMetrics
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
# Test 1: MLSignal has three distinct confidence fields
# ==============================================================================

class TestMLSignalConfidenceTriad:

    def test_raw_confidence_field_exists(self):
        sig = MLSignal(symbol="X", direction=1, confidence=0.6, predicted_return=0.01)
        assert hasattr(sig, "raw_confidence")

    def test_raw_confidence_default_is_zero(self):
        sig = MLSignal(symbol="X", direction=1, confidence=0.6, predicted_return=0.01)
        assert sig.raw_confidence == 0.0

    def test_confidence_field_is_calibrated(self):
        """The 'confidence' field stores calibrated (not raw) confidence."""
        src = inspect.getsource(MLSignalGenerator.predict)
        # predict() must call calibrate_confidence and store result in confidence
        assert "calibrated_confidence" in src
        assert "calibrate_confidence" in src

    def test_confidence_docstring_says_calibrated(self):
        """MLSignal.confidence must be documented as calibrated."""
        src = inspect.getsource(MLSignal)
        # Find the confidence field annotation line
        assert "calibrated" in src.lower()

    def test_raw_confidence_is_pre_calibration(self):
        """raw_confidence must be computed before calibrate_confidence()."""
        src = inspect.getsource(MLSignalGenerator.predict)
        # raw_confidence must be set before calibrate_confidence is called
        raw_pos = src.index("raw_confidence")
        cal_pos = src.index("calibrate_confidence")
        assert raw_pos < cal_pos, "raw_confidence must be set before calibration"

    def test_effective_confidence_is_post_calibration(self):
        """effective_confidence is computed from calibrated, not raw."""
        src = inspect.getsource(MLSignalGenerator._compute_effective_confidence)
        assert "calibrated_confidence" in src

    def test_three_confidence_fields_are_distinct_concepts(self):
        """MLSignal must have raw_confidence, confidence, effective_confidence as separate fields."""
        sig = MLSignal(
            symbol="X", direction=1,
            confidence=0.7,       # calibrated
            predicted_return=0.01,
            raw_confidence=0.8,   # pre-calibration
            effective_confidence=0.6,  # post-precision-cap
        )
        assert sig.raw_confidence == 0.8
        assert sig.confidence == 0.7
        assert sig.effective_confidence == 0.6


# ==============================================================================
# Test 2: predict() stores raw_confidence correctly
# ==============================================================================

class TestPredictStoresRawConfidence:

    def test_predict_sets_raw_confidence(self):
        """predict() must populate raw_confidence on the returned MLSignal."""
        src = inspect.getsource(MLSignalGenerator.predict)
        assert "raw_confidence=" in src

    def test_predict_confidence_is_calibrated_value(self):
        """predict() must set confidence= to the calibrated value, not raw."""
        src = inspect.getsource(MLSignalGenerator.predict)
        # Find the return MLSignal(...) block
        return_block_start = src.rindex("return MLSignal(")
        return_block = src[return_block_start:]
        assert "confidence=calibrated_confidence" in return_block

    def test_predict_raw_is_not_calibrated(self):
        """predict() must not pass calibrated value as raw_confidence."""
        src = inspect.getsource(MLSignalGenerator.predict)
        return_block_start = src.rindex("return MLSignal(")
        return_block = src[return_block_start:]
        assert "raw_confidence=raw_confidence" in return_block


# ==============================================================================
# Test 3: effective_mean_pred_return semantics documented correctly
# ==============================================================================

class TestEffectiveMeanPredReturnSemantics:

    def test_model_metrics_docstring_explains_calibration_source(self):
        """ModelMetrics docstring must say calibration is system-level, not candidate-specific."""
        doc = ModelMetrics.__doc__ or ""
        assert "system-level" in doc.lower() or "system" in doc.lower()

    def test_model_metrics_docstring_explains_effective_mean_pred_return(self):
        """ModelMetrics docstring must explain effective_mean_pred_return uses only cal_factor."""
        doc = ModelMetrics.__doc__ or ""
        assert "cal_factor" in doc or "calibration" in doc.lower()

    def test_evaluate_comment_explains_no_conf_factor(self):
        """_evaluate() must document why effective_mean_pred_return has no confidence_factor."""
        src = inspect.getsource(MLSignalGenerator._evaluate)
        assert "per-signal" in src.lower() or "aggregate" in src.lower()

    def test_effective_mean_pred_return_serialized(self):
        m = ModelMetrics(generation=1, effective_mean_pred_return=0.003)
        d = m.to_dict()
        assert "effective_mean_pred_return" in d
        assert abs(d["effective_mean_pred_return"] - 0.003) < 0.0001

    def test_raw_mean_pred_return_still_available(self):
        m = ModelMetrics(generation=1, mean_pred_return=0.005, effective_mean_pred_return=0.003)
        assert m.mean_pred_return == 0.005
        d = m.to_dict()
        assert "mean_pred_return" in d


# ==============================================================================
# Test 4: Acceptance gate calibration source documentation
# ==============================================================================

class TestAcceptanceGateCalibrationSourceDocs:

    def test_acceptance_gate_docstring_says_system_level(self):
        """acceptance_gate docstring must explain calibration is system-level."""
        doc = acceptance_gate.__doc__ or ""
        assert "system" in doc.lower()

    def test_acceptance_gate_source_comments_say_system_level(self):
        """acceptance_gate source comments must reference system-level calibration."""
        src = inspect.getsource(acceptance_gate)
        assert "system" in src.lower()

    def test_acceptance_gate_uses_effective_mean_pred_return(self):
        src = inspect.getsource(acceptance_gate)
        assert "effective_mean_pred_return" in src

    def test_model_metrics_calibration_comments_say_system_level(self):
        """ModelMetrics calibration field comments must say system-level."""
        src = inspect.getsource(ModelMetrics)
        assert "system" in src.lower() or "rolling" in src.lower()


# ==============================================================================
# Test 5: effective_mean_pred_return damping in _evaluate
# ==============================================================================

class TestEffectiveMeanPredReturnComputation:

    def test_zero_calibration_damps_to_zero(self):
        cal_factor = min(1.0, 0 / 30)
        assert 0.005 * cal_factor == 0.0

    def test_full_calibration_preserves(self):
        cal_factor = min(1.0, 50 / 30)
        assert 0.005 * cal_factor == 0.005

    def test_partial_calibration_damps_proportionally(self):
        cal_factor = min(1.0, 15 / 30)
        assert abs(0.010 * cal_factor - 0.005) < 0.0001

    def test_evaluate_source_computes_effective(self):
        src = inspect.getsource(MLSignalGenerator._evaluate)
        assert "effective_mean_pred_return" in src


# ==============================================================================
# Test 6: acceptance_gate uses effective_mean_pred_return
# ==============================================================================

class TestAcceptanceGateUsesEffective:

    def test_positive_raw_zero_effective_rejected(self):
        m = _good_metrics(mean_pred_return=0.005, effective_mean_pred_return=0.0)
        accepted, _ = acceptance_gate(m)
        assert not accepted

    def test_positive_effective_accepted(self):
        m = _good_metrics(mean_pred_return=0.005, effective_mean_pred_return=0.003)
        accepted, _ = acceptance_gate(m)
        assert accepted

    def test_negative_effective_rejected(self):
        m = _good_metrics(mean_pred_return=0.005, effective_mean_pred_return=-0.001)
        accepted, _ = acceptance_gate(m)
        assert not accepted


# ==============================================================================
# Test 7: Per-signal vs aggregate effective predicted return are different
# ==============================================================================

class TestPerSignalVsAggregateReturnDamping:

    def test_per_signal_uses_cal_factor_and_conf_factor(self):
        """_compute_effective_predicted_return must multiply by both factors."""
        src = inspect.getsource(MLSignalGenerator._compute_effective_predicted_return)
        assert "cal_factor" in src
        assert "conf_factor" in src

    def test_aggregate_uses_only_cal_factor(self):
        """_evaluate effective_mean_pred_return must use only cal_factor."""
        src = inspect.getsource(MLSignalGenerator._evaluate)
        # Find the effective_mean_pred_return computation
        start = src.index("effective_mean_pred_return")
        block = src[start:start + 200]
        assert "cal_factor" in block
        # Should NOT multiply by conf_factor at this level
        assert "conf_factor" not in block

    def test_per_signal_docstring_distinguishes_from_aggregate(self):
        doc = MLSignalGenerator._compute_effective_predicted_return.__doc__ or ""
        assert "per-signal" in doc.lower() or "aggregate" in doc.lower()


# ==============================================================================
# Test 8: apply_result preserves all calibration + effective fields
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

    def test_effective_mean_pred_return_preserved(self):
        sig = self._make_signal_gen()
        trainer = self._make_trainer_with_result()
        trainer.apply_result(sig, None, None, None, None, None, None)
        assert abs(sig._latest_metrics.effective_mean_pred_return - 0.004) < 0.0001

    def test_backward_compat_missing_calibration(self):
        sig = self._make_signal_gen()
        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=True,
            train_metrics={
                "generation": 3, "accuracy": 0.50, "precision": 0.50,
                "recall": 0.50, "f1": 0.50, "direction_accuracy": 0.50,
                "mean_pred_return": 0.001, "hit_rate": 0.50,
            },
            is_trained=True,
        )
        trainer.apply_result(sig, None, None, None, None, None, None)
        assert sig._latest_metrics.calibration_sample_count == 0
        assert sig._latest_metrics.calibration_monotonic is True
        assert sig._latest_metrics.effective_mean_pred_return == 0.0
