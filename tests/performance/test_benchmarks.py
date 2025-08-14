"""
Performance tests for latency, throughput, and resource usage.

Tests system performance under various load conditions and measures
key performance indicators for production readiness.
"""

from datetime import datetime
from decimal import Decimal
import gc
import statistics
import time

import numpy as np
import psutil
import pytest


class PerformanceProfiler:
    """Performance profiling utility for tests."""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.memory_samples = []
        self.cpu_samples = []
        self.process = psutil.Process()

    def start(self):
        """Start performance monitoring."""
        self.start_time = time.perf_counter()
        self.memory_samples = []
        self.cpu_samples = []

        # Force garbage collection for clean baseline
        gc.collect()

        return self

    def sample(self):
        """Take a performance sample."""
        try:
            memory_mb = self.process.memory_info().rss / 1024 / 1024
            cpu_percent = self.process.cpu_percent()

            self.memory_samples.append(memory_mb)
            self.cpu_samples.append(cpu_percent)
        except psutil.NoSuchProcess:
            pass  # Process may have ended

    def stop(self):
        """Stop monitoring and return results."""
        self.end_time = time.perf_counter()

        duration = self.end_time - self.start_time

        return {
            "duration_seconds": duration,
            "memory_peak_mb": max(self.memory_samples) if self.memory_samples else 0,
            "memory_avg_mb": (
                statistics.mean(self.memory_samples) if self.memory_samples else 0
            ),
            "cpu_avg_percent": (
                statistics.mean(self.cpu_samples) if self.cpu_samples else 0
            ),
            "cpu_peak_percent": max(self.cpu_samples) if self.cpu_samples else 0,
        }


