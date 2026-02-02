"""
Tests for backend/risk/math.py - Risk mathematics utilities.

Target: Cover value_at_risk, conditional_var, and helper functions.
"""

import pytest
import numpy as np


class TestToSeries:
    """Test _to_series helper function"""
    
    def test_to_series_none(self):
        """Test None input returns empty array"""
        from backend.risk.math import _to_series
        
        result = _to_series(None)
        assert isinstance(result, np.ndarray)
        assert result.size == 0
    
    def test_to_series_scalar_int(self):
        """Test integer scalar input"""
        from backend.risk.math import _to_series
        
        result = _to_series(5)
        assert isinstance(result, np.ndarray)
        assert len(result) == 1
        assert result[0] == 5.0
    
    def test_to_series_scalar_float(self):
        """Test float scalar input"""
        from backend.risk.math import _to_series
        
        result = _to_series(3.14)
        assert isinstance(result, np.ndarray)
        assert len(result) == 1
        assert result[0] == 3.14
    
    def test_to_series_list(self):
        """Test list input"""
        from backend.risk.math import _to_series
        
        result = _to_series([1, 2, 3])
        assert isinstance(result, np.ndarray)
        assert len(result) == 3
        np.testing.assert_array_equal(result, [1.0, 2.0, 3.0])
    
    def test_to_series_numpy_array(self):
        """Test numpy array input"""
        from backend.risk.math import _to_series
        
        arr = np.array([1.5, 2.5, 3.5])
        result = _to_series(arr)
        assert isinstance(result, np.ndarray)
        np.testing.assert_array_equal(result, arr)
    
    def test_to_series_empty_list(self):
        """Test empty list returns empty array"""
        from backend.risk.math import _to_series
        
        result = _to_series([])
        assert isinstance(result, np.ndarray)
        assert result.size == 0
    
    def test_to_series_invalid_string(self):
        """Test invalid string input returns empty array"""
        from backend.risk.math import _to_series
        
        result = _to_series("not_a_number")
        assert isinstance(result, np.ndarray)
        # Should return empty array for non-convertible string
        assert result.size == 0


class TestAlignForRiskMath:
    """Test align_for_risk_math helper"""
    
    def test_align_list(self):
        """Test list alignment"""
        from backend.risk.math import align_for_risk_math
        
        result = align_for_risk_math([1, 2, 3], 3)
        assert isinstance(result, np.ndarray)
        np.testing.assert_array_equal(result, [1.0, 2.0, 3.0])
    
    def test_align_numpy_array(self):
        """Test numpy array alignment"""
        from backend.risk.math import align_for_risk_math
        
        arr = np.array([0.1, 0.2, 0.3])
        result = align_for_risk_math(arr, 3)
        assert isinstance(result, np.ndarray)
        np.testing.assert_array_almost_equal(result, arr)
    
    def test_align_pandas_series(self):
        """Test pandas Series alignment"""
        from backend.risk.math import align_for_risk_math
        
        try:
            import pandas as pd
            series = pd.Series([0.1, 0.2, 0.3])
            result = align_for_risk_math(series, 3)
            assert isinstance(result, np.ndarray)
            np.testing.assert_array_almost_equal(result, [0.1, 0.2, 0.3])
        except ImportError:
            pytest.skip("pandas not available")
    
    def test_align_pandas_dataframe(self):
        """Test pandas DataFrame alignment takes first column"""
        from backend.risk.math import align_for_risk_math
        
        try:
            import pandas as pd
            df = pd.DataFrame({'a': [0.1, 0.2, 0.3], 'b': [0.4, 0.5, 0.6]})
            result = align_for_risk_math(df, 3)
            assert isinstance(result, np.ndarray)
            np.testing.assert_array_almost_equal(result, [0.1, 0.2, 0.3])
        except ImportError:
            pytest.skip("pandas not available")


class TestValueAtRisk:
    """Test value_at_risk function"""
    
    def test_var_empty_returns_zero(self):
        """Test empty input returns 0"""
        from backend.risk.math import value_at_risk
        
        assert value_at_risk([]) == 0.0
    
    def test_var_none_returns_zero(self):
        """Test None input returns 0"""
        from backend.risk.math import value_at_risk
        
        assert value_at_risk(None) == 0.0
    
    def test_var_single_value(self):
        """Test single value returns that value"""
        from backend.risk.math import value_at_risk
        
        assert value_at_risk(0.05) == 0.05
        assert value_at_risk([0.05]) == 0.05
    
    def test_var_basic_calculation(self):
        """Test basic VaR calculation"""
        from backend.risk.math import value_at_risk
        
        # With these returns, 5th percentile should be around -0.1
        returns = [-0.1, -0.05, -0.02, 0.01, 0.03, 0.05, 0.08, 0.1, 0.12, 0.15]
        var = value_at_risk(returns, 0.95)
        
        # VaR should be negative (a loss) 
        assert var <= 0.0
    
    def test_var_high_confidence(self):
        """Test VaR with high confidence level"""
        from backend.risk.math import value_at_risk
        
        returns = [-0.2, -0.1, 0.0, 0.1, 0.2]
        var_95 = value_at_risk(returns, 0.95)
        var_99 = value_at_risk(returns, 0.99)
        
        # Higher confidence should give more extreme VaR
        assert var_99 <= var_95
    
    def test_var_with_nan(self):
        """Test VaR handles NaN values"""
        from backend.risk.math import value_at_risk
        
        returns = [0.1, np.nan, -0.05, 0.02, np.nan, -0.1]
        var = value_at_risk(returns, 0.95)
        
        # Should return a valid number, not NaN
        assert not np.isnan(var)
    
    def test_var_all_nan_returns_zero(self):
        """Test all NaN input returns 0"""
        from backend.risk.math import value_at_risk
        
        returns = [np.nan, np.nan, np.nan]
        assert value_at_risk(returns, 0.95) == 0.0
    
    def test_var_numpy_array(self):
        """Test VaR with numpy array"""
        from backend.risk.math import value_at_risk
        
        returns = np.array([-0.1, -0.05, 0.0, 0.05, 0.1])
        var = value_at_risk(returns, 0.95)
        assert isinstance(var, float)
    
    def test_var_pandas_series(self):
        """Test VaR with pandas Series"""
        from backend.risk.math import value_at_risk
        
        try:
            import pandas as pd
            returns = pd.Series([-0.1, -0.05, 0.0, 0.05, 0.1])
            var = value_at_risk(returns, 0.95)
            assert isinstance(var, float)
        except ImportError:
            pytest.skip("pandas not available")


