"""Tests for Patch Queue I1 -- candidate-model calibration quality and acceptance realism."""
from __future__ import annotations

import inspect
import math

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
    """Create metrics that pass all acceptance gates."""
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
        candidate_calibration_sample_count=50,
        candidate_calibration_monotonic=True,
        candidate_calibration_error=0.05,
    )
    defaults.update(overrides)
    return ModelMetrics(**defaults)


# ==============================================================================
# Test 1: ModelMetrics has candidate calibration fields
# ==============================================================================

class TestModelMetricsCandidateCalibrationFields:

    def test_candidate_calibration_sample_count_exists(self):
        m = ModelMetrics(generation=1)
        assert hasattr(m, "candidate_calibration_sample_count")
        assert m.candidate_calibration_sample_count == 0

    def test_candidate_calibration_monotonic_exists(self):
        m = ModelMetrics(generation=1)
        assert hasattr(m, "candidate_calibration_monotonic")
        assert m.candidate_calibration_monotonic is True

    def test_candidate_calibration_error_exists(self):
        m = ModelMetrics(generation=1)
        assert hasattr(m, "candidate_calibration_error")
        assert m.candidate_calibration_error == 0.0

    def test_to_dict_includes_candidate_calibration_sample_count(self):
        m = ModelMetrics(generation=1, candidate_calibration_sample_count=42)
        d = m.to_dict()
        assert "candidate_calibration_sample_count" in d
        assert d["candidate_calibration_sample_count"] == 42

    def test_to_dict_includes_candidate_calibration_monotonic(self):
        m = ModelMetrics(generation=1, candidate_calibration_monotonic=False)
        d = m.to_dict()
        assert "candidate_calibration_monotonic" in d
        assert d["candidate_calibration_monotonic"] is False

    def test_to_dict_includes_candidate_calibration_error(self):
        m = ModelMetrics(generation=1, candidate_calibration_error=0.123)
        d = m.to_dict()
        assert "candidate_calibration_error" in d
        assert abs(d["candidate_calibration_error"] - 0.123) < 0.001

    def test_system_level_fields_still_exist(self):
        """Candidate fields do not replace system-level fields."""
        m = ModelMetrics(
            generation=1,
            calibration_sample_count=100,
            candidate_calibration_sample_count=50,
        )
        assert m.calibration_sample_count == 100
        assert m.candidate_calibration_sample_count == 50


# ==============================================================================
# Test 2: _evaluate() populates candidate calibration fields
# ==============================================================================

class TestEvaluatePopulatesCandidateCalibration:

    def test_evaluate_source_has_candidate_calibration(self):
        src = inspect.getsource(MLSignalGenerator._evaluate)
        assert "candidate_calibration_sample_count" in src
        assert "candidate_calibration_monotonic" in src
        assert "candidate_calibration_error" in src

    def test_evaluate_calls_candidate_calibration_summary(self):
        src = inspect.getsource(MLSignalGenerator._evaluate)
        assert "_candidate_calibration_summary" in src

    def test_candidate_calibration_summary_method_exists(self):
        assert hasattr(MLSignalGenerator, "_candidate_calibration_summary")

    def test_candidate_calibration_summary_uses_validation_data(self):
        """_candidate_calibration_summary must take confidence and correct arrays."""
        src = inspect.getsource(MLSignalGenerator._candidate_calibration_summary)
        assert "confidences" in src
        assert "correct" in src


# ==============================================================================
# Test 3: _candidate_calibration_summary correctness
# ==============================================================================

class TestCandidateCalibrationSummary:

    def test_monotonic_bins_return_true(self):
        import numpy as np
        # Low confidence bin: 30% correct, high confidence bin: 70% correct
        confs = np.array([0.1]*20 + [0.9]*20)
        correct = np.array([0]*14 + [1]*6 + [0]*6 + [1]*14)
        total, mono, err = MLSignalGenerator._candidate_calibration_summary(confs, correct)
        assert total == 40
        assert mono is True

    def test_inverted_bins_return_false(self):
        import numpy as np
        # Low confidence bin: 80% correct, high confidence bin: 20% correct
        confs = np.array([0.1]*20 + [0.9]*20)
        correct = np.array([0]*4 + [1]*16 + [0]*16 + [1]*4)
        total, mono, err = MLSignalGenerator._candidate_calibration_summary(confs, correct)
        assert total == 40
        assert mono is False

    def test_single_bin_is_monotonic(self):
        import numpy as np
        confs = np.array([0.5]*30)
        correct = np.array([1]*15 + [0]*15)
        total, mono, err = MLSignalGenerator._candidate_calibration_summary(confs, correct)
        assert total == 30
        assert mono is True

    def test_perfect_calibration_low_error(self):
        import numpy as np
        # Bin 0 midpoint=0.1, actual=0.1 -> error=0
        # Bin 4 midpoint=0.9, actual=0.9 -> error=0
        confs = np.array([0.1]*100 + [0.9]*100)
        correct = np.array([0]*90 + [1]*10 + [0]*10 + [1]*90)
        _, _, err = MLSignalGenerator._candidate_calibration_summary(confs, correct)
        assert err < 0.01


