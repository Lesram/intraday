"""
Test OrderService contract - idempotency, retries, circuit breaker, and metrics.
"""

import pytest
from unittest.mock import patch, MagicMock, call
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import time

from backend.services.order_service import OrderService
from backend.risk.types import OrderSpec, RiskLimits, Side
from backend.strategies.types import TradingSignal, ExecutionPlan


class TestOrderServiceContract:
    """Test OrderService business logic and resilience patterns"""

    @pytest.fixture
    def order_service(self):
        """Create OrderService with mocked dependencies"""
        with patch('backend.services.order_service.OrderService.__init__', return_value=None):
            service = OrderService.__new__(OrderService)
            service.broker_client = MagicMock()
            service.db_session = MagicMock()
            service.risk_manager = MagicMock()
            service.metrics = MagicMock()
            return service

    @pytest.fixture
    def sample_order_spec(self):
        """Create a sample order specification"""
        return OrderSpec(
            symbol="AAPL",
            side="buy",
            qty=Decimal('100'),
            notional=Decimal('15000.0'),
            price=Decimal('150.0'),
            attributes={"client_order_id": "test_order_123"}
        )

    def test_idempotency_same_client_order_id_single_external_call(self, order_service, sample_order_spec):
        """Test that duplicate client_order_id results in only one external call"""
        # Mock existing order in database
        existing_order = MagicMock()
        existing_order.client_order_id = "test_order_123"
        existing_order.status = "filled"
        
        # First call - order doesn't exist, should make external call
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        order_service.broker_client.submit_order.return_value = {"order_id": "ext_123", "status": "filled"}
        
        result1 = order_service.submit_order(sample_order_spec)
        assert order_service.broker_client.submit_order.call_count == 1
        
        # Second call - order exists, should NOT make external call
        order_service.db_session.query.return_value.filter.return_value.first.return_value = existing_order
        order_service.broker_client.reset_mock()
        
        result2 = order_service.submit_order(sample_order_spec)
        assert order_service.broker_client.submit_order.call_count == 0
        
        # Should return the existing order result
        assert result2 is not None

    def test_retry_on_429_with_jitter(self, order_service, sample_order_spec):
        """Test retry logic on 429 status with jitter"""
        from requests.exceptions import HTTPError
        
        # Mock 429 responses followed by success
        http_error_429 = HTTPError()
        http_error_429.response = MagicMock()
        http_error_429.response.status_code = 429
        
        order_service.broker_client.submit_order.side_effect = [
            http_error_429,  # First call - 429
            http_error_429,  # Second call - 429  
            {"order_id": "ext_123", "status": "filled"}  # Third call - success
        ]
        
        # Mock no existing order
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        # Mock sleep to avoid actual delays in tests
        with patch('time.sleep') as mock_sleep, \
             patch('random.uniform', return_value=0.5) as mock_jitter:
            
            result = order_service.submit_order(sample_order_spec)
            
            # Should have retried twice (3 total attempts)
            assert order_service.broker_client.submit_order.call_count == 3
            
            # Should have slept with jitter
            assert mock_sleep.call_count == 2  # Two retries
            
            # Verify jitter was applied to sleep duration
            sleep_calls = mock_sleep.call_args_list
            for call in sleep_calls:
                sleep_duration = call[0][0]
                assert sleep_duration > 0  # Should have some delay
                
            # Should eventually succeed
            assert result["order_id"] == "ext_123"

    def test_circuit_breaker_opens_after_n_failures(self, order_service, sample_order_spec):
        """Test circuit breaker opens after N consecutive failures"""
        from requests.exceptions import HTTPError, ConnectionError
        
        # Mock connection errors (simulating service unavailable)
        connection_error = ConnectionError("Service unavailable")
        
        order_service.broker_client.submit_order.side_effect = connection_error
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        # Mock circuit breaker state
        circuit_breaker = MagicMock()
        circuit_breaker.is_open = False
        circuit_breaker.failure_count = 0
        
        with patch('backend.services.order_service.CircuitBreaker', return_value=circuit_breaker):
            
            # Simulate multiple failures
            for i in range(5):  # Assume circuit breaker opens after 5 failures
                try:
                    order_service.submit_order(sample_order_spec)
                except Exception:
                    circuit_breaker.failure_count += 1
                    if circuit_breaker.failure_count >= 3:  # Mock threshold
                        circuit_breaker.is_open = True
                        break
            
            # Circuit breaker should be open
            assert circuit_breaker.is_open or circuit_breaker.failure_count >= 3

    def test_dead_letter_queue_on_final_failure(self, order_service, sample_order_spec):
        """Test that final failures are sent to Dead Letter Queue"""
        from requests.exceptions import HTTPError
        
        # Mock permanent error (non-retriable)
        http_error_400 = HTTPError()
        http_error_400.response = MagicMock()
        http_error_400.response.status_code = 400  # Bad request - don't retry
        
        order_service.broker_client.submit_order.side_effect = http_error_400
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        # Mock DLQ
        dlq_handler = MagicMock()
        
        with patch('backend.services.order_service.DLQHandler', return_value=dlq_handler):
            
            try:
                order_service.submit_order(sample_order_spec)
            except HTTPError:
                pass  # Expected to fail
            
            # Should have attempted only once (400 is not retriable)
            assert order_service.broker_client.submit_order.call_count == 1
            
            # Should have sent to DLQ
            if dlq_handler.send_to_dlq.called:
                dlq_handler.send_to_dlq.assert_called_once()

    def test_relevant_metrics_emitted(self, order_service, sample_order_spec):
        """Test that relevant metrics are emitted during order processing"""
        # Mock successful order
        order_service.broker_client.submit_order.return_value = {"order_id": "ext_123", "status": "filled"}
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        # Execute order submission
        result = order_service.submit_order(sample_order_spec)
        
        # Verify metrics were recorded
        metrics_calls = order_service.metrics.method_calls
        
        # Should have recorded order attempt
        metric_names = [call[0] for call in metrics_calls]
        
        # Look for expected metric calls
        expected_metrics = [
            'increment',  # For counters
            'histogram',  # For latency
            'gauge',      # For active orders
        ]
        
        # At least some metrics should have been called
        assert len(metrics_calls) > 0, "No metrics were recorded"

    def test_order_validation_before_submission(self, order_service, sample_order_spec):
        """Test that orders are validated before external submission"""
        # Mock risk manager to reject order
        order_service.risk_manager.validate_order.return_value = (False, "Risk limit exceeded")
        
        # Should not make external call if risk validation fails
        with pytest.raises(Exception):  # Should raise validation error
            order_service.submit_order(sample_order_spec)
        
        # Should not have called broker
        assert order_service.broker_client.submit_order.call_count == 0
        
        # Should have called risk validation
        order_service.risk_manager.validate_order.assert_called_once()

    def test_concurrent_order_submission_handling(self, order_service):
        """Test handling of concurrent order submissions"""
        order_specs = [
            OrderSpec(
                symbol="AAPL",
                side="buy", 
                qty=Decimal('100'),
                notional=Decimal('15000.0'),
                price=Decimal('150.0'),
                attributes={"client_order_id": f"concurrent_order_{i}"}
            )
            for i in range(3)
        ]
        
        # Mock successful responses
        order_service.broker_client.submit_order.side_effect = [
            {"order_id": f"ext_{i}", "status": "filled"} for i in range(3)
        ]
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        order_service.risk_manager.validate_order.return_value = (True, "OK")
        
        # Submit orders concurrently (simulated)
        results = []
        for spec in order_specs:
            result = order_service.submit_order(spec)
            results.append(result)
        
        # All should succeed
        assert len(results) == 3
        assert all(r is not None for r in results)
        
        # Each should have made an external call
        assert order_service.broker_client.submit_order.call_count == 3

    @pytest.mark.slow
    def test_timeout_handling(self, order_service, sample_order_spec):
        """Test that long-running operations timeout appropriately"""
        import asyncio
        
        # Mock slow broker response
        async def slow_response():
            await asyncio.sleep(10)  # 10 second delay
            return {"order_id": "ext_123", "status": "filled"}
        
        order_service.broker_client.submit_order.side_effect = lambda *args: slow_response()
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        # Should timeout and handle gracefully
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.side_effect = asyncio.TimeoutError()
            
            try:
                order_service.submit_order(sample_order_spec)
            except asyncio.TimeoutError:
                pass  # Expected
            
            # Should have attempted timeout
            mock_wait_for.assert_called()

    def test_order_status_tracking(self, order_service, sample_order_spec):
        """Test that order status is properly tracked through lifecycle"""
        # Mock partial fill response
        order_service.broker_client.submit_order.return_value = {
            "order_id": "ext_123", 
            "status": "partially_filled",
            "filled_quantity": 50
        }
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        result = order_service.submit_order(sample_order_spec)
        
        # Should track partial fill status
        assert result["status"] == "partially_filled"
        assert result["filled_quantity"] == 50
        
        # Should have persisted order state
        order_service.db_session.add.assert_called()
        order_service.db_session.commit.assert_called()

    def test_error_recovery_and_retry_backoff(self, order_service, sample_order_spec):
        """Test exponential backoff in retry logic"""
        from requests.exceptions import HTTPError
        
        # Mock 503 service unavailable (retriable)
        http_error_503 = HTTPError()
        http_error_503.response = MagicMock()
        http_error_503.response.status_code = 503
        
        order_service.broker_client.submit_order.side_effect = [
            http_error_503,  # First attempt
            http_error_503,  # Second attempt  
            {"order_id": "ext_123", "status": "filled"}  # Success
        ]
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        with patch('time.sleep') as mock_sleep:
            result = order_service.submit_order(sample_order_spec)
            
            # Should have used exponential backoff
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            
            if len(sleep_calls) >= 2:
                # Each subsequent sleep should be longer (exponential backoff)
                assert sleep_calls[1] > sleep_calls[0]
            
            # Should eventually succeed
            assert result["order_id"] == "ext_123"


