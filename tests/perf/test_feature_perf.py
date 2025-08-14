"""
Performance tests for feature pipeline components.
Validates that feature computation, validation, and alignment meet performance requirements.
"""

import asyncio
import time

import numpy as np
import pandas as pd
import pytest

from backend.features.alignment import align_features_target, align_multitimeframe
from backend.features.feature_engineering import (
    build_feature_frame,
    compute_all_features,
)
from backend.features.types import FeatureFrame
from backend.features.validators import (
    guard_no_lookahead,
    guard_no_lookahead_synthetic,
    validate_ohlcv,
)


@pytest.mark.perf
class TestFeatureComputePerformance:
    """Performance tests for feature computation."""

    @pytest.fixture(params=[1000, 5000, 10000])
    def performance_ohlcv_data(self, request):
        """Generate OHLCV data of varying sizes for performance testing."""
        n_periods = request.param
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        # Generate realistic OHLCV data
        np.random.seed(42)
        returns = np.random.normal(0, 0.02, n_periods)
        prices = 100 * np.exp(np.cumsum(returns))

        ohlcv = pd.DataFrame(
            {
                "open": prices * (1 + np.random.normal(0, 0.001, n_periods)),
                "high": prices * (1 + np.abs(np.random.normal(0, 0.005, n_periods))),
                "low": prices * (1 - np.abs(np.random.normal(0, 0.005, n_periods))),
                "close": prices,
                "volume": np.random.exponential(1000, n_periods),
            },
            index=dates,
        )

        return ohlcv, n_periods

    @pytest.mark.asyncio
    async def test_feature_computation_performance(self, performance_ohlcv_data):
        """Test feature computation performance across different data sizes."""
        ohlcv_data, n_periods = performance_ohlcv_data

        # Measure feature computation time
        start_time = time.perf_counter()
        features_df = await compute_all_features(ohlcv_data)
        compute_time = time.perf_counter() - start_time

        # Performance assertions
        assert not features_df.empty
        assert len(features_df) == n_periods

        # Performance benchmarks (adjust based on requirements)
        if n_periods <= 1000:
            assert (
                compute_time < 2.0
            ), f"Feature computation took {compute_time:.3f}s for {n_periods} periods"
        elif n_periods <= 5000:
            assert (
                compute_time < 8.0
            ), f"Feature computation took {compute_time:.3f}s for {n_periods} periods"
        else:  # 10000 periods
            assert (
                compute_time < 20.0
            ), f"Feature computation took {compute_time:.3f}s for {n_periods} periods"

        # Throughput metrics
        throughput = n_periods / compute_time
        print(
            f"Feature computation throughput: {throughput:.0f} periods/second for {n_periods} periods"
        )

        # Memory usage validation (features shouldn't be excessively large)
        memory_mb = features_df.memory_usage(deep=True).sum() / 1024 / 1024
        assert (
            memory_mb < n_periods * 0.01
        ), f"Feature memory usage {memory_mb:.2f}MB too high for {n_periods} periods"

    @pytest.mark.asyncio
    async def test_feature_frame_build_performance(self, performance_ohlcv_data):
        """Test FeatureFrame construction performance."""
        ohlcv_data, n_periods = performance_ohlcv_data

        # First compute features
        features_df = await compute_all_features(ohlcv_data)

        # Measure FeatureFrame build time
        start_time = time.perf_counter()
        feature_frame = build_feature_frame(features_df, expected_columns=None)
        build_time = time.perf_counter() - start_time

        # Performance assertions
        assert isinstance(feature_frame, FeatureFrame)
        assert len(feature_frame.data) == len(features_df)

        # Build time should be very fast (mostly schema validation)
        assert (
            build_time < 1.0
        ), f"FeatureFrame build took {build_time:.3f}s for {n_periods} periods"

        print(f"FeatureFrame build time: {build_time:.3f}s for {n_periods} periods")


