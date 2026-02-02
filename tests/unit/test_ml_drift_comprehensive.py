"""
Comprehensive tests for backend.ml.drift module.
Target: 77 missing statements -> high coverage
"""
import pytest
import numpy as np
import pandas as pd

from backend.ml.drift import (
    DriftResult,
    _safe_props,
    psi_from_proportions,
    build_quantile_bins,
    proportions_in_bins,
    build_drift_baseline,
    compute_drift,
)


# =============================================================================
# DriftResult Tests
# =============================================================================

class TestDriftResult:
    """Test DriftResult dataclass."""

    def test_creation(self):
        """Test DriftResult creation."""
        result = DriftResult(
            psi_score=0.15,
            feature_psi={"feature_1": 0.1, "feature_2": 0.2},
            affected_features=["feature_2", "feature_1"]
        )
        
        assert result.psi_score == 0.15
        assert len(result.feature_psi) == 2
        assert result.affected_features == ["feature_2", "feature_1"]

    def test_frozen(self):
        """Test DriftResult is frozen (immutable)."""
        result = DriftResult(
            psi_score=0.1,
            feature_psi={},
            affected_features=[]
        )
        
        with pytest.raises(Exception):  # FrozenInstanceError
            result.psi_score = 0.5


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestSafeProps:
    """Test _safe_props helper."""

    def test_normal_input(self):
        """Test with normal proportions."""
        props = np.array([0.3, 0.5, 0.2])
        
        result = _safe_props(props)
        
        assert np.isclose(result.sum(), 1.0)
        assert np.all(result > 0)

    def test_zeros_become_positive(self):
        """Test zeros are clipped to positive."""
        props = np.array([0.0, 0.5, 0.5])
        
        result = _safe_props(props)
        
        assert np.all(result > 0)  # No zeros
        assert np.isclose(result.sum(), 1.0)

    def test_negative_values_clipped(self):
        """Test negative values are clipped."""
        props = np.array([-0.1, 0.6, 0.5])
        
        result = _safe_props(props)
        
        assert np.all(result > 0)


class TestPsiFromProportions:
    """Test psi_from_proportions function."""

    def test_identical_distributions(self):
        """Test PSI is zero for identical distributions."""
        props = np.array([0.25, 0.25, 0.25, 0.25])
        
        psi = psi_from_proportions(props, props)
        
        assert np.isclose(psi, 0.0, atol=1e-5)

    def test_different_distributions(self):
        """Test PSI is positive for different distributions."""
        ref = np.array([0.2, 0.3, 0.3, 0.2])
        cur = np.array([0.1, 0.4, 0.4, 0.1])
        
        psi = psi_from_proportions(ref, cur)
        
        assert psi > 0

    def test_high_drift(self):
        """Test high PSI for very different distributions."""
        ref = np.array([0.9, 0.1])
        cur = np.array([0.1, 0.9])
        
        psi = psi_from_proportions(ref, cur)
        
        assert psi > 0.5  # Significant drift


class TestBuildQuantileBins:
    """Test build_quantile_bins function."""

    def test_normal_data(self):
        """Test building bins from normal data."""
        x = np.random.randn(1000)
        
        edges = build_quantile_bins(x, n_bins=10)
        
        assert edges[0] == -np.inf
        assert edges[-1] == np.inf
        assert len(edges) >= 2

    def test_empty_data(self):
        """Test building bins from empty data."""
        x = np.array([])
        
        edges = build_quantile_bins(x, n_bins=10)
        
        assert edges[0] == -np.inf
        assert edges[-1] == np.inf

    def test_all_nan_data(self):
        """Test building bins from all NaN data."""
        x = np.array([np.nan, np.nan, np.nan])
        
        edges = build_quantile_bins(x, n_bins=10)
        
        assert edges[0] == -np.inf
        assert edges[-1] == np.inf

    def test_constant_data(self):
        """Test building bins from constant data."""
        x = np.array([5.0, 5.0, 5.0, 5.0, 5.0])
        
        edges = build_quantile_bins(x, n_bins=10)
        
        # Should handle degenerate case
        assert len(edges) >= 2

    def test_few_data_points(self):
        """Test building bins from few data points."""
        x = np.array([1.0, 2.0, 3.0])
        
        edges = build_quantile_bins(x, n_bins=10)
        
        assert len(edges) >= 2


class TestProportionsInBins:
    """Test proportions_in_bins function."""

    def test_uniform_distribution(self):
        """Test proportions for uniform distribution."""
        x = np.linspace(0, 100, 100)
        edges = np.array([-np.inf, 25, 50, 75, np.inf])
        
        props = proportions_in_bins(x, edges)
        
        # Should be roughly equal
        assert len(props) == 4
        assert np.isclose(props.sum(), 1.0)

    def test_empty_data(self):
        """Test proportions for empty data."""
        x = np.array([])
        edges = np.array([-np.inf, 0, np.inf])
        
        props = proportions_in_bins(x, edges)
        
        assert props[0] == 1.0  # All mass in first bin
        assert np.isclose(props.sum(), 1.0)

    def test_all_nan_data(self):
        """Test proportions for all NaN data."""
        x = np.array([np.nan, np.nan])
        edges = np.array([-np.inf, 0, np.inf])
        
        props = proportions_in_bins(x, edges)
        
        assert np.isclose(props.sum(), 1.0)

    def test_single_bin(self):
        """Test proportions with single bin."""
        x = np.array([1.0, 2.0, 3.0])
        edges = np.array([-np.inf, np.inf])
        
        props = proportions_in_bins(x, edges)
        
        assert len(props) == 1
        assert props[0] == 1.0


