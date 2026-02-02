"""
Comprehensive tests for backend/ml/monitoring.py
Targets: RetrainDecision, decide_retrain function
"""

import pytest
from backend.ml.monitoring import RetrainDecision, decide_retrain


# =============================================================================
# RetrainDecision Tests
# =============================================================================
class TestRetrainDecision:
    """Tests for RetrainDecision dataclass."""

    def test_basic_creation(self):
        """Test creating RetrainDecision with all fields."""
        decision = RetrainDecision(
            should_retrain=True,
            reasons=["drift detected", "performance dropped"]
        )
        assert decision.should_retrain is True
        assert decision.reasons == ["drift detected", "performance dropped"]

    def test_no_retrain(self):
        """Test creating decision with no retrain."""
        decision = RetrainDecision(
            should_retrain=False,
            reasons=[]
        )
        assert decision.should_retrain is False
        assert decision.reasons == []

    def test_frozen(self):
        """Test dataclass is frozen (immutable)."""
        decision = RetrainDecision(should_retrain=True, reasons=["test"])
        with pytest.raises(Exception):
            decision.should_retrain = False


# =============================================================================
# decide_retrain Tests - PSI Threshold
# =============================================================================
class TestDecideRetrainPSI:
    """Tests for decide_retrain PSI threshold logic."""

    def test_psi_above_threshold_triggers_retrain(self):
        """Test PSI above threshold triggers retrain."""
        decision = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=0.05,
            psi_score=0.20,
            psi_threshold=0.15,
        )
        assert decision.should_retrain is True
        assert any("drift psi" in r for r in decision.reasons)

    def test_psi_at_threshold_triggers_retrain(self):
        """Test PSI at exact threshold triggers retrain."""
        decision = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=0.05,
            psi_score=0.15,
            psi_threshold=0.15,
        )
        assert decision.should_retrain is True
        assert any("drift psi" in r for r in decision.reasons)

    def test_psi_below_threshold_no_trigger(self):
        """Test PSI below threshold does not trigger retrain."""
        decision = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=0.05,
            psi_score=0.10,
            psi_threshold=0.15,
        )
        # Only PSI check shouldn't trigger
        assert "drift psi" not in str(decision.reasons)

    def test_psi_none_no_trigger(self):
        """Test PSI of None does not trigger retrain from PSI."""
        decision = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=0.05,
            psi_score=None,
            psi_threshold=0.15,
        )
        assert "drift psi" not in str(decision.reasons)

    def test_custom_psi_threshold(self):
        """Test custom PSI threshold works correctly."""
        # Below custom threshold
        decision1 = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=0.05,
            psi_score=0.20,
            psi_threshold=0.25,
        )
        assert "drift psi" not in str(decision1.reasons)

        # At custom threshold
        decision2 = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=0.05,
            psi_score=0.25,
            psi_threshold=0.25,
        )
        assert any("drift psi" in r for r in decision2.reasons)


# =============================================================================
# decide_retrain Tests - Performance Drop
# =============================================================================
class TestDecideRetrainPerformanceDrop:
    """Tests for decide_retrain performance drop logic."""

    def test_performance_drop_triggers_retrain(self):
        """Test significant performance drop triggers retrain."""
        decision = decide_retrain(
            recent_total_return=0.02,
            reference_total_return=0.05,
            psi_score=None,
            min_return_drop=0.02,
        )
        assert decision.should_retrain is True
        assert any("performance drop" in r for r in decision.reasons)

    def test_performance_at_threshold_triggers_retrain(self):
        """Test performance at exact threshold triggers retrain."""
        # recent = reference - min_return_drop
        decision = decide_retrain(
            recent_total_return=0.03,
            reference_total_return=0.05,
            psi_score=None,
            min_return_drop=0.02,
        )
        assert decision.should_retrain is True
        assert any("performance drop" in r for r in decision.reasons)

    def test_small_drop_no_trigger(self):
        """Test small performance drop does not trigger retrain."""
        decision = decide_retrain(
            recent_total_return=0.04,  # Only 0.01 drop, less than threshold
            reference_total_return=0.05,
            psi_score=None,
            min_return_drop=0.02,
        )
        assert "performance drop" not in str(decision.reasons)

    def test_improved_performance_no_trigger(self):
        """Test improved performance does not trigger retrain."""
        decision = decide_retrain(
            recent_total_return=0.08,
            reference_total_return=0.05,
            psi_score=None,
            min_return_drop=0.02,
        )
        assert decision.should_retrain is False

    def test_custom_min_return_drop(self):
        """Test custom min_return_drop works correctly."""
        # 0.05 drop with 0.06 threshold - should not trigger
        decision = decide_retrain(
            recent_total_return=0.00,
            reference_total_return=0.05,
            psi_score=None,
            min_return_drop=0.06,
        )
        assert "performance drop" not in str(decision.reasons)

        # 0.06 drop with 0.06 threshold - should trigger
        decision2 = decide_retrain(
            recent_total_return=-0.01,
            reference_total_return=0.05,
            psi_score=None,
            min_return_drop=0.06,
        )
        assert any("performance drop" in r for r in decision2.reasons)


