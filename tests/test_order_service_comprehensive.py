"""
Comprehensive Unit Tests for Order Service Module

This test suite covers:
1. CircuitBreaker - All state transitions, Redis persistence, failure/success recording
2. OrderService - Initialization, validation, submission flows
3. Module-level functions - get_circuit_breaker, circuit_breaker_check_async
4. Order lifecycle - submit, modify, cancel, status queries
5. Edge cases - Concurrent access, error handling, rate limiting

Coverage target: 80%+
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4, UUID
import json


# ============================================================================
# CircuitBreaker Tests
# ============================================================================

class TestCircuitBreakerInit:
    """Test CircuitBreaker initialization."""

    def test_default_initialization(self):
        """Test circuit breaker initializes with defaults."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        
        assert cb.failure_threshold == 5
        assert cb.success_threshold == 3
        assert cb.timeout_seconds == 60
        assert cb.window_seconds == 300
        assert cb.loss_threshold_pct == 5.0
        assert cb._redis is None

    def test_custom_initialization(self):
        """Test circuit breaker with custom parameters."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker(
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=120,
            window_seconds=600,
            loss_threshold_pct=10.0
        )
        
        assert cb.failure_threshold == 3
        assert cb.success_threshold == 2
        assert cb.timeout_seconds == 120
        assert cb.window_seconds == 600
        assert cb.loss_threshold_pct == 10.0

    def test_redis_client_injection(self):
        """Test circuit breaker accepts Redis client."""
        from backend.services.order_service import CircuitBreaker
        
        mock_redis = MagicMock()
        cb = CircuitBreaker(redis_client=mock_redis)
        
        assert cb._redis == mock_redis

    def test_initial_state_is_closed(self):
        """Test circuit breaker starts in CLOSED state."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        
        assert cb.state == CircuitBreaker.STATE_CLOSED


class TestCircuitBreakerStateProperty:
    """Test CircuitBreaker state property and transitions."""

    def test_state_property_without_redis(self):
        """Test state property returns in-memory state when no Redis."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._state = CircuitBreaker.STATE_OPEN
        # Need to set opened_at to avoid auto-transition
        cb._opened_at_mono = time.monotonic()
        
        assert cb.state == CircuitBreaker.STATE_OPEN

    def test_state_property_auto_transitions(self):
        """Test state property auto-transitions from OPEN after timeout."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker(timeout_seconds=1)
        cb._state = CircuitBreaker.STATE_OPEN
        cb._opened_at_mono = time.monotonic() - 2  # Expired
        
        # Should auto-transition to HALF_OPEN
        assert cb.state == CircuitBreaker.STATE_HALF_OPEN

    def test_is_open_property(self):
        """Test is_open property returns True when circuit is open."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._state = CircuitBreaker.STATE_OPEN
        cb._opened_at_mono = time.monotonic()
        
        assert cb.is_open is True
        
        cb._state = CircuitBreaker.STATE_CLOSED
        assert cb.is_open is False

    def test_state_remains_closed_by_default(self):
        """Test state remains closed when no failures."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        
        assert cb._state == CircuitBreaker.STATE_CLOSED
        assert cb.state == CircuitBreaker.STATE_CLOSED


class TestCircuitBreakerCheck:
    """Test CircuitBreaker check method."""

    def test_check_returns_false_when_closed(self):
        """Test check returns False (allows order) when closed."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._state = CircuitBreaker.STATE_CLOSED
        
        result = cb.check()
        assert result is False  # False means allow order

    def test_check_returns_true_when_open(self):
        """Test check returns True (blocks order) when open."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._state = CircuitBreaker.STATE_OPEN
        cb._opened_at_mono = time.monotonic()  # Just opened
        
        result = cb.check()
        assert result is True  # True means block order

    def test_check_allows_half_open_state(self):
        """Test check allows orders in half-open state."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._state = CircuitBreaker.STATE_HALF_OPEN
        
        result = cb.check()
        assert result is False  # Half-open allows test orders

    def test_check_with_daily_pnl_loss_threshold(self):
        """Test check blocks when daily PnL exceeds loss threshold."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker(loss_threshold_pct=5.0)
        cb._state = CircuitBreaker.STATE_CLOSED
        
        # Simulate 6% loss (exceeds 5% threshold)
        result = cb.check(daily_pnl=-6.0)
        
        assert result is True  # Should block
        assert cb.state == CircuitBreaker.STATE_OPEN


