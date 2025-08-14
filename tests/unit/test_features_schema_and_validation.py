"""
Test feature schema validation and data structures.
"""

import numpy as np
import pandas as pd
import pytest

from backend.features.types import (
    FeatureFrame,
    FeatureSchema,
    LookaheadLeakError,
)
from backend.features.validators import (
    detect_forward_fill_leakage,
    guard_no_lookahead,
    validate_ohlcv,
)


class TestFeatureSchema:
    """Test FeatureSchema validation and operations."""

    def test_schema_creation_valid(self):
        """Test valid schema creation."""
        schema = FeatureSchema(
            columns=["feature1", "feature2", "feature3"],
            dtypes={"feature1": "float64", "feature2": "int32", "feature3": "bool"},
        )

        assert schema.columns == ["feature1", "feature2", "feature3"]
        assert schema.dtypes["feature1"] == "float64"
        assert schema.dtypes["feature2"] == "int32"
        assert schema.dtypes["feature3"] == "bool"

    def test_schema_creation_duplicate_columns(self):
        """Test schema creation with duplicate columns fails."""
        with pytest.raises(ValueError, match="Duplicate column names"):
            FeatureSchema(
                columns=["feature1", "feature1", "feature2"],
                dtypes={"feature1": "float64", "feature2": "int32"},
            )

    def test_schema_creation_mismatched_dtypes(self):
        """Test schema creation with mismatched columns/dtypes fails."""
        with pytest.raises(ValueError, match="Columns and dtypes keys must match"):
            FeatureSchema(
                columns=["feature1", "feature2"],
                dtypes={"feature1": "float64", "feature3": "int32"},  # Wrong key
            )

    def test_validate_dataframe_valid(self):
        """Test DataFrame validation with valid data."""
        schema = FeatureSchema(
            columns=["price", "volume", "signal"],
            dtypes={"price": "float64", "volume": "int64", "signal": "bool"},
        )

        df = pd.DataFrame(
            {
                "price": [100.5, 101.2, 99.8],
                "volume": [1000, 1500, 800],
                "signal": [True, False, True],
            }
        )

        # Should not raise
        schema.validate_dataframe(df)

    def test_validate_dataframe_missing_columns(self):
        """Test DataFrame validation with missing columns."""
        schema = FeatureSchema(
            columns=["price", "volume", "signal"],
            dtypes={"price": "float64", "volume": "int64", "signal": "bool"},
        )

        df = pd.DataFrame(
            {
                "price": [100.5, 101.2],
                "volume": [1000, 1500],
                # Missing 'signal'
            }
        )

        with pytest.raises(ValueError, match="Missing columns: \\['signal'\\]"):
            schema.validate_dataframe(df)

    def test_validate_dataframe_extra_columns(self):
        """Test DataFrame validation with extra columns."""
        schema = FeatureSchema(
            columns=["price", "volume"], dtypes={"price": "float64", "volume": "int64"}
        )

        df = pd.DataFrame(
            {
                "price": [100.5, 101.2],
                "volume": [1000, 1500],
                "extra_col": [1, 2],  # Extra column
            }
        )

        with pytest.raises(ValueError, match="Extra columns: \\['extra_col'\\]"):
            schema.validate_dataframe(df)

    def test_reorder_columns(self):
        """Test column reordering functionality."""
        schema = FeatureSchema(
            columns=["c", "a", "b"],  # Specific order
            dtypes={"a": "float64", "b": "int64", "c": "bool"},
        )

        df = pd.DataFrame({"a": [1.0, 2.0], "b": [10, 20], "c": [True, False]})

        reordered = schema.reorder_columns(df)
        assert list(reordered.columns) == ["c", "a", "b"]
        assert reordered["c"].tolist() == [True, False]
        assert reordered["a"].tolist() == [1.0, 2.0]


class TestFeatureFrame:
    """Test FeatureFrame data container."""

    def test_feature_frame_creation_valid(self):
        """Test valid FeatureFrame creation."""
        index = pd.date_range("2023-01-01", periods=3, freq="1min")

        X = pd.DataFrame(
            {"feature1": [1.0, 2.0, 3.0], "feature2": [10, 20, 30]}, index=index
        )

        y = pd.Series([0.01, 0.02, -0.01], index=index, name="returns")
        mask = pd.Series([True, True, False], index=index)

        frame = FeatureFrame(X=X, y=y, index_mask=mask)

        assert len(frame.X) == 3
        assert frame.y is not None
        assert frame.valid_rows == 2  # Only 2 True values in mask

    def test_feature_frame_misaligned_indices(self):
        """Test FeatureFrame creation with misaligned indices fails."""
        index1 = pd.date_range("2023-01-01", periods=3, freq="1min")
        index2 = pd.date_range("2023-01-02", periods=3, freq="1min")  # Different dates

        X = pd.DataFrame({"feature1": [1, 2, 3]}, index=index1)
        y = pd.Series([0.1, 0.2, 0.3], index=index2)  # Misaligned
        mask = pd.Series([True, True, True], index=index1)

        with pytest.raises(
            ValueError, match="Feature and target indices must be aligned"
        ):
            FeatureFrame(X=X, y=y, index_mask=mask)

    def test_feature_frame_filter_valid(self):
        """Test filtering to valid rows only."""
        index = pd.date_range("2023-01-01", periods=4, freq="1min")

        X = pd.DataFrame(
            {"feature1": [1.0, 2.0, 3.0, 4.0], "feature2": [10, 20, 30, 40]},
            index=index,
        )

        y = pd.Series([0.01, 0.02, -0.01, 0.03], index=index)
        mask = pd.Series(
            [True, False, True, False], index=index
        )  # Only 1st and 3rd valid

        frame = FeatureFrame(X=X, y=y, index_mask=mask)
        filtered = frame.filter_valid()

        assert len(filtered.X) == 2
        assert filtered.X.iloc[0]["feature1"] == 1.0  # First valid row
        assert filtered.X.iloc[1]["feature1"] == 3.0  # Third row (index 2)
        assert filtered.y.iloc[0] == 0.01
        assert filtered.y.iloc[1] == -0.01


