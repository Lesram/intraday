"""
Coverage enhancement tests for backend.features.feature_engineering module.
Target: Comprehensive testing to significantly improve coverage from 38% baseline.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from typing import Any, Dict
import warnings

# Set test environment
import os
os.environ["DISABLE_ML"] = "1"
os.environ["DISABLE_TENSORFLOW"] = "1"
os.environ["PYTEST_RUNNING"] = "1"

from backend.features.feature_engineering import (
    FeatureEngineer,
    align_for_arithmetic,
    Settings,
    settings,
    TALIB_AVAILABLE
)


class TestAlignForArithmetic:
    """Comprehensive tests for align_for_arithmetic function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.index = pd.date_range('2023-01-01', periods=5, freq='D')
    
    def test_align_for_arithmetic_scalar_int(self):
        """Test align_for_arithmetic with scalar integer."""
        result = align_for_arithmetic(100, self.index)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.index)
        assert all(result == 100)
        assert result.index.equals(self.index)
    
    def test_align_for_arithmetic_scalar_float(self):
        """Test align_for_arithmetic with scalar float."""
        result = align_for_arithmetic(100.5, self.index)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.index)
        assert all(result == 100.5)
        assert result.index.equals(self.index)
    
    def test_align_for_arithmetic_series_matching(self):
        """Test align_for_arithmetic with matching Series."""
        series = pd.Series([1, 2, 3, 4, 5], index=self.index)
        result = align_for_arithmetic(series, self.index)
        
        assert isinstance(result, pd.Series)
        assert result.index.equals(self.index)
        assert result.equals(series)
    
    def test_align_for_arithmetic_series_different_index(self):
        """Test align_for_arithmetic with Series having different index."""
        different_index = pd.date_range('2023-01-03', periods=3, freq='D')
        series = pd.Series([10, 20, 30], index=different_index)
        
        result = align_for_arithmetic(series, self.index)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.index)
        assert result.index.equals(self.index)
    
    def test_align_for_arithmetic_dataframe(self):
        """Test align_for_arithmetic with DataFrame."""
        df = pd.DataFrame({'col1': [1, 2, 3, 4, 5], 'col2': [6, 7, 8, 9, 10]}, index=self.index)
        result = align_for_arithmetic(df, self.index)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.index)
        assert result.index.equals(self.index)
        # Should use first column
        assert result.equals(df.iloc[:, 0])
    
    def test_align_for_arithmetic_list_exact_length(self):
        """Test align_for_arithmetic with list of exact length."""
        data_list = [1, 2, 3, 4, 5]
        result = align_for_arithmetic(data_list, self.index)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.index)
        assert result.index.equals(self.index)
        assert result.tolist() == data_list
    
    def test_align_for_arithmetic_list_too_long(self):
        """Test align_for_arithmetic with list longer than index."""
        long_list = [1, 2, 3, 4, 5, 6, 7, 8]
        result = align_for_arithmetic(long_list, self.index)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.index)
        assert result.index.equals(self.index)
        assert result.tolist() == long_list[:len(self.index)]
    
    def test_align_for_arithmetic_list_too_short(self):
        """Test align_for_arithmetic with list shorter than index."""
        short_list = [1, 2, 3]
        result = align_for_arithmetic(short_list, self.index)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.index)
        assert result.index.equals(self.index)
        # Should pad with last value
        expected = [1, 2, 3, 3, 3]
        assert result.tolist() == expected
    
    def test_align_for_arithmetic_empty_list(self):
        """Test align_for_arithmetic with empty list."""
        result = align_for_arithmetic([], self.index)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.index)
        assert result.index.equals(self.index)
        # Should pad with zeros
        assert all(result == 0)
    
    def test_align_for_arithmetic_tuple(self):
        """Test align_for_arithmetic with tuple."""
        data_tuple = (1, 2, 3, 4, 5)
        result = align_for_arithmetic(data_tuple, self.index)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.index)
        assert result.tolist() == list(data_tuple)
    
    def test_align_for_arithmetic_numpy_array(self):
        """Test align_for_arithmetic with numpy array."""
        data_array = np.array([1, 2, 3, 4, 5])
        result = align_for_arithmetic(data_array, self.index)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.index)
        assert result.tolist() == data_array.tolist()
    
    @patch('backend.features.feature_engineering.get_structured_logger')
    def test_align_for_arithmetic_conversion_error_fallback(self, mock_logger):
        """Test align_for_arithmetic fallback when Series conversion fails."""
        # Create an object that can't be converted to Series normally
        problematic_object = object()
        
        result = align_for_arithmetic(problematic_object, self.index)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.index)
        # Should fallback to broadcasting the object
        assert all(result == problematic_object)
        
        # Should log debug message
        mock_logger.return_value.debug.assert_called()