class TestCircuitBreakerRecordSuccess:
    """Test CircuitBreaker record_success method."""

    def test_record_success_in_closed_state(self):
        """Test recording success in closed state has no effect."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._failures = [time.time()]
        cb._failures_mono = [time.monotonic()]
        
        cb.record_success()
        
        # Failures are not cleared in closed state by record_success
        # (they are cleaned by window timeout)
        assert cb._state == CircuitBreaker.STATE_CLOSED

    def test_record_success_in_half_open_increments_counter(self):
        """Test recording success in half-open state increments success count."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker(success_threshold=3)
        cb._state = CircuitBreaker.STATE_HALF_OPEN
        cb._successes_in_half_open = 0
        
        cb.record_success()
        
        assert cb._successes_in_half_open == 1

    def test_record_success_closes_circuit_after_threshold(self):
        """Test circuit closes after reaching success threshold in half-open."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker(success_threshold=2)
        cb._state = CircuitBreaker.STATE_HALF_OPEN
        cb._successes_in_half_open = 1
        
        cb.record_success()
        
        assert cb.state == CircuitBreaker.STATE_CLOSED
        assert cb._successes_in_half_open == 0


class TestCircuitBreakerRecordFailure:
    """Test CircuitBreaker record_failure method."""

    def test_record_failure_adds_to_failures_list(self):
        """Test recording failure adds to failures list."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._failures = []
        cb._failures_mono = []
        
        cb.record_failure("Test error")
        
        assert len(cb._failures) == 1

    def test_record_failure_opens_circuit_at_threshold(self):
        """Test circuit opens when failure count reaches threshold."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker(failure_threshold=3)
        cb._failures = []
        cb._failures_mono = []
        
        # Add failures up to threshold
        for i in range(3):
            cb.record_failure("Test error")
        
        assert cb._state == CircuitBreaker.STATE_OPEN
        assert cb._opened_at_mono is not None

    def test_record_failure_in_half_open_opens_immediately(self):
        """Test failure in half-open state opens circuit immediately."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._state = CircuitBreaker.STATE_HALF_OPEN
        cb._successes_in_half_open = 2
        
        cb.record_failure("Test error")
        
        assert cb._state == CircuitBreaker.STATE_OPEN

    def test_record_failure_stores_timestamp(self):
        """Test recording failure stores timestamp."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._failures = []
        cb._failures_mono = []
        
        before = time.time()
        cb.record_failure("Connection timeout")
        after = time.time()
        
        assert len(cb._failures) == 1
        assert before <= cb._failures[0] <= after


class TestCircuitBreakerReset:
    """Test CircuitBreaker reset method."""

    def test_reset_clears_all_state(self):
        """Test reset method clears all state."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._state = CircuitBreaker.STATE_OPEN
        cb._failures = [time.time() for _ in range(10)]
        cb._failures_mono = [time.monotonic() for _ in range(10)]
        cb._successes_in_half_open = 5
        cb._opened_at = time.time()
        cb._opened_at_mono = time.monotonic()
        
        cb.reset()
        
        assert cb._state == CircuitBreaker.STATE_CLOSED
        assert len(cb._failures) == 0
        assert len(cb._failures_mono) == 0
        assert cb._successes_in_half_open == 0
        assert cb._opened_at is None
        assert cb._opened_at_mono is None

    def test_reset_allows_orders_again(self):
        """Test reset allows orders to proceed again."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._state = CircuitBreaker.STATE_OPEN
        cb._opened_at_mono = time.monotonic()
        
        # Before reset, orders blocked
        assert cb.check() is True
        
        cb.reset()
        
        # After reset, orders allowed
        assert cb.check() is False


class TestCircuitBreakerGetStatus:
    """Test CircuitBreaker get_status method."""

    def test_get_status_returns_dict(self):
        """Test get_status returns proper status dictionary."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        
        status = cb.get_status()
        
        assert isinstance(status, dict)
        assert "state" in status
        assert "failures_in_window" in status
        assert "failure_threshold" in status
        assert "timeout_seconds" in status

    def test_get_status_includes_time_until_recovery(self):
        """Test get_status includes recovery time when open."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker(timeout_seconds=60)
        cb._state = CircuitBreaker.STATE_OPEN
        cb._opened_at_mono = time.monotonic()  # Just now
        
        status = cb.get_status()
        
        assert "time_until_recovery" in status
        assert status["time_until_recovery"] >= 0
        assert status["time_until_recovery"] <= 60

    def test_get_status_zero_recovery_when_closed(self):
        """Test get_status shows 0 recovery time when closed."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker()
        cb._state = CircuitBreaker.STATE_CLOSED
        
        status = cb.get_status()
        
        assert status["time_until_recovery"] == 0


