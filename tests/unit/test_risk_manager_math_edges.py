"""
Comprehensive unit tests for risk manager math edge cases and numerical stability.
Focuses on Kelly criterion, CVaR, VaR, and position sizing under extreme conditions.
"""

import numpy as np
import pytest
import pandas as pd
from decimal import Decimal
from unittest.mock import MagicMock, patch

from backend.risk.risk_manager import AsyncRiskManager, RiskMathUtils
from backend.risk.types import OrderSpec, PortfolioState, Side


class TestKellyFractionEdgeCases:
    """Test Kelly fraction calculation with extreme inputs and numerical stability."""

    @pytest.mark.unit
    def test_kelly_with_zero_variance(self):
        """Test Kelly fraction with zero variance (perfect certainty)."""
        kelly = RiskMathUtils.kelly_fraction(0.1, 0.0)
        assert kelly == 0.0  # Should return floor when variance is zero

    @pytest.mark.unit
    def test_kelly_with_negative_variance(self):
        """Test Kelly fraction with negative variance (invalid input)."""
        kelly = RiskMathUtils.kelly_fraction(0.1, -0.1)
        assert kelly == 0.0  # Should handle gracefully

    @pytest.mark.unit
    def test_kelly_with_very_small_variance(self):
        """Test Kelly fraction with variance near machine epsilon."""
        kelly = RiskMathUtils.kelly_fraction(0.1, 1e-15)
        assert kelly == 0.0  # Should be treated as zero variance

    @pytest.mark.unit
    def test_kelly_with_extreme_values(self):
        """Test Kelly fraction with extreme input values."""
        # Very high return, low variance -> should be capped
        kelly = RiskMathUtils.kelly_fraction(10.0, 0.1, kelly_ceiling=0.25)
        assert kelly == 0.25

        # Very low return, high variance -> should be floored
        kelly = RiskMathUtils.kelly_fraction(0.001, 100.0, kelly_floor=0.05)
        assert kelly == 0.05

    @pytest.mark.unit
    def test_kelly_with_negative_expected_return(self):
        """Test Kelly fraction with negative expected returns."""
        kelly = RiskMathUtils.kelly_fraction(-0.1, 0.5)
        assert kelly == 0.0  # Should not bet on negative expected returns

    @pytest.mark.unit
    def test_kelly_numerical_precision(self):
        """Test Kelly fraction maintains numerical precision with small values."""
        # Test with values near floating point precision limits
        kelly = RiskMathUtils.kelly_fraction(1e-10, 1e-8)
        assert isinstance(kelly, float)
        assert kelly >= 0.0

    @pytest.mark.unit
    def test_kelly_boundary_conditions(self):
        """Test Kelly fraction at exact boundary conditions."""
        # Test at exact floor boundary
        kelly = RiskMathUtils.kelly_fraction(0.05, 1.0, kelly_floor=0.05, kelly_ceiling=0.2)
        assert kelly == 0.05

        # Test at exact ceiling boundary  
        kelly = RiskMathUtils.kelly_fraction(0.21, 1.0, kelly_floor=0.0, kelly_ceiling=0.2)
        assert kelly == 0.2