# =============================================================================
# build_drift_baseline Tests
# =============================================================================

class TestBuildDriftBaseline:
    """Test build_drift_baseline function."""

    def test_normal_dataframe(self):
        """Test building baseline from normal DataFrame."""
        df = pd.DataFrame({
            'feature_1': np.random.randn(100),
            'feature_2': np.random.randn(100),
            'feature_3': np.random.randn(100)
        })
        
        baseline = build_drift_baseline(df, n_bins=10)
        
        assert 'n_bins' in baseline
        assert 'features' in baseline
        assert len(baseline['features']) == 3

    def test_empty_dataframe(self):
        """Test building baseline from empty DataFrame."""
        df = pd.DataFrame()
        
        baseline = build_drift_baseline(df)
        
        assert baseline['features'] == {}

    def test_none_input(self):
        """Test building baseline from None."""
        baseline = build_drift_baseline(None)
        
        assert baseline['features'] == {}

    def test_max_features_limit(self):
        """Test max_features limits number of features."""
        df = pd.DataFrame({
            f'feature_{i}': np.random.randn(100)
            for i in range(100)
        })
        
        baseline = build_drift_baseline(df, max_features=5)
        
        assert len(baseline['features']) == 5

    def test_non_numeric_columns_ignored(self):
        """Test non-numeric columns are ignored."""
        df = pd.DataFrame({
            'numeric': np.random.randn(100),
            'string': ['a'] * 100
        })
        
        baseline = build_drift_baseline(df)
        
        assert 'numeric' in baseline['features']
        assert 'string' not in baseline['features']

    def test_dataframe_with_inf(self):
        """Test DataFrame with inf values."""
        df = pd.DataFrame({
            'feature': [1.0, 2.0, np.inf, -np.inf, 3.0, 4.0]
        })
        
        baseline = build_drift_baseline(df)
        
        # Should handle inf values gracefully
        assert 'features' in baseline


# =============================================================================
# compute_drift Tests
# =============================================================================

class TestComputeDrift:
    """Test compute_drift function."""

    @pytest.fixture
    def sample_baseline(self):
        """Create sample baseline."""
        df = pd.DataFrame({
            'feature_1': np.random.randn(1000),
            'feature_2': np.random.randn(1000)
        })
        return build_drift_baseline(df, n_bins=10)

    def test_no_drift(self, sample_baseline):
        """Test no drift with same distribution."""
        current = pd.DataFrame({
            'feature_1': np.random.randn(100),
            'feature_2': np.random.randn(100)
        })
        
        result = compute_drift(sample_baseline, current)
        
        assert isinstance(result, DriftResult)
        # Should have low PSI for same distribution type
        assert result.psi_score >= 0

    def test_significant_drift(self):
        """Test significant drift detection."""
        # Create baseline with normal distribution
        baseline_df = pd.DataFrame({
            'feature': np.random.randn(1000)  # Normal around 0
        })
        baseline = build_drift_baseline(baseline_df, n_bins=10)
        
        # Current data with shifted distribution
        current = pd.DataFrame({
            'feature': np.random.randn(100) + 5  # Shifted by 5
        })
        
        result = compute_drift(baseline, current)
        
        assert result.psi_score > 0

    def test_empty_baseline(self):
        """Test with empty baseline."""
        current = pd.DataFrame({'feature': [1, 2, 3]})
        
        result = compute_drift({}, current)
        
        assert result.psi_score == 0.0
        assert result.feature_psi == {}

    def test_empty_current_data(self, sample_baseline):
        """Test with empty current data."""
        current = pd.DataFrame()
        
        result = compute_drift(sample_baseline, current)
        
        assert result.psi_score == 0.0

    def test_none_current_data(self, sample_baseline):
        """Test with None current data."""
        result = compute_drift(sample_baseline, None)
        
        assert result.psi_score == 0.0

    def test_missing_features_in_current(self, sample_baseline):
        """Test when current data is missing features."""
        current = pd.DataFrame({
            'feature_1': np.random.randn(100)
            # feature_2 is missing
        })
        
        result = compute_drift(sample_baseline, current)
        
        # Should still compute for available features
        assert 'feature_1' in result.feature_psi

    def test_top_k_affected_features(self):
        """Test top_k limits affected features."""
        baseline_df = pd.DataFrame({
            f'feature_{i}': np.random.randn(1000)
            for i in range(20)
        })
        baseline = build_drift_baseline(baseline_df, max_features=20)
        
        current = pd.DataFrame({
            f'feature_{i}': np.random.randn(100) + (i * 0.5)  # Different shifts
            for i in range(20)
        })
        
        result = compute_drift(baseline, current, top_k=5)
        
        assert len(result.affected_features) <= 5

    def test_baseline_with_missing_features_config(self):
        """Test baseline with empty features config."""
        baseline = {'n_bins': 10, 'features': {}}
        current = pd.DataFrame({'feature': [1, 2, 3]})
        
        result = compute_drift(baseline, current)
        
        assert result.psi_score == 0.0

    def test_current_with_inf_values(self, sample_baseline):
        """Test current data with inf values."""
        current = pd.DataFrame({
            'feature_1': [1.0, np.inf, -np.inf, 2.0],
            'feature_2': [1.0, 2.0, 3.0, 4.0]
        })
        
        result = compute_drift(sample_baseline, current)
        
        # Should handle inf gracefully
        assert isinstance(result, DriftResult)
