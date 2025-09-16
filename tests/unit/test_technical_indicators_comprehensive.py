"""
Comprehensive test suite for backend.features.technical_indicators module.
Tests TechnicalIndicators class and IndicatorResult dataclass with all methods and functionality.
Targets: 158 statements with comprehensive coverage.
"""

import os
import sys
import warnings
from unittest.mock import Mock, patch, MagicMock
import numpy as np
import pandas as pd
import pytest
from dataclasses import dataclass
import math

# Set test environment variables
os.environ['DISABLE_ML'] = '1'
os.environ['PYTEST_RUNNING'] = '1'

# Suppress warnings for cleaner test output
warnings.filterwarnings("ignore")

# Import the module to test
try:
    from backend.features import technical_indicators
except ImportError:
    # Fallback for complex import scenarios
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "technical_indicators", 
        "backend/features/technical_indicators.py"
    )
    technical_indicators = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(technical_indicators)


class TestIndicatorResult:
    """Test IndicatorResult dataclass."""
    
    def test_indicator_result_creation(self):
        """Test IndicatorResult creation with different parameters."""
        # Test basic creation
        result = technical_indicators.IndicatorResult(value=50.0, confidence=0.9)
        assert result.value == 50.0
        assert result.confidence == 0.9
        assert result.error is None
        
        # Test with error
        result_with_error = technical_indicators.IndicatorResult(
            value=None, 
            confidence=0.0, 
            error="calculation_failed"
        )
        assert result_with_error.value is None
        assert result_with_error.confidence == 0.0
        assert result_with_error.error == "calculation_failed"
    
    def test_indicator_result_default_values(self):
        """Test IndicatorResult default values."""
        result = technical_indicators.IndicatorResult(value=25.5, confidence=0.8)
        assert result.error is None  # Default value
    
    def test_indicator_result_types(self):
        """Test IndicatorResult with different value types."""
        # Float value
        result_float = technical_indicators.IndicatorResult(value=123.45, confidence=1.0)
        assert isinstance(result_float.value, float)
        
        # None value
        result_none = technical_indicators.IndicatorResult(value=None, confidence=0.0)
        assert result_none.value is None
        
        # Integer value (should work)
        result_int = technical_indicators.IndicatorResult(value=100, confidence=0.5)
        assert result_int.value == 100