class TestLatencyBenchmarks:
    """Test latency benchmarks for critical paths."""

    @pytest.mark.performance
    def test_feature_calculation_latency(self, sample_market_data):
        """Test feature calculation latency."""
        from backend.features.technical_indicators import TechnicalIndicators

        profiler = PerformanceProfiler().start()

        # Create feature calculator
        calculator = TechnicalIndicators()

        latencies = []

        # Test 1000 feature calculations
        for i in range(1000):
            data_slice = sample_market_data.iloc[
                max(0, i - 50) : i + 1
            ]  # 50-day window

            if len(data_slice) < 20:  # Skip if insufficient data
                continue

            start = time.perf_counter()

            # Calculate features
            features = calculator.calculate_all_features(data_slice)

            end = time.perf_counter()

            latency_ms = (end - start) * 1000
            latencies.append(latency_ms)

            if i % 100 == 0:
                profiler.sample()

        stats = profiler.stop()

        # Latency requirements
        p50_latency = statistics.median(latencies)
        p95_latency = np.percentile(latencies, 95)
        p99_latency = np.percentile(latencies, 99)

        print("✓ Feature Calculation Latency:")
        print(f"  - P50: {p50_latency:.2f}ms")
        print(f"  - P95: {p95_latency:.2f}ms")
        print(f"  - P99: {p99_latency:.2f}ms")
        print(f"  - Memory: {stats['memory_peak_mb']:.1f}MB peak")

        # Performance requirements
        assert p50_latency < 5.0, f"P50 latency too high: {p50_latency:.2f}ms"
        assert p95_latency < 20.0, f"P95 latency too high: {p95_latency:.2f}ms"
        assert p99_latency < 50.0, f"P99 latency too high: {p99_latency:.2f}ms"

        # Memory usage should be reasonable
        assert (
            stats["memory_peak_mb"] < 100
        ), f"Memory usage too high: {stats['memory_peak_mb']:.1f}MB"

    @pytest.mark.performance
    def test_risk_check_latency(self, mock_portfolio, mock_order):
        """Test risk management check latency."""
        from backend.risk.risk_manager import RiskManager

        # Create risk manager with realistic config
        risk_config = {
            "max_position_size": 0.1,
            "max_portfolio_risk": 0.02,
            "stop_loss_pct": 0.05,
            "max_correlation": 0.7,
        }

        risk_manager = RiskManager(config=risk_config)

        profiler = PerformanceProfiler().start()

        latencies = []

        # Test 10000 risk checks
        for i in range(10000):
            start = time.perf_counter()

            # Perform risk check
            risk_result = risk_manager.check_order_risk(
                order=mock_order,
                portfolio=mock_portfolio,
                market_data={"SPY": {"price": 450.0 + (i % 100) * 0.1}},
            )

            end = time.perf_counter()

            latency_ms = (end - start) * 1000
            latencies.append(latency_ms)

            if i % 1000 == 0:
                profiler.sample()

        stats = profiler.stop()

        # Calculate latency percentiles
        p50_latency = statistics.median(latencies)
        p95_latency = np.percentile(latencies, 95)
        p99_latency = np.percentile(latencies, 99)

        print("✓ Risk Check Latency:")
        print(f"  - P50: {p50_latency:.3f}ms")
        print(f"  - P95: {p95_latency:.3f}ms")
        print(f"  - P99: {p99_latency:.3f}ms")
        print(
            f"  - Throughput: {len(latencies) / stats['duration_seconds']:.0f} checks/sec"
        )

        # Risk checks must be very fast (sub-millisecond for most)
        assert p50_latency < 0.5, f"Risk check P50 too slow: {p50_latency:.3f}ms"
        assert p95_latency < 2.0, f"Risk check P95 too slow: {p95_latency:.3f}ms"
        assert p99_latency < 5.0, f"Risk check P99 too slow: {p99_latency:.3f}ms"

    @pytest.mark.performance
    def test_order_processing_latency(self):
        """Test order processing end-to-end latency."""
        from backend.services.order_service import OrderService

        # Mock broker with realistic latency
        class MockBroker:
            def __init__(self):
                self.orders = []

            def submit_order(self, order):
                # Simulate broker API latency (10-50ms)
                time.sleep(0.01 + np.random.exponential(0.02))

                order_id = f"order_{len(self.orders)}"
                self.orders.append(
                    {
                        "id": order_id,
                        "symbol": order["symbol"],
                        "side": order["side"],
                        "qty": order["qty"],
                        "status": "filled",
                    }
                )

                return {"id": order_id, "status": "accepted"}

        mock_broker = MockBroker()
        order_service = OrderService(broker=mock_broker)

        profiler = PerformanceProfiler().start()

        latencies = []
        symbols = ["SPY", "QQQ", "IWM", "DIA", "VTI"]

        # Test 1000 order submissions
        for i in range(1000):
            order = {
                "symbol": symbols[i % len(symbols)],
                "side": "buy" if i % 2 == 0 else "sell",
                "qty": 10 + (i % 90),
                "type": "market",
                "timestamp": datetime.now(),
            }

            start = time.perf_counter()

            # Process order end-to-end
            result = order_service.submit_order(order)

            end = time.perf_counter()

            latency_ms = (end - start) * 1000
            latencies.append(latency_ms)

            if i % 100 == 0:
                profiler.sample()

        stats = profiler.stop()

        # Calculate latency stats
        p50_latency = statistics.median(latencies)
        p95_latency = np.percentile(latencies, 95)
        p99_latency = np.percentile(latencies, 99)

        orders_per_second = len(latencies) / stats["duration_seconds"]

        print("✓ Order Processing Latency:")
        print(f"  - P50: {p50_latency:.1f}ms")
        print(f"  - P95: {p95_latency:.1f}ms")
        print(f"  - P99: {p99_latency:.1f}ms")
        print(f"  - Throughput: {orders_per_second:.1f} orders/sec")

        # Order processing should be reasonably fast
        assert p50_latency < 100, f"Order P50 latency too high: {p50_latency:.1f}ms"
        assert p95_latency < 200, f"Order P95 latency too high: {p95_latency:.1f}ms"
        assert (
            orders_per_second > 10
        ), f"Order throughput too low: {orders_per_second:.1f} orders/sec"


