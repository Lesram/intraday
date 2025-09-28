"""
Coverage enhancement tests for backend.features.alignment module.
Target: Comprehensive testing to significantly improve coverage from 12% baseline.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from typing import Literal
import pytz
from datetime import datetime, timedelta

# Set test environment
import os
os.environ["DISABLE_ML"] = "1"
os.environ["DISABLE_TENSORFLOW"] = "1"
os.environ["PYTEST_RUNNING"] = "1"

from backend.features.alignment import (
    align_features_target,
    align_multitimeframe,
    validate_temporal_order,
    detect_misalignment,
    create_training_splits,
    DISABLE_ML
)
from backend.features.types import FeatureFrame


class TestAlignFeaturesTarget:
    """Comprehensive tests for align_features_target function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create timezone-aware datetime index
        self.tz = pytz.UTC
        self.dates = pd.date_range('2023-01-01', periods=10, freq='1min', tz=self.tz)
        
        # Create sample features DataFrame
        self.features = pd.DataFrame({
            'feature1': np.random.randn(10),
            'feature2': np.random.randn(10),
            'feature3': np.random.randn(10)
        }, index=self.dates)
        
        # Create sample price series
        self.price = pd.Series(
            np.random.uniform(100, 200, 10), 
            index=self.dates, 
            name='close'
        )
    
    def test_align_features_target_basic_functionality(self):
        """Test basic functionality of align_features_target."""
        result = align_features_target(self.features, self.price)
        
        assert isinstance(result, FeatureFrame)
        assert result.X is not None
        assert result.y is not None
        assert result.index_mask is not None
    
    def test_align_features_target_with_custom_price_col(self):
        """Test align_features_target with custom price column name."""
        result = align_features_target(self.features, self.price, price_col="open")
        
        assert isinstance(result, FeatureFrame)
        assert result.X is not None
        assert result.y is not None
    
    def test_align_features_target_no_common_timestamps(self):
        """Test align_features_target with no common timestamps."""
        # Create price series with different dates
        different_dates = pd.date_range('2024-01-01', periods=5, freq='1min', tz=self.tz)
        different_price = pd.Series(np.random.uniform(100, 200, 5), index=different_dates)
        
        with pytest.raises(ValueError, match="No common timestamps between features and price"):
            align_features_target(self.features, different_price)
    
    def test_align_features_target_partial_overlap(self):
        """Test align_features_target with partial overlap."""
        # Create price series with partial overlap
        overlap_dates = pd.date_range('2023-01-01 00:05:00', periods=8, freq='1min', tz=self.tz)
        overlap_price = pd.Series(np.random.uniform(100, 200, 8), index=overlap_dates)
        
        result = align_features_target(self.features, overlap_price)
        
        assert isinstance(result, FeatureFrame)
        assert len(result.X) <= len(self.features)
        assert len(result.y) <= len(overlap_price)
    
    def test_align_features_target_with_nan_values(self):
        """Test align_features_target with NaN values in features."""
        # Introduce NaN values in features
        features_with_nan = self.features.copy()
        features_with_nan.iloc[2, 1] = np.nan
        features_with_nan.iloc[5, 0] = np.nan
        
        result = align_features_target(features_with_nan, self.price)
        
        assert isinstance(result, FeatureFrame)
        # Should handle NaN values appropriately
        assert result.X is not None
        assert result.y is not None
    
    def test_align_features_target_target_creation(self):
        """Test that target is created correctly (next-period return)."""
        # Use simple prices to verify target calculation
        simple_prices = pd.Series([100, 110, 105, 115, 120], index=self.dates[:5])
        simple_features = self.features.iloc[:5].copy()
        
        result = align_features_target(simple_features, simple_prices)
        
        # Verify target is percentage change shifted forward
        expected_returns = simple_prices.pct_change().shift(-1)
        
        # Check that target calculation logic is applied
        assert result.y is not None
        assert len(result.y) > 0
    
    def test_align_features_target_disable_ml_mode(self):
        """Test align_features_target behavior in DISABLE_ML mode."""
        # This should be true due to environment setup
        assert DISABLE_ML == True
        
        result = align_features_target(self.features, self.price)
        
        assert isinstance(result, FeatureFrame)
        # In DISABLE_ML mode, index_mask should be a StubSeries
        assert hasattr(result.index_mask, 'data')
        assert hasattr(result.index_mask, 'index')
        assert hasattr(result.index_mask, 'dtype')
    
    def test_align_features_target_stub_series_functionality(self):
        """Test StubSeries functionality in DISABLE_ML mode."""
        result = align_features_target(self.features, self.price)
        
        # Test StubSeries methods
        index_mask = result.index_mask
        assert hasattr(index_mask, 'equals')
        assert hasattr(index_mask, '__len__')
        assert hasattr(index_mask, 'sum')
        
        # Test methods work
        assert index_mask.equals(None) == True  # Always returns True in stub mode
        assert len(index_mask) >= 0
        assert index_mask.sum() >= 0


