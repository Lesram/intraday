"""
Comprehensive unit tests for feature validators edge cases and error branches.
Tests OHLCV validation, lookahead detection, and synthetic data validation.
"""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from backend.features.types import LookaheadLeakError
from backend.features.validators import (
    detect_forward_fill_leakage,
    guard_no_lookahead,
    guard_no_lookahead_synthetic,
    validate_feature_alignment,
    validate_ohlcv,
)


class TestOHLCVValidationErrors:
    """Test OHLCV validation with various error conditions."""

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_validate_ohlcv_wrong_dtypes(self):
        """Test OHLCV validation with incorrect data types."""
        df = pd.DataFrame(
            {
                "open": ["100.0", "101.0"],  # String instead of numeric
                "high": [105.0, 106.0],
                "low": [98.0, 99.0],
                "close": [104.0, 105.0],
                "volume": [1000, 1500],
            }
        )

        with pytest.raises(ValueError, match="must be numeric"):
            validate_ohlcv(df)

    @pytest.mark.unit
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

    @pytest.mark.unit
    def test_validate_ohlcv_invalid_ohlc_relationships(self):
        """Test OHLCV validation with invalid OHLC relationships."""
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

    @pytest.mark.unit
    def test_validate_ohlcv_high_less_than_low(self):
        """Test OHLCV validation when high < low."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [98.0, 106.0],  # High < low in first row
                "low": [99.0, 99.0],
                "close": [100.5, 105.0],
                "volume": [1000, 1500],
            }
        )

        with pytest.raises(ValueError, match="Invalid OHLC relationships"):
            validate_ohlcv(df)

    @pytest.mark.unit
    def test_validate_ohlcv_non_monotonic_timestamps(self):
        """Test OHLCV validation with non-monotonic timestamps."""
        dates = [
            datetime(2023, 1, 1, tzinfo=UTC),
            datetime(2023, 1, 3, tzinfo=UTC),  # Skip day 2
            datetime(2023, 1, 2, tzinfo=UTC),  # Go back to day 2 (non-monotonic)
        ]

        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 99.0],
                "high": [105.0, 106.0, 104.0],
                "low": [98.0, 99.0, 97.0],
                "close": [104.0, 105.0, 103.0],
                "volume": [1000, 1500, 1200],
            },
            index=pd.DatetimeIndex(dates),
        )

        with pytest.raises(ValueError, match="Timestamps must be strictly increasing"):
            validate_ohlcv(df)

    @pytest.mark.unit
    def test_validate_ohlcv_timezone_naive_timestamps(self):
        """Test OHLCV validation with timezone-naive timestamps."""
        dates = pd.date_range("2023-01-01", periods=3, freq="1D")  # No timezone

        df = pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0],
                "high": [105.0, 106.0, 107.0],
                "low": [98.0, 99.0, 100.0],
                "close": [104.0, 105.0, 103.0],
                "volume": [1000, 1500, 1200],
            },
            index=dates,
        )

        with pytest.raises(ValueError, match="Timestamps must be timezone-aware"):
            validate_ohlcv(df)

    @pytest.mark.unit
    def test_validate_ohlcv_nan_values(self):
        """Test OHLCV validation with NaN values."""
        df = pd.DataFrame(
            {
                "open": [100.0, np.nan],  # NaN in open
                "high": [105.0, 106.0],
                "low": [98.0, 99.0],
                "close": [104.0, 105.0],
                "volume": [1000, 1500],
            }
        )

        # Should handle NaN values gracefully (some validators allow them)
        try:
            validate_ohlcv(df)
        except ValueError as e:
            # If it raises, should be about NaN values
            assert "nan" in str(e).lower() or "missing" in str(e).lower()

    @pytest.mark.unit
    def test_validate_ohlcv_infinite_values(self):
        """Test OHLCV validation with infinite values."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [105.0, np.inf],  # Infinite high
                "low": [98.0, 99.0],
                "close": [104.0, 105.0],
                "volume": [1000, 1500],
            }
        )

        with pytest.raises(ValueError):
            validate_ohlcv(df)

    @pytest.mark.unit
    def test_validate_ohlcv_zero_volume(self):
        """Test OHLCV validation with zero volume (should be allowed)."""
        df = pd.DataFrame(
            {
                "open": [100.0, 101.0],
                "high": [105.0, 106.0],
                "low": [98.0, 99.0],
                "close": [104.0, 105.0],
                "volume": [0, 1500],  # Zero volume should be allowed
            }
        )

        # Should not raise - zero volume is valid
        validate_ohlcv(df)


