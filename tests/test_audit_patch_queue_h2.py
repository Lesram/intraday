"""Tests for Patch Queue H2 -- unify background trainer acceptance with learner acceptance."""
from __future__ import annotations

import pytest

from backend.organism.ml_signal import MLSignalGenerator, ModelMetrics
from backend.organism.continuous_learner import (
    ContinuousLearner,
    acceptance_gate,
    MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE,
)


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
        hit_rate=0.55,
        calibration_sample_count=50,
        calibration_monotonic=True,
        calibration_error=0.05,
    )
    defaults.update(overrides)
    return ModelMetrics(**defaults)


# ==============================================================================
# Test 1: acceptance_gate is a shared module-level function
# ==============================================================================

class TestAcceptanceGateIsShared:

    def test_acceptance_gate_is_callable(self):
        assert callable(acceptance_gate)

    def test_acceptance_gate_returns_tuple(self):
        m = _good_metrics()
        result = acceptance_gate(m)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_acceptance_gate_returns_bool_and_str(self):
        m = _good_metrics()
        accepted, reason = acceptance_gate(m)
        assert isinstance(accepted, bool)
        assert isinstance(reason, str)

    def test_min_calibration_constant_is_module_level(self):
        assert MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE == 30

    def test_learner_class_constant_matches_module(self):
        assert ContinuousLearner.MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE == MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE


# ==============================================================================
# Test 2: acceptance_gate enforces calibration honesty
# ==============================================================================

class TestAcceptanceGateCalibrationHonesty:

    def test_inverted_calibration_rejected_with_sufficient_data(self):
        m = _good_metrics(
            calibration_sample_count=50,
            calibration_monotonic=False,
        )
        accepted, reason = acceptance_gate(m)
        assert not accepted, "Inverted calibration with sufficient data must be rejected"
        assert "cal_monotonic" in reason

    def test_good_calibration_accepted(self):
        m = _good_metrics(
            calibration_sample_count=50,
            calibration_monotonic=True,
        )
        accepted, _ = acceptance_gate(m)
        assert accepted

    def test_inverted_calibration_ignored_with_insufficient_data(self):
        """With insufficient calibration data, monotonicity is not checked."""
        m = _good_metrics(
            calibration_sample_count=10,
            calibration_monotonic=False,
            # Boost stats to pass the raised 0.35 threshold
            accuracy=0.65,
            hit_rate=0.60,
            direction_accuracy=0.65,
        )
        accepted, _ = acceptance_gate(m)
        assert accepted, "Inverted calibration with insufficient data should not block"

    def test_insufficient_calibration_raises_threshold(self):
        """With insufficient calibration, minimum score threshold is raised to 0.35."""
        # score = 0.45*0.4 + 0.50*0.3 + max(0.50-0.5,0)*0.6 = 0.18 + 0.15 + 0 = 0.33
        m = _good_metrics(
            calibration_sample_count=5,
            accuracy=0.50,
            hit_rate=0.45,
            direction_accuracy=0.50,
        )
        accepted, _ = acceptance_gate(m)
        assert not accepted, "Weakly calibrated model with borderline score should be rejected"

    def test_same_stats_pass_with_sufficient_calibration(self):
        """Same stats with sufficient calibration pass at lower threshold."""
        # score = 0.48*0.4 + 0.52*0.3 + max(0.52-0.5,0)*0.6 = 0.192+0.156+0.012 = 0.36
        m = _good_metrics(
            calibration_sample_count=50,
            accuracy=0.52,
            hit_rate=0.48,
            direction_accuracy=0.52,
        )
        accepted, _ = acceptance_gate(m)
        assert accepted, "With sufficient calibration, lower threshold should apply"


# ==============================================================================
# Test 3: ContinuousLearner delegates to acceptance_gate
# ==============================================================================

class TestLearnerDelegatesToSharedGate:

    def _make_learner(self) -> ContinuousLearner:
        sig_gen = MLSignalGenerator()
        return ContinuousLearner(sig_gen)

    def test_learner_accepts_good_model(self):
        learner = self._make_learner()
        m = _good_metrics()
        assert learner._validate_new_model({}, m, None)

    def test_learner_rejects_inverted_calibration(self):
        learner = self._make_learner()
        m = _good_metrics(calibration_sample_count=50, calibration_monotonic=False)
        assert not learner._validate_new_model({}, m, None)

    def test_learner_raises_threshold_for_insufficient_cal(self):
        learner = self._make_learner()
        m = _good_metrics(
            calibration_sample_count=5,
            accuracy=0.50, hit_rate=0.45, direction_accuracy=0.50,
        )
        assert not learner._validate_new_model({}, m, None)


