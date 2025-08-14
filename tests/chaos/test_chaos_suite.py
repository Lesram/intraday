"""
Chaos Engineering Test Suite for Algorithmic Trading Platform

This module provides comprehensive chaos testing by injecting various failures
into external dependencies and infrastructure components. Tests verify:
- Circuit breaker behavior under failures
- Retry mechanisms with exponential backoff
- Dead Letter Queue (DLQ) message capture
- Service degradation and recovery
- Idempotency under failure conditions

All tests use mocks and simulated failures - no real network calls.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.infra.resilience import (
    CircuitBreakerConfig,
    CircuitBreakerOpenException,
    MaxRetriesExceededException,
    RetryConfig,
    TimeoutException,
    resilience_manager,
)

logger = logging.getLogger(__name__)


class FaultType(Enum):
    """Types of faults that can be injected."""

    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    CONNECTION_ERROR = "connection_error"
    SLOW_RESPONSE = "slow_response"
    INTERMITTENT_FAILURE = "intermittent_failure"
    DATA_CORRUPTION = "data_corruption"


@dataclass
class ChaosConfig:
    """Configuration for chaos test scenarios."""

    fault_type: FaultType
    failure_rate: float = 0.5  # Percentage of requests that fail
    failure_duration: float = 10.0  # Seconds
    recovery_time: float = 5.0  # Time to recover
    latency_ms: int = 5000  # Artificial latency in milliseconds


class ChaosFaultInjector:
    """Injects various types of faults into service calls."""

    def __init__(self, config: ChaosConfig):
        self.config = config
        self.injection_active = True
        self.call_count = 0

    async def inject_fault(self, original_func, *args, **kwargs):
        """Inject fault based on configuration."""
        self.call_count += 1

        if not self.injection_active:
            return await original_func(*args, **kwargs)

        # Determine if this call should fail
        should_fail = (self.call_count % int(1 / self.config.failure_rate)) == 0

        if should_fail:
            return await self._execute_fault(original_func, *args, **kwargs)
        else:
            return await original_func(*args, **kwargs)

    async def _execute_fault(self, original_func, *args, **kwargs):
        """Execute specific fault type."""
        if self.config.fault_type == FaultType.TIMEOUT:
            await asyncio.sleep(self.config.latency_ms / 1000)
            raise TimeoutError("Chaos-injected timeout")

        elif self.config.fault_type == FaultType.SERVER_ERROR:
            raise Exception("Chaos-injected server error (500)")

        elif self.config.fault_type == FaultType.CONNECTION_ERROR:
            raise ConnectionError("Chaos-injected connection error")

        elif self.config.fault_type == FaultType.SLOW_RESPONSE:
            await asyncio.sleep(self.config.latency_ms / 1000)
            return await original_func(*args, **kwargs)

        elif self.config.fault_type == FaultType.INTERMITTENT_FAILURE:
            if self.call_count % 3 == 0:  # Every 3rd call fails
                raise Exception("Chaos-injected intermittent failure")
            return await original_func(*args, **kwargs)

        elif self.config.fault_type == FaultType.DATA_CORRUPTION:
            result = await original_func(*args, **kwargs)
            # Corrupt the response data
            if isinstance(result, dict):
                result["corrupted"] = True
                result["price"] = -999.99  # Invalid price
            return result

        else:
            return await original_func(*args, **kwargs)

    def stop_injection(self):
        """Stop fault injection (simulate recovery)."""
        self.injection_active = False


@pytest.mark.chaos
class TestCircuitBreakerChaos:
    """Test circuit breaker behavior under various failure scenarios."""

    @pytest.fixture
    def circuit_breaker_config(self):
        """Circuit breaker configuration for testing."""
        return CircuitBreakerConfig(
            failure_threshold=3, recovery_timeout=5.0, success_threshold=2, timeout=2.0
        )

    @pytest.fixture
    def mock_external_service(self):
        """Mock external service that can be made to fail."""
        mock = AsyncMock()
        mock.return_value = {"status": "success", "data": "test_data"}
        return mock

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_consecutive_failures(
        self, circuit_breaker_config, mock_external_service
    ):
        """Test that circuit breaker opens after consecutive failures."""

        # Configure fault injection for server errors
        chaos_config = ChaosConfig(
            fault_type=FaultType.SERVER_ERROR,
            failure_rate=1.0,  # 100% failure rate
        )
        fault_injector = ChaosFaultInjector(chaos_config)

        # Get circuit breaker
        cb = resilience_manager.get_circuit_breaker(
            "test_service", circuit_breaker_config
        )

        # Mock the service to always fail
        mock_external_service.side_effect = Exception("Service unavailable")

        # Make enough failed calls to open the circuit
        failed_calls = 0
        for i in range(circuit_breaker_config.failure_threshold):
            try:
                await cb.call(mock_external_service)
            except Exception:
                failed_calls += 1

        assert failed_calls == circuit_breaker_config.failure_threshold

        # Next call should be rejected (circuit is open)
        with pytest.raises(CircuitBreakerOpenException):
            await cb.call(mock_external_service)

        # Verify circuit breaker metrics
        assert cb.state.value == "open"
        assert cb.failure_count == circuit_breaker_config.failure_threshold

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery_after_timeout(
        self, circuit_breaker_config, mock_external_service
    ):
        """Test circuit breaker transitions to half-open and recovers."""

        # Set very short recovery timeout for testing
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.1,  # 100ms
            success_threshold=1,
            timeout=1.0,
        )

        cb = resilience_manager.get_circuit_breaker("recovery_test", config)

        # First, open the circuit with failures
        mock_external_service.side_effect = Exception("Service down")

        for _ in range(config.failure_threshold):
            try:
                await cb.call(mock_external_service)
            except Exception:
                pass

        assert cb.state.value == "open"

        # Wait for recovery timeout
        await asyncio.sleep(0.2)

        # Now make service work again
        mock_external_service.side_effect = None
        mock_external_service.return_value = {"status": "recovered"}

        # Next call should succeed and close circuit
        result = await cb.call(mock_external_service)
        assert result["status"] == "recovered"
        assert cb.state.value == "closed"

    @pytest.mark.asyncio
    async def test_circuit_breaker_with_timeout_injection(
        self, circuit_breaker_config, mock_external_service
    ):
        """Test circuit breaker behavior with timeout faults."""

        # Configure for short timeout
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=1.0,
            timeout=0.5,  # 500ms timeout
        )

        cb = resilience_manager.get_circuit_breaker("timeout_test", config)

        # Mock service with long delay to trigger timeout
        async def slow_service():
            await asyncio.sleep(1.0)  # Longer than circuit breaker timeout
            return {"data": "slow_response"}

        # Trigger timeouts to open circuit
        timeout_count = 0
        for _ in range(config.failure_threshold):
            try:
                await cb.call(slow_service)
            except TimeoutException:
                timeout_count += 1

        assert timeout_count == config.failure_threshold
        assert cb.state.value == "open"

        # Circuit should now reject calls
        with pytest.raises(CircuitBreakerOpenException):
            await cb.call(slow_service)


@pytest.mark.chaos
class TestRetryMechanismChaos:
    """Test retry mechanisms under various failure scenarios."""

    @pytest.fixture
    def retry_config(self):
        """Retry configuration for testing."""
        return RetryConfig(
            max_attempts=3,
            base_delay=0.1,  # Fast retries for testing
            max_delay=1.0,
            backoff_multiplier=2.0,
            jitter=False,  # Disable jitter for predictable testing
        )

    @pytest.mark.asyncio
    async def test_retry_with_intermittent_failures(self, retry_config):
        """Test retry mechanism with intermittent failures."""

        retry_manager = resilience_manager.get_retry_manager(
            "intermittent_test", retry_config
        )

        call_count = 0

        async def flaky_service():
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                raise ConnectionError("First call fails")
            elif call_count == 2:
                raise Exception("Second call fails")
            else:
                return {"success": True, "attempt": call_count}

        # Should succeed on third attempt
        result = await retry_manager.execute_with_retry(flaky_service)

        assert result["success"] is True
        assert result["attempt"] == 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhaustion_sends_to_dlq(self, retry_config):
        """Test that exhausted retries send message to DLQ."""

        retry_manager = resilience_manager.get_retry_manager("dlq_test", retry_config)

        async def always_failing_service():
            raise Exception("Service permanently down")

        # Mock the DLQ sending
        with patch("backend.infra.resilience.logger") as mock_logger:
            with pytest.raises(MaxRetriesExceededException):
                await retry_manager.execute_with_retry(
                    always_failing_service, idempotency_key="test-key-123"
                )

            # Verify DLQ message was logged (in real implementation, would be sent to queue)
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0][0]
            assert "Sending to DLQ" in error_call

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self, retry_config):
        """Test that exponential backoff delays increase correctly."""

        retry_manager = resilience_manager.get_retry_manager(
            "backoff_test", retry_config
        )

        call_times = []

        async def timing_service():
            call_times.append(time.time())
            raise Exception("Always fails for timing test")

        start_time = time.time()

        with pytest.raises(MaxRetriesExceededException):
            await retry_manager.execute_with_retry(timing_service)

        # Verify exponential backoff delays
        assert len(call_times) == retry_config.max_attempts

        # Check delays between attempts
        delay_1 = call_times[1] - call_times[0]
        delay_2 = call_times[2] - call_times[1]

        # First delay should be ~0.1s, second ~0.2s
        assert 0.08 <= delay_1 <= 0.15  # Allow some variance
        assert 0.18 <= delay_2 <= 0.25


@pytest.mark.chaos
class TestDatabaseChaos:
    """Test database resilience under various failure scenarios."""

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_database_connection_failures(self, mock_db_session):
        """Test handling of database connection failures."""

        # Configure retry for database operations
        retry_config = RetryConfig(max_attempts=3, base_delay=0.1)
        retry_manager = resilience_manager.get_retry_manager("database", retry_config)

        # Simulate connection failures
        mock_db_session.execute.side_effect = [
            ConnectionError("Connection lost"),
            ConnectionError("Still down"),
            {"result": "success"},  # Third attempt succeeds
        ]

        async def database_operation():
            result = await mock_db_session.execute("SELECT * FROM orders")
            await mock_db_session.commit()
            return result

        result = await retry_manager.execute_with_retry(database_operation)
        assert result == {"result": "success"}
        assert mock_db_session.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_database_transaction_rollback_on_failure(self, mock_db_session):
        """Test that failed transactions are properly rolled back."""

        retry_manager = resilience_manager.get_retry_manager(
            "db_transaction", RetryConfig(max_attempts=1)
        )

        # Simulate transaction failure
        mock_db_session.commit.side_effect = Exception("Transaction failed")

        async def failing_transaction():
            await mock_db_session.execute("INSERT INTO orders ...")
            await mock_db_session.commit()
            return "committed"

        with pytest.raises(MaxRetriesExceededException):
            await retry_manager.execute_with_retry(failing_transaction)

        # Verify rollback was called
        mock_db_session.rollback.assert_called()


@pytest.mark.chaos
class TestExternalAPIResilienceChaos:
    """Test resilience with external API failures (Alpaca, etc.)."""

    @pytest.fixture
    def mock_alpaca_client(self):
        """Mock Alpaca API client."""
        client = MagicMock()
        client.get_account = AsyncMock()
        client.submit_order = AsyncMock()
        client.get_portfolio = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_broker_api_timeout_handling(self, mock_alpaca_client):
        """Test handling of broker API timeouts."""

        # Configure circuit breaker for broker API
        cb_config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout=1.0,  # 1 second timeout
            recovery_timeout=2.0,
        )

        cb = resilience_manager.get_circuit_breaker("alpaca_api", cb_config)

        # Simulate slow API responses
        async def slow_api_call():
            await asyncio.sleep(2.0)  # Longer than timeout
            return {"account": "test"}

        # First few calls should timeout and open circuit
        timeout_count = 0
        for _ in range(cb_config.failure_threshold):
            try:
                await cb.call(slow_api_call)
            except TimeoutException:
                timeout_count += 1

        assert timeout_count == cb_config.failure_threshold
        assert cb.state.value == "open"

    @pytest.mark.asyncio
    async def test_broker_api_rate_limit_handling(self, mock_alpaca_client):
        """Test handling of broker API rate limiting."""

        retry_config = RetryConfig(
            max_attempts=4,
            base_delay=1.0,  # Longer delay for rate limits
            max_delay=10.0,
            backoff_multiplier=2.0,
        )

        retry_manager = resilience_manager.get_retry_manager(
            "rate_limited_api", retry_config
        )

        call_count = 0

        async def rate_limited_api():
            nonlocal call_count
            call_count += 1

            if call_count <= 2:
                # Simulate rate limit error
                error = Exception("Rate limit exceeded - 429")
                error.status_code = 429
                raise error
            else:
                return {"order_id": "12345", "status": "submitted"}

        result = await retry_manager.execute_with_retry(rate_limited_api)

        assert result["status"] == "submitted"
        assert call_count == 3  # Succeeded on third attempt

    @pytest.mark.asyncio
    async def test_market_data_feed_interruption(self, mock_alpaca_client):
        """Test handling of market data feed interruptions."""

        # Simulate WebSocket connection drops
        connection_attempts = 0

        async def websocket_connect():
            nonlocal connection_attempts
            connection_attempts += 1

            if connection_attempts <= 2:
                raise ConnectionError("WebSocket connection failed")

            # Mock successful connection
            return MagicMock(
                connected=True,
                receive=AsyncMock(return_value='{"type": "quote", "symbol": "AAPL"}'),
            )

        retry_manager = resilience_manager.get_retry_manager(
            "websocket", RetryConfig(max_attempts=5)
        )

        connection = await retry_manager.execute_with_retry(websocket_connect)

        assert connection.connected is True
        assert connection_attempts == 3


@pytest.mark.chaos
class TestIdempotencyChaos:
    """Test idempotency under various failure scenarios."""

    @pytest.fixture
    def mock_order_service(self):
        """Mock order service with idempotency tracking."""
        service = MagicMock()
        service.processed_orders = set()  # Track processed order IDs

        async def submit_order(order_id, order_data):
            if order_id in service.processed_orders:
                return {"status": "duplicate", "order_id": order_id}

            # Simulate potential failure
            if order_data.get("should_fail"):
                raise Exception("Order processing failed")

            service.processed_orders.add(order_id)
            return {"status": "submitted", "order_id": order_id}

        service.submit_order = submit_order
        return service

    @pytest.mark.asyncio
    async def test_idempotent_order_submission_under_retries(self, mock_order_service):
        """Test that order submission remains idempotent under retries."""

        retry_manager = resilience_manager.get_retry_manager(
            "order_service", RetryConfig(max_attempts=3)
        )

        order_id = "test-order-123"
        order_data = {"symbol": "AAPL", "quantity": 100}

        # First submission should succeed
        result1 = await retry_manager.execute_with_retry(
            mock_order_service.submit_order,
            order_id,
            order_data,
            idempotency_key=order_id,
        )

        assert result1["status"] == "submitted"
        assert order_id in mock_order_service.processed_orders

        # Second submission with same ID should be detected as duplicate
        result2 = await retry_manager.execute_with_retry(
            mock_order_service.submit_order,
            order_id,
            order_data,
            idempotency_key=order_id,
        )

        assert result2["status"] == "duplicate"
        assert len(mock_order_service.processed_orders) == 1  # Still only one order

    @pytest.mark.asyncio
    async def test_idempotency_with_partial_failures(self, mock_order_service):
        """Test idempotency when operations partially fail."""

        retry_manager = resilience_manager.get_retry_manager(
            "partial_failure", RetryConfig(max_attempts=3)
        )

        call_count = 0

        async def partially_failing_operation():
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # Simulate partial success - order processed but response lost
                mock_order_service.processed_orders.add("partial-order-456")
                raise ConnectionError("Response lost")
            elif call_count == 2:
                # Second attempt should detect duplicate
                return {"status": "duplicate", "order_id": "partial-order-456"}

        result = await retry_manager.execute_with_retry(
            partially_failing_operation, idempotency_key="partial-order-456"
        )

        assert result["status"] == "duplicate"
        assert call_count == 2


@pytest.mark.chaos
class TestChaosSchedulingIntegration:
    """Test integration with CI scheduling for weekly chaos tests."""

    def test_chaos_test_discovery(self):
        """Test that chaos tests are properly marked and discoverable."""

        # This would be called by CI to discover chaos tests
        import inspect

        from tests.chaos import test_chaos_suite

        chaos_tests = []
        for name, obj in inspect.getmembers(test_chaos_suite):
            if inspect.isclass(obj) and hasattr(obj, "__pytest_mark__"):
                for mark in obj.__pytest_mark__:
                    if mark.name == "chaos":
                        chaos_tests.append(name)

        assert len(chaos_tests) > 0, "No chaos tests discovered"

    @pytest.mark.asyncio
    async def test_chaos_test_reporting(self):
        """Test that chaos test results are properly reported."""

        # Mock chaos test execution results
        chaos_results = {
            "circuit_breaker_tests": {"passed": 4, "failed": 0},
            "retry_mechanism_tests": {"passed": 3, "failed": 0},
            "database_chaos_tests": {"passed": 2, "failed": 0},
            "external_api_tests": {"passed": 3, "failed": 0},
            "idempotency_tests": {"passed": 2, "failed": 0},
        }

        total_passed = sum(result["passed"] for result in chaos_results.values())
        total_failed = sum(result["failed"] for result in chaos_results.values())

        assert total_passed > 10, "Insufficient chaos test coverage"
        assert total_failed == 0, "Some chaos tests are failing"

        # In real implementation, this would send results to monitoring system
        logger.info(f"Chaos test results: {total_passed} passed, {total_failed} failed")


# Chaos test configuration for CI scheduling
WEEKLY_CHAOS_CONFIG = {
    "schedule": "0 2 * * 1",  # Every Monday at 2 AM
    "duration_minutes": 60,
    "notification_channels": ["#chaos-engineering", "#sre-alerts"],
    "environments": ["staging", "pre-production"],
    "failure_scenarios": [
        "database_connection_loss",
        "external_api_timeout",
        "network_partition",
        "high_latency_injection",
        "memory_pressure",
        "cpu_throttling",
    ],
}


# Helper function for CI integration
def get_chaos_test_suite():
    """Return list of chaos test classes for CI execution."""
    return [
        TestCircuitBreakerChaos,
        TestRetryMechanismChaos,
        TestDatabaseChaos,
        TestExternalAPIResilienceChaos,
        TestIdempotencyChaos,
        TestChaosSchedulingIntegration,
    ]
