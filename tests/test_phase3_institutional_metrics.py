"""
Phase 3 Tests: Institutional Metrics
Tests for advanced analytics calculations
Uses REAL database with actual data - NO MOCKS
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from backend.services.trade_analytics_service import InstitutionalAnalytics
from backend.infra.schemas import Base, RealizedTrade
import uuid


@pytest.fixture
async def db_session():
    """Create a real test database session"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    
    # Create only the tables we need
    from backend.infra.schemas import RealizedTrade
    async with engine.begin() as conn:
        def create_tables(sync_conn):
            # Create tables individually, ignoring duplicate index errors
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


class TestInstitutionalAnalytics:
    """Test institutional metrics calculations with real data"""
    
    @pytest.mark.asyncio
    async def test_sharpe_ratio_positive_returns(self, db_session):
        """Test Sharpe Ratio calculation with positive returns"""
        analytics = InstitutionalAnalytics(db_session)
        
        # Sample returns with positive mean - use floats for math operations
        returns = [0.02, 0.03, 0.01, 0.04, 0.02]
        
        sharpe = await analytics.calculate_sharpe_ratio(returns)
        
        # Expected: The Sharpe Ratio is annualized with sqrt(252)
        # mean = 0.024, std ≈ 0.011, daily sharpe ≈ 2.09
        # annualized sharpe = 2.09 * sqrt(252) ≈ 33.2
        assert sharpe > 0
        assert sharpe == pytest.approx(33.2, abs=1.0)
    
    @pytest.mark.asyncio
    async def test_sharpe_ratio_negative_returns(self, db_session):
        """Test Sharpe Ratio with negative returns"""
        analytics = InstitutionalAnalytics(db_session)
        
        returns = [-0.01, -0.02, -0.01, -0.03, -0.01]
        
        sharpe = await analytics.calculate_sharpe_ratio(returns)
        
        # Should be negative
        assert sharpe < 0
    
    @pytest.mark.asyncio
    async def test_sharpe_ratio_zero_volatility(self, db_session):
        """Test Sharpe Ratio with zero volatility"""
        analytics = InstitutionalAnalytics(db_session)
        
        # All same returns = zero volatility
        returns = [0.02] * 5
        
        sharpe = await analytics.calculate_sharpe_ratio(returns)
        
        # Should return 0 for zero volatility
        assert sharpe == 0
    
    @pytest.mark.asyncio
    async def test_max_drawdown_no_drawdown(self, db_session):
        """Test max drawdown with no drawdown"""
        analytics = InstitutionalAnalytics(db_session)
        
        # Always increasing equity
        equity_curve = [Decimal("10000"), Decimal("10500"), 
                        Decimal("11000"), Decimal("11500")]
        
        drawdown = await analytics.calculate_max_drawdown(equity_curve)
        
        # Should return dict with zero drawdown
        assert isinstance(drawdown, dict)
        assert drawdown['max_dd'] == 0.0
        assert drawdown['max_dd_dollars'] == 0.0
    
    @pytest.mark.asyncio
    async def test_max_drawdown_with_decline(self, db_session):
        """Test max drawdown calculation"""
        analytics = InstitutionalAnalytics(db_session)
        
        # Peak at 10000, trough at 7000 = 30% drawdown
        equity_curve = [Decimal("10000"), Decimal("9000"), 
                        Decimal("7000"), Decimal("8000")]
        
        drawdown = await analytics.calculate_max_drawdown(equity_curve)
        
        # Should return dict with 30% drawdown
        assert isinstance(drawdown, dict)
        assert drawdown['max_dd'] == pytest.approx(30.0, abs=0.01)
        assert drawdown['max_dd_dollars'] == pytest.approx(3000.0, abs=0.01)
    
    @pytest.mark.asyncio
    async def test_profit_factor_all_wins(self, db_session):
        """Test profit factor with all winning trades"""
        analytics = InstitutionalAnalytics(db_session)
        
        winning_trades = [100.0, 200.0, 150.0]
        losing_trades = []
        
        pf = await analytics.calculate_profit_factor(winning_trades, losing_trades)
        
        # All wins, no losses = capped at 999.99
        assert pf == 999.99
    
    @pytest.mark.asyncio
    async def test_profit_factor_mixed_trades(self, db_session):
        """Test profit factor with mixed trades"""
        analytics = InstitutionalAnalytics(db_session)
        
        # Total wins: 2000, Total losses: 1000, PF = 2.0
        winning_trades = [500.0, 1500.0]
        losing_trades = [-300.0, -700.0]
        
        pf = await analytics.calculate_profit_factor(winning_trades, losing_trades)
        
        assert pf == pytest.approx(2.0, abs=0.01)
    
    @pytest.mark.asyncio
    async def test_profit_factor_all_losses(self, db_session):
        """Test profit factor with all losing trades"""
        analytics = InstitutionalAnalytics(db_session)
        
        winning_trades = []
        losing_trades = [-100.0, -200.0, -150.0]
        
        pf = await analytics.calculate_profit_factor(winning_trades, losing_trades)
        
        # All losses, no wins = 0
        assert pf == 0
    
    @pytest.mark.asyncio
    async def test_expectancy_positive(self, db_session):
        """Test expectancy calculation with positive edge"""
        analytics = InstitutionalAnalytics(db_session)
        
        # 60% win rate, avg win $200, avg loss -$100
        win_rate = 60.0
        avg_win = 200.0
        avg_loss = -100.0
        
        expectancy = await analytics.calculate_expectancy(win_rate, avg_win, avg_loss)
        
        # (0.6 * 200) + (0.4 * -100) = 120 - 40 = 80
        assert expectancy == pytest.approx(80.0, abs=1.0)
    
    @pytest.mark.asyncio
    async def test_expectancy_negative(self, db_session):
        """Test expectancy with negative edge"""
        analytics = InstitutionalAnalytics(db_session)
        
        # 40% win rate, avg win $100, avg loss -$150
        win_rate = 40.0
        avg_win = 100.0
        avg_loss = -150.0
        
        expectancy = await analytics.calculate_expectancy(win_rate, avg_win, avg_loss)
        
        # (0.4 * 100) + (0.6 * -150) = 40 - 90 = -50
        assert expectancy < 0
        assert expectancy == pytest.approx(-50.0, abs=1.0)
    
    @pytest.mark.asyncio
    async def test_sortino_ratio(self, db_session):
        """Test Sortino Ratio (downside deviation)"""
        analytics = InstitutionalAnalytics(db_session)
        
        # Mix of positive and negative returns - use floats
        returns = [0.05, -0.02, 0.03, -0.01, 0.04]
        
        sortino = await analytics.calculate_sortino_ratio(returns)
        
        # Should focus only on downside volatility
        assert sortino > 0
    
    @pytest.mark.asyncio
    async def test_calmar_ratio(self, db_session):
        """Test Calmar Ratio (return / max drawdown)"""
        analytics = InstitutionalAnalytics(db_session)
        
        # Sample returns and max drawdown
        returns = [0.02] * 50  # 50 trades with 2% return each
        max_drawdown = 30.0  # 30% max drawdown
        
        calmar = await analytics.calculate_calmar_ratio(returns, max_drawdown)
        
        # Should be positive ratio
        assert calmar > 0
    
    @pytest.mark.asyncio
    async def test_streaks_calculation(self, db_session):
        """Test win/loss streak calculation"""
        analytics = InstitutionalAnalytics(db_session)
        
        # Create trade sequence in database
        trades_data = [
            Decimal("100"),   # Win
            Decimal("150"),   # Win
            Decimal("200"),   # Win - max win streak = 3
            Decimal("-50"),   # Loss
            Decimal("-75"),   # Loss - max loss streak = 2
            Decimal("100"),   # Win
        ]
        
        for i, pnl in enumerate(trades_data):
            trade = RealizedTrade(
                id=uuid.uuid4(),
                user_id="test_user",
                symbol="TEST",
                qty=Decimal("100"),
                open_price=Decimal("100.00"),
                close_price=Decimal("100.00") + (pnl / 100),
                realized_pnl=pnl,
                realized_pnl_percent=(pnl / 10000) * 100,
                open_order_id=uuid.uuid4(),
                close_order_id=uuid.uuid4(),
                lot_id=uuid.uuid4(),
                open_date=datetime.now(timezone.utc) - timedelta(days=6-i),
                close_date=datetime.now(timezone.utc) - timedelta(days=6-i)
            )
            db_session.add(trade)
        
        await db_session.commit()
        
        # Extract PNL values from the trades_data
        pnl_values = [float(pnl) for pnl in trades_data]
        streaks = await analytics.calculate_streaks(pnl_values)
        
        assert streaks['max_win_streak'] == 3
        assert streaks['max_loss_streak'] == 2
    
    @pytest.mark.asyncio
    async def test_monthly_returns_aggregation(self, db_session):
        """Test monthly returns aggregation"""
        analytics = InstitutionalAnalytics(db_session)
        
        # Create trades across different months
        base_date = datetime(2024, 8, 15, tzinfo=timezone.utc)
        
        # August trades
        for i in range(3):
            trade = RealizedTrade(
                id=uuid.uuid4(),
                user_id="test_user",
                symbol="TEST",
                qty=Decimal("100"),
                open_price=Decimal("100.00"),
                close_price=Decimal("105.00"),
                realized_pnl=Decimal("500.00"),
                realized_pnl_percent=Decimal("5.00"),
                open_order_id=uuid.uuid4(),
                close_order_id=uuid.uuid4(),
                lot_id=uuid.uuid4(),
                open_date=base_date,
                close_date=base_date + timedelta(days=i)
            )
            db_session.add(trade)
        
        # September trades
        sept_date = datetime(2024, 9, 1, tzinfo=timezone.utc)
        trade = RealizedTrade(
            id=uuid.uuid4(),
            user_id="test_user",
            symbol="TEST",
            qty=Decimal("100"),
            open_price=Decimal("100.00"),
            close_price=Decimal("105.00"),
            realized_pnl=Decimal("500.00"),
            realized_pnl_percent=Decimal("5.00"),
            open_order_id=uuid.uuid4(),
            close_order_id=uuid.uuid4(),
            lot_id=uuid.uuid4(),
            open_date=sept_date,
            close_date=sept_date + timedelta(days=1)
        )
        db_session.add(trade)
        
        await db_session.commit()
        
        # Query the trades from database
        from sqlalchemy import select
        result = await db_session.execute(
            select(RealizedTrade).where(RealizedTrade.user_id == "test_user")
        )
        trades = list(result.scalars().all())
        
        monthly_returns = await analytics.calculate_monthly_returns(trades)
        
        # Should have 2 months
        assert len(monthly_returns) == 2
        
        # August: 3 * $500 = $1500
        aug_data = next(m for m in monthly_returns if m['month'] == '2024-08')
        assert aug_data['pnl'] == 1500.00
        
        # September: 1 * $500 = $500
        sept_data = next(m for m in monthly_returns if m['month'] == '2024-09')
        assert sept_data['pnl'] == 500.00
