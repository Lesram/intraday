"""
Comprehensive tests for PositionReconciliationService
Tests order-position reconciliation with Alpaca broker
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from backend.services.position_reconciliation_service import PositionReconciliationService


class TestPositionReconciliationInit:
    """Test PositionReconciliationService initialization"""
    
    def test_init_with_dependencies(self):
        """Test initialization with db and alpaca client"""
        mock_db = MagicMock()
        mock_alpaca = MagicMock()
        
        service = PositionReconciliationService(mock_db, mock_alpaca)
        
        assert service.db == mock_db
        assert service.alpaca_client == mock_alpaca


class TestGetPositionStatusForOrders:
    """Test get_position_status_for_orders method"""
    
    @pytest.fixture
    def mock_db_session(self):
        """Create mock async database session"""
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        return mock_db
        
    @pytest.fixture
    def mock_alpaca_client(self):
        """Create mock Alpaca client"""
        mock_client = MagicMock()
        mock_client.get_positions = AsyncMock(return_value=[])
        return mock_client
        
    @pytest.fixture
    def reconciliation_service(self, mock_db_session, mock_alpaca_client):
        """Create service instance"""
        return PositionReconciliationService(mock_db_session, mock_alpaca_client)
        
    @pytest.mark.asyncio
    async def test_empty_order_list(self, reconciliation_service, mock_db_session):
        """Test with empty order list"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        result = await reconciliation_service.get_position_status_for_orders([])
        
        assert result == {}
        
    @pytest.mark.asyncio
    async def test_buy_order_with_open_position(
        self, reconciliation_service, mock_db_session, mock_alpaca_client
    ):
        """Test filled buy order that's still open at Alpaca"""
        # Mock order
        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.symbol = "AAPL"
        mock_order.side = "buy"
        mock_order.status = "filled"
        mock_order.filled_qty = 100
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        # Mock Alpaca position
        mock_alpaca_client.get_positions = AsyncMock(return_value=[{
            "symbol": "AAPL",
            "qty": 100,
            "current_price": 150.0,
            "unrealized_pl": 500.0
        }])
        
        result = await reconciliation_service.get_position_status_for_orders(["order-123"])
        
        assert "order-123" in result
        assert result["order-123"]["position_status"] == "open"
        assert result["order-123"]["current_qty"] == 100.0
        
    @pytest.mark.asyncio
    async def test_buy_order_with_closed_position(
        self, reconciliation_service, mock_db_session, mock_alpaca_client
    ):
        """Test filled buy order with position no longer at Alpaca"""
        mock_order = MagicMock()
        mock_order.id = "order-456"
        mock_order.symbol = "MSFT"
        mock_order.side = "buy"
        mock_order.status = "filled"
        mock_order.filled_qty = 50
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        # No MSFT position at Alpaca
        mock_alpaca_client.get_positions = AsyncMock(return_value=[])
        
        result = await reconciliation_service.get_position_status_for_orders(["order-456"])
        
        assert "order-456" in result
        assert result["order-456"]["position_status"] == "closed"
        assert result["order-456"]["current_qty"] is None
        
    @pytest.mark.asyncio
    async def test_partially_closed_position(
        self, reconciliation_service, mock_db_session, mock_alpaca_client
    ):
        """Test position with partial close"""
        # Bought 100 shares but only 40 remain
        mock_order = MagicMock()
        mock_order.id = "order-789"
        mock_order.symbol = "GOOGL"
        mock_order.side = "buy"
        mock_order.status = "filled"
        mock_order.filled_qty = 100
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        # Only 40 shares remain
        mock_alpaca_client.get_positions = AsyncMock(return_value=[{
            "symbol": "GOOGL",
            "qty": 40,
            "current_price": 140.0,
            "unrealized_pl": -200.0
        }])
        
        result = await reconciliation_service.get_position_status_for_orders(["order-789"])
        
        assert "order-789" in result
        assert result["order-789"]["position_status"] == "partially_closed"
        assert result["order-789"]["current_qty"] == 40.0
        
    @pytest.mark.asyncio
    async def test_sell_order_status(
        self, reconciliation_service, mock_db_session, mock_alpaca_client
    ):
        """Test sell order returns closed_by_sell status"""
        mock_order = MagicMock()
        mock_order.id = "sell-order-123"
        mock_order.symbol = "TSLA"
        mock_order.side = "sell"
        mock_order.status = "filled"
        mock_order.filled_qty = 25
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        mock_alpaca_client.get_positions = AsyncMock(return_value=[])
        
        result = await reconciliation_service.get_position_status_for_orders(["sell-order-123"])
        
        assert "sell-order-123" in result
        assert result["sell-order-123"]["position_status"] == "closed_by_sell"
        
    @pytest.mark.asyncio
    async def test_pending_order_status(
        self, reconciliation_service, mock_db_session, mock_alpaca_client
    ):
        """Test pending order returns not_applicable status"""
        mock_order = MagicMock()
        mock_order.id = "pending-123"
        mock_order.symbol = "AMZN"
        mock_order.side = "buy"
        mock_order.status = "pending"  # Not filled yet
        mock_order.filled_qty = 0
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order]
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        mock_alpaca_client.get_positions = AsyncMock(return_value=[])
        
        result = await reconciliation_service.get_position_status_for_orders(["pending-123"])
        
        assert "pending-123" in result
        assert result["pending-123"]["position_status"] == "not_applicable"
        
    @pytest.mark.asyncio
    async def test_error_handling(
        self, reconciliation_service, mock_db_session, mock_alpaca_client
    ):
        """Test error handling returns unknown status"""
        mock_alpaca_client.get_positions = AsyncMock(
            side_effect=Exception("API error")
        )
        
        result = await reconciliation_service.get_position_status_for_orders(["order-error"])
        
        assert "order-error" in result
        assert result["order-error"]["position_status"] == "unknown"
        assert "Error" in result["order-error"]["note"]


