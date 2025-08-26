"""
Phase 5: Comprehensive Feature Engineering Test Suite
Tests for backend/features/feature_engineering.py (1,249 lines)

This module tests the critical ML feature pipeline including:
- Technical indicators calculation
- TA-Lib integration with pandas fallbacks
- Feature validation and schema enforcement
- ML feature preparation and alignment
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import warnings
from typing import Dict, List, Any

# Import the module under test
from backend.features.feature_engineering import (
    FeatureEngineer,
    FeatureScaler,
    align_for_arithmetic,
    validate_feature_schema,
    get_feature_schema,
    ensure_feature_order,
    create_feature_signature,
    validate_feature_ranges,
    compute_all_features,
    build_feature_frame,
    _is_dtype_compatible,
    _normalize_dtype
)


class TestFeatureEngineeringFixtures:
    """Test fixtures for feature engineering tests."""
    
    @pytest.fixture
    def sample_ohlcv_data(self):
        """Create sample OHLCV data for testing."""
        dates = pd.date_range(start='2023-01-01', periods=100, freq='1min')
        np.random.seed(42)  # Reproducible test data
        
        # Generate realistic price data with some trend
        base_price = 100.0
        price_changes = np.random.normal(0, 0.5, 100)
        closes = base_price + np.cumsum(price_changes)
        
        # Generate OHLC from closes with realistic spreads
        spreads = np.random.uniform(0.1, 1.0, 100)
        highs = closes + spreads * 0.7
        lows = closes - spreads * 0.3
        opens = np.roll(closes, 1)
        opens[0] = closes[0]
        
        # Generate volumes
        volumes = np.random.randint(1000, 10000, 100)
        
        return pd.DataFrame({
            'timestamp': dates,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }).set_index('timestamp')
    
    @pytest.fixture
    def minimal_ohlcv_data(self):
        """Create minimal OHLCV data for edge case testing."""
        dates = pd.date_range(start='2023-01-01', periods=5, freq='1min')
        return pd.DataFrame({
            'timestamp': dates,
            'open': [100.0, 101.0, 102.0, 101.5, 103.0],
            'high': [100.5, 101.5, 102.5, 102.0, 103.5],
            'low': [99.5, 100.5, 101.5, 101.0, 102.5],
            'close': [101.0, 102.0, 101.5, 103.0, 102.8],
            'volume': [1000, 1200, 800, 1500, 1100]
        }).set_index('timestamp')
    
    @pytest.fixture
    def trending_market_data(self):
        """Create trending market data for specific testing scenarios."""
        dates = pd.date_range(start='2023-01-01', periods=50, freq='1min')
        
        # Strong uptrend
        base_prices = np.linspace(100, 120, 50)
        noise = np.random.normal(0, 0.2, 50)
        closes = base_prices + noise
        
        highs = closes + np.random.uniform(0.1, 0.5, 50)
        lows = closes - np.random.uniform(0.1, 0.5, 50)
        opens = np.roll(closes, 1)
        opens[0] = closes[0]
        volumes = np.random.randint(500, 5000, 50)
        
        return pd.DataFrame({
            'timestamp': dates,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }).set_index('timestamp')
    
    @pytest.fixture
    def volatile_market_data(self):
        """Create highly volatile market data."""
        dates = pd.date_range(start='2023-01-01', periods=50, freq='1min')
        np.random.seed(123)
        
        # High volatility data
        closes = [100.0]
        for _ in range(49):
            change = np.random.normal(0, 2.0)  # High volatility
            closes.append(max(50.0, closes[-1] + change))  # Prevent negative prices
        
        closes = np.array(closes)
        highs = closes + np.random.uniform(0.5, 2.0, 50)
        lows = closes - np.random.uniform(0.5, 2.0, 50)
        opens = np.roll(closes, 1)
        opens[0] = closes[0]
        volumes = np.random.randint(2000, 20000, 50)
        
        return pd.DataFrame({
            'timestamp': dates,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }).set_index('timestamp')
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration for feature engineer."""
        return {
            'features': {
                'technical_indicators': {
                    'rsi_period': 14,
                    'macd_fast': 12,
                    'macd_slow': 26,
                    'macd_signal': 9,
                    'bb_period': 20,
                    'bb_std': 2.0
                },
                'enable_talib': False,  # Start with pandas fallbacks
                'normalize_features': True,
                'feature_selection': {
                    'max_features': 50,
                    'importance_threshold': 0.01
                }
            }
        }
    
    @pytest.fixture
    def sample_features_df(self):
        """Sample features DataFrame for validation testing."""
        np.random.seed(42)
        return pd.DataFrame({
            'rsi_14': np.random.uniform(0, 100, 20),
            'macd': np.random.uniform(-2, 2, 20),
            'bb_upper': np.random.uniform(100, 120, 20),
            'bb_lower': np.random.uniform(80, 100, 20),
            'volume_sma_10': np.random.uniform(1000, 5000, 20),
            'price_return_1': np.random.uniform(-0.05, 0.05, 20)
        })