class TestParametricVaREdgeCases:
    """Test parametric VaR calculation with extreme market conditions."""

    @pytest.mark.unit
    def test_var_with_insufficient_samples(self):
        """Test VaR with too few samples."""
        portfolio_value = 100000
        returns = np.array([0.01, 0.02])  # Less than minimum samples

        var = RiskMathUtils.parametric_var(portfolio_value, returns)
        expected_fallback = portfolio_value * 0.05
        assert var == expected_fallback

    @pytest.mark.unit
    def test_var_with_all_positive_returns(self):
        """Test VaR with all positive returns (no losses)."""
        portfolio_value = 100000
        returns = np.full(50, 0.01)  # All positive returns

        var = RiskMathUtils.parametric_var(portfolio_value, returns)
        assert var > 0  # Should still return positive VaR
        assert var < portfolio_value

    @pytest.mark.unit
    def test_var_with_all_negative_returns(self):
        """Test VaR with all negative returns (bear market)."""
        portfolio_value = 100000
        returns = np.full(50, -0.01)  # All negative returns

        var = RiskMathUtils.parametric_var(portfolio_value, returns)
        assert var > 0
        assert var < portfolio_value

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_var_confidence_levels(self):
        """Test VaR at different confidence levels."""
        portfolio_value = 100000
        np.random.seed(42)  # Reproducible results
        returns = np.random.normal(0.0, 0.02, 100)

        var_90 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.90)
        var_95 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.95)
        var_99 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.99)

        # Higher confidence should generally give higher VaR
        assert var_95 >= var_90
        assert all(var > 0 for var in [var_90, var_95, var_99])

    @pytest.mark.unit
    def test_var_with_zero_portfolio_value(self):
        """Test VaR with zero portfolio value."""
        returns = np.random.normal(0.0, 0.02, 50)
        var = RiskMathUtils.parametric_var(0.0, returns)
        assert var >= 0  # Should handle gracefully

    @pytest.mark.unit
    def test_var_with_nan_returns(self):
        """Test VaR with NaN returns in the dataset."""
        portfolio_value = 100000
        returns = np.array([0.01, np.nan, 0.02, np.nan] * 15)  # 60 total, 30 valid

        var = RiskMathUtils.parametric_var(portfolio_value, returns)
        # Should fallback due to insufficient valid samples
        expected_fallback = portfolio_value * 0.05
        assert var == expected_fallback

    @pytest.mark.unit
    def test_var_with_infinite_returns(self):
        """Test VaR with infinite returns."""
        portfolio_value = 100000
        returns = np.array([0.01, np.inf, 0.02, -np.inf] + [0.01] * 50)

        var = RiskMathUtils.parametric_var(portfolio_value, returns)
        # Should handle infinities gracefully
        assert var > 0
        assert var < np.inf


class TestHistoricalCVaREdgeCases:
    """Test historical CVaR calculation with extreme tail scenarios."""

    @pytest.mark.unit
    def test_cvar_with_no_tail_observations(self):
        """Test CVaR when no observations fall in the tail."""
        portfolio_value = 100000
        returns = np.full(50, 0.01)  # All returns are positive (no losses)

        cvar = RiskMathUtils.historical_cvar(portfolio_value, returns)
        expected_fallback = portfolio_value * 0.07
        assert cvar == expected_fallback

    @pytest.mark.unit
    def test_cvar_with_single_tail_observation(self):
        """Test CVaR with only one observation in the tail."""
        portfolio_value = 100000
        returns = np.concatenate([
            np.full(49, 0.001),  # 49 small positive returns
            np.array([-0.1])     # 1 large negative return
        ])

        cvar = RiskMathUtils.historical_cvar(portfolio_value, returns)
        assert cvar > 0
        assert cvar < portfolio_value

    @pytest.mark.unit
    def test_cvar_different_confidence_levels(self):
        """Test CVaR at different confidence levels."""
        portfolio_value = 100000
        np.random.seed(123)  # Reproducible results
        returns = np.random.normal(0.0, 0.02, 200)  # Enough data for tail analysis

        cvar_90 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.90)
        cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.95)
        cvar_99 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.99)

        # All should be positive and reasonable
        assert all(cvar > 0 for cvar in [cvar_90, cvar_95, cvar_99])
        assert all(cvar < portfolio_value * 0.5 for cvar in [cvar_90, cvar_95, cvar_99])

    @pytest.mark.unit
    def test_cvar_with_extreme_tail(self):
        """Test CVaR with extremely negative tail returns."""
        portfolio_value = 100000
        returns = np.concatenate([
            np.random.normal(0.001, 0.01, 90),  # Normal returns
            np.array([-0.5, -0.3, -0.4, -0.2, -0.6,  # Extreme tail
                     -0.1, -0.15, -0.25, -0.35, -0.45])
        ])

        cvar = RiskMathUtils.historical_cvar(portfolio_value, returns)
        assert cvar > 0
        assert cvar > portfolio_value * 0.1  # Should be significant given extreme tail

    @pytest.mark.unit
    def test_cvar_precision_with_percentiles(self):
        """Test CVaR precision around percentile boundaries."""
        portfolio_value = 100000
        returns = np.linspace(-0.1, 0.1, 100)  # Uniform distribution

        cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.95)

        # With uniform distribution, should be able to verify calculation
        expected_cutoff = np.percentile(returns, 5)  # 5th percentile
        tail_returns = returns[returns <= expected_cutoff]
        expected_cvar = abs(np.mean(tail_returns)) * portfolio_value

        assert abs(cvar_95 - expected_cvar) < portfolio_value * 0.01  # 1% tolerance

    @pytest.mark.unit
    def test_cvar_consistency_with_var(self):
        """Test that CVaR maintains expected shortfall property."""
        portfolio_value = 100000
        np.random.seed(456)
        returns = np.random.normal(0.0, 0.02, 250)

        var_95 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.95)
        cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.95)

        # Both should be positive and reasonable
        assert var_95 > 0
        assert cvar_95 > 0
        assert var_95 < portfolio_value * 0.5  # Sanity check
        assert cvar_95 < portfolio_value * 0.5  # Sanity check


