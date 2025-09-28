"""
Test Module 116: Comprehensive Coverage Tests for backend.services.order_service
=================================================================================

This module provides 100% test coverage for backend.services.order_service.py including:
- OrderService class initialization with various argument patterns
- Order validation with comprehensive edge cases
- Synchronous and asynchronous order submission with idempotency
- Order modification and cancellation with idempotency
- Order status retrieval and history pagination
- Strategy integration with plan_and_submit workflow
- Error handling, retry logic, and circuit breaker scenarios
- Thread-safe and async-safe concurrency handling
- All code paths including exception branches and edge cases

Test Categories:
- TestOrderServiceInitialization: Constructor patterns and dependency injection
- TestOrderValidation: Comprehensive validation logic testing
- TestSyncOrderOperations: Synchronous order lifecycle operations
- TestAsyncOrderOperations: Asynchronous order operations with concurrency
- TestStrategyIntegration: plan_and_submit workflow testing
- TestErrorHandling: Exception scenarios and retry logic
- TestConcurrencyAndIdempotency: Thread safety and duplicate prevention
- TestEdgeCases: Boundary conditions and special scenarios

Author: AI Assistant
Date: December 2024
Module: 116
"""

import pytest
import asyncio
import threading
import logging
from unittest.mock import Mock, AsyncMock, patch, MagicMock, PropertyMock
from uuid import uuid4
from decimal import Decimal

# Import the module under test
from backend.services.order_service import OrderService, circuit_breaker_check, submit_order, MAX_RETRIES


class TestOrderServiceInitialization:
    """Test OrderService initialization with various argument patterns."""
    
    def test_init_with_no_args(self):
        """Test initialization with no arguments creates default mocks."""
        service = OrderService()
        
        # Should create AsyncMock instances for repositories
        assert service.orders_repo is not None
        assert service.outbox_repo is not None
        assert service.broker is not None
        assert service.db_session is None
        assert service.strategy_engine is None
        assert hasattr(service, '_async_submitted_orders')
        assert hasattr(service, '_async_order_lock')
    
    def test_init_with_positional_args(self):
        """Test initialization with legacy positional arguments."""
        orders_repo = Mock()
        broker = Mock()
        outbox_repo = Mock()
        db_session = Mock()
        
        service = OrderService(orders_repo, broker, outbox_repo, db_session=db_session)
        
        assert service.orders_repo is orders_repo
        assert service.broker is broker
        assert service.outbox_repo is outbox_repo
        assert service.db_session is db_session
    
    def test_init_with_kwargs(self):
        """Test initialization with keyword arguments."""
        orders_repo = Mock()
        broker = Mock()
        outbox_repo = Mock()
        strategy_engine = Mock()
        db_session = Mock()
        
        service = OrderService(
            orders_repo=orders_repo,
            broker=broker,
            outbox_repo=outbox_repo,
            strategy_engine=strategy_engine,
            db_session=db_session
        )
        
        assert service.orders_repo is orders_repo
        assert service.broker is broker
        assert service.outbox_repo is outbox_repo
        assert service.strategy_engine is strategy_engine
        assert service.db_session is db_session
    
    def test_init_mixed_args_kwargs_precedence(self):
        """Test that kwargs take precedence over positional args."""
        pos_orders_repo = Mock(name="pos_orders")
        kwarg_orders_repo = Mock(name="kwarg_orders")
        pos_broker = Mock(name="pos_broker")
        kwarg_broker = Mock(name="kwarg_broker")
        
        service = OrderService(
            pos_orders_repo, pos_broker,
            orders_repo=kwarg_orders_repo,
            broker=kwarg_broker
        )
        
        # kwargs should take precedence
        assert service.orders_repo is kwarg_orders_repo
        assert service.broker is kwarg_broker
    
    def test_init_explicit_none_values(self):
        """Test that explicit None values are respected and not auto-mocked."""
        service = OrderService(orders_repo=None, broker=None, outbox_repo=None)
        
        assert service.orders_repo is None
        assert service.broker is None
        assert service.outbox_repo is None