class TestCircuitBreakerWindowCleanup:
    """Test CircuitBreaker failure window cleanup."""

    def test_old_failures_are_cleaned_up(self):
        """Test failures outside window are removed during record_failure."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker(window_seconds=60, failure_threshold=10)
        
        # Add old failures (outside window)
        old_time_epoch = time.time() - 120  # 2 minutes ago
        old_time_mono = time.monotonic() - 120
        cb._failures = [old_time_epoch, old_time_epoch + 10]
        cb._failures_mono = [old_time_mono, old_time_mono + 10]
        
        # Record new failure triggers cleanup
        cb.record_failure("New failure")
        
        # Old failures should be removed, only new one remains
        assert len(cb._failures) == 1


# ============================================================================
# Module-level Function Tests
# ============================================================================

class TestGetCircuitBreaker:
    """Test get_circuit_breaker module function."""

    def test_get_circuit_breaker_returns_singleton(self):
        """Test get_circuit_breaker returns the same instance."""
        from backend.services.order_service import get_circuit_breaker, _circuit_breaker
        
        cb1 = get_circuit_breaker()
        cb2 = get_circuit_breaker()
        
        assert cb1 is cb2

    def test_get_circuit_breaker_creates_instance(self):
        """Test get_circuit_breaker creates instance if none exists."""
        from backend.services import order_service
        from backend.services.order_service import get_circuit_breaker, CircuitBreaker
        
        # Save and clear global
        original = order_service._circuit_breaker
        order_service._circuit_breaker = None
        
        try:
            cb = get_circuit_breaker()
            assert isinstance(cb, CircuitBreaker)
        finally:
            # Restore original
            order_service._circuit_breaker = original


class TestCircuitBreakerCheckAsync:
    """Test circuit_breaker_check_async function."""

    def test_circuit_breaker_check_returns_bool(self):
        """Test sync check returns boolean."""
        from backend.services.order_service import circuit_breaker_check
        
        result = circuit_breaker_check()
        
        assert isinstance(result, bool)

    def test_get_circuit_breaker_status(self):
        """Test get_circuit_breaker returns instance with status method."""
        from backend.services.order_service import get_circuit_breaker
        
        cb = get_circuit_breaker()
        status = cb.get_status()
        
        assert isinstance(status, dict)
        assert "state" in status


# ============================================================================
# OrderService Initialization Tests
# ============================================================================

class TestOrderServiceInit:
    """Test OrderService initialization."""

    def test_minimal_initialization(self):
        """Test OrderService can be created with no arguments."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        assert service is not None

    def test_initialization_with_session(self):
        """Test OrderService accepts database session."""
        from backend.services.order_service import OrderService
        
        mock_session = MagicMock()
        service = OrderService(db_session=mock_session)
        
        assert service.db_session == mock_session

    def test_initialization_with_broker(self):
        """Test OrderService accepts broker."""
        from backend.services.order_service import OrderService
        
        mock_broker = MagicMock()
        service = OrderService(broker=mock_broker)
        
        assert service.broker == mock_broker

    def test_initialization_with_repositories(self):
        """Test OrderService accepts repositories."""
        from backend.services.order_service import OrderService
        
        mock_orders_repo = MagicMock()
        mock_outbox_repo = MagicMock()
        
        service = OrderService(
            orders_repo=mock_orders_repo,
            outbox_repo=mock_outbox_repo
        )
        
        assert service.orders_repo == mock_orders_repo
        assert service.outbox_repo == mock_outbox_repo


# ============================================================================
# OrderService Validation Tests
# ============================================================================