# ==============================================================================
# Test 4: acceptance_gate uses candidate-level calibration
# ==============================================================================

class TestAcceptanceGateUsesCandidateCalibration:

    def test_good_system_bad_candidate_monotonic_rejected(self):
        """Good system-level calibration but inverted candidate -> rejected."""
        m = _good_metrics(
            calibration_sample_count=50,
            calibration_monotonic=True,
            candidate_calibration_sample_count=50,
            candidate_calibration_monotonic=False,
        )
        accepted, reason = acceptance_gate(m)
        assert not accepted, "Inverted candidate calibration must reject"
        assert "cand_cal_mono" in reason

    def test_good_candidate_bad_system_monotonic_accepted(self):
        """System-level inverted but candidate is fine -> accepted
        (system-level monotonicity no longer used as hard gate)."""
        m = _good_metrics(
            calibration_sample_count=50,
            calibration_monotonic=False,
            candidate_calibration_sample_count=50,
            candidate_calibration_monotonic=True,
        )
        accepted, _ = acceptance_gate(m)
        assert accepted

    def test_candidate_inverted_ignored_when_insufficient(self):
        """With insufficient candidate calibration data, monotonicity not checked."""
        m = _good_metrics(
            candidate_calibration_sample_count=10,
            candidate_calibration_monotonic=False,
            # Boost stats to pass raised 0.35 threshold
            accuracy=0.65,
            hit_rate=0.60,
            direction_accuracy=0.65,
        )
        accepted, _ = acceptance_gate(m)
        assert accepted

    def test_insufficient_candidate_cal_raises_threshold(self):
        """When candidate calibration is insufficient, score threshold is 0.35."""
        # score ~ 0.33 (between 0.25 and 0.35)
        m = _good_metrics(
            candidate_calibration_sample_count=5,
            calibration_sample_count=50,
            accuracy=0.50,
            hit_rate=0.45,
            direction_accuracy=0.50,
        )
        accepted, _ = acceptance_gate(m)
        assert not accepted

    def test_sufficient_candidate_cal_lowers_threshold(self):
        """Same stats with sufficient candidate calibration -> lower threshold."""
        # score ~ 0.36 (passes 0.25 but not 0.35)
        m = _good_metrics(
            candidate_calibration_sample_count=50,
            calibration_sample_count=50,
            accuracy=0.52,
            hit_rate=0.48,
            direction_accuracy=0.52,
        )
        accepted, _ = acceptance_gate(m)
        assert accepted

    def test_high_candidate_calibration_error_rejected(self):
        """Candidate with calibration_error >= 0.25 and sufficient samples -> rejected."""
        m = _good_metrics(
            candidate_calibration_sample_count=50,
            candidate_calibration_monotonic=True,
            candidate_calibration_error=0.30,
        )
        accepted, reason = acceptance_gate(m)
        assert not accepted

    def test_low_candidate_calibration_error_accepted(self):
        """Candidate with calibration_error < 0.25 and sufficient samples -> accepted."""
        m = _good_metrics(
            candidate_calibration_sample_count=50,
            candidate_calibration_monotonic=True,
            candidate_calibration_error=0.10,
        )
        accepted, _ = acceptance_gate(m)
        assert accepted

    def test_acceptance_gate_source_references_candidate(self):
        src = inspect.getsource(acceptance_gate)
        assert "candidate_calibration" in src

    def test_acceptance_gate_docstring_documents_candidate(self):
        doc = acceptance_gate.__doc__ or ""
        assert "candidate" in doc.lower()


# ==============================================================================
# Test 5: acceptance_gate backward compat (missing candidate fields)
# ==============================================================================