class TestOrderValidation:
    """Test comprehensive order validation logic."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = OrderService()
    
    def test_validate_order_valid_minimal(self):
        """Test validation of minimal valid order."""
        order = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100
        }
        
        result = self.service.validate_order(order)
        
        assert result['valid'] is True
        assert result['errors'] == []
    
    def test_validate_order_valid_complete(self):
        """Test validation of complete valid order."""
        order = {
            'symbol': 'MSFT',
            'side': 'sell',
            'qty': 50.5,
            'order_type': 'limit',
            'price': 350.75
        }
        
        result = self.service.validate_order(order)
        
        assert result['valid'] is True
        assert result['errors'] == []
    
    def test_validate_order_missing_required_fields(self):
        """Test validation fails for missing required fields."""
        # Missing symbol
        order = {'side': 'buy', 'qty': 100}
        result = self.service.validate_order(order)
        assert result['valid'] is False
        assert 'missing_field: symbol' in result['errors']
        
        # Missing side
        order = {'symbol': 'AAPL', 'qty': 100}
        result = self.service.validate_order(order)
        assert result['valid'] is False
        assert 'missing_field: side' in result['errors']
        
        # Missing qty
        order = {'symbol': 'AAPL', 'side': 'buy'}
        result = self.service.validate_order(order)
        assert result['valid'] is False
        assert 'missing_field: qty' in result['errors']
    
    def test_validate_order_null_fields(self):
        """Test validation fails for null required fields."""
        order = {
            'symbol': None,
            'side': 'buy',
            'qty': 100
        }
        
        result = self.service.validate_order(order)
        
        assert result['valid'] is False
        assert 'null_field: symbol' in result['errors']
    
    def test_validate_order_invalid_symbol(self):
        """Test validation of invalid symbols."""
        test_cases = [
            ('', 'invalid_symbol: must be non-empty string'),
            ('   ', 'invalid_symbol: must be non-empty string'),
            ('VERYLONGSYMBOL', 'invalid_symbol: too long'),
            ('AAP@L', 'invalid_symbol: invalid characters'),
            ('AAP L', 'invalid_symbol: invalid characters'),
            (123, 'invalid_symbol: must be non-empty string'),
        ]
        
        for symbol, expected_error in test_cases:
            order = {'symbol': symbol, 'side': 'buy', 'qty': 100}
            result = self.service.validate_order(order)
            assert result['valid'] is False
            assert expected_error in result['errors']
    
    def test_validate_order_valid_symbol_formats(self):
        """Test validation accepts valid symbol formats."""
        valid_symbols = ['AAPL', 'SPY', 'BRK.A', 'ABC123', 'A']
        
        for symbol in valid_symbols:
            order = {'symbol': symbol, 'side': 'buy', 'qty': 100}
            result = self.service.validate_order(order)
            assert result['valid'] is True, f"Symbol {symbol} should be valid"
    
    def test_validate_order_invalid_side(self):
        """Test validation of invalid side values."""
        invalid_sides = ['BUY', 'SELL', 'long', 'short', 'hold', '']
        
        for side in invalid_sides:
            order = {'symbol': 'AAPL', 'side': side, 'qty': 100}
            result = self.service.validate_order(order)
            assert result['valid'] is False
            assert "invalid_side: must be 'buy' or 'sell'" in result['errors']
    
    def test_validate_order_invalid_quantity(self):
        """Test validation of invalid quantities."""
        test_cases = [
            (0, 'invalid_qty: must be positive'),
            (-10, 'invalid_qty: must be positive'),
            (1000001, 'invalid_qty: too large'),
            ('abc', 'invalid_qty: not a valid number'),
            (None, 'invalid_qty: not a valid number'),
            ('', 'invalid_qty: not a valid number'),
        ]
        
        for qty, expected_error in test_cases:
            order = {'symbol': 'AAPL', 'side': 'buy', 'qty': qty}
            result = self.service.validate_order(order)
            assert result['valid'] is False
            assert expected_error in result['errors']
    
    def test_validate_order_valid_quantities(self):
        """Test validation accepts valid quantities."""
        valid_qtys = [1, 100, 999999, 0.1, 50.5, '100', '50.5']
        
        for qty in valid_qtys:
            order = {'symbol': 'AAPL', 'side': 'buy', 'qty': qty}
            result = self.service.validate_order(order)
            assert result['valid'] is True, f"Quantity {qty} should be valid"
    
    def test_validate_order_invalid_order_type(self):
        """Test validation of invalid order types."""
        order = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'invalid_type'
        }
        
        result = self.service.validate_order(order)
        
        assert result['valid'] is False
        assert "invalid_order_type: must be one of ['market', 'limit', 'stop', 'stop_limit']" in result['errors']
    
    def test_validate_order_invalid_price(self):
        """Test validation of invalid prices for limit orders."""
        test_cases = [
            (0, 'invalid_price: must be positive'),
            (-100, 'invalid_price: must be positive'),
            (1000001, 'invalid_price: too large'),
            ('abc', 'invalid_price: not a valid number'),
            (None, 'invalid_price: not a valid number'),
        ]
        
        for price, expected_error in test_cases:
            order = {
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 100,
                'order_type': 'limit',
                'price': price
            }
            result = self.service.validate_order(order)
            assert result['valid'] is False
            assert expected_error in result['errors']
    
    def test_validate_order_exception_handling(self):
        """Test validation handles exceptions gracefully."""
        # Create an order that will cause an exception during validation
        order = Mock()
        order.__contains__ = Mock(side_effect=Exception("Test exception"))
        
        result = self.service.validate_order(order)
        
        assert result['valid'] is False
        assert len(result['errors']) == 1
        assert 'validation_exception: Test exception' in result['errors']


class TestSyncOrderOperations:
    """Test synchronous order operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = OrderService()
    
    def test_submit_order_success(self):
        """Test successful order submission."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'test-order-1'
        }
        
        result = self.service.submit_order(order_data)
        
        assert result['status'] == 'submitted'
        assert result['order_id'] == 'test-order-1'
        assert result['symbol'] == 'AAPL'
        assert result['side'] == 'buy'
        assert result['qty'] == 100
        assert 'submitted_at' in result
    
    def test_submit_order_idempotency(self):
        """Test that submitting the same order ID returns cached result."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'idempotent-order'
        }
        
        # First submission
        result1 = self.service.submit_order(order_data)
        assert result1['status'] == 'submitted'
        
        # Second submission with same order_id should return same result
        result2 = self.service.submit_order(order_data)
        assert result2 == result1
        assert result2['status'] == 'submitted'  # Not duplicate status
    
    def test_submit_order_invalid_parameters(self):
        """Test order submission with invalid parameters."""
        # Missing symbol (empty string)
        order_data = {'symbol': '', 'side': 'buy', 'qty': 100}
        result = self.service.submit_order(order_data)
        assert result['status'] == 'rejected'
        assert 'Invalid order parameters' in result['reason']
        
        # Invalid quantity
        order_data = {'symbol': 'AAPL', 'side': 'buy', 'qty': 0}
        result = self.service.submit_order(order_data)
        assert result['status'] == 'rejected'
        assert 'Invalid order parameters' in result['reason']
    
    def test_submit_order_quantity_fallback(self):
        """Test that order submission handles 'quantity' field as fallback."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'quantity': 100,  # Using 'quantity' instead of 'qty'
            'order_id': 'fallback-test'
        }
        
        result = self.service.submit_order(order_data)
        
        assert result['status'] == 'submitted'
        assert result['qty'] == 100
    
    def test_submit_order_thread_safety(self):
        """Test that submit_order is thread-safe."""
        results = []
        
        def submit_order_thread(order_id):
            order_data = {
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 100,
                'order_id': order_id
            }
            result = self.service.submit_order(order_data)
            results.append(result)
        
        # Create multiple threads submitting orders
        threads = []
        for i in range(5):
            thread = threading.Thread(target=submit_order_thread, args=[f'thread-order-{i}'])
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All orders should be submitted successfully
        assert len(results) == 5
        for result in results:
            assert result['status'] == 'submitted'
    
    def test_modify_order_success(self):
        """Test successful order modification."""
        modification_data = {
            'order_id': 'order-to-modify',
            'modification_id': 'mod-1',
            'new_qty': 150
        }
        
        result = self.service.modify_order(modification_data)
        
        assert result['status'] == 'modified'
        assert result['order_id'] == 'order-to-modify'
        assert result['modification_id'] == 'mod-1'
        assert 'modified_at' in result
    
    def test_modify_order_idempotency(self):
        """Test that order modifications are idempotent."""
        modification_data = {
            'order_id': 'order-to-modify',
            'modification_id': 'idempotent-mod'
        }
        
        # First modification
        result1 = self.service.modify_order(modification_data)
        assert result1['status'] == 'modified'
        
        # Second modification with same IDs should return same result
        result2 = self.service.modify_order(modification_data)
        assert result2 == result1
    
    def test_cancel_order_success(self):
        """Test successful order cancellation."""
        result = self.service.cancel_order('order-to-cancel')
        
        assert result['status'] == 'cancelled'
        assert result['order_id'] == 'order-to-cancel'
        assert 'cancelled_at' in result
    
    def test_cancel_order_idempotency(self):
        """Test that order cancellations are idempotent."""
        order_id = 'idempotent-cancel-order'
        
        # First cancellation
        result1 = self.service.cancel_order(order_id)
        assert result1['status'] == 'cancelled'
        
        # Second cancellation should return 'already_cancelled'
        result2 = self.service.cancel_order(order_id)
        assert result2['status'] == 'already_cancelled'
        assert result2['order_id'] == order_id
    
    def test_update_status_stub(self):
        """Test that update_status is a no-op stub."""
        result = self.service.update_status('arg1', 'arg2', kwarg='value')
        assert result is None


class TestAsyncOrderOperations:
    """Test asynchronous order operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = OrderService()
    
    @pytest.mark.asyncio
    async def test_submit_symbol_order_success(self):
        """Test successful async symbol order submission."""
        # Mock the repository methods
        self.service.orders_repo = AsyncMock()
        self.service.outbox_repo = AsyncMock()
        
        mock_order = Mock()
        mock_order.id = uuid4()
        mock_order.status = 'submitted'
        mock_order.submitted_at = None
        
        self.service.orders_repo.upsert_by_idempotency.return_value = mock_order
        
        result = await self.service.submit_symbol_order(
            symbol='AAPL',
            side='buy',
            qty=100.0,
            idempotency_key='test-key-1'
        )
        
        assert result['symbol'] == 'AAPL'
        assert result['side'] == 'buy'
        assert result['qty'] == '100.0'
        assert result['status'] == 'submitted'
        assert result['idempotency_key'] == 'test-key-1'
        
        # Verify repository calls
        self.service.orders_repo.upsert_by_idempotency.assert_called_once()
        self.service.outbox_repo.add_order_submit_event.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_submit_symbol_order_with_retry_429(self):
        """Test retry logic for 429 rate limiting errors."""
        self.service.orders_repo = AsyncMock()
        self.service.outbox_repo = AsyncMock()
        
        # Mock 429 error that has status_code attribute
        rate_limit_error = Exception("Rate limited")
        rate_limit_error.status_code = 429
        
        mock_order = Mock()
        mock_order.id = uuid4()
        mock_order.status = 'submitted'
        mock_order.submitted_at = None
        
        # First call raises 429, second succeeds
        self.service.orders_repo.upsert_by_idempotency.side_effect = [
            rate_limit_error, mock_order
        ]
        
        with patch('asyncio.sleep') as mock_sleep:
            result = await self.service.submit_symbol_order(
                symbol='AAPL',
                side='buy',
                qty=100.0,
                idempotency_key='retry-key'
            )
        
        assert result['symbol'] == 'AAPL'
        assert self.service.orders_repo.upsert_by_idempotency.call_count == 2
        mock_sleep.assert_called_once()  # Should have slept once for retry
    
    @pytest.mark.asyncio
    async def test_submit_symbol_order_max_retries_exceeded(self):
        """Test that max retries are respected for 429 errors."""
        self.service.orders_repo = AsyncMock()
        
        # Mock 429 error
        rate_limit_error = Exception("Rate limited")
        rate_limit_error.status_code = 429
        
        # All calls raise 429
        self.service.orders_repo.upsert_by_idempotency.side_effect = rate_limit_error
        
        with patch('asyncio.sleep'):
            with pytest.raises(Exception) as exc_info:
                await self.service.submit_symbol_order(
                    symbol='AAPL',
                    side='buy',
                    qty=100.0,
                    idempotency_key='max-retry-key'
                )
        
        assert exc_info.value.status_code == 429
        assert self.service.orders_repo.upsert_by_idempotency.call_count == MAX_RETRIES + 1
    
    @pytest.mark.asyncio
    async def test_submit_symbol_order_non_429_error(self):
        """Test that non-429 errors are not retried."""
        self.service.orders_repo = AsyncMock()
        
        # Mock non-429 error
        other_error = Exception("Database error")
        self.service.orders_repo.upsert_by_idempotency.side_effect = other_error
        
        with pytest.raises(Exception) as exc_info:
            await self.service.submit_symbol_order(
                symbol='AAPL',
                side='buy',
                qty=100.0,
                idempotency_key='no-retry-key'
            )
        
        assert str(exc_info.value) == "Database error"
        assert self.service.orders_repo.upsert_by_idempotency.call_count == 1  # No retry
    
    @pytest.mark.asyncio
    async def test_submit_order_async_success(self):
        """Test successful async order submission."""
        order_data = {
            'symbol': 'MSFT',
            'side': 'sell',
            'qty': 50,
            'order_id': 'async-order-1'
        }
        
        result = await self.service.submit_order_async(order_data)
        
        assert result['status'] == 'submitted'
        assert result['order_id'] == 'async-order-1'
        assert result['symbol'] == 'MSFT'
        assert result['side'] == 'sell'
        assert result['qty'] == 50
    
    @pytest.mark.asyncio
    async def test_submit_order_async_idempotency(self):
        """Test async order submission idempotency."""
        order_data = {
            'symbol': 'TSLA',
            'side': 'buy',
            'qty': 25,
            'order_id': 'async-idempotent'
        }
        
        # First submission
        result1 = await self.service.submit_order_async(order_data)
        assert result1['status'] == 'submitted'
        
        # Second submission should return duplicate status
        result2 = await self.service.submit_order_async(order_data)
        assert result2['status'] == 'duplicate'
        assert 'duplicate request' in result2['reason']
        assert result2['order_id'] == 'async-idempotent'
    
    @pytest.mark.asyncio
    async def test_submit_order_async_invalid_params(self):
        """Test async order submission with invalid parameters."""
        order_data = {
            'symbol': '',  # Invalid symbol
            'side': 'buy',
            'qty': 100
        }
        
        result = await self.service.submit_order_async(order_data)
        
        assert result['status'] == 'rejected'
        assert 'Invalid order parameters' in result['reason']
    
    @pytest.mark.asyncio
    async def test_submit_order_async_concurrency_safety(self):
        """Test that async order submission is concurrency-safe."""
        order_data = {
            'symbol': 'NVDA',
            'side': 'buy',
            'qty': 10,
            'order_id': 'concurrent-test'
        }
        
        # Submit same order concurrently
        tasks = [
            self.service.submit_order_async(order_data.copy())
            for _ in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # First result should be submitted, others should be duplicates
        submitted_count = sum(1 for r in results if r['status'] == 'submitted')
        duplicate_count = sum(1 for r in results if r['status'] == 'duplicate')
        
        assert submitted_count == 1
        assert duplicate_count == 4
    
    @pytest.mark.asyncio
    async def test_get_order_status_found(self):
        """Test getting order status for existing order."""
        # First submit an order
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'status-test-order'
        }
        
        await self.service.submit_order_async(order_data)
        
        # Now get its status
        status = await self.service.get_order_status('status-test-order')
        
        assert status is not None
        assert status['id'] == 'status-test-order'
        assert status['symbol'] == 'AAPL'
        assert status['status'] == 'submitted'
    
    @pytest.mark.asyncio
    async def test_get_order_status_sync_orders(self):
        """Test getting status for synchronously submitted orders."""
        # Submit order synchronously
        order_data = {
            'symbol': 'MSFT',
            'side': 'sell',
            'qty': 75,
            'order_id': 'sync-status-test'
        }
        
        self.service.submit_order(order_data)
        
        # Get status asynchronously
        status = await self.service.get_order_status('sync-status-test')
        
        assert status is not None
        assert status['id'] == 'sync-status-test'
        assert status['symbol'] == 'MSFT'
    
    @pytest.mark.asyncio
    async def test_get_order_status_mock_db(self):
        """Test getting order status with mocked database session."""
        mock_db_result = {
            'id': 'db-order',
            'symbol': 'GOOGL',
            'status': 'filled'
        }
        
        self.service.db_session = Mock()
        self.service.db_session.fetch_one = Mock(return_value=mock_db_result)
        
        status = await self.service.get_order_status('db-order')
        
        assert status == mock_db_result
    
    @pytest.mark.asyncio
    async def test_get_order_status_test_order(self):
        """Test getting status for known test order ID."""
        status = await self.service.get_order_status('test-123')
        
        assert status is not None
        assert status['id'] == 'test-123'
        assert status['status'] == 'filled'
        assert status['symbol'] == 'AAPL'
        assert status['filled_qty'] == 100.0
    
    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self):
        """Test getting status for non-existent order."""
        status = await self.service.get_order_status('non-existent-order')
        
        assert status is None
    
    @pytest.mark.asyncio
    async def test_get_order_history_empty(self):
        """Test getting order history when no orders exist."""
        history = await self.service.get_order_history()
        
        assert history['orders'] == []
        assert history['total'] == 0
        assert history['limit'] == 100
        assert history['offset'] == 0
        assert history['status_filter'] == 'all'
    
    @pytest.mark.asyncio
    async def test_get_order_history_with_orders(self):
        """Test getting order history with submitted orders."""
        # Submit some orders first
        orders = [
            {'symbol': 'AAPL', 'side': 'buy', 'qty': 100, 'order_id': 'hist-1'},
            {'symbol': 'MSFT', 'side': 'sell', 'qty': 50, 'order_id': 'hist-2'},
            {'symbol': 'GOOGL', 'side': 'buy', 'qty': 25, 'order_id': 'hist-3'}
        ]
        
        for order in orders:
            self.service.submit_order(order)
        
        history = await self.service.get_order_history()
        
        assert len(history['orders']) == 3
        assert history['total'] == 3
        
        # Check order details
        order_ids = [order['id'] for order in history['orders']]
        assert 'hist-1' in order_ids
        assert 'hist-2' in order_ids
        assert 'hist-3' in order_ids
    
    @pytest.mark.asyncio
    async def test_get_order_history_pagination(self):
        """Test order history pagination."""
        # Submit multiple orders
        for i in range(5):
            order = {
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 100,
                'order_id': f'page-order-{i}'
            }
            self.service.submit_order(order)
        
        # Get first page
        history = await self.service.get_order_history(limit=2, offset=0)
        assert len(history['orders']) == 2
        assert history['total'] == 5
        assert history['limit'] == 2
        assert history['offset'] == 0
        
        # Get second page
        history = await self.service.get_order_history(limit=2, offset=2)
        assert len(history['orders']) == 2
        assert history['offset'] == 2
    
    @pytest.mark.asyncio
    async def test_get_order_history_status_filter(self):
        """Test order history with status filtering."""
        # Submit orders with different outcomes
        self.service.submit_order({'symbol': 'AAPL', 'side': 'buy', 'qty': 100, 'order_id': 'submitted-1'})
        self.service.submit_order({'symbol': '', 'side': 'buy', 'qty': 100, 'order_id': 'rejected-1'})  # Invalid
        
        # Filter for submitted orders only
        history = await self.service.get_order_history(status_filter='submitted')
        
        assert len(history['orders']) == 1
        assert history['orders'][0]['id'] == 'submitted-1'
        assert history['status_filter'] == 'submitted'
    
    @pytest.mark.asyncio
    async def test_get_order_history_mock_db(self):
        """Test order history with mocked database."""
        mock_db_results = [
            {'id': 'db-order-1', 'symbol': 'AAPL', 'status': 'filled'},
            {'id': 'db-order-2', 'symbol': 'MSFT', 'status': 'cancelled'}
        ]
        
        self.service.db_session = Mock()
        self.service.db_session.fetch_all = Mock(return_value=mock_db_results)
        
        history = await self.service.get_order_history()
        
        assert history['orders'] == mock_db_results
        assert history['total'] == 2


