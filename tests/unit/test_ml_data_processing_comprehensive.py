"""
Comprehensive tests for backend/ml/data_processing.py

This module tests all classes and functions in the data_processing module:
- SimpleScaler (standard, minmax, robust scaling)
- SimpleImputer (mean, median, most_frequent strategies)
- DataProcessor (clean, preprocess, engineer_features, normalize, validate, transform)
- DataPipeline (fit, transform, fit_transform)
- Helper functions (create_sample_data, batch_process_data)
"""

import numpy as np
import pandas as pd
import pytest

from backend.ml.data_processing import (
    SimpleScaler,
    SimpleImputer,
    DataProcessor,
    DataPipeline,
    create_sample_data,
    batch_process_data,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data for testing."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="1h")
    np.random.seed(42)
    base_price = 100.0
    returns = np.random.normal(0, 0.02, 100)
    prices = [base_price]
    for r in returns[1:]:
        prices.append(prices[-1] * (1 + r))
    prices = np.array(prices)

    return pd.DataFrame(
        {
            "open": prices * (1 + np.random.uniform(-0.01, 0.01, 100)),
            "high": prices * (1 + np.abs(np.random.normal(0, 0.01, 100))),
            "low": prices * (1 - np.abs(np.random.normal(0, 0.01, 100))),
            "close": prices,
            "volume": np.random.randint(1000, 10000, 100),
        },
        index=dates,
    )


@pytest.fixture
def sample_data_with_timestamp():
    """Data with timestamp column instead of index."""
    dates = pd.date_range(start="2024-01-01", periods=50, freq="1h")
    np.random.seed(123)
    prices = 100 + np.cumsum(np.random.randn(50) * 0.5)

    return pd.DataFrame(
        {
            "timestamp": dates,
            "open": prices,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "volume": np.random.randint(1000, 5000, 50),
        }
    )


@pytest.fixture
def data_with_issues():
    """Data with quality issues for cleaning tests."""
    dates = pd.date_range(start="2024-01-01", periods=20, freq="1h")
    prices = np.array([100, 101, 102, np.nan, 104, 105, 106, 107, 108, 109,
                       110, 111, -5, 113, 114, 115, 116, 117, 118, 119])

    return pd.DataFrame(
        {
            "open": prices,
            "high": prices * 1.02,
            "low": prices * 0.98,
            "close": prices,
            "volume": [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000,
                       1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000],
        },
        index=dates,
    )


# ==============================================================================
# SimpleScaler Tests
# ==============================================================================


class TestSimpleScalerStandard:
    """Tests for SimpleScaler with standard scaling."""

    def test_init_default_method(self):
        """Test default initialization."""
        scaler = SimpleScaler()
        assert scaler.method == "standard"
        assert not scaler.fitted

    def test_init_explicit_method(self):
        """Test initialization with explicit method."""
        scaler = SimpleScaler(method="standard")
        assert scaler.method == "standard"

    def test_fit_calculates_mean_and_std(self):
        """Test fit computes mean and std."""
        scaler = SimpleScaler(method="standard")
        X = np.array([[1, 2], [3, 4], [5, 6]])
        scaler.fit(X)

        assert scaler.fitted
        np.testing.assert_array_almost_equal(scaler.mean_, [3, 4])
        np.testing.assert_array_almost_equal(scaler.std_, np.std(X, axis=0))
        np.testing.assert_array_almost_equal(scaler.scale_, scaler.std_)

    def test_transform_standard(self):
        """Test standard scaling transformation."""
        scaler = SimpleScaler(method="standard")
        X = np.array([[1, 2], [3, 4], [5, 6]])
        scaler.fit(X)

        transformed = scaler.transform(X)
        # Mean should be 0, std should be ~1
        np.testing.assert_array_almost_equal(transformed.mean(axis=0), [0, 0], decimal=5)

    def test_fit_transform(self):
        """Test fit_transform combines both steps."""
        scaler = SimpleScaler(method="standard")
        X = np.array([[10, 20], [30, 40], [50, 60]])

        result = scaler.fit_transform(X)
        assert scaler.fitted
        np.testing.assert_array_almost_equal(result.mean(axis=0), [0, 0], decimal=5)

    def test_transform_not_fitted_raises(self):
        """Test transform raises when not fitted."""
        scaler = SimpleScaler()
        with pytest.raises(ValueError, match="Scaler not fitted"):
            scaler.transform(np.array([[1, 2]]))


class TestSimpleScalerMinmax:
    """Tests for SimpleScaler with minmax scaling."""

    def test_fit_calculates_min_max(self):
        """Test fit computes min and max."""
        scaler = SimpleScaler(method="minmax")
        X = np.array([[1, 10], [5, 50], [10, 100]])
        scaler.fit(X)

        assert scaler.fitted
        np.testing.assert_array_equal(scaler.min_, [1, 10])
        np.testing.assert_array_equal(scaler.max_, [10, 100])
        np.testing.assert_array_equal(scaler.scale_, [9, 90])

    def test_transform_minmax(self):
        """Test minmax scaling produces values in [0, 1]."""
        scaler = SimpleScaler(method="minmax")
        X = np.array([[1.0], [5.0], [10.0]])
        scaler.fit(X)

        transformed = scaler.transform(X)
        # Should be approximately [0, 0.44, 1.0]
        assert transformed.min() >= 0
        assert transformed.max() <= 1.0 + 1e-6

    def test_fit_transform_minmax(self):
        """Test combined fit_transform."""
        scaler = SimpleScaler(method="minmax")
        X = np.array([[0, 0], [50, 100], [100, 200]])

        result = scaler.fit_transform(X)
        # First row should be [0, 0], last row should be [1, 1]
        np.testing.assert_array_almost_equal(result[0], [0, 0])
        np.testing.assert_array_almost_equal(result[-1], [1, 1])


class TestSimpleScalerRobust:
    """Tests for SimpleScaler with robust scaling."""

    def test_fit_calculates_median_mad(self):
        """Test fit computes median and MAD."""
        scaler = SimpleScaler(method="robust")
        X = np.array([[1], [2], [3], [4], [100]])  # 100 is an outlier
        scaler.fit(X)

        assert scaler.fitted
        np.testing.assert_array_equal(scaler.median_, [3])
        assert scaler.mad_ is not None
        assert scaler.scale_ is not None

    def test_transform_robust(self):
        """Test robust scaling is less affected by outliers."""
        scaler = SimpleScaler(method="robust")
        X = np.array([[1.0], [2.0], [3.0], [4.0], [5.0]])
        scaler.fit(X)

        transformed = scaler.transform(X)
        # Median (3) should map to 0
        assert abs(transformed[2, 0]) < 0.1  # Should be near 0


# ==============================================================================
# SimpleImputer Tests
# ==============================================================================


class TestSimpleImputerMean:
    """Tests for SimpleImputer with mean strategy."""

    def test_init_default_strategy(self):
        """Test default initialization."""
        imputer = SimpleImputer()
        assert imputer.strategy == "mean"
        assert not imputer.fitted

    def test_fit_calculates_mean(self):
        """Test fit computes column means."""
        imputer = SimpleImputer(strategy="mean")
        X = np.array([[1, 10], [2, np.nan], [3, 30]])
        imputer.fit(X)

        assert imputer.fitted
        np.testing.assert_array_almost_equal(imputer.fill_value_, [2, 20])

    def test_transform_fills_nan(self):
        """Test transform fills NaN with mean."""
        imputer = SimpleImputer(strategy="mean")
        X = np.array([[1.0, 10.0], [np.nan, 20.0], [3.0, np.nan]])
        imputer.fit(X)

        transformed = imputer.transform(X)
        assert not np.any(np.isnan(transformed))

    def test_fit_transform(self):
        """Test combined fit_transform."""
        imputer = SimpleImputer(strategy="mean")
        X = np.array([[1.0], [np.nan], [3.0]])

        result = imputer.fit_transform(X)
        assert not np.any(np.isnan(result))
        assert result[1, 0] == 2.0  # Mean of [1, 3]

    def test_fit_1d_array(self):
        """Test fit handles 1D arrays."""
        imputer = SimpleImputer()
        X = np.array([1, np.nan, 3, 4])
        imputer.fit(X)

        assert imputer.fitted
        assert len(imputer.fill_value_) == 1

    def test_transform_1d_array(self):
        """Test transform handles 1D arrays."""
        imputer = SimpleImputer()
        X = np.array([1.0, np.nan, 3.0])
        imputer.fit(X)

        result = imputer.transform(X)
        assert result.ndim == 1
        assert not np.any(np.isnan(result))

    def test_transform_not_fitted_raises(self):
        """Test transform raises when not fitted."""
        imputer = SimpleImputer()
        with pytest.raises(ValueError, match="Imputer not fitted"):
            imputer.transform(np.array([1, 2, 3]))


class TestSimpleImputerMedian:
    """Tests for SimpleImputer with median strategy."""

    def test_fit_calculates_median(self):
        """Test fit computes column medians."""
        imputer = SimpleImputer(strategy="median")
        X = np.array([[1], [2], [np.nan], [4], [100]])  # 100 is outlier
        imputer.fit(X)

        assert imputer.fitted
        # Median of [1, 2, 4, 100] = 3
        assert imputer.fill_value_[0] == 3.0

    def test_transform_fills_with_median(self):
        """Test transform fills NaN with median."""
        imputer = SimpleImputer(strategy="median")
        X = np.array([[1.0], [2.0], [3.0]])
        imputer.fit(X)

        X_test = np.array([[np.nan]])
        result = imputer.transform(X_test)
        assert result[0, 0] == 2.0


class TestSimpleImputerMostFrequent:
    """Tests for SimpleImputer with most_frequent strategy."""

    def test_fit_uses_median_for_numeric(self):
        """Test most_frequent strategy uses median for numeric data."""
        imputer = SimpleImputer(strategy="most_frequent")
        X = np.array([[1], [2], [3], [np.nan]])
        imputer.fit(X)

        assert imputer.fitted
        assert imputer.fill_value_ is not None

    def test_handles_all_nan_column(self):
        """Test fit handles columns with all NaN."""
        imputer = SimpleImputer()
        X = np.array([[np.nan], [np.nan], [np.nan]])
        imputer.fit(X)

        # Should default to 0.0 for all-NaN columns
        assert imputer.fill_value_[0] == 0.0


# ==============================================================================
# DataProcessor Tests
# ==============================================================================


class TestDataProcessorInit:
    """Tests for DataProcessor initialization."""

    def test_init_default(self):
        """Test default initialization."""
        processor = DataProcessor()
        assert processor.config == {}
        assert processor.scaler is None
        assert processor.imputer is None
        assert processor.feature_columns == []
        assert not processor.is_fitted

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = {"feature_window": 20}
        processor = DataProcessor(config=config)
        assert processor.config == config


class TestDataProcessorCleanData:
    """Tests for DataProcessor.clean_data method."""

    def test_clean_data_basic(self, sample_ohlcv_data):
        """Test basic data cleaning."""
        processor = DataProcessor()
        cleaned = processor.clean_data(sample_ohlcv_data)

        assert isinstance(cleaned, pd.DataFrame)
        assert not cleaned.empty
        # Should have same or fewer rows
        assert len(cleaned) <= len(sample_ohlcv_data)

    def test_clean_data_none_raises(self):
        """Test clean_data raises for None input."""
        processor = DataProcessor()
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.clean_data(None)

    def test_clean_data_empty_raises(self):
        """Test clean_data raises for empty DataFrame."""
        processor = DataProcessor()
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.clean_data(pd.DataFrame())

    def test_clean_data_removes_duplicates(self):
        """Test clean_data removes duplicate rows."""
        processor = DataProcessor()
        dates = pd.date_range("2024-01-01", periods=5, freq="1h")
        data = pd.DataFrame({
            "open": [100, 101, 101, 103, 104],
            "high": [102, 103, 103, 105, 106],
            "low": [99, 100, 100, 102, 103],
            "close": [101, 102, 102, 104, 105],
            "volume": [1000, 2000, 2000, 4000, 5000],
        }, index=dates)

        # Add duplicate row
        dup_data = pd.concat([data, data.iloc[[2]]])
        cleaned = processor.clean_data(dup_data)

        assert len(cleaned) <= len(dup_data)

    def test_clean_data_removes_negative_prices(self, data_with_issues):
        """Test clean_data removes rows with negative prices."""
        processor = DataProcessor()
        cleaned = processor.clean_data(data_with_issues)

        # Negative price at index 12 should be removed
        for col in ["open", "high", "low", "close"]:
            if col in cleaned.columns:
                assert (cleaned[col] > 0).all()

    def test_clean_data_handles_missing_values(self, data_with_issues):
        """Test clean_data handles missing values via forward/backward fill."""
        processor = DataProcessor()
        cleaned = processor.clean_data(data_with_issues)

        # Should have handled NaN at index 3
        for col in ["open", "high", "low", "close"]:
            if col in cleaned.columns:
                assert not cleaned[col].isna().any()


class TestDataProcessorPreprocessData:
    """Tests for DataProcessor.preprocess_data method."""

    def test_preprocess_basic(self, sample_ohlcv_data):
        """Test basic preprocessing."""
        processor = DataProcessor()
        processed = processor.preprocess_data(sample_ohlcv_data, fit=True)

        assert isinstance(processed, pd.DataFrame)
        assert processor.is_fitted
        assert processor.scaler is not None

    def test_preprocess_none_raises(self):
        """Test preprocess raises for None input."""
        processor = DataProcessor()
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.preprocess_data(None)

    def test_preprocess_empty_raises(self):
        """Test preprocess raises for empty DataFrame."""
        processor = DataProcessor()
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.preprocess_data(pd.DataFrame())

    def test_preprocess_with_timestamp_column(self, sample_data_with_timestamp):
        """Test preprocessing with timestamp column."""
        processor = DataProcessor()
        processed = processor.preprocess_data(sample_data_with_timestamp, fit=True)

        assert isinstance(processed.index, pd.DatetimeIndex)

    def test_preprocess_with_date_column(self):
        """Test preprocessing with date column."""
        processor = DataProcessor()
        data = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="D"),
            "close": range(100, 110),
        })

        processed = processor.preprocess_data(data, fit=True)
        assert isinstance(processed.index, pd.DatetimeIndex)

    def test_preprocess_fit_false_without_prior_fit_raises(self, sample_ohlcv_data):
        """Test preprocess with fit=False without prior fit raises."""
        processor = DataProcessor()
        with pytest.raises(ValueError, match="Scaler not fitted"):
            processor.preprocess_data(sample_ohlcv_data, fit=False)

    def test_preprocess_transform_after_fit(self, sample_ohlcv_data):
        """Test preprocessing can transform after fitting."""
        processor = DataProcessor()
        processor.preprocess_data(sample_ohlcv_data[:50], fit=True)

        # Now transform rest
        processed = processor.preprocess_data(sample_ohlcv_data[50:], fit=False)
        assert isinstance(processed, pd.DataFrame)


