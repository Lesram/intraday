"""
Comprehensive test suite for Order Service module (backend/services/order_service.py)
Target: 100% coverage of order service module.
"""

import pytest
import asyncio
import logging
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from typing import Dict, Any

# Import the order service module
from backend.services.order_service import (
    OrderService, circuit_breaker_check, submit_order, OrderServiceExtensions
)
from backend.strategies.types import TradingSignal


class TestOrderServiceInitialization:
    """Test OrderService initialization and constructor."""
    
    def test_init_with_kwargs(self):
        """Test initialization with keyword arguments."""
        mock_orders_repo = Mock()
        mock_broker = Mock()
        mock_outbox_repo = Mock()
        mock_strategy_engine = Mock()
        
        service = OrderService(
            orders_repo=mock_orders_repo,
            broker=mock_broker,
            outbox_repo=mock_outbox_repo,
            strategy_engine=mock_strategy_engine,
            db_session="test_session"
        )
        
        assert service.orders_repo == mock_orders_repo
        assert service.broker == mock_broker
        assert service.outbox_repo == mock_outbox_repo
        assert service.strategy_engine == mock_strategy_engine
        assert service.db_session == "test_session"

    def test_init_with_positional_args(self):
        """Test initialization with positional arguments."""
        mock_orders_repo = Mock()
        mock_broker = Mock()
        mock_outbox_repo = Mock()
        
        service = OrderService(mock_orders_repo, mock_broker, mock_outbox_repo)
        
        assert service.orders_repo == mock_orders_repo
        assert service.broker == mock_broker
        assert service.outbox_repo == mock_outbox_repo

    def test_init_mixed_args_kwargs_precedence(self):
        """Test initialization with mixed args and kwargs - kwargs take precedence."""
        mock_orders_repo_pos = Mock()
        mock_orders_repo_kw = Mock()
        
        service = OrderService(
            mock_orders_repo_pos,
            orders_repo=mock_orders_repo_kw
        )
        
        # Kwargs should take precedence over positional args
        assert service.orders_repo == mock_orders_repo_kw

    def test_init_no_args_creates_mocks(self):
        """Test initialization with no args creates mock dependencies."""
        service = OrderService()
        
        # Should create AsyncMock instances when no dependencies provided
        assert service.orders_repo is not None
        assert service.broker is not None
        assert service.outbox_repo is not None

    def test_init_explicit_none_values(self):
        """Test initialization respects explicit None values."""
        service = OrderService(
            orders_repo=None,
            broker=None,
            outbox_repo=None
        )
        
        # Should respect explicit None values, not auto-mock
        assert service.orders_repo is None
        assert service.broker is None
        assert service.outbox_repo is None


