"""
Phase 1 Tests: Best/Worst Trade Logic
Tests for single trade not appearing as both best AND worst
Uses REAL database with actual data - NO MOCKS
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from backend.services.trade_service import TradeService
from backend.infra.schemas import Base, RealizedTrade, Order
import uuid


@pytest.fixture
async def db_session():
    """Create a real test database session"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    
    # Create only the tables we need
    from backend.infra.schemas import RealizedTrade, Order
    async with engine.begin() as conn:
        def create_tables(sync_conn):
            # Create tables individually, ignoring duplicate index errors
            try:
                Order.__table__.create(sync_conn, checkfirst=False)
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


def create_order_pair(symbol, qty, open_price, close_price, pnl, is_long=True):
    """Helper to create open and close orders with realized trade"""
    open_order_id = uuid.uuid4()
    close_order_id = uuid.uuid4()
    lot_id = uuid.uuid4()
    
    # Create orders
    open_order = Order(
        id=open_order_id,
        client_idempotency_key=f"test-open-{open_order_id}",
        symbol=symbol,
        side="buy" if is_long else "sell",
        qty=qty,
        order_type="market",
        tif="day",
        filled_qty=qty,
        avg_fill_price=open_price,
        status="filled",
        submitted_at=datetime.now(timezone.utc)
    )
    close_order = Order(
        id=close_order_id,
        client_idempotency_key=f"test-close-{close_order_id}",
        symbol=symbol,
        side="sell" if is_long else "buy",
        qty=qty,
        order_type="market",
        tif="day",
        filled_qty=qty,
        avg_fill_price=close_price,
        status="filled",
        submitted_at=datetime.now(timezone.utc)
    )
    
    # Create realized trade
    trade = RealizedTrade(
        id=uuid.uuid4(),
        user_id="test_user",
        symbol=symbol,
        qty=qty,
        open_price=open_price,
        close_price=close_price,
        realized_pnl=pnl,
        realized_pnl_percent=(pnl / (open_price * qty)) * 100,
        open_order_id=open_order_id,
        close_order_id=close_order_id,
        lot_id=lot_id,
        open_date=datetime.now(timezone.utc),
        close_date=datetime.now(timezone.utc)
    )
    
    return open_order, close_order, trade


class TestBestWorstTradeLogic:
    """Tests for best/worst trade identification logic"""
    
    @pytest.mark.asyncio
    async def test_single_positive_trade_only_shows_as_best(self, db_session):
        """Single winning trade should only appear as best trade"""
        open_order, close_order, trade = create_order_pair(
            "AAPL", Decimal("100"), Decimal("150.00"), 
            Decimal("155.00"), Decimal("500.00")
        )
        
        db_session.add(open_order)
        db_session.add(close_order)
        db_session.add(trade)
        await db_session.commit()
        
        # Use real TradeService
        service = TradeService(db_session)
        analytics = await service.calculate_analytics()
        
        # Assertions
        assert analytics['bestTrade'] is not None
        assert float(analytics['bestTrade']['pnl']) == 500.00
        assert analytics['worstTrade'] is None  # Single positive trade has no worst
    
    @pytest.mark.asyncio
    async def test_single_negative_trade_only_shows_as_worst(self, db_session):
        """Single losing trade should only appear as worst trade"""
        open_order, close_order, trade = create_order_pair(
            "TSLA", Decimal("50"), Decimal("200.00"),
            Decimal("190.00"), Decimal("-300.00")
        )
        
        db_session.add(open_order)
        db_session.add(close_order)
        db_session.add(trade)
        await db_session.commit()
        
        # Use real TradeService
        service = TradeService(db_session)
        analytics = await service.calculate_analytics()
        
        # Assertions
        assert analytics['worstTrade'] is not None
        assert float(analytics['worstTrade']['pnl']) == -300.00
        assert analytics['bestTrade'] is None  # Single negative trade has no best
    
    @pytest.mark.asyncio
    async def test_break_even_trade_shows_neither(self, db_session):
        """Break-even trade should not appear as best or worst"""
        open_order, close_order, trade = create_order_pair(
            "MSFT", Decimal("75"), Decimal("300.00"),
            Decimal("300.00"), Decimal("0.00")
        )
        
        db_session.add(open_order)
        db_session.add(close_order)
        db_session.add(trade)
        await db_session.commit()
        
        # Use real TradeService
        service = TradeService(db_session)
        analytics = await service.calculate_analytics()
        
        # Assertions
        assert analytics['bestTrade'] is None  # Break-even has no best
        assert analytics['worstTrade'] is None  # Break-even has no worst
    
    @pytest.mark.asyncio
    async def test_multiple_trades_find_correct_best_worst(self, db_session):
        """With multiple trades, should correctly identify best and worst"""
        # Create multiple trades
        trades_data = [
            ("AAPL", Decimal("100"), Decimal("150.00"), Decimal("155.00"), Decimal("500.00")),   # Best
            ("TSLA", Decimal("50"), Decimal("200.00"), Decimal("194.00"), Decimal("-300.00")),  # Worst
            ("MSFT", Decimal("100"), Decimal("300.00"), Decimal("302.00"), Decimal("200.00")),  # Mid
            ("GOOGL", Decimal("100"), Decimal("140.00"), Decimal("139.00"), Decimal("-100.00")), # Mid
        ]
        
        for symbol, qty, open_price, close_price, pnl in trades_data:
            open_order, close_order, trade = create_order_pair(
                symbol, qty, open_price, close_price, pnl
            )
            db_session.add(open_order)
            db_session.add(close_order)
            db_session.add(trade)
        
        await db_session.commit()
        
        # Use real TradeService
        service = TradeService(db_session)
        analytics = await service.calculate_analytics()
        
        # Assertions
        assert analytics['bestTrade'] is not None
        assert analytics['worstTrade'] is not None
        assert float(analytics['bestTrade']['pnl']) == 500.00
        assert float(analytics['worstTrade']['pnl']) == -300.00