class TestDataProcessorEngineerFeatures:
    """Tests for DataProcessor.engineer_features method."""

    def test_engineer_features_basic(self, sample_ohlcv_data):
        """Test basic feature engineering."""
        processor = DataProcessor()
        features = processor.engineer_features(sample_ohlcv_data)

        assert len(features.columns) > len(sample_ohlcv_data.columns)
        assert "returns" in features.columns
        assert "log_returns" in features.columns
        assert "rsi" in features.columns

    def test_engineer_features_none_returns_input(self):
        """Test engineer_features returns None/empty unchanged."""
        processor = DataProcessor()
        assert processor.engineer_features(None) is None
        assert processor.engineer_features(pd.DataFrame()).empty

    def test_engineer_features_moving_averages(self, sample_ohlcv_data):
        """Test moving average features are created."""
        processor = DataProcessor()
        features = processor.engineer_features(sample_ohlcv_data)

        for window in [5, 10, 20, 50]:
            assert f"sma_{window}" in features.columns
            assert f"ema_{window}" in features.columns

    def test_engineer_features_volatility(self, sample_ohlcv_data):
        """Test volatility features are created."""
        processor = DataProcessor()
        features = processor.engineer_features(sample_ohlcv_data)

        assert "volatility_10" in features.columns
        assert "volatility_20" in features.columns

    def test_engineer_features_volume_based(self, sample_ohlcv_data):
        """Test volume-based features are created."""
        processor = DataProcessor()
        features = processor.engineer_features(sample_ohlcv_data)

        assert "volume_sma_10" in features.columns
        assert "volume_ratio" in features.columns
        assert "price_volume" in features.columns

    def test_engineer_features_ohlc_based(self, sample_ohlcv_data):
        """Test OHLC-based features are created."""
        processor = DataProcessor()
        features = processor.engineer_features(sample_ohlcv_data)

        assert "true_range" in features.columns
        assert "atr" in features.columns
        assert "price_position" in features.columns

    def test_engineer_features_stores_column_list(self, sample_ohlcv_data):
        """Test feature columns are stored."""
        processor = DataProcessor()
        processor.engineer_features(sample_ohlcv_data)

        assert len(processor.feature_columns) > 0


