"""
Comprehensive tests for backend/ml/data_processing.py
Tests ML data processing pipeline components.
Target: Increase coverage from 0% to 80%+
"""

import pytest
import numpy as np
import pandas as pd

from backend.ml.data_processing import (
    SimpleScaler,
    SimpleImputer,
    DataProcessor,
    DataPipeline,
    create_sample_data,
    batch_process_data,
)

pytestmark = pytest.mark.unit


# ============================================================================
# SIMPLE SCALER TESTS
# ============================================================================

class TestSimpleScaler:
    """Tests for SimpleScaler class."""

    def test_standard_scaler_fit(self):
        """Test standard scaler fit method."""
        scaler = SimpleScaler(method='standard')
        X = np.array([[1, 2], [3, 4], [5, 6]])
        
        scaler.fit(X)
        
        assert scaler.fitted is True
        assert scaler.mean_ is not None
        assert scaler.std_ is not None
        np.testing.assert_array_almost_equal(scaler.mean_, [3, 4])

    def test_standard_scaler_transform(self):
        """Test standard scaler transform method."""
        scaler = SimpleScaler(method='standard')
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        
        scaler.fit(X)
        transformed = scaler.transform(X)
        
        # Mean should be ~0
        assert abs(np.mean(transformed)) < 0.01

    def test_standard_scaler_fit_transform(self):
        """Test standard scaler fit_transform method."""
        scaler = SimpleScaler(method='standard')
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        
        transformed = scaler.fit_transform(X)
        
        assert scaler.fitted is True
        assert transformed.shape == X.shape

    def test_minmax_scaler_fit(self):
        """Test minmax scaler fit method."""
        scaler = SimpleScaler(method='minmax')
        X = np.array([[0.0, 10.0], [5.0, 20.0], [10.0, 30.0]])
        
        scaler.fit(X)
        
        assert scaler.fitted is True
        np.testing.assert_array_equal(scaler.min_, [0, 10])
        np.testing.assert_array_equal(scaler.max_, [10, 30])

    def test_minmax_scaler_transform(self):
        """Test minmax scaler transform method."""
        scaler = SimpleScaler(method='minmax')
        X = np.array([[0.0, 10.0], [5.0, 20.0], [10.0, 30.0]])
        
        scaler.fit(X)
        transformed = scaler.transform(X)
        
        # Values should be between 0 and 1
        assert transformed.min() >= 0
        assert transformed.max() <= 1.0 + 1e-6

    def test_robust_scaler_fit(self):
        """Test robust scaler fit method."""
        scaler = SimpleScaler(method='robust')
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [100.0, 200.0]])  # With outlier
        
        scaler.fit(X)
        
        assert scaler.fitted is True
        assert scaler.median_ is not None
        assert scaler.mad_ is not None

    def test_robust_scaler_transform(self):
        """Test robust scaler transform method."""
        scaler = SimpleScaler(method='robust')
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        
        transformed = scaler.fit_transform(X)
        
        assert transformed.shape == X.shape

    def test_transform_without_fit_raises(self):
        """Test that transform without fit raises ValueError."""
        scaler = SimpleScaler()
        X = np.array([[1, 2], [3, 4]])
        
        with pytest.raises(ValueError, match="Scaler not fitted"):
            scaler.transform(X)


# ============================================================================
# SIMPLE IMPUTER TESTS
# ============================================================================