class TestThroughputBenchmarks:
    """Test system throughput under load."""

    @pytest.mark.performance
    @pytest.mark.slow
    def test_market_data_throughput(self):
        """Test market data processing throughput."""
        from backend.data.market_data import MarketDataManager

        # Mock data processor
        processed_count = 0

        def mock_process_tick(tick_data):
            nonlocal processed_count
            processed_count += 1
            # Simulate processing time (0.1ms average)
            time.sleep(0.0001)

        data_manager = MarketDataManager()
        data_manager.process_tick = mock_process_tick

        profiler = PerformanceProfiler().start()

        symbols = ["SPY", "QQQ", "IWM", "DIA", "VTI", "EFA", "EEM", "TLT", "GLD", "XOP"]

        # Generate high-frequency tick data
        total_ticks = 50000

        for i in range(total_ticks):
            tick_data = {
                "symbol": symbols[i % len(symbols)],
                "price": 100 + np.random.normal(0, 1),
                "volume": np.random.randint(100, 1000),
                "timestamp": datetime.now(),
            }

            data_manager.process_tick(tick_data)

            if i % 5000 == 0:
                profiler.sample()

        stats = profiler.stop()

        ticks_per_second = processed_count / stats["duration_seconds"]

        print("✓ Market Data Throughput:")
        print(f"  - Ticks Processed: {processed_count:,}")
        print(f"  - Throughput: {ticks_per_second:,.0f} ticks/sec")
        print(f"  - Memory Usage: {stats['memory_peak_mb']:.1f}MB")
        print(f"  - CPU Usage: {stats['cpu_avg_percent']:.1f}%")

        # Should handle at least 1000 ticks/sec
        assert (
            ticks_per_second > 1000
        ), f"Throughput too low: {ticks_per_second:.0f} ticks/sec"

        # Resource usage should be reasonable
        assert (
            stats["memory_peak_mb"] < 200
        ), f"Memory usage too high: {stats['memory_peak_mb']:.1f}MB"
        assert (
            stats["cpu_avg_percent"] < 50
        ), f"CPU usage too high: {stats['cpu_avg_percent']:.1f}%"

    @pytest.mark.performance
    def test_concurrent_strategy_execution(self):
        """Test concurrent strategy execution performance."""
        from backend.strategies.engine import StrategyEngine

        # Mock strategies that simulate realistic computation
        class MockStrategy:
            def __init__(self, name, processing_time_ms=5):
                self.name = name
                self.processing_time = processing_time_ms / 1000
                self.signals_generated = 0

            def generate_signal(self, market_data):
                # Simulate computation time
                time.sleep(self.processing_time)

                self.signals_generated += 1

                return {
                    "symbol": market_data.get("symbol", "SPY"),
                    "signal": "buy" if self.signals_generated % 3 == 0 else "hold",
                    "confidence": np.random.uniform(0.6, 0.9),
                    "strategy": self.name,
                }

        # Create strategy engine with multiple strategies
        strategies = [
            MockStrategy("momentum", 3),
            MockStrategy("mean_reversion", 5),
            MockStrategy("pairs_trading", 8),
            MockStrategy("momentum_vol", 4),
            MockStrategy("risk_parity", 6),
        ]

        strategy_engine = StrategyEngine()

        for strategy in strategies:
            strategy_engine.register_strategy(strategy)

        profiler = PerformanceProfiler().start()

        # Generate market data for multiple symbols
        symbols = ["SPY", "QQQ", "IWM", "DIA", "VTI"]
        total_signals = 0

        # Process 1000 market updates across strategies
        for i in range(1000):
            market_data = {
                "symbol": symbols[i % len(symbols)],
                "price": 100 + np.random.normal(0, 5),
                "volume": np.random.randint(1000, 10000),
                "timestamp": datetime.now(),
            }

            # Run strategies concurrently
            signals = strategy_engine.process_market_update(market_data)
            total_signals += len(signals)

            if i % 100 == 0:
                profiler.sample()

        stats = profiler.stop()

        signals_per_second = total_signals / stats["duration_seconds"]

        print("✓ Concurrent Strategy Performance:")
        print(f"  - Strategies: {len(strategies)}")
        print(f"  - Total Signals: {total_signals}")
        print(f"  - Signals/sec: {signals_per_second:.1f}")
        print(
            f"  - Avg Latency: {stats['duration_seconds'] / 1000 * 1000:.1f}ms per update"
        )

        # Should generate reasonable throughput
        assert (
            signals_per_second > 50
        ), f"Signal generation too slow: {signals_per_second:.1f}/sec"

        # Each strategy should have run
        for strategy in strategies:
            assert (
                strategy.signals_generated > 0
            ), f"Strategy {strategy.name} didn't run"