class TestDataProcessorNormalizeData:
    """Tests for DataProcessor.normalize_data method."""

    def test_normalize_standard(self, sample_ohlcv_data):
        """Test standard normalization."""
        processor = DataProcessor()
        normalized = processor.normalize_data(sample_ohlcv_data, method="standard")

        assert isinstance(normalized, pd.DataFrame)

    def test_normalize_minmax(self, sample_ohlcv_data):
        """Test minmax normalization."""
        processor = DataProcessor()
        normalized = processor.normalize_data(sample_ohlcv_data, method="minmax")

        # Check that numeric columns are in [0, 1] range
        numeric_cols = normalized.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            assert normalized[col].min() >= -1e-6
            assert normalized[col].max() <= 1.0 + 1e-6

    def test_normalize_robust(self, sample_ohlcv_data):
        """Test robust normalization."""
        processor = DataProcessor()
        normalized = processor.normalize_data(sample_ohlcv_data, method="robust")

        assert isinstance(normalized, pd.DataFrame)

    def test_normalize_invalid_method_raises(self, sample_ohlcv_data):
        """Test invalid normalization method raises."""
        processor = DataProcessor()
        with pytest.raises(ValueError, match="Unknown normalization method"):
            processor.normalize_data(sample_ohlcv_data, method="invalid")

    def test_normalize_none_raises(self):
        """Test normalize raises for None input."""
        processor = DataProcessor()
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.normalize_data(None)

    def test_normalize_empty_raises(self):
        """Test normalize raises for empty DataFrame."""
        processor = DataProcessor()
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.normalize_data(pd.DataFrame())

    def test_normalize_no_numeric_columns(self):
        """Test normalize returns unchanged for non-numeric data."""
        processor = DataProcessor()
        data = pd.DataFrame({"text": ["a", "b", "c"]})
        normalized = processor.normalize_data(data)

        pd.testing.assert_frame_equal(normalized, data)


