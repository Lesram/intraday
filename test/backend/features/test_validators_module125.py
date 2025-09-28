"""
Simplified test suite for backend.features.validators module focused on coverage.
"""

import pytest
import numpy as np
import pandas as pd
import os
from unittest.mock import patch

from backend.features.validators import (
    validate_ohlcv,
    guard_no_lookahead,
    guard_no_lookahead_synthetic,
    validate_feature_alignment,
    detect_forward_fill_leakage,
    DISABLE_ML
)
from backend.features.types import LookaheadLeakError


class TestValidateOHLCV:
    """Test validate_ohlcv function."""
    
    def create_valid_ohlcv_df(self):
        """Create a valid OHLCV DataFrame for testing."""
        dates = pd.date_range('2023-01-01', periods=5, freq='D', tz='UTC')
        return pd.DataFrame({
            'open': [100.0, 101.0, 102.0, 103.0, 104.0],
            'high': [105.0, 106.0, 107.0, 108.0, 109.0],
            'low': [99.0, 100.0, 101.0, 102.0, 103.0],
            'close': [104.0, 105.0, 106.0, 107.0, 108.0],
            'volume': [1000, 1100, 1200, 1300, 1400]
        }, index=dates)
    
    def test_valid_ohlcv_success(self):
        """Test validation passes for valid OHLCV data."""
        df = self.create_valid_ohlcv_df()
        validate_ohlcv(df)  # Should not raise
    
    def test_missing_columns_error(self):
        """Test error when required columns are missing."""
        df = pd.DataFrame({
            'open': [100.0, 101.0],
            'high': [105.0, 106.0],
            'low': [99.0, 100.0],
        })
        
        with pytest.raises(ValueError, match="Missing required OHLCV columns"):
            validate_ohlcv(df)
    
    def test_non_numeric_column_error(self):
        """Test error when columns contain non-numeric data."""
        df = pd.DataFrame({
            'open': ['a', 'b'],
            'high': [105.0, 106.0],
            'low': [99.0, 100.0],
            'close': [104.0, 105.0],
            'volume': [1000, 1100]
        })
        
        with pytest.raises(ValueError, match="Column 'open' must be numeric"):
            validate_ohlcv(df)
    
    def test_infinite_values_error(self):
        """Test error when columns contain infinite values."""
        df = self.create_valid_ohlcv_df()
        df.loc[0, 'close'] = float('inf')
        
        with pytest.raises(ValueError, match="Column 'close' contains infinite values"):
            validate_ohlcv(df)
    
    def test_negative_volume_error(self):
        """Test error when volume is negative."""
        df = self.create_valid_ohlcv_df()
        df.loc[2, 'volume'] = -100
        
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            validate_ohlcv(df)
    
    def test_invalid_ohlc_relationships_error(self):
        """Test error for invalid OHLC relationships."""
        df = pd.DataFrame({
            'open': [100.0, 101.0],
            'high': [95.0, 106.0],  # First high < open
            'low': [99.0, 100.0],
            'close': [104.0, 105.0],
            'volume': [1000, 1100]
        })
        
        with pytest.raises(ValueError, match="Invalid OHLC relationships detected"):
            validate_ohlcv(df)
    
    def test_non_monotonic_timestamps(self):
        """Test error when timestamps are not monotonic."""
        dates = [pd.Timestamp('2023-01-01', tz='UTC'), 
                 pd.Timestamp('2023-01-03', tz='UTC'),
                 pd.Timestamp('2023-01-02', tz='UTC')]  # Not monotonic
        df = pd.DataFrame({
            'open': [100.0, 101.0, 102.0],
            'high': [105.0, 106.0, 107.0],
            'low': [99.0, 100.0, 101.0],
            'close': [104.0, 105.0, 106.0],
            'volume': [1000, 1100, 1200]
        }, index=pd.DatetimeIndex(dates))
        
        with pytest.raises(ValueError, match="Timestamps must be strictly increasing"):
            validate_ohlcv(df)
    
    def test_non_timezone_aware_timestamps(self):
        """Test error when timestamps are not timezone-aware."""
        dates = pd.date_range('2023-01-01', periods=3, freq='D')  # No timezone
        df = pd.DataFrame({
            'open': [100.0, 101.0, 102.0],
            'high': [105.0, 106.0, 107.0],
            'low': [99.0, 100.0, 101.0],
            'close': [104.0, 105.0, 106.0],
            'volume': [1000, 1100, 1200]
        }, index=dates)
        
        with pytest.raises(ValueError, match="Timestamps must be timezone-aware"):
            validate_ohlcv(df)


class TestGuardNoLookahead:
    """Test guard_no_lookahead function."""
    
    def test_insufficient_data_error(self):
        """Test error when insufficient data for analysis."""
        dates = pd.date_range('2023-01-01', periods=50, freq='D')
        features = pd.DataFrame({'feature1': np.random.randn(50)}, index=dates)
        price = pd.Series(np.random.randn(50), index=dates)
        
        with pytest.raises(ValueError, match="Insufficient data for lookahead detection"):
            guard_no_lookahead(features, price, window_size=100)
    



class TestGuardNoLookaheadSynthetic:
    """Test guard_no_lookahead_synthetic function."""
    
    def test_synthetic_insufficient_data(self):
        """Test synthetic detection with insufficient data."""
        dates = pd.date_range('2023-01-01', periods=30, freq='D')
        features = pd.DataFrame({'feature1': np.random.randn(30)}, index=dates)
        
        # Should return early without error (not enough data)
        guard_no_lookahead_synthetic(features)
    



