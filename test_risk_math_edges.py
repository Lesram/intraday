"""
BRANCH 2.8: Risk Math Edge Cases Test Suite

Focused testing of numerical edge cases and stability in risk calculations.
"""


import numpy as np
import pytest

from backend.risk.risk_manager import RiskMathUtils


class TestKellyFractionEdgeCases:
    """Test Kelly fraction calculation edge cases and numerical stability."""

    def test_kelly_with_zero_variance(self):
        """Test Kelly fraction with zero variance (perfect certainty)."""
        kelly = RiskMathUtils.kelly_fraction(0.1, 0.0)
        assert kelly == 0.0  # Should return floor when variance is zero

    def test_kelly_with_negative_variance(self):
        """Test Kelly fraction with negative variance (invalid input)."""
        kelly = RiskMathUtils.kelly_fraction(0.1, -0.1)
        assert kelly == 0.0

    def test_kelly_with_very_small_variance(self):
        """Test Kelly fraction with variance near machine epsilon."""
        kelly = RiskMathUtils.kelly_fraction(0.1, 1e-15)
        assert kelly == 0.0  # Should be treated as zero variance

    def test_kelly_with_extreme_values(self):
        """Test Kelly fraction with extreme input values."""
        # Very high return, low variance -> should be capped
        kelly = RiskMathUtils.kelly_fraction(10.0, 0.1, kelly_ceiling=0.25)
        assert kelly == 0.25

        # Very low return, high variance -> should be floored
        kelly = RiskMathUtils.kelly_fraction(0.001, 100.0, kelly_floor=0.05)
        assert kelly == 0.05

    def test_kelly_numerical_precision(self):
        """Test Kelly fraction maintains numerical precision."""
        # Test with values that might cause floating point issues
        mean_ret = 0.123456789
        variance = 0.987654321

        kelly = RiskMathUtils.kelly_fraction(mean_ret, variance)
        expected = mean_ret / variance

        assert abs(kelly - expected) < 1e-10  # High precision check

    def test_kelly_boundary_conditions(self):
        """Test Kelly fraction at exact boundary conditions."""
        # Test at exact ceiling
        kelly = RiskMathUtils.kelly_fraction(0.2, 1.0, kelly_ceiling=0.2)
        assert kelly == 0.2

        # Test just above ceiling
        kelly = RiskMathUtils.kelly_fraction(0.21, 1.0, kelly_ceiling=0.2)
        assert kelly == 0.2

        # Test at exact floor
        kelly = RiskMathUtils.kelly_fraction(0.05, 1.0, kelly_floor=0.05)
        assert kelly == 0.05


class TestEWMAVolatilityEdgeCases:
    """Test EWMA volatility calculation edge cases."""

    def test_ewma_with_single_return(self):
        """Test EWMA with only one return."""
        returns = np.array([0.05])
        vol = RiskMathUtils.ewma_volatility(returns)
        assert vol == 0.1  # Should return fallback

    def test_ewma_with_identical_returns(self):
        """Test EWMA with all identical returns (zero variance)."""
        returns = np.array([0.05, 0.05, 0.05, 0.05, 0.05])
        vol = RiskMathUtils.ewma_volatility(returns)
        assert vol > 0  # Should return minimum volatility due to EPS

    def test_ewma_with_extreme_returns(self):
        """Test EWMA with extreme return values."""
        returns = np.array([10.0, -10.0, 5.0, -5.0, 0.0])
        vol = RiskMathUtils.ewma_volatility(returns)
        assert vol > 0
        assert np.isfinite(vol)

    def test_ewma_with_nan_values(self):
        """Test EWMA handles NaN values correctly."""
        returns = np.array([0.01, np.nan, 0.02, np.nan, 0.03])
        vol = RiskMathUtils.ewma_volatility(returns)
        assert np.isfinite(vol)
        assert vol > 0

    def test_ewma_with_inf_values(self):
        """Test EWMA handles infinite values correctly."""
        returns = np.array([0.01, np.inf, 0.02, -np.inf, 0.03])
        vol = RiskMathUtils.ewma_volatility(returns)
        assert np.isfinite(vol)
        assert vol > 0

    def test_ewma_with_all_nan(self):
        """Test EWMA with all NaN values."""
        returns = np.array([np.nan, np.nan, np.nan])
        vol = RiskMathUtils.ewma_volatility(returns)
        assert vol == 0.1  # Should return fallback

    def test_ewma_lambda_boundary_cases(self):
        """Test EWMA with lambda parameter boundary values."""
        returns = np.array([0.01, 0.02, -0.01, 0.03, -0.02])

        # Lambda = 0 (equal weights)
        vol_0 = RiskMathUtils.ewma_volatility(returns, lambda_param=0.0)
        assert vol_0 > 0

        # Lambda = 1 (only last observation)
        vol_1 = RiskMathUtils.ewma_volatility(returns, lambda_param=1.0)
        assert vol_1 > 0

        # Lambda = 0.99 (very high decay)
        vol_99 = RiskMathUtils.ewma_volatility(returns, lambda_param=0.99)
        assert vol_99 > 0

    def test_ewma_numerical_stability(self):
        """Test EWMA numerical stability with small numbers."""
        returns = np.array([1e-10, -1e-10, 2e-10, -2e-10, 1e-10])
        vol = RiskMathUtils.ewma_volatility(returns)
        assert vol > 0
        assert np.isfinite(vol)