class TestSimpleImputer:
    """Tests for SimpleImputer class."""

    def test_mean_imputer_fit(self):
        """Test mean imputer fit method."""
        imputer = SimpleImputer(strategy='mean')
        X = np.array([[1.0, np.nan], [2.0, 4.0], [np.nan, 6.0]])
        
        imputer.fit(X)
        
        assert imputer.fitted is True
        assert imputer.fill_value_ is not None

    def test_mean_imputer_transform(self):
        """Test mean imputer transform method."""
        imputer = SimpleImputer(strategy='mean')
        X = np.array([[1.0, np.nan], [2.0, 4.0], [3.0, 6.0]])
        
        imputer.fit(X)
        transformed = imputer.transform(X)
        
        # Check no NaN values remain
        assert not np.isnan(transformed).any()
        # Check mean was used for filling
        assert transformed[0, 1] == 5.0  # Mean of 4 and 6

    def test_median_imputer_fit(self):
        """Test median imputer fit method."""
        imputer = SimpleImputer(strategy='median')
        X = np.array([[1.0, np.nan], [2.0, 4.0], [3.0, 8.0]])
        
        imputer.fit(X)
        
        assert imputer.fitted is True

    def test_median_imputer_transform(self):
        """Test median imputer transform method."""
        imputer = SimpleImputer(strategy='median')
        X = np.array([[1.0, np.nan], [2.0, 4.0], [3.0, 8.0]])
        
        imputer.fit(X)
        transformed = imputer.transform(X)
        
        assert not np.isnan(transformed).any()
        # Median of 4 and 8 is 6
        assert transformed[0, 1] == 6.0

    def test_most_frequent_imputer(self):
        """Test most_frequent imputer (uses median for numeric)."""
        imputer = SimpleImputer(strategy='most_frequent')
        X = np.array([[1.0, np.nan], [2.0, 4.0], [3.0, 8.0]])
        
        imputer.fit(X)
        transformed = imputer.transform(X)
        
        assert not np.isnan(transformed).any()

    def test_imputer_1d_input(self):
        """Test imputer with 1D input."""
        imputer = SimpleImputer(strategy='mean')
        X = np.array([1.0, np.nan, 3.0, 4.0])
        
        imputer.fit(X)
        transformed = imputer.transform(X)
        
        assert len(transformed) == 4
        assert not np.isnan(transformed).any()

    def test_fit_transform(self):
        """Test fit_transform method."""
        imputer = SimpleImputer(strategy='mean')
        X = np.array([[1.0, np.nan], [2.0, 4.0], [3.0, 6.0]])
        
        transformed = imputer.fit_transform(X)
        
        assert imputer.fitted is True
        assert not np.isnan(transformed).any()

    def test_transform_without_fit_raises(self):
        """Test that transform without fit raises ValueError."""
        imputer = SimpleImputer()
        X = np.array([[1, 2], [3, 4]])
        
        with pytest.raises(ValueError, match="Imputer not fitted"):
            imputer.transform(X)

    def test_all_nan_column_uses_zero(self):
        """Test that all-NaN column uses 0 as fill value."""
        imputer = SimpleImputer(strategy='mean')
        X = np.array([[1.0, np.nan], [2.0, np.nan], [3.0, np.nan]])
        
        imputer.fit(X)
        transformed = imputer.transform(X)
        
        # All NaN column should be filled with 0
        assert transformed[0, 1] == 0.0


# ============================================================================
# DATA PROCESSOR TESTS
# ============================================================================

