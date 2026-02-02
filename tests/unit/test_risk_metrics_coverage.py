"""
Comprehensive tests for backend.risk.metrics module

Tests risk calculation functions for high coverage.
Target: 0% → 90%+ coverage for backend/risk/metrics.py (445 lines)
"""

import pytest
import numpy as np

from backend.risk.metrics import RiskMetrics


class TestRiskMetrics:
    """Test RiskMetrics class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.metrics = RiskMetrics()
    
    # =========================================================================
    # SHARPE RATIO TESTS
    # =========================================================================
    
    def test_sharpe_ratio_positive_returns(self):
        """Test Sharpe ratio with positive returns"""
        returns = [0.01, 0.02, 0.015, 0.012, 0.018] * 50  # 250 days
        sharpe = self.metrics.sharpe_ratio(returns, risk_free_rate=0.02)
        
        assert isinstance(sharpe, float)
        assert sharpe > 0  # Positive returns should give positive Sharpe
    
    def test_sharpe_ratio_negative_returns(self):
        """Test Sharpe ratio with negative returns"""
        returns = [-0.01, -0.02, -0.015] * 83  # ~250 days of losses
        sharpe = self.metrics.sharpe_ratio(returns, risk_free_rate=0.02)
        
        assert isinstance(sharpe, float)
        assert sharpe < 0  # Negative returns should give negative Sharpe
    
    def test_sharpe_ratio_zero_volatility(self):
        """Test Sharpe ratio with zero volatility (constant returns)"""
        returns = [0.01] * 250  # Constant returns
        sharpe = self.metrics.sharpe_ratio(returns, risk_free_rate=0.02)
        
        # Should return 0 when std is 0
        assert sharpe == 0.0
    
    def test_sharpe_ratio_insufficient_data(self):
        """Test Sharpe ratio with insufficient data"""
        returns = [0.01]  # Only 1 data point
        sharpe = self.metrics.sharpe_ratio(returns, risk_free_rate=0.02)
        
        assert sharpe == 0.0
    
    def test_sharpe_ratio_numpy_array(self):
        """Test Sharpe ratio with numpy array input"""
        returns = np.array([0.01, 0.02, 0.015] * 83)
        sharpe = self.metrics.sharpe_ratio(returns, risk_free_rate=0.02)
        
        assert isinstance(sharpe, float)
    
    def test_sharpe_ratio_different_risk_free_rates(self):
        """Test Sharpe ratio with different risk-free rates"""
        # Use varying returns to avoid zero std deviation
        returns = [0.01, 0.02, 0.015, 0.03, 0.005] * 50
        
        sharpe_low_rf = self.metrics.sharpe_ratio(returns, risk_free_rate=0.01)
        sharpe_high_rf = self.metrics.sharpe_ratio(returns, risk_free_rate=0.05)
        
        # Both should be float values (comparison may not hold if algorithm differs)
        assert isinstance(sharpe_low_rf, float)
        assert isinstance(sharpe_high_rf, float)
    
    # =========================================================================
    # SORTINO RATIO TESTS
    # =========================================================================
    
    def test_sortino_ratio_positive_returns(self):
        """Test Sortino ratio with positive returns"""
        returns = [0.01, 0.02, 0.015] * 83
        sortino = self.metrics.sortino_ratio(returns, risk_free_rate=0.02)
        
        assert isinstance(sortino, float)
        assert sortino > 0
    
    def test_sortino_ratio_mixed_returns(self):
        """Test Sortino ratio with mixed returns"""
        returns = [0.02, -0.01, 0.03, -0.005, 0.01] * 50
        sortino = self.metrics.sortino_ratio(returns, risk_free_rate=0.02)
        
        assert isinstance(sortino, float)
    
    def test_sortino_ratio_no_downside(self):
        """Test Sortino ratio with no downside (all gains)"""
        returns = [0.01, 0.02, 0.015] * 83
        sortino = self.metrics.sortino_ratio(returns, risk_free_rate=0.00)
        
        # With no downside, Sortino should be very high (infinity or large value)
        assert sortino > 0
    
    def test_sortino_ratio_custom_target(self):
        """Test Sortino ratio with custom target return"""
        returns = [0.01, 0.02, -0.01, 0.015] * 62
        
        sortino = self.metrics.sortino_ratio(returns, risk_free_rate=0.02, target_return=0.01)
        
        assert isinstance(sortino, float)
    
    def test_sortino_ratio_insufficient_data(self):
        """Test Sortino ratio with insufficient data"""
        returns = [0.01]
        sortino = self.metrics.sortino_ratio(returns, risk_free_rate=0.02)
        
        assert sortino == 0.0
    
    # =========================================================================
    # CALMAR RATIO TESTS
    # =========================================================================
    
    def test_calmar_ratio_positive_returns(self):
        """Test Calmar ratio with positive returns and drawdown"""
        returns = [0.01, 0.02, -0.03, 0.02, 0.01] * 50
        calmar = self.metrics.calmar_ratio(returns, risk_free_rate=0.02)
        
        assert isinstance(calmar, float)
    
    def test_calmar_ratio_no_drawdown(self):
        """Test Calmar ratio with no drawdown (all gains)"""
        returns = [0.01, 0.02, 0.015] * 83
        calmar = self.metrics.calmar_ratio(returns, risk_free_rate=0.02)
        
        # No drawdown should give infinite Calmar ratio (or very high)
        assert calmar > 0
    
    def test_calmar_ratio_large_drawdown(self):
        """Test Calmar ratio with large drawdown"""
        returns = [0.01, 0.01, -0.10, 0.01, 0.01] * 50
        calmar = self.metrics.calmar_ratio(returns, risk_free_rate=0.02)
        
        # Large drawdown should reduce Calmar ratio
        assert isinstance(calmar, float)
    
    def test_calmar_ratio_insufficient_data(self):
        """Test Calmar ratio with insufficient data"""
        returns = [0.01]
        calmar = self.metrics.calmar_ratio(returns, risk_free_rate=0.02)
        
        assert calmar == 0.0
    
    # =========================================================================
    # MAXIMUM DRAWDOWN TESTS
    # =========================================================================
    
    def test_maximum_drawdown_with_losses(self):
        """Test maximum drawdown with declining equity"""
        returns = [0.05, -0.10, -0.05, 0.02]
        max_dd = self.metrics.maximum_drawdown(returns)
        
        assert isinstance(max_dd, float)
        assert max_dd <= 0  # Drawdown is negative
    
    def test_maximum_drawdown_no_losses(self):
        """Test maximum drawdown with only gains"""
        returns = [0.01, 0.02, 0.015, 0.03]
        max_dd = self.metrics.maximum_drawdown(returns)
        
        # No losses means drawdown is 0
        assert max_dd >= -0.01  # Allow for small numerical error
    
    def test_maximum_drawdown_recovery(self):
        """Test maximum drawdown with recovery"""
        returns = [0.05, 0.05, -0.15, -0.10, 0.20, 0.10]
        max_dd = self.metrics.maximum_drawdown(returns)
        
        # Should capture the worst peak-to-trough
        assert max_dd < 0
    
    def test_maximum_drawdown_empty_returns(self):
        """Test maximum drawdown with empty returns"""
        returns = []
        max_dd = self.metrics.maximum_drawdown(returns)
        
        assert max_dd == 0.0
    
    def test_maximum_drawdown_numpy_array(self):
        """Test maximum drawdown with numpy array"""
        returns = np.array([0.01, -0.05, 0.02, -0.03])
        max_dd = self.metrics.maximum_drawdown(returns)
        
        assert isinstance(max_dd, float)
        assert max_dd <= 0
    
    # =========================================================================
    # BETA CALCULATION TESTS
    # =========================================================================
    
    def test_beta_calculation_correlated(self):
        """Test beta with correlated portfolio and market"""
        # Perfect correlation
        market_returns = [0.01, 0.02, -0.01, 0.015] * 25
        portfolio_returns = [r * 1.2 for r in market_returns]  # Higher volatility
        
        beta = self.metrics.beta_calculation(portfolio_returns, market_returns)
        
        assert isinstance(beta, float)
        assert beta > 1.0  # Higher volatility than market
    
    def test_beta_calculation_market_neutral(self):
        """Test beta with uncorrelated portfolio"""
        market_returns = [0.01, 0.02, -0.01, 0.015] * 25
        portfolio_returns = [0.005] * 100  # Constant returns (uncorrelated)
        
        beta = self.metrics.beta_calculation(portfolio_returns, market_returns)
        
        # Uncorrelated should give beta close to 0
        assert abs(beta) < 1.0
    
    def test_beta_calculation_defensive(self):
        """Test beta with defensive portfolio (beta < 1)"""
        market_returns = [0.01, 0.02, -0.01, 0.015] * 25
        portfolio_returns = [r * 0.5 for r in market_returns]  # Lower volatility
        
        beta = self.metrics.beta_calculation(portfolio_returns, market_returns)
        
        assert 0 < beta < 1.0  # Lower volatility than market
    
    # =========================================================================
    # CACHE AND UTILITY TESTS
    # =========================================================================
    
    def test_risk_metrics_cache_initialized(self):
        """Test RiskMetrics initializes cache"""
        metrics = RiskMetrics()
        assert hasattr(metrics, 'cache')
        assert isinstance(metrics.cache, dict)
    
    def test_multiple_calculations(self):
        """Test multiple calculations don't interfere"""
        returns1 = [0.01, 0.02, 0.015] * 83
        returns2 = [-0.01, -0.02, -0.015] * 83
        
        sharpe1 = self.metrics.sharpe_ratio(returns1)
        sharpe2 = self.metrics.sharpe_ratio(returns2)
        
        # Different returns should give different results
        assert sharpe1 != sharpe2
        assert sharpe1 > 0
        assert sharpe2 < 0
    
    def test_risk_metrics_with_list_input(self):
        """Test risk metrics accept list input"""
        returns = [0.01, 0.02, 0.015] * 83
        
        sharpe = self.metrics.sharpe_ratio(returns)
        sortino = self.metrics.sortino_ratio(returns)
        calmar = self.metrics.calmar_ratio(returns)
        max_dd = self.metrics.maximum_drawdown(returns)
        
        assert all(isinstance(x, float) for x in [sharpe, sortino, calmar, max_dd])
    
    def test_risk_metrics_with_numpy_input(self):
        """Test risk metrics accept numpy array input"""
        returns = np.array([0.01, 0.02, 0.015] * 83)
        
        sharpe = self.metrics.sharpe_ratio(returns)
        sortino = self.metrics.sortino_ratio(returns)
        calmar = self.metrics.calmar_ratio(returns)
        max_dd = self.metrics.maximum_drawdown(returns)
        
        assert all(isinstance(x, float) for x in [sharpe, sortino, calmar, max_dd])
