"""
WebSocket Performance Test Suite for Algorithmic Trading Platform

This module provides comprehensive performance testing for WebSocket connections,
focusing on burst testing, connection stability, and message throughput under load.
"""

import asyncio
from dataclasses import dataclass, field
import json
import logging
import statistics
import threading
import time

import pytest
import websockets

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ConnectionMetrics:
    """Metrics for a single WebSocket connection during testing."""

    connection_id: str
    connect_time: float = 0.0
    disconnect_time: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0
    errors: list[str] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)
    connection_duration: float = 0.0

    @property
    def avg_latency(self) -> float:
        """Calculate average message latency."""
        return statistics.mean(self.latencies) if self.latencies else 0.0

    @property
    def p95_latency(self) -> float:
        """Calculate P95 message latency."""
        return (
            statistics.quantiles(self.latencies, n=20)[18]
            if len(self.latencies) >= 20
            else 0.0
        )


@dataclass
class TestResults:
    """Aggregate test results for WebSocket performance testing."""

    total_connections: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    total_messages: int = 0
    total_errors: int = 0
    test_duration: float = 0.0
    connection_metrics: list[ConnectionMetrics] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate connection success rate."""
        return (
            (self.successful_connections / self.total_connections * 100)
            if self.total_connections > 0
            else 0.0
        )

    @property
    def messages_per_second(self) -> float:
        """Calculate overall message throughput."""
        return (
            self.total_messages / self.test_duration if self.test_duration > 0 else 0.0
        )

    @property
    def avg_connection_duration(self) -> float:
        """Calculate average connection duration."""
        durations = [
            m.connection_duration
            for m in self.connection_metrics
            if m.connection_duration > 0
        ]
        return statistics.mean(durations) if durations else 0.0


class WebSocketBurstTester:
    """
    High-performance WebSocket burst tester for the algorithmic trading platform.

    Simulates realistic trading scenarios with multiple concurrent connections,
    message bursts, and connection churn.
    """

    def __init__(
        self,
        base_url: str = "ws://localhost:8000",
        auth_token: str | None = None,
        max_concurrent_connections: int = 100,
    ):
        self.base_url = base_url
        self.auth_token = auth_token
        self.max_concurrent_connections = max_concurrent_connections
        self.results = TestResults()
        self._stop_event = threading.Event()

    async def create_connection(
        self, connection_id: str, endpoint: str = "/api/v1/ws/market-data"
    ) -> ConnectionMetrics:
        """Create a single WebSocket connection and collect metrics."""
        metrics = ConnectionMetrics(connection_id=connection_id)
        uri = f"{self.base_url}{endpoint}"

        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        try:
            start_time = time.time()

            async with websockets.connect(uri, extra_headers=headers) as websocket:
                metrics.connect_time = time.time() - start_time
                logger.debug(
                    f"Connection {connection_id} established in {metrics.connect_time:.3f}s"
                )

                # Subscribe to market data
                subscribe_msg = {
                    "action": "subscribe",
                    "channel": "quotes",
                    "symbol": "AAPL",
                }
                await websocket.send(json.dumps(subscribe_msg))
                metrics.messages_sent += 1

                # Listen for messages until stopped
                connection_start = time.time()

                try:
                    while not self._stop_event.is_set():
                        try:
                            # Wait for message with timeout
                            message = await asyncio.wait_for(
                                websocket.recv(), timeout=1.0
                            )

                            receive_time = time.time()
                            metrics.messages_received += 1

                            # Parse message and calculate latency if it has a timestamp
                            try:
                                msg_data = json.loads(message)
                                if "timestamp" in msg_data:
                                    latency = receive_time - msg_data["timestamp"]
                                    metrics.latencies.append(latency)
                            except json.JSONDecodeError:
                                pass

                        except TimeoutError:
                            # Send heartbeat to keep connection alive
                            heartbeat = {"action": "ping"}
                            await websocket.send(json.dumps(heartbeat))
                            metrics.messages_sent += 1

                        except websockets.exceptions.ConnectionClosed:
                            logger.warning(
                                f"Connection {connection_id} closed by server"
                            )
                            break

                except Exception as e:
                    metrics.errors.append(f"Message handling error: {str(e)}")
                    logger.error(f"Connection {connection_id} error: {e}")

                metrics.connection_duration = time.time() - connection_start
                metrics.disconnect_time = time.time()

        except Exception as e:
            metrics.errors.append(f"Connection error: {str(e)}")
            logger.error(f"Failed to establish connection {connection_id}: {e}")

        return metrics

    async def burst_test(
        self,
        num_connections: int = 50,
        duration_seconds: float = 30.0,
        connection_ramp_rate: float = 10.0,
    ) -> TestResults:
        """
        Execute burst test with specified parameters.

        Args:
            num_connections: Number of concurrent connections to establish
            duration_seconds: How long to maintain the test
            connection_ramp_rate: Connections per second ramp-up rate
        """
        logger.info(
            f"Starting WebSocket burst test: {num_connections} connections, {duration_seconds}s duration"
        )

        self.results = TestResults()
        self.results.total_connections = num_connections
        self._stop_event.clear()

        # Start timer
        test_start_time = time.time()

        # Create connections with ramp-up
        connection_tasks = []
        for i in range(num_connections):
            connection_id = f"conn_{i:04d}"
            task = asyncio.create_task(self.create_connection(connection_id))
            connection_tasks.append(task)

            # Ramp up connections gradually
            if i < num_connections - 1:
                await asyncio.sleep(1.0 / connection_ramp_rate)

        # Let connections run for the specified duration
        await asyncio.sleep(duration_seconds)

        # Stop all connections
        self._stop_event.set()
        logger.info("Stopping all connections...")

        # Wait for all connections to complete
        metrics_list = await asyncio.gather(*connection_tasks, return_exceptions=True)

        # Process results
        for metrics in metrics_list:
            if isinstance(metrics, ConnectionMetrics):
                self.results.connection_metrics.append(metrics)
                if metrics.errors:
                    self.results.failed_connections += 1
                    self.results.total_errors += len(metrics.errors)
                else:
                    self.results.successful_connections += 1

                self.results.total_messages += (
                    metrics.messages_received + metrics.messages_sent
                )

        self.results.test_duration = time.time() - test_start_time

        logger.info(f"Burst test completed in {self.results.test_duration:.2f}s")
        self._log_results()

        return self.results

    async def connection_churn_test(
        self,
        connections_per_wave: int = 20,
        num_waves: int = 5,
        wave_interval: float = 10.0,
    ) -> TestResults:
        """
        Test connection churn - rapidly connecting and disconnecting.

        Args:
            connections_per_wave: Number of connections in each wave
            num_waves: Number of connection waves
            wave_interval: Time between waves in seconds
        """
        logger.info(
            f"Starting connection churn test: {num_waves} waves of {connections_per_wave} connections"
        )

        self.results = TestResults()
        self.results.total_connections = connections_per_wave * num_waves

        test_start_time = time.time()

        for wave in range(num_waves):
            logger.info(f"Starting wave {wave + 1}/{num_waves}")

            # Create connections for this wave
            wave_tasks = []
            for i in range(connections_per_wave):
                connection_id = f"wave_{wave:02d}_conn_{i:04d}"
                task = asyncio.create_task(self.create_connection(connection_id))
                wave_tasks.append(task)

            # Let connections run for a short time
            await asyncio.sleep(5.0)

            # Stop this wave
            self._stop_event.set()

            # Wait for wave to complete
            wave_metrics = await asyncio.gather(*wave_tasks, return_exceptions=True)

            # Process wave results
            for metrics in wave_metrics:
                if isinstance(metrics, ConnectionMetrics):
                    self.results.connection_metrics.append(metrics)
                    if metrics.errors:
                        self.results.failed_connections += 1
                        self.results.total_errors += len(metrics.errors)
                    else:
                        self.results.successful_connections += 1

                    self.results.total_messages += (
                        metrics.messages_received + metrics.messages_sent
                    )

            # Reset stop event for next wave
            self._stop_event.clear()

            # Wait before next wave (except for last wave)
            if wave < num_waves - 1:
                await asyncio.sleep(
                    wave_interval - 5.0
                )  # Subtract the 5s we already waited

        self.results.test_duration = time.time() - test_start_time

        logger.info(
            f"Connection churn test completed in {self.results.test_duration:.2f}s"
        )
        self._log_results()

        return self.results

    def _log_results(self):
        """Log comprehensive test results."""
        logger.info("=== WebSocket Performance Test Results ===")
        logger.info(f"Total connections attempted: {self.results.total_connections}")
        logger.info(f"Successful connections: {self.results.successful_connections}")
        logger.info(f"Failed connections: {self.results.failed_connections}")
        logger.info(f"Success rate: {self.results.success_rate:.1f}%")
        logger.info(f"Total messages: {self.results.total_messages}")
        logger.info(f"Messages per second: {self.results.messages_per_second:.1f}")
        logger.info(
            f"Average connection duration: {self.results.avg_connection_duration:.2f}s"
        )
        logger.info(f"Total errors: {self.results.total_errors}")

        if self.results.connection_metrics:
            all_latencies = []
            for metrics in self.results.connection_metrics:
                all_latencies.extend(metrics.latencies)

            if all_latencies:
                logger.info(
                    f"Average latency: {statistics.mean(all_latencies) * 1000:.1f}ms"
                )
                logger.info(
                    f"P95 latency: {statistics.quantiles(all_latencies, n=20)[18] * 1000:.1f}ms"
                )


# Test Classes for pytest


class TestWebSocketPerformance:
    """Pytest test class for WebSocket performance testing."""

    @pytest.fixture
    def tester(self):
        """Create a WebSocket burst tester instance."""
        return WebSocketBurstTester()

    @pytest.mark.asyncio
    async def test_websocket_burst_small(self, tester):
        """Test small burst of WebSocket connections."""
        results = await tester.burst_test(num_connections=10, duration_seconds=15.0)

        # Assertions for performance thresholds
        assert (
            results.success_rate >= 90.0
        ), f"Success rate too low: {results.success_rate}%"
        assert (
            results.messages_per_second >= 1.0
        ), f"Message throughput too low: {results.messages_per_second}"
        assert results.total_errors < 5, f"Too many errors: {results.total_errors}"

    @pytest.mark.asyncio
    async def test_websocket_burst_medium(self, tester):
        """Test medium burst of WebSocket connections."""
        results = await tester.burst_test(num_connections=25, duration_seconds=20.0)

        # Performance thresholds
        assert (
            results.success_rate >= 85.0
        ), f"Success rate too low: {results.success_rate}%"
        assert (
            results.messages_per_second >= 5.0
        ), f"Message throughput too low: {results.messages_per_second}"
        assert results.total_errors < 10, f"Too many errors: {results.total_errors}"

    @pytest.mark.asyncio
    async def test_websocket_connection_churn(self, tester):
        """Test connection churn with multiple waves."""
        results = await tester.connection_churn_test(
            connections_per_wave=15, num_waves=3, wave_interval=8.0
        )

        # Churn-specific thresholds
        assert (
            results.success_rate >= 80.0
        ), f"Success rate too low under churn: {results.success_rate}%"
        assert (
            results.total_errors < 15
        ), f"Too many errors during churn: {results.total_errors}"

    @pytest.mark.asyncio
    async def test_websocket_latency_requirements(self, tester):
        """Test that WebSocket message latency meets requirements."""
        results = await tester.burst_test(num_connections=5, duration_seconds=30.0)

        if results.connection_metrics:
            all_latencies = []
            for metrics in results.connection_metrics:
                all_latencies.extend(metrics.latencies)

            if all_latencies:
                avg_latency_ms = statistics.mean(all_latencies) * 1000
                p95_latency_ms = statistics.quantiles(all_latencies, n=20)[18] * 1000

                assert (
                    avg_latency_ms < 100.0
                ), f"Average latency too high: {avg_latency_ms:.1f}ms"
                assert (
                    p95_latency_ms < 200.0
                ), f"P95 latency too high: {p95_latency_ms:.1f}ms"


# Standalone execution for manual testing
async def main():
    """Main function for standalone execution."""
    logger.info("Starting WebSocket performance test suite")

    tester = WebSocketBurstTester(
        base_url="ws://localhost:8000",
        auth_token=None,  # Set this if authentication is required
    )

    # Run burst test
    logger.info("Running burst test...")
    await tester.burst_test(num_connections=20, duration_seconds=30.0)

    # Run connection churn test
    logger.info("Running connection churn test...")
    await tester.connection_churn_test(connections_per_wave=10, num_waves=3)

    logger.info("Performance test suite completed")


if __name__ == "__main__":
    asyncio.run(main())