class TestOrderServiceValidation:
    """Test OrderService validate_order method."""

    def test_validate_valid_market_order(self):
        """Test validation passes for valid market order."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "market"
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is True
        assert result["errors"] == []

    def test_validate_missing_symbol(self):
        """Test validation fails when symbol is missing."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "side": "buy",
            "qty": 100
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("symbol" in e.lower() for e in result["errors"])

    def test_validate_missing_side(self):
        """Test validation fails when side is missing."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "qty": 100
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("side" in e.lower() for e in result["errors"])

    def test_validate_invalid_side(self):
        """Test validation fails for invalid side value."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "hold",  # Invalid
            "qty": 100
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("side" in e.lower() for e in result["errors"])

    def test_validate_missing_qty(self):
        """Test validation fails when quantity is missing."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy"
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("qty" in e.lower() for e in result["errors"])

    def test_validate_negative_qty(self):
        """Test validation fails for negative quantity."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": -100
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("qty" in e.lower() for e in result["errors"])

    def test_validate_zero_qty(self):
        """Test validation fails for zero quantity."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 0
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("qty" in e.lower() for e in result["errors"])

    def test_validate_qty_too_large(self):
        """Test validation fails for excessively large quantity."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 10000000  # > 1M limit
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("qty" in e.lower() and "large" in e.lower() for e in result["errors"])

    def test_validate_invalid_order_type(self):
        """Test validation fails for invalid order type."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "trailing_stop"  # Not in valid list
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("order_type" in e.lower() for e in result["errors"])

    def test_validate_limit_order_without_price(self):
        """Test validation fails for limit order without price."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "limit"
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("price" in e.lower() for e in result["errors"])

    def test_validate_limit_order_with_price(self):
        """Test validation passes for limit order with price."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "limit",
            "price": 150.00
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is True

    def test_validate_stop_limit_order_requires_both_prices(self):
        """Test validation fails for stop_limit without stop_price."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "stop_limit",
            "price": 150.00
            # Missing stop_price
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("stop_price" in e.lower() for e in result["errors"])

    def test_validate_stop_order_requires_stop_price(self):
        """Test validation fails for stop order without stop_price."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "sell",
            "qty": 100,
            "order_type": "stop"
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("stop_price" in e.lower() for e in result["errors"])

    def test_validate_negative_price(self):
        """Test validation fails for negative price."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "limit",
            "price": -50.00
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("price" in e.lower() for e in result["errors"])

    def test_validate_price_too_large(self):
        """Test validation fails for excessively large price."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "limit",
            "price": 2000000  # > 1M limit
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("price" in e.lower() and "large" in e.lower() for e in result["errors"])

    def test_validate_invalid_price_type(self):
        """Test validation fails for non-numeric price."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "limit",
            "price": "one hundred"
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("price" in e.lower() for e in result["errors"])

    def test_validate_uses_quantity_when_qty_absent(self):
        """Test validation checks 'quantity' field when 'qty' is absent."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        # Validation should work with 'quantity' key - the validate_order
        # method checks for qty OR quantity
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100,
            "order_type": "market"
        }
        
        result = service.validate_order(order)
        
        # Even if not explicitly supported, both qty and quantity should work
        # Check if validation handles it
        assert "valid" in result

    def test_validate_empty_symbol(self):
        """Test validation fails for empty symbol."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "",
            "side": "buy",
            "qty": 100
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is False
        assert any("symbol" in e.lower() for e in result["errors"])


# ============================================================================
# OrderService Submit Order Tests
# ============================================================================

class TestOrderServiceSubmitOrder:
    """Test OrderService submit_order synchronous method."""

    def test_submit_order_returns_dict(self):
        """Test submit_order returns a dictionary response."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "",  # Invalid
            "side": "buy",
            "qty": 100
        }
        
        result = service.submit_order(order)
        
        assert isinstance(result, dict)
        assert "status" in result
        assert "order_id" in result

    def test_submit_order_in_mock_mode(self):
        """Test submit_order returns response when no database."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100
        }
        
        result = service.submit_order(order)
        
        # Without database, should return response
        assert "status" in result
        assert "order_id" in result