class TestStrategyIntegration:
    """Test strategy integration with plan_and_submit workflow."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = OrderService()
        self.service.orders_repo = AsyncMock()
        self.service.outbox_repo = AsyncMock()
        
        # Mock order for successful submissions
        self.mock_order = Mock()
        self.mock_order.id = uuid4()
        self.mock_order.status = 'submitted'
        self.mock_order.submitted_at = None
        self.service.orders_repo.upsert_by_idempotency.return_value = self.mock_order
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_no_strategy_engine(self):
        """Test plan_and_submit raises error without strategy engine."""
        signals = [Mock()]
        
        with pytest.raises(ValueError, match="StrategyEngine required"):
            await self.service.plan_and_submit(signals)
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_empty_signals(self):
        """Test plan_and_submit with empty signals list."""
        mock_strategy_engine = AsyncMock()
        
        result = await self.service.plan_and_submit([], strategy_engine=mock_strategy_engine)
        
        assert result == []
        mock_strategy_engine.generate_and_gate.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_successful_execution(self):
        """Test successful plan_and_submit execution."""
        signals = [Mock(), Mock()]
        
        # Mock execution plan
        mock_plan = Mock()
        mock_plan.symbol = 'AAPL'
        mock_plan.side = 'buy'
        mock_plan.qty = 100
        mock_plan.risk_allowed = True
        mock_plan.reason = 'Strategy signal'
        mock_plan.from_exposure = 0
        mock_plan.to_exposure = 10000
        mock_plan.notional = 10000
        
        mock_strategy_engine = AsyncMock()
        mock_strategy_engine.generate_and_gate.return_value = [mock_plan]
        
        result = await self.service.plan_and_submit(
            signals,
            strategy_engine=mock_strategy_engine,
            idempotency_key='test-key'
        )
        
        assert len(result) == 1
        assert result[0]['symbol'] == 'AAPL'
        assert result[0]['side'] == 'buy'
        assert result[0]['qty'] == '100.0'
        assert 'order_id' in result[0]
        
        # Verify strategy engine was called
        mock_strategy_engine.generate_and_gate.assert_called_once_with(signals, None)
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_risk_blocked(self):
        """Test plan_and_submit with risk-blocked plan."""
        signals = [Mock()]
        
        # Mock risk-blocked plan
        mock_plan = Mock()
        mock_plan.symbol = 'TSLA'
        mock_plan.risk_allowed = False
        mock_plan.risk_reason = 'Position limit exceeded'
        mock_plan.from_exposure = 5000
        mock_plan.to_exposure = 15000
        mock_plan.qty = 50
        
        mock_strategy_engine = AsyncMock()
        mock_strategy_engine.generate_and_gate.return_value = [mock_plan]
        
        result = await self.service.plan_and_submit(
            signals,
            strategy_engine=mock_strategy_engine
        )
        
        assert len(result) == 1
        assert result[0]['status'] == 'risk_blocked'
        assert result[0]['reason'] == 'Position limit exceeded'
        assert result[0]['symbol'] == 'TSLA'
        assert 'order_id' not in result[0]
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_no_change(self):
        """Test plan_and_submit with zero quantity (no-op) plan."""
        signals = [Mock()]
        
        # Mock no-change plan
        mock_plan = Mock()
        mock_plan.symbol = 'MSFT'
        mock_plan.risk_allowed = True
        mock_plan.qty = 0
        mock_plan.reason = 'No position change needed'
        mock_plan.from_exposure = 5000
        mock_plan.to_exposure = 5000
        
        mock_strategy_engine = AsyncMock()
        mock_strategy_engine.generate_and_gate.return_value = [mock_plan]
        
        result = await self.service.plan_and_submit(
            signals,
            strategy_engine=mock_strategy_engine
        )
        
        assert len(result) == 1
        assert result[0]['status'] == 'no_change'
        assert result[0]['symbol'] == 'MSFT'
        assert 'order_id' not in result[0]
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_order_submission_error(self):
        """Test plan_and_submit when order submission fails."""
        signals = [Mock()]
        
        # Mock valid plan
        mock_plan = Mock()
        mock_plan.symbol = 'NVDA'
        mock_plan.side = 'sell'
        mock_plan.qty = 25
        mock_plan.risk_allowed = True
        mock_plan.reason = 'Rebalance'
        mock_plan.from_exposure = 5000
        mock_plan.to_exposure = 2500
        mock_plan.notional = 2500
        
        mock_strategy_engine = AsyncMock()
        mock_strategy_engine.generate_and_gate.return_value = [mock_plan]
        
        # Make order submission fail
        self.service.orders_repo.upsert_by_idempotency.side_effect = Exception("Database error")
        
        result = await self.service.plan_and_submit(
            signals,
            strategy_engine=mock_strategy_engine
        )
        
        assert len(result) == 1
        assert result[0]['status'] == 'submit_error'
        assert 'Database error' in result[0]['reason']
        assert result[0]['symbol'] == 'NVDA'
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_with_portfolio_state(self):
        """Test plan_and_submit with portfolio state."""
        signals = [Mock()]
        portfolio_state = {'cash': 10000, 'positions': {}}
        
        mock_plan = Mock()
        mock_plan.symbol = 'SPY'
        mock_plan.side = 'buy'
        mock_plan.qty = 100
        mock_plan.risk_allowed = True
        mock_plan.reason = 'Portfolio rebalance'
        mock_plan.from_exposure = 0
        mock_plan.to_exposure = 40000
        mock_plan.notional = 40000
        
        mock_strategy_engine = AsyncMock()
        mock_strategy_engine.generate_and_gate.return_value = [mock_plan]
        
        result = await self.service.plan_and_submit(
            signals,
            strategy_engine=mock_strategy_engine,
            portfolio_state=portfolio_state
        )
        
        assert len(result) == 1
        assert result[0]['symbol'] == 'SPY'
        
        # Verify portfolio state was passed to strategy engine
        mock_strategy_engine.generate_and_gate.assert_called_once_with(signals, portfolio_state)
    
    @pytest.mark.asyncio
    async def test_plan_and_submit_strategy_engine_error(self):
        """Test plan_and_submit when strategy engine fails."""
        signals = [Mock()]
        
        mock_strategy_engine = AsyncMock()
        mock_strategy_engine.generate_and_gate.side_effect = Exception("Strategy engine error")
        
        with pytest.raises(Exception, match="Strategy engine error"):
            await self.service.plan_and_submit(
                signals,
                strategy_engine=mock_strategy_engine
            )


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = OrderService()
    
    def test_circuit_breaker_check_function(self):
        """Test the circuit_breaker_check function."""
        # Should return False by default (not triggering circuit breaker)
        result = circuit_breaker_check('arg1', 'arg2', kwarg='value')
        assert result is False
    
    @pytest.mark.asyncio
    async def test_submit_order_module_level_function(self):
        """Test the module-level submit_order function."""
        with pytest.raises(NotImplementedError, match="submit_order is a test patch point"):
            await submit_order('arg1', 'arg2')
    
    def test_order_service_extensions_class(self):
        """Test that OrderServiceExtensions class exists and is empty."""
        from backend.services.order_service import OrderServiceExtensions
        
        extensions = OrderServiceExtensions()
        assert extensions is not None
        
        # Should have no additional methods beyond object methods
        methods = [m for m in dir(extensions) if not m.startswith('_')]
        assert len(methods) == 0
    
    @pytest.mark.asyncio
    async def test_submit_symbol_order_logging(self):
        """Test that submit_symbol_order logs appropriately."""
        self.service.orders_repo = AsyncMock()
        self.service.outbox_repo = AsyncMock()
        
        mock_order = Mock()
        mock_order.id = uuid4()
        mock_order.status = 'submitted'
        mock_order.submitted_at = None
        
        self.service.orders_repo.upsert_by_idempotency.return_value = mock_order
        
        with patch('backend.services.order_service.logger') as mock_logger:
            await self.service.submit_symbol_order(
                symbol='AAPL',
                side='buy',
                qty=100.0,
                idempotency_key='log-test'
            )
            
            # Should log success
            mock_logger.info.assert_called_once()
            success_call = mock_logger.info.call_args
            assert 'Order submitted successfully' in success_call[0][0]
    
    @pytest.mark.asyncio
    async def test_submit_symbol_order_error_logging(self):
        """Test that submit_symbol_order logs errors appropriately."""
        self.service.orders_repo = AsyncMock()
        self.service.orders_repo.upsert_by_idempotency.side_effect = Exception("Test error")
        
        with patch('backend.services.order_service.logger') as mock_logger:
            with pytest.raises(Exception):
                await self.service.submit_symbol_order(
                    symbol='AAPL',
                    side='buy',
                    qty=100.0,
                    idempotency_key='error-log-test'
                )
            
            # Should log error
            mock_logger.error.assert_called_once()
            error_call = mock_logger.error.call_args
            assert 'Order submission failed' in error_call[0][0]


class TestConcurrencyAndIdempotency:
    """Test concurrency handling and idempotency features."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = OrderService()
    
    def test_sync_order_thread_safety_initialization(self):
        """Test that sync order tracking is initialized thread-safely."""
        results = []
        
        def check_initialization():
            # This should not raise any exceptions
            order_data = {
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 100,
                'order_id': f'thread-safe-{threading.current_thread().ident}'
            }
            result = self.service.submit_order(order_data)
            results.append(result['status'])
        
        # Create multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=check_initialization)
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # All should succeed
        assert all(status == 'submitted' for status in results)
        assert len(results) == 10
    
    @pytest.mark.asyncio
    async def test_async_lock_initialization(self):
        """Test that async lock is initialized properly."""
        # Initially should be None
        assert self.service._async_order_lock is None
        
        # First async call should initialize it
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'lock-init-test'
        }
        
        await self.service.submit_order_async(order_data)
        
        # Lock should now be initialized
        assert self.service._async_order_lock is not None
        assert isinstance(self.service._async_order_lock, asyncio.Lock)
    
    @pytest.mark.asyncio
    async def test_async_concurrent_order_different_ids(self):
        """Test concurrent async orders with different IDs work properly."""
        async def submit_async_order(order_id):
            order_data = {
                'symbol': 'TSLA',
                'side': 'buy',
                'qty': 50,
                'order_id': order_id
            }
            return await self.service.submit_order_async(order_data)
        
        # Submit multiple different orders concurrently
        tasks = [
            submit_async_order(f'concurrent-{i}')
            for i in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should be submitted successfully
        assert all(r['status'] == 'submitted' for r in results)
        assert len(set(r['order_id'] for r in results)) == 5  # All unique IDs
    
    def test_modification_idempotency_thread_safety(self):
        """Test that order modifications are thread-safe and idempotent."""
        results = []
        
        def modify_order():
            modification_data = {
                'order_id': 'shared-order',
                'modification_id': 'shared-mod'
            }
            result = self.service.modify_order(modification_data)
            results.append(result)
        
        # Multiple threads trying to modify same order
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=modify_order)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # All results should be identical (idempotent)
        assert len(results) == 5
        first_result = results[0]
        assert all(r == first_result for r in results)
        assert all(r['status'] == 'modified' for r in results)
    
    def test_cancellation_idempotency_edge_case(self):
        """Test cancellation idempotency with multiple calls."""
        order_id = 'multi-cancel-test'
        
        # First cancellation
        result1 = self.service.cancel_order(order_id)
        assert result1['status'] == 'cancelled'
        
        # Subsequent cancellations
        result2 = self.service.cancel_order(order_id)
        result3 = self.service.cancel_order(order_id)
        
        assert result2['status'] == 'already_cancelled'
        assert result3['status'] == 'already_cancelled'
        assert result2['order_id'] == order_id
        assert result3['order_id'] == order_id


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = OrderService()
    
    def test_submit_order_missing_order_id(self):
        """Test submit_order generates order_id when missing."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100
            # No order_id provided
        }
        
        result = self.service.submit_order(order_data)
        
        assert result['status'] == 'submitted'
        assert 'order_id' in result
        assert result['order_id'] != 'UNKNOWN'  # Should be generated UUID
    
    def test_submit_order_quantity_precedence(self):
        """Test that 'qty' takes precedence over 'quantity'."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'quantity': 50  # Should be ignored
        }
        
        result = self.service.submit_order(order_data)
        
        assert result['qty'] == 100  # qty should take precedence
    
    def test_modify_order_missing_modification_id(self):
        """Test modify_order generates modification_id when missing."""
        modification_data = {
            'order_id': 'test-order'
            # No modification_id provided
        }
        
        result = self.service.modify_order(modification_data)
        
        assert result['status'] == 'modified'
        assert 'modification_id' in result
        assert result['modification_id'] != ''
    
    @pytest.mark.asyncio
    async def test_get_order_status_calculated_remaining_qty(self):
        """Test that get_order_status calculates remaining_qty correctly."""
        # Submit an order first
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'calc-test',
            'filled_qty': 30  # Partially filled
        }
        
        self.service.submit_order(order_data)
        
        # Manually update the stored order to include filled_qty
        self.service._submitted_orders['calc-test']['filled_qty'] = 30
        
        status = await self.service.get_order_status('calc-test')
        
        assert status['qty'] == 100
        assert status['filled_qty'] == 30
        assert status['remaining_qty'] == 70  # 100 - 30
    
    @pytest.mark.asyncio
    async def test_get_order_history_mixed_sources(self):
        """Test order history combines sync and async orders."""
        # Submit sync order
        sync_order = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'sync-mixed'
        }
        self.service.submit_order(sync_order)
        
        # Submit async order
        async_order = {
            'symbol': 'MSFT',
            'side': 'sell',
            'qty': 50,
            'order_id': 'async-mixed'
        }
        await self.service.submit_order_async(async_order)
        
        # Get combined history
        history = await self.service.get_order_history()
        
        assert history['total'] == 2
        order_ids = [order['id'] for order in history['orders']]
        assert 'sync-mixed' in order_ids
        assert 'async-mixed' in order_ids
    
    @pytest.mark.asyncio
    async def test_submit_symbol_order_with_attributes(self):
        """Test submit_symbol_order with custom attributes."""
        self.service.orders_repo = AsyncMock()
        self.service.outbox_repo = AsyncMock()
        
        mock_order = Mock()
        mock_order.id = uuid4()
        mock_order.status = 'submitted'
        mock_order.submitted_at = None
        
        self.service.orders_repo.upsert_by_idempotency.return_value = mock_order
        
        custom_attributes = {
            'client_ref': 'TEST-REF-123',
            'strategy': 'momentum',
            'risk_level': 'medium'
        }
        
        result = await self.service.submit_symbol_order(
            symbol='AAPL',
            side='buy',
            qty=100.0,
            idempotency_key='attr-test',
            order_type='limit',
            tif='gtc',
            attributes=custom_attributes
        )
        
        assert result['symbol'] == 'AAPL'
        
        # Verify attributes were passed to repositories
        repo_call = self.service.orders_repo.upsert_by_idempotency.call_args
        assert repo_call[1]['attributes'] == custom_attributes
        assert repo_call[1]['order_type'] == 'limit'
        assert repo_call[1]['tif'] == 'gtc'
    
    @pytest.mark.asyncio
    async def test_submit_symbol_order_decimal_conversion(self):
        """Test that quantity is properly converted to Decimal."""
        self.service.orders_repo = AsyncMock()
        self.service.outbox_repo = AsyncMock()
        
        mock_order = Mock()
        mock_order.id = uuid4()
        mock_order.status = 'submitted'
        mock_order.submitted_at = None
        
        self.service.orders_repo.upsert_by_idempotency.return_value = mock_order
        
        await self.service.submit_symbol_order(
            symbol='AAPL',
            side='buy',
            qty=100.5,  # Float quantity
            idempotency_key='decimal-test'
        )
        
        # Verify Decimal conversion
        repo_call = self.service.orders_repo.upsert_by_idempotency.call_args
        assert repo_call[1]['qty'] == Decimal('100.5')
    
    def test_constants_and_globals(self):
        """Test module constants and global functions."""
        # Test MAX_RETRIES constant
        assert MAX_RETRIES == 3
        
        # Test circuit_breaker_check function
        assert circuit_breaker_check() is False
        assert circuit_breaker_check('arg1', 'arg2', kwarg='value') is False
    
    def test_submit_order_comprehensive_coverage(self):
        """Test comprehensive coverage scenarios for submit_order."""
        service = OrderService()
        
        # Test successful submission paths
        result = service.submit_order({
            'symbol': 'AAPL',
            'side': 'buy', 
            'qty': 100,
            'order_id': 'comprehensive-test'
        })
        assert result['status'] == 'submitted'
        
        # Test idempotency
        result2 = service.submit_order({
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100, 
            'order_id': 'comprehensive-test'
        })
        assert result2 == result  # Should be identical
    
    @pytest.mark.asyncio
    async def test_submit_order_async_comprehensive_coverage(self):
        """Test comprehensive coverage scenarios for submit_order_async."""
        service = OrderService()
        
        # Test successful async submission
        result = await service.submit_order_async({
            'symbol': 'MSFT',
            'side': 'sell',
            'qty': 75,
            'order_id': 'async-comprehensive-test'
        })
        assert result['status'] == 'submitted'
        
        # Test async idempotency (should return duplicate status)
        result2 = await service.submit_order_async({
            'symbol': 'MSFT',
            'side': 'sell',
            'qty': 75,
            'order_id': 'async-comprehensive-test'
        })
        assert result2['status'] == 'duplicate'

    def test_submit_order_exception_handling(self):
        """Test submit_order exception handling path (lines 310-320)."""
        service = OrderService()
        
        # Create a broken cache object that raises exception on first assignment only
        class FailingDict:
            def __init__(self):
                self.failed = False
                self.backup = {}
            def __contains__(self, key):
                return key in self.backup
            def __setitem__(self, key, value):
                if not self.failed and value.get('status') == 'submitted':
                    # Fail on first submission (inside try block)
                    self.failed = True
                    raise Exception("Cache assignment failed")
                else:
                    # Allow rejection to be cached (inside except block)
                    self.backup[key] = value
            def __getitem__(self, key):
                return self.backup[key]
        
        # Replace the _submitted_orders with our failing dict
        service._submitted_orders = FailingDict()
        
        result = service.submit_order({
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'exception-test-sync'
        })
        
        # Should return rejection with exception message
        assert result['status'] == 'rejected'
        assert 'Order submission failed: Cache assignment failed' in result['reason']
        assert result['order_id'] == 'exception-test-sync'
        assert result['symbol'] == 'AAPL'
        assert result['qty'] == 100
        assert result['side'] == 'buy'

    @pytest.mark.asyncio
    async def test_submit_order_async_exception_handling(self):
        """Test submit_order_async exception handling path (lines 558-568)."""
        service = OrderService()
        
        # Create a broken cache object that raises exception on first assignment only
        class FailingDict:
            def __init__(self):
                self.failed = False
                self.backup = {}
            def __contains__(self, key):
                return key in self.backup
            def __setitem__(self, key, value):
                if not self.failed and value.get('status') == 'submitted':
                    # Fail on first submission (inside try block)
                    self.failed = True
                    raise Exception("Async cache assignment failed")
                else:
                    # Allow rejection to be cached (inside except block)
                    self.backup[key] = value
            def __getitem__(self, key):
                return self.backup[key]
        
        # Replace the _async_submitted_orders with our failing dict
        service._async_submitted_orders = FailingDict()
        
        result = await service.submit_order_async({
            'symbol': 'MSFT',
            'side': 'sell',
            'qty': 150,
            'order_id': 'exception-test-async'
        })
        
        # Should return rejection with exception message
        assert result['status'] == 'rejected'
        assert 'Order submission failed: Async cache assignment failed' in result['reason']
        assert result['order_id'] == 'exception-test-async'
        assert result['symbol'] == 'MSFT'
        assert result['qty'] == 150
        assert result['side'] == 'sell'


# Module-level test execution setup
if __name__ == "__main__":
    # Enable asyncio mode for pytest
    pytest.main([__file__, "-v", "--tb=short"])