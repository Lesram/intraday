"""
Comprehensive tests for OrderService with 100% coverage target.

This test suite covers all methods and code paths in the OrderService
to achieve 100% code coverage.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from decimal import Decimal

from backend.services.order_service import OrderService


class TestOrderServiceInitialization:
    """Test OrderService initialization and setup."""

    def test_init_with_positional_args(self):
        """Test OrderService initialization with positional arguments."""
        orders_repo = MagicMock()
        broker = MagicMock()
        outbox_repo = MagicMock()
        
        service = OrderService(orders_repo, broker, outbox_repo)
        
        assert service.orders_repo == orders_repo
        assert service.broker == broker
        assert service.outbox_repo == outbox_repo
        assert service.strategy_engine is None

    def test_init_with_keyword_args(self):
        """Test OrderService initialization with keyword arguments."""
        orders_repo = MagicMock()
        broker = MagicMock()
        outbox_repo = MagicMock()
        strategy_engine = MagicMock()
        
        service = OrderService(
            orders_repo=orders_repo,
            broker=broker,
            outbox_repo=outbox_repo,
            strategy_engine=strategy_engine
        )
        
        assert service.orders_repo == orders_repo
        assert service.broker == broker
        assert service.outbox_repo == outbox_repo
        assert service.strategy_engine == strategy_engine

    def test_init_with_mixed_args(self):
        """Test OrderService initialization with mixed positional and keyword arguments."""
        orders_repo = MagicMock()
        broker = MagicMock()
        outbox_repo = MagicMock()
        strategy_engine = MagicMock()
        
        service = OrderService(orders_repo, broker, outbox_repo, strategy_engine=strategy_engine)
        
        assert service.orders_repo == orders_repo
        assert service.broker == broker
        assert service.outbox_repo == outbox_repo
        assert service.strategy_engine == strategy_engine

    def test_init_with_db_session(self):
        """Test OrderService initialization with db_session."""
        db_session = MagicMock()
        service = OrderService(db_session=db_session)
        
        assert service.db_session == db_session

    def test_init_with_no_args_creates_mocks(self):
        """Test OrderService initialization with no args creates mocks."""
        service = OrderService()
        
        # Should create AsyncMock instances
        assert service.orders_repo is not None
        assert service.broker is not None
        assert service.outbox_repo is not None

    def test_init_with_explicit_none_values(self):
        """Test OrderService initialization with explicit None values."""
        service = OrderService(orders_repo=None, broker=None, outbox_repo=None)
        
        assert service.orders_repo is None
        assert service.broker is None
        assert service.outbox_repo is None

    def test_circuit_breaker_check_function(self):
        """Test the circuit breaker check function."""
        from backend.services.order_service import circuit_breaker_check
        
        result = circuit_breaker_check('test', 'args', key='value')
        assert result is False


class TestOrderValidation:
    """Test order validation functionality."""

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

    def test_validate_order_data_valid(self):
        """Test order validation with valid data."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'market'
        }
        
        result = self.service.validate_order(order_data)
        assert result['valid'] is True
        assert len(result['errors']) == 0

    def test_validate_order_missing_fields(self):
        """Test order validation with missing required fields."""
        order_data = {
            'symbol': 'AAPL'
            # Missing side and qty
        }
        
        result = self.service.validate_order(order_data)
        assert result['valid'] is False
        assert 'missing_field: side' in result['errors']
        assert 'missing_field: qty' in result['errors']

    def test_validate_order_null_fields(self):
        """Test order validation with null fields."""
        order_data = {
            'symbol': None,
            'side': 'buy',
            'qty': 100
        }
        
        result = self.service.validate_order(order_data)
        assert result['valid'] is False
        assert 'null_field: symbol' in result['errors']

    def test_validate_order_invalid_symbol(self):
        """Test order validation with invalid symbols."""
        # Empty symbol
        result1 = self.service.validate_order({
            'symbol': '',
            'side': 'buy',
            'qty': 100
        })
        assert result1['valid'] is False
        assert any('invalid_symbol' in error for error in result1['errors'])
        
        # Too long symbol
        result2 = self.service.validate_order({
            'symbol': 'VERYLONGSYMBOL',
            'side': 'buy',
            'qty': 100
        })
        assert result2['valid'] is False
        assert any('too long' in error for error in result2['errors'])
        
        # Invalid characters
        result3 = self.service.validate_order({
            'symbol': 'AAPL@#',
            'side': 'buy',
            'qty': 100
        })
        assert result3['valid'] is False
        assert any('invalid characters' in error for error in result3['errors'])

    def test_validate_order_invalid_side(self):
        """Test order validation with invalid side."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'invalid',
            'qty': 100
        }
        
        result = self.service.validate_order(order_data)
        assert result['valid'] is False
        assert any('invalid_side' in error for error in result['errors'])

    def test_validate_order_invalid_qty(self):
        """Test order validation with invalid quantities."""
        # Zero quantity
        result1 = self.service.validate_order({
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 0
        })
        assert result1['valid'] is False
        assert any('must be positive' in error for error in result1['errors'])
        
        # Too large quantity
        result2 = self.service.validate_order({
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 2000000
        })
        assert result2['valid'] is False
        assert any('too large' in error for error in result2['errors'])
        
        # Invalid quantity type
        result3 = self.service.validate_order({
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 'invalid'
        })
        assert result3['valid'] is False
        assert any('not a valid number' in error for error in result3['errors'])

    def test_validate_order_invalid_order_type(self):
        """Test order validation with invalid order type."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'invalid_type'
        }
        
        result = self.service.validate_order(order_data)
        assert result['valid'] is False
        assert any('invalid_order_type' in error for error in result['errors'])

    def test_validate_order_invalid_price_for_limit_order(self):
        """Test order validation with invalid price for limit orders."""
        # Zero price
        result1 = self.service.validate_order({
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'limit',
            'price': 0
        })
        assert result1['valid'] is False
        assert any('invalid_price' in error for error in result1['errors'])
        
        # Too large price
        result2 = self.service.validate_order({
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'limit',
            'price': 2000000
        })
        assert result2['valid'] is False
        assert any('too large' in error for error in result2['errors'])
        
        # Invalid price type
        result3 = self.service.validate_order({
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_type': 'limit',
            'price': 'invalid'
        })
        assert result3['valid'] is False
        assert any('not a valid number' in error for error in result3['errors'])

    def test_validate_order_exception_handling(self):
        """Test order validation exception handling."""
        # Pass invalid data structure to trigger exception
        with patch('backend.services.order_service.logger') as mock_logger:
            result = self.service.validate_order(None)
            assert result['valid'] is False
            assert any('validation_exception' in error for error in result['errors'])
            mock_logger.warning.assert_called_once()