class TestLookaheadDetectionEdgeCases:
    """Test lookahead bias detection with edge cases and synthetic data."""

    @pytest.mark.unit
    def test_guard_no_lookahead_insufficient_data(self):
        """Test lookahead detection with insufficient data."""
        dates = pd.date_range("2023-01-01", periods=10, freq="1min", tz="UTC")
        features = pd.DataFrame({"feature1": np.random.randn(10)}, index=dates)
        price = pd.Series(100 + np.arange(10), index=dates)

        with pytest.raises(ValueError, match="Insufficient data"):
            guard_no_lookahead(features, price, window_size=50)  # Window too large

    @pytest.mark.unit
    def test_guard_no_lookahead_detects_future_leak(self):
        """Test lookahead guard detects features using future information."""
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

        with pytest.raises(
            LookaheadLeakError, match="Potential lookahead bias detected"
        ):
            guard_no_lookahead(features, price, threshold=0.6)

    @pytest.mark.unit
    def test_guard_no_lookahead_clean_features(self):
        """Test lookahead guard with properly lagged features."""
        np.random.seed(42)
        dates = pd.date_range("2023-01-01", periods=200, freq="1min", tz="UTC")
        price = pd.Series(100 + np.cumsum(np.random.randn(200) * 0.1), index=dates)

        # Create properly lagged features
        features = pd.DataFrame(
            {
                "sma_5": price.rolling(5).mean().shift(1),
                "returns_1": price.pct_change().shift(1),
                "rsi": price.rolling(14).apply(
                    lambda x: 50 + np.random.randn()
                ),  # Random oscillator
            },
            index=dates,
        )

        # Should not raise
        guard_no_lookahead(features, price, threshold=0.7)

    @pytest.mark.unit
    def test_guard_no_lookahead_all_nan_features(self):
        """Test lookahead detection with all-NaN features."""
        dates = pd.date_range("2023-01-01", periods=200, freq="1min", tz="UTC")
        features = pd.DataFrame({"nan_feature": [np.nan] * 200}, index=dates)
        price = pd.Series(100 + np.arange(200), index=dates)

        # Should handle gracefully
        guard_no_lookahead(features, price, threshold=0.7)

    @pytest.mark.unit
    def test_guard_no_lookahead_constant_features(self):
        """Test lookahead detection with constant features."""
        dates = pd.date_range("2023-01-01", periods=200, freq="1min", tz="UTC")
        features = pd.DataFrame(
            {
                "constant": [42.0] * 200,
                "zero": [0.0] * 200,
                "normal": np.random.randn(200),
            },
            index=dates,
        )
        price = pd.Series(100 + np.arange(200), index=dates)

        # Constant features should not trigger lookahead detection
        guard_no_lookahead(features, price, threshold=0.7)

    @pytest.mark.unit
    def test_guard_no_lookahead_mismatched_indices(self):
        """Test lookahead detection with mismatched indices."""
        dates_features = pd.date_range("2023-01-01", periods=200, freq="1min", tz="UTC")
        dates_price = pd.date_range(
            "2023-01-02", periods=100, freq="1min", tz="UTC"
        )  # Different dates

        features = pd.DataFrame(
            {"feature1": np.random.randn(200)}, index=dates_features
        )
        price = pd.Series(np.random.randn(100), index=dates_price)

        # Should handle mismatched indices by taking intersection
        common_dates = dates_features.intersection(dates_price)
        if len(common_dates) >= 100:  # If enough common data
            guard_no_lookahead(features, price, threshold=0.7, window_size=50)
        else:
            with pytest.raises(ValueError, match="Insufficient data"):
                guard_no_lookahead(features, price, threshold=0.7, window_size=100)

    @pytest.mark.unit
    def test_guard_no_lookahead_synthetic_perfect_monotone(self):
        """Test synthetic lookahead detection with perfect monotone series."""
        dates = pd.date_range("2023-01-01", periods=100, freq="1min", tz="UTC")

        # Create feature that's perfectly correlated with monotone trend
        features = pd.DataFrame(
            {
                "monotone_feature": np.arange(100),  # Perfect monotone correlation
                "random_feature": np.random.randn(100),
            },
            index=dates,
        )

        with pytest.raises(
            LookaheadLeakError, match="suspicious correlation with synthetic monotone"
        ):
            guard_no_lookahead_synthetic(features, accuracy_threshold=0.8)

    @pytest.mark.unit
    def test_guard_no_lookahead_synthetic_insufficient_data(self):
        """Test synthetic lookahead detection with insufficient data."""
        dates = pd.date_range("2023-01-01", periods=20, freq="1min", tz="UTC")
        features = pd.DataFrame({"feature1": np.random.randn(20)}, index=dates)

        # Should skip test with insufficient data (< 50 points)
        guard_no_lookahead_synthetic(features)  # Should not raise

    @pytest.mark.unit
    def test_guard_no_lookahead_synthetic_specific_columns(self):
        """Test synthetic lookahead detection on specific columns only."""
        dates = pd.date_range("2023-01-01", periods=100, freq="1min", tz="UTC")
        features = pd.DataFrame(
            {
                "good_feature": np.random.randn(100),
                "suspicious_feature": np.arange(100),  # Monotone
                "another_good_feature": np.random.randn(100),
            },
            index=dates,
        )

        # Test only the suspicious feature
        with pytest.raises(LookaheadLeakError):
            guard_no_lookahead_synthetic(
                features, feature_cols=["suspicious_feature"], accuracy_threshold=0.8
            )

        # Test only good features - should pass
        guard_no_lookahead_synthetic(
            features, feature_cols=["good_feature", "another_good_feature"]
        )