class TestValidateFeatureAlignment:
    """Test validate_feature_alignment function."""
    
    def test_valid_alignment_success(self):
        """Test validation passes for properly aligned data."""
        dates = pd.date_range('2023-01-01', periods=5, freq='D')
        features = pd.DataFrame({'feature1': [1, 2, 3, 4, 5]}, index=dates)
        target = pd.Series([0.01, 0.02, 0.03, 0.04, np.nan], index=dates)
        
        validate_feature_alignment(features, target)  # Should not raise
    
    def test_different_indices_error(self):
        """Test error when features and target have different indices."""
        features = pd.DataFrame({'feature1': [1, 2, 3]}, index=[0, 1, 2])
        target = pd.Series([0.01, 0.02, 0.03], index=[1, 2, 3])
        
        with pytest.raises(ValueError, match="Features and target must have identical indices"):
            validate_feature_alignment(features, target)
    
    def test_target_validation_fallback(self):
        """Test target validation in fallback mode."""
        dates = pd.date_range('2023-01-01', periods=5, freq='D')
        features = pd.DataFrame({'feature1': [1, 2, 3, 4, 5]}, index=dates)
        target = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05], index=dates)
        
        # Mock pd.isna to cause fallback behavior
        with patch('backend.features.validators.pd.isna', side_effect=Exception("Mock error")):
            # Should skip validation and pass
            validate_feature_alignment(features, target)


class TestDetectForwardFillLeakage:
    """Test detect_forward_fill_leakage function."""
    
    def test_no_leakage_clean_data(self):
        """Test with clean data that has no forward-fill leakage."""
        df = pd.DataFrame({
            'clean_col': [1.0, 2.0, 3.0, 4.0, 5.0],
            'varying_col': [10, 20, 15, 25, 30]
        })
        
        result = detect_forward_fill_leakage(df)
        assert result == []
    
    def test_forward_fill_detection(self):
        """Test detection of columns with excessive forward-filling."""
        df = pd.DataFrame({
            'good_col': [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
            'bad_col': [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 15.0],  # 8 consecutive same values
        })
        
        result = detect_forward_fill_leakage(df, max_consecutive_fill=5)
        assert 'bad_col' in result
        assert 'good_col' not in result
    
    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        df = pd.DataFrame()
        result = detect_forward_fill_leakage(df)
        assert result == []
    
    def test_non_numeric_columns_ignored(self):
        """Test that non-numeric columns are ignored."""
        df = pd.DataFrame({
            'numeric_col': [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            'string_col': ['a', 'a', 'a', 'a', 'a', 'a', 'a', 'a'],  # Would be flagged if numeric
        })
        
        result = detect_forward_fill_leakage(df, max_consecutive_fill=3)
        assert 'string_col' not in result
        assert 'numeric_col' not in result


class TestLookaheadLeakError:
    """Test LookaheadLeakError exception."""
    
    def test_lookahead_leak_error_creation(self):
        """Test creation of LookaheadLeakError."""
        features = ['feature1', 'feature2']
        error = LookaheadLeakError("Test message", features)
        
        assert str(error) == "Test message"
        assert error.columns == features


class TestDISABLE_ML:
    """Test DISABLE_ML flag."""
    
    def test_disable_ml_flag(self):
        """Test DISABLE_ML flag exists and is boolean."""
        assert isinstance(DISABLE_ML, bool)


# Test for fallback mode coverage
class TestFallbackModes:
    """Test fallback modes for various validation functions."""
    
    def test_numeric_check_fallback(self):
        """Test numeric check fallback mode."""
        df = pd.DataFrame({
            'open': [100.0, 101.0],
            'high': [105.0, 106.0],
            'low': [99.0, 100.0],
            'close': [104.0, 105.0],
            'volume': [1000, 1100]
        })
        
        # Mock pd.api.types to not exist (fallback mode)
        with patch('pandas.api.types.is_numeric_dtype', side_effect=AttributeError):
            # Should use pd.to_numeric fallback
            validate_ohlcv(df)  # Should pass
    
    def test_infinite_check_fallback(self):
        """Test infinity check fallback mode."""
        df = pd.DataFrame({
            'open': [100.0, 101.0],
            'high': [105.0, 106.0],
            'low': [99.0, 100.0],
            'close': [104.0, 105.0],
            'volume': [1000, 1100]
        })
        
        # This should pass normally
        validate_ohlcv(df)
    
    def test_timestamp_validation_fallback(self):
        """Test timestamp validation fallback mode."""
        df = pd.DataFrame({
            'open': [100.0, 101.0],
            'high': [105.0, 106.0],
            'low': [99.0, 100.0],
            'close': [104.0, 105.0],
            'volume': [1000, 1100]
        })
        
        # Mock pd.DatetimeIndex to not exist (stub mode)
        with patch('pandas.DatetimeIndex', side_effect=AttributeError):
            validate_ohlcv(df)  # Should skip timestamp validation
    
    def test_numeric_check_final_fallback(self):
        """Test final fallback for numeric check when pd.to_numeric fails."""
        df = pd.DataFrame({
            'open': [100.0, 101.0],
            'high': [105.0, 106.0],
            'low': [99.0, 100.0],
            'close': [104.0, 105.0],
            'volume': [1000, 1100]
        })
        
        # Mock both pandas API and to_numeric to fail
        with patch('pandas.api.types.is_numeric_dtype', side_effect=AttributeError):
            with patch('pandas.to_numeric', side_effect=Exception("Mock error")):
                # Should use the final try-except fallback
                validate_ohlcv(df)  # Should still pass with valid numeric data


if __name__ == "__main__":
    pytest.main([__file__])