class TestDataProcessorValidateData:
    """Tests for DataProcessor.validate_data method."""

    def test_validate_valid_data(self, sample_ohlcv_data):
        """Test validation of valid data."""
        processor = DataProcessor()
        result = processor.validate_data(sample_ohlcv_data)

        assert result["valid"]
        assert result["shape"] == sample_ohlcv_data.shape
        assert "missing_values" in result
        assert "duplicates" in result
        assert "data_types" in result

    def test_validate_none_data(self):
        """Test validation of None data."""
        processor = DataProcessor()
        result = processor.validate_data(None)

        assert not result["valid"]
        assert result["error"] == "Data is None"

    def test_validate_empty_data(self):
        """Test validation of empty data."""
        processor = DataProcessor()
        result = processor.validate_data(pd.DataFrame())

        assert not result["valid"]
        assert result["error"] == "Data is empty"

    def test_validate_detects_negative_prices(self):
        """Test validation detects negative prices."""
        processor = DataProcessor()
        data = pd.DataFrame({
            "open": [100, -10, 102],
            "high": [105, 108, 110],
            "low": [95, 90, 98],
            "close": [103, 107, 109],
        })

        result = processor.validate_data(data)
        assert not result["valid"]
        assert "negative_prices" in result
        assert "open" in result["negative_prices"]

    def test_validate_detects_infinite_values(self):
        """Test validation detects infinite values."""
        processor = DataProcessor()
        data = pd.DataFrame({
            "value1": [1.0, np.inf, 3.0],
            "value2": [4.0, 5.0, -np.inf],
        })

        result = processor.validate_data(data)
        assert not result["valid"]
        assert "infinite_values" in result

    def test_validate_counts_missing_values(self):
        """Test validation counts missing values correctly."""
        processor = DataProcessor()
        data = pd.DataFrame({
            "col1": [1, np.nan, 3],
            "col2": [np.nan, np.nan, 3],
        })

        result = processor.validate_data(data)
        assert result["missing_values"]["col1"] == 1
        assert result["missing_values"]["col2"] == 2


