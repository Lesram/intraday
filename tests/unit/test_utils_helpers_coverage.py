"""
Comprehensive tests for backend.utils.helpers module

Tests all utility functions for financial calculations, data processing, and helpers.
Target: 0% → 90%+ coverage for backend/utils/helpers.py (498 lines)
"""

import pytest
import numpy as np
import pandas as pd
from decimal import Decimal

from backend.utils.helpers import (
    align_for_pandas_arithmetic,
    calculate_returns,
    calculate_sharpe_ratio,
    calculate_max_drawdown,
    calculate_var,
)


class TestAlignForPandasArithmetic:
    """Test align_for_pandas_arithmetic function"""
    
    def test_align_scalar(self):
        """Test aligning scalar value"""
        index = pd.Index([0, 1, 2])
        result = align_for_pandas_arithmetic(5, index)
        assert isinstance(result, pd.Series)
        assert len(result) == 3
        assert all(result == 5)
    
    def test_align_list(self):
        """Test aligning list"""
        index = pd.Index([0, 1, 2])
        result = align_for_pandas_arithmetic([1, 2, 3], index)
        assert isinstance(result, pd.Series)
        assert len(result) == 3
        assert list(result) == [1, 2, 3]
    
    def test_align_series(self):
        """Test aligning pandas Series"""
        index = pd.Index([0, 1, 2])
        series = pd.Series([10, 20, 30], index=index)
        result = align_for_pandas_arithmetic(series, index)
        assert isinstance(result, pd.Series)
        assert len(result) == 3
        pd.testing.assert_series_equal(result, series)
    
    def test_align_dataframe(self):
        """Test aligning DataFrame (uses first column)"""
        index = pd.Index([0, 1, 2])
        df = pd.DataFrame({'col': [10, 20, 30]}, index=index)
        result = align_for_pandas_arithmetic(df, index)
        assert isinstance(result, pd.Series)
        assert len(result) == 3
    
    def test_align_list_too_long(self):
        """Test aligning list longer than index"""
        index = pd.Index([0, 1, 2])
        result = align_for_pandas_arithmetic([1, 2, 3, 4, 5], index)
        assert len(result) == 3
        assert list(result) == [1, 2, 3]  # Truncated
    
    def test_align_list_too_short(self):
        """Test aligning list shorter than index"""
        index = pd.Index([0, 1, 2, 3, 4])
        result = align_for_pandas_arithmetic([1, 2], index)
        assert len(result) == 5
        # Should pad with last value
        assert list(result) == [1, 2, 2, 2, 2]
    
    def test_align_empty_list(self):
        """Test aligning empty list"""
        index = pd.Index([0, 1, 2])
        result = align_for_pandas_arithmetic([], index)
        assert len(result) == 3
        # Should pad with zeros
        assert all(result == 0)
    
    def test_align_numpy_array(self):
        """Test aligning numpy array"""
        index = pd.Index([0, 1, 2])
        arr = np.array([10, 20, 30])
        result = align_for_pandas_arithmetic(arr, index)
        assert isinstance(result, pd.Series)
        assert len(result) == 3
        assert list(result) == [10, 20, 30]
    
    def test_align_tuple(self):
        """Test aligning tuple"""
        index = pd.Index([0, 1, 2])
        result = align_for_pandas_arithmetic((5, 10, 15), index)
        assert isinstance(result, pd.Series)
        assert list(result) == [5, 10, 15]
    
    def test_align_int_float(self):
        """Test aligning int and float scalars"""
        index = pd.Index([0, 1, 2])
        
        result_int = align_for_pandas_arithmetic(42, index)
        assert all(result_int == 42)
        
        result_float = align_for_pandas_arithmetic(3.14, index)
        assert all(result_float == 3.14)