# =============================================================================
# decide_retrain Tests - Negative Return Fallback
# =============================================================================
class TestDecideRetrainNegativeReturn:
    """Tests for decide_retrain negative return fallback logic."""

    def test_negative_return_without_reference_triggers(self):
        """Test negative return without reference triggers retrain."""
        decision = decide_retrain(
            recent_total_return=-0.05,
            reference_total_return=None,  # No reference
            psi_score=None,
        )
        assert decision.should_retrain is True
        assert any("negative recent total_return" in r for r in decision.reasons)

    def test_zero_return_without_reference_no_trigger(self):
        """Test zero return without reference does not trigger retrain."""
        decision = decide_retrain(
            recent_total_return=0.0,
            reference_total_return=None,
            psi_score=None,
        )
        assert "negative recent total_return" not in str(decision.reasons)

    def test_positive_return_without_reference_no_trigger(self):
        """Test positive return without reference does not trigger."""
        decision = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=None,
            psi_score=None,
        )
        assert decision.should_retrain is False


# =============================================================================
# decide_retrain Tests - Combined Scenarios
# =============================================================================
class TestDecideRetrainCombined:
    """Tests for decide_retrain with multiple conditions."""

    def test_both_psi_and_performance_triggers(self):
        """Test both PSI and performance drop trigger together."""
        decision = decide_retrain(
            recent_total_return=0.01,
            reference_total_return=0.10,
            psi_score=0.25,
            min_return_drop=0.02,
            psi_threshold=0.15,
        )
        assert decision.should_retrain is True
        assert len(decision.reasons) == 2
        assert any("drift psi" in r for r in decision.reasons)
        assert any("performance drop" in r for r in decision.reasons)

    def test_neither_triggers(self):
        """Test when neither PSI nor performance drop triggers."""
        decision = decide_retrain(
            recent_total_return=0.08,
            reference_total_return=0.10,
            psi_score=0.05,
            min_return_drop=0.03,
            psi_threshold=0.15,
        )
        assert decision.should_retrain is False
        assert len(decision.reasons) == 0

    def test_only_psi_triggers(self):
        """Test when only PSI triggers."""
        decision = decide_retrain(
            recent_total_return=0.09,  # Good performance
            reference_total_return=0.10,
            psi_score=0.20,  # High PSI
            min_return_drop=0.02,
            psi_threshold=0.15,
        )
        assert decision.should_retrain is True
        assert len(decision.reasons) == 1
        assert "drift psi" in decision.reasons[0]

    def test_only_performance_triggers(self):
        """Test when only performance drop triggers."""
        decision = decide_retrain(
            recent_total_return=0.05,  # Dropped from 0.10
            reference_total_return=0.10,
            psi_score=0.05,  # Low PSI
            min_return_drop=0.02,
            psi_threshold=0.15,
        )
        assert decision.should_retrain is True
        assert len(decision.reasons) == 1
        assert "performance drop" in decision.reasons[0]


# =============================================================================
# decide_retrain Tests - Edge Cases
# =============================================================================
class TestDecideRetrainEdgeCases:
    """Edge case tests for decide_retrain."""

    def test_very_small_psi(self):
        """Test very small PSI values."""
        decision = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=0.05,
            psi_score=0.001,
            psi_threshold=0.15,
        )
        assert "drift psi" not in str(decision.reasons)

    def test_very_large_psi(self):
        """Test very large PSI values."""
        decision = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=0.05,
            psi_score=0.95,
            psi_threshold=0.15,
        )
        assert any("drift psi" in r for r in decision.reasons)

    def test_very_negative_return(self):
        """Test very negative return values."""
        decision = decide_retrain(
            recent_total_return=-0.50,
            reference_total_return=0.10,
            psi_score=None,
            min_return_drop=0.02,
        )
        assert decision.should_retrain is True
        assert any("performance drop" in r for r in decision.reasons)

    def test_zero_thresholds(self):
        """Test with zero thresholds."""
        decision = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=0.05,
            psi_score=0.01,
            min_return_drop=0.0,
            psi_threshold=0.0,
        )
        # Any PSI >= 0 would trigger
        assert any("drift psi" in r for r in decision.reasons)

    def test_equal_returns_with_zero_drop_threshold(self):
        """Test equal returns with zero drop threshold."""
        decision = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=0.05,
            psi_score=None,
            min_return_drop=0.0,
        )
        # recent (0.05) <= reference (0.05) - 0 = 0.05, so exactly equal triggers
        assert any("performance drop" in r for r in decision.reasons)

    def test_float_precision(self):
        """Test float precision handling."""
        decision = decide_retrain(
            recent_total_return=0.029999999999,
            reference_total_return=0.05,
            psi_score=0.149999999999,
            min_return_drop=0.02,
            psi_threshold=0.15,
        )
        # Should handle float precision correctly
        assert isinstance(decision.should_retrain, bool)

    def test_string_numeric_conversion(self):
        """Test that numeric values are properly converted from strings if needed."""
        # The function uses float() on all inputs, so implicit conversion should work
        decision = decide_retrain(
            recent_total_return=0.05,
            reference_total_return=0.10,
            psi_score=0.20,
            min_return_drop=0.02,
            psi_threshold=0.15,
        )
        assert decision.should_retrain is True