class TestAcceptanceGateBackwardCompat:

    def test_old_metrics_without_candidate_fields_still_work(self):
        """ModelMetrics created without candidate fields should default safely."""
        m = ModelMetrics(
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
            # No candidate fields — defaults apply
        )
        # candidate defaults: sample_count=0, monotonic=True, error=0.0
        # -> insufficient candidate -> raised threshold (0.35)
        # But score is high enough: 0.55*0.4 + 0.60*0.3 + 0.10*0.6 = 0.46
        accepted, _ = acceptance_gate(m)
        assert accepted


# ==============================================================================
# Test 6: Background trainer preserves candidate calibration fields
# ==============================================================================

class TestBackgroundTrainerCandidateCalibration:

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
            "calibration_sample_count": 50,
            "calibration_monotonic": True,
            "calibration_error": 0.05,
            "candidate_calibration_sample_count": 45,
            "candidate_calibration_monotonic": False,
            "candidate_calibration_error": 0.12,
        }
        tm.update(tm_overrides)
        trainer = BackgroundTrainer()
        trainer._last_result = TrainResult(
            accepted=True,
            train_metrics=tm,
            is_trained=True,
        )
        return trainer

    def test_candidate_calibration_sample_count_preserved(self):
        sig = self._make_signal_gen()
        trainer = self._make_trainer_with_result()
        trainer.apply_result(sig, None, None, None, None, None, None)
        assert sig._latest_metrics.candidate_calibration_sample_count == 45

    def test_candidate_calibration_monotonic_preserved(self):
        sig = self._make_signal_gen()
        trainer = self._make_trainer_with_result()
        trainer.apply_result(sig, None, None, None, None, None, None)
        assert sig._latest_metrics.candidate_calibration_monotonic is False

    def test_candidate_calibration_error_preserved(self):
        sig = self._make_signal_gen()
        trainer = self._make_trainer_with_result()
        trainer.apply_result(sig, None, None, None, None, None, None)
        assert abs(sig._latest_metrics.candidate_calibration_error - 0.12) < 0.001

    def test_backward_compat_missing_candidate_calibration(self):
        """Old train_metrics without candidate fields should default safely."""
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
        assert sig._latest_metrics.candidate_calibration_sample_count == 0
        assert sig._latest_metrics.candidate_calibration_monotonic is True
        assert sig._latest_metrics.candidate_calibration_error == 0.0


# ==============================================================================
# Test 7: _build_train_metrics includes candidate calibration fields
# ==============================================================================

class TestBuildTrainMetricsCandidateCalibration:

    def test_build_train_metrics_includes_candidate_fields(self):
        """_build_train_metrics helper in _train_in_process must include
        all three candidate calibration fields."""
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module._train_in_process)
        assert "_build_train_metrics" in src
        helper_start = src.index("def _build_train_metrics")
        # Find the end of the helper (next if/return or unindented block)
        helper_block = src[helper_start:src.index("if not accepted", helper_start)]
        assert "candidate_calibration_sample_count" in helper_block
        assert "candidate_calibration_monotonic" in helper_block
        assert "candidate_calibration_error" in helper_block


# ==============================================================================
# Test 8: old_metrics reconstruction includes candidate calibration fields
# ==============================================================================

class TestOldMetricsReconstructionCandidateCalibration:

    def test_old_metrics_reconstruction_has_candidate_fields(self):
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module._train_in_process)
        old_block_start = src.index("old_metrics_obj = _MM(")
        old_block_end = src.index("acceptance_gate", old_block_start)
        old_block = src[old_block_start:old_block_end]
        assert "candidate_calibration_sample_count" in old_block
        assert "candidate_calibration_monotonic" in old_block
        assert "candidate_calibration_error" in old_block


# ==============================================================================
# Test 9: Documentation clarity
# ==============================================================================

class TestDocumentationClarity:

    def test_model_metrics_docstring_mentions_candidate(self):
        doc = ModelMetrics.__doc__ or ""
        assert "candidate" in doc.lower()

    def test_model_metrics_comments_distinguish_system_and_candidate(self):
        src = inspect.getsource(ModelMetrics)
        assert "system-level" in src.lower() or "system" in src.lower()
        assert "candidate" in src.lower()

    def test_acceptance_gate_docstring_has_two_scopes(self):
        doc = acceptance_gate.__doc__ or ""
        assert "system" in doc.lower()
        assert "candidate" in doc.lower()

    def test_evaluate_comments_distinguish_system_and_candidate(self):
        src = inspect.getsource(MLSignalGenerator._evaluate)
        assert "system" in src.lower() or "System" in src
        assert "candidate" in src.lower() or "Candidate" in src