class TestCalculateReturns:
    """Test calculate_returns function"""
    
    def test_simple_returns_series(self):
        """Test simple returns calculation with pandas Series"""
        prices = pd.Series([100, 110, 105, 115])
        returns = calculate_returns(prices, method="simple")
        
        assert isinstance(returns, pd.Series)
        assert len(returns) == 4
        assert pd.isna(returns.iloc[0])  # First value is NaN
        assert abs(returns.iloc[1] - 0.10) < 0.001  # 10% gain
        assert abs(returns.iloc[2] - (-0.0454)) < 0.01  # ~4.54% loss
        assert abs(returns.iloc[3] - 0.0952) < 0.01  # ~9.52% gain
    
    def test_log_returns_series(self):
        """Test log returns calculation with pandas Series"""
        prices = pd.Series([100, 110, 105, 115])
        returns = calculate_returns(prices, method="log")
        
        assert isinstance(returns, pd.Series)
        assert len(returns) == 4
        assert pd.isna(returns.iloc[0])
        # Log returns should be slightly less than simple returns
        assert returns.iloc[1] < 0.10
    
    def test_simple_returns_array(self):
        """Test simple returns with numpy array"""
        prices = np.array([100, 110, 105, 115])
        returns = calculate_returns(prices, method="simple")
        
        assert isinstance(returns, np.ndarray)
        assert len(returns) == 3  # One less than input
        assert abs(returns[0] - 0.10) < 0.001
    
    def test_log_returns_array(self):
        """Test log returns with numpy array"""
        prices = np.array([100, 110, 105, 115])
        returns = calculate_returns(prices, method="log")
        
        assert isinstance(returns, np.ndarray)
        assert len(returns) == 3
    
    def test_returns_all_same_prices(self):
        """Test returns when prices don't change"""
        prices = pd.Series([100, 100, 100, 100])
        returns = calculate_returns(prices, method="simple")
        
        # All returns should be 0 (except first NaN)
        assert returns.iloc[1:].sum() == 0


class TestCalculateSharpeRatio:
    """Test calculate_sharpe_ratio function"""
    
    def test_sharpe_ratio_positive_returns(self):
        """Test Sharpe ratio with positive returns"""
        returns = pd.Series([0.01, 0.02, 0.015, 0.012, 0.018] * 50)  # 250 days
        sharpe = calculate_sharpe_ratio(returns, risk_free_rate=0.02)
        
        assert isinstance(sharpe, float)
        assert sharpe > 0  # Should be positive with positive returns
    
    def test_sharpe_ratio_negative_returns(self):
        """Test Sharpe ratio with negative returns"""
        returns = pd.Series([-0.01, -0.02, -0.015] * 83)  # ~250 days
        sharpe = calculate_sharpe_ratio(returns, risk_free_rate=0.02)
        
        assert isinstance(sharpe, float)
        assert sharpe < 0  # Should be negative
    
    def test_sharpe_ratio_numpy_array(self):
        """Test Sharpe ratio with numpy array"""
        returns = np.array([0.01, 0.02, 0.015, 0.012, 0.018] * 50)
        sharpe = calculate_sharpe_ratio(returns, risk_free_rate=0.02)
        
        assert isinstance(sharpe, float)
        assert not np.isnan(sharpe)
    
    def test_sharpe_ratio_zero_volatility(self):
        """Test Sharpe ratio with zero volatility (constant returns)"""
        returns = pd.Series([0.01] * 250)
        sharpe = calculate_sharpe_ratio(returns, risk_free_rate=0.02)
        
        # Should return 0 when std is 0 (avoid division by zero)
        assert sharpe == 0
    
    def test_sharpe_ratio_high_volatility(self):
        """Test Sharpe ratio with high volatility"""
        # Alternating large gains/losses
        returns = pd.Series([0.05, -0.04, 0.06, -0.03] * 62)  # ~250 days
        sharpe = calculate_sharpe_ratio(returns)
        
        # High volatility should reduce Sharpe ratio
        assert abs(sharpe) < 5
    
    def test_sharpe_ratio_different_risk_free_rates(self):
        """Test Sharpe ratio with different risk-free rates"""
        # Use varying returns to avoid zero std deviation
        returns = pd.Series([0.01, 0.02, 0.015, 0.03, 0.005] * 50)
        
        sharpe_low = calculate_sharpe_ratio(returns, risk_free_rate=0.01)
        sharpe_high = calculate_sharpe_ratio(returns, risk_free_rate=0.05)
        
        # Both should be float values 
        assert isinstance(sharpe_low, (int, float))
        assert isinstance(sharpe_high, (int, float))