# ==============================================================================
# Test 4: Background trainer uses acceptance_gate (source-level verification)
# ==============================================================================

class TestBackgroundTrainerUsesSharedGate:

    def test_train_in_process_imports_acceptance_gate(self):
        """_train_in_process must import and call acceptance_gate."""
        import inspect
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module._train_in_process)
        assert "acceptance_gate" in src, \
            "_train_in_process must use the shared acceptance_gate"

    def test_train_in_process_does_not_have_inline_score(self):
        """_train_in_process must NOT define its own _score function."""
        import inspect
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module._train_in_process)
        assert "def _score" not in src, \
            "_train_in_process must delegate to acceptance_gate, not define _score"


# ==============================================================================
# Test 5: Background trainer and ContinuousLearner agree on same metrics
# ==============================================================================

class TestBackgroundAndLearnerAgree:

    def _make_learner(self) -> ContinuousLearner:
        sig_gen = MLSignalGenerator()
        return ContinuousLearner(sig_gen)

    def _check_agreement(self, metrics: ModelMetrics) -> None:
        """Both paths must give the same accept/reject decision."""
        learner = self._make_learner()
        learner_decision = learner._validate_new_model({}, metrics, None)
        gate_decision, _ = acceptance_gate(metrics, old_metrics=None)
        assert learner_decision == gate_decision, \
            f"Learner={learner_decision}, gate={gate_decision} for {metrics}"

    def test_agreement_good_model(self):
        self._check_agreement(_good_metrics())

    def test_agreement_inverted_calibration(self):
        self._check_agreement(_good_metrics(
            calibration_sample_count=50, calibration_monotonic=False,
        ))

    def test_agreement_insufficient_calibration_low_score(self):
        self._check_agreement(_good_metrics(
            calibration_sample_count=5,
            accuracy=0.50, hit_rate=0.45, direction_accuracy=0.50,
        ))

    def test_agreement_insufficient_calibration_high_score(self):
        self._check_agreement(_good_metrics(
            calibration_sample_count=5,
            accuracy=0.65, hit_rate=0.60, direction_accuracy=0.65,
            calibration_monotonic=False,
        ))

    def test_agreement_no_edge(self):
        self._check_agreement(_good_metrics(mean_pred_return=-0.001))

    def test_agreement_low_precision(self):
        self._check_agreement(_good_metrics(precision=0.30))


# ==============================================================================
# Test 6: train_metrics includes calibration fields
# ==============================================================================

class TestTrainMetricsCalibrationFields:

    def test_train_metrics_has_calibration_sample_count(self):
        """Background trainer train_metrics must include calibration_sample_count."""
        import inspect
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module._train_in_process)
        assert "calibration_sample_count" in src

    def test_train_metrics_has_calibration_monotonic(self):
        """Background trainer train_metrics must include calibration_monotonic."""
        import inspect
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module._train_in_process)
        assert "calibration_monotonic" in src

    def test_train_metrics_has_calibration_error(self):
        """Background trainer train_metrics must include calibration_error."""
        import inspect
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module._train_in_process)
        assert "calibration_error" in src

    def test_build_train_metrics_includes_all_calibration_fields(self):
        """The _build_train_metrics helper in _train_in_process must
        include all three calibration fields."""
        import inspect
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module._train_in_process)
        # Find the _build_train_metrics helper
        assert "_build_train_metrics" in src
        # The helper must reference all three calibration fields
        helper_start = src.index("def _build_train_metrics")
        helper_block = src[helper_start:src.index("if not accepted", helper_start)]
        assert "calibration_sample_count" in helper_block
        assert "calibration_monotonic" in helper_block
        assert "calibration_error" in helper_block


# ==============================================================================
# Test 7: Old metrics reconstruction includes calibration fields
# ==============================================================================

class TestOldMetricsReconstructionIncludesCalibration:

    def test_old_metrics_reconstruction_has_calibration_fields(self):
        """When reconstructing old ModelMetrics from dict, calibration fields
        must be included."""
        import inspect
        from backend.organism import background_trainer as bt_module
        src = inspect.getsource(bt_module._train_in_process)
        # Find old_metrics_obj construction block (up to the closing paren + acceptance_gate call)
        old_metrics_block_start = src.index("old_metrics_obj = _MM(")
        old_metrics_block_end = src.index("acceptance_gate", old_metrics_block_start)
        old_metrics_block = src[old_metrics_block_start:old_metrics_block_end]
        assert "calibration_sample_count" in old_metrics_block
        assert "calibration_monotonic" in old_metrics_block
        assert "calibration_error" in old_metrics_block