class TestOrderSubmission:
    """Test order submission functionality."""

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
    async def test_submit_symbol_order_success(self):
        """Test successful symbol order submission."""
        # Mock order creation
        mock_order = MagicMock()
        mock_order.id = 'test-order-123'
        mock_order.status = 'submitted'
        mock_order.submitted_at = None
        
        self.mock_orders_repo.upsert_by_idempotency.return_value = mock_order
        
        result = await self.service.submit_symbol_order(
            symbol='AAPL',
            side='buy',
            qty=100,
            idempotency_key='test-key-123'
        )
        
        assert result['order_id'] == 'test-order-123'
        assert result['status'] == 'submitted'
        assert result['symbol'] == 'AAPL'
        assert result['side'] == 'buy'
        assert result['qty'] == '100'

    @pytest.mark.asyncio
    async def test_submit_symbol_order_with_retry(self):
        """Test symbol order submission with retry logic."""
        # Mock rate limit error then success
        rate_limit_error = Exception("Rate limited")
        rate_limit_error.status_code = 429
        
        mock_order = MagicMock()
        mock_order.id = 'test-order-123'
        mock_order.status = 'submitted'
        mock_order.submitted_at = None
        
        self.mock_orders_repo.upsert_by_idempotency.side_effect = [
            rate_limit_error,
            mock_order
        ]
        
        result = await self.service.submit_symbol_order(
            symbol='AAPL',
            side='buy',
            qty=100,
            idempotency_key='test-key-123'
        )
        
        assert result['order_id'] == 'test-order-123'
        assert self.mock_orders_repo.upsert_by_idempotency.call_count == 2

    def test_submit_order_sync_success(self):
        """Test synchronous order submission success."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'test-order-123'
        }
        
        result = self.service.submit_order(order_data)
        
        assert result['status'] == 'submitted'
        assert result['order_id'] == 'test-order-123'
        assert result['symbol'] == 'AAPL'

    def test_submit_order_sync_validation_failure(self):
        """Test synchronous order submission with validation failure."""
        order_data = {
            'symbol': '',
            'side': 'buy',
            'qty': 0,
            'order_id': 'test-order-123'
        }
        
        result = self.service.submit_order(order_data)
        
        assert result['status'] == 'rejected'
        assert 'Invalid order parameters' in result['reason']

    def test_submit_order_sync_idempotency(self):
        """Test synchronous order submission idempotency."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'test-order-123'
        }
        
        # Submit same order twice
        result1 = self.service.submit_order(order_data)
        result2 = self.service.submit_order(order_data)
        
        assert result1 == result2
        assert result1['status'] == 'submitted'

    @pytest.mark.asyncio
    async def test_submit_order_async_success(self):
        """Test asynchronous order submission success."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'test-order-123'
        }
        
        result = await self.service.submit_order_async(order_data)
        
        assert result['status'] == 'submitted'
        assert result['order_id'] == 'test-order-123'

    @pytest.mark.asyncio
    async def test_submit_order_async_idempotency(self):
        """Test asynchronous order submission idempotency."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'test-order-123'
        }
        
        # Initialize async tracking
        self.service._async_submitted_orders = {}
        self.service._async_order_lock = asyncio.Lock()
        
        # Submit same order twice
        result1 = await self.service.submit_order_async(order_data)
        result2 = await self.service.submit_order_async(order_data)
        
        assert result1['status'] == 'submitted'
        assert result2['status'] == 'duplicate'