class TestFeatureEngineerCore(TestFeatureEngineeringFixtures):
    """Test core FeatureEngineer functionality."""
    
    def test_feature_engineer_initialization_default(self):
        """Test FeatureEngineer initialization with default config."""
        engineer = FeatureEngineer()
        
        assert engineer.config is not None
        assert hasattr(engineer, 'logger')
        assert hasattr(engineer, 'settings')
        assert 'rsi_period' in engineer.config
        assert 'sma_periods' in engineer.config
    
    def test_feature_engineer_initialization_custom_config(self, mock_config):
        """Test FeatureEngineer initialization with custom config."""
        engineer = FeatureEngineer(mock_config)
        
        # Config should be merged with defaults, not replaced
        assert 'rsi_period' in engineer.config  # Default key should exist
        assert hasattr(engineer, 'logger')
        assert hasattr(engineer, 'settings')
    
    def test_feature_engineer_talib_handling(self):
        """Test TA-Lib availability handling."""
        engineer = FeatureEngineer()
        # TALIB_AVAILABLE is a module constant, engineer doesn't have talib_available attr
        from backend.features.feature_engineering import TALIB_AVAILABLE
        assert isinstance(TALIB_AVAILABLE, bool)
    
    def test_compute_technical_indicators_basic(self, sample_ohlcv_data):
        """Test basic technical indicators computation."""
        engineer = FeatureEngineer()
        
        result = engineer.compute_technical_indicators(sample_ohlcv_data)
        
        assert isinstance(result, pd.DataFrame)
        # May have fewer rows due to indicator calculations requiring history
        assert len(result) <= len(sample_ohlcv_data)
        assert len(result.columns) > 10  # Should have multiple indicators
        
        # Check for key indicators
        expected_patterns = ['sma', 'ema', 'rsi', 'macd', 'bb']
        found_patterns = []
        for pattern in expected_patterns:
            if any(pattern in col.lower() for col in result.columns):
                found_patterns.append(pattern)
        
        assert len(found_patterns) >= 3, f"Expected indicators not found. Found: {found_patterns}"
    
    def test_compute_features_basic(self, sample_ohlcv_data):
        """Test basic feature computation."""
        engineer = FeatureEngineer()
        
        result = engineer.compute_features(sample_ohlcv_data)
        
        assert isinstance(result, pd.DataFrame)
        # May have fewer rows due to indicator calculations
        assert len(result) <= len(sample_ohlcv_data)
        assert not result.empty
    
    def test_compute_all_features(self, sample_ohlcv_data):
        """Test comprehensive feature computation."""
        engineer = FeatureEngineer()
        
        result = engineer.compute_all_features(sample_ohlcv_data)
        
        assert isinstance(result, pd.DataFrame)
        # May have fewer rows due to indicator calculations
        assert len(result) <= len(sample_ohlcv_data)
        assert len(result.columns) > 20  # Should have many features
        
        # Verify no NaN in recent data (allow some in early periods for indicators)
        if len(result) > 10:
            recent_data = result.iloc[-10:]
            nan_ratio = recent_data.isna().sum().sum() / (recent_data.shape[0] * recent_data.shape[1])
            assert nan_ratio < 0.8, f"Too many NaN values in recent data: {nan_ratio}"
    
    def test_calculate_feature_importance_mock(self, sample_features_df):
        """Test feature importance calculation with mock data."""
        engineer = FeatureEngineer()
        
        # Create mock labels
        labels = pd.Series(np.random.choice([0, 1], size=len(sample_features_df)))
        
        # The actual implementation uses correlation-based importance
        result = engineer.calculate_feature_importance(sample_features_df, labels)
        
        assert isinstance(result, dict)
        assert len(result) == len(sample_features_df.columns)
        assert all(isinstance(v, (int, float)) for v in result.values())
        assert all(0 <= v <= 1 for v in result.values())  # Correlation values
    
    def test_get_feature_importance_ranking(self, sample_features_df):
        """Test feature importance ranking."""
        engineer = FeatureEngineer()
        
        # Add a target column to the features
        features_with_target = sample_features_df.copy()
        features_with_target['returns'] = np.random.normal(0, 0.01, len(sample_features_df))
        
        result = engineer.get_feature_importance_ranking(features_with_target, 'returns')
        
        assert isinstance(result, dict)
        assert len(result) >= 5  # Should have at least the original features
        # 'returns' should not be in result (target is excluded)
        assert 'returns' not in result
    
    def test_select_features_by_importance(self, sample_features_df):
        """Test feature selection by importance."""
        engineer = FeatureEngineer()
        
        # Add a target column
        features_with_target = sample_features_df.copy()
        features_with_target['returns'] = np.random.normal(0, 0.01, len(sample_features_df))
        
        result = engineer.select_features(features_with_target, 'returns', top_k=3)
        
        assert isinstance(result, list)
        assert len(result) <= 3
        assert all(isinstance(feature, str) for feature in result)
        # Should not include the target column
        assert 'returns' not in result
    
    def test_add_sentiment_features_basic(self, sample_ohlcv_data):
        """Test sentiment features addition."""
        engineer = FeatureEngineer()
        
        # Create mock sentiment data
        sentiment_data = {
            'sentiment_score': np.random.uniform(-1, 1, len(sample_ohlcv_data)),
            'news_count': np.random.randint(0, 10, len(sample_ohlcv_data))
        }
        
        result = engineer.add_sentiment_features(sample_ohlcv_data, sentiment_data)
        
        assert isinstance(result, pd.DataFrame)
        # The implementation may prefix sentiment features
        sentiment_cols = [col for col in result.columns if 'sentiment' in col.lower()]
        assert len(sentiment_cols) > 0
        assert len(result) == len(sample_ohlcv_data)
    
    def test_config_integration(self, mock_config):
        """Test configuration integration in feature computation."""
        engineer = FeatureEngineer(mock_config)
        
        # Verify config is updated, not replaced
        assert 'rsi_period' in engineer.config  # Should have default keys
        if 'features' in mock_config:
            # Custom config should influence the merged config
            assert isinstance(engineer.config, dict)


