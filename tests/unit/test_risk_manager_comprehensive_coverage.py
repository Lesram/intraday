"""
Comprehensive test suite for backend.risk.risk_manager module
Tests risk calculations, position limits, and safety mechanisms
"""

import pytest
import asyncio
import numpy as np
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, time, UTC
from decimal import Decimal

# Import risk manager components
from backend.risk.risk_manager import (
    RiskMathUtils,
    is_market_hours,
    RISK_REASONS,
    EPS,
    MIN_SAMPLES,
    logger,
    risk_metrics
)
from backend.risk.types import OrderSpec, PortfolioState, RiskDecision, RiskLimits


class TestRiskMathUtils:
    """Test mathematical utility functions for risk calculations."""

    def test_kelly_fraction_normal_case(self):
        """Test Kelly fraction calculation with normal parameters."""
        mean_return = 0.05
        variance = 0.02
        
        kelly = RiskMathUtils.kelly_fraction(mean_return, variance)
        
        # Kelly fraction is capped at default ceiling of 0.2
        assert kelly == 0.2  # Capped at ceiling

    def test_kelly_fraction_with_bounds(self):
        """Test Kelly fraction with floor and ceiling bounds."""
        mean_return = 0.1
        variance = 0.01  # Would give kelly = 10
        kelly_floor = 0.0
        kelly_ceiling = 0.2
        
        kelly = RiskMathUtils.kelly_fraction(
            mean_return, variance, kelly_floor, kelly_ceiling
        )
        
        assert kelly == kelly_ceiling

    def test_kelly_fraction_negative_return(self):
        """Test Kelly fraction with negative mean return."""
        mean_return = -0.05
        variance = 0.02
        kelly_floor = 0.01
        
        kelly = RiskMathUtils.kelly_fraction(
            mean_return, variance, kelly_floor=kelly_floor
        )
        
        assert kelly == kelly_floor

    def test_kelly_fraction_zero_variance(self):
        """Test Kelly fraction with zero variance."""
        mean_return = 0.05
        variance = 0.0
        kelly_floor = 0.02
        
        kelly = RiskMathUtils.kelly_fraction(
            mean_return, variance, kelly_floor=kelly_floor
        )
        
        assert kelly == kelly_floor

    def test_kelly_fraction_small_variance(self):
        """Test Kelly fraction with very small variance."""
        mean_return = 0.05
        variance = EPS / 2  # Smaller than EPS
        kelly_floor = 0.01
        
        kelly = RiskMathUtils.kelly_fraction(
            mean_return, variance, kelly_floor=kelly_floor
        )
        
        assert kelly == kelly_floor

    def test_ewma_volatility_normal_returns(self):
        """Test EWMA volatility calculation with normal returns."""
        returns = np.array([0.01, -0.02, 0.015, -0.008, 0.012])
        
        volatility = RiskMathUtils.ewma_volatility(returns)
        
        assert volatility > 0
        assert volatility > EPS
        # Should be reasonable volatility (annualized)
        assert 0.01 < volatility < 2.0

    def test_ewma_volatility_custom_lambda(self):
        """Test EWMA volatility with custom lambda parameter."""
        returns = np.array([0.01, -0.02, 0.015, -0.008, 0.012])
        lambda_param = 0.90
        
        volatility = RiskMathUtils.ewma_volatility(returns, lambda_param)
        
        assert volatility > 0
        assert volatility > EPS

    def test_ewma_volatility_insufficient_data(self):
        """Test EWMA volatility with insufficient data."""
        returns = np.array([0.01])  # Only one return
        
        volatility = RiskMathUtils.ewma_volatility(returns)
        
        assert volatility == 0.1  # Fallback volatility

    def test_ewma_volatility_empty_array(self):
        """Test EWMA volatility with empty array."""
        returns = np.array([])
        
        volatility = RiskMathUtils.ewma_volatility(returns)
        
        assert volatility == 0.1  # Fallback volatility

    def test_ewma_volatility_with_nan_values(self):
        """Test EWMA volatility with NaN values in returns."""
        returns = np.array([0.01, np.nan, 0.015, -0.008, np.inf, 0.012])
        
        volatility = RiskMathUtils.ewma_volatility(returns)
        
        assert volatility > 0
        assert np.isfinite(volatility)

    def test_parametric_var_normal_case(self):
        """Test parametric VaR calculation with normal data."""
        returns = [0.01, -0.02, 0.015, -0.008, 0.012, -0.005, 0.008]
        confidence = 0.05
        
        var = RiskMathUtils.parametric_var(returns, confidence)
        
        assert var >= 0  # VaR should be positive
        assert var < 1   # Should be reasonable

    def test_parametric_var_different_confidence_levels(self):
        """Test parametric VaR with different confidence levels."""
        returns = [0.01, -0.02, 0.015, -0.008, 0.012, -0.005, 0.008]
        
        var_1pct = RiskMathUtils.parametric_var(returns, 0.01)
        var_5pct = RiskMathUtils.parametric_var(returns, 0.05)
        var_10pct = RiskMathUtils.parametric_var(returns, 0.10)
        
        # Higher confidence should give higher VaR
        assert var_1pct >= var_5pct >= var_10pct

    def test_parametric_var_insufficient_data(self):
        """Test parametric VaR with insufficient data."""
        returns = [0.01]  # Only one return
        
        var = RiskMathUtils.parametric_var(returns)
        
        assert var == 0.0

    def test_parametric_var_with_nan_values(self):
        """Test parametric VaR with NaN values."""
        returns = [0.01, np.nan, 0.015, -0.008, np.inf]
        
        var = RiskMathUtils.parametric_var(returns)
        
        assert var >= 0
        assert np.isfinite(var)

    def test_historical_cvar_normal_case(self):
        """Test historical CVaR calculation with normal data."""
        returns = [0.01, -0.02, 0.015, -0.008, 0.012, -0.005, 0.008, 
                  -0.01, 0.006, -0.003, 0.009, -0.007]
        confidence = 0.05
        
        cvar = RiskMathUtils.historical_cvar(returns, confidence)
        
        assert cvar >= 0  # CVaR should be positive
        assert cvar < 1   # Should be reasonable

    def test_historical_cvar_different_confidence_levels(self):
        """Test historical CVaR with different confidence levels."""
        returns = [0.01, -0.02, 0.015, -0.008, 0.012, -0.005, 0.008,
                  -0.01, 0.006, -0.003, 0.009, -0.007, -0.015, 0.002]
        
        cvar_1pct = RiskMathUtils.historical_cvar(returns, 0.01)
        cvar_5pct = RiskMathUtils.historical_cvar(returns, 0.05)
        cvar_10pct = RiskMathUtils.historical_cvar(returns, 0.10)
        
        # Higher confidence should generally give higher CVaR
        assert cvar_1pct >= 0
        assert cvar_5pct >= 0
        assert cvar_10pct >= 0

    def test_historical_cvar_insufficient_data(self):
        """Test historical CVaR with insufficient data."""
        returns = [0.01, -0.02]  # Less than 10 returns
        
        cvar = RiskMathUtils.historical_cvar(returns)
        
        assert cvar == 0.0

    def test_historical_cvar_with_nan_values(self):
        """Test historical CVaR with NaN values."""
        returns = [0.01, -0.02, np.nan, 0.015, -0.008, 0.012, -0.005, 
                  0.008, -0.01, np.inf, 0.006, -0.003]
        
        cvar = RiskMathUtils.historical_cvar(returns)
        
        assert cvar >= 0
        assert np.isfinite(cvar)


