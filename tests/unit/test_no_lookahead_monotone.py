"""
Test lookahead detection using monotone synthetic series.
"""

import numpy as np
import pandas as pd
import pytest

from backend.features.types import LookaheadLeakError
from backend.features.validators import guard_no_lookahead, guard_no_lookahead_synthetic


class TestMonotoneLookaheadDetection:
    """Test lookahead detection with synthetic monotone price series."""

    def test_monotone_series_clean_features(self):
        """Test that properly lagged features pass monotone test."""
        # Create strictly increasing monotone series
        np.random.seed(42)
        n_periods = 200
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        # Monotone increasing with small noise
        monotone_price = pd.Series(
            np.arange(n_periods) + np.random.normal(0, 0.01, n_periods),
            index=dates,
            name="monotone_price",
        )

        # Create properly lagged features that should NOT be able to predict monotone series
        features = pd.DataFrame(
            {
                # Lagged price-based features (should be uncorrelated with future monotone trend)
                "lagged_return": monotone_price.pct_change().shift(5),
                "lagged_sma": monotone_price.rolling(10).mean().shift(3),
                # Random oscillators (should be uncorrelated)
                "random_rsi": pd.Series(
                    np.random.uniform(20, 80, n_periods), index=dates
                ),
                "random_macd": pd.Series(
                    np.random.normal(0, 1, n_periods), index=dates
                ),
            },
            index=dates,
        )

        # Should pass without raising exception
        guard_no_lookahead_synthetic(
            features, list(features.columns), accuracy_threshold=0.8
        )

    def test_monotone_series_detects_lookahead(self):
        """Test that lookahead features are detected by monotone test."""
        n_periods = 200
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        # Create features with intentional lookahead bias
        features = pd.DataFrame(
            {
                # Good feature (random)
                "good_feature": pd.Series(
                    np.random.normal(0, 1, n_periods), index=dates
                ),
                # Bad feature - directly correlated with row index (will predict monotone trend!)
                "leaked_index": pd.Series(np.arange(n_periods), index=dates),
                # Another bad feature - future-shifted noise (less obvious but still leaky)
                "subtle_leak": pd.Series(np.random.randn(n_periods), index=dates).shift(
                    -5
                ),
            },
            index=dates,
        )

        # Should detect lookahead bias and raise exception
        with pytest.raises(
            LookaheadLeakError, match="suspicious correlation with synthetic monotone"
        ):
            guard_no_lookahead_synthetic(
                features, list(features.columns), accuracy_threshold=0.6
            )

    def test_monotone_detection_specific_columns(self):
        """Test monotone detection on specific columns only."""
        n_periods = 100
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        features = pd.DataFrame(
            {
                # Clean feature
                "clean_feature": pd.Series(
                    np.random.normal(0, 1, n_periods), index=dates
                ),
                # Leaky feature (correlated with index)
                "leaky_feature": pd.Series(np.arange(n_periods) * 0.1, index=dates),
                # Another clean feature
                "another_clean": pd.Series(
                    np.random.uniform(-1, 1, n_periods), index=dates
                ),
            },
            index=dates,
        )

        # Test only the clean feature - should pass
        guard_no_lookahead_synthetic(
            features, ["clean_feature", "another_clean"], accuracy_threshold=0.7
        )

        # Test including the leaky feature - should fail
        with pytest.raises(LookaheadLeakError):
            guard_no_lookahead_synthetic(
                features, ["clean_feature", "leaky_feature"], accuracy_threshold=0.7
            )

    def test_corrected_features_pass_test(self):
        """Test that corrected (properly shifted) features pass the test."""
        n_periods = 150
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        # Base series that could be leaky if not properly shifted
        base_monotone_like = pd.Series(
            np.arange(n_periods) + np.random.normal(0, 0.1, n_periods), index=dates
        )

        # WRONG: Direct use would be leaky
        wrong_features = pd.DataFrame(
            {
                "direct_trend": base_monotone_like,  # This would be leaky
            },
            index=dates,
        )

        # RIGHT: Properly lagged version
        corrected_features = pd.DataFrame(
            {
                "lagged_trend": base_monotone_like.shift(10),  # Properly lagged
                "differenced": base_monotone_like.diff().shift(
                    5
                ),  # Differenced and lagged
            },
            index=dates,
        )

        # Wrong approach should fail
        with pytest.raises(LookaheadLeakError):
            guard_no_lookahead_synthetic(wrong_features, accuracy_threshold=0.7)

        # Corrected approach should pass
        guard_no_lookahead_synthetic(corrected_features, accuracy_threshold=0.7)


