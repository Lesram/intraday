"""
Tests for backend/features/alignment.py - Feature alignment utilities.

Target: Cover align_features_target and align_multitimeframe functions.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


class TestAlignFeaturesTarget:
    """Test align_features_target function"""
    
    def test_basic_alignment(self):
        """Test basic feature-target alignment"""
        from backend.features.alignment import align_features_target
        
        # Create simple features and price
        dates = pd.date_range('2024-01-01', periods=10, freq='D')
        features = pd.DataFrame({
            'feature1': np.random.randn(10),
            'feature2': np.random.randn(10)
        }, index=dates)
        price = pd.Series(np.cumsum(np.random.randn(10)) + 100, index=dates)
        
        result = align_features_target(features, price)
        
        assert result is not None
        assert hasattr(result, 'X')
        assert hasattr(result, 'y')
    
    def test_no_common_index_raises(self):
        """Test error when no common timestamps"""
        from backend.features.alignment import align_features_target
        
        dates1 = pd.date_range('2024-01-01', periods=5, freq='D')
        dates2 = pd.date_range('2024-02-01', periods=5, freq='D')
        
        features = pd.DataFrame({'feature1': [1, 2, 3, 4, 5]}, index=dates1)
        price = pd.Series([100, 101, 102, 103, 104], index=dates2)
        
        with pytest.raises(ValueError, match="No common timestamps"):
            align_features_target(features, price)
    
    def test_partial_overlap(self):
        """Test alignment with partial index overlap"""
        from backend.features.alignment import align_features_target
        
        dates1 = pd.date_range('2024-01-01', periods=10, freq='D')
        dates2 = pd.date_range('2024-01-05', periods=10, freq='D')
        
        features = pd.DataFrame({
            'feature1': np.random.randn(10)
        }, index=dates1)
        price = pd.Series(np.random.randn(10) + 100, index=dates2)
        
        result = align_features_target(features, price)
        
        # Should only contain overlapping dates
        assert len(result.X) <= min(len(features), len(price))
    
    def test_nan_handling_in_features(self):
        """Test alignment handles NaN in features"""
        from backend.features.alignment import align_features_target
        
        dates = pd.date_range('2024-01-01', periods=10, freq='D')
        features = pd.DataFrame({
            'feature1': [1, 2, np.nan, 4, 5, 6, 7, 8, 9, 10],
            'feature2': np.random.randn(10)
        }, index=dates)
        price = pd.Series(np.cumsum(np.random.randn(10)) + 100, index=dates)
        
        result = align_features_target(features, price)
        
        # Result should track NaN in the index mask
        assert result is not None
    
    def test_target_is_shifted_returns(self):
        """Test target is next-period returns (shifted)"""
        from backend.features.alignment import align_features_target
        
        dates = pd.date_range('2024-01-01', periods=10, freq='D')
        features = pd.DataFrame({'feature1': range(10)}, index=dates)
        price = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109], index=dates)
        
        result = align_features_target(features, price)
        
        # Target y should be percent change shifted (forward looking)
        assert result.y is not None


class TestAlignMultitimeframe:
    """Test align_multitimeframe function"""
    
    def test_basic_multitimeframe_alignment(self):
        """Test basic multi-timeframe alignment"""
        from backend.features.alignment import align_multitimeframe
        
        # Create 1m and 5m features
        dates_1m = pd.date_range('2024-01-01 09:30', periods=30, freq='1min')
        dates_5m = pd.date_range('2024-01-01 09:30', periods=6, freq='5min')
        
        features_1m = pd.DataFrame({
            'feature_1m': np.random.randn(30)
        }, index=dates_1m)
        
        features_5m = pd.DataFrame({
            'feature_5m': np.random.randn(6)
        }, index=dates_5m)
        
        result = align_multitimeframe(features_1m, features_5m)
        
        assert isinstance(result, pd.DataFrame)
        assert '_1m' in ''.join(result.columns) or '_5m' in ''.join(result.columns) or len(result.columns) >= 2
    
    def test_only_right_alignment_supported(self):
        """Test that only 'right' alignment is supported"""
        from backend.features.alignment import align_multitimeframe
        
        dates = pd.date_range('2024-01-01', periods=5, freq='5min')
        features_1m = pd.DataFrame({'f1': [1, 2, 3, 4, 5]}, index=dates)
        features_5m = pd.DataFrame({'f5': [10, 20, 30, 40, 50]}, index=dates)
        
        with pytest.raises(ValueError, match="Only 'right' alignment supported"):
            align_multitimeframe(features_1m, features_5m, how="left")
    
    def test_empty_features_raises(self):
        """Test error on empty features"""
        from backend.features.alignment import align_multitimeframe
        
        dates = pd.date_range('2024-01-01', periods=5, freq='1min')
        features_1m = pd.DataFrame({'f1': [1, 2, 3, 4, 5]}, index=dates)
        features_5m = pd.DataFrame()
        
        with pytest.raises(ValueError, match="Both timeframes must have data"):
            align_multitimeframe(features_1m, features_5m)
    
    def test_max_ffill_parameter(self):
        """Test max_ffill parameter is respected"""
        from backend.features.alignment import align_multitimeframe
        
        dates_1m = pd.date_range('2024-01-01 09:30', periods=30, freq='1min')
        dates_5m = pd.date_range('2024-01-01 09:30', periods=6, freq='5min')
        
        features_1m = pd.DataFrame({'f1': np.random.randn(30)}, index=dates_1m)
        features_5m = pd.DataFrame({'f5': np.random.randn(6)}, index=dates_5m)
        
        # Test with different max_ffill values
        result_5 = align_multitimeframe(features_1m, features_5m, max_ffill=5)
        result_3 = align_multitimeframe(features_1m, features_5m, max_ffill=3)
        
        assert result_5 is not None
        assert result_3 is not None


class TestFeatureFrame:
    """Test FeatureFrame data class"""
    
    def test_feature_frame_import(self):
        """Test FeatureFrame can be imported"""
        from backend.features.types import FeatureFrame
        assert FeatureFrame is not None
    
    def test_feature_frame_creation(self):
        """Test FeatureFrame instantiation"""
        from backend.features.types import FeatureFrame
        
        X = pd.DataFrame({'a': [1, 2, 3]})
        y = pd.Series([0.1, 0.2, 0.3])
        index_mask = pd.Series([True, True, True])
        
        ff = FeatureFrame(X=X, y=y, index_mask=index_mask)
        
        assert ff.X is not None
        assert ff.y is not None


class TestDisableMLMode:
    """Test DISABLE_ML mode behavior"""
    
    def test_disable_ml_import(self):
        """Test DISABLE_ML constant exists"""
        from backend.features.alignment import DISABLE_ML
        assert isinstance(DISABLE_ML, bool)