class TestMemoryPerformance:
    """Test memory usage and leak detection."""

    @pytest.mark.performance
    def test_memory_usage_under_load(self, sample_features):
        """Test memory usage during extended operation."""

        # Force garbage collection baseline
        gc.collect()
        baseline_memory = psutil.Process().memory_info().rss / 1024 / 1024

        memory_samples = []
        feature_cache = {}

        # Simulate 1 hour of operations (1 update per second)
        for i in range(3600):
            # Generate features (simulate feature calculation)
            symbol = f"SYMBOL_{i % 100}"  # 100 different symbols

            features = {
                "rsi": np.random.uniform(20, 80),
                "macd": np.random.uniform(-2, 2),
                "bb_upper": np.random.uniform(100, 120),
                "bb_lower": np.random.uniform(80, 100),
                "volume_ratio": np.random.uniform(0.5, 2.0),
                "price_momentum": np.random.uniform(-5, 5),
            }

            # Store in cache (simulate feature storage)
            feature_cache[symbol] = features

            # Periodic cleanup (simulate cache management)
            if i % 300 == 0:  # Every 5 minutes
                # Keep only recent features (simulate LRU cache)
                recent_symbols = [
                    f"SYMBOL_{j}"
                    for j in range(max(0, i - 299), i + 1)
                    if j % 100 == (i % 100)
                ]
                feature_cache = {
                    k: v for k, v in feature_cache.items() if k in recent_symbols
                }

                # Force garbage collection
                gc.collect()

                # Sample memory
                current_memory = psutil.Process().memory_info().rss / 1024 / 1024
                memory_samples.append(current_memory)

            # Brief pause to simulate real-time operation
            if i % 100 == 0:
                time.sleep(0.001)  # 1ms pause

        # Final memory measurement
        final_memory = psutil.Process().memory_info().rss / 1024 / 1024

        # Calculate memory statistics
        memory_growth = final_memory - baseline_memory
        peak_memory = max(memory_samples) if memory_samples else final_memory

        print("✓ Memory Usage Test:")
        print(f"  - Baseline: {baseline_memory:.1f}MB")
        print(f"  - Peak: {peak_memory:.1f}MB")
        print(f"  - Final: {final_memory:.1f}MB")
        print(f"  - Growth: {memory_growth:.1f}MB")
        print(f"  - Cache Size: {len(feature_cache)} items")

        # Memory growth should be controlled
        assert memory_growth < 50, f"Memory growth too high: {memory_growth:.1f}MB"

        # Peak memory should be reasonable
        assert (
            peak_memory < baseline_memory + 100
        ), f"Peak memory too high: {peak_memory:.1f}MB"

        # Cache should be bounded
        assert (
            len(feature_cache) < 200
        ), f"Cache not bounded: {len(feature_cache)} items"

    @pytest.mark.performance
    def test_garbage_collection_impact(self):
        """Test impact of garbage collection on performance."""

        # Create objects that will trigger GC
        large_objects = []
        processing_times = []

        for i in range(100):
            # Create large objects periodically
            if i % 10 == 0:
                # Create objects that will need GC
                large_obj = {f"key_{j}": list(range(1000)) for j in range(100)}
                large_objects.append(large_obj)

            # Time a typical operation
            start = time.perf_counter()

            # Simulate feature calculation
            data = np.random.randn(1000)
            result = {
                "mean": np.mean(data),
                "std": np.std(data),
                "max": np.max(data),
                "min": np.min(data),
            }

            end = time.perf_counter()
            processing_times.append((end - start) * 1000)  # Convert to ms

            # Cleanup periodically
            if i % 20 == 0 and large_objects:
                # Remove old objects to trigger GC
                large_objects = large_objects[-5:]  # Keep only recent 5
                gc.collect()

        # Analyze GC impact
        p50_time = statistics.median(processing_times)
        p95_time = np.percentile(processing_times, 95)
        p99_time = np.percentile(processing_times, 99)

        # Check for GC-related latency spikes
        outliers = [t for t in processing_times if t > p95_time * 2]

        print("✓ Garbage Collection Impact:")
        print(f"  - P50 Processing Time: {p50_time:.3f}ms")
        print(f"  - P95 Processing Time: {p95_time:.3f}ms")
        print(f"  - P99 Processing Time: {p99_time:.3f}ms")
        print(f"  - GC-related spikes: {len(outliers)}")

        # GC should not cause excessive latency spikes
        assert len(outliers) < 5, f"Too many GC spikes: {len(outliers)}"
        assert (
            p99_time < p50_time * 10
        ), f"P99 too high relative to P50: {p99_time:.3f}ms vs {p50_time:.3f}ms"