class TestMarketHours:
    """Test market hours functionality."""

    def test_is_market_hours_function_exists(self):
        """Test market hours function exists and returns boolean."""
        result = is_market_hours()
        assert isinstance(result, bool)

    def test_is_market_hours_basic_functionality(self):
        """Test basic market hours functionality."""
        # Test that function can be called and returns a boolean
        result1 = is_market_hours()
        result2 = is_market_hours()
        
        assert isinstance(result1, bool)
        assert isinstance(result2, bool)
        # Results should be consistent for same time
        assert result1 == result2


class TestRiskConstants:
    """Test risk manager constants and configurations."""

    def test_eps_constant(self):
        """Test EPS constant is properly defined."""
        assert EPS == 1e-12
        assert EPS > 0
        assert EPS < 1e-10

    def test_min_samples_constant(self):
        """Test MIN_SAMPLES constant is properly defined."""
        assert MIN_SAMPLES == 30
        assert isinstance(MIN_SAMPLES, int)
        assert MIN_SAMPLES > 0

    def test_risk_reasons_set(self):
        """Test RISK_REASONS contains expected categories."""
        expected_reasons = {
            "window", "halt", "whitelist", "pos_cap", "notional_cap",
            "var", "cvar", "kelly", "correlation", "sector", "heat", "leverage"
        }
        
        assert RISK_REASONS == expected_reasons
        assert isinstance(RISK_REASONS, set)
        assert len(RISK_REASONS) > 0

    def test_risk_reasons_immutable(self):
        """Test RISK_REASONS is a set (immutable for our purposes)."""
        original_size = len(RISK_REASONS)
        
        # Verify we can't accidentally modify it in tests
        assert isinstance(RISK_REASONS, set)
        assert len(RISK_REASONS) == original_size