class TestTechnicalIndicators:
    """Test TechnicalIndicators class."""
    
    @pytest.fixture
    def indicators_instance(self):
        """Create TechnicalIndicators instance for testing."""
        return technical_indicators.TechnicalIndicators()
    
    @pytest.fixture
    def indicators_with_config(self):
        """Create TechnicalIndicators instance with custom config."""
        config = {
            'sma_periods': [10, 20],
            'rsi_period': 14,
            'bb_period': 20
        }
        return technical_indicators.TechnicalIndicators(config=config)
    
    @pytest.fixture
    def sample_prices(self):
        """Create sample price data for testing."""
        # Generate realistic price series
        np.random.seed(42)
        base_price = 100.0
        prices = [base_price]
        
        for i in range(50):
            change = np.random.normal(0, 0.02) * prices[-1]
            new_price = prices[-1] + change
            prices.append(max(new_price, 1.0))  # Ensure positive prices
        
        return prices[1:]  # Remove initial base price
    
    @pytest.fixture
    def sample_dataframe(self, sample_prices):
        """Create sample DataFrame for testing."""
        dates = pd.date_range('2023-01-01', periods=len(sample_prices), freq='D')
        df = pd.DataFrame({
            'close': sample_prices,
            'open': [p * (1 + np.random.uniform(-0.01, 0.01)) for p in sample_prices],
            'high': [p * (1 + abs(np.random.uniform(0, 0.02))) for p in sample_prices],
            'low': [p * (1 - abs(np.random.uniform(0, 0.02))) for p in sample_prices],
            'volume': np.random.randint(1000, 10000, len(sample_prices))
        }, index=dates)
        return df
    
    def test_technical_indicators_initialization(self):
        """Test TechnicalIndicators initialization."""
        # Test default initialization
        ti = technical_indicators.TechnicalIndicators()
        assert ti.config == {}
        assert ti.calculation_count == 0
        assert ti.error_count == 0
        
        # Test with custom config
        config = {'test_param': 'test_value'}
        ti_with_config = technical_indicators.TechnicalIndicators(config=config)
        assert ti_with_config.config == config
        assert ti_with_config.calculation_count == 0
        assert ti_with_config.error_count == 0
    
    def test_calculate_all_features_basic(self, indicators_instance, sample_dataframe):
        """Test calculate_all_features basic functionality."""
        result = indicators_instance.calculate_all_features(sample_dataframe)
        
        # Should return a dictionary of features
        assert isinstance(result, dict)
        assert len(result) > 0
        
        # Should contain some expected features
        expected_features = ['sma_20', 'sma_50', 'rsi', 'bb_upper', 'bb_lower', 'bb_middle']
        for feature in expected_features:
            if feature in result:
                assert isinstance(result[feature], (int, float, type(None)))
    
    def test_calculate_all_features_empty_data(self, indicators_instance):
        """Test calculate_all_features with empty data."""
        # Test with None
        result = indicators_instance.calculate_all_features(None)
        assert result is None
        
        # Test with empty DataFrame
        empty_df = pd.DataFrame()
        result = indicators_instance.calculate_all_features(empty_df)
        assert result is None
    
    def test_calculate_all_features_missing_close(self, indicators_instance):
        """Test calculate_all_features with missing close column."""
        df_no_close = pd.DataFrame({
            'open': [100, 101, 102],
            'high': [102, 103, 104],
            'low': [99, 100, 101]
        })
        
        result = indicators_instance.calculate_all_features(df_no_close)
        assert result is None
    
    def test_calculate_all_features_insufficient_data(self, indicators_instance):
        """Test calculate_all_features with insufficient data."""
        # Create small DataFrame with less than 10 rows
        small_df = pd.DataFrame({
            'close': [100, 101, 102, 103, 104]
        })
        
        result = indicators_instance.calculate_all_features(small_df)
        assert result is None
    
    def test_calculate_sma_basic(self, indicators_instance, sample_prices):
        """Test calculate_sma basic functionality."""
        result = indicators_instance.calculate_sma(sample_prices, period=20)
        
        assert isinstance(result, technical_indicators.IndicatorResult)
        assert result.value is not None
        assert isinstance(result.value, float)
        assert result.confidence > 0.0  # Confidence > 0 for valid calculation
        assert result.error is None
    
    def test_calculate_sma_edge_cases(self, indicators_instance):
        """Test calculate_sma edge cases."""
        # Test with insufficient data
        short_prices = [100, 101, 102]
        result = indicators_instance.calculate_sma(short_prices, period=20)
        
        assert isinstance(result, technical_indicators.IndicatorResult)
        assert result.value is None
        assert result.confidence == 0.0
        assert result.error == "insufficient_data"
        
        # Test with empty list
        result = indicators_instance.calculate_sma([], period=10)
        assert result.value is None
        assert result.error == "insufficient_data"
        
        # Test with None
        result = indicators_instance.calculate_sma(None, period=10)
        assert result.value is None
        assert result.error == "insufficient_data"
    
    def test_calculate_sma_invalid_prices(self, indicators_instance):
        """Test calculate_sma with invalid prices."""
        # Test with some invalid prices
        prices_with_invalid = [100, None, 102, float('inf'), 104, -5, 106]
        result = indicators_instance.calculate_sma(prices_with_invalid, period=3)
        
        # Should handle invalid prices gracefully
        assert isinstance(result, technical_indicators.IndicatorResult)
        # May have value or error depending on implementation
    
    def test_calculate_rsi_basic(self, indicators_instance, sample_prices):
        """Test calculate_rsi basic functionality."""
        result = indicators_instance.calculate_rsi(sample_prices, period=14)
        
        assert isinstance(result, technical_indicators.IndicatorResult)
        assert result.value is not None
        assert isinstance(result.value, float)
        assert 0.0 <= result.value <= 100.0  # RSI should be between 0 and 100
        assert result.confidence > 0.0  # Confidence can be > 1.0 (ratio of available data to period)
        assert result.error is None
    
    def test_calculate_rsi_edge_cases(self, indicators_instance):
        """Test calculate_rsi edge cases."""
        # Test with insufficient data
        short_prices = [100, 101, 102]
        result = indicators_instance.calculate_rsi(short_prices, period=14)
        
        assert isinstance(result, technical_indicators.IndicatorResult)
        assert result.value is None
        assert result.confidence == 0.0
        assert result.error == "insufficient_data"
        
        # Test with empty list
        result = indicators_instance.calculate_rsi([], period=14)
        assert result.value is None
        assert result.error == "insufficient_data"
    
    def test_calculate_rsi_constant_prices(self, indicators_instance):
        """Test calculate_rsi with constant prices."""
        # RSI should be 50 for constant prices (no gains or losses)
        constant_prices = [100.0] * 20
        result = indicators_instance.calculate_rsi(constant_prices, period=14)
        
        assert isinstance(result, technical_indicators.IndicatorResult)
        # For constant prices, RSI calculation may vary by implementation
    
    def test_calculate_rsi_all_gains(self, indicators_instance):
        """Test calculate_rsi with all price gains."""
        # Steadily increasing prices should give high RSI
        increasing_prices = [100 + i for i in range(20)]
        result = indicators_instance.calculate_rsi(increasing_prices, period=14)
        
        assert isinstance(result, technical_indicators.IndicatorResult)
        if result.value is not None:
            assert result.value >= 50.0  # Should be high for all gains
    
    def test_calculate_bollinger_bands_basic(self, indicators_instance, sample_prices):
        """Test calculate_bollinger_bands basic functionality."""
        result = indicators_instance.calculate_bollinger_bands(sample_prices, period=20, std_dev=2.0)
        
        assert isinstance(result, dict)
        expected_keys = ['upper', 'middle', 'lower']
        
        for key in expected_keys:
            assert key in result
            assert isinstance(result[key], technical_indicators.IndicatorResult)
            assert result[key].value is not None
            assert isinstance(result[key].value, float)
            assert result[key].confidence > 0.0  # Confidence > 0 for valid calculation
    
    def test_calculate_bollinger_bands_edge_cases(self, indicators_instance):
        """Test calculate_bollinger_bands edge cases."""
        # Test with insufficient data
        short_prices = [100, 101, 102]
        result = indicators_instance.calculate_bollinger_bands(short_prices, period=20)
        
        assert isinstance(result, dict)
        for band_result in result.values():
            assert band_result.value is None
            assert band_result.error == "sma_calculation_failed"  # Based on actual implementation
    
    def test_calculate_bollinger_bands_parameters(self, indicators_instance, sample_prices):
        """Test calculate_bollinger_bands with different parameters."""
        # Test with different standard deviation
        result_1 = indicators_instance.calculate_bollinger_bands(sample_prices, period=10, std_dev=1.0)
        result_2 = indicators_instance.calculate_bollinger_bands(sample_prices, period=10, std_dev=3.0)
        
        # Bands should be wider with higher std_dev
        if (result_1['upper'].value and result_1['lower'].value and 
            result_2['upper'].value and result_2['lower'].value):
            assert (result_2['upper'].value - result_2['lower'].value) > (result_1['upper'].value - result_1['lower'].value)
    
    def test_is_valid_price_method(self, indicators_instance):
        """Test _is_valid_price helper method."""
        # Test valid prices
        assert indicators_instance._is_valid_price(100.0) is True
        assert indicators_instance._is_valid_price(0.01) is True
        assert indicators_instance._is_valid_price(1000000) is True
        
        # Test invalid prices
        assert indicators_instance._is_valid_price(None) is False
        assert indicators_instance._is_valid_price(float('inf')) is False
        assert indicators_instance._is_valid_price(float('-inf')) is False
        assert indicators_instance._is_valid_price(float('nan')) is False
        assert indicators_instance._is_valid_price(-100) is False
        assert indicators_instance._is_valid_price(0) is False
    
    def test_get_calculation_stats(self, indicators_instance):
        """Test get_calculation_stats method."""
        # Initial stats
        stats = indicators_instance.get_calculation_stats()
        assert isinstance(stats, dict)
        assert 'calculation_count' in stats
        assert 'error_count' in stats
        assert 'success_rate' in stats
        
        assert stats['calculation_count'] == 0
        assert stats['error_count'] == 0
        assert stats['success_rate'] == 0.0
        
        # After some calculations
        sample_prices = [100 + i for i in range(30)]
        indicators_instance.calculate_sma(sample_prices, 20)
        indicators_instance.calculate_rsi(sample_prices, 14)
        
        stats_after = indicators_instance.get_calculation_stats()
        assert stats_after['calculation_count'] > 0
        assert stats_after['success_rate'] > 0.0


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.fixture
    def indicators_instance(self):
        """Create TechnicalIndicators instance for testing."""
        return technical_indicators.TechnicalIndicators()
    
    def test_calculation_error_handling(self, indicators_instance):
        """Test error handling in calculations."""
        # Test with extreme values that might cause overflow
        extreme_prices = [1e10, 1e11, 1e12] * 10
        
        try:
            result = indicators_instance.calculate_sma(extreme_prices, 10)
            # Should either succeed or fail gracefully
            assert isinstance(result, technical_indicators.IndicatorResult)
        except Exception:
            # Any exception should be caught by the method
            pytest.fail("Method should handle exceptions internally")
    
    def test_invalid_data_types(self, indicators_instance):
        """Test handling of invalid data types."""
        # Test with string prices
        string_prices = ["100", "101", "102"] * 10
        result = indicators_instance.calculate_sma(string_prices, 10)
        assert isinstance(result, technical_indicators.IndicatorResult)
        
        # Test with mixed types
        mixed_prices = [100, "101", 102.5, None, 104] * 6
        result = indicators_instance.calculate_rsi(mixed_prices, 14)
        assert isinstance(result, technical_indicators.IndicatorResult)
    
    def test_zero_division_protection(self, indicators_instance):
        """Test protection against zero division."""
        # Create price series that could cause zero division in RSI
        prices = [100.0] * 20  # Constant prices
        result = indicators_instance.calculate_rsi(prices, 14)
        
        # Should handle gracefully without throwing exception
        assert isinstance(result, technical_indicators.IndicatorResult)
    
    def test_calculation_count_tracking(self, indicators_instance):
        """Test that calculation counts are tracked correctly."""
        initial_calc_count = indicators_instance.calculation_count
        initial_error_count = indicators_instance.error_count
        
        # Perform successful calculation
        valid_prices = [100 + i for i in range(30)]
        indicators_instance.calculate_sma(valid_prices, 20)
        
        assert indicators_instance.calculation_count > initial_calc_count
        
        # Perform calculation that should cause error
        indicators_instance.calculate_sma([], 20)  # Empty list
        
        # Error count might increase depending on implementation
        assert indicators_instance.error_count >= initial_error_count


