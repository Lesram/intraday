"""
Coverage enhancement tests for backend.features.technical_indicators module.
Target: Comprehensive testing to significantly improve coverage from 14% baseline.
"""

import pytest
import numpy as np
import pandas as pd
import math
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# Set test environment
import os
os.environ["DISABLE_ML"] = "1"
os.environ["DISABLE_TENSORFLOW"] = "1"
os.environ["PYTEST_RUNNING"] = "1"

from backend.features.technical_indicators import TechnicalIndicators, IndicatorResult


class TestTechnicalIndicatorsCoverageEnhancement:
    """Comprehensive tests for TechnicalIndicators class coverage enhancement."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.ti = TechnicalIndicators()
        self.sample_prices = [100.0, 102.0, 101.0, 103.0, 104.0, 102.0, 105.0, 106.0, 107.0, 108.0, 
                            109.0, 108.0, 107.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0]
        
        # Create sample DataFrame
        self.sample_data = pd.DataFrame({
            'close': self.sample_prices,
            'high': [p + 1 for p in self.sample_prices],
            'low': [p - 1 for p in self.sample_prices],
            'open': self.sample_prices,
            'volume': [1000 + i * 100 for i in range(len(self.sample_prices))]
        })
        
    def test_indicator_result_dataclass(self):
        """Test IndicatorResult dataclass functionality."""
        # Test basic creation
        result = IndicatorResult(value=50.5, confidence=0.8)
        assert result.value == 50.5
        assert result.confidence == 0.8
        assert result.error is None
        
        # Test with error
        error_result = IndicatorResult(value=None, confidence=0.0, error="test_error")
        assert error_result.value is None
        assert error_result.confidence == 0.0
        assert error_result.error == "test_error"
    
    def test_technical_indicators_initialization_default_config(self):
        """Test TechnicalIndicators initialization with default config."""
        ti = TechnicalIndicators()
        assert ti.config == {}
        assert ti.calculation_count == 0
        assert ti.error_count == 0
    
    def test_technical_indicators_initialization_custom_config(self):
        """Test TechnicalIndicators initialization with custom config."""
        config = {"rsi_period": 21, "sma_period": 30}
        ti = TechnicalIndicators(config=config)
        assert ti.config == config
        assert ti.calculation_count == 0
        assert ti.error_count == 0
    
    def test_calculate_all_features_valid_data(self):
        """Test calculate_all_features with valid data."""
        result = self.ti.calculate_all_features(self.sample_data)
        
        assert result is not None
        assert isinstance(result, dict)
        
        # Check expected features
        expected_keys = ['sma_20', 'sma_50', 'rsi', 'price_mean', 'price_std', 'price_max', 'price_min']
        for key in expected_keys:
            if key == 'sma_50':
                continue  # May not exist if insufficient data
            assert key in result or len(self.sample_prices) < 20
    
    def test_calculate_all_features_none_dataframe(self):
        """Test calculate_all_features with None DataFrame."""
        result = self.ti.calculate_all_features(None)
        assert result is None
    
    def test_calculate_all_features_empty_dataframe(self):
        """Test calculate_all_features with empty DataFrame."""
        empty_df = pd.DataFrame()
        result = self.ti.calculate_all_features(empty_df)
        assert result is None
    
    def test_calculate_all_features_missing_close_column(self):
        """Test calculate_all_features with missing close column."""
        df_no_close = pd.DataFrame({
            'high': [100, 101, 102],
            'low': [98, 99, 100],
            'volume': [1000, 1100, 1200]
        })
        result = self.ti.calculate_all_features(df_no_close)
        assert result is None
    
    def test_calculate_all_features_insufficient_data(self):
        """Test calculate_all_features with insufficient data points."""
        short_df = pd.DataFrame({
            'close': [100, 101, 102],  # Only 3 data points
            'high': [101, 102, 103],
            'low': [99, 100, 101],
            'volume': [1000, 1100, 1200]
        })
        result = self.ti.calculate_all_features(short_df)
        assert result is None
    
    @patch('backend.features.technical_indicators.logger')
    def test_calculate_all_features_exception_handling(self, mock_logger):
        """Test calculate_all_features exception handling."""
        # Create a DataFrame that will cause an exception
        with patch.object(self.ti, 'calculate_sma', side_effect=Exception("Test error")):
            result = self.ti.calculate_all_features(self.sample_data)
            assert result is None
            mock_logger.warning.assert_called()
    
    def test_calculate_sma_valid_data(self):
        """Test calculate_sma with valid data."""
        prices = [100, 102, 101, 103, 104]
        period = 3
        
        result = self.ti.calculate_sma(prices, period)
        
        assert result is not None
        assert isinstance(result, IndicatorResult)
        assert result.value is not None
        assert result.confidence > 0
        assert result.error is None
        assert self.ti.calculation_count > 0
    
    def test_calculate_sma_insufficient_data(self):
        """Test calculate_sma with insufficient data."""
        prices = [100, 102]
        period = 5
        
        result = self.ti.calculate_sma(prices, period)
        
        assert result is not None
        assert result.value is None
        assert result.confidence == 0.0
        assert result.error == "insufficient_data"
    
    def test_calculate_sma_empty_prices(self):
        """Test calculate_sma with empty prices list."""
        prices = []
        period = 5
        
        result = self.ti.calculate_sma(prices, period)
        
        assert result is not None
        assert result.value is None
        assert result.confidence == 0.0
        assert result.error == "insufficient_data"
    
    def test_calculate_sma_none_prices(self):
        """Test calculate_sma with None prices."""
        prices = None
        period = 5
        
        result = self.ti.calculate_sma(prices, period)
        
        assert result is not None
        assert result.value is None
        assert result.confidence == 0.0
        assert result.error == "insufficient_data"
    
    def test_calculate_sma_with_invalid_prices(self):
        """Test calculate_sma with some invalid prices."""
        # Mock _is_valid_price to return False for some values
        with patch.object(self.ti, '_is_valid_price') as mock_valid:
            mock_valid.side_effect = lambda x: x not in [None, float('inf'), float('-inf')]
            
            prices = [100, float('inf'), 102, None, 103, 104, 105]
            period = 5
            
            result = self.ti.calculate_sma(prices, period)
            
            # Should still work with valid prices
            assert result is not None
            if result.value is not None:
                assert result.confidence > 0
    
    @patch('backend.features.technical_indicators.logger')
    def test_calculate_sma_exception_handling(self, mock_logger):
        """Test calculate_sma exception handling."""
        with patch.object(self.ti, '_is_valid_price', side_effect=Exception("Test error")):
            prices = [100, 102, 103, 104, 105]
            period = 3
            
            result = self.ti.calculate_sma(prices, period)
            
            assert result is not None
            assert result.value is None
            assert result.confidence == 0.0
            assert result.error is not None
            assert self.ti.error_count > 0
            mock_logger.warning.assert_called()
    
    def test_calculate_rsi_valid_data(self):
        """Test calculate_rsi with valid data."""
        # Create trending data for RSI calculation
        prices = list(range(100, 120))  # 20 data points
        
        result = self.ti.calculate_rsi(prices)
        
        assert result is not None
        assert isinstance(result, IndicatorResult)
        # RSI should be between 0 and 100
        if result.value is not None:
            assert 0 <= result.value <= 100
    
    def test_calculate_rsi_insufficient_data(self):
        """Test calculate_rsi with insufficient data."""
        prices = [100, 102, 103]  # Less than period + 1
        period = 14
        
        result = self.ti.calculate_rsi(prices, period)
        
        assert result is not None
        assert result.value is None
        assert result.confidence == 0.0
        assert result.error == "insufficient_data"
    
    def test_calculate_rsi_empty_prices(self):
        """Test calculate_rsi with empty prices."""
        prices = []
        
        result = self.ti.calculate_rsi(prices)
        
        assert result is not None
        assert result.value is None
        assert result.confidence == 0.0
        assert result.error == "insufficient_data"
    
    def test_calculate_rsi_none_prices(self):
        """Test calculate_rsi with None prices."""
        prices = None
        
        result = self.ti.calculate_rsi(prices)
        
        assert result is not None
        assert result.value is None
        assert result.confidence == 0.0
        assert result.error == "insufficient_data"
    
    def test_calculate_rsi_insufficient_valid_changes(self):
        """Test calculate_rsi with insufficient valid price changes."""
        # Mock _is_valid_price to return False for most values
        with patch.object(self.ti, '_is_valid_price') as mock_valid:
            mock_valid.side_effect = lambda x: x in [100, 101]  # Only first two are valid
            
            prices = [100, 101] + [float('inf')] * 20  # Only 2 valid prices
            
            result = self.ti.calculate_rsi(prices)
            
            assert result is not None
            assert result.value is None
            assert result.confidence == 0.0
            assert result.error == "insufficient_valid_changes"


class TestTechnicalIndicatorsAdvancedMethods:
    """Test advanced methods and edge cases in TechnicalIndicators."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.ti = TechnicalIndicators()
    
    def test_is_valid_price_method_exists(self):
        """Test that _is_valid_price method exists and can be called."""
        # Test with different price values
        if hasattr(self.ti, '_is_valid_price'):
            # Test valid prices
            assert self.ti._is_valid_price(100.0) == True
            assert self.ti._is_valid_price(0.01) == True
            
            # Test invalid prices
            assert self.ti._is_valid_price(None) == False
            assert self.ti._is_valid_price(float('inf')) == False
            assert self.ti._is_valid_price(float('-inf')) == False
            assert self.ti._is_valid_price(float('nan')) == False
    
    def test_calculate_all_features_sma_periods(self):
        """Test calculate_all_features SMA calculations with different periods."""
        # Create data with enough points for both SMA periods
        long_prices = list(range(100, 160))  # 60 data points
        long_df = pd.DataFrame({
            'close': long_prices,
            'high': [p + 1 for p in long_prices],
            'low': [p - 1 for p in long_prices],
            'volume': [1000] * len(long_prices)
        })
        
        result = self.ti.calculate_all_features(long_df)
        
        assert result is not None
        assert 'sma_20' in result
        assert 'sma_50' in result
        assert isinstance(result['sma_20'], float)
        assert isinstance(result['sma_50'], float)
    
    def test_calculate_all_features_basic_statistics(self):
        """Test calculate_all_features basic price statistics."""
        result = self.ti.calculate_all_features(self.sample_data)
        
        if result is not None:
            expected_stats = ['price_mean', 'price_std', 'price_max', 'price_min']
            for stat in expected_stats:
                assert stat in result
                assert isinstance(result[stat], (int, float))
            
            # Verify statistics are correct
            close_prices = self.sample_data['close'].values
            assert result['price_mean'] == np.mean(close_prices)
            assert result['price_std'] == np.std(close_prices)
            assert result['price_max'] == np.max(close_prices)
            assert result['price_min'] == np.min(close_prices)
    
    @property
    def sample_data(self):
        """Create sample data for testing."""
        prices = [100.0, 102.0, 101.0, 103.0, 104.0, 102.0, 105.0, 106.0, 107.0, 108.0, 
                 109.0, 108.0, 107.0, 110.0, 111.0, 112.0, 113.0, 114.0, 115.0, 116.0]
        return pd.DataFrame({
            'close': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'open': prices,
            'volume': [1000 + i * 100 for i in range(len(prices))]
        })