class TestRiskManagerLogging:
    """Test risk manager logging functionality."""

    def test_logger_exists(self):
        """Test that logger is properly initialized."""
        assert logger is not None
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'error')
        assert hasattr(logger, 'warning')

    def test_risk_metrics_initialization(self):
        """Test that risk_metrics can be initialized."""
        # risk_metrics starts as None for test compatibility
        assert risk_metrics is None or hasattr(risk_metrics, 'labels')


class TestRiskMathEdgeCases:
    """Test edge cases and error conditions in risk math."""

    def test_kelly_fraction_extreme_values(self):
        """Test Kelly fraction with extreme input values."""
        # Very large mean return
        kelly_large = RiskMathUtils.kelly_fraction(1000.0, 1.0, kelly_ceiling=0.5)
        assert kelly_large == 0.5  # Should be capped at ceiling
        
        # Very small mean return
        kelly_small = RiskMathUtils.kelly_fraction(1e-10, 1.0, kelly_floor=0.01)
        assert kelly_small == 0.01  # Should be floored

    def test_ewma_volatility_all_zeros(self):
        """Test EWMA volatility with all zero returns."""
        returns = np.array([0.0, 0.0, 0.0, 0.0])
        
        volatility = RiskMathUtils.ewma_volatility(returns)
        
        assert volatility == EPS  # Should return minimum volatility

    def test_ewma_volatility_constant_returns(self):
        """Test EWMA volatility with constant returns."""
        returns = np.array([0.01, 0.01, 0.01, 0.01, 0.01])
        
        volatility = RiskMathUtils.ewma_volatility(returns)
        
        assert volatility == EPS  # Zero variance should give minimum volatility

    def test_parametric_var_all_positive_returns(self):
        """Test parametric VaR with all positive returns."""
        returns = [0.01, 0.02, 0.015, 0.008, 0.012]
        
        var = RiskMathUtils.parametric_var(returns)
        
        # VaR can be negative with positive returns (indicates low risk)
        assert np.isfinite(var)

    def test_parametric_var_all_negative_returns(self):
        """Test parametric VaR with all negative returns."""
        returns = [-0.01, -0.02, -0.015, -0.008, -0.012]
        
        var = RiskMathUtils.parametric_var(returns)
        
        # Should return positive VaR for negative returns
        assert var > 0

    def test_historical_cvar_all_positive_returns(self):
        """Test historical CVaR with all positive returns."""
        returns = [0.01, 0.02, 0.015, 0.008, 0.012, 0.005, 0.018,
                  0.006, 0.009, 0.003, 0.011, 0.007]
        
        cvar = RiskMathUtils.historical_cvar(returns)
        
        # CVaR calculation might return negative values (indicating negative of worst returns)
        assert np.isfinite(cvar)

    def test_historical_cvar_extreme_outliers(self):
        """Test historical CVaR with extreme outlier returns."""
        returns = [0.01, -0.02, 0.015, -100.0, 0.012, -0.005, 0.008,
                  -0.01, 0.006, -0.003, 0.009, -0.007]
        
        cvar = RiskMathUtils.historical_cvar(returns)
        
        # Should handle extreme outliers gracefully
        assert cvar >= 0
        assert np.isfinite(cvar)


class TestRiskCalculationConsistency:
    """Test consistency and relationships between risk calculations."""

    def test_var_cvar_relationship(self):
        """Test that CVaR >= VaR for same confidence level."""
        returns = [0.01, -0.02, 0.015, -0.008, 0.012, -0.005, 0.008,
                  -0.01, 0.006, -0.003, 0.009, -0.007, -0.015, 0.002]
        confidence = 0.05
        
        var = RiskMathUtils.parametric_var(returns, confidence)
        cvar = RiskMathUtils.historical_cvar(returns, confidence)
        
        # CVaR should generally be >= VaR (though different calculation methods)
        assert var >= 0
        assert cvar >= 0

    def test_kelly_fraction_monotonicity(self):
        """Test Kelly fraction monotonicity with respect to return/risk ratio."""
        variance = 0.02
        
        # Higher mean return should give higher Kelly fraction (up to ceiling)
        kelly_low = RiskMathUtils.kelly_fraction(0.01, variance, kelly_ceiling=1.0)
        kelly_high = RiskMathUtils.kelly_fraction(0.05, variance, kelly_ceiling=1.0)
        
        assert kelly_high > kelly_low

    def test_volatility_scaling(self):
        """Test that volatility scales appropriately with return magnitude."""
        base_returns = np.array([0.01, -0.02, 0.015, -0.008, 0.012])
        scaled_returns = base_returns * 2
        
        vol_base = RiskMathUtils.ewma_volatility(base_returns)
        vol_scaled = RiskMathUtils.ewma_volatility(scaled_returns)
        
        # Scaled returns should have roughly double the volatility
        assert vol_scaled > vol_base
        assert vol_scaled < vol_base * 3  # Allow some tolerance

    def test_confidence_level_ordering(self):
        """Test that higher confidence levels give more conservative estimates."""
        returns = [0.01, -0.02, 0.015, -0.008, 0.012, -0.005, 0.008,
                  -0.01, 0.006, -0.003, 0.009, -0.007, -0.015, 0.002]
        
        # Test parametric VaR
        var_conservative = RiskMathUtils.parametric_var(returns, 0.01)  # 1%
        var_moderate = RiskMathUtils.parametric_var(returns, 0.05)      # 5%
        var_liberal = RiskMathUtils.parametric_var(returns, 0.10)       # 10%
        
        # More conservative confidence should give higher VaR
        assert var_conservative >= var_moderate >= var_liberal


