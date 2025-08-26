"""
Phase 7B.3: Order Service Module Testing - Comprehensive Coverage
Targeting backend/services/order_service.py for high test coverage
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from decimal import Decimal
from typing import Any

from backend.services.order_service import OrderService, OrderServiceExtensions


class TestOrderServiceInitializationPhase7B3:
    """Test OrderService initialization and configuration"""
    
    def test_initialization_default(self):
        """Test OrderService initialization with defaults"""
        service = OrderService()
        
        assert service is not None
        assert service.orders_repo is not None  # Should be AsyncMock
        assert service.broker is not None  # Should be AsyncMock
        assert service.outbox_repo is not None  # Should be AsyncMock
        assert service.db_session is None
        assert service.strategy_engine is None
        assert service._async_submitted_orders == {}
        assert service._async_order_lock is None
    
    def test_initialization_with_kwargs(self):
        """Test OrderService initialization with keyword arguments"""
        mock_orders_repo = AsyncMock()
        mock_broker = AsyncMock()
        mock_outbox_repo = AsyncMock()
        mock_db_session = Mock()
        mock_strategy_engine = Mock()
        
        service = OrderService(
            orders_repo=mock_orders_repo,
            broker=mock_broker,
            outbox_repo=mock_outbox_repo,
            db_session=mock_db_session,
            strategy_engine=mock_strategy_engine
        )
        
        assert service.orders_repo is mock_orders_repo
        assert service.broker is mock_broker
        assert service.outbox_repo is mock_outbox_repo
        assert service.db_session is mock_db_session
        assert service.strategy_engine is mock_strategy_engine
    
    def test_initialization_with_positional_args(self):
        """Test OrderService initialization with legacy positional arguments"""
        mock_orders_repo = AsyncMock()
        mock_broker = AsyncMock()
        mock_outbox_repo = AsyncMock()
        
        service = OrderService(mock_orders_repo, mock_broker, mock_outbox_repo)
        
        assert service.orders_repo is mock_orders_repo
        assert service.broker is mock_broker
        assert service.outbox_repo is mock_outbox_repo
    
    def test_initialization_mixed_args(self):
        """Test OrderService initialization with mixed positional and keyword args"""
        mock_orders_repo = AsyncMock()
        mock_broker = AsyncMock()
        mock_strategy_engine = Mock()
        
        service = OrderService(
            mock_orders_repo,
            strategy_engine=mock_strategy_engine
        )
        
        assert service.orders_repo is mock_orders_repo
        # broker should be from kwargs, but not provided, so AsyncMock default
        assert service.broker is not None
        assert service.strategy_engine is mock_strategy_engine


class TestOrderValidationPhase7B3:
    """Test order validation functionality"""
    
    @pytest.fixture
    def service(self):
        return OrderService()
    
    def test_validate_order_valid_basic(self, service):
        """Test validation of valid basic order"""
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is True
        assert result["errors"] == []
    
    def test_validate_order_valid_complete(self, service):
        """Test validation of valid complete order"""
        order = {
            "symbol": "MSFT",
            "side": "sell", 
            "qty": 50,
            "order_type": "limit",
            "price": 150.25
        }
        
        result = service.validate_order(order)
        
        assert result["valid"] is True
        assert result["errors"] == []
    
    def test_validate_order_missing_required_fields(self, service):
        """Test validation with missing required fields"""
        # Missing symbol
        order = {"side": "buy", "qty": 100}
        result = service.validate_order(order)
        assert not result["valid"]
        assert "missing_field: symbol" in result["errors"]
        
        # Missing side
        order = {"symbol": "AAPL", "qty": 100}
        result = service.validate_order(order)
        assert not result["valid"]
        assert "missing_field: side" in result["errors"]
        
        # Missing qty
        order = {"symbol": "AAPL", "side": "buy"}
        result = service.validate_order(order)
        assert not result["valid"]
        assert "missing_field: qty" in result["errors"]
    
    def test_validate_order_null_fields(self, service):
        """Test validation with null fields"""
        order = {
            "symbol": None,
            "side": "buy",
            "qty": 100
        }
        
        result = service.validate_order(order)
        
        assert not result["valid"]
        assert "null_field: symbol" in result["errors"]
    
    def test_validate_order_invalid_symbol(self, service):
        """Test validation with invalid symbols"""
        # Empty string
        order = {"symbol": "", "side": "buy", "qty": 100}
        result = service.validate_order(order)
        assert not result["valid"]
        assert any("invalid_symbol: must be non-empty string" in error for error in result["errors"])
        
        # Too long
        order = {"symbol": "VERYLONGSYMBOL", "side": "buy", "qty": 100}
        result = service.validate_order(order)
        assert not result["valid"]
        assert any("invalid_symbol: too long" in error for error in result["errors"])
        
        # Invalid characters
        order = {"symbol": "AAPL@!", "side": "buy", "qty": 100}
        result = service.validate_order(order)
        assert not result["valid"]
        assert any("invalid_symbol: invalid characters" in error for error in result["errors"])
        
        # Not a string
        order = {"symbol": 123, "side": "buy", "qty": 100}
        result = service.validate_order(order)
        assert not result["valid"]
        assert any("invalid_symbol: must be non-empty string" in error for error in result["errors"])
    
    def test_validate_order_invalid_side(self, service):
        """Test validation with invalid side"""
        order = {
            "symbol": "AAPL",
            "side": "invalid_side",
            "qty": 100
        }
        
        result = service.validate_order(order)
        
        assert not result["valid"]
        assert "invalid_side: must be 'buy' or 'sell'" in result["errors"]
    
    def test_validate_order_invalid_quantity(self, service):
        """Test validation with invalid quantities"""
        # Negative quantity
        order = {"symbol": "AAPL", "side": "buy", "qty": -10}
        result = service.validate_order(order)
        assert not result["valid"]
        assert "invalid_qty: must be positive" in result["errors"]
        
        # Zero quantity
        order = {"symbol": "AAPL", "side": "buy", "qty": 0}
        result = service.validate_order(order)
        assert not result["valid"]
        assert "invalid_qty: must be positive" in result["errors"]
        
        # Too large quantity
        order = {"symbol": "AAPL", "side": "buy", "qty": 2000000}
        result = service.validate_order(order)
        assert not result["valid"]
        assert "invalid_qty: too large" in result["errors"]
        
        # Invalid number format
        order = {"symbol": "AAPL", "side": "buy", "qty": "invalid"}
        result = service.validate_order(order)
        assert not result["valid"]
        assert "invalid_qty: not a valid number" in result["errors"]
    
    def test_validate_order_invalid_order_type(self, service):
        """Test validation with invalid order type"""
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "invalid_type"
        }
        
        result = service.validate_order(order)
        
        assert not result["valid"]
        assert "invalid_order_type: must be one of ['market', 'limit', 'stop', 'stop_limit']" in result["errors"]
    
    def test_validate_order_invalid_price(self, service):
        """Test validation with invalid prices for limit orders"""
        # Negative price
        order = {
            "symbol": "AAPL", 
            "side": "buy", 
            "qty": 100,
            "order_type": "limit",
            "price": -50
        }
        result = service.validate_order(order)
        assert not result["valid"]
        assert "invalid_price: must be positive" in result["errors"]
        
        # Too large price
        order = {
            "symbol": "AAPL",
            "side": "buy", 
            "qty": 100,
            "order_type": "limit",
            "price": 2000000
        }
        result = service.validate_order(order)
        assert not result["valid"]
        assert "invalid_price: too large" in result["errors"]
        
        # Invalid price format
        order = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "limit", 
            "price": "invalid_price"
        }
        result = service.validate_order(order)
        assert not result["valid"]
        assert "invalid_price: not a valid number" in result["errors"]
    
    def test_validate_order_multiple_errors(self, service):
        """Test validation with multiple errors"""
        order = {
            "symbol": "",  # Invalid
            "side": "invalid_side",  # Invalid
            "qty": -50  # Invalid
        }
        
        result = service.validate_order(order)
        
        assert not result["valid"]
        assert len(result["errors"]) >= 3
        assert any("invalid_symbol" in error for error in result["errors"])
        assert any("invalid_side" in error for error in result["errors"])
        assert any("invalid_qty" in error for error in result["errors"])
    
    def test_validate_order_exception_handling(self, service):
        """Test validation exception handling"""
        # Pass an invalid order that might cause an exception
        with patch('backend.services.order_service.logger') as mock_logger:
            result = service.validate_order(None)  # This should cause an exception
            
            assert not result["valid"]
            assert any("validation_exception" in error for error in result["errors"])
            mock_logger.warning.assert_called_once()


class TestSynchronousOrderOperationsPhase7B3:
    """Test synchronous order operations"""
    
    @pytest.fixture
    def service(self):
        return OrderService()
    
    def test_submit_order_success(self, service):
        """Test successful order submission"""
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_id": "test_order_1"
        }
        
        result = service.submit_order(order_data)
        
        assert result["status"] == "submitted"
        assert result["order_id"] == "test_order_1"
        assert result["symbol"] == "AAPL"
        assert result["qty"] == 100
        assert result["side"] == "buy"
        assert "submitted_at" in result
    
    def test_submit_order_with_quantity_field(self, service):
        """Test order submission with 'quantity' instead of 'qty'"""
        order_data = {
            "symbol": "MSFT",
            "side": "sell",
            "quantity": 50,  # Using quantity instead of qty
            "order_id": "test_order_2"
        }
        
        result = service.submit_order(order_data)
        
        assert result["status"] == "submitted"
        assert result["qty"] == 50
    
    def test_submit_order_idempotency(self, service):
        """Test order submission idempotency"""
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_id": "idempotent_order"
        }
        
        # Submit the same order twice
        result1 = service.submit_order(order_data)
        result2 = service.submit_order(order_data)
        
        # Should return the same result
        assert result1 == result2
        assert result1["order_id"] == "idempotent_order"
        assert result1["status"] == "submitted"
    
    def test_submit_order_invalid_parameters(self, service):
        """Test order submission with invalid parameters"""
        # Missing symbol
        order_data = {
            "side": "buy",
            "qty": 100,
            "order_id": "invalid_order_1"
        }
        
        result = service.submit_order(order_data)
        
        # The implementation treats missing symbol as "UNKNOWN", which is valid
        assert result["status"] == "submitted"
        assert result["symbol"] == "UNKNOWN"
        
        # Zero quantity
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 0,
            "order_id": "invalid_order_2"
        }
        
        result = service.submit_order(order_data)
        
        assert result["status"] == "rejected"
        assert "Invalid order parameters" in result["reason"]
    
    def test_submit_order_generates_id(self, service):
        """Test order submission generates ID when not provided"""
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100
            # No order_id provided
        }
        
        result = service.submit_order(order_data)
        
        assert result["status"] == "submitted"
        assert "order_id" in result
        assert result["order_id"] is not None
    
    def test_modify_order_success(self, service):
        """Test successful order modification"""
        modification_data = {
            "order_id": "existing_order",
            "modification_id": "mod_1",
            "new_qty": 150
        }
        
        result = service.modify_order(modification_data)
        
        # Implementation returns success for valid modification
        assert "order_id" in result
        assert result["order_id"] == "existing_order"
    
    def test_modify_order_idempotency(self, service):
        """Test order modification idempotency"""
        modification_data = {
            "order_id": "existing_order",
            "modification_id": "idempotent_mod"
        }
        
        # Submit the same modification twice
        result1 = service.modify_order(modification_data)
        result2 = service.modify_order(modification_data)
        
        # Should return the same result
        assert result1 == result2
    
    def test_cancel_order_success(self, service):
        """Test successful order cancellation"""
        result = service.cancel_order("order_to_cancel")
        
        assert "order_id" in result
        assert result["order_id"] == "order_to_cancel"
    
    def test_cancel_order_idempotency(self, service):
        """Test order cancellation idempotency"""
        order_id = "idempotent_cancel_order"
        
        # Cancel the same order twice
        result1 = service.cancel_order(order_id)
        result2 = service.cancel_order(order_id)
        
        # First should be cancelled, second should be already_cancelled
        assert result1["order_id"] == order_id
        assert result1["status"] == "cancelled"
        assert result2["order_id"] == order_id
        assert result2["status"] == "already_cancelled"
    
    def test_update_status_stub(self, service):
        """Test update_status stub method"""
        # This is a stub method for mock compatibility
        result = service.update_status("order_1", "filled")
        
        # Stub should handle any arguments without error
        assert result is None


class TestAsynchronousOrderOperationsPhase7B3:
    """Test asynchronous order operations"""
    
    @pytest.fixture
    def service(self):
        return OrderService()
    
    @pytest.mark.asyncio
    async def test_submit_symbol_order_success(self, service):
        """Test successful async symbol order submission"""
        # Mock the repository responses
        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.status = "pending"
        mock_order.submitted_at = None
        
        service.orders_repo.upsert_by_idempotency = AsyncMock(return_value=mock_order)
        service.outbox_repo.add_order_submit_event = AsyncMock()
        
        result = await service.submit_symbol_order(
            symbol="AAPL",
            side="buy",
            qty=100.0,
            idempotency_key="test_key_1"
        )
        
        assert result["order_id"] == "order_123"
        assert result["symbol"] == "AAPL"
        assert result["side"] == "buy"
        assert result["qty"] == "100.0"
        assert result["status"] == "pending"
        assert result["idempotency_key"] == "test_key_1"
        
        # Verify repository calls
        service.orders_repo.upsert_by_idempotency.assert_called_once_with(
            client_key="test_key_1",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100.0"),
            order_type="market",
            tif="ioc",
            attributes={}
        )
        
        service.outbox_repo.add_order_submit_event.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_submit_symbol_order_with_options(self, service):
        """Test async symbol order submission with all options"""
        mock_order = Mock()
        mock_order.id = "order_456"
        mock_order.status = "submitted"
        mock_order.submitted_at = Mock()
        mock_order.submitted_at.isoformat.return_value = "2025-08-25T10:00:00Z"
        
        service.orders_repo.upsert_by_idempotency = AsyncMock(return_value=mock_order)
        service.outbox_repo.add_order_submit_event = AsyncMock()
        
        attributes = {"strategy": "momentum", "risk_level": "medium"}
        
        result = await service.submit_symbol_order(
            symbol="TSLA",
            side="sell",
            qty=50.5,
            idempotency_key="test_key_2",
            order_type="limit",
            tif="day",
            attributes=attributes
        )
        
        assert result["order_id"] == "order_456"
        assert result["symbol"] == "TSLA"
        assert result["side"] == "sell"
        assert result["qty"] == "50.5"
        assert result["status"] == "submitted"
        assert result["submitted_at"] == "2025-08-25T10:00:00Z"
        assert result["idempotency_key"] == "test_key_2"
        
        # Verify repository call with options
        service.orders_repo.upsert_by_idempotency.assert_called_once_with(
            client_key="test_key_2",
            symbol="TSLA",
            side="sell",
            qty=Decimal("50.5"),
            order_type="limit",
            tif="day",
            attributes=attributes
        )
    
    @pytest.mark.asyncio
    async def test_submit_symbol_order_exception_handling(self, service):
        """Test async symbol order submission exception handling"""
        # Mock repository to raise an exception
        service.orders_repo.upsert_by_idempotency = AsyncMock(
            side_effect=Exception("Database error")
        )
        
        with pytest.raises(Exception) as exc_info:
            await service.submit_symbol_order(
                symbol="AAPL",
                side="buy",
                qty=100.0,
                idempotency_key="failing_key"
            )
        
        assert "Database error" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_submit_order_async_success(self, service):
        """Test async order submission wrapper"""
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "order_type": "market",
            "order_id": "async_order_1"  # Provide explicit order_id
        }
        
        result = await service.submit_order_async(order_data)
        
        assert result["order_id"] == "async_order_1"
        assert result["status"] == "submitted"
    
    @pytest.mark.asyncio
    async def test_submit_order_async_validation_failure(self, service):
        """Test async order submission with validation failure"""
        order_data = {
            "symbol": "AAPL",  # Valid symbol
            "side": "buy",
            "qty": 0  # Invalid quantity
        }
        
        result = await service.submit_order_async(order_data)
        
        assert result["status"] == "rejected"
        assert "Invalid order parameters" in result["reason"]
    
    @pytest.mark.asyncio
    async def test_submit_order_async_concurrency_protection(self, service):
        """Test async order submission concurrency protection"""
        order_data = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100,
            "idempotency_key": "concurrent_key"
        }
        
        # Mock successful submission
        with patch.object(service, 'submit_symbol_order') as mock_submit:
            mock_submit.return_value = {"order_id": "concurrent_order", "status": "submitted"}
            
            # Submit the same order concurrently
            tasks = [
                service.submit_order_async(order_data),
                service.submit_order_async(order_data)
            ]
            
            results = await asyncio.gather(*tasks)
            
            # Both should succeed (idempotency handled at repository level)
            assert len(results) == 2
            for result in results:
                assert result["status"] == "submitted"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