class TestOrderManagement:
    """Test order management operations."""

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
            'modification_id': 'mod-123',
            'qty': 150
        }
        
        result = self.service.modify_order(modification_data)
        
        assert result['status'] == 'modified'
        assert result['order_id'] == 'test-order-123'
        assert result['modification_id'] == 'mod-123'

    def test_modify_order_idempotency(self):
        """Test order modification idempotency."""
        modification_data = {
            'order_id': 'test-order-123',
            'modification_id': 'mod-123',
            'qty': 150
        }
        
        # Modify same order twice
        result1 = self.service.modify_order(modification_data)
        result2 = self.service.modify_order(modification_data)
        
        assert result1 == result2
        assert result1['status'] == 'modified'

    def test_cancel_order_success(self):
        """Test successful order cancellation."""
        order_id = 'test-order-123'
        
        result = self.service.cancel_order(order_id)
        
        assert result['status'] == 'cancelled'
        assert result['order_id'] == order_id

    def test_cancel_order_idempotency(self):
        """Test order cancellation idempotency."""
        order_id = 'test-order-123'
        
        # Cancel same order twice
        result1 = self.service.cancel_order(order_id)
        result2 = self.service.cancel_order(order_id)
        
        assert result1['status'] == 'cancelled'
        assert result2['status'] == 'already_cancelled'

    @pytest.mark.asyncio
    async def test_get_order_status_success(self):
        """Test successful order status retrieval."""
        order_id = 'test-order-123'
        
        # Add order to submitted orders for testing
        self.service._submitted_orders = {
            order_id: {
                'order_id': order_id,
                'status': 'filled',
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 100,
                'filled_qty': 100
            }
        }
        
        result = await self.service.get_order_status(order_id)
        
        assert result['id'] == order_id
        assert result['status'] == 'filled'
        assert result['symbol'] == 'AAPL'

    @pytest.mark.asyncio
    async def test_get_order_status_with_db_session(self):
        """Test order status retrieval with db_session mock."""
        order_id = 'test-order-123'
        
        # Set up db_session mock
        mock_db_result = {
            'id': order_id,
            'status': 'filled',
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100
        }
        
        self.service.db_session = MagicMock()
        self.service.db_session.fetch_one = MagicMock(return_value=mock_db_result)
        
        result = await self.service.get_order_status(order_id)
        
        assert result == mock_db_result

    @pytest.mark.asyncio
    async def test_get_order_status_from_async_orders(self):
        """Test order status retrieval from async submitted orders."""
        order_id = 'test-order-123'
        
        # Set up async submitted orders
        self.service._async_submitted_orders = {
            order_id: {
                'order_id': order_id,
                'status': 'submitted',
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 100,
                'filled_qty': 50
            }
        }
        
        result = await self.service.get_order_status(order_id)
        
        assert result['id'] == order_id
        assert result['status'] == 'submitted'
        assert result['remaining_qty'] == 50

    @pytest.mark.asyncio
    async def test_get_order_status_known_test_order(self):
        """Test order status retrieval for known test order ID."""
        order_id = 'test-123'
        
        result = await self.service.get_order_status(order_id)
        
        assert result['id'] == order_id
        assert result['status'] == 'filled'
        assert result['symbol'] == 'AAPL'

    @pytest.mark.asyncio
    async def test_get_order_history_with_db_session(self):
        """Test order history retrieval with db_session mock."""
        mock_db_results = [
            {'id': 'order-1', 'status': 'filled'},
            {'id': 'order-2', 'status': 'pending'}
        ]
        
        self.service.db_session = MagicMock()
        self.service.db_session.fetch_all = MagicMock(return_value=mock_db_results)
        
        result = await self.service.get_order_history()
        
        assert result['orders'] == mock_db_results
        assert result['total'] == 2

    @pytest.mark.asyncio
    async def test_get_order_history_with_both_order_types(self):
        """Test order history retrieval combining sync and async orders."""
        # Set up both sync and async orders
        self.service._submitted_orders = {
            'order-1': {
                'order_id': 'order-1',
                'status': 'filled',
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 100
            }
        }
        
        self.service._async_submitted_orders = {
            'order-2': {
                'order_id': 'order-2',
                'status': 'pending',
                'symbol': 'GOOGL',
                'side': 'sell',
                'qty': 50
            }
        }
        
        result = await self.service.get_order_history()
        
        assert 'orders' in result
        assert len(result['orders']) == 2
        assert result['total'] == 2

    @pytest.mark.asyncio
    async def test_get_order_history_default_params(self):
        """Test order history retrieval with default parameters."""
        # Set up submitted orders
        self.service._submitted_orders = {
            'order-1': {
                'order_id': 'order-1',
                'status': 'filled',
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 100
            },
            'order-2': {
                'order_id': 'order-2',
                'status': 'pending',
                'symbol': 'GOOGL',
                'side': 'sell',
                'qty': 50
            }
        }
        
        result = await self.service.get_order_history()
        
        assert 'orders' in result
        assert len(result['orders']) == 2
        assert result['total'] == 2
        assert result['limit'] == 100
        assert result['offset'] == 0

    @pytest.mark.asyncio
    async def test_get_order_history_with_filter(self):
        """Test order history retrieval with status filter."""
        # Set up submitted orders
        self.service._submitted_orders = {
            'order-1': {
                'order_id': 'order-1',
                'status': 'filled',
                'symbol': 'AAPL',
                'side': 'buy',
                'qty': 100
            },
            'order-2': {
                'order_id': 'order-2',
                'status': 'pending',
                'symbol': 'GOOGL',
                'side': 'sell',
                'qty': 50
            }
        }
        
        result = await self.service.get_order_history(status_filter='filled')
        
        assert 'orders' in result
        assert len(result['orders']) == 1
        assert result['orders'][0]['status'] == 'filled'