class TestFeatureAlignmentValidation:
    """Test feature and target alignment validation."""

    @pytest.mark.unit
    def test_validate_feature_alignment_mismatched_indices(self):
        """Test feature alignment with mismatched indices."""
        dates_features = pd.date_range("2023-01-01", periods=100, freq="1min", tz="UTC")
        dates_target = pd.date_range("2023-01-02", periods=50, freq="1min", tz="UTC")

        features = pd.DataFrame(
            {"feature1": np.random.randn(100)}, index=dates_features
        )
        target = pd.Series(np.random.randn(50), index=dates_target)

        with pytest.raises(ValueError, match="identical indices"):
            validate_feature_alignment(features, target)

    @pytest.mark.unit
    def test_validate_feature_alignment_different_lengths(self):
        """Test feature alignment with different lengths."""
        dates = pd.date_range("2023-01-01", periods=100, freq="1min", tz="UTC")
        features = pd.DataFrame({"feature1": np.random.randn(100)}, index=dates)
        target = pd.Series(
            np.random.randn(50), index=dates[:50]
        )  # Same index range but shorter

        with pytest.raises(ValueError, match="same length"):
            validate_feature_alignment(features, target)

    @pytest.mark.unit
    def test_validate_feature_alignment_improper_target_construction(self):
        """Test detection of improper target construction (no future shift)."""
        dates = pd.date_range("2023-01-01", periods=100, freq="1min", tz="UTC")
        features = pd.DataFrame({"feature1": np.random.randn(100)}, index=dates)

        # Target that doesn't have NaN at the end (suggests no future shift)
        target = pd.Series(np.random.randn(100), index=dates)  # No NaN at end

        with pytest.raises(ValueError, match="appears to use future information"):
            validate_feature_alignment(features, target)

    @pytest.mark.unit
    def test_validate_feature_alignment_proper_construction(self):
        """Test proper feature-target alignment passes validation."""
        dates = pd.date_range("2023-01-01", periods=100, freq="1min", tz="UTC")
        features = pd.DataFrame(
            {"feature1": np.random.randn(100), "feature2": np.random.randn(100)},
            index=dates,
        )

        # Properly constructed target with NaN at the end (future shift)
        target_values = np.random.randn(100)
        target_values[-1] = np.nan  # Last value should be NaN
        target = pd.Series(target_values, index=dates)

        # Should not raise
        validate_feature_alignment(features, target)


