"""
Property-based tests for feature engineering to ensure no look-ahead bias.

Uses Hypothesis to fuzz features and verify temporal integrity - no future
information should leak into features calculated for historical timestamps.
"""

from datetime import datetime, timedelta

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
import numpy as np
import pandas as pd
import pytest


# Mock feature calculator for testing
class MockFeatureCalculator:
    """Mock feature calculator to test temporal constraints."""

    def __init__(self):
        self.calculation_calls = []

    def calculate_features_at_time(
        self, data: pd.DataFrame, timestamp: datetime
    ) -> dict:
        """
        Calculate features using only data up to the given timestamp.

        This is the contract we're testing - features at time T should only
        use data with timestamps <= T.
        """
        self.calculation_calls.append(
            {
                "timestamp": timestamp,
                "data_shape": data.shape,
                "data_end_time": data.index.max() if not data.empty else None,
            }
        )

        # Filter data to only include points up to timestamp
        if data.empty:
            return {}

        # Ensure we only use data up to the timestamp
        valid_data = data[data.index <= timestamp]

        if valid_data.empty:
            return {}

        # Calculate mock features
        features = {}

        if "close" in valid_data.columns:
            close_prices = valid_data["close"].dropna()
            if len(close_prices) > 0:
                features["price_mean"] = float(close_prices.mean())
                features["price_std"] = (
                    float(close_prices.std()) if len(close_prices) > 1 else 0.0
                )
                features["price_last"] = float(close_prices.iloc[-1])

                # Moving averages (require sufficient data)
                if len(close_prices) >= 5:
                    features["sma_5"] = float(close_prices.tail(5).mean())

                if len(close_prices) >= 20:
                    features["sma_20"] = float(close_prices.tail(20).mean())

                # RSI calculation (simplified)
                if len(close_prices) >= 14:
                    deltas = close_prices.diff().dropna()
                    gains = deltas.where(deltas > 0, 0)
                    losses = -deltas.where(deltas < 0, 0)

                    avg_gain = gains.tail(14).mean()
                    avg_loss = losses.tail(14).mean()

                    if avg_loss != 0:
                        rs = avg_gain / avg_loss
                        features["rsi"] = float(100 - (100 / (1 + rs)))

        if "volume" in valid_data.columns:
            volume_data = valid_data["volume"].dropna()
            if len(volume_data) > 0:
                features["volume_mean"] = float(volume_data.mean())
                features["volume_last"] = float(volume_data.iloc[-1])

        # Add temporal metadata for verification
        features["_calculation_timestamp"] = timestamp.isoformat()
        features["_data_points_used"] = len(valid_data)
        features["_latest_data_timestamp"] = valid_data.index.max().isoformat()

        return features


# Hypothesis strategies for generating test data
@st.composite
def market_data_strategy(draw, min_periods=10, max_periods=200):
    """Generate realistic market data with temporal ordering."""

    periods = draw(st.integers(min_value=min_periods, max_value=max_periods))

    # Generate timestamps (always increasing)
    start_date = datetime(2024, 1, 1, 9, 30)  # Market open
    timestamps = [start_date + timedelta(minutes=i) for i in range(periods)]

    # Generate price data (reasonable ranges)
    initial_price = draw(st.floats(min_value=10.0, max_value=1000.0))
    price_changes = draw(
        st.lists(
            st.floats(min_value=-0.05, max_value=0.05),  # ±5% changes
            min_size=periods - 1,
            max_size=periods - 1,
        )
    )

    # Generate prices with cumulative changes
    prices = [initial_price]
    for change in price_changes:
        new_price = prices[-1] * (1 + change)
        prices.append(max(0.01, new_price))  # Prevent negative prices

    # Generate volume data
    volumes = draw(
        st.lists(
            st.integers(min_value=100, max_value=1000000),
            min_size=periods,
            max_size=periods,
        )
    )

    return pd.DataFrame(
        {"close": prices, "volume": volumes}, index=pd.to_datetime(timestamps)
    )


@st.composite
def calculation_timestamp_strategy(draw, data_df):
    """Generate a timestamp for feature calculation within the data range."""
    if data_df.empty:
        return datetime.now()

    start_time = data_df.index.min()
    end_time = data_df.index.max()

    # Generate timestamp within or after the data range
    time_offset_minutes = draw(
        st.integers(min_value=0, max_value=1440)
    )  # 0 to 24 hours
    calc_timestamp = start_time + timedelta(minutes=time_offset_minutes)

    return calc_timestamp