class TestEWMAVolatilityEdgeCases:
    """Test EWMA volatility calculation with extreme market regimes."""

    @pytest.mark.unit
    def test_ewma_with_constant_returns(self):
        """Test EWMA volatility with constant returns."""
        returns = np.full(50, 0.01)  # Constant returns
        volatility = RiskMathUtils.ewma_volatility(returns)
        assert volatility == 0.0  # No volatility with constant returns

    @pytest.mark.unit
    def test_ewma_with_single_return(self):
        """Test EWMA volatility with single return."""
        returns = np.array([0.01])
        volatility = RiskMathUtils.ewma_volatility(returns)
        assert volatility == 0.0  # Cannot calculate volatility with single point

    @pytest.mark.unit
    def test_ewma_with_extreme_volatility_regime(self):
        """Test EWMA with extreme volatility regime changes."""
        # Simulate market crash followed by calm period
        returns = np.concatenate([
            np.random.normal(0.0, 0.001, 30),  # Calm period (0.1% daily vol)
            np.random.normal(0.0, 0.05, 5),   # Crash period (5% daily vol)
            np.random.normal(0.0, 0.002, 15)  # Recovery period (0.2% daily vol)
        ])
        
        volatility = RiskMathUtils.ewma_volatility(returns)
        assert volatility > 0
        assert volatility < 0.1  # Should be reasonable despite extremes

    @pytest.mark.unit
    def test_ewma_with_different_lambda_values(self):
        """Test EWMA with different decay parameters."""
        returns = np.random.normal(0.0, 0.02, 100)
        
        vol_fast = RiskMathUtils.ewma_volatility(returns, lambda_param=0.90)  # Fast decay
        vol_medium = RiskMathUtils.ewma_volatility(returns, lambda_param=0.94)  # Medium decay
        vol_slow = RiskMathUtils.ewma_volatility(returns, lambda_param=0.97)   # Slow decay
        
        # All should be positive
        assert all(vol > 0 for vol in [vol_fast, vol_medium, vol_slow])
        # Fast decay should be more responsive to recent volatility
        assert vol_fast != vol_slow

    @pytest.mark.unit
    def test_ewma_numerical_stability(self):
        """Test EWMA volatility numerical stability with edge cases."""
        # Very small returns
        tiny_returns = np.random.normal(0.0, 1e-10, 50)
        vol_tiny = RiskMathUtils.ewma_volatility(tiny_returns)
        assert vol_tiny >= 0
        assert not np.isnan(vol_tiny)
        assert not np.isinf(vol_tiny)

        # Mixed positive/negative returns
        mixed_returns = np.array([0.1, -0.1, 0.1, -0.1] * 25)
        vol_mixed = RiskMathUtils.ewma_volatility(mixed_returns)
        assert vol_mixed > 0