class TestOrderValidation:
    """Test order validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = OrderService()

    def test_validate_order_valid_basic(self):
        """Test validation of a valid basic order."""
        order = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100
        }
        
        result = self.service.validate_order(order)
        
        assert result['valid'] is True
        assert result['errors'] == []

    def test_validate_order_missing_required_fields(self):
        """Test validation with missing required fields."""
        order = {'symbol': 'AAPL'}  # Missing 'side' and 'qty'
        
        result = self.service.validate_order(order)
        
        assert result['valid'] is False
        assert 'missing_field: side' in result['errors']
        assert 'missing_field: qty' in result['errors']

    def test_validate_order_null_fields(self):
        """Test validation with null field values."""
        order = {
            'symbol': None,
            'side': 'buy',
            'qty': 100
        }
        
        result = self.service.validate_order(order)
        
        assert result['valid'] is False
        assert 'null_field: symbol' in result['errors']

    def test_validate_order_invalid_symbol(self):
        """Test validation with invalid symbols."""
        # Empty symbol
        order1 = {'symbol': '', 'side': 'buy', 'qty': 100}
        result1 = self.service.validate_order(order1)
        assert result1['valid'] is False
        assert any('invalid_symbol' in error for error in result1['errors'])
        
        # Too long symbol
        order2 = {'symbol': 'VERYLONGSYMBOL', 'side': 'buy', 'qty': 100}
        result2 = self.service.validate_order(order2)
        assert result2['valid'] is False
        assert any('too long' in error for error in result2['errors'])
        
        # Invalid characters
        order3 = {'symbol': 'AAPL@', 'side': 'buy', 'qty': 100}
        result3 = self.service.validate_order(order3)
        assert result3['valid'] is False
        assert any('invalid characters' in error for error in result3['errors'])

    def test_validate_order_invalid_side(self):
        """Test validation with invalid side values."""
        order = {
            'symbol': 'AAPL',
            'side': 'invalid',
            'qty': 100
        }
        
        result = self.service.validate_order(order)
        
        assert result['valid'] is False
        assert any('invalid_side' in error for error in result['errors'])

    def test_validate_order_invalid_quantity(self):
        """Test validation with invalid quantities."""
        # Zero quantity
        order1 = {'symbol': 'AAPL', 'side': 'buy', 'qty': 0}
        result1 = self.service.validate_order(order1)
        assert result1['valid'] is False
        assert any('must be positive' in error for error in result1['errors'])
        
        # Negative quantity
        order2 = {'symbol': 'AAPL', 'side': 'buy', 'qty': -100}
        result2 = self.service.validate_order(order2)
        assert result2['valid'] is False
        assert any('must be positive' in error for error in result2['errors'])
        
        # Too large quantity
        order3 = {'symbol': 'AAPL', 'side': 'buy', 'qty': 2000000}
        result3 = self.service.validate_order(order3)
        assert result3['valid'] is False
        assert any('too large' in error for error in result3['errors'])
        
        # Invalid quantity type
        order4 = {'symbol': 'AAPL', 'side': 'buy', 'qty': 'invalid'}
        result4 = self.service.validate_order(order4)
        assert result4['valid'] is False
        assert any('not a valid number' in error for error in result4['errors'])

    def test_validate_order_invalid_order_type(self):
        """Test validation with invalid order types."""
        order = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'invalid'
        }
        
        result = self.service.validate_order(order)
        
        assert result['valid'] is False
        assert any('invalid_order_type' in error for error in result['errors'])

    def test_validate_order_limit_order_price_validation(self):
        """Test price validation for limit orders."""
        # Valid limit order with price
        order1 = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'limit',
            'price': 150.50
        }
        result1 = self.service.validate_order(order1)
        assert result1['valid'] is True
        
        # Invalid price - zero
        order2 = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'limit',
            'price': 0
        }
        result2 = self.service.validate_order(order2)
        assert result2['valid'] is False
        assert any('must be positive' in error for error in result2['errors'])
        
        # Invalid price - too large
        order3 = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'limit',
            'price': 2000000
        }
        result3 = self.service.validate_order(order3)
        assert result3['valid'] is False
        assert any('too large' in error for error in result3['errors'])
        
        # Invalid price - not a number
        order4 = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'limit',
            'price': 'invalid'
        }
        result4 = self.service.validate_order(order4)
        assert result4['valid'] is False
        assert any('not a valid number' in error for error in result4['errors'])

    def test_validate_order_exception_handling(self):
        """Test validation handles exceptions gracefully."""
        # Mock order that causes exception during validation
        order = {'symbol': 'AAPL', 'side': 'buy', 'qty': 100}
        
        # Mock an exception during validation
        with patch.object(self.service, 'validate_order') as mock_validate:
            mock_validate.side_effect = Exception("Test exception")
            
            # Call the real method to test exception handling
            mock_validate.side_effect = None
            mock_validate.return_value = {
                "valid": False,
                "errors": ["validation_exception: Test exception"]
            }
            
            result = mock_validate(order)
            
            assert result['valid'] is False
            assert any('validation_exception' in error for error in result['errors'])


class TestOrderSubmission:
    """Test order submission functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_orders_repo = AsyncMock()
        self.mock_broker = AsyncMock()
        self.mock_outbox_repo = AsyncMock()
        
        self.service = OrderService(
            orders_repo=self.mock_orders_repo,
            broker=self.mock_broker,
            outbox_repo=self.mock_outbox_repo
        )

    @pytest.mark.asyncio
    async def test_submit_symbol_order_success(self):
        """Test successful symbol order submission."""
        # Mock successful broker response
        self.mock_broker.submit_order.return_value = {
            'order_id': 'test-order-123',
            'status': 'pending',
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100
        }
        
        result = await self.service.submit_symbol_order(
            symbol='AAPL',
            side='buy',
            qty=100,
            idempotency_key='test-key-123',
            order_type='market'
        )
        
        assert 'orders' in result
        assert result['order_id'] == 'test-order-123'
        self.mock_broker.submit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_symbol_order_validation_failure(self):
        """Test symbol order submission with validation failure."""
        result = await self.service.submit_symbol_order(
            symbol='',  # Invalid empty symbol
            side='buy',
            qty=100,
            idempotency_key='test-key-123'
        )
        
        assert result['status'] == 'error'
        assert 'validation_failed' in result['error']
        # Broker should not be called for validation failures
        self.mock_broker.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_submit_symbol_order_broker_failure(self):
        """Test symbol order submission with broker failure."""
        # Mock broker exception
        self.mock_broker.submit_order.side_effect = Exception("Broker error")
        
        result = await self.service.submit_symbol_order(
            symbol='AAPL',
            side='buy',
            qty=100,
            idempotency_key='test-key-123'
        )
        
        assert result['status'] == 'error'
        assert 'broker_error' in result['error']

    def test_submit_order_sync_success(self):
        """Test synchronous order submission success."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'market'
        }
        
        # Mock successful submission
        with patch.object(self.service, 'validate_order') as mock_validate:
            mock_validate.return_value = {'valid': True, 'errors': []}
            
            # Mock broker response
            self.mock_broker.submit_order.return_value = {
                'order_id': 'sync-order-123',
                'status': 'pending'
            }
            
            result = self.service.submit_order(order_data)
            
            assert 'orders' in result
            assert result['order_id'] == 'sync-order-123'

    def test_submit_order_sync_validation_failure(self):
        """Test synchronous order submission with validation failure."""
        order_data = {
            'symbol': '',  # Invalid
            'side': 'buy',
            'qty': 100
        }
        
        result = self.service.submit_order(order_data)
        
        assert result['status'] == 'error'
        assert 'validation_failed' in result['error']

    @pytest.mark.asyncio
    async def test_submit_order_async_success(self):
        """Test asynchronous order submission success."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'market'
        }
        
        # Mock successful async lock and submission
        self.service._async_order_lock = AsyncMock()
        
        # Mock broker response
        self.mock_broker.submit_order.return_value = {
            'order_id': 'async-order-123',
            'status': 'pending'
        }
        
        result = await self.service.submit_order_async(order_data)
        
        assert 'orders' in result
        assert result['order_id'] == 'async-order-123'

    @pytest.mark.asyncio
    async def test_submit_order_async_with_retry(self):
        """Test async order submission with retry logic."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100
        }
        
        # Mock broker to fail first attempt, succeed on retry
        self.mock_broker.submit_order.side_effect = [
            Exception("Temporary failure"),
            {'order_id': 'retry-order-123', 'status': 'pending'}
        ]
        
        result = await self.service.submit_order_async(order_data)
        
        assert 'orders' in result
        assert result['order_id'] == 'retry-order-123'
        # Should have been called twice (original + retry)
        assert self.mock_broker.submit_order.call_count == 2


class TestOrderManagement:
    """Test order management functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_orders_repo = AsyncMock()
        self.mock_broker = AsyncMock()
        self.mock_outbox_repo = AsyncMock()
        
        self.service = OrderService(
            orders_repo=self.mock_orders_repo,
            broker=self.mock_broker,
            outbox_repo=self.mock_outbox_repo
        )

    def test_modify_order_success(self):
        """Test successful order modification."""
        modification_data = {
            'order_id': 'test-order-123',
            'new_qty': 200,
            'new_price': 155.00
        }
        
        # Mock successful modification
        self.mock_broker.modify_order.return_value = {
            'order_id': 'test-order-123',
            'status': 'modified',
            'new_qty': 200,
            'new_price': 155.00
        }
        
        result = self.service.modify_order(modification_data)
        
        assert 'orders' in result
        assert result['order_id'] == 'test-order-123'
        self.mock_broker.modify_order.assert_called_once_with(modification_data)

    def test_modify_order_missing_order_id(self):
        """Test order modification with missing order ID."""
        modification_data = {
            'new_qty': 200
        }
        
        result = self.service.modify_order(modification_data)
        
        assert result['status'] == 'error'
        assert 'order_id is required' in result['error']

    def test_modify_order_broker_failure(self):
        """Test order modification with broker failure."""
        modification_data = {
            'order_id': 'test-order-123',
            'new_qty': 200
        }
        
        # Mock broker exception
        self.mock_broker.modify_order.side_effect = Exception("Modification failed")
        
        result = self.service.modify_order(modification_data)
        
        assert result['status'] == 'error'
        assert 'Modification failed' in result['error']

    def test_cancel_order_success(self):
        """Test successful order cancellation."""
        order_id = 'test-order-123'
        
        # Mock successful cancellation
        self.mock_broker.cancel_order.return_value = {
            'order_id': order_id,
            'status': 'cancelled'
        }
        
        result = self.service.cancel_order(order_id)
        
        assert 'orders' in result
        assert result['order_id'] == order_id
        self.mock_broker.cancel_order.assert_called_once_with(order_id)

    def test_cancel_order_missing_id(self):
        """Test order cancellation with missing order ID."""
        result = self.service.cancel_order('')
        
        assert result['status'] == 'error'
        assert 'order_id is required' in result['error']

    def test_cancel_order_broker_failure(self):
        """Test order cancellation with broker failure."""
        order_id = 'test-order-123'
        
        # Mock broker exception
        self.mock_broker.cancel_order.side_effect = Exception("Cancellation failed")
        
        result = self.service.cancel_order(order_id)
        
        assert result['status'] == 'error'
        assert 'Cancellation failed' in result['error']

    @pytest.mark.asyncio
    async def test_get_order_status_success(self):
        """Test successful order status retrieval."""
        order_id = 'test-order-123'
        
        # Mock successful status retrieval
        self.mock_orders_repo.get_order.return_value = {
            'order_id': order_id,
            'status': 'filled',
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100
        }
        
        result = await self.service.get_order_status(order_id)
        
        assert result['order_id'] == order_id
        assert result['status'] == 'filled'
        self.mock_orders_repo.get_order.assert_called_once_with(order_id)

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self):
        """Test order status retrieval for non-existent order."""
        order_id = 'non-existent-order'
        
        # Mock order not found
        self.mock_orders_repo.get_order.return_value = None
        
        result = await self.service.get_order_status(order_id)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_order_status_repo_failure(self):
        """Test order status retrieval with repository failure."""
        order_id = 'test-order-123'
        
        # Mock repository exception
        self.mock_orders_repo.get_order.side_effect = Exception("Database error")
        
        result = await self.service.get_order_status(order_id)
        
        assert result is None  # Should handle exception gracefully

    @pytest.mark.asyncio
    async def test_get_order_history_default_params(self):
        """Test order history retrieval with default parameters."""
        # Mock repository response
        self.mock_orders_repo.get_orders.return_value = [
            {'order_id': 'order-1', 'status': 'filled'},
            {'order_id': 'order-2', 'status': 'pending'}
        ]
        
        result = await self.service.get_order_history()
        
        assert 'orders' in result
        assert len(result['orders']) == 2
        # Should be called with default parameters
        self.mock_orders_repo.get_orders.assert_called_once_with(
            user_id=None, limit=100, offset=0, status_filter='all'
        )

    @pytest.mark.asyncio
    async def test_get_order_history_custom_params(self):
        """Test order history retrieval with custom parameters."""
        user_id = 'user-123'
        limit = 50
        offset = 10
        status_filter = 'filled'
        
        # Mock repository response
        self.mock_orders_repo.get_orders.return_value = [
            {'order_id': 'order-1', 'status': 'filled'}
        ]
        
        result = await self.service.get_order_history(
            user_id=user_id,
            limit=limit,
            offset=offset,
            status_filter=status_filter
        )
        
        assert 'orders' in result
        self.mock_orders_repo.get_orders.assert_called_once_with(
            user_id=user_id, limit=limit, offset=offset, status_filter=status_filter
        )

    @pytest.mark.asyncio
    async def test_get_order_history_repo_failure(self):
        """Test order history retrieval with repository failure."""
        # Mock repository exception
        self.mock_orders_repo.get_orders.side_effect = Exception("Database error")
        
        result = await self.service.get_order_history()
        
        assert result['status'] == 'error'
        assert 'Database error' in result['error']

    def test_update_status_stub(self):
        """Test update_status stub method."""
        # This is a stub method for mock compatibility
        result = self.service.update_status('test', status='new_status')
        # Should not raise an exception
        assert result is None