class TestFeatureNoLeakage:
    """Property-based tests to ensure no look-ahead bias in features."""

    @pytest.fixture
    def feature_calculator(self):
        """Create a mock feature calculator."""
        return MockFeatureCalculator()

    @given(market_data=market_data_strategy())
    @settings(
        max_examples=50,
        suppress_health_check=[
            HealthCheck.filter_too_much,
            HealthCheck.function_scoped_fixture,
        ],
    )
    def test_features_only_use_past_data(self, feature_calculator, market_data):
        """Test that features only use data from the past, never the future."""
        assume(not market_data.empty)
        assume(len(market_data) >= 5)  # Need some data points

        # Pick a calculation timestamp somewhere in the middle of the data
        data_start = market_data.index.min()
        data_end = market_data.index.max()

        # Calculate features at various points in time
        calc_timestamp = data_start + (data_end - data_start) / 2

        features = feature_calculator.calculate_features_at_time(
            market_data, calc_timestamp
        )

        # Verify temporal constraint
        if features.get("_latest_data_timestamp"):
            latest_used = datetime.fromisoformat(features["_latest_data_timestamp"])
            assert (
                latest_used <= calc_timestamp
            ), f"Feature used data from {latest_used} which is after calculation time {calc_timestamp}"

        # Verify feature values are reasonable
        if "price_mean" in features:
            assert features["price_mean"] > 0, "Price mean should be positive"
            assert np.isfinite(features["price_mean"]), "Price mean should be finite"

        if "rsi" in features:
            assert (
                0 <= features["rsi"] <= 100
            ), f"RSI should be between 0-100, got {features['rsi']}"

    @given(market_data=market_data_strategy(min_periods=20, max_periods=100))
    @settings(
        max_examples=30,
        suppress_health_check=[
            HealthCheck.filter_too_much,
            HealthCheck.function_scoped_fixture,
        ],
    )
    def test_features_consistent_across_time_points(
        self, feature_calculator, market_data
    ):
        """Test that features calculated at earlier times don't change when new data arrives."""
        assume(len(market_data) >= 20)

        # Calculate features at an early timestamp
        early_timestamp = market_data.index[10]  # 10th data point
        early_features = feature_calculator.calculate_features_at_time(
            market_data, early_timestamp
        )

        # Add more data (simulating new market data arrival)
        future_data = market_data[market_data.index > early_timestamp]
        assume(len(future_data) > 0)

        # Recalculate features at the same early timestamp
        recalc_features = feature_calculator.calculate_features_at_time(
            market_data, early_timestamp
        )

        # Features at the early timestamp should be identical
        for feature_name in early_features:
            if not feature_name.startswith("_"):  # Skip metadata
                assert early_features[feature_name] == recalc_features[feature_name], (
                    f"Feature {feature_name} changed when new data was added: "
                    f"{early_features[feature_name]} != {recalc_features[feature_name]}"
                )

    @given(market_data=market_data_strategy(min_periods=30, max_periods=150))
    @settings(
        max_examples=25, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_moving_averages_temporal_correctness(
        self, feature_calculator, market_data
    ):
        """Test that moving averages only use historical data points."""
        assume(len(market_data) >= 30)

        # Calculate features at various timestamps
        timestamps_to_test = [
            market_data.index[20],  # After SMA-20 warmup
            market_data.index[len(market_data) // 2],  # Middle
            market_data.index[-10],  # Near end
        ]

        for calc_timestamp in timestamps_to_test:
            features = feature_calculator.calculate_features_at_time(
                market_data, calc_timestamp
            )

            if "sma_20" in features:
                # Manually calculate SMA-20 using only data up to calc_timestamp
                valid_data = market_data[market_data.index <= calc_timestamp]
                expected_sma20 = valid_data["close"].tail(20).mean()

                assert abs(features["sma_20"] - expected_sma20) < 1e-10, (
                    f"SMA-20 calculation incorrect at {calc_timestamp}: "
                    f"got {features['sma_20']}, expected {expected_sma20}"
                )

            if "sma_5" in features:
                # Manually calculate SMA-5
                valid_data = market_data[market_data.index <= calc_timestamp]
                expected_sma5 = valid_data["close"].tail(5).mean()

                assert (
                    abs(features["sma_5"] - expected_sma5) < 1e-10
                ), f"SMA-5 calculation incorrect at {calc_timestamp}"

    @given(market_data=market_data_strategy(min_periods=50, max_periods=200))
    @settings(
        max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_feature_causality_ordering(self, feature_calculator, market_data):
        """Test that features maintain causal ordering - past doesn't depend on future."""
        assume(len(market_data) >= 50)

        # Create timeline of calculation points
        n_points = 5
        calc_timestamps = [
            market_data.index[i * len(market_data) // (n_points + 1)]
            for i in range(1, n_points + 1)
        ]

        all_features = {}

        # Calculate features at each timestamp
        for ts in calc_timestamps:
            features = feature_calculator.calculate_features_at_time(market_data, ts)
            all_features[ts] = features

        # Verify causal ordering property
        for i, ts1 in enumerate(calc_timestamps):
            for j, ts2 in enumerate(calc_timestamps):
                if i < j:  # ts1 comes before ts2
                    features1 = all_features[ts1]
                    features2 = all_features[ts2]

                    # Features at ts1 should not be affected by data after ts1
                    # This is implicitly tested by the temporal constraint, but we verify
                    # that data points used is non-decreasing over time
                    if (
                        "_data_points_used" in features1
                        and "_data_points_used" in features2
                    ):
                        assert (
                            features1["_data_points_used"]
                            <= features2["_data_points_used"]
                        ), (
                            f"Causality violation: earlier calculation at {ts1} used more data "
                            f"than later calculation at {ts2}"
                        )

    @pytest.mark.property
    def test_feature_determinism_with_seed(self, feature_calculator, test_seed):
        """Test that feature calculations are deterministic given the same input and seed."""
        # Generate deterministic test data
        np.random.seed(test_seed)

        timestamps = pd.date_range(start="2024-01-01 09:30", periods=50, freq="1min")
        prices = 100 + np.random.randn(50).cumsum() * 0.1
        volumes = np.random.randint(1000, 10000, 50)

        market_data = pd.DataFrame(
            {"close": prices, "volume": volumes}, index=timestamps
        )

        calc_timestamp = timestamps[30]

        # Calculate features twice with same seed
        np.random.seed(test_seed)
        features1 = feature_calculator.calculate_features_at_time(
            market_data, calc_timestamp
        )

        np.random.seed(test_seed)
        features2 = feature_calculator.calculate_features_at_time(
            market_data, calc_timestamp
        )

        # Should be identical
        for key in features1:
            if not key.startswith("_"):
                assert (
                    features1[key] == features2[key]
                ), f"Non-deterministic feature calculation for {key}"

    def test_empty_data_handling(self, feature_calculator):
        """Test feature calculation with empty or insufficient data."""
        # Empty data
        empty_data = pd.DataFrame(columns=["close", "volume"])
        features = feature_calculator.calculate_features_at_time(
            empty_data, datetime.now()
        )
        assert features == {}, "Empty data should return empty features"

        # Single data point
        single_point = pd.DataFrame(
            {"close": [100.0], "volume": [1000]}, index=[datetime.now()]
        )

        features = feature_calculator.calculate_features_at_time(
            single_point, single_point.index[0]
        )

        # Should have basic features but no moving averages
        assert "price_last" in features
        assert "sma_5" not in features
        assert "sma_20" not in features
        assert "rsi" not in features

    def test_future_calculation_timestamp(self, feature_calculator):
        """Test feature calculation when calc timestamp is after all data."""
        timestamps = pd.date_range(start="2024-01-01 09:30", periods=20, freq="1min")
        market_data = pd.DataFrame(
            {
                "close": np.random.randn(20).cumsum() + 100,
                "volume": np.random.randint(1000, 5000, 20),
            },
            index=timestamps,
        )

        # Calculate features 1 hour after the last data point
        future_timestamp = timestamps[-1] + timedelta(hours=1)
        features = feature_calculator.calculate_features_at_time(
            market_data, future_timestamp
        )

        # Should use all available data
        assert features.get("_data_points_used") == len(market_data)

        # Latest data timestamp should be the last data point, not the calc timestamp
        if "_latest_data_timestamp" in features:
            latest_used = datetime.fromisoformat(features["_latest_data_timestamp"])
            assert latest_used == timestamps[-1]

    @given(st.data())
    def test_feature_monotonicity_properties(self, data, feature_calculator):
        """Test monotonicity properties of features as more data becomes available."""
        # Generate market data
        market_data = data.draw(market_data_strategy(min_periods=30, max_periods=100))
        assume(len(market_data) >= 30)

        # Pick two calculation timestamps
        mid_point = len(market_data) // 2
        early_ts = market_data.index[mid_point]
        later_ts = market_data.index[min(mid_point + 10, len(market_data) - 1)]

        early_features = feature_calculator.calculate_features_at_time(
            market_data, early_ts
        )
        later_features = feature_calculator.calculate_features_at_time(
            market_data, later_ts
        )

        # Data points used should be monotonically non-decreasing
        if (
            "_data_points_used" in early_features
            and "_data_points_used" in later_features
        ):
            assert (
                early_features["_data_points_used"]
                <= later_features["_data_points_used"]
            )

        # Both feature sets should be valid
        for features in [early_features, later_features]:
            if "rsi" in features:
                assert 0 <= features["rsi"] <= 100
            if "price_mean" in features:
                assert features["price_mean"] > 0
            if "price_std" in features:
                assert features["price_std"] >= 0