@pytest.mark.perf
class TestValidationPerformance:
    """Performance tests for feature validation components."""

    @pytest.fixture
    def large_feature_dataset(self):
        """Create large feature dataset for validation performance testing."""
        n_periods = 5000
        n_features = 50

        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        # Generate diverse feature types
        features_data = {}
        np.random.seed(123)

        for i in range(n_features):
            if i % 4 == 0:  # Price-based features
                base_price = 100 + np.cumsum(np.random.normal(0, 1, n_periods))
                features_data[f"price_feature_{i}"] = base_price * (
                    1 + np.random.normal(0, 0.01, n_periods)
                )
            elif i % 4 == 1:  # Oscillator features
                features_data[f"oscillator_{i}"] = np.sin(
                    np.arange(n_periods) / 50
                ) + np.random.normal(0, 0.1, n_periods)
            elif i % 4 == 2:  # Volume features
                features_data[f"volume_{i}"] = np.random.exponential(1000, n_periods)
            else:  # Regime features
                features_data[f"regime_{i}"] = np.random.choice([0, 1, 2], n_periods)

        features_df = pd.DataFrame(features_data, index=dates)

        # Create target variable
        target = pd.Series(
            np.random.normal(0, 0.01, n_periods), index=dates, name="target"
        )

        return features_df, target

    def test_ohlcv_validation_performance(self):
        """Test OHLCV validation performance."""
        n_periods = 10000
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        # Generate large OHLCV dataset
        ohlcv = pd.DataFrame(
            {
                "open": np.random.uniform(99, 101, n_periods),
                "high": np.random.uniform(101, 103, n_periods),
                "low": np.random.uniform(97, 99, n_periods),
                "close": np.random.uniform(99, 101, n_periods),
                "volume": np.random.exponential(1000, n_periods),
            },
            index=dates,
        )

        # Measure validation time
        start_time = time.perf_counter()
        validate_ohlcv(ohlcv)  # Should pass without exception
        validation_time = time.perf_counter() - start_time

        # Performance assertion
        assert (
            validation_time < 1.0
        ), f"OHLCV validation took {validation_time:.3f}s for {n_periods} periods"

        print(f"OHLCV validation time: {validation_time:.3f}s for {n_periods} periods")

    def test_lookahead_detection_performance(self, large_feature_dataset):
        """Test lookahead detection performance."""
        features_df, target = large_feature_dataset

        # Measure correlation-based lookahead detection
        start_time = time.perf_counter()
        guard_no_lookahead(features_df, target, threshold=0.7)
        correlation_time = time.perf_counter() - start_time

        # Measure synthetic lookahead detection
        start_time = time.perf_counter()
        guard_no_lookahead_synthetic(features_df, accuracy_threshold=0.8)
        synthetic_time = time.perf_counter() - start_time

        # Performance assertions
        n_features = len(features_df.columns)
        n_periods = len(features_df)

        assert (
            correlation_time < 5.0
        ), f"Correlation lookahead detection took {correlation_time:.3f}s"
        assert (
            synthetic_time < 10.0
        ), f"Synthetic lookahead detection took {synthetic_time:.3f}s"

        print(
            f"Lookahead detection performance for {n_features} features, {n_periods} periods:"
        )
        print(f"  Correlation method: {correlation_time:.3f}s")
        print(f"  Synthetic method: {synthetic_time:.3f}s")