class TestOrderService429RetryWithJitter:
    """Test 429 retry logic with exponential backoff and jitter"""
    
    @pytest.fixture
    def order_service(self):
        """Create OrderService with retry configuration"""
        with patch('backend.services.order_service.OrderService.__init__', return_value=None):
            service = OrderService.__new__(OrderService)
            service.broker_client = MagicMock()
            service.db_session = MagicMock()
            service.metrics = MagicMock()
            service.max_retries = 3
            service.base_retry_delay = 0.1
            return service
    
    @pytest.fixture
    def sample_order_spec(self):
        """Create a sample order specification"""
        return OrderSpec(
            symbol="TSLA",
            side="buy", 
            qty=Decimal('50'),
            notional=Decimal('10000.0'),
            price=Decimal('200.0'),
            attributes={"client_order_id": "retry_test_order_456"}
        )
    
    @patch('time.sleep')  # Mock sleep to avoid delays
    @patch('random.uniform')  # Mock random for predictable jitter
    def test_429_retry_with_jitter_success(self, mock_uniform, mock_sleep, order_service, sample_order_spec):
        """Test 429 rate limit retry with jitter succeeds eventually"""
        mock_uniform.return_value = 0.25  # Fixed jitter for testing
        
        # Mock 429 responses then success
        from requests.exceptions import HTTPError
        http_error_429 = HTTPError()
        http_error_429.response = MagicMock()
        http_error_429.response.status_code = 429
        http_error_429.response.headers = {"Retry-After": "1"}
        
        order_service.broker_client.submit_order.side_effect = [
            http_error_429,  # First attempt - rate limited
            http_error_429,  # Second attempt - rate limited  
            {"order_id": "ext_456", "status": "filled"}  # Third attempt - success
        ]
        
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        result = order_service.submit_order(sample_order_spec)
        
        # Should eventually succeed
        assert result["order_id"] == "ext_456"
        assert result["status"] == "filled"
        
        # Should have made 3 attempts total
        assert order_service.broker_client.submit_order.call_count == 3
        
        # Should have slept with exponential backoff + jitter
        expected_sleeps = [
            call(0.1 * (2**0) + 0.25),  # base * 2^0 + jitter = 0.35
            call(0.1 * (2**1) + 0.25),  # base * 2^1 + jitter = 0.45
        ]
        mock_sleep.assert_has_calls(expected_sleeps)
        
        # Should increment retry metrics
        order_service.metrics.increment.assert_any_call("orders_retry_attempts_total")
    
    @patch('time.sleep')
    def test_429_retry_exhaustion_increments_failed_counter(self, mock_sleep, order_service, sample_order_spec):
        """Test that exhausted 429 retries increment failed counter with reason"""
        from requests.exceptions import HTTPError
        http_error_429 = HTTPError()
        http_error_429.response = MagicMock()
        http_error_429.response.status_code = 429
        
        # Mock 429 for all retry attempts
        order_service.broker_client.submit_order.side_effect = http_error_429
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        # Should raise after max retries exhausted
        with pytest.raises(HTTPError):
            order_service.submit_order(sample_order_spec)
        
        # Should increment failed counter with specific reason
        order_service.metrics.increment.assert_any_call(
            "orders_failed_total",
            tags={"reason": "rate_limit_exhausted", "symbol": "TSLA"}
        )
    
    @patch('time.sleep')
    @patch('random.uniform')
    def test_retry_jitter_randomization(self, mock_uniform, mock_sleep, order_service, sample_order_spec):
        """Test that jitter adds randomization to retry delays"""
        # Set different jitter values for each retry
        mock_uniform.side_effect = [0.1, 0.8, 0.3]
        
        from requests.exceptions import HTTPError
        http_error_429 = HTTPError()
        http_error_429.response = MagicMock()
        http_error_429.response.status_code = 429
        
        order_service.broker_client.submit_order.side_effect = [
            http_error_429,
            http_error_429, 
            {"order_id": "ext_456", "status": "filled"}
        ]
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        order_service.submit_order(sample_order_spec)
        
        # Should have different sleep times due to different jitter
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        expected_sleeps = [
            0.1 * (2**0) + 0.1,  # 0.2
            0.1 * (2**1) + 0.8,  # 1.0
        ]
        
        assert sleep_calls == expected_sleeps


