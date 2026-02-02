"""
Phase 2 Tests: Cost Basis Tracking & Lot Matching
Tests for FIFO lot tracking, position lots, realized trades
Uses REAL database with actual data - NO MOCKS
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from backend.services.lot_tracker_service import LotTracker
from backend.infra.schemas import Base, PositionLot, RealizedTrade
import uuid


@pytest.fixture
async def db_session():
    """Create a real test database session"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    
    # Create only the tables we need
    from backend.infra.schemas import PositionLot, RealizedTrade
    async with engine.begin() as conn:
        def create_tables(sync_conn):
            # Create tables individually, ignoring duplicate index errors
            try:
                PositionLot.__table__.create(sync_conn, checkfirst=False)
            except Exception as e:
                if "already exists" not in str(e):
                    raise
            try:
                RealizedTrade.__table__.create(sync_conn, checkfirst=False)
            except Exception as e:
                if "already exists" not in str(e):
                    raise
        await conn.run_sync(create_tables)
    
    # Create session
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
        await session.rollback()
    
    await engine.dispose()


class TestLotTracker:
    """Test LotTracker FIFO matching logic with real data"""
    
    @pytest.mark.asyncio
    async def test_create_lot_on_buy(self, db_session):
        """Buying should create a position lot"""
        tracker = LotTracker(db_session)
        
        lot = await tracker.create_lot(
            user_id="test_user",
            symbol="AAPL",
            qty=Decimal("100"),
            cost_basis=Decimal("150.00"),
            order_id=uuid.uuid4(),
            open_date=datetime.now(timezone.utc)
        )
        
        assert lot is not None
        assert lot.symbol == "AAPL"
        assert lot.qty == Decimal("100")
        assert lot.remaining_qty == Decimal("100")
        assert lot.cost_basis == Decimal("150.00")
        assert lot.status == "open"
    
    @pytest.mark.asyncio
    async def test_fifo_matching_single_lot(self, db_session):
        """Selling should close lots in FIFO order"""
        tracker = LotTracker(db_session)
        
        # Create real lot in database
        lot = await tracker.create_lot(
            user_id="test_user",
            symbol="AAPL",
            qty=Decimal("100"),
            cost_basis=Decimal("150.00"),
            order_id=uuid.uuid4(),
            open_date=datetime.now(timezone.utc)
        )
        
        # Close 50 shares
        realized_trades = await tracker.close_lots_fifo(
            user_id="test_user",
            symbol="AAPL",
            qty_to_close=Decimal("50"),
            close_price=Decimal("155.00"),
            close_order_id=uuid.uuid4(),
            close_date=datetime.now(timezone.utc)
        )
        
        assert len(realized_trades) == 1
        assert realized_trades[0].qty == Decimal("50")
        assert realized_trades[0].open_price == Decimal("150.00")
        assert realized_trades[0].close_price == Decimal("155.00")
        # P&L = 50 * (155 - 150) = 250
        assert realized_trades[0].realized_pnl == Decimal("250.00")
        
        # Verify lot was updated in database
        await db_session.refresh(lot)
        assert lot.remaining_qty == Decimal("50")
        assert lot.status == "open"  # Still open with remaining shares
    
    @pytest.mark.asyncio
    async def test_fifo_multiple_lots(self, db_session):
        """Selling across multiple lots should match FIFO"""
        tracker = LotTracker(db_session)
        
        # Create multiple lots with different cost bases
        lot1 = await tracker.create_lot(
            user_id="test_user",
            symbol="AAPL",
            qty=Decimal("100"),
            cost_basis=Decimal("150.00"),
            order_id=uuid.uuid4(),
            open_date=datetime.now(timezone.utc)
        )
        
        lot2 = await tracker.create_lot(
            user_id="test_user",
            symbol="AAPL",
            qty=Decimal("100"),
            cost_basis=Decimal("151.00"),
            order_id=uuid.uuid4(),
            open_date=datetime.now(timezone.utc)
        )
        
        lot3 = await tracker.create_lot(
            user_id="test_user",
            symbol="AAPL",
            qty=Decimal("50"),
            cost_basis=Decimal("152.00"),
            order_id=uuid.uuid4(),
            open_date=datetime.now(timezone.utc)
        )
        
        # Close 150 shares (should close lot1 completely and lot2 partially)
        realized_trades = await tracker.close_lots_fifo(
            user_id="test_user",
            symbol="AAPL",
            qty_to_close=Decimal("150"),
            close_price=Decimal("155.00"),
            close_order_id=uuid.uuid4(),
            close_date=datetime.now(timezone.utc)
        )
        
        # Should have 2 realized trades
        assert len(realized_trades) == 2
        
        # First trade: 100 shares at cost basis $150
        assert realized_trades[0].qty == Decimal("100")
        assert realized_trades[0].open_price == Decimal("150.00")
        assert realized_trades[0].realized_pnl == Decimal("500.00")  # 100 * (155 - 150)
        
        # Second trade: 50 shares at cost basis $151
        assert realized_trades[1].qty == Decimal("50")
        assert realized_trades[1].open_price == Decimal("151.00")
        assert realized_trades[1].realized_pnl == Decimal("200.00")  # 50 * (155 - 151)
        
        # Verify lots status
        await db_session.refresh(lot1)
        await db_session.refresh(lot2)
        await db_session.refresh(lot3)
        
        assert lot1.status == "closed"
        assert lot1.remaining_qty == Decimal("0")
        
        assert lot2.status == "open"
        assert lot2.remaining_qty == Decimal("50")  # 100 - 50
        
        assert lot3.status == "open"
        assert lot3.remaining_qty == Decimal("50")  # Untouched
    
    @pytest.mark.asyncio
    async def test_cost_basis_calculation(self, db_session):
        """Calculate weighted average cost basis"""
        tracker = LotTracker(db_session)
        
        # Create multiple lots
        await tracker.create_lot(
            user_id="test_user",
            symbol="AAPL",
            qty=Decimal("100"),
            cost_basis=Decimal("150.00"),
            order_id=uuid.uuid4(),
            open_date=datetime.now(timezone.utc)
        )
        
        await tracker.create_lot(
            user_id="test_user",
            symbol="AAPL",
            qty=Decimal("200"),
            cost_basis=Decimal("152.00"),
            order_id=uuid.uuid4(),
            open_date=datetime.now(timezone.utc)
        )
        
        cost_basis = await tracker.get_cost_basis("test_user", "AAPL")
        
        # Weighted avg: (100*150 + 200*152) / 300 = 151.33...
        expected = Decimal("151.33")
        assert abs(cost_basis - expected) < Decimal("0.01")
    
    @pytest.mark.asyncio
    async def test_unrealized_pnl(self, db_session):
        """Calculate unrealized P&L for open lots"""
        tracker = LotTracker(db_session)
        
        # Create open lot
        await tracker.create_lot(
            user_id="test_user",
            symbol="AAPL",
            qty=Decimal("100"),
            cost_basis=Decimal("150.00"),
            order_id=uuid.uuid4(),
            open_date=datetime.now(timezone.utc)
        )
        
        unrealized_pnl = await tracker.get_unrealized_pnl(
            "test_user", "AAPL", Decimal("155.00")
        )
        
        # 100 shares * (155 - 150) = $500
        assert unrealized_pnl == Decimal("500.00")