class TestRealWorldLookaheadScenarios:
    """Test lookahead detection with realistic trading scenarios."""

    def test_technical_indicators_properly_lagged(self):
        """Test that properly constructed technical indicators pass tests."""
        np.random.seed(123)
        n_periods = 300
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        # Simulate realistic price series (random walk with drift)
        returns = np.random.normal(0.0001, 0.02, n_periods)  # Small positive drift
        price = pd.Series(100 * np.exp(np.cumsum(returns)), index=dates, name="price")

        # Properly constructed technical indicators
        features = pd.DataFrame(
            {
                # Moving averages (lagged appropriately)
                "sma_20": price.rolling(20).mean().shift(1),
                "ema_12": price.ewm(span=12).mean().shift(1),
                # Momentum indicators (lagged)
                "roc_5": (price / price.shift(5) - 1).shift(
                    1
                ),  # Rate of change, lagged
                "momentum": (price - price.shift(10)).shift(1),
                # Volatility (lagged)
                "volatility": price.pct_change().rolling(20).std().shift(1),
                # Price relative positions (lagged)
                "price_position": (
                    (price - price.rolling(50).min())
                    / (price.rolling(50).max() - price.rolling(50).min())
                ).shift(1),
            },
            index=dates,
        )

        # All these should pass both regular and synthetic monotone tests
        guard_no_lookahead(features, price, threshold=0.7)
        guard_no_lookahead_synthetic(features, accuracy_threshold=0.7)

    def test_volume_indicators_no_lookahead(self):
        """Test volume-based indicators for lookahead bias."""
        np.random.seed(456)
        n_periods = 250
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        # Simulate price and volume
        price = pd.Series(
            100 + np.cumsum(np.random.randn(n_periods) * 0.1), index=dates
        )
        volume = pd.Series(1000 + np.abs(np.random.randn(n_periods) * 200), index=dates)

        # Volume-based features (properly lagged)
        features = pd.DataFrame(
            {
                # Volume moving averages
                "vol_sma_10": volume.rolling(10).mean().shift(1),
                "vol_ratio": (volume / volume.rolling(20).mean()).shift(1),
                # Price-volume interactions
                "vwap_deviation": (
                    price
                    - (price * volume).rolling(20).sum() / volume.rolling(20).sum()
                ).shift(1),
                "volume_price_trend": ((price * volume).rolling(10).sum()).shift(1),
                # On-balance volume (properly calculated)
                "obv": (
                    (price.diff() > 0).astype(int) * volume
                    - (price.diff() < 0).astype(int) * volume
                )
                .cumsum()
                .shift(1),
            },
            index=dates,
        )

        # Should pass lookahead tests
        guard_no_lookahead(features, price, threshold=0.6)
        guard_no_lookahead_synthetic(features, accuracy_threshold=0.7)

    def test_regime_indicators_no_lookahead(self):
        """Test market regime indicators for lookahead bias."""
        np.random.seed(789)
        n_periods = 400
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        # Create price series with regime changes
        regime_changes = np.random.choice(
            [0, 1], n_periods, p=[0.95, 0.05]
        )  # 5% chance of regime change
        volatility_regime = np.cumsum(
            regime_changes * np.random.choice([-1, 1], n_periods)
        )
        volatility_regime = np.clip(
            volatility_regime, 0.5, 3.0
        )  # Keep vol between 0.5% and 3%

        price = pd.Series(
            100
            * np.exp(np.cumsum(np.random.randn(n_periods) * volatility_regime / 100)),
            index=dates,
        )

        # Regime detection features (all properly lagged)
        returns = price.pct_change()
        features = pd.DataFrame(
            {
                # Volatility regime indicators
                "rolling_vol_20": returns.rolling(20).std().shift(1),
                "vol_ratio": (
                    returns.rolling(20).std() / returns.rolling(60).std()
                ).shift(1),
                # Trend strength indicators
                "trend_strength": np.abs(
                    returns.rolling(20).mean() / returns.rolling(20).std()
                ).shift(1),
                # Regime persistence
                "vol_persistence": returns.rolling(20).std().rolling(5).std().shift(1),
                # Drawdown indicators
                "drawdown": (
                    (price - price.rolling(50).max()) / price.rolling(50).max()
                ).shift(1),
            },
            index=dates,
        )

        # Should pass both lookahead tests
        guard_no_lookahead(features, price, threshold=0.6)
        guard_no_lookahead_synthetic(features, accuracy_threshold=0.75)


class TestEdgeCases:
    """Test edge cases in lookahead detection."""

    def test_insufficient_data_handling(self):
        """Test lookahead detection with insufficient data."""
        # Very small dataset
        dates = pd.date_range("2023-01-01", periods=10, freq="1min", tz="UTC")
        features = pd.DataFrame({"feature1": np.random.randn(10)}, index=dates)
        price = pd.Series(100 + np.arange(10), index=dates)

        # Should handle gracefully (not enough data for reliable detection)
        # Regular guard should raise ValueError for insufficient data
        with pytest.raises(ValueError, match="Insufficient data"):
            guard_no_lookahead(features, price, window_size=50)  # Window too large

        # Synthetic guard should skip (not enough data)
        guard_no_lookahead_synthetic(
            features, accuracy_threshold=0.8
        )  # Should not raise

    def test_all_nan_features(self):
        """Test lookahead detection with all-NaN features."""
        dates = pd.date_range("2023-01-01", periods=100, freq="1min", tz="UTC")
        features = pd.DataFrame(
            {
                "all_nan": [np.nan] * 100,
                "mostly_nan": [1.0] + [np.nan] * 99,
            },
            index=dates,
        )
        price = pd.Series(100 + np.arange(100), index=dates)

        # Should handle NaN features gracefully
        guard_no_lookahead(features, price, threshold=0.7)
        guard_no_lookahead_synthetic(features, accuracy_threshold=0.7)

    def test_constant_features(self):
        """Test lookahead detection with constant features."""
        dates = pd.date_range("2023-01-01", periods=200, freq="1min", tz="UTC")
        features = pd.DataFrame(
            {
                "constant": [42.0] * 200,  # Constant value
                "zero": [0.0] * 200,  # Constant zero
                "normal": np.random.randn(200),  # Normal random feature
            },
            index=dates,
        )
        price = pd.Series(100 + np.arange(200), index=dates)

        # Constant features should not trigger lookahead detection
        # (they can't predict anything)
        guard_no_lookahead(features, price, threshold=0.7)
        guard_no_lookahead_synthetic(features, accuracy_threshold=0.7)