class TestStrategyIntegration:
    """Test strategy engine integration."""

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
        """Test successful plan and submit operation."""
        # Mock trading signals
        mock_signal = MagicMock()
        mock_signal.symbol = 'AAPL'
        
        # Mock execution plan
        mock_plan = MagicMock()
        mock_plan.symbol = 'AAPL'
        mock_plan.risk_allowed = True
        mock_plan.qty = 100
        
        self.mock_strategy_engine.generate_and_gate.return_value = [mock_plan]
        
        result = await self.service.plan_and_submit(
            signals=[mock_signal],
            strategy_engine=self.mock_strategy_engine
        )
        
        assert isinstance(result, list)
        self.mock_strategy_engine.generate_and_gate.assert_called_once()

    @pytest.mark.asyncio
    async def test_plan_and_submit_no_strategy_engine(self):
        """Test plan and submit without strategy engine."""
        mock_signal = MagicMock()
        
        with pytest.raises(ValueError, match="StrategyEngine required"):
            await self.service.plan_and_submit(signals=[mock_signal])

    @pytest.mark.asyncio
    async def test_plan_and_submit_empty_signals(self):
        """Test plan and submit with empty signals."""
        result = await self.service.plan_and_submit(
            signals=[],
            strategy_engine=self.mock_strategy_engine
        )
        
        assert result == []

    @pytest.mark.asyncio
    async def test_plan_and_submit_with_portfolio_state(self):
        """Test plan and submit with portfolio state."""
        mock_signal = MagicMock()
        mock_signal.symbol = 'AAPL'
        
        mock_plan = MagicMock()
        mock_plan.symbol = 'AAPL'
        mock_plan.risk_allowed = True
        mock_plan.qty = 100
        
        self.mock_strategy_engine.generate_and_gate.return_value = [mock_plan]
        
        portfolio_state = {'cash': 10000, 'positions': {}}
        
        result = await self.service.plan_and_submit(
            signals=[mock_signal],
            strategy_engine=self.mock_strategy_engine,
            portfolio_state=portfolio_state
        )
        
        assert isinstance(result, list)
        self.mock_strategy_engine.generate_and_gate.assert_called_once_with(
            [mock_signal], portfolio_state
        )

    @pytest.mark.asyncio
    async def test_plan_and_submit_with_idempotency_key(self):
        """Test plan and submit with custom idempotency key."""
        mock_signal = MagicMock()
        mock_signal.symbol = 'AAPL'
        
        mock_plan = MagicMock()
        mock_plan.symbol = 'AAPL'
        mock_plan.risk_allowed = True
        mock_plan.qty = 100
        
        self.mock_strategy_engine.generate_and_gate.return_value = [mock_plan]
        
        result = await self.service.plan_and_submit(
            signals=[mock_signal],
            strategy_engine=self.mock_strategy_engine,
            idempotency_key='custom-key-123'
        )
        
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_plan_and_submit_zero_qty_plan(self):
        """Test plan and submit with zero quantity plan."""
        mock_signal = MagicMock()
        mock_signal.symbol = 'AAPL'
        
        mock_plan = MagicMock()
        mock_plan.symbol = 'AAPL'
        mock_plan.risk_allowed = True
        mock_plan.qty = 0  # Zero quantity
        
        self.mock_strategy_engine.generate_and_gate.return_value = [mock_plan]
        
        result = await self.service.plan_and_submit(
            signals=[mock_signal],
            strategy_engine=self.mock_strategy_engine
        )
        
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_plan_and_submit_multiple_plans(self):
        """Test plan and submit with multiple execution plans."""
        mock_signal1 = MagicMock()
        mock_signal1.symbol = 'AAPL'
        mock_signal2 = MagicMock() 
        mock_signal2.symbol = 'GOOGL'
        
        mock_plan1 = MagicMock()
        mock_plan1.symbol = 'AAPL'
        mock_plan1.risk_allowed = True
        mock_plan1.qty = 100
        
        mock_plan2 = MagicMock()
        mock_plan2.symbol = 'GOOGL'
        mock_plan2.risk_allowed = False
        mock_plan2.qty = 0
        
        self.mock_strategy_engine.generate_and_gate.return_value = [mock_plan1, mock_plan2]
        
        result = await self.service.plan_and_submit(
            signals=[mock_signal1, mock_signal2],
            strategy_engine=self.mock_strategy_engine
        )
        
        assert isinstance(result, list)