class TestGetReconciliationSummary:
    """Test get_reconciliation_summary method"""
    
    @pytest.fixture
    def mock_db_session(self):
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        return mock_db
        
    @pytest.fixture
    def mock_alpaca_client(self):
        mock_client = MagicMock()
        mock_client.get_positions = AsyncMock(return_value=[])
        return mock_client
        
    @pytest.fixture
    def reconciliation_service(self, mock_db_session, mock_alpaca_client):
        return PositionReconciliationService(mock_db_session, mock_alpaca_client)
        
    @pytest.mark.asyncio
    async def test_summary_with_no_orders(self, reconciliation_service, mock_db_session):
        """Test summary with no filled orders"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        summary = await reconciliation_service.get_reconciliation_summary()
        
        assert summary["total_filled_buys"] == 0
        assert summary["open_positions"] == 0
        assert summary["closed_positions"] == 0
        assert summary["discrepancies"] == []
        
    @pytest.mark.asyncio
    async def test_summary_with_mixed_positions(
        self, reconciliation_service, mock_db_session, mock_alpaca_client
    ):
        """Test summary with open and closed positions"""
        # Create mock orders
        mock_order1 = MagicMock()
        mock_order1.id = "order-1"
        mock_order1.symbol = "AAPL"
        mock_order1.side = "buy"
        mock_order1.status = "filled"
        mock_order1.filled_qty = 100
        mock_order1.submitted_at = datetime.now()
        
        mock_order2 = MagicMock()
        mock_order2.id = "order-2"
        mock_order2.symbol = "MSFT"
        mock_order2.side = "buy"
        mock_order2.status = "filled"
        mock_order2.filled_qty = 50
        mock_order2.submitted_at = datetime.now()
        
        # First query returns orders, subsequent queries for sell orders
        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = [mock_order1, mock_order2]
        
        mock_result_no_sell = MagicMock()
        mock_result_no_sell.scalar_one_or_none.return_value = None
        
        mock_db_session.execute = AsyncMock(side_effect=[
            mock_result1,  # Initial query for filled buys
            mock_result1,  # Query for position status
            mock_result_no_sell,  # Check for sell order 1
            mock_result_no_sell,  # Check for sell order 2
        ])
        
        # Only AAPL has open position
        mock_alpaca_client.get_positions = AsyncMock(return_value=[{
            "symbol": "AAPL",
            "qty": 100,
            "current_price": 175.0,
            "unrealized_pl": 1000.0
        }])
        
        summary = await reconciliation_service.get_reconciliation_summary()
        
        assert summary["total_filled_buys"] == 2
        
    @pytest.mark.asyncio
    async def test_summary_error_handling(
        self, reconciliation_service, mock_db_session
    ):
        """Test summary returns error info on exception"""
        mock_db_session.execute = AsyncMock(side_effect=Exception("Database error"))
        
        summary = await reconciliation_service.get_reconciliation_summary()
        
        assert "error" in summary
        assert summary["total_filled_buys"] == 0


class TestMultipleOrdersSameSymbol:
    """Test reconciliation with multiple orders for same symbol"""
    
    @pytest.fixture
    def mock_db_session(self):
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        return mock_db
        
    @pytest.fixture
    def mock_alpaca_client(self):
        mock_client = MagicMock()
        mock_client.get_positions = AsyncMock(return_value=[])
        return mock_client
        
    @pytest.fixture
    def reconciliation_service(self, mock_db_session, mock_alpaca_client):
        return PositionReconciliationService(mock_db_session, mock_alpaca_client)
        
    @pytest.mark.asyncio
    async def test_multiple_buys_same_symbol_all_open(
        self, reconciliation_service, mock_db_session, mock_alpaca_client
    ):
        """Test multiple buy orders same symbol - all open"""
        # Two buy orders for AAPL totaling 150 shares
        mock_order1 = MagicMock()
        mock_order1.id = "order-1"
        mock_order1.symbol = "AAPL"
        mock_order1.side = "buy"
        mock_order1.status = "filled"
        mock_order1.filled_qty = 100
        
        mock_order2 = MagicMock()
        mock_order2.id = "order-2"
        mock_order2.symbol = "AAPL"
        mock_order2.side = "buy"
        mock_order2.status = "filled"
        mock_order2.filled_qty = 50
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_order1, mock_order2]
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        
        # Alpaca has 150 shares
        mock_alpaca_client.get_positions = AsyncMock(return_value=[{
            "symbol": "AAPL",
            "qty": 150,
            "current_price": 175.0,
            "unrealized_pl": 500.0
        }])
        
        result = await reconciliation_service.get_position_status_for_orders(["order-1", "order-2"])
        
        assert result["order-1"]["position_status"] == "open"
        assert result["order-2"]["position_status"] == "open"