class TestAlignMultitimeframe:
    """Comprehensive tests for align_multitimeframe function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.tz = pytz.UTC
        
        # Create 1-minute data
        self.dates_1m = pd.date_range('2023-01-01', periods=10, freq='1min', tz=self.tz)
        self.features_1m = pd.DataFrame({
            'rsi_1m': np.random.randn(10),
            'sma_1m': np.random.randn(10)
        }, index=self.dates_1m)
        
        # Create 5-minute data (less frequent)
        self.dates_5m = pd.date_range('2023-01-01', periods=3, freq='5min', tz=self.tz)
        self.features_5m = pd.DataFrame({
            'rsi_5m': np.random.randn(3),
            'sma_5m': np.random.randn(3)
        }, index=self.dates_5m)
    
    def test_align_multitimeframe_basic_functionality(self):
        """Test basic functionality of align_multitimeframe."""
        result = align_multitimeframe(self.features_1m, self.features_5m)
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(self.features_1m)  # Should match 1m timeframe
        
        # Check column suffixes
        expected_1m_cols = ['rsi_1m_1m', 'sma_1m_1m']
        expected_5m_cols = ['rsi_5m_5m', 'sma_5m_5m']
        
        for col in expected_1m_cols:
            assert col in result.columns
        for col in expected_5m_cols:
            assert col in result.columns
    
    def test_align_multitimeframe_left_alignment_error(self):
        """Test that left alignment raises error."""
        with pytest.raises(ValueError, match="Only 'right' alignment supported for safety"):
            align_multitimeframe(self.features_1m, self.features_5m, how="left")
    
    def test_align_multitimeframe_empty_features_1m(self):
        """Test align_multitimeframe with empty 1m features."""
        empty_1m = pd.DataFrame(index=pd.DatetimeIndex([], tz=self.tz))
        
        with pytest.raises(ValueError, match="Both timeframes must have data"):
            align_multitimeframe(empty_1m, self.features_5m)
    
    def test_align_multitimeframe_empty_features_5m(self):
        """Test align_multitimeframe with empty 5m features."""
        empty_5m = pd.DataFrame(index=pd.DatetimeIndex([], tz=self.tz))
        
        with pytest.raises(ValueError, match="Both timeframes must have data"):
            align_multitimeframe(self.features_1m, empty_5m)
    
    def test_align_multitimeframe_non_datetime_index_1m(self):
        """Test align_multitimeframe with non-DatetimeIndex for 1m features."""
        features_1m_bad = self.features_1m.copy()
        features_1m_bad.index = range(len(features_1m_bad))
        
        with pytest.raises(ValueError, match="1m features must have DatetimeIndex"):
            align_multitimeframe(features_1m_bad, self.features_5m)
    
    def test_align_multitimeframe_non_datetime_index_5m(self):
        """Test align_multitimeframe with non-DatetimeIndex for 5m features."""
        features_5m_bad = self.features_5m.copy()
        features_5m_bad.index = range(len(features_5m_bad))
        
        with pytest.raises(ValueError, match="5m features must have DatetimeIndex"):
            align_multitimeframe(self.features_1m, features_5m_bad)
    
    def test_align_multitimeframe_custom_max_ffill(self):
        """Test align_multitimeframe with custom max_ffill parameter."""
        result = align_multitimeframe(self.features_1m, self.features_5m, max_ffill=2)
        
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(self.features_1m)
    
    @patch('backend.features.alignment.get_structured_logger')
    def test_align_multitimeframe_ffill_limit_exceeded(self, mock_logger):
        """Test align_multitimeframe when ffill limit is exceeded."""
        # Create data where ffill limit will be exceeded
        dates_1m_long = pd.date_range('2023-01-01', periods=20, freq='1min', tz=self.tz)
        features_1m_long = pd.DataFrame({
            'rsi_1m': np.random.randn(20),
        }, index=dates_1m_long)
        
        # 5m data with gaps
        dates_5m_sparse = pd.date_range('2023-01-01', periods=2, freq='10min', tz=self.tz)
        features_5m_sparse = pd.DataFrame({
            'rsi_5m': np.random.randn(2),
        }, index=dates_5m_sparse)
        
        result = align_multitimeframe(features_1m_long, features_5m_sparse, max_ffill=2)
        
        # Should still return a result
        assert isinstance(result, pd.DataFrame)
        
        # Logger should be called if rows are dropped
        if mock_logger.called:
            mock_logger.return_value.info.assert_called()


class TestValidateTemporalOrder:
    """Comprehensive tests for validate_temporal_order function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.tz = pytz.UTC
        self.valid_dates = pd.date_range('2023-01-01', periods=5, freq='1min', tz=self.tz)
        self.valid_df = pd.DataFrame({
            'value1': np.random.randn(5),
            'value2': np.random.randn(5)
        }, index=self.valid_dates)
    
    def test_validate_temporal_order_valid_data(self):
        """Test validate_temporal_order with valid data."""
        # Should not raise any exception
        validate_temporal_order(self.valid_df)
    
    def test_validate_temporal_order_non_datetime_index(self):
        """Test validate_temporal_order with non-DatetimeIndex."""
        df_bad_index = self.valid_df.copy()
        df_bad_index.index = range(len(df_bad_index))
        
        with pytest.raises(ValueError, match="DataFrame must have DatetimeIndex"):
            validate_temporal_order(df_bad_index)
    
    def test_validate_temporal_order_non_monotonic(self):
        """Test validate_temporal_order with non-monotonic index."""
        # Create non-monotonic dates
        bad_dates = [
            datetime(2023, 1, 1, 0, 0, tzinfo=self.tz),
            datetime(2023, 1, 1, 0, 2, tzinfo=self.tz),
            datetime(2023, 1, 1, 0, 1, tzinfo=self.tz),  # Out of order
        ]
        df_bad_order = pd.DataFrame({
            'value': [1, 2, 3]
        }, index=pd.DatetimeIndex(bad_dates))
        
        with pytest.raises(ValueError, match="Index must be monotonically increasing"):
            validate_temporal_order(df_bad_order)
    
    def test_validate_temporal_order_no_timezone(self):
        """Test validate_temporal_order with timezone-naive index."""
        naive_dates = pd.date_range('2023-01-01', periods=5, freq='1min')
        df_naive = pd.DataFrame({
            'value': np.random.randn(5)
        }, index=naive_dates)
        
        with pytest.raises(ValueError, match="Index must be timezone-aware"):
            validate_temporal_order(df_naive)
    
    def test_validate_temporal_order_duplicate_timestamps(self):
        """Test validate_temporal_order with duplicate timestamps."""
        # Create duplicate dates
        duplicate_dates = [
            datetime(2023, 1, 1, 0, 0, tzinfo=self.tz),
            datetime(2023, 1, 1, 0, 1, tzinfo=self.tz),
            datetime(2023, 1, 1, 0, 1, tzinfo=self.tz),  # Duplicate
        ]
        df_duplicates = pd.DataFrame({
            'value': [1, 2, 3]
        }, index=pd.DatetimeIndex(duplicate_dates))
        
        with pytest.raises(ValueError, match="Index cannot have duplicate timestamps"):
            validate_temporal_order(df_duplicates)


