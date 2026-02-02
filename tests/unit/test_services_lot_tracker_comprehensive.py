"""
Phase 7: Comprehensive tests for LotTrackerService
Coverage target: 85%+
Tests FIFO lot matching, position lots, and realized trades.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC
from decimal import Decimal
import uuid


# ============================================================================
# LOT TRACKER CLASS TESTS
# ============================================================================

class TestLotTrackerInit:
    """Test LotTracker initialization."""
    
    def test_init_with_session(self):
        """Test LotTracker initializes with session."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = MagicMock()
        tracker = LotTracker(mock_session)
        
        assert tracker.session is mock_session
    
    def test_lot_tracker_module_imports(self):
        """Test module imports work correctly."""
        from backend.services.lot_tracker_service import LotTracker
        from backend.infra.schemas import PositionLot, RealizedTrade
        
        assert LotTracker is not None
        assert PositionLot is not None
        assert RealizedTrade is not None


class TestCreateLot:
    """Test LotTracker.create_lot method."""
    
    @pytest.mark.asyncio
    async def test_create_lot_success(self):
        """Test successful lot creation."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        tracker = LotTracker(mock_session)
        
        user_id = "user123"
        symbol = "AAPL"
        qty = Decimal("10")
        cost_basis = Decimal("150.50")
        order_id = uuid.uuid4()
        open_date = datetime.now(UTC)
        
        lot = await tracker.create_lot(
            user_id=user_id,
            symbol=symbol,
            qty=qty,
            cost_basis=cost_basis,
            order_id=order_id,
            open_date=open_date
        )
        
        assert lot.user_id == user_id
        assert lot.symbol == symbol
        assert lot.qty == qty
        assert lot.remaining_qty == qty
        assert lot.cost_basis == cost_basis
        assert lot.order_id == order_id
        assert lot.status == "open"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
    
    @pytest.mark.asyncio
    async def test_create_lot_generates_uuid(self):
        """Test lot creation generates unique UUID."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        tracker = LotTracker(mock_session)
        
        lot = await tracker.create_lot(
            user_id="user123",
            symbol="MSFT",
            qty=Decimal("5"),
            cost_basis=Decimal("300.00"),
            order_id=uuid.uuid4(),
            open_date=datetime.now(UTC)
        )
        
        assert lot.id is not None
        assert isinstance(lot.id, uuid.UUID)
    
    @pytest.mark.asyncio
    async def test_create_lot_with_decimal_precision(self):
        """Test lot creation with high precision decimals."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        tracker = LotTracker(mock_session)
        
        qty = Decimal("10.123456")
        cost_basis = Decimal("150.987654")
        
        lot = await tracker.create_lot(
            user_id="user123",
            symbol="GOOGL",
            qty=qty,
            cost_basis=cost_basis,
            order_id=uuid.uuid4(),
            open_date=datetime.now(UTC)
        )
        
        assert lot.qty == qty
        assert lot.cost_basis == cost_basis


class TestCloseLotsFifo:
    """Test LotTracker.close_lots_fifo method."""
    
    @pytest.mark.asyncio
    async def test_close_lots_fifo_no_open_lots_raises(self):
        """Test closing lots when no open lots exist raises ValueError."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        
        with pytest.raises(ValueError, match="No open lots found"):
            await tracker.close_lots_fifo(
                user_id="user123",
                symbol="AAPL",
                qty_to_close=Decimal("10"),
                close_price=Decimal("160.00"),
                close_order_id=uuid.uuid4(),
                close_date=datetime.now(UTC)
            )
    
    @pytest.mark.asyncio
    async def test_close_lots_fifo_insufficient_quantity_raises(self):
        """Test closing more than available raises ValueError."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        # Create mock lot with only 5 shares
        mock_lot = MagicMock()
        mock_lot.id = uuid.uuid4()
        mock_lot.remaining_qty = Decimal("5")
        mock_lot.cost_basis = Decimal("150.00")
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        
        with pytest.raises(ValueError, match="Insufficient lots"):
            await tracker.close_lots_fifo(
                user_id="user123",
                symbol="AAPL",
                qty_to_close=Decimal("10"),  # Try to close more than available
                close_price=Decimal("160.00"),
                close_order_id=uuid.uuid4(),
                close_date=datetime.now(UTC)
            )
    
    @pytest.mark.asyncio
    async def test_close_lots_fifo_single_lot_full_close(self):
        """Test closing exactly one full lot."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        # Create mock lot with 10 shares
        mock_lot = MagicMock()
        mock_lot.id = uuid.uuid4()
        mock_lot.user_id = "user123"
        mock_lot.symbol = "AAPL"
        mock_lot.remaining_qty = Decimal("10")
        mock_lot.cost_basis = Decimal("150.00")
        mock_lot.order_id = uuid.uuid4()
        mock_lot.open_date = datetime.now(UTC)
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        
        trades = await tracker.close_lots_fifo(
            user_id="user123",
            symbol="AAPL",
            qty_to_close=Decimal("10"),
            close_price=Decimal("160.00"),
            close_order_id=uuid.uuid4(),
            close_date=datetime.now(UTC)
        )
        
        assert len(trades) == 1
        assert mock_lot.remaining_qty == Decimal("0")
        assert mock_lot.status == "closed"
    
    @pytest.mark.asyncio
    async def test_close_lots_fifo_partial_close(self):
        """Test partially closing a lot."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        # Create mock lot with 10 shares
        mock_lot = MagicMock()
        mock_lot.id = uuid.uuid4()
        mock_lot.user_id = "user123"
        mock_lot.symbol = "AAPL"
        mock_lot.remaining_qty = Decimal("10")
        mock_lot.cost_basis = Decimal("150.00")
        mock_lot.order_id = uuid.uuid4()
        mock_lot.open_date = datetime.now(UTC)
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        
        trades = await tracker.close_lots_fifo(
            user_id="user123",
            symbol="AAPL",
            qty_to_close=Decimal("5"),  # Only close half
            close_price=Decimal("160.00"),
            close_order_id=uuid.uuid4(),
            close_date=datetime.now(UTC)
        )
        
        assert len(trades) == 1
        assert mock_lot.remaining_qty == Decimal("5")  # 5 remaining
        assert mock_lot.status != "closed"  # Not fully closed
    
    @pytest.mark.asyncio
    async def test_close_lots_fifo_multiple_lots(self):
        """Test closing across multiple lots in FIFO order."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        # Create two mock lots
        mock_lot1 = MagicMock()
        mock_lot1.id = uuid.uuid4()
        mock_lot1.user_id = "user123"
        mock_lot1.symbol = "AAPL"
        mock_lot1.remaining_qty = Decimal("5")
        mock_lot1.cost_basis = Decimal("140.00")  # Older, lower cost
        mock_lot1.order_id = uuid.uuid4()
        mock_lot1.open_date = datetime(2024, 1, 1)
        
        mock_lot2 = MagicMock()
        mock_lot2.id = uuid.uuid4()
        mock_lot2.user_id = "user123"
        mock_lot2.symbol = "AAPL"
        mock_lot2.remaining_qty = Decimal("10")
        mock_lot2.cost_basis = Decimal("150.00")  # Newer, higher cost
        mock_lot2.order_id = uuid.uuid4()
        mock_lot2.open_date = datetime(2024, 2, 1)
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot1, mock_lot2]  # FIFO order
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        
        trades = await tracker.close_lots_fifo(
            user_id="user123",
            symbol="AAPL",
            qty_to_close=Decimal("8"),  # Close 5 from lot1 + 3 from lot2
            close_price=Decimal("160.00"),
            close_order_id=uuid.uuid4(),
            close_date=datetime.now(UTC)
        )
        
        assert len(trades) == 2
        assert mock_lot1.remaining_qty == Decimal("0")
        assert mock_lot1.status == "closed"
        assert mock_lot2.remaining_qty == Decimal("7")  # 10 - 3
    
    @pytest.mark.asyncio
    async def test_close_lots_fifo_calculates_pnl(self):
        """Test P&L calculation on lot close."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_lot = MagicMock()
        mock_lot.id = uuid.uuid4()
        mock_lot.user_id = "user123"
        mock_lot.symbol = "AAPL"
        mock_lot.remaining_qty = Decimal("10")
        mock_lot.cost_basis = Decimal("150.00")
        mock_lot.order_id = uuid.uuid4()
        mock_lot.open_date = datetime.now(UTC)
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        
        trades = await tracker.close_lots_fifo(
            user_id="user123",
            symbol="AAPL",
            qty_to_close=Decimal("10"),
            close_price=Decimal("160.00"),  # Sold at $160, bought at $150
            close_order_id=uuid.uuid4(),
            close_date=datetime.now(UTC)
        )
        
        # Expected P&L: 10 * (160 - 150) = 100
        assert len(trades) == 1
        trade = trades[0]
        assert trade.realized_pnl == Decimal("100.00")


class TestGetOpenLots:
    """Test LotTracker.get_open_lots method."""
    
    @pytest.mark.asyncio
    async def test_get_open_lots_all(self):
        """Test getting all open lots for a user."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_lot1 = MagicMock()
        mock_lot1.symbol = "AAPL"
        mock_lot2 = MagicMock()
        mock_lot2.symbol = "MSFT"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot1, mock_lot2]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        lots = await tracker.get_open_lots("user123")
        
        assert len(lots) == 2
    
    @pytest.mark.asyncio
    async def test_get_open_lots_by_symbol(self):
        """Test getting open lots filtered by symbol."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_lot = MagicMock()
        mock_lot.symbol = "AAPL"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        lots = await tracker.get_open_lots("user123", symbol="AAPL")
        
        assert len(lots) == 1
        assert lots[0].symbol == "AAPL"
    
    @pytest.mark.asyncio
    async def test_get_open_lots_empty(self):
        """Test getting open lots when none exist."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        lots = await tracker.get_open_lots("user123")
        
        assert lots == []