class TestDataProcessor:
    """Tests for DataProcessor class."""

    @pytest.fixture
    def sample_data(self):
        """Create sample market data for testing."""
        dates = pd.date_range('2023-01-01', periods=50, freq='h')
        return pd.DataFrame({
            'open': np.random.uniform(100, 110, 50),
            'high': np.random.uniform(110, 120, 50),
            'low': np.random.uniform(90, 100, 50),
            'close': np.random.uniform(100, 110, 50),
            'volume': np.random.randint(1000, 10000, 50)
        }, index=dates)

    @pytest.fixture
    def processor(self):
        """Create DataProcessor instance."""
        return DataProcessor()

    def test_init_default_config(self):
        """Test initialization with default config."""
        processor = DataProcessor()
        
        assert processor.config == {}
        assert processor.is_fitted is False

    def test_init_custom_config(self):
        """Test initialization with custom config."""
        config = {'scaling_method': 'minmax'}
        processor = DataProcessor(config=config)
        
        assert processor.config == config

    def test_clean_data_basic(self, processor, sample_data):
        """Test basic data cleaning."""
        cleaned = processor.clean_data(sample_data)
        
        assert len(cleaned) <= len(sample_data)
        assert not cleaned.duplicated().any()

    def test_clean_data_removes_duplicates(self, processor):
        """Test that duplicates are removed."""
        dates = pd.date_range('2023-01-01', periods=10, freq='h')
        data = pd.DataFrame({
            'open': [100] * 10,
            'close': [100] * 10
        }, index=dates)
        # Add duplicates
        data = pd.concat([data, data])
        
        cleaned = processor.clean_data(data)
        
        # Duplicates should be removed
        assert len(cleaned) < len(data)

    def test_clean_data_handles_missing_values(self, processor):
        """Test handling of missing values."""
        dates = pd.date_range('2023-01-01', periods=10, freq='h')
        data = pd.DataFrame({
            'open': [100, np.nan, 102, 103, np.nan, 105, 106, 107, 108, 109],
            'close': [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
            'volume': [1000] * 10
        }, index=dates)
        
        cleaned = processor.clean_data(data)
        
        # NaN values should be filled
        assert not cleaned['open'].isnull().any()

    def test_clean_data_empty_raises(self, processor):
        """Test that empty data raises ValueError."""
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.clean_data(pd.DataFrame())

    def test_clean_data_none_raises(self, processor):
        """Test that None data raises ValueError."""
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.clean_data(None)

    def test_preprocess_data_basic(self, processor, sample_data):
        """Test basic preprocessing."""
        processed = processor.preprocess_data(sample_data, fit=True)
        
        assert processor.is_fitted is True
        assert len(processed) == len(sample_data)

    def test_preprocess_data_with_timestamp_column(self, processor):
        """Test preprocessing with timestamp column."""
        data = pd.DataFrame({
            'timestamp': pd.date_range('2023-01-01', periods=10, freq='h'),
            'close': np.random.uniform(100, 110, 10)
        })
        
        processed = processor.preprocess_data(data, fit=True)
        
        assert isinstance(processed.index, pd.DatetimeIndex)

    def test_preprocess_data_with_date_column(self, processor):
        """Test preprocessing with date column."""
        data = pd.DataFrame({
            'date': pd.date_range('2023-01-01', periods=10, freq='D'),
            'close': np.random.uniform(100, 110, 10)
        })
        
        processed = processor.preprocess_data(data, fit=True)
        
        assert isinstance(processed.index, pd.DatetimeIndex)

    def test_preprocess_data_fit_false_without_scaler_raises(self, processor, sample_data):
        """Test that fit=False without fitted scaler raises."""
        with pytest.raises(ValueError, match="Scaler not fitted"):
            processor.preprocess_data(sample_data, fit=False)

    def test_preprocess_data_fit_false_with_scaler(self, processor, sample_data):
        """Test fit=False after fitting."""
        # First fit
        processor.preprocess_data(sample_data, fit=True)
        
        # Then transform with fit=False
        processed = processor.preprocess_data(sample_data, fit=False)
        
        assert len(processed) == len(sample_data)

    def test_engineer_features_creates_indicators(self, processor, sample_data):
        """Test feature engineering creates technical indicators."""
        features = processor.engineer_features(sample_data)
        
        # Check returns were calculated
        assert 'returns' in features.columns
        assert 'log_returns' in features.columns
        
        # Check SMAs
        assert 'sma_5' in features.columns
        assert 'sma_20' in features.columns
        
        # Check EMAs
        assert 'ema_10' in features.columns
        
        # Check volatility
        assert 'volatility_10' in features.columns
        
        # Check RSI
        assert 'rsi' in features.columns

    def test_engineer_features_volume_indicators(self, processor, sample_data):
        """Test volume-based features."""
        features = processor.engineer_features(sample_data)
        
        assert 'volume_sma_10' in features.columns
        assert 'volume_ratio' in features.columns
        assert 'price_volume' in features.columns

    def test_engineer_features_ohlc_indicators(self, processor, sample_data):
        """Test OHLC-based features."""
        features = processor.engineer_features(sample_data)
        
        assert 'true_range' in features.columns
        assert 'atr' in features.columns
        assert 'price_position' in features.columns

    def test_engineer_features_empty_returns_same(self, processor):
        """Test that empty data returns same data."""
        result = processor.engineer_features(pd.DataFrame())
        
        assert result.empty

    def test_engineer_features_none_returns_same(self, processor):
        """Test that None returns None."""
        result = processor.engineer_features(None)
        
        assert result is None

    def test_normalize_data_standard(self, processor, sample_data):
        """Test standard normalization."""
        normalized = processor.normalize_data(sample_data, method='standard')
        
        assert len(normalized) == len(sample_data)

    def test_normalize_data_minmax(self, processor, sample_data):
        """Test minmax normalization."""
        normalized = processor.normalize_data(sample_data, method='minmax')
        
        # Values should be in [0, 1] range
        numeric_cols = normalized.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            assert normalized[col].min() >= -1e-6
            assert normalized[col].max() <= 1.0 + 1e-6

    def test_normalize_data_robust(self, processor, sample_data):
        """Test robust normalization."""
        normalized = processor.normalize_data(sample_data, method='robust')
        
        assert len(normalized) == len(sample_data)

    def test_normalize_data_invalid_method(self, processor, sample_data):
        """Test invalid normalization method."""
        with pytest.raises(ValueError, match="Unknown normalization method"):
            processor.normalize_data(sample_data, method='invalid')

    def test_normalize_data_empty_raises(self, processor):
        """Test normalization of empty data raises."""
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.normalize_data(pd.DataFrame())

    def test_validate_data_valid(self, processor, sample_data):
        """Test validation of valid data."""
        result = processor.validate_data(sample_data)
        
        assert result['valid'] is True
        assert result['shape'] == sample_data.shape
        assert 'missing_values' in result
        assert 'duplicates' in result

    def test_validate_data_none(self, processor):
        """Test validation of None data."""
        result = processor.validate_data(None)
        
        assert result['valid'] is False
        assert 'error' in result

    def test_validate_data_empty(self, processor):
        """Test validation of empty data."""
        result = processor.validate_data(pd.DataFrame())
        
        assert result['valid'] is False
        assert 'error' in result

    def test_validate_data_negative_prices(self, processor):
        """Test validation detects negative prices."""
        data = pd.DataFrame({
            'close': [100, -50, 102],
            'open': [100, 101, 102]
        })
        
        result = processor.validate_data(data)
        
        assert result['valid'] is False
        assert 'negative_prices' in result

    def test_validate_data_infinite_values(self, processor):
        """Test validation detects infinite values."""
        data = pd.DataFrame({
            'close': [100, np.inf, 102],
            'open': [100, 101, 102]
        })
        
        result = processor.validate_data(data)
        
        assert result['valid'] is False
        assert 'infinite_values' in result

    def test_transform_data_log(self, processor, sample_data):
        """Test log transformation."""
        transformed = processor.transform_data(sample_data, ['log'])
        
        # Should have log columns
        log_cols = [c for c in transformed.columns if '_log' in c]
        assert len(log_cols) > 0

    def test_transform_data_diff(self, processor, sample_data):
        """Test diff transformation."""
        transformed = processor.transform_data(sample_data, ['diff'])
        
        # Should have diff columns
        diff_cols = [c for c in transformed.columns if '_diff' in c]
        assert len(diff_cols) > 0

    def test_transform_data_pct_change(self, processor, sample_data):
        """Test pct_change transformation."""
        transformed = processor.transform_data(sample_data, ['pct_change'])
        
        # Should have pct columns
        pct_cols = [c for c in transformed.columns if '_pct' in c]
        assert len(pct_cols) > 0

    def test_transform_data_empty_transformations(self, processor, sample_data):
        """Test with empty transformation list."""
        transformed = processor.transform_data(sample_data, [])
        
        assert len(transformed.columns) == len(sample_data.columns)

    def test_transform_data_unknown_transformation(self, processor, sample_data):
        """Test unknown transformation is logged but doesn't fail."""
        # Should not raise, just log warning
        transformed = processor.transform_data(sample_data, ['unknown_transform'])
        
        assert len(transformed) == len(sample_data)

    def test_transform_data_empty_raises(self, processor):
        """Test transform of empty data raises."""
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.transform_data(pd.DataFrame(), ['log'])


# ============================================================================
# DATA PIPELINE TESTS
# ============================================================================

class TestDataPipeline:
    """Tests for DataPipeline class."""

    @pytest.fixture
    def sample_data(self):
        """Create sample market data."""
        return create_sample_data(n_rows=100)

    def test_init_default_steps(self):
        """Test initialization with default steps."""
        pipeline = DataPipeline()
        
        assert 'clean' in pipeline.steps
        assert 'preprocess' in pipeline.steps
        assert 'engineer_features' in pipeline.steps
        assert pipeline.pipeline_fitted is False

    def test_init_custom_steps(self):
        """Test initialization with custom steps."""
        steps = ['clean', 'preprocess']
        pipeline = DataPipeline(steps=steps)
        
        assert pipeline.steps == steps

    def test_fit_returns_self(self, sample_data):
        """Test fit returns pipeline instance."""
        pipeline = DataPipeline(steps=['clean'])
        
        result = pipeline.fit(sample_data)
        
        assert result is pipeline
        assert pipeline.pipeline_fitted is True

    def test_transform_after_fit(self, sample_data):
        """Test transform after fitting."""
        pipeline = DataPipeline(steps=['clean'])
        
        pipeline.fit(sample_data)
        transformed = pipeline.transform(sample_data)
        
        assert len(transformed) <= len(sample_data)

    def test_transform_without_fit_raises(self, sample_data):
        """Test transform without fit raises."""
        pipeline = DataPipeline()
        
        with pytest.raises(ValueError, match="Pipeline not fitted"):
            pipeline.transform(sample_data)

    def test_fit_transform(self, sample_data):
        """Test fit_transform method."""
        pipeline = DataPipeline(steps=['clean'])
        
        result = pipeline.fit_transform(sample_data)
        
        assert pipeline.pipeline_fitted is True
        assert len(result) <= len(sample_data)


# ============================================================================
# UTILITY FUNCTION TESTS
# ============================================================================

class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_create_sample_data_default(self):
        """Test create_sample_data with defaults."""
        data = create_sample_data()
        
        assert len(data) == 100
        assert 'open' in data.columns
        assert 'high' in data.columns
        assert 'low' in data.columns
        assert 'close' in data.columns
        assert 'volume' in data.columns

    def test_create_sample_data_custom_rows(self):
        """Test create_sample_data with custom row count."""
        data = create_sample_data(n_rows=50)
        
        assert len(data) == 50

    def test_create_sample_data_custom_start_date(self):
        """Test create_sample_data with custom start date."""
        data = create_sample_data(start_date='2024-06-01')
        
        assert data.index[0].year == 2024
        assert data.index[0].month == 6

    def test_create_sample_data_zero_rows_raises(self):
        """Test create_sample_data with zero rows raises."""
        with pytest.raises(ValueError, match="must be positive"):
            create_sample_data(n_rows=0)

    def test_create_sample_data_negative_rows_raises(self):
        """Test create_sample_data with negative rows raises."""
        with pytest.raises(ValueError, match="must be positive"):
            create_sample_data(n_rows=-10)

    def test_batch_process_data_basic(self):
        """Test batch processing of data."""
        pipeline = DataPipeline(steps=['clean'])
        sample = create_sample_data(n_rows=50)
        pipeline.fit(sample)
        
        batches = [create_sample_data(n_rows=20) for _ in range(3)]
        results = batch_process_data(batches, pipeline)
        
        assert len(results) == 3
        for result in results:
            assert isinstance(result, pd.DataFrame)

    def test_batch_process_empty_list(self):
        """Test batch processing of empty list."""
        pipeline = DataPipeline()
        
        results = batch_process_data([], pipeline)
        
        assert results == []

    def test_batch_process_unfitted_raises(self):
        """Test batch processing with unfitted pipeline raises."""
        pipeline = DataPipeline()
        batches = [create_sample_data(n_rows=20)]
        
        with pytest.raises(ValueError, match="Pipeline must be fitted"):
            batch_process_data(batches, pipeline)