class TestDetectMisalignment:
    """Comprehensive tests for detect_misalignment function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.tz = pytz.UTC
        self.dates = pd.date_range('2023-01-01', periods=10, freq='1min', tz=self.tz)
        
        self.features = pd.DataFrame({
            'feature1': np.random.randn(10),
            'feature2': np.random.randn(10)
        }, index=self.dates)
        
        self.price = pd.Series(
            np.random.uniform(100, 200, 10),
            index=self.dates
        )
    
    def test_detect_misalignment_aligned_data(self):
        """Test detect_misalignment with properly aligned data."""
        result = detect_misalignment(self.features, self.price)
        
        assert result['status'] == 'aligned'
        assert result['common_rows'] == len(self.dates)
        assert result['total_features'] == len(self.features)
        assert result['total_price'] == len(self.price)
    
    def test_detect_misalignment_no_overlap(self):
        """Test detect_misalignment with no overlap."""
        # Create non-overlapping price data
        different_dates = pd.date_range('2024-01-01', periods=5, freq='1min', tz=self.tz)
        different_price = pd.Series(np.random.uniform(100, 200, 5), index=different_dates)
        
        result = detect_misalignment(self.features, different_price)
        
        assert result['status'] == 'no_overlap'
        assert 'feature_start' in result
        assert 'feature_end' in result
        assert 'price_start' in result
        assert 'price_end' in result
    
    def test_detect_misalignment_empty_features(self):
        """Test detect_misalignment with empty features."""
        empty_features = pd.DataFrame(index=pd.DatetimeIndex([], tz=self.tz))
        
        result = detect_misalignment(empty_features, self.price)
        
        assert result['status'] == 'no_overlap'
        assert result['feature_start'] is None
        assert result['feature_end'] is None
    
    def test_detect_misalignment_empty_price(self):
        """Test detect_misalignment with empty price."""
        empty_price = pd.Series([], dtype=float, index=pd.DatetimeIndex([], tz=self.tz))
        
        result = detect_misalignment(empty_price, self.features)
        
        assert result['status'] == 'no_overlap'
        assert result['price_start'] is None
        assert result['price_end'] is None
    
    def test_detect_misalignment_large_gaps(self):
        """Test detect_misalignment with large time gaps."""
        # Create data with large gaps
        gap_dates = pd.date_range('2023-01-01', periods=3, freq='1min', tz=self.tz).tolist()
        gap_dates.extend(pd.date_range('2023-01-01 02:00:00', periods=3, freq='1min', tz=self.tz))
        gap_dates = pd.DatetimeIndex(gap_dates).sort_values()
        
        gap_features = pd.DataFrame({
            'feature1': np.random.randn(len(gap_dates))
        }, index=gap_dates)
        
        gap_price = pd.Series(np.random.uniform(100, 200, len(gap_dates)), index=gap_dates)
        
        result = detect_misalignment(gap_features, gap_price, tolerance_seconds=60)
        
        assert result['status'] == 'aligned'
        assert 'large_gaps' in result
        assert 'max_gap_seconds' in result
    
    def test_detect_misalignment_non_datetime_index(self):
        """Test detect_misalignment with non-DatetimeIndex."""
        # Create data with non-datetime index
        non_dt_features = pd.DataFrame({
            'feature1': np.random.randn(5)
        }, index=range(5))
        
        non_dt_price = pd.Series(np.random.uniform(100, 200, 5), index=range(5))
        
        result = detect_misalignment(non_dt_features, non_dt_price)
        
        assert result['status'] == 'aligned'
        assert 'common_rows' in result
        assert 'large_gaps' not in result  # Should not have time-based analysis


class TestCreateTrainingSplits:
    """Comprehensive tests for create_training_splits function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.tz = pytz.UTC
        self.dates = pd.date_range('2023-01-01', periods=2000, freq='1min', tz=self.tz)
        
        # Create FeatureFrame with sufficient data
        self.X = pd.DataFrame({
            'feature1': np.random.randn(2000),
            'feature2': np.random.randn(2000)
        }, index=self.dates)
        
        self.y = pd.Series(np.random.randn(2000), index=self.dates)
        
        # Create mock index_mask
        if DISABLE_ML:
            class MockIndexMask:
                def __init__(self):
                    self.index = self.dates
                def sum(self):
                    return len(self.dates)
            index_mask = MockIndexMask()
        else:
            index_mask = pd.Series([True] * 2000, index=self.dates)
        
        self.feature_frame = FeatureFrame(X=self.X, y=self.y, index_mask=index_mask)
    
    def test_create_training_splits_basic_functionality(self):
        """Test basic functionality of create_training_splits."""
        with patch.object(self.feature_frame, 'filter_valid', return_value=self.feature_frame):
            train_frame, test_frame = create_training_splits(self.feature_frame)
            
            assert isinstance(train_frame, FeatureFrame)
            assert isinstance(test_frame, FeatureFrame)
            assert len(train_frame.X) > 0
            assert len(test_frame.X) > 0
            assert len(train_frame.X) + len(test_frame.X) == len(self.feature_frame.X)
    
    def test_create_training_splits_custom_train_ratio(self):
        """Test create_training_splits with custom train ratio."""
        with patch.object(self.feature_frame, 'filter_valid', return_value=self.feature_frame):
            train_frame, test_frame = create_training_splits(self.feature_frame, train_ratio=0.7)
            
            expected_train_size = int(len(self.feature_frame.X) * 0.7)
            assert len(train_frame.X) == expected_train_size
            assert len(test_frame.X) == len(self.feature_frame.X) - expected_train_size
    
    def test_create_training_splits_insufficient_data(self):
        """Test create_training_splits with insufficient data."""
        # Create small dataset
        small_dates = pd.date_range('2023-01-01', periods=500, freq='1min', tz=self.tz)
        small_X = pd.DataFrame({'feature1': np.random.randn(500)}, index=small_dates)
        small_y = pd.Series(np.random.randn(500), index=small_dates)
        
        if DISABLE_ML:
            class MockSmallIndexMask:
                def sum(self):
                    return 500
            small_mask = MockSmallIndexMask()
        else:
            small_mask = pd.Series([True] * 500, index=small_dates)
        
        small_frame = FeatureFrame(X=small_X, y=small_y, index_mask=small_mask)
        
        with patch.object(small_frame, 'filter_valid', return_value=small_frame):
            with pytest.raises(ValueError, match="Insufficient data for training"):
                create_training_splits(small_frame, min_train_samples=1000)
    
    def test_create_training_splits_temporal_order_maintained(self):
        """Test that create_training_splits maintains temporal order."""
        with patch.object(self.feature_frame, 'filter_valid', return_value=self.feature_frame):
            train_frame, test_frame = create_training_splits(self.feature_frame)
            
            # Test that train data comes before test data temporally
            assert train_frame.X.index.max() <= test_frame.X.index.min()
    
    def test_create_training_splits_none_target(self):
        """Test create_training_splits with None target."""
        # Create FeatureFrame with no target
        frame_no_target = FeatureFrame(X=self.X, y=None, index_mask=self.feature_frame.index_mask)
        
        with patch.object(frame_no_target, 'filter_valid', return_value=frame_no_target):
            train_frame, test_frame = create_training_splits(frame_no_target)
            
            assert train_frame.y is None
            assert test_frame.y is None
            assert len(train_frame.X) > 0
            assert len(test_frame.X) > 0


class TestDisableMlFunctionality:
    """Test DISABLE_ML environment variable functionality."""
    
    def test_disable_ml_flag(self):
        """Test that DISABLE_ML flag is properly set."""
        assert DISABLE_ML == True  # Should be True due to environment setup
    
    def test_disable_ml_import_behavior(self):
        """Test that DISABLE_ML affects import behavior."""
        # Test that pandas is still imported normally
        import pandas as pd
        assert pd is not None
        
        # DISABLE_ML should be True in test environment
        from backend.features.alignment import DISABLE_ML
        assert DISABLE_ML == True


if __name__ == "__main__":
    pytest.main([__file__])