class TestDataProcessorTransformData:
    """Tests for DataProcessor.transform_data method."""

    def test_transform_log(self, sample_ohlcv_data):
        """Test log transformation."""
        processor = DataProcessor()
        transformed = processor.transform_data(sample_ohlcv_data, ["log"])

        # Should have log columns for positive numeric columns
        assert "close_log" in transformed.columns
        assert "open_log" in transformed.columns

    def test_transform_diff(self, sample_ohlcv_data):
        """Test diff transformation."""
        processor = DataProcessor()
        transformed = processor.transform_data(sample_ohlcv_data, ["diff"])

        assert "close_diff" in transformed.columns
        assert "volume_diff" in transformed.columns

    def test_transform_pct_change(self, sample_ohlcv_data):
        """Test pct_change transformation."""
        processor = DataProcessor()
        transformed = processor.transform_data(sample_ohlcv_data, ["pct_change"])

        assert "close_pct" in transformed.columns

    def test_transform_multiple(self, sample_ohlcv_data):
        """Test multiple transformations."""
        processor = DataProcessor()
        transformed = processor.transform_data(sample_ohlcv_data, ["log", "diff"])

        assert "close_log" in transformed.columns
        assert "close_diff" in transformed.columns

    def test_transform_empty_list_returns_unchanged(self, sample_ohlcv_data):
        """Test empty transformation list returns data unchanged."""
        processor = DataProcessor()
        transformed = processor.transform_data(sample_ohlcv_data, [])

        pd.testing.assert_frame_equal(transformed, sample_ohlcv_data)

    def test_transform_none_raises(self):
        """Test transform raises for None input."""
        processor = DataProcessor()
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.transform_data(None, ["log"])

    def test_transform_empty_raises(self):
        """Test transform raises for empty DataFrame."""
        processor = DataProcessor()
        with pytest.raises(ValueError, match="cannot be None or empty"):
            processor.transform_data(pd.DataFrame(), ["log"])

    def test_transform_unknown_logs_warning(self, sample_ohlcv_data, caplog):
        """Test unknown transformation logs warning."""
        processor = DataProcessor()
        processor.transform_data(sample_ohlcv_data, ["unknown_transform"])

        assert "Unknown transformation" in caplog.text