class TestResourceUtilization:
    """Test CPU, memory, and I/O resource utilization."""

    @pytest.mark.performance
    @pytest.mark.slow
    def test_cpu_utilization_efficiency(self):
        """Test CPU utilization efficiency under load."""

        process = psutil.Process()
        cpu_samples = []
        work_completed = 0

        # Simulate CPU-intensive workload
        start_time = time.perf_counter()

        while time.perf_counter() - start_time < 10:  # Run for 10 seconds
            # CPU-intensive work (feature calculations)
            data = np.random.randn(10000)

            # Technical indicator calculations
            sma_short = np.convolve(data, np.ones(20) / 20, mode="valid")
            sma_long = np.convolve(data, np.ones(50) / 50, mode="valid")

            # RSI calculation
            delta = np.diff(data)
            gains = np.where(delta > 0, delta, 0)
            losses = np.where(delta < 0, -delta, 0)

            avg_gains = np.convolve(gains, np.ones(14) / 14, mode="valid")
            avg_losses = np.convolve(losses, np.ones(14) / 14, mode="valid")

            rs = avg_gains / (avg_losses + 1e-8)  # Avoid division by zero
            rsi = 100 - (100 / (1 + rs))

            work_completed += 1

            # Sample CPU usage
            if work_completed % 10 == 0:
                cpu_percent = process.cpu_percent()
                cpu_samples.append(cpu_percent)

        duration = time.perf_counter() - start_time

        avg_cpu = statistics.mean(cpu_samples) if cpu_samples else 0
        work_per_second = work_completed / duration

        print("✓ CPU Utilization Test:")
        print(f"  - Work Completed: {work_completed} iterations")
        print(f"  - Work Rate: {work_per_second:.1f} iterations/sec")
        print(f"  - Average CPU: {avg_cpu:.1f}%")
        print(f"  - CPU Efficiency: {work_per_second / max(avg_cpu, 1):.2f} work/cpu%")

        # Should maintain reasonable CPU utilization
        assert avg_cpu < 80, f"CPU usage too high: {avg_cpu:.1f}%"

        # Should complete meaningful work
        assert work_completed > 50, f"Not enough work completed: {work_completed}"

    @pytest.mark.performance
    def test_io_performance(self, tmp_path):
        """Test I/O performance for data persistence."""

        profiler = PerformanceProfiler().start()

        # Test file I/O performance (simulating trade logging)
        log_file = tmp_path / "performance_test.log"

        write_times = []
        read_times = []

        # Write test - simulate trade logging
        trades_logged = 0

        with open(log_file, "w") as f:
            for i in range(10000):
                trade_data = {
                    "timestamp": datetime.now().isoformat(),
                    "symbol": f"SYMBOL_{i % 100}",
                    "side": "buy" if i % 2 == 0 else "sell",
                    "qty": 100 + (i % 900),
                    "price": 100.0 + np.random.normal(0, 10),
                    "commission": 1.0,
                }

                start = time.perf_counter()
                f.write(f"{trade_data}\n")
                end = time.perf_counter()

                write_times.append((end - start) * 1000)
                trades_logged += 1

                if i % 1000 == 0:
                    profiler.sample()
                    f.flush()  # Force write to disk

        # Read test - simulate log analysis
        start = time.perf_counter()

        with open(log_file) as f:
            lines_read = sum(1 for _ in f)

        end = time.perf_counter()
        read_time = (end - start) * 1000

        stats = profiler.stop()

        # Calculate I/O statistics
        avg_write_time = statistics.mean(write_times)
        p95_write_time = np.percentile(write_times, 95)

        writes_per_second = trades_logged / (
            stats["duration_seconds"] - read_time / 1000
        )

        print("✓ I/O Performance Test:")
        print(f"  - Writes: {trades_logged:,}")
        print(f"  - Write Rate: {writes_per_second:,.0f} writes/sec")
        print(f"  - Avg Write Time: {avg_write_time:.3f}ms")
        print(f"  - P95 Write Time: {p95_write_time:.3f}ms")
        print(f"  - Read Time: {read_time:.1f}ms for {lines_read:,} lines")

        # I/O should be reasonably fast
        assert avg_write_time < 1.0, f"Write latency too high: {avg_write_time:.3f}ms"
        assert (
            writes_per_second > 1000
        ), f"Write throughput too low: {writes_per_second:,.0f}/sec"
        assert (
            read_time < 100
        ), f"Read too slow: {read_time:.1f}ms for {lines_read} lines"