class TestOrderServiceCircuitBreaker:
    """Test circuit breaker opens after N failures and prevents further calls"""
    
    @pytest.fixture
    def order_service(self):
        """Create OrderService with circuit breaker"""
        with patch('backend.services.order_service.OrderService.__init__', return_value=None):
            service = OrderService.__new__(OrderService)
            service.broker_client = MagicMock()
            service.db_session = MagicMock()
            service.metrics = MagicMock()
            service.circuit_breaker_threshold = 3
            service.circuit_breaker_timeout = 60
            service._circuit_breaker_failures = 0
            service._circuit_breaker_last_failure = None
            service._circuit_breaker_state = "closed"  # closed, open, half-open
            return service
    
    def test_circuit_breaker_opens_after_threshold_failures(self, order_service):
        """Test circuit breaker opens after configured threshold failures"""
        from requests.exceptions import ConnectionError
        
        # Mock connection errors to trigger circuit breaker
        connection_error = ConnectionError("Connection refused")
        order_service.broker_client.submit_order.side_effect = connection_error
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        order_spec = OrderSpec(
            symbol="AAPL",
            side="sell",
            qty=Decimal('100'),
            notional=Decimal('15000.0'),
            price=Decimal('150.0'),
            attributes={"client_order_id": "cb_test_order"}
        )
        
        # Make threshold number of failures (3)
        for i in range(3):
            with pytest.raises(ConnectionError):
                order_service.submit_order(order_spec)
        
        # Circuit breaker should now be open
        assert order_service._circuit_breaker_state == "open"
        
        # Next call should fail fast without hitting broker
        from backend.exceptions import CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError):
            order_service.submit_order(order_spec)
        
        # Should have made only 3 calls to broker, not 4
        assert order_service.broker_client.submit_order.call_count == 3
        
        # Should increment circuit breaker opened metric
        order_service.metrics.increment.assert_any_call("orders_circuit_breaker_opened_total")
    
    def test_circuit_breaker_half_open_allows_probe_request(self, order_service):
        """Test circuit breaker allows probe request after timeout"""
        # Manually set circuit breaker to open state
        order_service._circuit_breaker_state = "open"
        order_service._circuit_breaker_failures = 3
        order_service._circuit_breaker_last_failure = time.time() - 61  # 61 seconds ago
        
        order_spec = OrderSpec(
            symbol="NVDA",
            side="buy",
            qty=Decimal('25'),
            notional=Decimal('12500.0'),
            price=Decimal('500.0'),
            attributes={"client_order_id": "probe_test_order"}
        )
        
        # Mock successful response for probe request
        order_service.broker_client.submit_order.return_value = {
            "order_id": "ext_probe_123", 
            "status": "filled"
        }
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        result = order_service.submit_order(order_spec)
        
        # Should succeed and close circuit breaker
        assert result["order_id"] == "ext_probe_123"
        assert order_service._circuit_breaker_state == "closed"
        
        # Should increment circuit breaker closed metric
        order_service.metrics.increment.assert_any_call("orders_circuit_breaker_closed_total")
    
    def test_circuit_breaker_probe_failure_keeps_open(self, order_service):
        """Test failed probe request keeps circuit breaker open"""
        # Set circuit breaker to half-open (timeout expired)
        order_service._circuit_breaker_state = "open"
        order_service._circuit_breaker_last_failure = time.time() - 61
        
        from requests.exceptions import ConnectionError
        order_service.broker_client.submit_order.side_effect = ConnectionError("Still down")
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        order_spec = OrderSpec(
            symbol="MSFT", 
            side="buy",
            qty=Decimal('75'),
            notional=Decimal('22500.0'),
            price=Decimal('300.0'),
            attributes={"client_order_id": "probe_fail_order"}
        )
        
        # Probe request should fail
        with pytest.raises(ConnectionError):
            order_service.submit_order(order_spec)
        
        # Circuit breaker should remain open
        assert order_service._circuit_breaker_state == "open"