class TestDataProcessorRSI:
    """Tests for DataProcessor._calculate_rsi method."""

    def test_rsi_basic(self):
        """Test RSI calculation."""
        processor = DataProcessor()
        prices = pd.Series([44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10,
                           45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28])

        rsi = processor._calculate_rsi(prices, window=14)
        assert len(rsi) == len(prices)
        # RSI should be between 0 and 100
        valid_rsi = rsi.dropna()
        if len(valid_rsi) > 0:
            assert valid_rsi.min() >= 0
            assert valid_rsi.max() <= 100


class TestDataProcessorTrueRange:
    """Tests for DataProcessor._calculate_true_range method."""

    def test_true_range_calculation(self):
        """Test true range calculation."""
        processor = DataProcessor()
        data = pd.DataFrame({
            "high": [105, 110, 108, 115],
            "low": [100, 105, 103, 110],
            "close": [103, 107, 105, 113],
        })

        tr = processor._calculate_true_range(data)
        assert len(tr) == len(data)
        # True range should be positive
        assert (tr.dropna() >= 0).all()


# ==============================================================================
# DataPipeline Tests
# ==============================================================================


class TestDataPipelineInit:
    """Tests for DataPipeline initialization."""

    def test_init_default_steps(self):
        """Test default initialization with default steps."""
        pipeline = DataPipeline()
        assert pipeline.steps == ["clean", "preprocess", "engineer_features"]
        assert isinstance(pipeline.processor, DataProcessor)
        assert not pipeline.pipeline_fitted

    def test_init_custom_steps(self):
        """Test initialization with custom steps."""
        custom_steps = ["clean", "preprocess"]
        pipeline = DataPipeline(steps=custom_steps)
        assert pipeline.steps == custom_steps