class TestTechnicalIndicators(TestFeatureEngineeringFixtures):
    """Test technical indicator calculations."""
    
    def test_calculate_rsi_basic(self, sample_ohlcv_data):
        """Test RSI calculation."""
        engineer = FeatureEngineer()
        
        rsi = engineer._calculate_rsi(sample_ohlcv_data['close'], period=14)
        
        assert isinstance(rsi, pd.Series)
        assert len(rsi) == len(sample_ohlcv_data)
        
        # Check RSI bounds (should be 0-100)
        valid_rsi = rsi.dropna()
        assert valid_rsi.min() >= 0, f"RSI minimum: {valid_rsi.min()}"
        assert valid_rsi.max() <= 100, f"RSI maximum: {valid_rsi.max()}"
    
    def test_calculate_rsi_edge_cases(self, minimal_ohlcv_data):
        """Test RSI with minimal data."""
        engineer = FeatureEngineer()
        
        rsi = engineer._calculate_rsi(minimal_ohlcv_data['close'], period=3)
        
        assert isinstance(rsi, pd.Series)
        # Should handle insufficient data gracefully
        assert not rsi.isna().all()
    
    def test_calculate_macd_basic(self, sample_ohlcv_data):
        """Test MACD calculation."""
        engineer = FeatureEngineer()
        
        result = engineer._calculate_macd(sample_ohlcv_data['close'], fast=12, slow=26, signal=9)
        
        # Returns a tuple of 3 Series, not a dict
        assert isinstance(result, tuple)
        assert len(result) == 3
        
        macd, signal, histogram = result
        for series in [macd, signal, histogram]:
            assert isinstance(series, pd.Series)
            assert len(series) == len(sample_ohlcv_data)
    
    def test_calculate_bollinger_bands(self, sample_ohlcv_data):
        """Test Bollinger Bands calculation."""
        engineer = FeatureEngineer()
        
        result = engineer._calculate_bollinger_bands(sample_ohlcv_data['close'], period=20, std_dev=2.0)
        
        # Returns a tuple of 3 Series
        assert isinstance(result, tuple)
        assert len(result) == 3
        
        upper_band, middle_band, lower_band = result
        for band in [upper_band, middle_band, lower_band]:
            assert isinstance(band, pd.Series)
            assert len(band) == len(sample_ohlcv_data)
        
        # Check logical ordering where data is available
        valid_indices = ~(upper_band.isna() | middle_band.isna() | lower_band.isna())
        if valid_indices.any():
            assert (upper_band[valid_indices] >= middle_band[valid_indices]).all()
            assert (middle_band[valid_indices] >= lower_band[valid_indices]).all()
    
    def test_calculate_volume_features(self, sample_ohlcv_data):
        """Test volume feature calculation."""
        engineer = FeatureEngineer()
        
        result = engineer._calculate_volume_features(sample_ohlcv_data)
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_ohlcv_data)
        
        # Check for volume-related columns
        volume_cols = [col for col in result.columns if 'volume' in col.lower()]
        assert len(volume_cols) > 0
    
    def test_calculate_returns(self, sample_ohlcv_data):
        """Test returns calculation."""
        engineer = FeatureEngineer()
        
        periods = [1, 5, 10]
        result = engineer._calculate_returns(sample_ohlcv_data['close'], periods)
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_ohlcv_data)
        
        # Check for expected columns (actual implementation uses 'd' suffix)
        for period in periods:
            expected_col = f'return_{period}d'
            assert expected_col in result.columns
    
    def test_calculate_volatility(self, volatile_market_data):
        """Test volatility calculation with volatile data."""
        engineer = FeatureEngineer()
        
        periods = [5, 10, 20]
        result = engineer._calculate_volatility(volatile_market_data['close'], periods)
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(volatile_market_data)
        
        # Volatility should be positive
        for col in result.columns:
            valid_vol = result[col].dropna()
            if len(valid_vol) > 0:
                assert valid_vol.min() >= 0, f"Negative volatility in {col}"
    
    def test_add_moving_averages(self, sample_ohlcv_data):
        """Test moving averages addition."""
        engineer = FeatureEngineer()
        
        result = engineer._add_moving_averages(sample_ohlcv_data.copy())
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_ohlcv_data)
        
        # Check for MA columns
        ma_cols = [col for col in result.columns if 'sma' in col.lower() or 'ema' in col.lower()]
        assert len(ma_cols) > 0
    
    def test_add_momentum_indicators(self, trending_market_data):
        """Test momentum indicators with trending data."""
        engineer = FeatureEngineer()
        
        result = engineer._add_momentum_indicators(trending_market_data.copy())
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(trending_market_data)
        
        # Check for momentum indicators
        momentum_cols = [col for col in result.columns if any(indicator in col.lower() 
                         for indicator in ['rsi', 'roc', 'momentum'])]
        assert len(momentum_cols) > 0
    
    def test_add_volatility_indicators(self, volatile_market_data):
        """Test volatility indicators."""
        engineer = FeatureEngineer()
        
        result = engineer._add_volatility_indicators(volatile_market_data.copy())
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(volatile_market_data)
        
        # Check for volatility indicators
        vol_cols = [col for col in result.columns if any(indicator in col.lower() 
                   for indicator in ['atr', 'bb', 'volatility'])]
        assert len(vol_cols) > 0
    
    def test_add_volume_indicators(self, sample_ohlcv_data):
        """Test volume indicators."""
        engineer = FeatureEngineer()
        
        result = engineer._add_volume_indicators(sample_ohlcv_data.copy())
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_ohlcv_data)
        
        # Check for volume indicators
        vol_cols = [col for col in result.columns if 'volume' in col.lower()]
        assert len(vol_cols) > 0
    
    def test_technical_indicators_nan_handling(self, minimal_ohlcv_data):
        """Test technical indicators handle NaN values properly."""
        engineer = FeatureEngineer()
        
        # Add some NaN values
        data_with_nan = minimal_ohlcv_data.copy()
        data_with_nan.loc[data_with_nan.index[1], 'close'] = np.nan
        
        result = engineer.compute_technical_indicators(data_with_nan)
        
        assert isinstance(result, pd.DataFrame)
        # Should not crash, but may return empty DataFrame with insufficient data
        # This is expected behavior for technical indicators
    
    def test_insufficient_data_handling(self):
        """Test behavior with insufficient data."""
        engineer = FeatureEngineer()
        
        # Create very minimal data
        dates = pd.date_range(start='2023-01-01', periods=2, freq='1min')
        tiny_data = pd.DataFrame({
            'timestamp': dates,
            'open': [100.0, 101.0],
            'high': [100.5, 101.5],
            'low': [99.5, 100.5],
            'close': [101.0, 102.0],
            'volume': [1000, 1200]
        }).set_index('timestamp')
        
        result = engineer.compute_technical_indicators(tiny_data)
        
        assert isinstance(result, pd.DataFrame)
        # With insufficient data, may return empty DataFrame - this is expected
        # Most indicators need at least 14-20 periods to compute meaningful values


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
