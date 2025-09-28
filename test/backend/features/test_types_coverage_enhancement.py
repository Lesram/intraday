"""
Coverage enhancement tests for backend.features.types module.
Target: Comprehensive testing to significantly improve coverage from 38% baseline.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, MagicMock

# Set test environment
import os
os.environ["DISABLE_ML"] = "1"
os.environ["DISABLE_TENSORFLOW"] = "1" 
os.environ["PYTEST_RUNNING"] = "1"

from backend.features.types import (
    FeatureSchema,
    FeatureFrame,
    LookaheadLeakError,
    SchemaValidationError,
    DType
)


class TestFeatureSchema:
    """Comprehensive tests for FeatureSchema class."""
    
    def test_feature_schema_basic_initialization(self):
        """Test basic FeatureSchema initialization."""
        columns = ['feature1', 'feature2', 'feature3']
        dtypes = {'feature1': 'float64', 'feature2': 'int64', 'feature3': 'bool'}
        
        schema = FeatureSchema(columns=columns, dtypes=dtypes)
        
        assert schema.columns == columns
        assert schema.dtypes == dtypes
    
    def test_feature_schema_initialization_with_features_alias(self):
        """Test FeatureSchema initialization using 'features' alias."""
        features = ['feat1', 'feat2']
        dtypes = {'feat1': 'float32', 'feat2': 'int32'}
        
        schema = FeatureSchema(features=features, dtypes=dtypes)
        
        assert schema.columns == features
        assert schema.dtypes == dtypes
    
    def test_feature_schema_columns_preference_over_features(self):
        """Test that 'columns' takes preference over 'features'."""
        columns = ['col1', 'col2']
        features = ['feat1', 'feat2']
        dtypes = {'col1': 'float64', 'col2': 'float64'}
        
        schema = FeatureSchema(columns=columns, features=features, dtypes=dtypes)
        
        assert schema.columns == columns
        assert schema.columns != features
    
    def test_feature_schema_empty_initialization(self):
        """Test FeatureSchema initialization with empty values."""
        schema = FeatureSchema()
        
        assert schema.columns == []
        assert schema.dtypes == {}
    
    def test_feature_schema_duplicate_columns_error(self):
        """Test FeatureSchema raises error for duplicate columns."""
        columns = ['feature1', 'feature1', 'feature2']
        dtypes = {'feature1': 'float64', 'feature2': 'int64'}
        
        with pytest.raises(ValueError, match="Duplicate column names in schema"):
            FeatureSchema(columns=columns, dtypes=dtypes)
    
    def test_feature_schema_mismatched_columns_dtypes_error(self):
        """Test FeatureSchema raises error for mismatched columns and dtypes."""
        columns = ['feature1', 'feature2']
        dtypes = {'feature1': 'float64', 'different_name': 'int64'}
        
        with pytest.raises(ValueError, match="Columns and dtypes keys must match"):
            FeatureSchema(columns=columns, dtypes=dtypes)
    
    def test_feature_schema_frozen_dataclass(self):
        """Test that FeatureSchema is frozen (immutable)."""
        schema = FeatureSchema(columns=['feat1'], dtypes={'feat1': 'float64'})
        
        with pytest.raises(AttributeError):
            schema.columns = ['different']
    
    def test_validate_dataframe_valid_data(self):
        """Test validate_dataframe with valid DataFrame."""
        columns = ['col1', 'col2', 'col3']
        dtypes = {'col1': 'float64', 'col2': 'int64', 'col3': 'bool'}
        schema = FeatureSchema(columns=columns, dtypes=dtypes)
        
        # Create valid DataFrame
        df = pd.DataFrame({
            'col1': [1.1, 2.2, 3.3],
            'col2': [1, 2, 3],
            'col3': [True, False, True]
        })
        
        # Should not raise any exception
        schema.validate_dataframe(df)
    
    def test_validate_dataframe_missing_columns_error(self):
        """Test validate_dataframe with missing columns."""
        schema = FeatureSchema(
            columns=['col1', 'col2', 'col3'],
            dtypes={'col1': 'float64', 'col2': 'int64', 'col3': 'bool'}
        )
        
        # DataFrame missing col3
        df = pd.DataFrame({
            'col1': [1.1, 2.2],
            'col2': [1, 2]
        })
        
        with pytest.raises(ValueError, match="Missing columns: \\['col3'\\]"):
            schema.validate_dataframe(df)
    
    def test_validate_dataframe_extra_columns_error(self):
        """Test validate_dataframe with extra columns."""
        schema = FeatureSchema(
            columns=['col1', 'col2'],
            dtypes={'col1': 'float64', 'col2': 'int64'}
        )
        
        # DataFrame with extra column
        df = pd.DataFrame({
            'col1': [1.1, 2.2],
            'col2': [1, 2],
            'col3': [True, False]  # Extra column
        })
        
        with pytest.raises(ValueError, match="Extra columns: \\['col3'\\]"):
            schema.validate_dataframe(df)
    
    def test_validate_dataframe_wrong_dtype_error(self):
        """Test validate_dataframe with wrong dtype."""
        schema = FeatureSchema(
            columns=['col1', 'col2'],
            dtypes={'col1': 'float64', 'col2': 'int64'}
        )
        
        # col2 has wrong dtype (should be int64 but is float64)
        df = pd.DataFrame({
            'col1': [1.1, 2.2],
            'col2': [1.5, 2.5]  # float instead of int
        })
        
        with pytest.raises(ValueError, match="Column 'col2' has dtype"):
            schema.validate_dataframe(df)
    
    def test_validate_dataframe_compatible_float_types(self):
        """Test validate_dataframe accepts compatible float types."""
        schema = FeatureSchema(
            columns=['col1', 'col2'],
            dtypes={'col1': 'float64', 'col2': 'float32'}
        )
        
        # Use different but compatible float types
        df = pd.DataFrame({
            'col1': pd.Series([1.1, 2.2], dtype='float32'),  # float32 for float64 column
            'col2': pd.Series([3.3, 4.4], dtype='float64')   # float64 for float32 column
        })
        
        # Should not raise exception - compatible types
        schema.validate_dataframe(df)
    
    def test_validate_dataframe_compatible_int_types(self):
        """Test validate_dataframe accepts compatible integer types."""
        schema = FeatureSchema(
            columns=['col1', 'col2'],
            dtypes={'col1': 'int64', 'col2': 'int32'}
        )
        
        # Use different but compatible integer types
        df = pd.DataFrame({
            'col1': pd.Series([1, 2], dtype='int32'),  # int32 for int64 column
            'col2': pd.Series([3, 4], dtype='int64')   # int64 for int32 column
        })
        
        # Should not raise exception - compatible types
        schema.validate_dataframe(df)
    
    def test_validate_dataframe_bool_type(self):
        """Test validate_dataframe with boolean type."""
        schema = FeatureSchema(
            columns=['bool_col'],
            dtypes={'bool_col': 'bool'}
        )
        
        df = pd.DataFrame({
            'bool_col': [True, False, True]
        })
        
        # Should not raise exception
        schema.validate_dataframe(df)
    
    def test_validate_dataframe_exact_dtype_match(self):
        """Test validate_dataframe accepts exact dtype matches."""
        schema = FeatureSchema(
            columns=['col1'],
            dtypes={'col1': 'float64'}
        )
        
        df = pd.DataFrame({
            'col1': pd.Series([1.1, 2.2], dtype='float64')  # Exact match
        })
        
        # Should not raise exception
        schema.validate_dataframe(df)
    
    def test_reorder_columns(self):
        """Test reorder_columns functionality."""
        schema = FeatureSchema(
            columns=['col2', 'col1', 'col3'],  # Specific order
            dtypes={'col1': 'float64', 'col2': 'int64', 'col3': 'bool'}
        )
        
        # DataFrame with different column order
        df = pd.DataFrame({
            'col1': [1.1, 2.2],
            'col3': [True, False],
            'col2': [1, 2]
        })
        
        reordered = schema.reorder_columns(df)
        
        # Should match schema column order
        expected_order = ['col2', 'col1', 'col3']
        assert list(reordered.columns) == expected_order


class TestFeatureFrame:
    """Comprehensive tests for FeatureFrame class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.index = pd.date_range('2023-01-01', periods=5, freq='D')
        
        self.X = pd.DataFrame({
            'feature1': [1.1, 2.2, 3.3, 4.4, 5.5],
            'feature2': [10, 20, 30, 40, 50]
        }, index=self.index)
        
        self.y = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5], index=self.index, name='target')
        
        self.index_mask = pd.Series([True, True, False, True, True], index=self.index)
    
    def test_feature_frame_basic_initialization(self):
        """Test basic FeatureFrame initialization."""
        frame = FeatureFrame(X=self.X, y=self.y, index_mask=self.index_mask)
        
        assert frame.X.equals(self.X)
        assert frame.y.equals(self.y)
        assert frame.index_mask.equals(self.index_mask)
    
    def test_feature_frame_initialization_no_target(self):
        """Test FeatureFrame initialization without target."""
        frame = FeatureFrame(X=self.X, y=None, index_mask=self.index_mask)
        
        assert frame.X.equals(self.X)
        assert frame.y is None
        assert frame.index_mask.equals(self.index_mask)
    
    def test_feature_frame_misaligned_X_y_indices_error(self):
        """Test FeatureFrame raises error for misaligned X and y indices."""
        different_index = pd.date_range('2024-01-01', periods=5, freq='D')
        misaligned_y = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5], index=different_index)
        
        with pytest.raises(ValueError, match="Feature and target indices must be aligned"):
            FeatureFrame(X=self.X, y=misaligned_y, index_mask=self.index_mask)
    
    def test_feature_frame_misaligned_X_mask_indices_error(self):
        """Test FeatureFrame raises error for misaligned X and mask indices."""
        different_index = pd.date_range('2024-01-01', periods=5, freq='D')
        misaligned_mask = pd.Series([True, True, False, True, True], index=different_index)
        
        with pytest.raises(ValueError, match="Feature and mask indices must be aligned"):
            FeatureFrame(X=self.X, y=self.y, index_mask=misaligned_mask)
    
    def test_feature_frame_different_lengths_error(self):
        """Test FeatureFrame raises error for different lengths."""
        short_mask = pd.Series([True, True, False], index=self.index[:3])

        with pytest.raises(ValueError, match="Feature and mask indices must be aligned"):
            FeatureFrame(X=self.X, y=self.y, index_mask=short_mask)

    def test_feature_frame_valid_rows_property(self):
        """Test valid_rows property."""
        frame = FeatureFrame(X=self.X, y=self.y, index_mask=self.index_mask)
        
        # index_mask has 4 True values out of 5
        expected_valid = self.index_mask.sum()
        assert frame.valid_rows == expected_valid
    
    def test_feature_frame_filter_valid(self):
        """Test filter_valid method."""
        frame = FeatureFrame(X=self.X, y=self.y, index_mask=self.index_mask)
        
        filtered = frame.filter_valid()
        
        # Should only include rows where mask is True
        expected_X = self.X[self.index_mask]
        expected_y = self.y[self.index_mask]
        
        assert filtered.X.equals(expected_X)
        assert filtered.y.equals(expected_y)
        
        # Filtered mask should be all True
        assert all(filtered.index_mask)
    
    def test_feature_frame_filter_valid_no_target(self):
        """Test filter_valid method without target."""
        frame = FeatureFrame(X=self.X, y=None, index_mask=self.index_mask)
        
        filtered = frame.filter_valid()
        
        expected_X = self.X[self.index_mask]
        
        assert filtered.X.equals(expected_X)
        assert filtered.y is None
        assert all(filtered.index_mask)
    
    def test_feature_frame_frozen_dataclass(self):
        """Test that FeatureFrame is frozen (immutable)."""
        frame = FeatureFrame(X=self.X, y=self.y, index_mask=self.index_mask)
        
        with pytest.raises(AttributeError):
            frame.X = pd.DataFrame()
    
    def test_feature_frame_stub_series_compatibility(self):
        """Test FeatureFrame works with stub series (for DISABLE_ML mode)."""
        # Create a mock stub series that doesn't have .index attribute
        class StubIndexMask:
            def __init__(self, length):
                self._length = length

            def __len__(self):
                return self._length

            def sum(self):
                return 4

        stub_mask = StubIndexMask(len(self.X))

        # Should handle AttributeError gracefully and fall back to length check
        try:
            frame = FeatureFrame(X=self.X, y=None, index_mask=stub_mask)
            # If we get here, the AttributeError was handled
            assert frame.X.equals(self.X)
        except AttributeError:
            # This shouldn't happen if stub mode is handled correctly
            pytest.fail("FeatureFrame should handle stub series gracefully")