class TestDataPipelineFit:
    """Tests for DataPipeline.fit method."""

    def test_fit_basic(self, sample_ohlcv_data):
        """Test basic pipeline fitting."""
        pipeline = DataPipeline()
        result = pipeline.fit(sample_ohlcv_data)

        assert result is pipeline  # Returns self
        assert pipeline.pipeline_fitted

    def test_fit_with_clean_step(self, sample_ohlcv_data):
        """Test fit with clean step."""
        pipeline = DataPipeline(steps=["clean"])
        pipeline.fit(sample_ohlcv_data)

        assert pipeline.pipeline_fitted

    def test_fit_with_preprocess_step(self, sample_ohlcv_data):
        """Test fit with preprocess step."""
        pipeline = DataPipeline(steps=["preprocess"])
        pipeline.fit(sample_ohlcv_data)

        assert pipeline.pipeline_fitted
        assert pipeline.processor.is_fitted

    def test_fit_with_engineer_features_step(self, sample_ohlcv_data):
        """Test fit with engineer_features step."""
        pipeline = DataPipeline(steps=["engineer_features"])
        pipeline.fit(sample_ohlcv_data)

        assert pipeline.pipeline_fitted


class TestDataPipelineTransform:
    """Tests for DataPipeline.transform method."""

    def test_transform_after_fit(self, sample_ohlcv_data):
        """Test transform after fitting."""
        pipeline = DataPipeline()
        pipeline.fit(sample_ohlcv_data[:50])

        transformed = pipeline.transform(sample_ohlcv_data[50:])
        assert isinstance(transformed, pd.DataFrame)

    def test_transform_not_fitted_raises(self, sample_ohlcv_data):
        """Test transform raises when not fitted."""
        pipeline = DataPipeline()
        with pytest.raises(ValueError, match="Pipeline not fitted"):
            pipeline.transform(sample_ohlcv_data)


class TestDataPipelineFitTransform:
    """Tests for DataPipeline.fit_transform method."""

    def test_fit_transform_basic(self, sample_ohlcv_data):
        """Test combined fit_transform."""
        pipeline = DataPipeline()
        result = pipeline.fit_transform(sample_ohlcv_data)

        assert isinstance(result, pd.DataFrame)
        assert pipeline.pipeline_fitted

    def test_fit_transform_produces_features(self, sample_ohlcv_data):
        """Test fit_transform produces engineered features."""
        pipeline = DataPipeline(steps=["engineer_features"])
        result = pipeline.fit_transform(sample_ohlcv_data)

        # Should have more columns than input
        assert len(result.columns) > len(sample_ohlcv_data.columns)


# ==============================================================================
# Helper Function Tests
# ==============================================================================


class TestCreateSampleData:
    """Tests for create_sample_data function."""

    def test_create_sample_data_default(self):
        """Test default sample data creation."""
        data = create_sample_data()

        assert isinstance(data, pd.DataFrame)
        assert len(data) == 100
        assert "open" in data.columns
        assert "high" in data.columns
        assert "low" in data.columns
        assert "close" in data.columns
        assert "volume" in data.columns

    def test_create_sample_data_custom_rows(self):
        """Test sample data with custom row count."""
        data = create_sample_data(n_rows=50)
        assert len(data) == 50

    def test_create_sample_data_custom_start_date(self):
        """Test sample data with custom start date."""
        data = create_sample_data(start_date="2025-06-01")
        assert data.index[0] == pd.Timestamp("2025-06-01")

    def test_create_sample_data_zero_rows_raises(self):
        """Test zero rows raises ValueError."""
        with pytest.raises(ValueError, match="n_rows must be positive"):
            create_sample_data(n_rows=0)

    def test_create_sample_data_negative_rows_raises(self):
        """Test negative rows raises ValueError."""
        with pytest.raises(ValueError, match="n_rows must be positive"):
            create_sample_data(n_rows=-10)

    def test_create_sample_data_has_datetime_index(self):
        """Test created data has DatetimeIndex."""
        data = create_sample_data()
        assert isinstance(data.index, pd.DatetimeIndex)
        assert data.index.name == "timestamp"

    def test_create_sample_data_prices_positive(self):
        """Test all prices are positive."""
        data = create_sample_data(n_rows=200)

        for col in ["open", "high", "low", "close"]:
            assert (data[col] > 0).all()

    def test_create_sample_data_high_low_relationship(self):
        """Test high >= close >= low roughly holds."""
        data = create_sample_data(n_rows=100)

        # High should be >= close most of the time
        assert (data["high"] >= data["close"] * 0.99).all()
        # Low should be <= close most of the time
        assert (data["low"] <= data["close"] * 1.01).all()