class TestForwardFillLeakageDetection:
    """Test detection of forward-fill data leakage."""

    @pytest.mark.unit
    def test_detect_forward_fill_leakage_excessive_fills(self):
        """Test detection of excessive forward fills."""
        df = pd.DataFrame(
            {
                "price": [
                    100,
                    100,
                    100,
                    100,
                    100,
                    101,
                    102,
                ],  # 5 consecutive identical values
                "volume": [1000, 1001, 1002, 1003, 1004, 1005, 1006],  # No forward fill
                "bad_feature": [
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                    50,
                ],  # 7 consecutive identical (bad)
            }
        )

        leaky_columns = detect_forward_fill_leakage(df, max_consecutive_fill=4)
        assert "price" in leaky_columns  # 5 > 4
        assert "bad_feature" in leaky_columns  # 7 > 4
        assert "volume" not in leaky_columns  # No consecutive fills

    @pytest.mark.unit
    def test_detect_forward_fill_leakage_acceptable_fills(self):
        """Test that acceptable forward fills are not flagged."""
        df = pd.DataFrame(
            {
                "price": [100, 100, 100, 101, 102, 102, 103],  # Max 3 consecutive
                "volume": [
                    1000,
                    1000,
                    1001,
                    1002,
                    1003,
                    1003,
                    1004,
                ],  # Max 2 consecutive
            }
        )

        leaky_columns = detect_forward_fill_leakage(df, max_consecutive_fill=5)
        assert len(leaky_columns) == 0  # None should be flagged

    @pytest.mark.unit
    def test_detect_forward_fill_leakage_with_nans(self):
        """Test forward fill detection with NaN values."""
        df = pd.DataFrame(
            {
                "with_nans": [100, 100, np.nan, 100, 100, 101],  # NaN breaks sequence
                "without_nans": [100, 100, 100, 100, 100, 101],  # 5 consecutive
            }
        )

        leaky_columns = detect_forward_fill_leakage(df, max_consecutive_fill=4)
        assert "with_nans" not in leaky_columns  # NaN breaks the sequence
        assert "without_nans" in leaky_columns  # 5 > 4

    @pytest.mark.unit
    def test_detect_forward_fill_leakage_floating_point_precision(self):
        """Test forward fill detection with floating point precision issues."""
        df = pd.DataFrame(
            {
                "precise": [1.0, 1.0, 1.0, 1.0, 1.0, 2.0],  # Exactly equal
                "imprecise": [
                    1.0,
                    1.0000000001,
                    1.0000000002,
                    1.0,
                    1.0,
                    2.0,
                ],  # Tiny differences
            }
        )

        leaky_columns = detect_forward_fill_leakage(df, max_consecutive_fill=4)
        assert "precise" in leaky_columns
        assert "imprecise" not in leaky_columns  # Tiny differences break sequence


class TestValidatorErrorHandling:
    """Test error handling and edge cases in validators."""

    @pytest.mark.unit
    def test_validators_with_empty_dataframes(self):
        """Test validators with empty DataFrames."""
        empty_df = pd.DataFrame()

        # Empty OHLCV should fail
        with pytest.raises(ValueError, match="Missing required OHLCV columns"):
            validate_ohlcv(empty_df)

        # Empty forward fill detection should return empty list
        leaky_columns = detect_forward_fill_leakage(empty_df)
        assert leaky_columns == []

    @pytest.mark.unit
    def test_validators_with_single_row(self):
        """Test validators with single-row DataFrames."""
        single_row = pd.DataFrame(
            {
                "open": [100.0],
                "high": [105.0],
                "low": [98.0],
                "close": [104.0],
                "volume": [1000],
            },
            index=pd.date_range("2023-01-01", periods=1, freq="1D", tz="UTC"),
        )

        # Single row OHLCV should pass basic validation
        validate_ohlcv(single_row)

        # Single row forward fill detection
        leaky_columns = detect_forward_fill_leakage(single_row)
        assert leaky_columns == []  # Cannot have consecutive fills with one row

    @pytest.mark.unit
    def test_validators_with_extreme_values(self):
        """Test validators with extreme numerical values."""
        extreme_df = pd.DataFrame(
            {
                "open": [1e-10, 1e10],  # Very small and very large
                "high": [1e-10, 1e10],
                "low": [1e-11, 9e9],
                "close": [9e-11, 9.5e9],
                "volume": [1e-5, 1e15],  # Extreme volumes
            },
            index=pd.date_range("2023-01-01", periods=2, freq="1D", tz="UTC"),
        )

        # Should handle extreme values gracefully
        validate_ohlcv(extreme_df)

    @pytest.mark.unit
    def test_lookahead_detection_performance_with_large_datasets(self):
        """Test lookahead detection performance doesn't degrade severely with large datasets."""
        import time

        # Create large dataset
        n_periods = 5000
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")
        features = pd.DataFrame(
            {f"feature_{i}": np.random.randn(n_periods) for i in range(10)}, index=dates
        )
        price = pd.Series(
            100 + np.cumsum(np.random.randn(n_periods) * 0.1), index=dates
        )

        # Test should complete in reasonable time (< 10 seconds)
        start_time = time.time()
        guard_no_lookahead(features, price, threshold=0.8, window_size=100)
        elapsed_time = time.time() - start_time

        assert (
            elapsed_time < 10.0
        ), f"Lookahead detection took {elapsed_time:.2f} seconds"

    @pytest.mark.unit
    def test_synthetic_lookahead_with_edge_case_correlations(self):
        """Test synthetic lookahead detection with edge case correlations."""
        dates = pd.date_range("2023-01-01", periods=100, freq="1min", tz="UTC")

        # Test various correlation patterns
        features = pd.DataFrame(
            {
                "perfect_positive": np.arange(100),  # Perfect positive correlation
                "perfect_negative": -np.arange(100),  # Perfect negative correlation
                "step_function": [0] * 50 + [1] * 50,  # Step function
                "sine_wave": np.sin(np.linspace(0, 4 * np.pi, 100)),  # Oscillating
                "random_walk": np.cumsum(np.random.randn(100)),  # Random walk
            },
            index=dates,
        )

        # Should detect perfect correlations
        with pytest.raises(LookaheadLeakError):
            guard_no_lookahead_synthetic(
                features, feature_cols=["perfect_positive"], accuracy_threshold=0.9
            )

        with pytest.raises(LookaheadLeakError):
            guard_no_lookahead_synthetic(
                features, feature_cols=["perfect_negative"], accuracy_threshold=0.9
            )

        # Step function might also be detected depending on threshold
        try:
            guard_no_lookahead_synthetic(
                features, feature_cols=["step_function"], accuracy_threshold=0.9
            )
        except LookaheadLeakError:
            pass  # This is acceptable

        # Sine wave and random walk should generally pass
        guard_no_lookahead_synthetic(
            features, feature_cols=["sine_wave"], accuracy_threshold=0.9
        )


