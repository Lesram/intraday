"""Tests for Patch Queue H1 -- ML signal honesty and economic-quality gate tightening."""
from __future__ import annotations

import math
import pytest

from backend.organism.ml_signal import MLSignalGenerator, MLSignal, ModelMetrics
from backend.organism.continuous_learner import ContinuousLearner


# ==============================================================================
# Test 1: ModelMetrics serialization includes calibration fields
# ==============================================================================

class TestModelMetricsCalibrationFields:

    def test_to_dict_includes_calibration_sample_count(self):
        m = ModelMetrics(generation=1, calibration_sample_count=42)
        d = m.to_dict()
        assert "calibration_sample_count" in d
        assert d["calibration_sample_count"] == 42

    def test_to_dict_includes_calibration_monotonic(self):
        m = ModelMetrics(generation=1, calibration_monotonic=False)
        d = m.to_dict()
        assert "calibration_monotonic" in d
        assert d["calibration_monotonic"] is False

    def test_to_dict_includes_calibration_error(self):
        m = ModelMetrics(generation=1, calibration_error=0.123)
        d = m.to_dict()
        assert "calibration_error" in d
        assert abs(d["calibration_error"] - 0.123) < 0.001

    def test_defaults_are_safe(self):
        m = ModelMetrics(generation=1)
        assert m.calibration_sample_count == 0
        assert m.calibration_monotonic is True
        assert m.calibration_error == 0.0

    def test_backward_compat_with_existing_fields(self):
        """New fields don't break existing to_dict keys."""
        m = ModelMetrics(generation=5, accuracy=0.6, precision=0.55)
        d = m.to_dict()
        assert d["accuracy"] == 0.6
        assert d["precision"] == 0.55
        assert "calibration_sample_count" in d


# ==============================================================================
# Test 2: Calibration quality method
# ==============================================================================

class TestCalibrationQuality:

    def test_empty_calibration_returns_zero_samples(self):
        sig = MLSignalGenerator()
        total, mono, err = sig.calibration_quality()
        assert total == 0
        assert mono is True
        assert err == 0.0

    def test_sufficient_monotonic_calibration(self):
        """Monotonically increasing win rates should return monotonic=True."""
        sig = MLSignalGenerator()
        # Bin 0 (0-0.2): 3/10 = 0.30
        sig._calibration_counts[0] = [3, 10]
        # Bin 1 (0.2-0.4): 4/10 = 0.40
        sig._calibration_counts[1] = [4, 10]
        # Bin 2 (0.4-0.6): 5/10 = 0.50
        sig._calibration_counts[2] = [5, 10]

        total, mono, err = sig.calibration_quality()
        assert total == 30
        assert mono is True
        assert err > 0  # some miscalibration expected

    def test_inverted_calibration_returns_monotonic_false(self):
        """Higher-confidence bin with LOWER win rate -> monotonic=False."""
        sig = MLSignalGenerator()
        # Bin 0 (0-0.2): 8/10 = 0.80 (high for a low-confidence bin)
        sig._calibration_counts[0] = [8, 10]
        # Bin 2 (0.4-0.6): 3/10 = 0.30 (low for a high-confidence bin)
        sig._calibration_counts[2] = [3, 10]

        total, mono, err = sig.calibration_quality()
        assert total == 20
        assert mono is False

    def test_calibration_error_measures_miscalibration(self):
        """Perfect calibration should give error near 0."""
        sig = MLSignalGenerator()
        # Bin 0 midpoint = 0.1, set win rate = 0.1
        sig._calibration_counts[0] = [1, 10]
        # Bin 2 midpoint = 0.5, set win rate = 0.5
        sig._calibration_counts[2] = [5, 10]

        _, _, err = sig.calibration_quality()
        assert err < 0.01  # near-perfect calibration


# ==============================================================================
# Test 3: Effective predicted_return damping
# ==============================================================================

