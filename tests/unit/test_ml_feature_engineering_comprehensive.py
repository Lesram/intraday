"""
Comprehensive tests for backend/ml/feature_engineering.py

This module tests all classes and functions in the feature_engineering module:
- FeatureType enum
- FeatureConfig dataclass
- TechnicalIndicators (SMA, EMA, RSI, Bollinger Bands, MACD, Stochastic, ATR)
- StatisticalFeatures (rolling_statistics, price_features, volatility_features, momentum_features)
- CategoricalEncoder (fit, transform, one_hot_encode)
- TemporalFeatures (extract_time_features, create_lags, create_leads)
- FeatureSelector (correlation_filter, variance_filter, missing_value_filter)
- FeatureEngineer (main class combining all functionality)
- create_sample_financial_data function
"""

import numpy as np
import pandas as pd
import pytest

from backend.ml.feature_engineering import (
    FeatureType,
    FeatureConfig,
    TechnicalIndicators,
    StatisticalFeatures,
    CategoricalEncoder,
    TemporalFeatures,
    FeatureSelector,
    FeatureEngineer,
    create_sample_financial_data,
)


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def sample_price_series():
    """Create sample price series for indicator tests."""
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
    return pd.Series(prices, name="close")


@pytest.fixture
def sample_ohlcv_data():
    """Create sample OHLCV data for testing."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="1h")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(100) * 0.5)

    return pd.DataFrame(
        {
            "open": close * (1 + np.random.uniform(-0.01, 0.01, 100)),
            "high": close * (1 + np.abs(np.random.normal(0, 0.01, 100))),
            "low": close * (1 - np.abs(np.random.normal(0, 0.01, 100))),
            "close": close,
            "volume": np.random.randint(1000, 10000, 100),
        },
        index=dates,
    )


@pytest.fixture
def sample_categorical_data():
    """Create sample data with categorical columns."""
    dates = pd.date_range(start="2024-01-01", periods=50, freq="D")
    return pd.DataFrame(
        {
            "close": np.random.uniform(100, 150, 50),
            "sector": ["Tech", "Finance", "Tech", "Health"] * 12 + ["Tech", "Finance"],
            "market": ["NYSE", "NASDAQ"] * 25,
        },
        index=dates,
    )


# ==============================================================================
# FeatureType and FeatureConfig Tests
# ==============================================================================


class TestFeatureType:
    """Tests for FeatureType enum."""

    def test_all_types_exist(self):
        """Test all feature types are defined."""
        assert FeatureType.TECHNICAL.value == "technical"
        assert FeatureType.STATISTICAL.value == "statistical"
        assert FeatureType.CATEGORICAL.value == "categorical"
        assert FeatureType.TEMPORAL.value == "temporal"
        assert FeatureType.DERIVED.value == "derived"

    def test_enum_membership(self):
        """Test enum membership."""
        assert FeatureType.TECHNICAL in FeatureType
        assert len(FeatureType) == 5


class TestFeatureConfig:
    """Tests for FeatureConfig dataclass."""

    def test_basic_config(self):
        """Test basic config creation."""
        config = FeatureConfig(
            name="sma_20",
            feature_type=FeatureType.TECHNICAL,
            parameters={"window": 20},
        )

        assert config.name == "sma_20"
        assert config.feature_type == FeatureType.TECHNICAL
        assert config.parameters == {"window": 20}
        assert config.enabled  # Default is True

    def test_config_with_enabled_false(self):
        """Test config with enabled=False."""
        config = FeatureConfig(
            name="test",
            feature_type=FeatureType.DERIVED,
            parameters={},
            enabled=False,
        )

        assert not config.enabled


# ==============================================================================
# TechnicalIndicators Tests
# ==============================================================================


class TestTechnicalIndicatorsSMA:
    """Tests for TechnicalIndicators.sma method."""

    def test_sma_basic(self, sample_price_series):
        """Test basic SMA calculation."""
        result = TechnicalIndicators.sma(sample_price_series, window=5)

        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_price_series)
        # First 4 values should be NaN
        assert result.isna().sum() == 4

    def test_sma_window_1(self, sample_price_series):
        """Test SMA with window=1 equals original."""
        result = TechnicalIndicators.sma(sample_price_series, window=1)
        pd.testing.assert_series_equal(result, sample_price_series)

    def test_sma_zero_window_raises(self, sample_price_series):
        """Test SMA with zero window raises."""
        with pytest.raises(ValueError, match="Window must be positive"):
            TechnicalIndicators.sma(sample_price_series, window=0)

    def test_sma_negative_window_raises(self, sample_price_series):
        """Test SMA with negative window raises."""
        with pytest.raises(ValueError, match="Window must be positive"):
            TechnicalIndicators.sma(sample_price_series, window=-5)


class TestTechnicalIndicatorsEMA:
    """Tests for TechnicalIndicators.ema method."""

    def test_ema_basic(self, sample_price_series):
        """Test basic EMA calculation."""
        result = TechnicalIndicators.ema(sample_price_series, window=10)

        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_price_series)
        # EMA starts from first value
        assert not result.isna().all()

    def test_ema_zero_window_raises(self, sample_price_series):
        """Test EMA with zero window raises."""
        with pytest.raises(ValueError, match="Window must be positive"):
            TechnicalIndicators.ema(sample_price_series, window=0)


class TestTechnicalIndicatorsRSI:
    """Tests for TechnicalIndicators.rsi method."""

    def test_rsi_basic(self, sample_price_series):
        """Test basic RSI calculation."""
        result = TechnicalIndicators.rsi(sample_price_series, window=14)

        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_price_series)

    def test_rsi_bounds(self, sample_price_series):
        """Test RSI is bounded between 0 and 100."""
        result = TechnicalIndicators.rsi(sample_price_series, window=14)
        valid = result.dropna()

        assert valid.min() >= 0
        assert valid.max() <= 100

    def test_rsi_zero_window_raises(self, sample_price_series):
        """Test RSI with zero window raises."""
        with pytest.raises(ValueError, match="Window must be positive"):
            TechnicalIndicators.rsi(sample_price_series, window=0)


class TestTechnicalIndicatorsBollingerBands:
    """Tests for TechnicalIndicators.bollinger_bands method."""

    def test_bollinger_bands_basic(self, sample_price_series):
        """Test basic Bollinger Bands calculation."""
        result = TechnicalIndicators.bollinger_bands(sample_price_series, window=20)

        assert isinstance(result, dict)
        assert "bb_upper" in result
        assert "bb_middle" in result
        assert "bb_lower" in result
        assert "bb_width" in result
        assert "bb_position" in result

    def test_bollinger_bands_relationship(self, sample_price_series):
        """Test upper > middle > lower relationship."""
        result = TechnicalIndicators.bollinger_bands(sample_price_series, window=20)

        # Check valid values
        valid_idx = ~result["bb_upper"].isna()
        assert (result["bb_upper"][valid_idx] >= result["bb_middle"][valid_idx]).all()
        assert (result["bb_middle"][valid_idx] >= result["bb_lower"][valid_idx]).all()

    def test_bollinger_bands_zero_window_raises(self, sample_price_series):
        """Test Bollinger Bands with zero window raises."""
        with pytest.raises(ValueError, match="Window must be positive"):
            TechnicalIndicators.bollinger_bands(sample_price_series, window=0)

    def test_bollinger_bands_zero_std_raises(self, sample_price_series):
        """Test Bollinger Bands with zero std_dev raises."""
        with pytest.raises(ValueError, match="Standard deviation multiplier must be positive"):
            TechnicalIndicators.bollinger_bands(sample_price_series, std_dev=0)


class TestTechnicalIndicatorsMACD:
    """Tests for TechnicalIndicators.macd method."""

    def test_macd_basic(self, sample_price_series):
        """Test basic MACD calculation."""
        result = TechnicalIndicators.macd(sample_price_series)

        assert isinstance(result, dict)
        assert "macd" in result
        assert "macd_signal" in result
        assert "macd_histogram" in result

    def test_macd_histogram_relationship(self, sample_price_series):
        """Test histogram = macd - signal."""
        result = TechnicalIndicators.macd(sample_price_series)

        calculated_hist = result["macd"] - result["macd_signal"]
        pd.testing.assert_series_equal(
            result["macd_histogram"], calculated_hist, check_names=False
        )

    def test_macd_invalid_periods_raises(self, sample_price_series):
        """Test MACD with invalid periods raises."""
        with pytest.raises(ValueError, match="All periods must be positive"):
            TechnicalIndicators.macd(sample_price_series, fast=0)

        with pytest.raises(ValueError, match="Fast period must be less than slow"):
            TechnicalIndicators.macd(sample_price_series, fast=26, slow=12)


class TestTechnicalIndicatorsStochastic:
    """Tests for TechnicalIndicators.stochastic method."""

    def test_stochastic_basic(self, sample_ohlcv_data):
        """Test basic Stochastic calculation."""
        result = TechnicalIndicators.stochastic(
            sample_ohlcv_data["high"],
            sample_ohlcv_data["low"],
            sample_ohlcv_data["close"],
        )

        assert isinstance(result, dict)
        assert "stoch_k" in result
        assert "stoch_d" in result

    def test_stochastic_bounds(self, sample_ohlcv_data):
        """Test Stochastic is bounded between 0 and 100."""
        result = TechnicalIndicators.stochastic(
            sample_ohlcv_data["high"],
            sample_ohlcv_data["low"],
            sample_ohlcv_data["close"],
        )

        valid_k = result["stoch_k"].dropna()
        assert valid_k.min() >= 0
        assert valid_k.max() <= 100

    def test_stochastic_invalid_period_raises(self, sample_ohlcv_data):
        """Test Stochastic with invalid period raises."""
        with pytest.raises(ValueError, match="All periods must be positive"):
            TechnicalIndicators.stochastic(
                sample_ohlcv_data["high"],
                sample_ohlcv_data["low"],
                sample_ohlcv_data["close"],
                k_period=0,
            )


class TestTechnicalIndicatorsATR:
    """Tests for TechnicalIndicators.atr method."""

    def test_atr_basic(self, sample_ohlcv_data):
        """Test basic ATR calculation."""
        result = TechnicalIndicators.atr(
            sample_ohlcv_data["high"],
            sample_ohlcv_data["low"],
            sample_ohlcv_data["close"],
            window=14,
        )

        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_ohlcv_data)

    def test_atr_positive(self, sample_ohlcv_data):
        """Test ATR is always positive."""
        result = TechnicalIndicators.atr(
            sample_ohlcv_data["high"],
            sample_ohlcv_data["low"],
            sample_ohlcv_data["close"],
        )

        valid = result.dropna()
        assert (valid >= 0).all()

    def test_atr_zero_window_raises(self, sample_ohlcv_data):
        """Test ATR with zero window raises."""
        with pytest.raises(ValueError, match="Window must be positive"):
            TechnicalIndicators.atr(
                sample_ohlcv_data["high"],
                sample_ohlcv_data["low"],
                sample_ohlcv_data["close"],
                window=0,
            )


# ==============================================================================
# StatisticalFeatures Tests
# ==============================================================================


class TestStatisticalFeaturesRolling:
    """Tests for StatisticalFeatures.rolling_statistics method."""

    def test_rolling_statistics_basic(self, sample_price_series):
        """Test basic rolling statistics."""
        result = StatisticalFeatures.rolling_statistics(sample_price_series, window=10)

        assert isinstance(result, dict)
        assert "mean" in result
        assert "std" in result
        assert "var" in result
        assert "min" in result
        assert "max" in result
        assert "median" in result
        assert "quantile_25" in result
        assert "quantile_75" in result

    def test_rolling_statistics_zero_window_raises(self, sample_price_series):
        """Test rolling statistics with zero window raises."""
        with pytest.raises(ValueError, match="Window must be positive"):
            StatisticalFeatures.rolling_statistics(sample_price_series, window=0)


class TestStatisticalFeaturesPriceFeatures:
    """Tests for StatisticalFeatures.price_features method."""

    def test_price_features_basic(self, sample_price_series):
        """Test basic price features."""
        result = StatisticalFeatures.price_features(sample_price_series)

        assert isinstance(result, dict)
        assert "returns" in result
        assert "log_returns" in result
        assert "price_change" in result
        assert "price_acceleration" in result
        assert "normalized_price" in result


class TestStatisticalFeaturesVolatility:
    """Tests for StatisticalFeatures.volatility_features method."""

    def test_volatility_features_default(self, sample_price_series):
        """Test volatility features with default windows."""
        returns = sample_price_series.pct_change()
        result = StatisticalFeatures.volatility_features(returns)

        assert isinstance(result, dict)
        assert "volatility_5" in result
        assert "volatility_10" in result
        assert "volatility_20" in result
        assert "volatility_50" in result
        assert "realized_vol_5" in result

    def test_volatility_features_custom_windows(self, sample_price_series):
        """Test volatility features with custom windows."""
        returns = sample_price_series.pct_change()
        result = StatisticalFeatures.volatility_features(returns, windows=[7, 14, 30])

        assert "volatility_7" in result
        assert "volatility_14" in result
        assert "volatility_30" in result


class TestStatisticalFeaturesMomentum:
    """Tests for StatisticalFeatures.momentum_features method."""

    def test_momentum_features_default(self, sample_price_series):
        """Test momentum features with default periods."""
        result = StatisticalFeatures.momentum_features(sample_price_series)

        assert isinstance(result, dict)
        assert "momentum_1" in result
        assert "momentum_5" in result
        assert "momentum_10" in result
        assert "momentum_20" in result
        assert "rate_of_change_1" in result

    def test_momentum_features_custom_periods(self, sample_price_series):
        """Test momentum features with custom periods."""
        result = StatisticalFeatures.momentum_features(
            sample_price_series, periods=[3, 7, 21]
        )

        assert "momentum_3" in result
        assert "momentum_7" in result
        assert "momentum_21" in result


# ==============================================================================
# CategoricalEncoder Tests
# ==============================================================================


class TestCategoricalEncoderFit:
    """Tests for CategoricalEncoder.fit method."""

    def test_fit_basic(self, sample_categorical_data):
        """Test basic encoder fitting."""
        encoder = CategoricalEncoder()
        result = encoder.fit(sample_categorical_data, ["sector", "market"])

        assert result is encoder  # Returns self
        assert encoder.fitted
        assert "sector" in encoder.encodings
        assert "market" in encoder.encodings

    def test_fit_creates_mapping(self, sample_categorical_data):
        """Test fit creates correct mappings."""
        encoder = CategoricalEncoder()
        encoder.fit(sample_categorical_data, ["sector"])

        # Each unique value should have a mapping
        assert len(encoder.encodings["sector"]) == len(
            sample_categorical_data["sector"].unique()
        )


class TestCategoricalEncoderTransform:
    """Tests for CategoricalEncoder.transform method."""

    def test_transform_basic(self, sample_categorical_data):
        """Test basic transformation."""
        encoder = CategoricalEncoder()
        encoder.fit(sample_categorical_data, ["sector", "market"])

        transformed = encoder.transform(sample_categorical_data)

        # Categorical columns should now be numeric
        assert transformed["sector"].dtype in [np.int64, np.float64, int, float]
        assert transformed["market"].dtype in [np.int64, np.float64, int, float]

    def test_transform_not_fitted_raises(self, sample_categorical_data):
        """Test transform raises when not fitted."""
        encoder = CategoricalEncoder()
        with pytest.raises(ValueError, match="Encoder not fitted"):
            encoder.transform(sample_categorical_data)


class TestCategoricalEncoderFitTransform:
    """Tests for CategoricalEncoder.fit_transform method."""

    def test_fit_transform_basic(self, sample_categorical_data):
        """Test combined fit_transform."""
        encoder = CategoricalEncoder()
        result = encoder.fit_transform(sample_categorical_data, ["sector"])

        assert encoder.fitted
        assert result["sector"].dtype in [np.int64, np.float64, int, float]


class TestCategoricalEncoderOneHot:
    """Tests for CategoricalEncoder.one_hot_encode method."""

    def test_one_hot_basic(self, sample_categorical_data):
        """Test basic one-hot encoding."""
        encoder = CategoricalEncoder()
        result = encoder.one_hot_encode(sample_categorical_data, ["market"])

        # Should have new columns for market values
        assert "sector" in result.columns  # Not encoded, should remain
        assert "market" not in result.columns  # Should be replaced

    def test_one_hot_drop_first(self, sample_categorical_data):
        """Test one-hot with drop_first=True."""
        encoder = CategoricalEncoder()
        result = encoder.one_hot_encode(
            sample_categorical_data, ["market"], drop_first=True
        )

        # With drop_first, should have n-1 columns
        market_cols = [c for c in result.columns if c.startswith("market_")]
        assert len(market_cols) == 1  # 2 unique values, drop first = 1 column

    def test_one_hot_keep_all(self, sample_categorical_data):
        """Test one-hot with drop_first=False."""
        encoder = CategoricalEncoder()
        result = encoder.one_hot_encode(
            sample_categorical_data, ["market"], drop_first=False
        )

        market_cols = [c for c in result.columns if c.startswith("market_")]
        assert len(market_cols) == 2  # 2 unique values


# ==============================================================================
# TemporalFeatures Tests
# ==============================================================================


class TestTemporalFeaturesExtract:
    """Tests for TemporalFeatures.extract_time_features method."""

    def test_extract_basic(self):
        """Test basic time feature extraction."""
        timestamps = pd.date_range("2024-01-15 09:30:00", periods=50, freq="1h")
        result = TemporalFeatures.extract_time_features(timestamps)

        assert isinstance(result, pd.DataFrame)
        assert "year" in result.columns
        assert "month" in result.columns
        assert "day" in result.columns
        assert "hour" in result.columns
        assert "day_of_week" in result.columns
        assert "month_sin" in result.columns
        assert "month_cos" in result.columns
        assert "is_month_start" in result.columns
        assert "is_year_end" in result.columns

    def test_cyclical_features_range(self):
        """Test cyclical features are in [-1, 1]."""
        timestamps = pd.date_range("2024-01-01", periods=365 * 24, freq="1h")
        result = TemporalFeatures.extract_time_features(timestamps)

        for col in ["month_sin", "month_cos", "day_sin", "day_cos", "hour_sin", "hour_cos"]:
            assert result[col].min() >= -1.0
            assert result[col].max() <= 1.0


class TestTemporalFeaturesLags:
    """Tests for TemporalFeatures.create_lags method."""

    def test_create_lags_basic(self, sample_price_series):
        """Test basic lag creation."""
        result = TemporalFeatures.create_lags(sample_price_series, lags=[1, 5, 10])

        assert isinstance(result, pd.DataFrame)
        assert "close_lag_1" in result.columns
        assert "close_lag_5" in result.columns
        assert "close_lag_10" in result.columns

    def test_lags_values_correct(self, sample_price_series):
        """Test lag values are correct."""
        result = TemporalFeatures.create_lags(sample_price_series, lags=[1])

        # Lag 1 should equal shifted series
        expected = sample_price_series.shift(1)
        pd.testing.assert_series_equal(
            result["close_lag_1"], expected, check_names=False
        )

    def test_create_lags_ignores_nonpositive(self, sample_price_series):
        """Test lags ignores non-positive values."""
        result = TemporalFeatures.create_lags(sample_price_series, lags=[0, -1, 1])

        assert "close_lag_0" not in result.columns
        assert "close_lag_-1" not in result.columns
        assert "close_lag_1" in result.columns


class TestTemporalFeaturesLeads:
    """Tests for TemporalFeatures.create_leads method."""

    def test_create_leads_basic(self, sample_price_series):
        """Test basic lead creation with _training_target_only=True."""
        result = TemporalFeatures.create_leads(sample_price_series, leads=[1, 5], _training_target_only=True)

        assert isinstance(result, pd.DataFrame)
        assert "close_lead_1" in result.columns
        assert "close_lead_5" in result.columns

    def test_leads_values_correct(self, sample_price_series):
        """Test lead values are correct."""
        result = TemporalFeatures.create_leads(sample_price_series, leads=[1], _training_target_only=True)

        # Lead 1 should equal shifted series (negative shift)
        expected = sample_price_series.shift(-1)
        pd.testing.assert_series_equal(
            result["close_lead_1"], expected, check_names=False
        )

    def test_create_leads_raises_without_flag(self, sample_price_series):
        """P&L-023: Calling create_leads without _training_target_only=True must raise."""
        with pytest.raises(ValueError, match="P&L-023"):
            TemporalFeatures.create_leads(sample_price_series, leads=[1])


# ==============================================================================
# FeatureSelector Tests
# ==============================================================================


class TestFeatureSelectorCorrelation:
    """Tests for FeatureSelector.correlation_filter method."""

    def test_correlation_filter_basic(self):
        """Test basic correlation filtering."""
        np.random.seed(42)
        data = pd.DataFrame({
            "a": np.random.randn(100),
            "b": np.random.randn(100),
            "c": np.random.randn(100),
        })
        # Make 'c' highly correlated with 'a'
        data["c"] = data["a"] * 1.01 + np.random.randn(100) * 0.001

        to_drop = FeatureSelector.correlation_filter(data, threshold=0.95)

        # 'c' should be marked for dropping
        assert "c" in to_drop

    def test_correlation_filter_empty_data(self):
        """Test correlation filter with empty data."""
        result = FeatureSelector.correlation_filter(pd.DataFrame(), threshold=0.95)
        assert result == []

    def test_correlation_filter_non_numeric(self):
        """Test correlation filter with non-numeric data."""
        data = pd.DataFrame({"text": ["a", "b", "c"]})
        result = FeatureSelector.correlation_filter(data)
        assert result == []


class TestFeatureSelectorVariance:
    """Tests for FeatureSelector.variance_filter method."""

    def test_variance_filter_basic(self):
        """Test basic variance filtering."""
        data = pd.DataFrame({
            "high_var": np.random.randn(100) * 10,
            "low_var": np.ones(100) * 5 + np.random.randn(100) * 0.001,
            "constant": np.ones(100),
        })

        to_drop = FeatureSelector.variance_filter(data, threshold=0.01)

        assert "constant" in to_drop  # Zero variance
        assert "high_var" not in to_drop

    def test_variance_filter_empty_data(self):
        """Test variance filter with empty data."""
        result = FeatureSelector.variance_filter(pd.DataFrame())
        assert result == []


class TestFeatureSelectorMissingValue:
    """Tests for FeatureSelector.missing_value_filter method."""

    def test_missing_value_filter_basic(self):
        """Test basic missing value filtering."""
        data = pd.DataFrame({
            "no_missing": range(10),
            "some_missing": [1, 2, 3, np.nan, np.nan, 6, 7, 8, 9, 10],
            "lots_missing": [np.nan] * 6 + [1, 2, 3, 4],
        })

        to_drop = FeatureSelector.missing_value_filter(data, threshold=0.5)

        assert "lots_missing" in to_drop  # 60% missing
        assert "no_missing" not in to_drop
        assert "some_missing" not in to_drop  # 20% missing

    def test_missing_value_filter_empty_data(self):
        """Test missing value filter with empty data."""
        result = FeatureSelector.missing_value_filter(pd.DataFrame())
        assert result == []


# ==============================================================================
# FeatureEngineer Tests
# ==============================================================================


class TestFeatureEngineerInit:
    """Tests for FeatureEngineer initialization."""

    def test_init_default(self):
        """Test default initialization."""
        engineer = FeatureEngineer()

        assert engineer.config == []
        assert isinstance(engineer.technical_indicators, TechnicalIndicators)
        assert isinstance(engineer.statistical_features, StatisticalFeatures)
        assert isinstance(engineer.categorical_encoder, CategoricalEncoder)
        assert isinstance(engineer.temporal_features, TemporalFeatures)
        assert isinstance(engineer.feature_selector, FeatureSelector)
        assert not engineer.is_fitted

    def test_init_with_config(self):
        """Test initialization with config."""
        config = [
            FeatureConfig(
                name="sma_20",
                feature_type=FeatureType.TECHNICAL,
                parameters={"window": 20},
            )
        ]
        engineer = FeatureEngineer(config=config)

        assert len(engineer.config) == 1


class TestFeatureEngineerAddConfig:
    """Tests for FeatureEngineer.add_feature_config method."""

    def test_add_feature_config(self):
        """Test adding feature config."""
        engineer = FeatureEngineer()
        config = FeatureConfig(
            name="test",
            feature_type=FeatureType.DERIVED,
            parameters={},
        )

        engineer.add_feature_config(config)
        assert len(engineer.config) == 1
        assert engineer.config[0].name == "test"


class TestFeatureEngineerTechnicalFeatures:
    """Tests for FeatureEngineer.create_technical_features method."""

    def test_create_technical_features_basic(self, sample_ohlcv_data):
        """Test basic technical feature creation."""
        engineer = FeatureEngineer()
        result = engineer.create_technical_features(sample_ohlcv_data)

        assert len(result.columns) > len(sample_ohlcv_data.columns)
        # Check for various technical indicators
        assert "rsi" in result.columns
        assert "macd" in result.columns
        assert "bb_upper" in result.columns
        assert "atr" in result.columns

    def test_create_technical_features_no_close_raises(self):
        """Test error when no close column."""
        engineer = FeatureEngineer()
        data = pd.DataFrame({"open": [1, 2, 3]})

        with pytest.raises(ValueError, match="must contain 'close' column"):
            engineer.create_technical_features(data)

    def test_create_technical_features_moving_averages(self, sample_ohlcv_data):
        """Test moving average features are created."""
        engineer = FeatureEngineer()
        result = engineer.create_technical_features(sample_ohlcv_data)

        for window in [5, 10, 20, 50, 200]:
            assert f"sma_{window}" in result.columns
            assert f"ema_{window}" in result.columns


class TestFeatureEngineerStatisticalFeatures:
    """Tests for FeatureEngineer.create_statistical_features method."""

    def test_create_statistical_features_basic(self, sample_ohlcv_data):
        """Test basic statistical feature creation."""
        engineer = FeatureEngineer()
        result = engineer.create_statistical_features(sample_ohlcv_data)

        assert "returns" in result.columns
        assert "log_returns" in result.columns

    def test_create_statistical_features_rolling(self, sample_ohlcv_data):
        """Test rolling statistical features."""
        engineer = FeatureEngineer()
        result = engineer.create_statistical_features(sample_ohlcv_data)

        # Should have rolling stats for various windows
        assert "mean_5" in result.columns or "mean_10" in result.columns

    def test_create_statistical_features_momentum(self, sample_ohlcv_data):
        """Test momentum features."""
        engineer = FeatureEngineer()
        result = engineer.create_statistical_features(sample_ohlcv_data)

        assert "momentum_1" in result.columns


class TestFeatureEngineerTemporalFeatures:
    """Tests for FeatureEngineer.create_temporal_features method."""

    def test_create_temporal_features_basic(self, sample_ohlcv_data):
        """Test basic temporal feature creation."""
        engineer = FeatureEngineer()
        result = engineer.create_temporal_features(sample_ohlcv_data)

        # Should have time-based features
        assert "hour" in result.columns
        assert "day_of_week" in result.columns

    def test_create_temporal_features_lags(self, sample_ohlcv_data):
        """Test lag features are created."""
        engineer = FeatureEngineer()
        result = engineer.create_temporal_features(sample_ohlcv_data)

        # Should have lag features for close
        assert "close_lag_1" in result.columns


class TestFeatureEngineerFit:
    """Tests for FeatureEngineer.fit method."""

    def test_fit_basic(self, sample_ohlcv_data):
        """Test basic fitting."""
        engineer = FeatureEngineer()
        result = engineer.fit(sample_ohlcv_data)

        assert result is engineer
        assert engineer.is_fitted

    def test_fit_with_categorical(self, sample_categorical_data):
        """Test fitting with categorical columns."""
        engineer = FeatureEngineer()
        engineer.fit(sample_categorical_data, categorical_columns=["sector", "market"])

        assert engineer.is_fitted
        assert engineer.categorical_encoder.fitted


class TestFeatureEngineerTransform:
    """Tests for FeatureEngineer.transform method."""

    def test_transform_all_features(self, sample_ohlcv_data):
        """Test transform with all feature types."""
        engineer = FeatureEngineer()
        result = engineer.transform(
            sample_ohlcv_data,
            include_technical=True,
            include_statistical=True,
            include_temporal=True,
        )

        # Should have many more columns
        assert len(result.columns) > len(sample_ohlcv_data.columns) * 2

    def test_transform_technical_only(self, sample_ohlcv_data):
        """Test transform with only technical features."""
        engineer = FeatureEngineer()
        result = engineer.transform(
            sample_ohlcv_data,
            include_technical=True,
            include_statistical=False,
            include_temporal=False,
        )

        assert "rsi" in result.columns
        # Temporal features should not be added
        assert "hour" not in result.columns

    def test_transform_handles_errors(self):
        """Test transform raises RuntimeError on transformation failure (fail-fast for ML safety)."""
        engineer = FeatureEngineer()
        # Data without 'close' will fail technical features
        data = pd.DataFrame({"open": [1, 2, 3]})

        with pytest.raises(RuntimeError, match="Feature transformation failed"):
            engineer.transform(
                data,
                include_technical=True,
                include_statistical=False,
                include_temporal=False,
            )


class TestFeatureEngineerFitTransform:
    """Tests for FeatureEngineer.fit_transform method."""

    def test_fit_transform_basic(self, sample_ohlcv_data):
        """Test combined fit_transform."""
        engineer = FeatureEngineer()
        result = engineer.fit_transform(sample_ohlcv_data)

        assert engineer.is_fitted
        assert isinstance(result, pd.DataFrame)
        assert len(result.columns) > len(sample_ohlcv_data.columns)


class TestFeatureEngineerSelectFeatures:
    """Tests for FeatureEngineer.select_features method."""

    def test_select_features_basic(self, sample_ohlcv_data):
        """Test basic feature selection."""
        engineer = FeatureEngineer()
        # First add many features
        features = engineer.transform(sample_ohlcv_data)

        # Then select
        selected = engineer.select_features(
            features,
            correlation_threshold=0.95,
            variance_threshold=0.01,
            missing_threshold=0.5,
        )

        # Should have fewer or equal columns
        assert len(selected.columns) <= len(features.columns)

    def test_select_features_no_numeric(self):
        """Test feature selection with no numeric columns."""
        engineer = FeatureEngineer()
        data = pd.DataFrame({"text": ["a", "b", "c"]})

        result = engineer.select_features(data)
        pd.testing.assert_frame_equal(result, data)


class TestFeatureEngineerImportance:
    """Tests for FeatureEngineer.get_feature_importance method."""

    def test_get_feature_importance_basic(self, sample_ohlcv_data):
        """Test basic feature importance calculation."""
        engineer = FeatureEngineer()
        importance = engineer.get_feature_importance(sample_ohlcv_data)

        assert isinstance(importance, dict)
        assert len(importance) == len(
            sample_ohlcv_data.select_dtypes(include=[np.number]).columns
        )

    def test_importance_sums_to_one(self, sample_ohlcv_data):
        """Test importance values sum to 1."""
        engineer = FeatureEngineer()
        importance = engineer.get_feature_importance(sample_ohlcv_data)

        total = sum(importance.values())
        assert abs(total - 1.0) < 0.01

    def test_importance_no_numeric(self):
        """Test importance with no numeric columns."""
        engineer = FeatureEngineer()
        data = pd.DataFrame({"text": ["a", "b", "c"]})

        result = engineer.get_feature_importance(data)
        assert result == {}


# ==============================================================================
# Helper Function Tests
# ==============================================================================


class TestCreateSampleFinancialData:
    """Tests for create_sample_financial_data function."""

    def test_basic_creation(self):
        """Test basic sample data creation."""
        data = create_sample_financial_data()

        assert isinstance(data, pd.DataFrame)
        assert len(data) == 1000
        assert "open" in data.columns
        assert "high" in data.columns
        assert "low" in data.columns
        assert "close" in data.columns
        assert "volume" in data.columns
        assert "symbol" in data.columns
        assert "market" in data.columns

    def test_custom_rows(self):
        """Test with custom row count."""
        data = create_sample_financial_data(n_rows=500)
        assert len(data) == 500

    def test_custom_start_date(self):
        """Test with custom start date."""
        data = create_sample_financial_data(start_date="2025-06-01")
        assert data.index[0] == pd.Timestamp("2025-06-01")

    def test_has_datetime_index(self):
        """Test data has DatetimeIndex."""
        data = create_sample_financial_data()
        assert isinstance(data.index, pd.DatetimeIndex)

    def test_prices_positive(self):
        """Test all prices are positive."""
        data = create_sample_financial_data()

        for col in ["open", "high", "low", "close"]:
            assert (data[col] > 0).all()

    def test_high_low_relationship(self):
        """Test high >= low."""
        data = create_sample_financial_data()
        assert (data["high"] >= data["low"]).all()


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_feature_engineering_workflow(self):
        """Test complete feature engineering workflow."""
        # Create sample data
        data = create_sample_financial_data(n_rows=200)

        # Initialize engineer
        engineer = FeatureEngineer()

        # Fit and transform
        result = engineer.fit_transform(
            data,
            categorical_columns=["symbol", "market"],
        )

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 200
        assert len(result.columns) > len(data.columns)

    def test_technical_and_selection(self, sample_ohlcv_data):
        """Test technical features then selection."""
        engineer = FeatureEngineer()

        # Create features
        features = engineer.create_technical_features(sample_ohlcv_data)

        # Select features
        selected = engineer.select_features(features, correlation_threshold=0.9)

        assert len(selected.columns) <= len(features.columns)

    def test_statistical_features_chain(self, sample_ohlcv_data):
        """Test chaining statistical feature operations."""
        # Price features
        price_feats = StatisticalFeatures.price_features(sample_ohlcv_data["close"])

        # Volatility features on returns
        vol_feats = StatisticalFeatures.volatility_features(price_feats["returns"])

        # Momentum features
        mom_feats = StatisticalFeatures.momentum_features(sample_ohlcv_data["close"])

        assert len(price_feats) > 0
        assert len(vol_feats) > 0
        assert len(mom_feats) > 0