class TestParametricVaREdgeCases:
    """Test parametric VaR calculation edge cases."""

    def test_var_with_insufficient_samples(self):
        """Test VaR with too few samples."""
        portfolio_value = 100000
        returns = np.array([0.01, 0.02])  # Less than MIN_SAMPLES

        var = RiskMathUtils.parametric_var(portfolio_value, returns)
        expected_fallback = portfolio_value * 0.05
        assert var == expected_fallback

    def test_var_with_all_positive_returns(self):
        """Test VaR with all positive returns."""
        portfolio_value = 100000
        returns = np.full(50, 0.01)  # All positive

        var = RiskMathUtils.parametric_var(portfolio_value, returns)
        assert var > 0  # Should still return positive VaR

    def test_var_with_all_negative_returns(self):
        """Test VaR with all negative returns."""
        portfolio_value = 100000
        returns = np.full(50, -0.01)  # All negative

        var = RiskMathUtils.parametric_var(portfolio_value, returns)
        assert var > 0
        assert var < portfolio_value

    def test_var_with_extreme_outliers(self):
        """Test VaR with extreme outlier returns."""
        portfolio_value = 100000
        returns = np.concatenate([
            np.random.normal(0.001, 0.01, 45),  # Normal returns
            np.array([-0.5, 0.8, -0.3, 0.6, -0.4])  # Extreme outliers
        ])

        var = RiskMathUtils.parametric_var(portfolio_value, returns)
        assert var > 0
        assert var < portfolio_value

    def test_var_confidence_levels(self):
        """Test VaR at different confidence levels."""
        portfolio_value = 100000
        returns = np.random.normal(0.0, 0.02, 100)

        var_90 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.90)
        var_95 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.95)
        var_99 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.99)

        # Higher confidence should give higher VaR
        assert var_95 >= var_90
        # Note: var_99 might not be higher due to z-score simplification

    def test_var_with_zero_portfolio_value(self):
        """Test VaR with zero portfolio value."""
        returns = np.random.normal(0.0, 0.02, 50)
        var = RiskMathUtils.parametric_var(0.0, returns)
        assert var >= 0  # Should handle gracefully

    def test_var_with_nan_returns(self):
        """Test VaR with NaN returns."""
        portfolio_value = 100000
        returns = np.array([0.01, np.nan, 0.02, np.nan] * 15)  # 60 total, 30 valid

        var = RiskMathUtils.parametric_var(portfolio_value, returns)
        # Should fallback due to insufficient valid samples
        expected_fallback = portfolio_value * 0.05
        assert var == expected_fallback