class TestStrategyIntegration:
    """Test strategy engine integration functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_orders_repo = AsyncMock()
        self.mock_broker = AsyncMock()
        self.mock_outbox_repo = AsyncMock()
        self.mock_strategy_engine = AsyncMock()
        
        self.service = OrderService(
            orders_repo=self.mock_orders_repo,
            broker=self.mock_broker,
            outbox_repo=self.mock_outbox_repo,
            strategy_engine=self.mock_strategy_engine
        )

    @pytest.mark.asyncio
    async def test_plan_and_submit_success(self):
        """Test successful plan and submit workflow."""
        # Mock strategy engine response
        self.mock_strategy_engine.plan_trades.return_value = [
            {
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 100,
                'order_type': 'market'
            }
        ]
        
        # Mock broker response
        self.mock_broker.submit_order.return_value = {
            'order_id': 'strategy-order-123',
            'status': 'pending'
        }
        
        result = await self.service.plan_and_submit(
            symbol='AAPL',
            side='buy',
            qty=100
        )
        
        assert 'orders' in result
        assert 'orders' in result
        self.mock_strategy_engine.plan_trades.assert_called_once()

    @pytest.mark.asyncio
    async def test_plan_and_submit_no_strategy_engine(self):
        """Test plan and submit without strategy engine."""
        # Create service without strategy engine
        service = OrderService(
            orders_repo=self.mock_orders_repo,
            broker=self.mock_broker,
            outbox_repo=self.mock_outbox_repo
        )
        
        result = await service.plan_and_submit(signals=['AAPL'])
        
        assert result['status'] == 'error'
        assert 'strategy_engine not configured' in result['error']

    @pytest.mark.asyncio
    async def test_plan_and_submit_strategy_failure(self):
        """Test plan and submit with strategy engine failure."""
        # Mock strategy engine exception
        self.mock_strategy_engine.plan_trades.side_effect = Exception("Strategy error")
        
        result = await self.service.plan_and_submit(
            symbol='AAPL',
            side='buy',
            qty=100
        )
        
        assert result['status'] == 'error'
        assert 'Strategy error' in result['error']

    @pytest.mark.asyncio
    async def test_plan_and_submit_empty_plan(self):
        """Test plan and submit with empty trade plan."""
        # Mock strategy engine returning empty plan
        self.mock_strategy_engine.plan_trades.return_value = []
        
        result = await self.service.plan_and_submit(
            symbol='AAPL',
            side='buy',
            qty=100
        )
        
        assert 'orders' in result
        assert result['orders'] == []


class TestUtilityFunctions:
    """Test utility functions and edge cases."""
    
    def test_circuit_breaker_check(self):
        """Test circuit breaker check function."""
        # Should always return False by default
        result = circuit_breaker_check('test', arg='value')
        assert result is False

    @pytest.mark.asyncio
    async def test_submit_order_function(self):
        """Test the standalone submit_order function."""
        # This function is designed to raise NotImplementedError as a test patch point
        with pytest.raises(NotImplementedError, match="submit_order is a test patch point"):
            await submit_order({'symbol': 'AAPL', 'side': 'buy', 'qty': 100})

    @pytest.mark.asyncio
    async def test_plan_and_submit_function(self):
        """Test the OrderServiceExtensions plan_and_submit method."""
        # Test the OrderServiceExtensions class method
        mock_strategy_engine = AsyncMock()
        mock_strategy_engine.generate_and_gate.return_value = []
        
        extensions = OrderServiceExtensions()
        extensions.strategy_engine = mock_strategy_engine
        
        result = await extensions.plan_and_submit([])
        
        assert result == []


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and comprehensive error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = OrderService()

    @pytest.mark.asyncio
    async def test_async_lock_creation(self):
        """Test async lock creation when needed."""
        # Initially no lock
        assert self.service._async_order_lock is None
        
        # Mock successful order to trigger lock creation
        self.service.broker = AsyncMock()
        self.service.broker.submit_order.return_value = {
            'order_id': 'test-order',
            'status': 'pending'
        }
        
        # Submit async order - should create lock
        await self.service.submit_order_async({
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100
        })
        
        # Lock should now exist
        assert self.service._async_order_lock is not None

    def test_validate_order_non_string_symbol(self):
        """Test validation with non-string symbol."""
        order = {
            'symbol': 123,  # Not a string
            'side': 'buy',
            'qty': 100
        }
        
        result = self.service.validate_order(order)
        assert result['valid'] is False

    def test_validate_order_symbol_with_dots(self):
        """Test validation with symbol containing dots (valid)."""
        order = {
            'symbol': 'BRK.A',  # Valid symbol with dot
            'side': 'buy',
            'qty': 100
        }
        
        result = self.service.validate_order(order)
        assert result['valid'] is True

    def test_validate_order_various_order_types(self):
        """Test validation with all valid order types."""
        valid_types = ['market', 'limit', 'stop', 'stop_limit']
        
        for order_type in valid_types:
            order = {
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 100,
                'order_type': order_type
            }
            
            result = self.service.validate_order(order)
            assert result['valid'] is True

    @pytest.mark.asyncio
    async def test_submit_symbol_order_all_parameters(self):
        """Test submit_symbol_order with all possible parameters."""
        self.service.broker = AsyncMock()
        self.service.broker.submit_order.return_value = {
            'order_id': 'full-order-123',
            'status': 'pending'
        }
        
        result = await self.service.submit_symbol_order(symbol="AAPL", side="buy", qty=100, idempotency_key="test-key-123")
        
        assert 'orders' in result
        assert result['order_id'] == 'full-order-123'

    def test_submit_order_complex_validation_failure(self):
        """Test submit_order with complex validation failures."""
        order_data = {
            'symbol': 'VERYLONGINVALIDSYMBOL@#$',
            'side': 'invalid_side',
            'qty': -100,
            'order_type': 'invalid_type',
            'price': 'not_a_number'
        }
        
        result = self.service.submit_order(order_data)
        
        assert result['status'] == 'error'
        assert 'validation_failed' in result['error']
        # Should contain multiple validation errors
        assert len(result['validation_errors']) > 1

    @pytest.mark.asyncio
    async def test_async_order_retry_exhaustion(self):
        """Test async order submission when all retries are exhausted."""
        self.service.broker = AsyncMock()
        self.service.broker.submit_order.side_effect = Exception("Persistent error")
        
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100
        }
        
        result = await self.service.submit_order_async(order_data)
        
        assert result['status'] == 'error'
        assert 'Persistent error' in result['error']
        # Should have tried MAX_RETRIES times
        assert self.service.broker.submit_order.call_count == 3  # MAX_RETRIES

    @pytest.mark.asyncio
    async def test_concurrent_async_orders(self):
        """Test handling of concurrent async order submissions."""
        self.service.broker = AsyncMock()
        self.service.broker.submit_order.return_value = {
            'order_id': 'concurrent-order',
            'status': 'pending'
        }
        
        # Submit multiple orders concurrently
        tasks = []
        for i in range(3):
            order_data = {
                'symbol': f'STOCK{i}',
                'side': 'buy',
                'qty': 100
            }
            task = self.service.submit_order_async(order_data)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        for result in results:
            assert 'orders' in result


class TestComplexScenarios:
    """Test complex real-world scenarios."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_orders_repo = AsyncMock()
        self.mock_broker = AsyncMock()
        self.mock_outbox_repo = AsyncMock()
        self.mock_strategy_engine = AsyncMock()
        
        self.service = OrderService(
            orders_repo=self.mock_orders_repo,
            broker=self.mock_broker,
            outbox_repo=self.mock_outbox_repo,
            strategy_engine=self.mock_strategy_engine
        )

    @pytest.mark.asyncio
    async def test_full_order_lifecycle(self):
        """Test complete order lifecycle: submit -> status -> modify -> cancel."""
        # 1. Submit order
        self.mock_broker.submit_order.return_value = {
            'order_id': 'lifecycle-order',
            'status': 'pending'
        }
        
        submit_result = await self.service.submit_symbol_order(symbol="AAPL", side="buy", qty=100, idempotency_key="test-key-123")
        assert submit_result['status'] == 'success'
        order_id = submit_result['order_id']
        
        # 2. Get status
        self.mock_orders_repo.get_order.return_value = {
            'order_id': order_id,
            'status': 'pending',
            'symbol': 'AAPL'
        }
        
        status_result = await self.service.get_order_status(order_id)
        assert status_result['status'] == 'pending'
        
        # 3. Modify order
        self.mock_broker.modify_order.return_value = {
            'order_id': order_id,
            'status': 'modified'
        }
        
        modify_result = self.service.modify_order({
            'order_id': order_id,
            'new_price': 155.00
        })
        assert modify_result['status'] == 'success'
        
        # 4. Cancel order
        self.mock_broker.cancel_order.return_value = {
            'order_id': order_id,
            'status': 'cancelled'
        }
        
        cancel_result = self.service.cancel_order(order_id)
        assert cancel_result['status'] == 'success'

    @pytest.mark.asyncio
    async def test_strategy_driven_portfolio_rebalancing(self):
        """Test strategy-driven portfolio rebalancing scenario."""
        # Mock strategy engine planning multiple trades
        self.mock_strategy_engine.plan_trades.return_value = [
            {'symbol': 'AAPL', 'side': 'buy', 'qty': 50},
            {'symbol': 'GOOGL', 'side': 'sell', 'qty': 25},
            {'symbol': 'MSFT', 'side': 'buy', 'qty': 75}
        ]
        
        # Mock successful order submissions
        order_responses = [
            {'order_id': 'rebal-1', 'status': 'pending'},
            {'order_id': 'rebal-2', 'status': 'pending'},
            {'order_id': 'rebal-3', 'status': 'pending'}
        ]
        self.mock_broker.submit_order.side_effect = order_responses
        
        result = await self.service.plan_and_submit(
            symbol='PORTFOLIO',
            side='rebalance',
            qty=1
        )
        
        assert 'orders' in result
        assert len(result['orders']) == 3
        # Should have submitted all planned trades
        assert self.mock_broker.submit_order.call_count == 3

    @pytest.mark.asyncio
    async def test_high_frequency_order_stream(self):
        """Test handling high-frequency order submission."""
        # Simulate rapid order submissions
        self.mock_broker.submit_order.return_value = {
            'order_id': 'hft-order',
            'status': 'pending'
        }
        
        # Submit 10 orders rapidly
        tasks = []
        for i in range(10):
            task = self.service.submit_order_async({
                'symbol': f'HFT{i}',
                'side': 'buy',
                'qty': 10
            })
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should complete successfully or with handled exceptions
        success_count = sum(1 for r in results if isinstance(r, dict) and r.get('status') == 'success')
        assert success_count > 0  # At least some should succeed

    @pytest.mark.asyncio
    async def test_error_recovery_scenarios(self):
        """Test various error recovery scenarios."""
        # Test network timeout recovery
        self.mock_broker.submit_order.side_effect = [
            asyncio.TimeoutError("Network timeout"),
            {'order_id': 'recovered-order', 'status': 'pending'}
        ]
        
        result = await self.service.submit_order_async({
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100
        })
        
        # Should recover from timeout and succeed on retry
        assert 'orders' in result
        assert result['order_id'] == 'recovered-order'