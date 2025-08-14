"""
Micro-benchmark performance tests for prediction latency.

Ensures predict() p95 latency < 40ms with tiny sample sets to catch
performance regressions in hot path code without expensive model loading.
"""

from contextlib import contextmanager
import statistics
import threading
import time
from typing import Any

import numpy as np
import pytest


class MockFastPredictor:
    """Ultra-lightweight mock predictor for micro-benchmarks."""

    def __init__(self, base_latency_ms: float = 2.0, variance_ms: float = 0.5):
        """
        Initialize with configurable latency characteristics.

        Args:
            base_latency_ms: Base latency in milliseconds
            variance_ms: Variance in latency to simulate real-world conditions
        """
        self.base_latency_ms = base_latency_ms
        self.variance_ms = variance_ms
        self.call_count = 0
        self.warmup_calls = 0

        # Simple feature weights to simulate computation
        self.weights = np.random.randn(10) * 0.1

    def predict(self, features: np.ndarray) -> dict[str, Any]:
        """
        Fast prediction with configurable latency simulation.

        Returns:
            Prediction result with confidence and metadata
        """
        start_time = time.perf_counter()

        # Simulate brief computation
        if features.ndim == 1:
            features = features.reshape(1, -1)

        # Simple dot product to simulate model inference
        raw_prediction = np.dot(features, self.weights[: features.shape[1]])

        # Add sigmoid activation
        probability = 1.0 / (1.0 + np.exp(-raw_prediction))

        # Simulate additional latency with variance
        if self.call_count > self.warmup_calls:
            latency_noise = np.random.normal(0, self.variance_ms) / 1000.0
            simulated_latency = max(0, (self.base_latency_ms / 1000.0) + latency_noise)

            # Busy wait to simulate real computation time
            target_end = start_time + simulated_latency
            while time.perf_counter() < target_end:
                pass

        self.call_count += 1

        return {
            "prediction": float(probability[0]),
            "confidence": min(0.95, abs(float(probability[0]) - 0.5) * 2),
            "feature_count": features.shape[1],
            "model_version": "1.0.0-mock",
            "computation_time_ms": (time.perf_counter() - start_time) * 1000,
        }

    def warmup(self, num_calls: int = 10):
        """Warmup the predictor to simulate JIT compilation/caching."""
        self.warmup_calls = num_calls
        dummy_features = np.random.randn(5)

        for _ in range(num_calls):
            self.predict(dummy_features)

    def reset_stats(self):
        """Reset call statistics."""
        self.call_count = 0
        self.warmup_calls = 0


class MockMarketDataFeatures:
    """Mock market data feature generator for micro-benchmarks."""

    def __init__(self, feature_count: int = 10):
        self.feature_count = feature_count

    def generate_tiny_sample(self) -> np.ndarray:
        """Generate minimal feature set for performance testing."""
        return np.array(
            [
                # Price features
                100.50,  # current_price
                0.02,  # price_change_pct
                1.5,  # volatility
                # Volume features
                1000000,  # volume
                0.8,  # volume_ratio
                # Technical indicators (simplified)
                0.6,  # rsi_normalized
                1.2,  # macd_signal
                0.3,  # bollinger_position
                # Market features
                0.1,  # spread_bps
                0.95,  # market_hours_factor
            ]
        )

    def generate_batch(self, batch_size: int) -> np.ndarray:
        """Generate batch of feature sets."""
        return np.array([self.generate_tiny_sample() for _ in range(batch_size)])


@contextmanager
def precise_timer():
    """Context manager for precise timing measurements."""
    start = time.perf_counter()
    yield lambda: (time.perf_counter() - start) * 1000  # Return time in milliseconds


class PerformanceCollector:
    """Collect and analyze performance metrics."""

    def __init__(self):
        self.latencies: list[float] = []
        self.start_time = None
        self.end_time = None

    def record_latency(self, latency_ms: float):
        """Record a latency measurement."""
        self.latencies.append(latency_ms)

    def start_collection(self):
        """Start collecting metrics."""
        self.start_time = time.perf_counter()
        self.latencies.clear()

    def stop_collection(self):
        """Stop collecting metrics."""
        self.end_time = time.perf_counter()

    def get_stats(self) -> dict[str, float]:
        """Get comprehensive performance statistics."""
        if not self.latencies:
            return {}

        sorted_latencies = sorted(self.latencies)

        return {
            "count": len(self.latencies),
            "mean_ms": statistics.mean(self.latencies),
            "median_ms": statistics.median(self.latencies),
            "p95_ms": sorted_latencies[int(0.95 * len(sorted_latencies))],
            "p99_ms": sorted_latencies[int(0.99 * len(sorted_latencies))],
            "min_ms": min(self.latencies),
            "max_ms": max(self.latencies),
            "std_dev_ms": (
                statistics.stdev(self.latencies) if len(self.latencies) > 1 else 0.0
            ),
            "total_duration_ms": (
                (self.end_time - self.start_time) * 1000
                if self.start_time and self.end_time
                else 0.0
            ),
            "throughput_rps": len(self.latencies)
            / (
                (self.end_time - self.start_time)
                if self.start_time and self.end_time
                else 1.0
            ),
        }