class TestGetRealizedTrades:
    """Test LotTracker.get_realized_trades method."""
    
    @pytest.mark.asyncio
    async def test_get_realized_trades_all(self):
        """Test getting all realized trades for a user."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_trade1 = MagicMock()
        mock_trade1.symbol = "AAPL"
        mock_trade2 = MagicMock()
        mock_trade2.symbol = "MSFT"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_trade1, mock_trade2]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        trades = await tracker.get_realized_trades("user123")
        
        assert len(trades) == 2
    
    @pytest.mark.asyncio
    async def test_get_realized_trades_by_symbol(self):
        """Test getting realized trades filtered by symbol."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_trade = MagicMock()
        mock_trade.symbol = "GOOGL"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_trade]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        trades = await tracker.get_realized_trades("user123", symbol="GOOGL")
        
        assert len(trades) == 1
    
    @pytest.mark.asyncio
    async def test_get_realized_trades_date_range(self):
        """Test getting realized trades with date range filter."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_trade = MagicMock()
        mock_trade.close_date = datetime(2024, 6, 15)
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_trade]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        trades = await tracker.get_realized_trades(
            "user123",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31)
        )
        
        assert len(trades) == 1


class TestGetCostBasis:
    """Test LotTracker.get_cost_basis method."""
    
    @pytest.mark.asyncio
    async def test_get_cost_basis_no_lots(self):
        """Test cost basis when no lots exist returns zero."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        cost_basis = await tracker.get_cost_basis("user123", "AAPL")
        
        assert cost_basis == Decimal("0")
    
    @pytest.mark.asyncio
    async def test_get_cost_basis_single_lot(self):
        """Test cost basis with single lot."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_lot = MagicMock()
        mock_lot.remaining_qty = Decimal("10")
        mock_lot.cost_basis = Decimal("150.00")
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        cost_basis = await tracker.get_cost_basis("user123", "AAPL")
        
        assert cost_basis == Decimal("150.00")
    
    @pytest.mark.asyncio
    async def test_get_cost_basis_weighted_average(self):
        """Test weighted average cost basis calculation."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        # Lot 1: 10 shares at $100 = $1000
        mock_lot1 = MagicMock()
        mock_lot1.remaining_qty = Decimal("10")
        mock_lot1.cost_basis = Decimal("100.00")
        
        # Lot 2: 20 shares at $150 = $3000
        mock_lot2 = MagicMock()
        mock_lot2.remaining_qty = Decimal("20")
        mock_lot2.cost_basis = Decimal("150.00")
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot1, mock_lot2]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        cost_basis = await tracker.get_cost_basis("user123", "AAPL")
        
        # Weighted average: (10*100 + 20*150) / 30 = 4000 / 30 = 133.33...
        expected = Decimal("4000") / Decimal("30")
        assert cost_basis == expected