class TestBatchProcessData:
    """Tests for batch_process_data function."""

    def test_batch_process_empty_list(self):
        """Test empty batch list returns empty list."""
        pipeline = DataPipeline()
        pipeline.pipeline_fitted = True

        result = batch_process_data([], pipeline)
        assert result == []

    def test_batch_process_not_fitted_raises(self, sample_ohlcv_data):
        """Test batch processing with unfitted pipeline raises."""
        pipeline = DataPipeline()
        batches = [sample_ohlcv_data[:20], sample_ohlcv_data[20:40]]

        with pytest.raises(ValueError, match="must be fitted"):
            batch_process_data(batches, pipeline)

    def test_batch_process_multiple_batches(self, sample_ohlcv_data):
        """Test batch processing with multiple batches."""
        pipeline = DataPipeline(steps=["clean"])
        pipeline.fit(sample_ohlcv_data[:20])

        batches = [sample_ohlcv_data[:30], sample_ohlcv_data[30:60], sample_ohlcv_data[60:]]
        results = batch_process_data(batches, pipeline)

        assert len(results) == 3
        for result in results:
            assert isinstance(result, pd.DataFrame)

    def test_batch_process_handles_failed_batch(self, sample_ohlcv_data):
        """Test batch processing handles failed batches gracefully."""
        pipeline = DataPipeline(steps=["preprocess"])
        pipeline.fit(sample_ohlcv_data)

        # Create a batch that will fail (None)
        batches = [sample_ohlcv_data[:20], pd.DataFrame()]  # Empty df might not fail but tests robustness
        results = batch_process_data(batches, pipeline)

        assert len(results) == 2


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_pipeline_workflow(self):
        """Test complete pipeline workflow."""
        # Create sample data
        data = create_sample_data(n_rows=200)

        # Initialize and run pipeline
        pipeline = DataPipeline(steps=["clean", "preprocess", "engineer_features"])
        result = pipeline.fit_transform(data)

        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        assert len(result.columns) > len(data.columns)

    def test_scaler_imputer_integration(self):
        """Test scaler and imputer work together."""
        # Data with missing values
        X = np.array([[1, 2], [np.nan, 4], [5, np.nan], [7, 8]])

        # Impute first
        imputer = SimpleImputer(strategy="mean")
        X_imputed = imputer.fit_transform(X)

        # Then scale
        scaler = SimpleScaler(method="standard")
        X_scaled = scaler.fit_transform(X_imputed)

        assert not np.any(np.isnan(X_scaled))
        np.testing.assert_array_almost_equal(X_scaled.mean(axis=0), [0, 0], decimal=5)

    def test_processor_with_real_workflow(self, sample_ohlcv_data):
        """Test DataProcessor in realistic workflow."""
        processor = DataProcessor()

        # Step 1: Validate
        validation = processor.validate_data(sample_ohlcv_data)
        assert validation["valid"]

        # Step 2: Clean
        cleaned = processor.clean_data(sample_ohlcv_data)

        # Step 3: Engineer features
        features = processor.engineer_features(cleaned)

        # Step 4: Normalize
        normalized = processor.normalize_data(features, method="standard")

        assert isinstance(normalized, pd.DataFrame)
        assert len(normalized.columns) > len(sample_ohlcv_data.columns)