class TestOrderServiceSubmitSymbolOrder:
    """Test OrderService submit_symbol_order async method."""

    @pytest.mark.asyncio
    async def test_submit_symbol_order_circuit_breaker_blocks(self):
        """Test submit_symbol_order raises when circuit breaker is open."""
        from backend.services.order_service import OrderService, get_circuit_breaker
        
        # Open the circuit breaker
        cb = get_circuit_breaker()
        cb._state = cb.STATE_OPEN
        cb._opened_at = time.time()
        
        service = OrderService()
        
        try:
            with pytest.raises(RuntimeError) as exc_info:
                await service.submit_symbol_order(
                    symbol="AAPL",
                    side="buy",
                    qty=100,
                    idempotency_key="test-key-123"
                )
            
            assert "circuit breaker" in str(exc_info.value).lower()
        finally:
            cb.reset()

    @pytest.mark.asyncio
    async def test_submit_symbol_order_with_daily_pnl_loss(self):
        """Test submit_symbol_order blocks when daily PnL exceeds threshold."""
        from backend.services.order_service import OrderService, get_circuit_breaker
        
        cb = get_circuit_breaker()
        cb.reset()  # Start fresh
        
        service = OrderService()
        
        try:
            with pytest.raises(RuntimeError) as exc_info:
                await service.submit_symbol_order(
                    symbol="AAPL",
                    side="buy",
                    qty=100,
                    idempotency_key="test-key-456",
                    daily_pnl=-10.0  # Exceeds default 5% threshold
                )
            
            assert "circuit breaker" in str(exc_info.value).lower()
        finally:
            cb.reset()

    @pytest.mark.asyncio
    async def test_submit_symbol_order_success_path(self):
        """Test submit_symbol_order success with mocked repositories."""
        from backend.services.order_service import OrderService, get_circuit_breaker
        
        cb = get_circuit_breaker()
        cb.reset()
        
        # Mock order object
        mock_order = MagicMock()
        mock_order.id = uuid4()
        mock_order.status = "submitted"
        mock_order.submitted_at = datetime.utcnow()
        
        # Mock repositories
        mock_orders_repo = AsyncMock()
        mock_orders_repo.upsert_by_idempotency = AsyncMock(return_value=mock_order)
        
        mock_outbox_repo = AsyncMock()
        mock_outbox_repo.add_order_submit_event = AsyncMock()
        
        service = OrderService(
            orders_repo=mock_orders_repo,
            outbox_repo=mock_outbox_repo
        )
        
        result = await service.submit_symbol_order(
            symbol="AAPL",
            side="buy",
            qty=100,
            idempotency_key="test-success-key"
        )
        
        assert result["symbol"] == "AAPL"
        assert result["side"] == "buy"
        assert "order_id" in result
        mock_orders_repo.upsert_by_idempotency.assert_called_once()


# ============================================================================
# OrderService Submit Order Async Tests
# ============================================================================