@pytest.mark.perf
class TestAlignmentPerformance:
    """Performance tests for feature alignment components."""

    @pytest.fixture
    def alignment_test_data(self):
        """Create test data for alignment performance testing."""
        n_periods = 8000
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        # Features with various lag structures
        np.random.seed(456)
        features = pd.DataFrame(
            {
                "feature_1": np.random.randn(n_periods),
                "feature_2": np.random.randn(n_periods),
                "lagged_feature_1": np.random.randn(n_periods),
                "lagged_feature_2": np.random.randn(n_periods),
                "volume_feature": np.random.exponential(1000, n_periods),
            },
            index=dates,
        )

        # Add some NaN values to simulate realistic data
        features.iloc[::100, 0] = np.nan  # Sparse NaNs in first feature
        features.iloc[:50, 1] = np.nan  # Initial NaNs in second feature

        # Target variable
        target = pd.Series(
            np.random.normal(0, 0.01, n_periods), index=dates, name="target"
        )

        return features, target

    def test_single_timeframe_alignment_performance(self, alignment_test_data):
        """Test single timeframe alignment performance."""
        features, target = alignment_test_data

        # Measure alignment time
        start_time = time.perf_counter()
        aligned_features, aligned_target = align_features_target(features, target)
        alignment_time = time.perf_counter() - start_time

        # Performance assertions
        n_periods = len(features)
        assert (
            alignment_time < 2.0
        ), f"Single TF alignment took {alignment_time:.3f}s for {n_periods} periods"

        # Verify alignment worked
        assert len(aligned_features) > 0
        assert len(aligned_features) == len(aligned_target)
        assert aligned_features.index.equals(aligned_target.index)

        print(
            f"Single timeframe alignment: {alignment_time:.3f}s for {n_periods} periods"
        )

    def test_multitimeframe_alignment_performance(self):
        """Test multi-timeframe alignment performance."""
        # Create multi-timeframe data
        n_periods_1min = 5000
        dates_1min = pd.date_range(
            "2023-01-01", periods=n_periods_1min, freq="1min", tz="UTC"
        )

        # 1-minute features
        features_1min = pd.DataFrame(
            {
                "fast_ma": np.random.randn(n_periods_1min),
                "momentum_1min": np.random.randn(n_periods_1min),
            },
            index=dates_1min,
        )

        # 5-minute features (1/5 the data points)
        dates_5min = dates_1min[::5]  # Every 5th timestamp
        features_5min = pd.DataFrame(
            {
                "slow_ma": np.random.randn(len(dates_5min)),
                "trend_5min": np.random.randn(len(dates_5min)),
            },
            index=dates_5min,
        )

        # 15-minute features (1/15 the data points)
        dates_15min = dates_1min[::15]  # Every 15th timestamp
        features_15min = pd.DataFrame(
            {
                "regime_15min": np.random.choice([0, 1, 2], len(dates_15min)),
                "vol_15min": np.random.exponential(1, len(dates_15min)),
            },
            index=dates_15min,
        )

        feature_sets = [
            ("1min", features_1min),
            ("5min", features_5min),
            ("15min", features_15min),
        ]

        # Measure multi-timeframe alignment
        start_time = time.perf_counter()
        aligned_features = align_multitimeframe(
            feature_sets, target_timeframe="1min", max_ffill_periods=10
        )
        alignment_time = time.perf_counter() - start_time

        # Performance assertions
        assert alignment_time < 3.0, f"Multi-TF alignment took {alignment_time:.3f}s"

        # Verify alignment results
        assert not aligned_features.empty
        assert len(aligned_features.columns) == 6  # 2+2+2 features
        assert aligned_features.index.freq is not None  # Should maintain frequency

        print(f"Multi-timeframe alignment: {alignment_time:.3f}s for 3 timeframes")


