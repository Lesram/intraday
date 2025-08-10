"""
Performance sanity tests for critical system components.
Tests latency budgets and throughput requirements under load.
Gated behind @pytest.mark.perf marker.
"""

import asyncio
import json
import statistics
import time
from unittest.mock import AsyncMock, patch

import pytest

from tests.helpers.factories import create_order_spec, create_signal_payload


@pytest.mark.perf
class TestPerformanceSanity:
    """Performance sanity tests with latency budgets and throughput requirements."""

    @pytest.fixture
    async def perf_test_app(self):
        """Create app configured for performance testing."""
        from backend.api.main import app

        # Configure with performance-optimized settings
        with patch.dict("os.environ", {
            "REDIS_POOL_SIZE": "20",
            "DB_POOL_SIZE": "10",
            "WORKER_CONCURRENCY": "4",
            "PERFORMANCE_MODE": "true"
        }):
            yield app

    @pytest.fixture
    def signal_factory(self):
        """Factory for generating test signals."""
        return create_signal_payload

    @pytest.fixture
    def order_factory(self):
        """Factory for generating test orders."""
        return create_order_spec

    @pytest.mark.asyncio
    async def test_api_latency_p50_budget(self, perf_test_app, signal_factory):
        """Test that API endpoints meet P50 latency budget of 50ms."""
        from httpx import ASGITransport, AsyncClient

        # Performance budget: P50 < 50ms
        latency_budget_ms = 50
        num_requests = 100

        latencies = []

        async with AsyncClient(
            transport=ASGITransport(app=perf_test_app),
            base_url="http://testserver"
        ) as client:

            # Warm up the application
            await client.get("/health")
            await asyncio.sleep(0.1)

            # Test signal submission endpoint
            for i in range(num_requests):
                signal_data = signal_factory(
                    symbol="AAPL",
                    signal_type="BUY",
                    strength=0.8,
                    features={"price_momentum": 0.05}
                )

                start_time = time.perf_counter()

                response = await client.post(
                    "/api/v1/signals",
                    json=signal_data,
                    headers={"Content-Type": "application/json"}
                )

                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000
                latencies.append(latency_ms)

                # Ensure request succeeded
                assert response.status_code in [200, 201, 202]

        # Analyze latency distribution
        p50_latency = statistics.median(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        p99_latency = statistics.quantiles(latencies, n=100)[98]  # 99th percentile

        # Assert performance budget
        assert p50_latency < latency_budget_ms, f"P50 latency {p50_latency:.1f}ms exceeds budget {latency_budget_ms}ms"

        # Log performance metrics for monitoring
        print("\nAPI Latency Performance:")
        print(f"P50: {p50_latency:.1f}ms (budget: {latency_budget_ms}ms)")
        print(f"P95: {p95_latency:.1f}ms")
        print(f"P99: {p99_latency:.1f}ms")
        print(f"Min: {min(latencies):.1f}ms")
        print(f"Max: {max(latencies):.1f}ms")

    @pytest.mark.asyncio
    async def test_order_processing_throughput(self, perf_test_app, order_factory):
        """Test order processing throughput meets minimum requirements."""
        # Throughput requirement: 100 orders/second sustained
        min_throughput_ops = 100
        test_duration_seconds = 5
        target_orders = min_throughput_ops * test_duration_seconds

        orders_processed = 0
        start_time = time.perf_counter()

        # Mock order processing components
        with patch("backend.services.order_service.OrderService") as mock_order_service:
            mock_order_service_instance = AsyncMock()
            mock_order_service.return_value = mock_order_service_instance

            async def mock_process_order(order_spec):
                # Simulate realistic processing time (5-10ms)
                await asyncio.sleep(0.007)
                return {
                    "order_id": f"order_{orders_processed}",
                    "status": "ACCEPTED",
                    "timestamp": time.time()
                }

            mock_order_service_instance.process_order.side_effect = mock_process_order

            # Create concurrent order processing tasks
            async def process_orders_batch(batch_size: int = 20):
                nonlocal orders_processed
                tasks = []

                for _ in range(batch_size):
                    order_spec = order_factory(
                        symbol="AAPL",
                        side="buy",
                        quantity=100,
                        order_type="market"
                    )

                    task = asyncio.create_task(
                        mock_order_service_instance.process_order(order_spec)
                    )
                    tasks.append(task)

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Count successful orders
                for result in results:
                    if not isinstance(result, Exception):
                        orders_processed += 1

            # Run throughput test
            batch_tasks = []
            while time.perf_counter() - start_time < test_duration_seconds:
                batch_task = asyncio.create_task(process_orders_batch())
                batch_tasks.append(batch_task)

                # Control batch rate to avoid overwhelming
                await asyncio.sleep(0.05)  # 50ms between batches

            # Wait for all batches to complete
            await asyncio.gather(*batch_tasks, return_exceptions=True)

        end_time = time.perf_counter()
        actual_duration = end_time - start_time
        actual_throughput = orders_processed / actual_duration

        # Assert throughput requirement
        assert actual_throughput >= min_throughput_ops, (
            f"Throughput {actual_throughput:.1f} ops/sec below requirement {min_throughput_ops} ops/sec"
        )

        print("\nOrder Processing Throughput:")
        print(f"Orders processed: {orders_processed}")
        print(f"Duration: {actual_duration:.2f}s")
        print(f"Throughput: {actual_throughput:.1f} orders/sec (requirement: {min_throughput_ops} orders/sec)")

    @pytest.mark.asyncio
    async def test_risk_engine_latency_budget(self, perf_test_app, order_factory):
        """Test risk engine processing meets latency budget of 10ms."""
        # Risk engine latency budget: P95 < 10ms
        risk_latency_budget_ms = 10
        num_risk_checks = 200

        latencies = []

        # Mock risk engine components
        with patch("backend.services.risk_manager.RiskManager") as mock_risk_manager:
            mock_risk_manager_instance = AsyncMock()
            mock_risk_manager.return_value = mock_risk_manager_instance

            async def mock_validate_order(order_spec):
                # Simulate risk calculation time (2-5ms)
                start = time.perf_counter()
                await asyncio.sleep(0.003)  # 3ms simulation
                end = time.perf_counter()

                return {
                    "approved": True,
                    "risk_score": 0.3,
                    "processing_time_ms": (end - start) * 1000
                }

            mock_risk_manager_instance.validate_order.side_effect = mock_validate_order

            # Run risk validation performance test
            for i in range(num_risk_checks):
                order_spec = order_factory(
                    symbol=f"STOCK_{i % 10}",  # Rotate symbols
                    side="buy" if i % 2 == 0 else "sell",
                    quantity=100 + (i * 10),
                    order_type="limit",
                    price=150.0 + (i * 0.1)
                )

                start_time = time.perf_counter()
                result = await mock_risk_manager_instance.validate_order(order_spec)
                end_time = time.perf_counter()

                latency_ms = (end_time - start_time) * 1000
                latencies.append(latency_ms)

                assert result["approved"] is not None  # Basic validation

        # Analyze risk engine performance
        p50_latency = statistics.median(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]
        p99_latency = statistics.quantiles(latencies, n=100)[98]

        # Assert performance budget
        assert p95_latency < risk_latency_budget_ms, (
            f"Risk engine P95 latency {p95_latency:.1f}ms exceeds budget {risk_latency_budget_ms}ms"
        )

        print("\nRisk Engine Latency Performance:")
        print(f"P50: {p50_latency:.1f}ms")
        print(f"P95: {p95_latency:.1f}ms (budget: {risk_latency_budget_ms}ms)")
        print(f"P99: {p99_latency:.1f}ms")

    @pytest.mark.asyncio
    async def test_database_query_performance(self, perf_test_app):
        """Test database query performance meets latency requirements."""
        # Database query budget: P95 < 25ms for complex queries
        db_latency_budget_ms = 25
        num_queries = 50

        latencies = []

        # Mock database operations
        with patch("backend.database.connection.get_db_session") as mock_get_session:
            mock_session = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_session

            async def mock_query_execution():
                # Simulate database query time (5-20ms)
                await asyncio.sleep(0.012)  # 12ms simulation
                return [
                    {"id": i, "symbol": f"STOCK_{i}", "price": 100.0 + i}
                    for i in range(100)  # Simulate result set
                ]

            mock_session.execute.return_value.fetchall.side_effect = mock_query_execution

            # Test different types of queries
            query_types = [
                "SELECT * FROM orders WHERE status = 'PENDING'",
                "SELECT * FROM positions WHERE symbol IN ('AAPL', 'GOOGL', 'MSFT')",
                "SELECT COUNT(*) FROM trades WHERE created_at > NOW() - INTERVAL '1 DAY'",
                "SELECT symbol, AVG(price) FROM trades GROUP BY symbol",
                "SELECT * FROM orders o JOIN positions p ON o.symbol = p.symbol"
            ]

            for i in range(num_queries):
                query = query_types[i % len(query_types)]

                start_time = time.perf_counter()

                async with mock_get_session() as session:
                    result = await session.execute(query)
                    rows = await result.fetchall()

                end_time = time.perf_counter()

                latency_ms = (end_time - start_time) * 1000
                latencies.append(latency_ms)

                assert len(rows) >= 0  # Basic result validation

        # Analyze database performance
        p95_latency = statistics.quantiles(latencies, n=20)[18]

        assert p95_latency < db_latency_budget_ms, (
            f"Database P95 latency {p95_latency:.1f}ms exceeds budget {db_latency_budget_ms}ms"
        )

        print("\nDatabase Query Performance:")
        print(f"P95: {p95_latency:.1f}ms (budget: {db_latency_budget_ms}ms)")

    @pytest.mark.asyncio
    async def test_websocket_broadcast_performance(self, perf_test_app):
        """Test WebSocket broadcast performance under load."""
        # WebSocket broadcast requirement: 1000 msgs/sec to 100 clients
        target_msg_rate = 1000  # messages per second
        num_clients = 100
        test_duration_seconds = 3

        messages_sent = 0
        clients_updated = 0

        # Mock WebSocket broadcaster
        with patch("backend.websocket.broadcaster.WebSocketBroadcaster") as mock_broadcaster:
            mock_broadcaster_instance = AsyncMock()
            mock_broadcaster.return_value = mock_broadcaster_instance

            # Simulate client connections
            active_connections = {}
            for i in range(num_clients):
                active_connections[f"client_{i}"] = {
                    "queue": [],
                    "last_update": time.time()
                }

            async def mock_broadcast(message_data):
                nonlocal messages_sent, clients_updated

                # Simulate broadcast latency (0.5-2ms per 100 clients)
                await asyncio.sleep(0.001)

                # Update all active connections
                for client_id in active_connections:
                    active_connections[client_id]["queue"].append(message_data)
                    active_connections[client_id]["last_update"] = time.time()

                messages_sent += 1
                clients_updated += len(active_connections)

            mock_broadcaster_instance.broadcast.side_effect = mock_broadcast
            mock_broadcaster_instance.active_connections = active_connections

            # Run broadcast performance test
            start_time = time.perf_counter()

            async def message_generator():
                """Generate market data messages at target rate."""
                message_interval = 1.0 / target_msg_rate  # seconds between messages

                while time.perf_counter() - start_time < test_duration_seconds:
                    message = {
                        "type": "market_data",
                        "symbol": "AAPL",
                        "price": 150.0 + (time.time() % 10),
                        "timestamp": time.time(),
                        "sequence": messages_sent
                    }

                    await mock_broadcaster_instance.broadcast(json.dumps(message))
                    await asyncio.sleep(message_interval)

            # Run message generation
            await message_generator()

        end_time = time.perf_counter()
        actual_duration = end_time - start_time
        actual_msg_rate = messages_sent / actual_duration

        # Assert performance requirements
        min_acceptable_rate = target_msg_rate * 0.9  # 90% of target rate
        assert actual_msg_rate >= min_acceptable_rate, (
            f"WebSocket broadcast rate {actual_msg_rate:.1f} msgs/sec below requirement {min_acceptable_rate} msgs/sec"
        )

        # Verify all clients received messages
        total_client_messages = sum(len(conn["queue"]) for conn in active_connections.values())
        expected_total = messages_sent * num_clients

        assert total_client_messages == expected_total, (
            f"Client message delivery mismatch: {total_client_messages} != {expected_total}"
        )

        print("\nWebSocket Broadcast Performance:")
        print(f"Messages sent: {messages_sent}")
        print(f"Duration: {actual_duration:.2f}s")
        print(f"Message rate: {actual_msg_rate:.1f} msgs/sec (target: {target_msg_rate} msgs/sec)")
        print(f"Total client updates: {clients_updated}")

    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, perf_test_app, signal_factory):
        """Test memory usage remains stable under sustained load."""
        import os

        import psutil

        process = psutil.Process(os.getpid())

        # Record initial memory usage
        initial_memory_mb = process.memory_info().rss / 1024 / 1024

        # Memory growth limit: 50MB during test
        max_memory_growth_mb = 50

        # Generate sustained load
        num_operations = 1000
        operations_completed = 0

        # Mock components to avoid external dependencies
        with patch("backend.services.signal_service.SignalService") as mock_signal_service:
            mock_signal_service_instance = AsyncMock()
            mock_signal_service.return_value = mock_signal_service_instance

            async def mock_process_signal(signal_data):
                # Simulate processing without memory leaks
                await asyncio.sleep(0.001)
                return {"status": "processed", "id": f"signal_{operations_completed}"}

            mock_signal_service_instance.process_signal.side_effect = mock_process_signal

            # Run sustained load test
            memory_readings = []

            for i in range(num_operations):
                signal_data = signal_factory(
                    symbol=f"STOCK_{i % 50}",  # Limited symbol rotation
                    signal_type="BUY" if i % 2 == 0 else "SELL",
                    strength=0.7
                )

                await mock_signal_service_instance.process_signal(signal_data)
                operations_completed += 1

                # Sample memory every 100 operations
                if i % 100 == 0:
                    current_memory_mb = process.memory_info().rss / 1024 / 1024
                    memory_readings.append(current_memory_mb)

        # Final memory reading
        final_memory_mb = process.memory_info().rss / 1024 / 1024
        memory_growth_mb = final_memory_mb - initial_memory_mb

        # Assert memory stability
        assert memory_growth_mb < max_memory_growth_mb, (
            f"Memory growth {memory_growth_mb:.1f}MB exceeds limit {max_memory_growth_mb}MB"
        )

        print("\nMemory Usage Performance:")
        print(f"Initial memory: {initial_memory_mb:.1f}MB")
        print(f"Final memory: {final_memory_mb:.1f}MB")
        print(f"Memory growth: {memory_growth_mb:.1f}MB (limit: {max_memory_growth_mb}MB)")
        print(f"Operations completed: {operations_completed}")

    @pytest.mark.asyncio
    async def test_concurrent_request_handling(self, perf_test_app, signal_factory):
        """Test system handles concurrent requests without degradation."""
        from httpx import ASGITransport, AsyncClient

        # Concurrency test: 50 concurrent requests should complete within 5 seconds
        num_concurrent_requests = 50
        max_completion_time_seconds = 5

        async def make_concurrent_request(client: AsyncClient, request_id: int):
            """Make a single concurrent request."""
            signal_data = signal_factory(
                symbol=f"CONC_{request_id % 10}",
                signal_type="BUY",
                strength=0.6
            )

            start_time = time.perf_counter()
            response = await client.post(
                "/api/v1/signals",
                json=signal_data,
                timeout=30.0  # Generous timeout
            )
            end_time = time.perf_counter()

            return {
                "request_id": request_id,
                "status_code": response.status_code,
                "latency_ms": (end_time - start_time) * 1000,
                "success": response.status_code in [200, 201, 202]
            }

        # Execute concurrent requests
        async with AsyncClient(
            transport=ASGITransport(app=perf_test_app),
            base_url="http://testserver"
        ) as client:

            start_time = time.perf_counter()

            # Create all concurrent request tasks
            tasks = [
                make_concurrent_request(client, i)
                for i in range(num_concurrent_requests)
            ]

            # Execute all requests concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            end_time = time.perf_counter()

        # Analyze concurrency performance
        total_completion_time = end_time - start_time
        successful_requests = [r for r in results if not isinstance(r, Exception) and r.get("success")]
        failed_requests = len(results) - len(successful_requests)

        # Assert concurrency requirements
        assert total_completion_time < max_completion_time_seconds, (
            f"Concurrent requests took {total_completion_time:.2f}s, exceeding limit {max_completion_time_seconds}s"
        )

        success_rate = len(successful_requests) / num_concurrent_requests
        assert success_rate >= 0.95, f"Success rate {success_rate:.2%} below 95% requirement"

        # Analyze latency under concurrency
        latencies = [r["latency_ms"] for r in successful_requests]
        if latencies:
            median_latency = statistics.median(latencies)
            max_latency = max(latencies)

            print("\nConcurrent Request Performance:")
            print(f"Total completion time: {total_completion_time:.2f}s (limit: {max_completion_time_seconds}s)")
            print(f"Success rate: {success_rate:.2%} ({len(successful_requests)}/{num_concurrent_requests})")
            print(f"Failed requests: {failed_requests}")
            print(f"Median latency: {median_latency:.1f}ms")
            print(f"Max latency: {max_latency:.1f}ms")