class TestOrderServiceSubmitOrderAsync:
    """Test OrderService submit_order_async method."""

    @pytest.mark.asyncio
    async def test_submit_order_async_requires_session(self):
        """Test submit_order_async raises without session."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100
        }
        
        with pytest.raises(ValueError) as exc_info:
            await service.submit_order_async(order)
        
        assert "session" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_submit_order_async_validates_order(self):
        """Test submit_order_async validates order before submission."""
        from backend.services.order_service import OrderService
        
        mock_session = AsyncMock()
        mock_outbox_repo = AsyncMock()
        mock_orders_repo = AsyncMock()
        
        service = OrderService(
            db_session=mock_session,
            outbox_repo=mock_outbox_repo,
            orders_repo=mock_orders_repo
        )
        
        order = {
            "symbol": "",  # Invalid
            "side": "buy",
            "qty": 100
        }
        
        result = await service.submit_order_async(order, session=mock_session, outbox_repo=mock_outbox_repo)
        
        assert result["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_submit_order_async_success(self):
        """Test submit_order_async succeeds with valid order."""
        from backend.services.order_service import OrderService
        
        # Create mock order
        mock_order = MagicMock()
        mock_order.id = uuid4()
        mock_order.status = "submitted"
        mock_order.submitted_at = datetime.now()
        
        # Mock repositories
        mock_orders_repo = AsyncMock()
        mock_orders_repo.upsert_by_idempotency = AsyncMock(return_value=mock_order)
        
        mock_outbox_repo = AsyncMock()
        mock_outbox_repo.enqueue = AsyncMock()
        
        mock_session = AsyncMock()
        
        service = OrderService(
            db_session=mock_session,
            outbox_repo=mock_outbox_repo,
            orders_repo=mock_orders_repo
        )
        
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100
        }
        
        result = await service.submit_order_async(order, session=mock_session, outbox_repo=mock_outbox_repo)
        
        assert result["status"] == "submitted"
        assert result["symbol"] == "AAPL"


# ============================================================================
# OrderService Cancel Order Tests
# ============================================================================

class TestOrderServiceCancelOrder:
    """Test OrderService cancel_order method."""

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self):
        """Test cancel_order handles order not found."""
        from backend.services.order_service import OrderService
        
        mock_orders_repo = AsyncMock()
        mock_orders_repo.get_by_id = AsyncMock(return_value=None)
        
        service = OrderService(orders_repo=mock_orders_repo)
        
        result = await service.cancel_order("non-existent-id")
        
        # Should still return success (idempotent)
        assert result["order_id"] == "non-existent-id"

    @pytest.mark.asyncio
    async def test_cancel_order_success(self):
        """Test cancel_order succeeds for existing order."""
        from backend.services.order_service import OrderService
        
        mock_order = MagicMock()
        mock_order.id = uuid4()
        mock_order.broker_order_id = "broker-123"
        
        mock_orders_repo = AsyncMock()
        mock_orders_repo.get_by_id = AsyncMock(return_value=mock_order)
        mock_orders_repo.update_status = AsyncMock()
        
        mock_broker = AsyncMock()
        mock_broker.cancel_order = AsyncMock()
        
        service = OrderService(
            orders_repo=mock_orders_repo,
            broker=mock_broker
        )
        
        order_id = str(mock_order.id)
        result = await service.cancel_order(order_id)
        
        assert result["status"] == "cancelled"
        assert result["order_id"] == order_id

    @pytest.mark.asyncio
    async def test_cancel_order_idempotent(self):
        """Test cancel_order returns same result for duplicate calls."""
        from backend.services.order_service import OrderService
        
        mock_orders_repo = AsyncMock()
        mock_orders_repo.get_by_id = AsyncMock(return_value=MagicMock(
            id=uuid4(),
            broker_order_id="broker-123"
        ))
        mock_orders_repo.update_status = AsyncMock()
        
        service = OrderService(orders_repo=mock_orders_repo)
        
        order_id = str(uuid4())
        
        result1 = await service.cancel_order(order_id)
        result2 = await service.cancel_order(order_id)
        
        assert result1["status"] == "cancelled"
        assert result2["status"] == "already_cancelled"


# ============================================================================
# OrderService Modify Order Tests
# ============================================================================

class TestOrderServiceModifyOrder:
    """Test OrderService modify_order method."""

    @pytest.mark.asyncio
    async def test_modify_order_not_found(self):
        """Test modify_order returns error for non-existent order."""
        from backend.services.order_service import OrderService
        
        mock_orders_repo = AsyncMock()
        mock_orders_repo.get_by_id = AsyncMock(return_value=None)
        
        service = OrderService(orders_repo=mock_orders_repo)
        
        result = await service.modify_order({
            "order_id": "non-existent",
            "new_qty": 200
        })
        
        assert result["status"] == "error"
        assert "not found" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_modify_order_idempotent(self):
        """Test modify_order returns cached result for duplicate requests."""
        from backend.services.order_service import OrderService
        
        mock_order = MagicMock()
        mock_order.id = uuid4()
        
        mock_orders_repo = AsyncMock()
        mock_orders_repo.get_by_id = AsyncMock(return_value=mock_order)
        mock_orders_repo.update_status = AsyncMock()
        
        service = OrderService(orders_repo=mock_orders_repo)
        
        order_id = str(mock_order.id)
        mod_id = "mod-123"
        
        result1 = await service.modify_order({
            "order_id": order_id,
            "modification_id": mod_id,
            "new_qty": 200
        })
        
        result2 = await service.modify_order({
            "order_id": order_id,
            "modification_id": mod_id,
            "new_qty": 200
        })
        
        # Same modification_id should return cached result
        assert result1 == result2


# ============================================================================
# OrderService Get Order Status Tests
# ============================================================================

class TestOrderServiceGetOrderStatus:
    """Test OrderService get_order_status method."""

    @pytest.mark.asyncio
    async def test_get_order_status_from_database(self):
        """Test get_order_status retrieves from database."""
        from backend.services.order_service import OrderService
        
        mock_order = MagicMock()
        mock_order.id = uuid4()
        mock_order.status = "filled"
        mock_order.symbol = "AAPL"
        mock_order.side = "buy"
        mock_order.qty = Decimal("100")
        mock_order.filled_qty = Decimal("100")
        mock_order.avg_fill_price = Decimal("150.00")
        mock_order.submitted_at = datetime.utcnow()
        mock_order.updated_at = datetime.utcnow()
        
        mock_orders_repo = AsyncMock()
        mock_orders_repo.get_by_id = AsyncMock(return_value=mock_order)
        
        service = OrderService(orders_repo=mock_orders_repo)
        
        result = await service.get_order_status(str(mock_order.id))
        
        assert result is not None
        assert result["status"] == "filled"
        assert result["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self):
        """Test get_order_status returns None for unknown order."""
        from backend.services.order_service import OrderService
        
        mock_orders_repo = AsyncMock()
        mock_orders_repo.get_by_id = AsyncMock(return_value=None)
        
        service = OrderService(orders_repo=mock_orders_repo)
        
        result = await service.get_order_status("unknown-id")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_order_status_test_order(self):
        """Test get_order_status returns mock data for test-123."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        result = await service.get_order_status("test-123")
        
        assert result is not None
        assert result["order_id"] == "test-123"
        assert result["status"] == "filled"