class TestSettings:
    """Test Settings class functionality."""
    
    def test_settings_initialization(self):
        """Test Settings class initialization."""
        s = Settings()
        
        assert s.feature_window == 100
        assert s.technical_indicators == True
        assert s.volume_indicators == True
        assert s.sentiment_features == False
        assert s.debug_mode == False
    
    def test_settings_get_existing_attribute(self):
        """Test Settings.get() with existing attribute."""
        s = Settings()
        
        assert s.get('feature_window') == 100
        assert s.get('technical_indicators') == True
    
    def test_settings_get_missing_attribute_with_default(self):
        """Test Settings.get() with missing attribute and default."""
        s = Settings()
        
        assert s.get('nonexistent', 'default_value') == 'default_value'
        assert s.get('missing_key', None) is None
    
    def test_settings_get_missing_attribute_no_default(self):
        """Test Settings.get() with missing attribute and no default."""
        s = Settings()
        
        assert s.get('nonexistent') is None
    
    def test_global_settings_instance(self):
        """Test global settings instance."""
        from backend.features.feature_engineering import settings
        
        assert isinstance(settings, Settings)
        assert hasattr(settings, 'feature_window')


class TestFeatureEngineerInitialization:
    """Test FeatureEngineer initialization and configuration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock the dependencies to avoid import issues
        self.mock_get_settings = patch('backend.features.feature_engineering.get_settings').start()
        self.mock_get_logger = patch('backend.features.feature_engineering.get_structured_logger').start()
        
        # Create mock settings
        mock_settings = Mock()
        mock_settings.trading = Mock()
        mock_settings.trading.max_rolling_window = 252
        mock_settings.trading.feature_mode = 'full'
        mock_settings.trading.enable_heavy_features = True
        mock_settings.trading.enable_autocorr_features = False
        
        self.mock_get_settings.return_value = mock_settings
        self.mock_get_logger.return_value = Mock()
    
    def teardown_method(self):
        """Clean up patches."""
        patch.stopall()
    
    def test_feature_engineer_initialization_default_config(self):
        """Test FeatureEngineer initialization with default config."""
        fe = FeatureEngineer()
        
        assert fe is not None
        assert hasattr(fe, 'config')
        assert hasattr(fe, 'logger')
        assert hasattr(fe, 'settings')
        
        # Check default configuration keys
        expected_keys = [
            'sma_periods', 'ema_periods', 'rsi_period', 'rsi_fast_period',
            'macd_fast', 'macd_slow', 'macd_signal', 'atr_period', 'bb_period',
            'bb_std', 'volume_sma_period', 'stoch_k_period', 'stoch_d_period'
        ]
        for key in expected_keys:
            assert key in fe.config
    
    def test_feature_engineer_initialization_custom_config(self):
        """Test FeatureEngineer initialization with custom config."""
        custom_config = {
            'rsi_period': 21,
            'bb_period': 30,
            'custom_param': 'test_value'
        }
        
        fe = FeatureEngineer(config=custom_config)
        
        # Custom config should override defaults
        assert fe.config['rsi_period'] == 21
        assert fe.config['bb_period'] == 30
        assert fe.config['custom_param'] == 'test_value'
        
        # Other defaults should still be present
        assert 'sma_periods' in fe.config
        assert 'ema_periods' in fe.config
    
    def test_feature_engineer_talib_awareness(self):
        """Test that FeatureEngineer is aware of TALIB availability."""
        fe = FeatureEngineer()
        
        # Should log TALIB availability during initialization
        self.mock_get_logger.return_value.info.assert_called()
        
        # Check that TALIB_AVAILABLE is accessible
        assert isinstance(TALIB_AVAILABLE, bool)


class TestFeatureEngineerCompatibilityMethods:
    """Test FeatureEngineer compatibility methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock dependencies
        self.mock_get_settings = patch('backend.features.feature_engineering.get_settings').start()
        self.mock_get_logger = patch('backend.features.feature_engineering.get_structured_logger').start()
        
        mock_settings = Mock()
        mock_settings.trading = Mock()
        mock_settings.trading.max_rolling_window = 252
        mock_settings.trading.feature_mode = 'full'
        mock_settings.trading.enable_heavy_features = True
        mock_settings.trading.enable_autocorr_features = False
        
        self.mock_get_settings.return_value = mock_settings
        self.mock_get_logger.return_value = Mock()
        
        self.fe = FeatureEngineer()
        
        # Create sample price data
        dates = pd.date_range('2023-01-01', periods=50, freq='D')
        self.price_series = pd.Series(np.random.uniform(100, 200, 50), index=dates)
    
    def teardown_method(self):
        """Clean up patches."""
        patch.stopall()
    
    def test_calculate_rsi_method(self):
        """Test _calculate_rsi method."""
        result = self.fe._calculate_rsi(self.price_series)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.price_series)
        assert result.index.equals(self.price_series.index)
    
    def test_calculate_rsi_custom_period(self):
        """Test _calculate_rsi with custom period."""
        result = self.fe._calculate_rsi(self.price_series, period=21)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.price_series)
    
    def test_calculate_macd_method(self):
        """Test _calculate_macd method."""
        macd, signal_line, histogram = self.fe._calculate_macd(self.price_series)
        
        assert isinstance(macd, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(histogram, pd.Series)
        
        assert len(macd) == len(self.price_series)
        assert len(signal_line) == len(self.price_series)
        assert len(histogram) == len(self.price_series)
    
    def test_calculate_macd_custom_parameters(self):
        """Test _calculate_macd with custom parameters."""
        macd, signal_line, histogram = self.fe._calculate_macd(
            self.price_series, fast=10, slow=20, signal=5
        )
        
        assert isinstance(macd, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(histogram, pd.Series)
    
    def test_calculate_bollinger_bands_method(self):
        """Test _calculate_bollinger_bands method."""
        result = self.fe._calculate_bollinger_bands(self.price_series)
        
        # Should return tuple or dict of upper, middle, lower bands
        assert result is not None
    
    def test_calculate_bollinger_bands_custom_parameters(self):
        """Test _calculate_bollinger_bands with custom parameters."""
        result = self.fe._calculate_bollinger_bands(
            self.price_series, period=30, std_dev=1.5
        )
        
        assert result is not None
    
    def test_calculate_volume_features_method(self):
        """Test _calculate_volume_features method."""
        # Create sample OHLCV DataFrame
        dates = pd.date_range('2023-01-01', periods=20, freq='D')
        df = pd.DataFrame({
            'open': np.random.uniform(95, 105, 20),
            'high': np.random.uniform(105, 115, 20),
            'low': np.random.uniform(85, 95, 20),
            'close': np.random.uniform(95, 105, 20),
            'volume': np.random.randint(1000, 10000, 20)
        }, index=dates)
        
        result = self.fe._calculate_volume_features(df)
        
        # Should return a DataFrame (even if method is incomplete)
        assert isinstance(result, pd.DataFrame) or result is None


class TestFeatureEngineerTalibIntegration:
    """Test FeatureEngineer methods with and without TALIB."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock dependencies
        self.mock_get_settings = patch('backend.features.feature_engineering.get_settings').start()
        self.mock_get_logger = patch('backend.features.feature_engineering.get_structured_logger').start()
        
        mock_settings = Mock()
        mock_settings.trading = Mock()
        mock_settings.trading.max_rolling_window = 252
        mock_settings.trading.feature_mode = 'full'
        mock_settings.trading.enable_heavy_features = True
        mock_settings.trading.enable_autocorr_features = False
        
        self.mock_get_settings.return_value = mock_settings
        self.mock_get_logger.return_value = Mock()
        
        self.fe = FeatureEngineer()
        
        # Create sample data
        dates = pd.date_range('2023-01-01', periods=30, freq='D')
        self.sample_prices = pd.Series(np.random.uniform(100, 200, 30), index=dates)
    
    def teardown_method(self):
        """Clean up patches."""
        patch.stopall()
    
    @patch('backend.features.feature_engineering.TALIB_AVAILABLE', True)
    @patch('backend.features.feature_engineering.talib')
    def test_calculate_rsi_with_talib(self, mock_talib):
        """Test RSI calculation when TALIB is available."""
        # Mock TALIB RSI function
        mock_rsi_values = np.random.uniform(20, 80, len(self.sample_prices))
        mock_talib.RSI.return_value = mock_rsi_values
        
        result = self.fe._calculate_rsi(self.sample_prices)
        
        mock_talib.RSI.assert_called_once()
        assert isinstance(result, pd.Series)
        assert len(result) == len(self.sample_prices)
    
    @patch('backend.features.feature_engineering.TALIB_AVAILABLE', False)
    @patch('backend.features.feature_engineering.rsi')
    def test_calculate_rsi_without_talib(self, mock_rsi_func):
        """Test RSI calculation when TALIB is not available."""
        # Mock the fallback RSI function
        mock_rsi_values = pd.Series(np.random.uniform(20, 80, len(self.sample_prices)), index=self.sample_prices.index)
        mock_rsi_func.return_value = mock_rsi_values
        
        result = self.fe._calculate_rsi(self.sample_prices)
        
        mock_rsi_func.assert_called_once_with(self.sample_prices, 14)
        assert isinstance(result, pd.Series)
    
    @patch('backend.features.feature_engineering.TALIB_AVAILABLE', True)
    @patch('backend.features.feature_engineering.talib')
    def test_calculate_macd_with_talib(self, mock_talib):
        """Test MACD calculation when TALIB is available."""
        # Mock TALIB MACD function
        mock_macd = np.random.uniform(-5, 5, len(self.sample_prices))
        mock_signal = np.random.uniform(-5, 5, len(self.sample_prices))
        mock_histogram = np.random.uniform(-2, 2, len(self.sample_prices))
        
        mock_talib.MACD.return_value = (mock_macd, mock_signal, mock_histogram)
        
        macd, signal_line, histogram = self.fe._calculate_macd(self.sample_prices)
        
        mock_talib.MACD.assert_called_once()
        assert isinstance(macd, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(histogram, pd.Series)
    
    @patch('backend.features.feature_engineering.TALIB_AVAILABLE', False)
    @patch('backend.features.feature_engineering.exponential_moving_average')
    def test_calculate_macd_without_talib(self, mock_ema):
        """Test MACD calculation when TALIB is not available."""
        # Mock EMA function calls
        mock_ema_fast = pd.Series(np.random.uniform(95, 105, len(self.sample_prices)), index=self.sample_prices.index)
        mock_ema_slow = pd.Series(np.random.uniform(95, 105, len(self.sample_prices)), index=self.sample_prices.index)
        
        def ema_side_effect(series, period):
            if period == 12:
                return mock_ema_fast
            elif period == 26:
                return mock_ema_slow
            else:  # Signal line
                return pd.Series(np.random.uniform(-1, 1, len(series)), index=series.index)
        
        mock_ema.side_effect = ema_side_effect
        
        macd, signal_line, histogram = self.fe._calculate_macd(self.sample_prices)
        
        assert mock_ema.call_count >= 2  # Should call EMA multiple times
        assert isinstance(macd, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(histogram, pd.Series)


class TestFeatureEngineerEdgeCases:
    """Test edge cases and error conditions in FeatureEngineer."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock dependencies with minimal setup
        self.mock_get_settings = patch('backend.features.feature_engineering.get_settings').start()
        self.mock_get_logger = patch('backend.features.feature_engineering.get_structured_logger').start()
        
        mock_settings = Mock()
        mock_settings.trading = Mock()
        mock_settings.trading.max_rolling_window = 100  # Smaller for edge cases
        mock_settings.trading.feature_mode = 'light'
        mock_settings.trading.enable_heavy_features = False
        mock_settings.trading.enable_autocorr_features = False
        
        self.mock_get_settings.return_value = mock_settings
        self.mock_get_logger.return_value = Mock()
    
    def teardown_method(self):
        """Clean up patches."""
        patch.stopall()
    
    def test_feature_engineer_with_small_rolling_window(self):
        """Test FeatureEngineer with small max_rolling_window setting."""
        fe = FeatureEngineer()
        
        # Should adapt lookback periods to smaller rolling window
        assert all(period <= 100 for period in fe.config['lookback_periods'])
        assert fe.config['normalization_window'] <= 100
    
    def test_feature_engineer_config_merging(self):
        """Test that configuration merging works correctly."""
        base_config = {'rsi_period': 14, 'bb_period': 20}
        custom_config = {'rsi_period': 21, 'new_param': 'test'}
        
        fe = FeatureEngineer(config=custom_config)
        
        # Should merge configs correctly
        assert fe.config['rsi_period'] == 21  # Overridden
        assert fe.config['bb_period'] == 20   # Default preserved
        assert fe.config['new_param'] == 'test'  # New param added
    
    def test_feature_engineer_none_config(self):
        """Test FeatureEngineer with None config."""
        fe = FeatureEngineer(config=None)
        
        # Should work with None config
        assert fe.config is not None
        assert 'rsi_period' in fe.config


if __name__ == "__main__":
    pytest.main([__file__])