class TestGetUnrealizedPnl:
    """Test LotTracker.get_unrealized_pnl method."""
    
    @pytest.mark.asyncio
    async def test_unrealized_pnl_no_lots(self):
        """Test unrealized P&L when no lots exist."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        pnl = await tracker.get_unrealized_pnl(
            "user123", "AAPL", Decimal("160.00")
        )
        
        assert pnl == Decimal("0")
    
    @pytest.mark.asyncio
    async def test_unrealized_pnl_profit(self):
        """Test unrealized P&L with profit."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_lot = MagicMock()
        mock_lot.remaining_qty = Decimal("10")
        mock_lot.cost_basis = Decimal("150.00")
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        pnl = await tracker.get_unrealized_pnl(
            "user123", "AAPL", Decimal("160.00")  # Current price > cost
        )
        
        # Expected: 10 * (160 - 150) = 100
        assert pnl == Decimal("100.00")
    
    @pytest.mark.asyncio
    async def test_unrealized_pnl_loss(self):
        """Test unrealized P&L with loss."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_lot = MagicMock()
        mock_lot.remaining_qty = Decimal("10")
        mock_lot.cost_basis = Decimal("150.00")
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        pnl = await tracker.get_unrealized_pnl(
            "user123", "AAPL", Decimal("140.00")  # Current price < cost
        )
        
        # Expected: 10 * (140 - 150) = -100
        assert pnl == Decimal("-100.00")
    
    @pytest.mark.asyncio
    async def test_unrealized_pnl_multiple_lots(self):
        """Test unrealized P&L across multiple lots."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_lot1 = MagicMock()
        mock_lot1.remaining_qty = Decimal("10")
        mock_lot1.cost_basis = Decimal("100.00")
        
        mock_lot2 = MagicMock()
        mock_lot2.remaining_qty = Decimal("5")
        mock_lot2.cost_basis = Decimal("120.00")
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot1, mock_lot2]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        pnl = await tracker.get_unrealized_pnl(
            "user123", "AAPL", Decimal("110.00")
        )
        
        # Lot 1: 10 * (110 - 100) = 100
        # Lot 2: 5 * (110 - 120) = -50
        # Total: 50
        assert pnl == Decimal("50.00")