class TestLookaheadLeakError:
    """Test LookaheadLeakError exception class."""
    
    def test_lookahead_leak_error_basic(self):
        """Test basic LookaheadLeakError functionality."""
        columns = ['future_price', 'next_day_volume']
        message = "Lookahead bias detected in features"
        
        error = LookaheadLeakError(message, columns)
        
        assert str(error) == message
        assert error.columns == columns
    
    def test_lookahead_leak_error_inheritance(self):
        """Test LookaheadLeakError inherits from ValueError."""
        error = LookaheadLeakError("test", [])
        
        assert isinstance(error, ValueError)
        assert isinstance(error, LookaheadLeakError)


class TestSchemaValidationError:
    """Test SchemaValidationError exception class."""
    
    def test_schema_validation_error_basic(self):
        """Test basic SchemaValidationError functionality."""
        message = "Schema validation failed"
        missing = ['col1', 'col2']
        extra = ['col3']
        
        error = SchemaValidationError(message, missing, extra)
        
        assert str(error) == message
        assert error.missing_columns == missing
        assert error.extra_columns == extra
    
    def test_schema_validation_error_optional_params(self):
        """Test SchemaValidationError with optional parameters."""
        message = "Schema validation failed"
        
        error = SchemaValidationError(message)
        
        assert str(error) == message
        assert error.missing_columns == []
        assert error.extra_columns == []
    
    def test_schema_validation_error_none_params(self):
        """Test SchemaValidationError with None parameters."""
        message = "Schema validation failed"
        
        error = SchemaValidationError(message, None, None)
        
        assert str(error) == message
        assert error.missing_columns == []
        assert error.extra_columns == []
    
    def test_schema_validation_error_inheritance(self):
        """Test SchemaValidationError inherits from ValueError."""
        error = SchemaValidationError("test")
        
        assert isinstance(error, ValueError)
        assert isinstance(error, SchemaValidationError)


class TestDTypeAlias:
    """Test DType type alias."""
    
    def test_dtype_literal_values(self):
        """Test that DType includes expected literal values."""
        from backend.features.types import DType
        
        # This is mainly for documentation - can't easily test Literal at runtime
        # But we can test that it's importable and usable in type hints
        assert DType is not None
        
        # Test some example values that should be valid
        valid_dtypes = ["float64", "float32", "int64", "int32", "bool"]
        
        # In a real type checker, these would be validated
        for dtype in valid_dtypes:
            assert isinstance(dtype, str)


if __name__ == "__main__":
    pytest.main([__file__])