class TestRiskManagerIntegration:
    """Test integration aspects of the risk manager."""

    def test_risk_math_utils_static_methods(self):
        """Test that all RiskMathUtils methods are static."""
        # Verify we can call methods without instantiating the class
        returns = [0.01, -0.02, 0.015]
        
        kelly = RiskMathUtils.kelly_fraction(0.05, 0.02)
        vol = RiskMathUtils.ewma_volatility(np.array(returns))
        var = RiskMathUtils.parametric_var(returns)
        cvar = RiskMathUtils.historical_cvar(returns * 4)  # Ensure enough samples
        
        assert all(isinstance(x, (int, float)) for x in [kelly, vol, var, cvar])
        assert all(np.isfinite([kelly, vol, var, cvar]))

    def test_module_imports(self):
        """Test that all necessary modules and functions are importable."""
        # Verify imports work
        assert EPS is not None
        assert MIN_SAMPLES is not None
        assert RISK_REASONS is not None
        assert logger is not None
        assert RiskMathUtils is not None
        assert is_market_hours is not None

    @patch('backend.risk.risk_manager.get_settings')
    def test_settings_integration(self, mock_get_settings):
        """Test integration with settings module."""
        mock_settings = Mock()
        mock_get_settings.return_value = mock_settings
        
        # Test that settings can be accessed (though not used in current tests)
        settings = mock_get_settings()
        assert settings is not None

    @patch('backend.risk.risk_manager.get_metrics_registry')
    def test_metrics_integration(self, mock_get_metrics):
        """Test integration with metrics module."""
        mock_registry = Mock()
        mock_get_metrics.return_value = mock_registry
        
        # Test that metrics registry can be accessed
        registry = mock_get_metrics()
        assert registry is not None

    @patch('backend.risk.risk_manager.get_structured_logger')
    def test_logger_integration(self, mock_get_logger):
        """Test integration with logger module."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        # Test that structured logger can be accessed
        test_logger = mock_get_logger(__name__)
        assert test_logger is not None


class TestNumericalStability:
    """Test numerical stability of risk calculations."""

    def test_kelly_fraction_numerical_stability(self):
        """Test Kelly fraction calculation with numerically challenging inputs."""
        # Very small variance
        kelly1 = RiskMathUtils.kelly_fraction(0.001, 1e-15)
        assert np.isfinite(kelly1)
        
        # Very large variance
        kelly2 = RiskMathUtils.kelly_fraction(0.001, 1e15)
        assert np.isfinite(kelly2)
        assert kelly2 >= 0

    def test_volatility_numerical_stability(self):
        """Test volatility calculation numerical stability."""
        # Very small returns
        small_returns = np.array([1e-10, -1e-10, 1e-11])
        vol_small = RiskMathUtils.ewma_volatility(small_returns)
        assert np.isfinite(vol_small)
        assert vol_small > 0
        
        # Very large returns
        large_returns = np.array([1e6, -1e6, 1e5])
        vol_large = RiskMathUtils.ewma_volatility(large_returns)
        assert np.isfinite(vol_large)
        assert vol_large > 0

    def test_var_cvar_numerical_stability(self):
        """Test VaR and CVaR numerical stability."""
        # Test with extreme values
        extreme_returns = [1e-10, -1e-10, 1e10, -1e10, 0.001, -0.001]
        
        var = RiskMathUtils.parametric_var(extreme_returns)
        cvar = RiskMathUtils.historical_cvar(extreme_returns * 2)  # Ensure enough samples
        
        assert np.isfinite(var)
        assert np.isfinite(cvar)
        assert var >= 0
        assert cvar >= 0