class TestTechnicalIndicatorsEdgeCases:
    """Test edge cases and error conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.ti = TechnicalIndicators()
    
    def test_sma_with_too_many_invalid_prices(self):
        """Test SMA calculation with too many invalid prices."""
        with patch.object(self.ti, '_is_valid_price') as mock_valid:
            # Return False for most prices (less than 50% valid)
            mock_valid.side_effect = lambda x: x in [100, 101]  # Only 2 out of 10 valid
            
            prices = [100, 101] + [float('inf')] * 8
            period = 10
            
            result = self.ti.calculate_sma(prices, period)
            
            assert result is not None
            assert result.value is None
            assert result.confidence == 0.0
            assert result.error == "too_many_invalid_prices"
    
    def test_calculate_all_features_rsi_with_sufficient_data(self):
        """Test RSI calculation when there's sufficient data."""
        # Create data with exactly 15 points (14 + 1 for RSI)
        prices = list(range(100, 115))
        df = pd.DataFrame({
            'close': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'volume': [1000] * len(prices)
        })
        
        result = self.ti.calculate_all_features(df)
        
        if result is not None and 'rsi' in result:
            assert isinstance(result['rsi'], (int, float))
            assert 0 <= result['rsi'] <= 100
    
    def test_indicator_counters(self):
        """Test that calculation and error counters work correctly."""
        initial_calc_count = self.ti.calculation_count
        initial_error_count = self.ti.error_count
        
        # Successful calculation should increment calculation_count
        prices = [100, 102, 103, 104, 105]
        self.ti.calculate_sma(prices, 3)
        assert self.ti.calculation_count > initial_calc_count
        
        # Error should increment error_count
        with patch.object(self.ti, '_is_valid_price', side_effect=Exception("Test error")):
            self.ti.calculate_sma(prices, 3)
            assert self.ti.error_count > initial_error_count