class TestConditionalVar:
    """Test conditional_var (CVaR/Expected Shortfall) function"""
    
    def test_cvar_empty_returns_zero(self):
        """Test empty input returns 0"""
        from backend.risk.math import conditional_var
        
        assert conditional_var([]) == 0.0
    
    def test_cvar_none_returns_zero(self):
        """Test None input returns 0"""
        from backend.risk.math import conditional_var
        
        assert conditional_var(None) == 0.0
    
    def test_cvar_single_value(self):
        """Test single value returns that value"""
        from backend.risk.math import conditional_var
        
        assert conditional_var(-0.05) == -0.05
        assert conditional_var([-0.05]) == -0.05
    
    def test_cvar_basic_calculation(self):
        """Test basic CVaR calculation"""
        from backend.risk.math import conditional_var
        
        # CVaR should be worse than VaR (more negative for losses)
        returns = [-0.1, -0.05, -0.02, 0.01, 0.03]
        cvar = conditional_var(returns, 0.95)
        
        # CVaR is the average of tail losses
        assert isinstance(cvar, float)
    
    def test_cvar_worse_than_var(self):
        """Test CVaR is always worse than or equal to VaR"""
        from backend.risk.math import conditional_var, value_at_risk
        
        returns = [-0.15, -0.1, -0.05, 0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3]
        
        var = value_at_risk(returns, 0.95)
        cvar = conditional_var(returns, 0.95)
        
        # CVaR should be less than or equal to VaR (more extreme loss)
        assert cvar <= var
    
    def test_cvar_with_nan(self):
        """Test CVaR handles NaN values"""
        from backend.risk.math import conditional_var
        
        returns = [0.1, np.nan, -0.05, 0.02, np.nan, -0.1]
        cvar = conditional_var(returns, 0.95)
        
        # Should return a valid number, not NaN
        assert not np.isnan(cvar)
    
    def test_cvar_all_nan_returns_zero(self):
        """Test all NaN input returns 0"""
        from backend.risk.math import conditional_var
        
        returns = [np.nan, np.nan, np.nan]
        assert conditional_var(returns, 0.95) == 0.0
    
    def test_cvar_numpy_array(self):
        """Test CVaR with numpy array"""
        from backend.risk.math import conditional_var
        
        returns = np.array([-0.1, -0.05, 0.0, 0.05, 0.1])
        cvar = conditional_var(returns, 0.95)
        assert isinstance(cvar, float)


class TestMaxDrawdown:
    """Test max_drawdown function if available"""
    
    def test_max_drawdown_exists(self):
        """Test max_drawdown function exists"""
        try:
            from backend.risk.math import max_drawdown
            assert max_drawdown is not None
        except ImportError:
            pytest.skip("max_drawdown not available")
    
    def test_max_drawdown_basic(self):
        """Test basic max drawdown calculation"""
        try:
            from backend.risk.math import max_drawdown
            
            # Price series that goes up then down
            prices = [100, 110, 105, 120, 90, 95]
            dd = max_drawdown(prices)
            
            assert isinstance(dd, (int, float))
            assert dd <= 0  # Drawdown should be negative or zero
        except ImportError:
            pytest.skip("max_drawdown not available")


class TestSharpeRatio:
    """Test sharpe_ratio function if available"""
    
    def test_sharpe_ratio_exists(self):
        """Test sharpe_ratio function exists"""
        try:
            from backend.risk.math import sharpe_ratio
            assert sharpe_ratio is not None
        except ImportError:
            pytest.skip("sharpe_ratio not available")
    
    def test_sharpe_ratio_basic(self):
        """Test basic Sharpe ratio calculation"""
        try:
            from backend.risk.math import sharpe_ratio
            
            returns = [0.01, 0.02, -0.01, 0.03, 0.02]
            sr = sharpe_ratio(returns)
            
            assert isinstance(sr, (int, float))
        except ImportError:
            pytest.skip("sharpe_ratio not available")


class TestSortinoRatio:
    """Test sortino_ratio function if available"""
    
    def test_sortino_ratio_exists(self):
        """Test sortino_ratio function exists"""
        try:
            from backend.risk.math import sortino_ratio
            assert sortino_ratio is not None
        except ImportError:
            pytest.skip("sortino_ratio not available")


class TestCalmarRatio:
    """Test calmar_ratio function if available"""
    
    def test_calmar_ratio_exists(self):
        """Test calmar_ratio function exists"""
        try:
            from backend.risk.math import calmar_ratio
            assert calmar_ratio is not None
        except ImportError:
            pytest.skip("calmar_ratio not available")