@pytest.mark.perf
class TestMemoryUsageValidation:
    """Test memory usage characteristics of feature pipeline."""

    def test_feature_pipeline_memory_usage(self):
        """Test that feature pipeline doesn't consume excessive memory."""
        import os

        import psutil

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create large dataset
        n_periods = 10000
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        ohlcv = pd.DataFrame(
            {
                "open": np.random.uniform(99, 101, n_periods),
                "high": np.random.uniform(101, 103, n_periods),
                "low": np.random.uniform(97, 99, n_periods),
                "close": np.random.uniform(99, 101, n_periods),
                "volume": np.random.exponential(1000, n_periods),
            },
            index=dates,
        )

        # Run complete feature pipeline
        async def run_pipeline():
            features = await compute_all_features(ohlcv)
            feature_frame = build_feature_frame(features, expected_columns=None)

            # Create target and align
            target = ohlcv["close"].pct_change().shift(-1).dropna()
            target.name = "target"

            aligned_features, aligned_target = align_features_target(
                feature_frame.data, target
            )

            return aligned_features, aligned_target

        # Run pipeline and measure memory
        aligned_features, aligned_target = asyncio.run(run_pipeline())

        # Get peak memory usage
        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = peak_memory - initial_memory

        # Memory usage assertions
        expected_data_size = ohlcv.memory_usage(deep=True).sum() / 1024 / 1024  # MB

        # Memory increase should be reasonable (< 5x input data size)
        assert (
            memory_increase < expected_data_size * 5
        ), f"Memory usage increased by {memory_increase:.2f}MB, expected < {expected_data_size * 5:.2f}MB"

        print(f"Memory usage for {n_periods} periods:")
        print(f"  Input OHLCV: {expected_data_size:.2f}MB")
        print(f"  Memory increase: {memory_increase:.2f}MB")
        print(f"  Peak memory: {peak_memory:.2f}MB")

    def test_feature_frame_memory_efficiency(self):
        """Test that FeatureFrame doesn't duplicate data unnecessarily."""
        # Create features
        n_periods = 5000
        dates = pd.date_range("2023-01-01", periods=n_periods, freq="1min", tz="UTC")

        features_df = pd.DataFrame(
            {
                f"feature_{i}": np.random.randn(n_periods)
                for i in range(20)  # 20 features
            },
            index=dates,
        )

        # Measure original DataFrame memory usage
        original_memory = features_df.memory_usage(deep=True).sum() / 1024 / 1024  # MB

        # Build FeatureFrame
        feature_frame = build_feature_frame(features_df, expected_columns=None)

        # Measure FeatureFrame memory usage
        frame_memory = (
            feature_frame.data.memory_usage(deep=True).sum() / 1024 / 1024
        )  # MB

        # FeatureFrame should not significantly increase memory usage
        memory_ratio = frame_memory / original_memory
        assert (
            memory_ratio < 1.2
        ), f"FeatureFrame uses {memory_ratio:.2f}x original memory"

        print("Memory efficiency test:")
        print(f"  Original DataFrame: {original_memory:.2f}MB")
        print(f"  FeatureFrame: {frame_memory:.2f}MB")
        print(f"  Ratio: {memory_ratio:.2f}x")


@pytest.mark.perf
class TestConcurrencyPerformance:
    """Test performance under concurrent operations."""

    @pytest.mark.asyncio
    async def test_concurrent_feature_computation(self):
        """Test feature computation performance with concurrent requests."""
        # Create multiple OHLCV datasets
        n_concurrent = 5
        n_periods = 2000

        datasets = []
        for i in range(n_concurrent):
            dates = pd.date_range(
                f"2023-0{i + 1}-01", periods=n_periods, freq="1min", tz="UTC"
            )
            np.random.seed(42 + i)

            ohlcv = pd.DataFrame(
                {
                    "open": np.random.uniform(99, 101, n_periods),
                    "high": np.random.uniform(101, 103, n_periods),
                    "low": np.random.uniform(97, 99, n_periods),
                    "close": np.random.uniform(99, 101, n_periods),
                    "volume": np.random.exponential(1000, n_periods),
                },
                index=dates,
            )

            datasets.append(ohlcv)

        # Measure concurrent computation time
        start_time = time.perf_counter()

        # Run feature computation concurrently
        tasks = [compute_all_features(ohlcv) for ohlcv in datasets]
        results = await asyncio.gather(*tasks)

        concurrent_time = time.perf_counter() - start_time

        # Verify all computations succeeded
        assert len(results) == n_concurrent
        for features_df in results:
            assert not features_df.empty
            assert len(features_df) == n_periods

        # Performance assertion (concurrent should be faster than sequential)
        expected_sequential_time = n_concurrent * 2.0  # Rough estimate
        assert (
            concurrent_time < expected_sequential_time
        ), f"Concurrent computation took {concurrent_time:.3f}s, expected < {expected_sequential_time:.3f}s"

        print("Concurrent feature computation:")
        print(f"  {n_concurrent} datasets of {n_periods} periods each")
        print(f"  Total time: {concurrent_time:.3f}s")
        print(f"  Time per dataset: {concurrent_time / n_concurrent:.3f}s")