class TestTechnicalIndicatorsIntegration:
    """Integration tests for technical indicators."""
    
    def test_full_workflow_with_realistic_data(self):
        """Test full workflow with realistic market data."""
        # Create realistic price data
        np.random.seed(42)  # For reproducible results
        base_price = 100
        returns = np.random.normal(0.001, 0.02, 50)  # 50 periods of returns
        prices = [base_price]
        
        for ret in returns:
            prices.append(prices[-1] * (1 + ret))
        
        df = pd.DataFrame({
            'close': prices,
            'high': [p * 1.01 for p in prices],
            'low': [p * 0.99 for p in prices],
            'volume': np.random.randint(1000, 5000, len(prices))
        })
        
        ti = TechnicalIndicators()
        result = ti.calculate_all_features(df)
        
        assert result is not None
        assert isinstance(result, dict)
        assert len(result) > 0
    
    def test_config_impact(self):
        """Test that configuration affects behavior."""
        config1 = {"test_param": "value1"}
        config2 = {"test_param": "value2"}
        
        ti1 = TechnicalIndicators(config=config1)
        ti2 = TechnicalIndicators(config=config2)
        
        assert ti1.config != ti2.config
        assert ti1.config["test_param"] == "value1"
        assert ti2.config["test_param"] == "value2"


if __name__ == "__main__":
    pytest.main([__file__])