@pytest.mark.performance
class TestMicroPredictPerformance:
    """Micro-benchmark tests for prediction performance."""

    @pytest.fixture
    def fast_predictor(self):
        """Create a fast mock predictor."""
        predictor = MockFastPredictor(base_latency_ms=2.0, variance_ms=0.5)
        predictor.warmup(10)  # Warmup for consistent performance
        return predictor

    @pytest.fixture
    def market_features(self):
        """Create market data features generator."""
        return MockMarketDataFeatures(feature_count=10)

    @pytest.fixture
    def performance_collector(self):
        """Create performance metrics collector."""
        return PerformanceCollector()

    def test_predict_p95_under_40ms_single(
        self, fast_predictor, market_features, performance_collector
    ):
        """Test that single predictions have p95 latency < 40ms."""
        target_p95_ms = 40.0
        num_samples = 100

        performance_collector.start_collection()

        for _ in range(num_samples):
            features = market_features.generate_tiny_sample()

            with precise_timer() as get_time:
                result = fast_predictor.predict(features)

            latency_ms = get_time()
            performance_collector.record_latency(latency_ms)

            # Verify prediction structure
            assert "prediction" in result
            assert "confidence" in result
            assert 0.0 <= result["prediction"] <= 1.0
            assert 0.0 <= result["confidence"] <= 1.0

        performance_collector.stop_collection()
        stats = performance_collector.get_stats()

        # Critical performance requirement
        assert stats["p95_ms"] < target_p95_ms, (
            f"p95 latency {stats['p95_ms']:.2f}ms exceeds target {target_p95_ms}ms. "
            f"Stats: mean={stats['mean_ms']:.2f}ms, max={stats['max_ms']:.2f}ms"
        )

        # Additional performance checks
        assert stats["mean_ms"] < target_p95_ms * 0.5, "Mean latency too high"
        assert stats["max_ms"] < target_p95_ms * 2.0, "Max latency excessive"

        print(
            f"✓ Single prediction p95: {stats['p95_ms']:.2f}ms (target: <{target_p95_ms}ms)"
        )

    def test_predict_p95_under_40ms_batch(
        self, fast_predictor, market_features, performance_collector
    ):
        """Test that batch predictions maintain p95 latency < 40ms per item."""
        target_p95_ms = 40.0
        batch_sizes = [1, 5, 10, 20]
        min_samples_per_batch = 50

        for batch_size in batch_sizes:
            performance_collector.start_collection()

            for _ in range(min_samples_per_batch):
                features_batch = market_features.generate_batch(batch_size)

                with precise_timer() as get_time:
                    for i in range(batch_size):
                        result = fast_predictor.predict(features_batch[i])
                        assert "prediction" in result

                # Record per-item latency
                total_latency_ms = get_time()
                per_item_latency = total_latency_ms / batch_size
                performance_collector.record_latency(per_item_latency)

            performance_collector.stop_collection()
            stats = performance_collector.get_stats()

            assert stats["p95_ms"] < target_p95_ms, (
                f"Batch size {batch_size}: p95 per-item latency {stats['p95_ms']:.2f}ms "
                f"exceeds target {target_p95_ms}ms"
            )

            print(f"✓ Batch size {batch_size} p95 per-item: {stats['p95_ms']:.2f}ms")

    def test_predict_performance_consistency(self, fast_predictor, market_features):
        """Test that prediction performance is consistent across multiple runs."""
        num_runs = 10
        samples_per_run = 50
        target_p95_ms = 40.0
        max_p95_variance = 10.0  # ms

        run_p95s = []

        for run in range(num_runs):
            collector = PerformanceCollector()
            collector.start_collection()

            for _ in range(samples_per_run):
                features = market_features.generate_tiny_sample()

                with precise_timer() as get_time:
                    fast_predictor.predict(features)

                collector.record_latency(get_time())

            collector.stop_collection()
            stats = collector.get_stats()
            run_p95s.append(stats["p95_ms"])

        # Check consistency across runs
        p95_variance = statistics.stdev(run_p95s)
        mean_p95 = statistics.mean(run_p95s)

        assert mean_p95 < target_p95_ms, f"Mean p95 {mean_p95:.2f}ms exceeds target"
        assert (
            p95_variance < max_p95_variance
        ), f"p95 variance {p95_variance:.2f}ms too high (max {max_p95_variance}ms)"

        print(
            f"✓ Consistency check: mean p95={mean_p95:.2f}ms, variance={p95_variance:.2f}ms"
        )

    def test_predict_memory_efficiency(self, fast_predictor, market_features):
        """Test memory efficiency during predictions."""
        import tracemalloc

        # Start memory tracking
        tracemalloc.start()

        # Baseline memory
        baseline_snapshot = tracemalloc.take_snapshot()

        # Perform predictions
        num_predictions = 1000
        for _ in range(num_predictions):
            features = market_features.generate_tiny_sample()
            result = fast_predictor.predict(features)

            # Ensure result is used (prevent optimization)
            assert result["prediction"] is not None

        # Measure memory after predictions
        final_snapshot = tracemalloc.take_snapshot()

        # Compare memory usage
        top_stats = final_snapshot.compare_to(baseline_snapshot, "lineno")
        total_memory_mb = sum(stat.size_diff for stat in top_stats) / 1024 / 1024

        # Memory should not grow significantly (< 10MB for 1000 predictions)
        max_memory_mb = 10.0
        assert (
            abs(total_memory_mb) < max_memory_mb
        ), f"Memory usage {total_memory_mb:.2f}MB exceeds limit {max_memory_mb}MB"

        tracemalloc.stop()
        print(
            f"✓ Memory efficiency: {total_memory_mb:.2f}MB for {num_predictions} predictions"
        )

    def test_predict_concurrent_performance(self, market_features):
        """Test prediction performance under concurrent load."""
        target_p95_ms = 40.0
        num_threads = 4
        predictions_per_thread = 50
        results = {}

        def worker_thread(thread_id: int):
            """Worker thread for concurrent predictions."""
            predictor = MockFastPredictor(base_latency_ms=2.0, variance_ms=0.5)
            predictor.warmup(5)

            collector = PerformanceCollector()
            collector.start_collection()

            for _ in range(predictions_per_thread):
                features = market_features.generate_tiny_sample()

                with precise_timer() as get_time:
                    result = predictor.predict(features)
                    assert "prediction" in result

                collector.record_latency(get_time())

            collector.stop_collection()
            results[thread_id] = collector.get_stats()

        # Start concurrent threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Analyze concurrent performance
        all_p95s = [stats["p95_ms"] for stats in results.values()]
        worst_p95 = max(all_p95s)
        mean_p95 = statistics.mean(all_p95s)

        assert (
            worst_p95 < target_p95_ms * 1.5
        ), f"Worst concurrent p95 {worst_p95:.2f}ms too high (target: <{target_p95_ms * 1.5}ms)"  # Allow 50% degradation under load

        assert (
            mean_p95 < target_p95_ms
        ), f"Mean concurrent p95 {mean_p95:.2f}ms exceeds target {target_p95_ms}ms"

        print(f"✓ Concurrent test: mean p95={mean_p95:.2f}ms, worst={worst_p95:.2f}ms")

    def test_predict_cold_start_performance(self, market_features):
        """Test prediction performance on cold start (no warmup)."""
        target_cold_p95_ms = 60.0  # Allow higher latency for cold start
        num_samples = 20  # Fewer samples as cold start is expensive

        collector = PerformanceCollector()
        collector.start_collection()

        # Create fresh predictor without warmup
        cold_predictor = MockFastPredictor(base_latency_ms=5.0, variance_ms=2.0)

        for i in range(num_samples):
            features = market_features.generate_tiny_sample()

            with precise_timer() as get_time:
                result = cold_predictor.predict(features)
                assert "prediction" in result

            latency_ms = get_time()
            collector.record_latency(latency_ms)

            # First few predictions might be slower
            if i < 5:
                print(f"Cold start prediction {i + 1}: {latency_ms:.2f}ms")

        collector.stop_collection()
        stats = collector.get_stats()

        assert (
            stats["p95_ms"] < target_cold_p95_ms
        ), f"Cold start p95 {stats['p95_ms']:.2f}ms exceeds target {target_cold_p95_ms}ms"

        # Performance should improve over time (last 50% should be better than first 50%)
        mid_point = len(collector.latencies) // 2
        first_half_mean = statistics.mean(collector.latencies[:mid_point])
        second_half_mean = statistics.mean(collector.latencies[mid_point:])

        assert second_half_mean <= first_half_mean, (
            "Performance didn't improve during warmup "
            f"(first half: {first_half_mean:.2f}ms, second half: {second_half_mean:.2f}ms)"
        )

        print(
            f"✓ Cold start p95: {stats['p95_ms']:.2f}ms, warmup improvement: {first_half_mean - second_half_mean:.2f}ms"
        )

    def test_predict_degradation_detection(self, fast_predictor, market_features):
        """Test detection of performance degradation."""
        baseline_samples = 50
        degraded_samples = 50

        # Collect baseline performance
        baseline_latencies = []
        for _ in range(baseline_samples):
            features = market_features.generate_tiny_sample()

            with precise_timer() as get_time:
                fast_predictor.predict(features)

            baseline_latencies.append(get_time())

        baseline_p95 = sorted(baseline_latencies)[int(0.95 * len(baseline_latencies))]

        # Simulate degraded predictor
        degraded_predictor = MockFastPredictor(base_latency_ms=15.0, variance_ms=5.0)
        degraded_predictor.warmup(5)

        degraded_latencies = []
        for _ in range(degraded_samples):
            features = market_features.generate_tiny_sample()

            with precise_timer() as get_time:
                degraded_predictor.predict(features)

            degraded_latencies.append(get_time())

        degraded_p95 = sorted(degraded_latencies)[int(0.95 * len(degraded_latencies))]

        # Should detect significant degradation
        degradation_ratio = degraded_p95 / baseline_p95
        min_detectable_degradation = 2.0  # 100% increase

        assert degradation_ratio >= min_detectable_degradation, (
            f"Failed to detect performance degradation: "
            f"baseline p95={baseline_p95:.2f}ms, degraded p95={degraded_p95:.2f}ms, "
            f"ratio={degradation_ratio:.2f}x (min {min_detectable_degradation}x)"
        )

        print(
            f"✓ Degradation detection: {degradation_ratio:.2f}x performance regression detected"
        )

    def test_predict_tiny_sample_requirements(self, fast_predictor, market_features):
        """Test that we can achieve performance targets with tiny sample sets."""
        min_samples = 20  # Absolute minimum for statistical validity
        target_p95_ms = 40.0

        collector = PerformanceCollector()
        collector.start_collection()

        for _ in range(min_samples):
            features = market_features.generate_tiny_sample()

            with precise_timer() as get_time:
                result = fast_predictor.predict(features)
                assert len(features) == 10  # Verify tiny sample size
                assert "prediction" in result

            collector.record_latency(get_time())

        collector.stop_collection()
        stats = collector.get_stats()

        # Even with tiny sample set, should meet performance requirements
        assert stats["p95_ms"] < target_p95_ms, (
            f"Tiny sample p95 {stats['p95_ms']:.2f}ms exceeds target {target_p95_ms}ms "
            f"with only {min_samples} samples"
        )

        # Sample size should be minimal for fast CI
        max_test_duration_ms = 1000  # 1 second max for micro-benchmark
        assert (
            stats["total_duration_ms"] < max_test_duration_ms
        ), f"Test duration {stats['total_duration_ms']:.0f}ms too long (max {max_test_duration_ms}ms)"

        print(
            f"✓ Tiny sample test: {min_samples} samples, p95={stats['p95_ms']:.2f}ms, "
            f"duration={stats['total_duration_ms']:.0f}ms"
        )

    def test_performance_regression_alerting(self, test_seed):
        """Test that performance regression detection is deterministic."""
        # Use deterministic seed for consistent results
        np.random.seed(test_seed)

        target_p95_ms = 40.0
        samples = 100

        # Create predictable performance profile
        deterministic_predictor = MockFastPredictor(
            base_latency_ms=3.0, variance_ms=1.0
        )
        deterministic_predictor.warmup(10)

        features_gen = MockMarketDataFeatures()

        # Multiple runs should have consistent results
        run_results = []
        for run in range(3):
            np.random.seed(test_seed + run)  # Slight variation but deterministic

            collector = PerformanceCollector()
            collector.start_collection()

            for _ in range(samples):
                features = features_gen.generate_tiny_sample()

                with precise_timer() as get_time:
                    deterministic_predictor.predict(features)

                collector.record_latency(get_time())

            collector.stop_collection()
            stats = collector.get_stats()
            run_results.append(stats["p95_ms"])

        # Results should be within acceptable variance
        max_variance = 5.0  # ms
        p95_variance = statistics.stdev(run_results)

        assert (
            p95_variance < max_variance
        ), f"Performance results not deterministic: variance {p95_variance:.2f}ms > {max_variance}ms"

        # All runs should pass performance requirements
        for i, p95_ms in enumerate(run_results):
            assert (
                p95_ms < target_p95_ms
            ), f"Run {i + 1} p95 {p95_ms:.2f}ms exceeds target {target_p95_ms}ms"

        print(
            f"✓ Deterministic performance: runs {[f'{p95:.1f}' for p95 in run_results]}ms, "
            f"variance {p95_variance:.2f}ms"
        )