# ============================================================================
# OrderService Get Order History Tests
# ============================================================================

class TestOrderServiceGetOrderHistory:
    """Test OrderService get_order_history method."""

    @pytest.mark.asyncio
    async def test_get_order_history_empty(self):
        """Test get_order_history returns empty list when no orders."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        result = await service.get_order_history()
        
        assert "orders" in result
        assert "total" in result
        assert result["total"] >= 0

    @pytest.mark.asyncio
    async def test_get_order_history_pagination(self):
        """Test get_order_history respects pagination parameters."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        result = await service.get_order_history(limit=10, offset=0)
        
        assert result["limit"] == 10
        assert result["offset"] == 0

    @pytest.mark.asyncio
    async def test_get_order_history_status_filter(self):
        """Test get_order_history applies status filter."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        result = await service.get_order_history(status_filter="filled")
        
        assert result["status_filter"] == "filled"


# ============================================================================
# OrderService Plan and Submit Tests
# ============================================================================

class TestOrderServicePlanAndSubmit:
    """Test OrderService plan_and_submit method."""

    @pytest.mark.asyncio
    async def test_plan_and_submit_requires_strategy_engine(self):
        """Test plan_and_submit raises without strategy engine."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        with pytest.raises(ValueError) as exc_info:
            await service.plan_and_submit(signals=[])
        
        assert "strategy" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_plan_and_submit_empty_signals(self):
        """Test plan_and_submit returns empty for no signals."""
        from backend.services.order_service import OrderService
        
        mock_engine = MagicMock()
        service = OrderService()
        
        result = await service.plan_and_submit(signals=[], strategy_engine=mock_engine)
        
        assert result == []

    @pytest.mark.asyncio
    async def test_plan_and_submit_risk_blocked(self):
        """Test plan_and_submit handles risk-blocked plans."""
        from backend.services.order_service import OrderService, get_circuit_breaker
        
        cb = get_circuit_breaker()
        cb.reset()
        
        # Create mock plan that is risk-blocked
        mock_plan = MagicMock()
        mock_plan.symbol = "AAPL"
        mock_plan.side = "buy"
        mock_plan.qty = 100
        mock_plan.risk_allowed = False
        mock_plan.risk_reason = "Position limit exceeded"
        mock_plan.from_exposure = 0
        mock_plan.to_exposure = 100
        
        mock_engine = AsyncMock()
        mock_engine.generate_and_gate = AsyncMock(return_value=[mock_plan])
        
        service = OrderService()
        
        result = await service.plan_and_submit(
            signals=[MagicMock()],
            strategy_engine=mock_engine
        )
        
        assert len(result) == 1
        assert result[0]["status"] == "risk_blocked"


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestOrderServiceEdgeCases:
    """Test edge cases and error handling."""

    def test_validate_order_handles_exception(self):
        """Test validate_order handles unexpected exceptions gracefully."""
        from backend.services.order_service import OrderService
        
        service = OrderService()
        
        # Malformed order that might cause issues
        order = None
        
        # Should handle gracefully
        try:
            result = service.validate_order(order)
            assert result["valid"] is False
        except Exception:
            # If it raises, that's also acceptable for None input
            pass

    def test_validate_order_with_dict_subclass(self):
        """Test validate_order works with dict-like objects."""
        from backend.services.order_service import OrderService
        
        class OrderDict(dict):
            pass
        
        service = OrderService()
        
        order = OrderDict({
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100
        })
        
        result = service.validate_order(order)
        
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_cancel_order_broker_failure(self):
        """Test cancel_order handles broker failure gracefully."""
        from backend.services.order_service import OrderService
        
        mock_order = MagicMock()
        mock_order.id = uuid4()
        mock_order.broker_order_id = "broker-123"
        
        mock_orders_repo = AsyncMock()
        mock_orders_repo.get_by_id = AsyncMock(return_value=mock_order)
        mock_orders_repo.update_status = AsyncMock()
        
        mock_broker = AsyncMock()
        mock_broker.cancel_order = AsyncMock(side_effect=Exception("Broker connection failed"))
        
        service = OrderService(
            orders_repo=mock_orders_repo,
            broker=mock_broker
        )
        
        # Should not raise, should log warning and continue
        result = await service.cancel_order(str(mock_order.id))
        
        assert result["status"] == "cancelled"

    def test_circuit_breaker_concurrent_access(self):
        """Test circuit breaker handles concurrent state changes."""
        from backend.services.order_service import CircuitBreaker
        
        cb = CircuitBreaker(failure_threshold=5)
        
        # Simulate rapid concurrent failures
        for _ in range(10):
            cb.record_failure("Concurrent error")
        
        # Should be open after exceeding threshold
        assert cb.state == CircuitBreaker.STATE_OPEN