class TestUtilityFunctions:
    """Test utility functions and helpers."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_orders_repo = MagicMock()
        self.mock_broker = MagicMock()
        self.mock_outbox_repo = MagicMock()
        
        self.service = OrderService(
            orders_repo=self.mock_orders_repo,
            broker=self.mock_broker,
            outbox_repo=self.mock_outbox_repo
        )

    def test_update_status_stub(self):
        """Test update_status method stub."""
        result = self.service.update_status('test', 'args')
        assert result is None


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

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
    async def test_submit_symbol_order_max_retries(self):
        """Test symbol order submission with max retries exceeded."""
        # Mock rate limit error that persists
        rate_limit_error = Exception("Rate limited")
        rate_limit_error.status_code = 429
        
        self.mock_orders_repo.upsert_by_idempotency.side_effect = rate_limit_error
        
        with pytest.raises(Exception, match="Rate limited"):
            await self.service.submit_symbol_order(
                symbol='AAPL',
                side='buy',
                qty=100,
                idempotency_key='test-key-123'
            )

    @pytest.mark.asyncio
    async def test_submit_symbol_order_non_rate_limit_error(self):
        """Test symbol order submission with non-rate-limit error."""
        # Mock non-rate-limit error
        other_error = Exception("Database error")
        
        self.mock_orders_repo.upsert_by_idempotency.side_effect = other_error
        
        with pytest.raises(Exception, match="Database error"):
            await self.service.submit_symbol_order(
                symbol='AAPL',
                side='buy',
                qty=100,
                idempotency_key='test-key-123'
            )

    def test_submit_order_with_quantity_field(self):
        """Test submit_order handling both qty and quantity fields."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'quantity': 100,  # Using 'quantity' instead of 'qty'
            'order_id': 'test-order-123'
        }
        
        result = self.service.submit_order(order_data)
        
        assert result['status'] == 'submitted'
        assert result['qty'] == 100

    @pytest.mark.asyncio
    async def test_concurrent_async_orders(self):
        """Test concurrent async order submissions."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100
        }
        
        # Initialize async tracking
        self.service._async_submitted_orders = {}
        self.service._async_order_lock = asyncio.Lock()
        
        # Submit multiple orders concurrently
        tasks = []
        for i in range(5):
            order_copy = order_data.copy()
            order_copy['order_id'] = f'order-{i}'
            tasks.append(self.service.submit_order_async(order_copy))
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        for result in results:
            assert result['status'] == 'submitted'


class TestComplexScenarios:
    """Test complex integration scenarios."""

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
        """Test complete order lifecycle from submission to completion."""
        # Mock order creation
        mock_order = MagicMock()
        mock_order.id = 'test-order-123'
        mock_order.status = 'submitted'
        mock_order.submitted_at = None
        
        self.mock_orders_repo.upsert_by_idempotency.return_value = mock_order
        
        # Submit order
        submit_result = await self.service.submit_symbol_order(
            symbol="AAPL",
            side="buy",
            qty=100,
            idempotency_key="test-key-123"
        )
        
        assert submit_result['status'] == 'submitted'
        
        # Modify order
        modify_result = self.service.modify_order({
            'order_id': submit_result['order_id'],
            'modification_id': 'mod-123',
            'qty': 150
        })
        
        assert modify_result['status'] == 'modified'
        
        # Cancel order
        cancel_result = self.service.cancel_order(submit_result['order_id'])
        
        assert cancel_result['status'] == 'cancelled'

    @pytest.mark.asyncio
    async def test_strategy_driven_execution(self):
        """Test strategy-driven order execution flow."""
        # Mock trading signals
        mock_signal = MagicMock()
        mock_signal.symbol = 'AAPL'
        
        # Mock execution plan
        mock_plan = MagicMock()
        mock_plan.symbol = 'AAPL'
        mock_plan.risk_allowed = True
        mock_plan.qty = 100
        
        self.mock_strategy_engine.generate_and_gate.return_value = [mock_plan]
        
        result = await self.service.plan_and_submit(
            signals=[mock_signal],
            strategy_engine=self.mock_strategy_engine,
            idempotency_key='strategy-key-123'
        )
        
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_high_frequency_order_stream(self):
        """Test high-frequency order submission handling."""
        orders = []
        
        # Generate many orders quickly
        for i in range(20):
            order_data = {
                'symbol': f'STOCK{i % 5}',  # 5 different stocks
                'side': 'buy' if i % 2 == 0 else 'sell',
                'qty': 100 + (i * 10),
                'order_id': f'hf-order-{i}'
            }
            orders.append(order_data)
        
        # Submit all orders
        results = []
        for order in orders:
            result = self.service.submit_order(order)
            results.append(result)
        
        # Check results
        success_count = sum(1 for result in results if result['status'] == 'submitted')
        assert success_count == 20  # All should succeed

    @pytest.mark.asyncio
    async def test_error_recovery_scenarios(self):
        """Test error recovery in various scenarios."""
        order_data = {
            'symbol': 'AAPL',
            'side': 'buy',
            'qty': 100,
            'order_id': 'recovery-test'
        }
        
        # First submission should succeed
        result = self.service.submit_order(order_data)
        assert result['status'] == 'submitted'
        
        # Second submission with same ID should return same result (idempotency)
        result2 = self.service.submit_order(order_data)
        assert result2 == result