# ============================================================================
# POSITION LOT MODEL TESTS
# ============================================================================

class TestPositionLotModel:
    """Test PositionLot model structure."""
    
    def test_position_lot_import(self):
        """Test PositionLot can be imported."""
        from backend.infra.schemas import PositionLot
        
        assert PositionLot is not None
    
    def test_position_lot_has_required_fields(self):
        """Test PositionLot has expected fields."""
        from backend.infra.schemas import PositionLot
        
        # Check that the model has expected columns
        columns = [c.name for c in PositionLot.__table__.columns]
        
        expected_fields = ['id', 'user_id', 'symbol', 'qty', 'remaining_qty', 'cost_basis', 'status']
        for field in expected_fields:
            assert field in columns, f"Missing field: {field}"


class TestRealizedTradeModel:
    """Test RealizedTrade model structure."""
    
    def test_realized_trade_import(self):
        """Test RealizedTrade can be imported."""
        from backend.infra.schemas import RealizedTrade
        
        assert RealizedTrade is not None
    
    def test_realized_trade_has_required_fields(self):
        """Test RealizedTrade has expected fields."""
        from backend.infra.schemas import RealizedTrade
        
        columns = [c.name for c in RealizedTrade.__table__.columns]
        
        expected_fields = ['id', 'user_id', 'symbol', 'qty', 'realized_pnl']
        for field in expected_fields:
            assert field in columns, f"Missing field: {field}"


# ============================================================================
# EDGE CASES
# ============================================================================

class TestLotTrackerEdgeCases:
    """Test edge cases for lot tracking."""
    
    @pytest.mark.asyncio
    async def test_create_lot_with_zero_quantity(self):
        """Test creating lot with zero quantity."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        tracker = LotTracker(mock_session)
        
        # This should still work - validation should be at higher level
        lot = await tracker.create_lot(
            user_id="user123",
            symbol="AAPL",
            qty=Decimal("0"),
            cost_basis=Decimal("150.00"),
            order_id=uuid.uuid4(),
            open_date=datetime.now(UTC)
        )
        
        assert lot.qty == Decimal("0")
    
    @pytest.mark.asyncio
    async def test_close_lots_with_zero_cost_basis(self):
        """Test closing lots with zero cost basis (free shares)."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_lot = MagicMock()
        mock_lot.id = uuid.uuid4()
        mock_lot.user_id = "user123"
        mock_lot.symbol = "FREE"
        mock_lot.remaining_qty = Decimal("100")
        mock_lot.cost_basis = Decimal("0")  # Free shares
        mock_lot.order_id = uuid.uuid4()
        mock_lot.open_date = datetime.now(UTC)
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        
        trades = await tracker.close_lots_fifo(
            user_id="user123",
            symbol="FREE",
            qty_to_close=Decimal("100"),
            close_price=Decimal("10.00"),
            close_order_id=uuid.uuid4(),
            close_date=datetime.now(UTC)
        )
        
        # P&L should be 100 * 10 = 1000 (all profit from free shares)
        assert len(trades) == 1
        trade = trades[0]
        assert trade.realized_pnl == Decimal("1000.00")
        assert trade.realized_pnl_percent == Decimal("0")  # Avoid division by zero
    
    @pytest.mark.asyncio
    async def test_get_cost_basis_with_zero_total_qty(self):
        """Test cost basis when total quantity is zero."""
        from backend.services.lot_tracker_service import LotTracker
        
        mock_session = AsyncMock()
        
        mock_lot = MagicMock()
        mock_lot.remaining_qty = Decimal("0")
        mock_lot.cost_basis = Decimal("100.00")
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_lot]
        mock_session.execute.return_value = mock_result
        
        tracker = LotTracker(mock_session)
        cost_basis = await tracker.get_cost_basis("user123", "AAPL")
        
        # Should return 0, not divide by zero
        assert cost_basis == Decimal("0")