class TestCalculateMaxDrawdown:
    """Test calculate_max_drawdown function"""
    
    def test_max_drawdown_declining_equity(self):
        """Test max drawdown with declining equity"""
        equity = pd.Series([10000, 9500, 9000, 8500, 8000])
        drawdown = calculate_max_drawdown(equity)
        
        assert isinstance(drawdown, float)
        assert drawdown < 0  # Drawdown is negative
        assert abs(drawdown) > 0.19  # Should be around -20%
    
    def test_max_drawdown_growing_equity(self):
        """Test max drawdown with growing equity (no drawdown)"""
        equity = pd.Series([10000, 11000, 12000, 13000, 14000])
        drawdown = calculate_max_drawdown(equity)
        
        # No drawdown when equity only grows
        assert drawdown == 0
    
    def test_max_drawdown_with_recovery(self):
        """Test max drawdown with decline and recovery"""
        equity = pd.Series([10000, 12000, 9000, 11000, 13000])
        drawdown = calculate_max_drawdown(equity)
        
        assert drawdown < 0
        # Max drawdown should be from 12000 to 9000 = -25%
        assert abs(drawdown + 0.25) < 0.01
    
    def test_max_drawdown_numpy_array(self):
        """Test max drawdown with numpy array"""
        equity = np.array([10000, 9500, 9000, 9500, 10000])
        drawdown = calculate_max_drawdown(equity)
        
        assert isinstance(drawdown, float)
        assert drawdown < 0
    
    def test_max_drawdown_flat_equity(self):
        """Test max drawdown with flat equity"""
        equity = pd.Series([10000] * 10)
        drawdown = calculate_max_drawdown(equity)
        
        # No drawdown when equity is constant
        assert drawdown == 0
    
    def test_max_drawdown_single_large_drop(self):
        """Test max drawdown with one large drop"""
        equity = pd.Series([10000, 10000, 5000, 5000, 5000])
        drawdown = calculate_max_drawdown(equity)
        
        # Should capture 50% drawdown
        assert abs(drawdown + 0.5) < 0.01


class TestCalculateVaR:
    """Test calculate_var function"""
    
    def test_var_normal_returns(self):
        """Test VaR with normally distributed returns"""
        # Create normally distributed returns
        np.random.seed(42)
        returns = pd.Series(np.random.normal(0.001, 0.02, 1000))
        
        var = calculate_var(returns, confidence=0.95)
        
        assert isinstance(var, float)
        assert var < 0  # VaR is typically negative (loss)
    
    def test_var_different_confidence_levels(self):
        """Test VaR with different confidence levels"""
        returns = pd.Series([-0.01, -0.02, 0.01, 0.02, -0.015] * 100)
        
        var_90 = calculate_var(returns, confidence=0.90)
        var_95 = calculate_var(returns, confidence=0.95)
        var_99 = calculate_var(returns, confidence=0.99)
        
        # Higher confidence should give larger (more negative) VaR
        assert var_99 <= var_95 <= var_90
    
    def test_var_numpy_array(self):
        """Test VaR with numpy array"""
        returns = np.array([-0.01, -0.02, 0.01, 0.02, -0.015] * 100)
        var = calculate_var(returns, confidence=0.95)
        
        assert isinstance(var, float)
    
    def test_var_all_positive_returns(self):
        """Test VaR with all positive returns"""
        returns = pd.Series([0.01, 0.02, 0.015, 0.018, 0.012] * 100)
        var = calculate_var(returns, confidence=0.95)
        
        # VaR might be positive or small negative with only gains
        assert var < 0.05
    
    def test_var_all_negative_returns(self):
        """Test VaR with all negative returns"""
        returns = pd.Series([-0.01, -0.02, -0.015, -0.018] * 100)
        var = calculate_var(returns, confidence=0.95)
        
        # VaR should be significantly negative
        assert var < -0.01