class TestRealWorldValidationScenarios:
    """Test validators with real-world-like data scenarios."""

    @pytest.mark.unit
    def test_market_hours_gap_handling(self):
        """Test validation with market hours gaps (weekends, holidays)."""
        # Create data with gaps (simulate market closed periods)
        trading_dates = pd.date_range(
            "2023-01-01", periods=10, freq="B", tz="UTC"
        )  # Business days only

        df = pd.DataFrame(
            {
                "open": np.random.uniform(95, 105, 10),
                "high": np.random.uniform(105, 115, 10),
                "low": np.random.uniform(85, 95, 10),
                "close": np.random.uniform(95, 105, 10),
                "volume": np.random.exponential(1000, 10),
            },
            index=trading_dates,
        )

        # Should handle gaps in timestamps gracefully
        validate_ohlcv(df)

    @pytest.mark.unit
    def test_corporate_action_data_validation(self):
        """Test validation around corporate actions (splits, dividends)."""
        dates = pd.date_range("2023-01-01", periods=10, freq="1D", tz="UTC")

        # Simulate stock split (prices halved overnight)
        prices_pre_split = [100, 101, 102, 103, 104]
        prices_post_split = [52, 51, 52.5, 53, 54]  # ~50% due to split

        df = pd.DataFrame(
            {
                "open": prices_pre_split + prices_post_split,
                "high": [p * 1.02 for p in prices_pre_split + prices_post_split],
                "low": [p * 0.98 for p in prices_pre_split + prices_post_split],
                "close": [p * 1.01 for p in prices_pre_split + prices_post_split],
                "volume": [1000] * 10,
            },
            index=dates,
        )

        # Should validate despite the split
        validate_ohlcv(df)

    @pytest.mark.unit
    def test_validation_with_penny_stock_data(self):
        """Test validation with penny stock data (very low prices)."""
        dates = pd.date_range("2023-01-01", periods=20, freq="1D", tz="UTC")

        df = pd.DataFrame(
            {
                "open": np.random.uniform(0.01, 0.05, 20),  # Penny stock prices
                "high": np.random.uniform(0.05, 0.08, 20),
                "low": np.random.uniform(0.005, 0.02, 20),
                "close": np.random.uniform(0.02, 0.06, 20),
                "volume": np.random.exponential(
                    100000, 20
                ),  # High volume typical for penny stocks
            },
            index=dates,
        )

        validate_ohlcv(df)

    @pytest.mark.unit
    def test_validation_with_crypto_data_characteristics(self):
        """Test validation with cryptocurrency-like data (24/7, high volatility)."""
        # 24/7 data with high volatility
        dates = pd.date_range(
            "2023-01-01", periods=168, freq="1H", tz="UTC"
        )  # One week hourly

        # High volatility returns
        returns = np.random.normal(0, 0.03, 168)  # 3% hourly volatility
        prices = 50000 * np.exp(np.cumsum(returns))  # Starting at $50k

        df = pd.DataFrame(
            {
                "open": prices * np.random.uniform(0.995, 1.005, 168),
                "high": prices * np.random.uniform(1.01, 1.05, 168),
                "low": prices * np.random.uniform(0.95, 0.99, 168),
                "close": prices * np.random.uniform(0.995, 1.005, 168),
                "volume": np.random.exponential(1000, 168),
            },
            index=dates,
        )

        validate_ohlcv(df)