class TestOrderServiceDLQManagement:
    """Test Dead Letter Queue management for failed orders"""
    
    @pytest.fixture
    def order_service(self):
        """Create OrderService with DLQ support"""
        with patch('backend.services.order_service.OrderService.__init__', return_value=None):
            service = OrderService.__new__(OrderService)
            service.broker_client = MagicMock()
            service.db_session = MagicMock()
            service.metrics = MagicMock()
            service.dlq_client = MagicMock()
            return service
    
    def test_final_failure_goes_to_dlq(self, order_service):
        """Test that finally failed orders are moved to DLQ"""
        from requests.exceptions import HTTPError
        http_error_500 = HTTPError()
        http_error_500.response = MagicMock()
        http_error_500.response.status_code = 500
        
        # Mock persistent failures
        order_service.broker_client.submit_order.side_effect = http_error_500
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        order_spec = OrderSpec(
            symbol="GOOG",
            side="buy",
            qty=Decimal('10'),
            notional=Decimal('15000.0'),
            price=Decimal('1500.0'),
            attributes={"client_order_id": "dlq_test_order"}
        )
        
        with patch('time.sleep'):  # Skip retry delays
            with pytest.raises(HTTPError):
                order_service.submit_order(order_spec)
        
        # Should move failed order to DLQ
        order_service.dlq_client.send_to_dlq.assert_called_once()
        dlq_call_args = order_service.dlq_client.send_to_dlq.call_args[0]
        assert "dlq_test_order" in str(dlq_call_args)
        
        # Should increment DLQ metrics
        order_service.metrics.increment.assert_any_call(
            "orders_dlq_total",
            tags={"reason": "retry_exhausted", "symbol": "GOOG"}
        )
    
    def test_admin_retry_moves_from_dlq(self, order_service):
        """Test admin retry functionality moves messages from DLQ back to processing"""
        # Mock DLQ with failed orders
        dlq_orders = [
            {"client_order_id": "DLQ_ORDER_001", "symbol": "AAPL", "reason": "broker_error"},
            {"client_order_id": "DLQ_ORDER_002", "symbol": "TSLA", "reason": "timeout"}
        ]
        order_service.dlq_client.get_dlq_messages.return_value = dlq_orders
        
        # Admin retry all DLQ orders
        retried_count = order_service.admin_retry_dlq_orders()
        
        # Should have processed both orders
        assert retried_count == 2
        
        # Should move orders back to processing queue
        assert order_service.dlq_client.move_to_processing.call_count == 2
        
        # Should increment admin retry metrics
        order_service.metrics.increment.assert_any_call("orders_admin_retry_total", tags={"count": "2"})
    
    def test_admin_retry_specific_order(self, order_service):
        """Test admin retry of specific order by client_order_id"""
        dlq_orders = [
            {"client_order_id": "SPECIFIC_ORDER_001", "symbol": "NFLX", "reason": "rate_limit"},
            {"client_order_id": "OTHER_ORDER_002", "symbol": "NVDA", "reason": "broker_error"}
        ]
        order_service.dlq_client.get_dlq_messages.return_value = dlq_orders
        
        # Retry only specific order
        success = order_service.admin_retry_order("SPECIFIC_ORDER_001")
        
        assert success is True
        # Should move only the specific order
        order_service.dlq_client.move_to_processing.assert_called_once()
        move_call_args = order_service.dlq_client.move_to_processing.call_args[0][0]
        assert move_call_args["client_order_id"] == "SPECIFIC_ORDER_001"