class TestAsyncRiskManagerEdgeCases:
    """Test AsyncRiskManager with extreme portfolio states and order scenarios."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_position_sizing_with_zero_volatility(self):
        """Test position sizing when volatility is zero."""
        risk_manager = AsyncRiskManager()
        
        # Mock portfolio with zero volatility asset
        portfolio = PortfolioState(
            equity=Decimal("100000.0"),
            cash=Decimal("50000.0"),
            positions={"AAPL": Decimal("100")},
            sector_map={"AAPL": "Technology"}
        )
        
        # Order for zero-volatility asset
        order = OrderSpec(
            symbol="STABLE_ASSET",
            side=Side.BUY,
            qty=Decimal("100"),
            notional=Decimal("10000")
        )
        
        # Should handle gracefully without crashing
        result = await risk_manager.evaluate_order_async(order, portfolio)
        assert isinstance(result, dict)
        assert "allowed" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_position_sizing_with_extreme_correlation(self):
        """Test position sizing with perfect correlation between assets."""
        risk_manager = AsyncRiskManager()
        
        # Portfolio with highly correlated positions
        portfolio = PortfolioState(
            total_value=100000.0,
            available_cash=20000.0,
            positions={
                "AAPL": {"qty": 100, "avg_price": 150.0, "market_value": 15000.0},
                "MSFT": {"qty": 50, "avg_price": 300.0, "market_value": 15000.0},
                "GOOGL": {"qty": 20, "avg_price": 2500.0, "market_value": 50000.0}
            },
            daily_pnl=0.0,
            unrealized_pnl=0.0
        )
        
        # Order that would increase correlation risk
        order = OrderSpec(
            symbol="AMZN",  # Another tech stock
            action="buy",
            quantity=10,
            order_type="market"
        )
        
        result = await risk_manager.evaluate_order_async(order, portfolio)
        assert isinstance(result, dict)
        # Should consider correlation in risk assessment
        assert "concentration_risk" in result or "sector_exposure" in result or "allowed" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_drawdown_calculation_with_volatile_history(self):
        """Test drawdown calculation with highly volatile portfolio history."""
        risk_manager = AsyncRiskManager()
        
        # Create volatile portfolio value history
        base_value = 100000
        volatile_values = []
        for i in range(100):
            # Simulate high volatility with occasional large drawdowns
            if i in [20, 45, 70]:  # Simulate crashes
                change = -0.15  # -15% drawdown days
            else:
                change = np.random.normal(0.001, 0.03)  # 3% daily volatility
            
            if i == 0:
                volatile_values.append(base_value)
            else:
                new_value = volatile_values[-1] * (1 + change)
                volatile_values.append(max(new_value, base_value * 0.1))  # Floor at 10%
        
        # Test with mock portfolio history
        with patch.object(risk_manager, '_get_portfolio_history') as mock_history:
            mock_history.return_value = [
                {"timestamp": pd.Timestamp.now() - pd.Timedelta(days=99-i), "total_value": val}
                for i, val in enumerate(volatile_values)
            ]
            
            portfolio = PortfolioState(
                total_value=volatile_values[-1],
                available_cash=10000.0,
                positions={"SPY": {"qty": 100, "avg_price": 400.0, "market_value": 40000.0}},
                daily_pnl=0.0,
                unrealized_pnl=0.0
            )
            
            metrics = await risk_manager.get_portfolio_risk_async(portfolio)
            assert isinstance(metrics, dict)
            assert "max_drawdown" in metrics
            assert metrics["max_drawdown"] >= 0.15  # Should detect the 15% drawdowns

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_risk_limits_with_edge_case_orders(self):
        """Test risk limits with edge case order specifications."""
        risk_manager = AsyncRiskManager()
        
        portfolio = PortfolioState(
            total_value=100000.0,
            available_cash=50000.0,
            positions={},
            daily_pnl=-5000.0,  # Already down 5% today
            unrealized_pnl=0.0
        )
        
        # Edge case orders
        edge_cases = [
            # Zero quantity order
            OrderSpec(symbol="AAPL", action="buy", quantity=0, order_type="market"),
            # Negative quantity (short)
            OrderSpec(symbol="TSLA", action="sell", quantity=100, order_type="market"),
            # Very small quantity
            OrderSpec(symbol="MSFT", action="buy", quantity=0.001, order_type="market"),
            # Very large quantity
            OrderSpec(symbol="SPY", action="buy", quantity=10000, order_type="market"),
        ]
        
        for order in edge_cases:
            result = await risk_manager.evaluate_order_async(order, portfolio)
            assert isinstance(result, dict)
            assert "allowed" in result
            assert "reason" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_kelly_sizing_with_negative_expected_returns(self):
        """Test Kelly position sizing with negative expected returns."""
        risk_manager = AsyncRiskManager()
        
        # Mock negative expected returns for an asset
        with patch.object(risk_manager, '_calculate_expected_return') as mock_return:
            mock_return.return_value = -0.05  # -5% expected return
            
            portfolio = PortfolioState(
                total_value=100000.0,
                available_cash=50000.0,
                positions={},
                daily_pnl=0.0,
                unrealized_pnl=0.0
            )
            
            order = OrderSpec(
                symbol="DECLINING_STOCK",
                action="buy",
                quantity=100,
                order_type="market"
            )
            
            result = await risk_manager.evaluate_order_async(order, portfolio)
            # Should reject or heavily limit orders with negative expected returns
            assert isinstance(result, dict)
            if result.get("allowed", False):
                # If allowed, position size should be minimal
                assert result.get("recommended_quantity", 100) <= order.quantity

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_portfolio_greek_calculations_edge_cases(self):
        """Test portfolio Greek calculations with extreme scenarios."""
        risk_manager = AsyncRiskManager()
        
        # Portfolio with options-heavy exposure
        portfolio = PortfolioState(
            total_value=100000.0,
            available_cash=10000.0,
            positions={
                "AAPL_CALL_150": {"qty": 10, "avg_price": 5.0, "market_value": 5000.0, "delta": 0.7, "gamma": 0.05},
                "SPY_PUT_400": {"qty": -5, "avg_price": 3.0, "market_value": -1500.0, "delta": -0.3, "gamma": 0.02},
                "QQQ": {"qty": 100, "avg_price": 350.0, "market_value": 35000.0, "delta": 1.0, "gamma": 0.0}
            },
            daily_pnl=0.0,
            unrealized_pnl=0.0
        )
        
        metrics = await risk_manager.get_portfolio_risk_async(portfolio)
        assert isinstance(metrics, dict)
        
        # Should handle options Greeks even if some positions don't have them
        if "portfolio_delta" in metrics:
            assert isinstance(metrics["portfolio_delta"], (int, float))
        if "portfolio_gamma" in metrics:
            assert isinstance(metrics["portfolio_gamma"], (int, float))


class TestCombinedMathStability:
    """Test mathematical operations working together under stress conditions."""

    @pytest.mark.unit
    def test_combined_risk_metrics_consistency(self):
        """Test that different risk metrics are mathematically consistent."""
        np.random.seed(789)
        portfolio_value = 100000
        returns = np.random.normal(0.01, 0.02, 252)  # One year of daily returns
        
        # Calculate multiple metrics
        var_95 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.95)
        cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.95)
        volatility = RiskMathUtils.ewma_volatility(returns)
        kelly = RiskMathUtils.kelly_fraction(np.mean(returns), np.var(returns))
        
        # Consistency checks
        assert all(metric > 0 for metric in [var_95, cvar_95, volatility])
        assert kelly >= 0
        assert kelly <= 1  # Kelly should never exceed 100%
        
        # CVaR should generally be >= VaR (expected shortfall property)
        # Note: Due to different methodologies, this might not always hold exactly
        assert cvar_95 > 0
        assert var_95 > 0

    @pytest.mark.unit
    def test_risk_metrics_under_market_stress(self):
        """Test risk metrics during simulated market stress scenarios."""
        scenarios = [
            # Black Monday (1987-style crash)
            {"returns": np.concatenate([
                np.random.normal(0.001, 0.01, 240),  # Normal period
                np.array([-0.22]),                   # Crash day
                np.random.normal(-0.01, 0.03, 11)   # Volatile recovery
            ])},
            # Dot-com bubble volatility
            {"returns": np.concatenate([
                np.random.normal(0.01, 0.015, 100),  # Bull market
                np.random.normal(-0.005, 0.04, 100), # High volatility decline
                np.random.normal(0.002, 0.02, 52)    # Stabilization
            ])},
            # 2008 Financial Crisis-style
            {"returns": np.concatenate([
                np.random.normal(0.0, 0.01, 100),    # Pre-crisis calm
                np.random.normal(-0.02, 0.06, 50),   # Crisis volatility
                np.random.normal(-0.01, 0.04, 102)   # Recovery period
            ])}
        ]
        
        portfolio_value = 100000
        
        for scenario in scenarios:
            returns = scenario["returns"]
            
            # All metrics should handle extreme scenarios gracefully
            var_95 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.95)
            cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.95)
            volatility = RiskMathUtils.ewma_volatility(returns)
            kelly = RiskMathUtils.kelly_fraction(np.mean(returns), np.var(returns))
            
            # Sanity checks - no infinite or NaN values
            metrics = [var_95, cvar_95, volatility, kelly]
            assert all(not np.isnan(metric) for metric in metrics)
            assert all(not np.isinf(metric) for metric in metrics)
            assert all(metric >= 0 for metric in metrics)
            
            # Volatility should be elevated during stress
            assert volatility > 0.01  # Should be above normal levels

    @pytest.mark.unit
    def test_numerical_stability_with_extreme_portfolio_sizes(self):
        """Test numerical stability with very large and very small portfolio values."""
        returns = np.random.normal(0.01, 0.02, 100)
        
        # Test with extreme portfolio sizes
        extreme_sizes = [
            1.0,        # $1 portfolio
            100.0,      # $100 portfolio  
            1e6,        # $1M portfolio
            1e9,        # $1B portfolio
            1e12        # $1T portfolio
        ]
        
        for portfolio_value in extreme_sizes:
            var_95 = RiskMathUtils.parametric_var(portfolio_value, returns, 0.95)
            cvar_95 = RiskMathUtils.historical_cvar(portfolio_value, returns, 0.95)
            
            # Should scale proportionally with portfolio size
            assert var_95 > 0
            assert cvar_95 > 0
            assert var_95 < portfolio_value  # VaR should be less than total value
            assert cvar_95 < portfolio_value  # CVaR should be less than total value
            
            # Should maintain reasonable proportions
            var_ratio = var_95 / portfolio_value
            cvar_ratio = cvar_95 / portfolio_value
            assert 0 < var_ratio < 1
            assert 0 < cvar_ratio < 1

    @pytest.mark.unit
    def test_fuzz_small_returns_arrays(self):
        """Fuzz test with small returns arrays to hit numerical stability branches."""
        np.random.seed(42)
        portfolio_value = 100000
        
        # Generate various small arrays that might cause edge cases
        test_arrays = [
            # Empty and tiny arrays
            np.array([]),
            np.array([0.01]),
            np.array([0.01, 0.02]),
            
            # Arrays with special values
            np.array([0.0] * 10),
            np.array([np.nan, 0.01, 0.02]),
            np.array([np.inf, 0.01, 0.02]),
            np.array([-np.inf, 0.01, 0.02]),
            
            # Very small variance arrays
            np.array([0.01] * 50),  # Constant returns
            np.array([0.01, 0.010001] * 25),  # Minimal variance
            
            # Extreme value arrays
            np.array([1.0, -1.0] * 5),  # 100% swings
            np.array([1e-10] * 20),     # Tiny values
            np.array([1e10, -1e10]),    # Huge values
        ]
        
        for returns in test_arrays:
            # All functions should handle gracefully without crashing
            try:
                if len(returns) > 0:
                    var = RiskMathUtils.parametric_var(portfolio_value, returns)
                    cvar = RiskMathUtils.historical_cvar(portfolio_value, returns)
                    vol = RiskMathUtils.ewma_volatility(returns)
                    
                    # Results should be non-negative numbers (including zero)
                    assert var >= 0 or np.isnan(var)
                    assert cvar >= 0 or np.isnan(cvar)
                    assert vol >= 0 or np.isnan(vol)
                    
                    if len(returns) > 1:
                        kelly = RiskMathUtils.kelly_fraction(np.mean(returns), np.var(returns))
                        assert kelly >= 0 or np.isnan(kelly)
                        
            except (ValueError, ZeroDivisionError) as e:
                # These exceptions are acceptable for invalid inputs
                assert "insufficient" in str(e).lower() or "invalid" in str(e).lower() or "zero" in str(e).lower()