class TestOHLCVValidation:
    """Test OHLCV data validation."""

    def test_validate_ohlcv_valid(self):
        """Test valid OHLCV data passes validation."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0],
                "high": [105.0, 106.0, 107.0],
                "low": [98.0, 99.0, 100.0],
                "close": [104.0, 105.0, 103.0],
                "volume": [1000, 1500, 1200],
            },
            index=pd.date_range("2023-01-01", periods=3, freq="1min", tz="UTC"),
        )

        # Should not raise
        validate_ohlcv(df)

    def test_validate_ohlcv_missing_columns(self):
        """Test OHLCV validation with missing required columns."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [105.0, 106.0],
                "close": [104.0, 105.0],
                # Missing 'low' and 'volume'
            }
        )

        with pytest.raises(ValueError, match="Missing required OHLCV columns"):
            validate_ohlcv(df)

    def test_validate_ohlcv_negative_volume(self):
        """Test OHLCV validation with negative volume."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [105.0, 106.0],
                "low": [98.0, 99.0],
                "close": [104.0, 105.0],
                "volume": [1000, -500],  # Negative volume
            }
        )

        with pytest.raises(ValueError, match="Volume cannot be negative"):
            validate_ohlcv(df)

    def test_validate_ohlcv_invalid_relationships(self):
        """Test OHLCV validation with invalid high/low relationships."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [95.0, 106.0],  # First high < open (invalid)
                "low": [98.0, 99.0],
                "close": [104.0, 105.0],
                "volume": [1000, 1500],
            }
        )

        with pytest.raises(ValueError, match="Invalid OHLC relationships"):
            validate_ohlcv(df)


class TestLookaheadDetection:
    """Test lookahead bias detection."""

    def test_guard_no_lookahead_clean_features(self):
        """Test lookahead guard with properly lagged features."""
        # Create synthetic price series
        np.random.seed(42)
        dates = pd.date_range("2023-01-01", periods=200, freq="1min", tz="UTC")
        price = pd.Series(100 + np.cumsum(np.random.randn(200) * 0.1), index=dates)

        # Create properly lagged features (using past price)
        features = pd.DataFrame(
            {
                "sma_5": price.rolling(5).mean().shift(1),  # Properly lagged
                "returns_1": price.pct_change().shift(1),  # Properly lagged
                "rsi": price.rolling(14).apply(
                    lambda x: 50 + np.random.randn()
                ),  # Random oscillator
            },
            index=dates,
        )

        # Should not raise (no lookahead detected)
        guard_no_lookahead(features, price, threshold=0.7)

    def test_guard_no_lookahead_detects_future_leak(self):
        """Test lookahead guard detects features using future information."""
        # Create synthetic price series
        np.random.seed(42)
        dates = pd.date_range("2023-01-01", periods=200, freq="1min", tz="UTC")
        price = pd.Series(100 + np.cumsum(np.random.randn(200) * 0.1), index=dates)

        # Create features with intentional lookahead bias
        features = pd.DataFrame(
            {
                "good_feature": price.rolling(5).mean().shift(1),  # Properly lagged
                "leaked_feature": price.shift(-1),  # Using next period price!
            },
            index=dates,
        )

        # Should raise LookaheadLeakError
        with pytest.raises(
            LookaheadLeakError, match="Potential lookahead bias detected"
        ):
            guard_no_lookahead(features, price, threshold=0.6)


class TestForwardFillDetection:
    """Test forward-fill leakage detection."""

    def test_detect_forward_fill_normal_data(self):
        """Test forward-fill detection with normal varying data."""
        df = pd.DataFrame(
            {
                "price": [100, 101, 102, 103, 104],
                "volume": [1000, 1100, 1200, 1300, 1400],
                "volatility": [0.1, 0.12, 0.08, 0.15, 0.11],
            }
        )

        suspicious = detect_forward_fill_leakage(df, max_consecutive_fill=3)
        assert len(suspicious) == 0  # No suspicious columns

    def test_detect_forward_fill_suspicious_data(self):
        """Test forward-fill detection with suspicious repeated values."""
        df = pd.DataFrame(
            {
                "price": [100, 101, 102, 103, 104],
                "suspicious_col": [50, 50, 50, 50, 50],  # All same value
                "partially_filled": [
                    1.0,
                    2.0,
                    2.0,
                    2.0,
                    2.0,
                ],  # 4 consecutive same values
            }
        )

        suspicious = detect_forward_fill_leakage(df, max_consecutive_fill=3)
        assert "suspicious_col" in suspicious
        assert "partially_filled" in suspicious
        assert "price" not in suspicious