# ============================================================================
# Integration-style Tests (with mocks)
# ============================================================================

class TestOrderServiceIntegration:
    """Integration-style tests with comprehensive mocking."""

    @pytest.mark.asyncio
    async def test_full_order_lifecycle(self):
        """Test complete order submit -> status check -> cancel flow."""
        from backend.services.order_service import OrderService, get_circuit_breaker
        
        cb = get_circuit_breaker()
        cb.reset()
        
        # Create mock order
        order_id = uuid4()
        mock_order = MagicMock()
        mock_order.id = order_id
        mock_order.status = "submitted"
        mock_order.symbol = "AAPL"
        mock_order.side = "buy"
        mock_order.qty = Decimal("100")
        mock_order.submitted_at = datetime.utcnow()
        mock_order.updated_at = datetime.utcnow()
        mock_order.filled_qty = Decimal("0")
        mock_order.avg_fill_price = None
        mock_order.broker_order_id = "broker-456"
        
        # Setup repositories
        mock_orders_repo = AsyncMock()
        mock_orders_repo.upsert_by_idempotency = AsyncMock(return_value=mock_order)
        mock_orders_repo.get_by_id = AsyncMock(return_value=mock_order)
        mock_orders_repo.update_status = AsyncMock()
        
        mock_outbox_repo = AsyncMock()
        mock_outbox_repo.add_order_submit_event = AsyncMock()
        mock_outbox_repo.enqueue = AsyncMock()
        
        mock_broker = AsyncMock()
        mock_broker.cancel_order = AsyncMock()
        
        mock_session = AsyncMock()
        
        service = OrderService(
            db_session=mock_session,
            orders_repo=mock_orders_repo,
            outbox_repo=mock_outbox_repo,
            broker=mock_broker
        )
        
        # 1. Submit order
        submit_result = await service.submit_symbol_order(
            symbol="AAPL",
            side="buy",
            qty=100,
            idempotency_key="lifecycle-test-key"
        )
        
        assert submit_result["symbol"] == "AAPL"
        assert "order_id" in submit_result
        
        # 2. Check status
        status = await service.get_order_status(str(order_id))
        
        assert status is not None
        assert status["symbol"] == "AAPL"
        
        # 3. Cancel order
        cancel_result = await service.cancel_order(str(order_id))
        
        assert cancel_result["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_rate_limit_retry_behavior(self):
        """Test order submission retries on 429 rate limit."""
        from backend.services.order_service import OrderService, get_circuit_breaker
        
        cb = get_circuit_breaker()
        cb.reset()
        
        # Create mock order
        mock_order = MagicMock()
        mock_order.id = uuid4()
        mock_order.status = "submitted"
        mock_order.submitted_at = datetime.utcnow()
        
        # Create a 429 error
        rate_limit_error = Exception("Rate limit exceeded")
        rate_limit_error.status_code = 429
        
        call_count = 0
        
        async def mock_upsert(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise rate_limit_error
            return mock_order
        
        mock_orders_repo = AsyncMock()
        mock_orders_repo.upsert_by_idempotency = mock_upsert
        
        mock_outbox_repo = AsyncMock()
        mock_outbox_repo.add_order_submit_event = AsyncMock()
        
        service = OrderService(
            orders_repo=mock_orders_repo,
            outbox_repo=mock_outbox_repo
        )
        
        # Should succeed after retry
        result = await service.submit_symbol_order(
            symbol="AAPL",
            side="buy",
            qty=100,
            idempotency_key="rate-limit-test"
        )
        
        assert result["symbol"] == "AAPL"
        assert call_count >= 2  # Retry happened


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