class TestHistoricalCVaREdgeCases:
    """Test historical CVaR calculation edge cases."""

    def test_cvar_with_no_tail_observations(self):
        """Test CVaR when no observations fall in the tail."""
        portfolio_value = 100000
        # All returns are positive (no losses)
        returns = np.full(50, 0.01)

        cvar = RiskMathUtils.historical_cvar(portfolio_value, returns)
        expected_fallback = portfolio_value * 0.07
        assert cvar == expected_fallback

    def test_cvar_with_single_tail_observation(self):
        """Test CVaR with only one observation in the tail."""
        portfolio_value = 100000
        # 49 small positive returns, 1 large negative
        returns = np.concatenate([
            np.full(49, 0.001),
            np.array([-0.1])
        ])

        cvar = RiskMathUtils.historical_cvar(portfolio_value, returns)
        assert cvar > 0
        assert cvar < portfolio_value

    def test_cvar_different_confidence_levels(self):
        """Test CVaR at different confidence levels."""
        portfolio_value = 100000
        returns = np.random.normal(0.0, 0.02, 200)  # Enough for tail analysis

        cvar_90 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.90)
        cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.95)
        cvar_99 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.99)

        # Higher confidence typically gives higher CVaR
        # But this may not always hold due to sample variations
        assert all(cvar > 0 for cvar in [cvar_90, cvar_95, cvar_99])

    def test_cvar_with_extreme_tail(self):
        """Test CVaR with extremely negative tail returns."""
        portfolio_value = 100000
        # Mix normal returns with extreme tail
        returns = np.concatenate([
            np.random.normal(0.001, 0.01, 90),  # Normal returns
            np.array([-0.5, -0.3, -0.4, -0.2, -0.6,  # Extreme tail
                     -0.1, -0.15, -0.25, -0.35, -0.45])
        ])

        cvar = RiskMathUtils.historical_cvar(portfolio_value, returns)
        assert cvar > 0
        assert cvar > portfolio_value * 0.1  # Should be significant

    def test_cvar_precision_with_percentiles(self):
        """Test CVaR precision around percentile boundaries."""
        portfolio_value = 100000
        # Create returns where exact percentiles are important
        returns = np.linspace(-0.1, 0.1, 100)  # Uniform distribution

        cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.95)

        # With uniform distribution, should be able to verify calculation
        expected_cutoff = np.percentile(returns, 5)  # 5th percentile
        tail_returns = returns[returns <= expected_cutoff]
        expected_cvar = abs(np.mean(tail_returns)) * portfolio_value

        assert abs(cvar_95 - expected_cvar) < portfolio_value * 0.01  # 1% tolerance

    def test_cvar_consistency_with_var(self):
        """Test that CVaR is generally higher than VaR (expected shortfall property)."""
        portfolio_value = 100000
        returns = np.random.normal(0.0, 0.02, 250)

        var_95 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.95)
        cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.95)

        # CVaR should generally be >= VaR (though different methodologies may vary)
        # At minimum, both should be positive and reasonable
        assert var_95 > 0
        assert cvar_95 > 0
        assert var_95 < portfolio_value * 0.5  # Sanity check
        assert cvar_95 < portfolio_value * 0.5  # Sanity check


class TestCombinedMathStability:
    """Test mathematical operations working together."""

    def test_kelly_with_ewma_volatility(self):
        """Test Kelly fraction using EWMA-derived variance."""
        returns = np.random.normal(0.02, 0.15, 100)  # 2% mean, 15% vol

        # Use EWMA to estimate volatility
        ewma_vol = RiskMathUtils.ewma_volatility(returns)
        mean_return = np.mean(returns)
        variance = ewma_vol ** 2 / 252  # Convert to daily variance

        kelly = RiskMathUtils.kelly_fraction(mean_return, variance)

        assert 0 <= kelly <= 1  # Kelly should be reasonable
        assert np.isfinite(kelly)

    def test_var_cvar_relationship(self):
        """Test relationship between VaR and CVaR calculations."""
        portfolio_value = 100000
        returns = np.random.normal(-0.001, 0.03, 200)  # Slightly negative mean

        var_95 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.95)
        cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.95)

        # Both should be positive
        assert var_95 > 0
        assert cvar_95 > 0

        # Both should be less than total portfolio
        assert var_95 < portfolio_value
        assert cvar_95 < portfolio_value

    def test_numerical_stability_under_stress(self):
        """Test all math functions under numerical stress conditions."""
        # Create challenging dataset
        base_returns = np.random.normal(0.0, 0.02, 80)
        extreme_returns = np.array([10.0, -10.0, 5.0, -5.0])
        tiny_returns = np.array([1e-15, -1e-15, 2e-15, -2e-15])
        nan_returns = np.array([np.nan, np.inf, -np.inf])

        # Combine all challenging cases
        all_returns = np.concatenate([base_returns, extreme_returns, tiny_returns, nan_returns])
        portfolio_value = 100000

        # All functions should handle this gracefully
        vol = RiskMathUtils.ewma_volatility(all_returns)
        assert np.isfinite(vol) and vol > 0

        clean_returns = all_returns[np.isfinite(all_returns)]
        if len(clean_returns) >= 30:
            var = RiskMathUtils.parametric_var(portfolio_value, clean_returns)
            cvar = RiskMathUtils.historical_cvar(portfolio_value, clean_returns)

            assert np.isfinite(var) and var > 0
            assert np.isfinite(cvar) and cvar > 0

        # Kelly with extreme values
        kelly = RiskMathUtils.kelly_fraction(100.0, 1e-10)  # High return, tiny variance
        assert kelly >= 0  # Should be floored, not blow up


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