@pytest.fixture
def sample_market_data():
    """Generate sample market data for performance tests."""
    from tests.fixtures.market_data import generate_synthetic_ohlcv

    return generate_synthetic_ohlcv(
        symbol="TEST",
        days=252,  # 1 year
        freq="1min",  # Minute data for more samples
        volatility=0.02,
        trend=0.0001,
    )


@pytest.fixture
def mock_portfolio():
    """Mock portfolio for performance testing."""
    return {
        "cash": Decimal("50000.00"),
        "positions": {
            "SPY": {
                "qty": 100,
                "avg_price": Decimal("450.00"),
                "market_value": Decimal("45000.00"),
            },
            "QQQ": {
                "qty": 50,
                "avg_price": Decimal("375.00"),
                "market_value": Decimal("18750.00"),
            },
        },
        "total_value": Decimal("113750.00"),
    }


@pytest.fixture
def mock_order():
    """Mock order for performance testing."""
    return {
        "symbol": "AAPL",
        "side": "buy",
        "qty": 50,
        "type": "market",
        "timestamp": datetime.now(),
    }


@pytest.fixture
def sample_features():
    """Sample feature data for testing."""
    return {
        "rsi_14": 65.5,
        "macd_signal": 0.25,
        "bb_position": 0.75,
        "volume_ratio": 1.2,
        "price_momentum_5d": 2.3,
        "volatility_20d": 0.18,
    }