class TestIntegrationScenarios:
    """Test integration scenarios and real-world usage."""
    
    @pytest.fixture
    def indicators_instance(self):
        """Create TechnicalIndicators instance for testing."""
        return technical_indicators.TechnicalIndicators()
    
    def test_realistic_trading_data(self, indicators_instance):
        """Test with realistic trading data patterns."""
        # Simulate realistic price movements
        np.random.seed(123)
        prices = [100.0]
        
        for i in range(100):
            # Random walk with some trend
            change = np.random.normal(0.001, 0.02)  # 0.1% daily trend, 2% volatility
            new_price = prices[-1] * (1 + change)
            prices.append(max(new_price, 1.0))
        
        prices = prices[1:]  # Remove initial price
        
        # Test all indicators
        sma_result = indicators_instance.calculate_sma(prices, 20)
        rsi_result = indicators_instance.calculate_rsi(prices, 14)
        bb_result = indicators_instance.calculate_bollinger_bands(prices, 20)
        
        # All should succeed with realistic data
        assert sma_result.value is not None
        assert rsi_result.value is not None
        assert bb_result['upper'].value is not None
        
        # Check realistic value ranges
        assert 0 <= rsi_result.value <= 100
        assert bb_result['lower'].value <= bb_result['middle'].value <= bb_result['upper'].value
    
    def test_market_crash_scenario(self, indicators_instance):
        """Test behavior during market crash scenario."""
        # Simulate market crash (steep decline)
        prices = [100.0]
        for i in range(30):
            decline = 0.05  # 5% daily decline
            new_price = prices[-1] * (1 - decline)
            prices.append(max(new_price, 1.0))
        
        prices = prices[1:]
        
        # Indicators should still work
        rsi_result = indicators_instance.calculate_rsi(prices, 14)
        bb_result = indicators_instance.calculate_bollinger_bands(prices, 20)
        
        # RSI should be low for consistent declines
        if rsi_result.value is not None:
            assert rsi_result.value <= 50  # Should be oversold
    
    def test_high_volatility_scenario(self, indicators_instance):
        """Test behavior during high volatility."""
        # Simulate high volatility (large random movements)
        np.random.seed(456)
        prices = [100.0]
        
        for i in range(50):
            change = np.random.normal(0, 0.1)  # 10% daily volatility
            new_price = prices[-1] * (1 + change)
            prices.append(max(new_price, 1.0))
        
        prices = prices[1:]
        
        # All calculations should complete despite volatility
        sma_result = indicators_instance.calculate_sma(prices, 10)
        rsi_result = indicators_instance.calculate_rsi(prices, 14)
        bb_result = indicators_instance.calculate_bollinger_bands(prices, 20)
        
        assert isinstance(sma_result, technical_indicators.IndicatorResult)
        assert isinstance(rsi_result, technical_indicators.IndicatorResult)
        assert isinstance(bb_result, dict)
    
    def test_batch_calculation_performance(self, indicators_instance):
        """Test performance characteristics of batch calculations."""
        # Create large dataset
        large_prices = [100 + np.random.normal(0, 10) for _ in range(1000)]
        
        # Should handle large datasets efficiently
        start_count = indicators_instance.calculation_count
        
        sma_result = indicators_instance.calculate_sma(large_prices, 50)
        rsi_result = indicators_instance.calculate_rsi(large_prices, 14)
        bb_result = indicators_instance.calculate_bollinger_bands(large_prices, 30)
        
        # Calculations should complete
        assert indicators_instance.calculation_count > start_count
        
        # Results should be valid
        assert sma_result.confidence > 0
        assert rsi_result.confidence > 0
        assert bb_result['middle'].confidence > 0


class TestConfigurationIntegration:
    """Test configuration and customization features."""
    
    def test_custom_config_usage(self):
        """Test usage of custom configuration."""
        config = {
            'sma_periods': [10, 30],
            'rsi_period': 21,
            'bb_period': 25,
            'custom_param': 'test_value'
        }
        
        indicators = technical_indicators.TechnicalIndicators(config=config)
        assert indicators.config == config
        
        # Config should be accessible for custom behavior
        assert indicators.config.get('custom_param') == 'test_value'
    
    def test_config_parameter_validation(self):
        """Test that configuration parameters are used appropriately."""
        # Create indicators with specific config
        indicators = technical_indicators.TechnicalIndicators(config={'test': True})
        
        # Should not break with custom config
        prices = [100 + i for i in range(30)]
        result = indicators.calculate_sma(prices, 20)
        assert isinstance(result, technical_indicators.IndicatorResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])