class TestEffectivePredictedReturn:

    def test_mlsignal_has_effective_predicted_return_field(self):
        sig = MLSignal(
            symbol="TEST", direction=1.0, confidence=0.8,
            predicted_return=0.03,
        )
        assert hasattr(sig, "effective_predicted_return")

    def test_weak_calibration_damps_predicted_return(self):
        """With zero calibration samples, effective_predicted_return < raw."""
        sig = MLSignalGenerator()
        # No calibration data at all
        raw_return = 0.05
        eff_conf = 0.6
        eff_ret = sig._compute_effective_predicted_return(raw_return, eff_conf)
        # cal_factor = 0/30 = 0, so effective should be heavily damped
        assert eff_ret < raw_return * 0.5, \
            f"Expected heavy damping with zero calibration, got {eff_ret}"

    def test_strong_calibration_preserves_predicted_return(self):
        """With sufficient calibration and high confidence, preserve more signal."""
        sig = MLSignalGenerator()
        # Fill calibration with 50 total samples
        sig._calibration_counts[2] = [25, 50]

        raw_return = 0.05
        eff_conf = 0.9
        eff_ret = sig._compute_effective_predicted_return(raw_return, eff_conf)
        # cal_factor = min(1, 50/30) = 1.0, conf_factor = 0.9
        # damping = 1.0 * 0.9 = 0.9
        assert eff_ret >= raw_return * 0.8, \
            f"Expected preserved signal with strong calibration, got {eff_ret}"

    def test_low_confidence_damps_predicted_return(self):
        """Even with good calibration, low confidence damps return."""
        sig = MLSignalGenerator()
        sig._calibration_counts[2] = [25, 50]

        raw_return = 0.05
        eff_conf = 0.1  # very low
        eff_ret = sig._compute_effective_predicted_return(raw_return, eff_conf)
        # cal_factor = 1.0, conf_factor = max(0.1, 0.1) = 0.1
        assert eff_ret <= raw_return * 0.15, \
            f"Expected damped signal with low confidence, got {eff_ret}"

    def test_effective_predicted_return_preserves_sign(self):
        """Damping should not flip the sign of predicted_return."""
        sig = MLSignalGenerator()
        sig._calibration_counts[2] = [25, 50]
        neg_ret = sig._compute_effective_predicted_return(-0.03, 0.8)
        assert neg_ret < 0
        pos_ret = sig._compute_effective_predicted_return(0.03, 0.8)
        assert pos_ret > 0

    def test_min_calibration_samples_constant_exists(self):
        """MIN_CALIBRATION_SAMPLES must be defined on MLSignalGenerator."""
        assert hasattr(MLSignalGenerator, "MIN_CALIBRATION_SAMPLES")
        assert MLSignalGenerator.MIN_CALIBRATION_SAMPLES == 30


# ==============================================================================
# Test 4: Acceptance gate calibration honesty constraint
# ==============================================================================

class TestAcceptanceGateCalibration:

    def _make_learner(self) -> ContinuousLearner:
        sig_gen = MLSignalGenerator()
        return ContinuousLearner(sig_gen)

    def _good_metrics(self, **overrides) -> ModelMetrics:
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

    def test_good_model_accepted(self):
        """Model with good stats + honest calibration is accepted."""
        learner = self._make_learner()
        metrics = self._good_metrics()
        accepted = learner._validate_new_model({}, metrics, None)
        assert accepted

    def test_inverted_calibration_rejected_with_sufficient_data(self):
        """Model with sufficient calibration but inverted monotonicity is rejected."""
        learner = self._make_learner()
        metrics = self._good_metrics(
            calibration_sample_count=50,
            calibration_monotonic=False,
        )
        accepted = learner._validate_new_model({}, metrics, None)
        assert not accepted, \
            "Model with inverted calibration must be rejected"

    def test_inverted_calibration_ignored_with_insufficient_data(self):
        """With insufficient calibration data, monotonicity is not checked."""
        learner = self._make_learner()
        # Good stats but inverted calibration with only 10 samples
        # Should still pass if score is high enough (raised threshold)
        metrics = self._good_metrics(
            calibration_sample_count=10,
            calibration_monotonic=False,
            # Boost stats to pass the raised 0.35 threshold
            accuracy=0.65,
            hit_rate=0.60,
            direction_accuracy=0.65,
        )
        accepted = learner._validate_new_model({}, metrics, None)
        # Should be accepted because insufficient data means monotonicity is not enforced
        assert accepted

    def test_weak_calibration_requires_higher_score(self):
        """With insufficient calibration, minimum score threshold is raised to 0.35."""
        learner = self._make_learner()
        # Score that would pass 0.25 but fail 0.35
        # score = 0.45*0.4 + 0.50*0.3 + max(0.50-0.5,0)*0.6 = 0.18 + 0.15 + 0 = 0.33
        metrics = self._good_metrics(
            calibration_sample_count=5,  # insufficient
            accuracy=0.50,
            hit_rate=0.45,
            direction_accuracy=0.50,
        )
        accepted = learner._validate_new_model({}, metrics, None)
        assert not accepted, \
            "Weakly calibrated model with borderline score should be rejected"

    def test_same_model_passes_with_sufficient_calibration(self):
        """Same stats with sufficient calibration pass at lower threshold."""
        learner = self._make_learner()
        # score = 0.50*0.4 + 0.55*0.3 + max(0.55-0.5,0)*0.6 = 0.20 + 0.165 + 0.03 = 0.395
        # This would fail at 0.35 if we had insufficient cal, but it's above 0.25
        # Actually let's make a score that's between 0.25 and 0.35
        # score = 0.48*0.4 + 0.52*0.3 + max(0.52-0.5,0)*0.6 = 0.192+0.156+0.012 = 0.36
        metrics = self._good_metrics(
            calibration_sample_count=50,
            accuracy=0.52,
            hit_rate=0.48,
            direction_accuracy=0.52,
        )
        accepted = learner._validate_new_model({}, metrics, None)
        assert accepted, \
            "With sufficient calibration, lower score threshold should apply"

    def test_min_calibration_constant_exists(self):
        """MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE must be defined."""
        assert hasattr(ContinuousLearner, "MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE")
        assert ContinuousLearner.MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE == 30