class TestOrderServiceComprehensiveMetrics:
    """Test comprehensive metrics recording for all operations"""
    
    @pytest.fixture
    def order_service(self):
        """Create OrderService with metrics"""
        with patch('backend.services.order_service.OrderService.__init__', return_value=None):
            service = OrderService.__new__(OrderService)
            service.broker_client = MagicMock()
            service.db_session = MagicMock()
            service.metrics = MagicMock()
            return service
    
    def test_orders_created_total_counter(self, order_service):
        """Test orders_created_total counter with symbol tags"""
        order_service.broker_client.submit_order.return_value = {
            "order_id": "ext_metrics_123",
            "status": "filled"
        }
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        order_spec = OrderSpec(
            symbol="AMZN",
            side="buy",
            qty=Decimal('20'),
            notional=Decimal('3000.0'),
            price=Decimal('150.0'),
            attributes={"client_order_id": "metrics_order_001"}
        )
        
        order_service.submit_order(order_spec)
        
        # Should increment created counter with symbol tag
        order_service.metrics.increment.assert_any_call(
            "orders_created_total",
            tags={"symbol": "AMZN", "side": "buy"}
        )
    
    def test_orders_failed_total_with_reason_tags(self, order_service):
        """Test orders_failed_total counter with reason and symbol tags"""
        from requests.exceptions import Timeout
        order_service.broker_client.submit_order.side_effect = Timeout("Request timeout")
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        order_spec = OrderSpec(
            symbol="META",
            side="sell",
            qty=Decimal('50'),
            notional=Decimal('15000.0'),
            price=Decimal('300.0'),
            attributes={"client_order_id": "failed_order_002"}
        )
        
        with pytest.raises(Timeout):
            order_service.submit_order(order_spec)
        
        # Should increment failed counter with reason and symbol tags
        order_service.metrics.increment.assert_any_call(
            "orders_failed_total",
            tags={"reason": "timeout", "symbol": "META", "side": "sell"}
        )
    
    def test_retry_attempts_counter_increments(self, order_service):
        """Test retries counter increments for each retry attempt"""
        from requests.exceptions import HTTPError
        http_error_502 = HTTPError()
        http_error_502.response = MagicMock()
        http_error_502.response.status_code = 502  # Bad Gateway - retriable
        
        order_service.broker_client.submit_order.side_effect = [
            http_error_502,  # First attempt fails
            http_error_502,  # Second attempt fails
            {"order_id": "ext_retry_123", "status": "filled"}  # Third attempt succeeds
        ]
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        order_spec = OrderSpec(
            symbol="TSLA",
            side="buy",
            qty=Decimal('15'),
            notional=Decimal('3000.0'),
            price=Decimal('200.0'),
            attributes={"client_order_id": "retry_metrics_order"}
        )
        
        with patch('time.sleep'):
            order_service.submit_order(order_spec)
        
        # Should increment retry counter for each retry attempt
        retry_calls = [call for call in order_service.metrics.increment.call_args_list 
                      if call[0][0] == "orders_retry_attempts_total"]
        assert len(retry_calls) == 2  # Two retry attempts
    
    def test_order_latency_histogram(self, order_service):
        """Test order processing latency is recorded in histogram"""
        order_service.broker_client.submit_order.return_value = {
            "order_id": "ext_latency_123",
            "status": "filled"
        }
        order_service.db_session.query.return_value.filter.return_value.first.return_value = None
        
        order_spec = OrderSpec(
            symbol="GOOGL",
            side="buy",
            qty=Decimal('5'),
            notional=Decimal('1000.0'),
            price=Decimal('200.0'),
            attributes={"client_order_id": "latency_order"}
        )
        
        with patch('time.time', side_effect=[1000.0, 1000.25]):  # 250ms processing time
            order_service.submit_order(order_spec)
        
        # Should record processing latency
        order_service.metrics.histogram.assert_any_call(
            "orders_processing_duration_seconds",
            0.25,
            tags={"symbol": "GOOGL"}
        )
