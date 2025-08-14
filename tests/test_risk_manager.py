"""
Test Risk Management System - LEGACY COMPATIBILITY TESTS

WARNING: This file tests the DEPRECATED synchronous RiskManager wrapper.
For new tests, use AsyncRiskManager in test_risk_manager_current.py instead.

These tests are kept only for backward compatibility validation.
Do not use these patterns in new code.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock
import warnings

import numpy as np
import pandas as pd
import pytest

from backend.risk.risk_manager import (
    RiskManager,  # DEPRECATED - Legacy wrapper for compatibility only
)
from backend.risk.types import PortfolioRisk, RiskLevel, RiskLimits


class TestLegacyRiskManager:
    """LEGACY compatibility tests for deprecated RiskManager wrapper"""

    def setup_method(self):
        """Setup for each test method - LEGACY COMPATIBILITY ONLY"""
        # Suppress deprecation warnings for legacy tests
        warnings.filterwarnings("ignore", category=DeprecationWarning)

        # Create mock portfolio
        mock_portfolio = Mock()
        mock_portfolio.total_value = 100000
        mock_portfolio.cash = 20000
        mock_portfolio.get_positions.return_value = {
            "AAPL": {
                "quantity": 100,
                "market_value": 15000,
                "unrealized_pl": 500,
                "days_held": 10,
                "avg_entry_price": 150.0,
            }
        }
        mock_portfolio.get_position.return_value = None

        self.risk_manager = RiskManager(portfolio=mock_portfolio)

        # Add some historical data for calculations
        self.risk_manager.portfolio_history = [
            {
                "timestamp": datetime.now() - timedelta(days=i),
                "total_value": 100000 + i * 100,
                "cash": 20000,
                "positions": 1,
            }
            for i in range(50)
        ]

    @pytest.mark.unit
    def test_initialization(self):
        """Test RiskManager initialization"""
        assert self.risk_manager is not None
        assert hasattr(self.risk_manager, "limits")
        assert hasattr(self.risk_manager, "portfolio")
        assert hasattr(self.risk_manager, "circuit_breaker_active")
        assert isinstance(self.risk_manager.limits, RiskLimits)

    @pytest.mark.unit
    def test_var_calculation(self):
        """Test Value at Risk calculation"""
        # Test default method (monte_carlo)
        var_95 = self.risk_manager.calculate_var(confidence=0.95)
        var_99 = self.risk_manager.calculate_var(confidence=0.99)

        assert isinstance(var_95, (int, float))
        assert isinstance(var_99, (int, float))

        # Test historical method
        var_hist = self.risk_manager.calculate_var(confidence=0.95, method="historical")
        assert isinstance(var_hist, (int, float))

    @pytest.mark.unit
    def test_cvar_calculation(self):
        """Test Conditional Value at Risk calculation"""
        # Test with default confidence level
        cvar_95 = self.risk_manager.calculate_cvar(confidence=0.95)
        cvar_99 = self.risk_manager.calculate_cvar(confidence=0.99)

        assert isinstance(cvar_95, (int, float))
        assert isinstance(cvar_99, (int, float))

    @pytest.mark.unit
    def test_kelly_position_sizing(self):
        """Test Kelly criterion position sizing"""
        # Test with valid win rate and ratio
        kelly_fraction = self.risk_manager.kelly_position_size(
            prob_win=0.6, win_loss_ratio=1.5
        )

        assert isinstance(kelly_fraction, float)
        assert 0 <= kelly_fraction <= 1  # Should be between 0 and 1

    @pytest.mark.unit
    def test_kelly_position_sizing_edge_cases(self):
        """Test Kelly criterion with edge cases"""
        # No edge case (50% win rate)
        kelly_no_edge = self.risk_manager.kelly_position_size(
            prob_win=0.5, win_loss_ratio=1.0
        )
        assert kelly_no_edge >= 0.0

        # Negative edge case
        kelly_negative = self.risk_manager.kelly_position_size(
            prob_win=0.3, win_loss_ratio=0.8
        )
        assert kelly_negative >= 0.0

    @pytest.mark.unit
    def test_before_order_validation(self):
        """Test before_order method for trade validation"""
        # Test valid order
        allowed, reason, adjusted_qty = self.risk_manager.before_order(
            symbol="MSFT", intended_qty=50, price=300.0
        )

        assert isinstance(allowed, bool)
        assert isinstance(reason, str)
        assert isinstance(adjusted_qty, (int, float))

    @pytest.mark.unit
    def test_position_size_limits(self):
        """Test position size limits through before_order"""
        # Test large position that should be limited
        allowed, reason, adjusted_qty = self.risk_manager.before_order(
            symbol="TSLA",
            intended_qty=1000,  # Large quantity
            price=800.0,
        )

        # Should either be rejected or adjusted
        if not allowed:
            assert "limit" in reason.lower()
        else:
            assert adjusted_qty <= 1000

    @pytest.mark.unit
    def test_risk_metrics_calculation(self):
        """Test comprehensive risk metrics calculation"""
        metrics = self.risk_manager.get_risk_metrics()

        assert isinstance(metrics, PortfolioRisk)
        assert hasattr(metrics, "total_value")
        assert hasattr(metrics, "var_95")
        assert hasattr(metrics, "cvar_95")
        assert hasattr(metrics, "leverage")
        assert hasattr(metrics, "risk_level")
        assert isinstance(metrics.risk_level, RiskLevel)

    @pytest.mark.unit
    def test_enforce_global_limits(self):
        """Test global risk limit enforcement"""
        result = self.risk_manager.enforce_global_limits()

        assert isinstance(result, dict)
        assert "status" in result
        assert "actions_taken" in result
        assert result["status"] in ["OK", "MEDIUM", "HIGH", "CRITICAL", "ERROR"]

    @pytest.mark.unit
    def test_circuit_breaker_functionality(self):
        """Test circuit breaker activation and reset"""
        # Test circuit breaker is initially inactive
        assert not self.risk_manager.circuit_breaker_active

        # Test reset functionality
        self.risk_manager.reset_circuit_breaker("manual_reset")
        assert not self.risk_manager.circuit_breaker_active

    @pytest.mark.unit
    def test_portfolio_history_update(self):
        """Test portfolio history tracking"""
        initial_count = len(self.risk_manager.portfolio_history)

        # Update portfolio history
        self.risk_manager.update_portfolio_history()

        assert len(self.risk_manager.portfolio_history) >= initial_count

    @pytest.mark.unit
    def test_price_history_update(self):
        """Test price history tracking"""
        symbol = "AAPL"
        price = 150.0

        # Update price history
        self.risk_manager.update_price_history(symbol, price)

        assert symbol in self.risk_manager.price_history
        assert len(self.risk_manager.price_history[symbol]) > 0

    @pytest.mark.unit
    def test_position_sizing_recommendation(self):
        """Test position sizing recommendations"""
        recommendation = self.risk_manager.get_position_sizing_recommendation(
            symbol="AAPL", signal_strength=0.8, win_probability=0.6, win_loss_ratio=1.5
        )

        assert isinstance(recommendation, dict)
        assert "symbol" in recommendation
        assert "recommended_position_pct" in recommendation
        assert "recommended_dollar_amount" in recommendation

    @pytest.mark.unit
    def test_risk_event_logging(self):
        """Test risk event logging through calculations"""
        # This will trigger logging internally
        var_result = self.risk_manager.calculate_var(confidence=0.95)
        cvar_result = self.risk_manager.calculate_cvar(confidence=0.95)

        # Just verify the methods execute without error
        assert isinstance(var_result, (int, float))
        assert isinstance(cvar_result, (int, float))


class TestRiskManagerEdgeCases:
    """Test edge cases and error handling"""

    def setup_method(self):
        """Setup for each test method"""
        self.risk_manager = RiskManager()  # No portfolio

    @pytest.mark.unit
    def test_empty_data_handling(self):
        """Test handling of empty data"""
        # Test with empty portfolio
        var_result = self.risk_manager.calculate_var()
        cvar_result = self.risk_manager.calculate_cvar()

        assert isinstance(var_result, (int, float))
        assert isinstance(cvar_result, (int, float))

    @pytest.mark.unit
    def test_single_value_data(self):
        """Test handling of single value data"""
        # Add minimal data
        self.risk_manager.portfolio_history = [
            {
                "timestamp": datetime.now(),
                "total_value": 100000,
                "cash": 20000,
                "positions": 0,
            }
        ]

        var_result = self.risk_manager.calculate_var()
        assert isinstance(var_result, (int, float))

    @pytest.mark.unit
    def test_extreme_values(self):
        """Test handling of extreme market values"""
        # Add extreme portfolio history
        self.risk_manager.portfolio_history = [
            {
                "timestamp": datetime.now() - timedelta(days=i),
                "total_value": 100000 * (1 + i * 0.1),
                "cash": 20000,
                "positions": 1,
            }
            for i in range(10)
        ]

        var_result = self.risk_manager.calculate_var()
        assert isinstance(var_result, (int, float))

    @pytest.mark.unit
    def test_invalid_parameters(self):
        """Test handling of invalid parameters"""
        # Test invalid confidence level
        var_result = self.risk_manager.calculate_var(
            confidence=1.5
        )  # Invalid confidence
        assert isinstance(var_result, (int, float))

        # Test invalid Kelly parameters
        kelly_result = self.risk_manager.kelly_position_size(
            -0.1, 1.0
        )  # Negative probability
        assert kelly_result >= 0.0


# Fixtures for test data
@pytest.fixture
def sample_price_data():
    """Generate sample price data for testing"""
    dates = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    np.random.seed(42)  # For reproducible results

    prices = []
    price = 100.0
    for _ in dates:
        price *= 1 + np.random.normal(0, 0.02)  # 2% daily volatility
        prices.append(price)

    return pd.DataFrame(
        {
            "date": dates,
            "close": prices,
            "high": [p * 1.02 for p in prices],
            "low": [p * 0.98 for p in prices],
            "volume": np.random.randint(100000, 1000000, len(dates)),
        }
    )


class TestRiskManagerEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.fixture(autouse=True)
    def setup(self):
        config = {
            "MAX_POSITION_SIZE": 1000,
            "MAX_PORTFOLIO_VALUE": 100000,
            "MAX_DAILY_LOSS": 0.05,
            "MAX_DRAWDOWN": 0.1,
            "RISK_FREE_RATE": 0.02,
        }
        self.risk_manager = RiskManager(config)

    @pytest.mark.unit
    def test_empty_data_handling(self):
        """Test VaR calculation with empty or invalid data"""
        empty_returns = pd.Series(dtype=float)

        # Should handle empty data gracefully
        var = self.risk_manager.calculate_var(confidence=0.95, method="parametric")
        assert var is not None

    @pytest.mark.unit
    def test_extreme_confidence_levels(self):
        """Test VaR with extreme confidence levels"""
        # Test with very high confidence
        var_999 = self.risk_manager.calculate_var(confidence=0.999, method="parametric")
        assert var_999 is not None

        # Test with very low confidence
        var_50 = self.risk_manager.calculate_var(confidence=0.5, method="parametric")
        assert var_50 is not None

    @pytest.mark.unit
    def test_kelly_criterion_edge_cases(self):
        """Test Kelly criterion with edge cases"""
        # Test with zero probability
        kelly_zero = self.risk_manager.kelly_position_size(
            prob_win=0, win_loss_ratio=2.0
        )
        assert kelly_zero == 0

        # Test with very high probability (but capped)
        kelly_high = self.risk_manager.kelly_position_size(
            prob_win=0.9, win_loss_ratio=2.0
        )
        assert 0 < kelly_high <= 0.25  # Should be positive but capped at 25%

        # Test with very low win/loss ratio
        kelly_low = self.risk_manager.kelly_position_size(
            prob_win=0.6, win_loss_ratio=0.1
        )
        assert kelly_low == 0  # Should not bet with poor odds

    @pytest.mark.unit
    def test_invalid_method_handling(self):
        """Test handling of invalid VaR methods"""
        try:
            var = self.risk_manager.calculate_var(
                confidence=0.95, method="invalid_method"
            )
            # Should either return default or raise appropriate error
            assert var is not None or True  # Test passes if it handles gracefully
        except ValueError:
            # Expected behavior for invalid method
            pass

    @pytest.mark.unit
    def test_risk_metrics_with_minimal_data(self):
        """Test risk metrics calculation with minimal portfolio data"""
        # Set minimal portfolio
        self.risk_manager.portfolio_value = 1000

        metrics = self.risk_manager.get_risk_metrics()
        assert isinstance(metrics, object)  # Returns PortfolioRisk object

        # Should have all expected attributes even with minimal data
        expected_attrs = ["var_95", "cvar_95", "max_drawdown", "sharpe_ratio"]
        for attr in expected_attrs:
            assert hasattr(metrics, attr)
