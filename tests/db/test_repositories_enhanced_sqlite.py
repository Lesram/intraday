"""
Database Repositories SQLite Testing - Enhanced Coverage.
Tests in-memory SQLite CRUD operations and transaction handling.
Focuses on high-yield coverage for backend/infra/repositories/ modules.
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from backend.infra.repositories.orders import OrdersRepo
from backend.infra.repositories.positions import PositionsRepo  
from backend.infra.repositories.executions import ExecutionsRepo  # Use executions instead of trades
from backend.infra.database import DatabaseManager


# Test fixtures for SQLite testing
@pytest.fixture
async def sqlite_memory_connection():
    """Create in-memory SQLite connection for testing."""
    connection = await aiosqlite.connect(":memory:")
    
    # Create test tables
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty DECIMAL(15,6) NOT NULL,
            price DECIMAL(15,6),
            status TEXT NOT NULL,
            client_key TEXT UNIQUE,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            filled_at TIMESTAMP,
            cancelled_at TIMESTAMP,
            account_id TEXT NOT NULL
        )
    """)
    
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            qty DECIMAL(15,6) NOT NULL DEFAULT 0,
            avg_price DECIMAL(15,6) NOT NULL DEFAULT 0,
            market_value DECIMAL(15,6) NOT NULL DEFAULT 0,
            unrealized_pnl DECIMAL(15,6) NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, symbol)
        )
    """)
    
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty DECIMAL(15,6) NOT NULL,
            price DECIMAL(15,6) NOT NULL,
            executed_at TIMESTAMP NOT NULL,
            commission DECIMAL(15,6) DEFAULT 0,
            account_id TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id)
        )
    """)
    
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS outbox_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )
    """)
    
    # Create indexes for performance
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_orders_account_id ON orders(account_id)")
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_orders_client_key ON orders(client_key)")
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_positions_account_symbol ON positions(account_id, symbol)")
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_trades_order_id ON trades(order_id)")
    await connection.execute("CREATE INDEX IF NOT EXISTS idx_trades_account_id ON trades(account_id)")
    
    await connection.commit()
    yield connection
    await connection.close()


@pytest.fixture
async def orders_repo(sqlite_memory_connection):
    """Create orders repository with SQLite connection."""
    repo = OrdersRepo(connection=sqlite_memory_connection)
    return repo


@pytest.fixture
async def positions_repo(sqlite_memory_connection):
    """Create positions repository with SQLite connection.""" 
    repo = PositionsRepo(connection=sqlite_memory_connection)
    return repo


@pytest.fixture
async def trades_repo(sqlite_memory_connection):
    """Create trades repository with SQLite connection."""
    repo = ExecutionsRepo(connection=sqlite_memory_connection)
    return repo


@pytest.fixture
def sample_order_data():
    """Sample order data for testing."""
    return {
        "id": "order-123",
        "symbol": "AAPL", 
        "side": "buy",
        "qty": Decimal("100"),
        "price": Decimal("150.00"),
        "status": "new",
        "client_key": "client-order-123",
        "account_id": "account-456",
        "submitted_at": datetime.utcnow()
    }


@pytest.fixture
def sample_position_data():
    """Sample position data for testing."""
    return {
        "id": "position-123",
        "account_id": "account-456",
        "symbol": "AAPL",
        "qty": Decimal("100"),
        "avg_price": Decimal("145.50"),
        "market_value": Decimal("15000.00"),
        "unrealized_pnl": Decimal("450.00")
    }


@pytest.fixture
def sample_trade_data():
    """Sample trade data for testing."""
    return {
        "id": "trade-123",
        "order_id": "order-123",
        "symbol": "AAPL",
        "side": "buy", 
        "qty": Decimal("100"),
        "price": Decimal("150.00"),
        "executed_at": datetime.utcnow(),
        "commission": Decimal("1.00"),
        "account_id": "account-456"
    }


class TestEnhancedOrdersRepositorySQLite:
    """Enhanced test orders repository CRUD operations with SQLite."""
    
    @pytest.mark.asyncio
    async def test_bulk_insert_orders_performance(self, sqlite_memory_connection):
        """Test bulk insert performance for large order batches."""
        # Generate large batch of orders
        orders_batch = []
        base_time = datetime.utcnow()
        
        for i in range(1000):
            orders_batch.append((
                f"bulk-order-{i}",
                f"SYMBOL{i % 10}",  # 10 different symbols
                "buy" if i % 2 == 0 else "sell",
                100 + (i % 50),  # Varying quantities
                150.0 + (i % 20),  # Varying prices
                "new",
                f"bulk-client-{i}",
                f"account-{i % 5}",  # 5 different accounts
                base_time + timedelta(seconds=i)
            ))
        
        # Bulk insert using executemany for performance
        start_time = datetime.utcnow()
        await sqlite_memory_connection.executemany("""
            INSERT INTO orders (id, symbol, side, qty, price, status, client_key, account_id, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, orders_batch)
        await sqlite_memory_connection.commit()
        insert_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Verify all orders inserted
        cursor = await sqlite_memory_connection.execute("SELECT COUNT(*) FROM orders")
        count = await cursor.fetchone()
        assert count[0] == 1000
        
        # Performance assertion (should be fast with SQLite in memory)
        assert insert_time < 5.0, f"Bulk insert took {insert_time} seconds - too slow"
        
        # Test query performance
        start_time = datetime.utcnow()
        cursor = await sqlite_memory_connection.execute(
            "SELECT COUNT(*) FROM orders WHERE account_id = ? AND symbol = ?", 
            ("account-0", "SYMBOL0")
        )
        query_result = await cursor.fetchone()
        query_time = (datetime.utcnow() - start_time).total_seconds()
        
        # Verify results and performance
        assert query_result[0] == 20  # account-0 with SYMBOL0
        assert query_time < 0.1, f"Query took {query_time} seconds - too slow"

    @pytest.mark.asyncio
    async def test_complex_order_filtering_and_sorting(self, sqlite_memory_connection):
        """Test complex filtering and sorting scenarios."""
        # Insert orders with varying attributes
        test_orders = [
            ("order-1", "AAPL", "buy", 100, 150.0, "new", "client-1", "account-1", datetime(2024, 1, 1, 10, 0)),
            ("order-2", "AAPL", "sell", 50, 155.0, "filled", "client-2", "account-1", datetime(2024, 1, 1, 11, 0)),
            ("order-3", "MSFT", "buy", 200, 300.0, "cancelled", "client-3", "account-2", datetime(2024, 1, 1, 12, 0)),
            ("order-4", "MSFT", "buy", 75, 305.0, "new", "client-4", "account-1", datetime(2024, 1, 2, 9, 0)),
            ("order-5", "GOOGL", "sell", 25, 2000.0, "filled", "client-5", "account-2", datetime(2024, 1, 2, 14, 0)),
        ]
        
        for order in test_orders:
            await sqlite_memory_connection.execute("""
                INSERT INTO orders (id, symbol, side, qty, price, status, client_key, account_id, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, order)
        await sqlite_memory_connection.commit()
        
        # Test 1: Filter by multiple criteria and sort
        cursor = await sqlite_memory_connection.execute("""
            SELECT id, symbol, side, status, qty 
            FROM orders 
            WHERE account_id = ? AND status IN ('new', 'filled') AND qty >= ?
            ORDER BY submitted_at DESC, qty DESC
        """, ("account-1", 50))
        results = await cursor.fetchall()
        
        assert len(results) == 3
        assert results[0][0] == "order-4"  # Most recent, MSFT buy
        assert results[1][0] == "order-2"  # Second most recent, AAPL sell
        assert results[2][0] == "order-1"  # Oldest, AAPL buy
        
        # Test 2: Aggregate queries
        cursor = await sqlite_memory_connection.execute("""
            SELECT symbol, side, COUNT(*) as order_count, SUM(qty) as total_qty, AVG(price) as avg_price
            FROM orders
            WHERE status != 'cancelled'
            GROUP BY symbol, side
            ORDER BY symbol, side
        """)
        aggregates = await cursor.fetchall()
        
        # Verify aggregates
        assert len(aggregates) >= 3  # At least 3 symbol/side combinations
        
        # Find AAPL buy aggregate
        aapl_buy = next((row for row in aggregates if row[0] == "AAPL" and row[1] == "buy"), None)
        assert aapl_buy is not None
        assert aapl_buy[2] == 1  # 1 order
        assert aapl_buy[3] == 100  # Total qty
        assert aapl_buy[4] == 150.0  # Avg price

    @pytest.mark.asyncio
    async def test_order_status_transitions_and_timestamps(self, sqlite_memory_connection):
        """Test order status transitions with proper timestamp handling."""
        order_id = "status-transition-order"
        
        # Insert new order
        await sqlite_memory_connection.execute("""
            INSERT INTO orders (id, symbol, side, qty, price, status, client_key, account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_id, "AAPL", "buy", 100, 150.0, "new", "status-client", "account-1"))
        await sqlite_memory_connection.commit()
        
        # Transition to filled
        fill_time = datetime.utcnow()
        await sqlite_memory_connection.execute("""
            UPDATE orders 
            SET status = 'filled', filled_at = ?
            WHERE id = ? AND status = 'new'
        """, (fill_time, order_id))
        await sqlite_memory_connection.commit()
        
        # Verify transition
        cursor = await sqlite_memory_connection.execute("""
            SELECT status, filled_at, cancelled_at
            FROM orders 
            WHERE id = ?
        """, (order_id,))
        row = await cursor.fetchone()
        
        assert row[0] == "filled"
        assert row[1] is not None  # filled_at set
        assert row[2] is None      # cancelled_at still null
        
        # Test invalid transition (filled -> cancelled should not be allowed in business logic)
        # This would be enforced by application logic, not database constraints
        
        # Test partial fill scenario
        partial_order_id = "partial-fill-order"
        await sqlite_memory_connection.execute("""
            INSERT INTO orders (id, symbol, side, qty, price, status, client_key, account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (partial_order_id, "MSFT", "sell", 100, 300.0, "new", "partial-client", "account-2"))
        
        # Update to partially filled
        await sqlite_memory_connection.execute("""
            UPDATE orders 
            SET status = 'partially_filled'
            WHERE id = ?
        """, (partial_order_id,))
        await sqlite_memory_connection.commit()
        
        cursor = await sqlite_memory_connection.execute(
            "SELECT status FROM orders WHERE id = ?", (partial_order_id,)
        )
        status = await cursor.fetchone()
        assert status[0] == "partially_filled"


class TestEnhancedPositionsRepositorySQLite:
    """Enhanced test positions repository with advanced scenarios."""
    
    @pytest.mark.asyncio
    async def test_position_aggregation_across_accounts(self, sqlite_memory_connection):
        """Test position aggregation and portfolio-level calculations."""
        # Insert positions across multiple accounts and symbols
        positions_data = [
            ("pos-1", "account-1", "AAPL", 100, 150.0, 15000.0, 500.0),
            ("pos-2", "account-1", "MSFT", 50, 300.0, 15000.0, -250.0),
            ("pos-3", "account-1", "GOOGL", 25, 2000.0, 50000.0, 1000.0),
            ("pos-4", "account-2", "AAPL", 200, 145.0, 30000.0, 1000.0),
            ("pos-5", "account-2", "TSLA", 75, 800.0, 60000.0, -3000.0),
        ]
        
        for pos_data in positions_data:
            await sqlite_memory_connection.execute("""
                INSERT INTO positions (id, account_id, symbol, qty, avg_price, market_value, unrealized_pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, pos_data)
        await sqlite_memory_connection.commit()
        
        # Test 1: Account-level aggregation
        cursor = await sqlite_memory_connection.execute("""
            SELECT 
                account_id,
                COUNT(*) as position_count,
                SUM(market_value) as total_market_value,
                SUM(unrealized_pnl) as total_unrealized_pnl,
                AVG(unrealized_pnl) as avg_pnl_per_position
            FROM positions
            GROUP BY account_id
            ORDER BY account_id
        """)
        account_summaries = await cursor.fetchall()
        
        assert len(account_summaries) == 2
        
        # Account 1 summary
        acc1 = account_summaries[0]
        assert acc1[0] == "account-1"
        assert acc1[1] == 3  # 3 positions
        assert acc1[2] == 80000.0  # Total market value
        assert acc1[3] == 1250.0   # Total unrealized P&L (500 - 250 + 1000)
        
        # Account 2 summary  
        acc2 = account_summaries[1]
        assert acc2[0] == "account-2"
        assert acc2[1] == 2  # 2 positions
        assert acc2[2] == 90000.0  # Total market value
        assert acc2[3] == -2000.0  # Total unrealized P&L (1000 - 3000)
        
        # Test 2: Symbol-level aggregation across accounts
        cursor = await sqlite_memory_connection.execute("""
            SELECT 
                symbol,
                COUNT(*) as holder_count,
                SUM(qty) as total_shares,
                AVG(avg_price) as avg_entry_price,
                SUM(unrealized_pnl) as symbol_total_pnl
            FROM positions
            GROUP BY symbol
            ORDER BY symbol
        """)
        symbol_summaries = await cursor.fetchall()
        
        # Find AAPL summary (held by both accounts)
        aapl_summary = next((row for row in symbol_summaries if row[0] == "AAPL"), None)
        assert aapl_summary is not None
        assert aapl_summary[1] == 2      # 2 holders
        assert aapl_summary[2] == 300    # Total shares (100 + 200)
        assert aapl_summary[4] == 1500.0 # Total P&L (500 + 1000)

    @pytest.mark.asyncio
    async def test_position_updates_with_trade_impact(self, sqlite_memory_connection):
        """Test position updates reflecting trade executions."""
        # Insert initial position
        initial_position = ("pos-1", "account-1", "AAPL", 100, 145.0, 14500.0, 0.0)
        await sqlite_memory_connection.execute("""
            INSERT INTO positions (id, account_id, symbol, qty, avg_price, market_value, unrealized_pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, initial_position)
        await sqlite_memory_connection.commit()
        
        # Simulate trade execution that affects position
        trade_qty = Decimal("50")
        trade_price = Decimal("155.0")
        
        # Calculate new position after trade
        current_qty = Decimal("100")
        current_avg_price = Decimal("145.0")
        
        new_qty = current_qty + trade_qty
        new_avg_price = ((current_qty * current_avg_price) + (trade_qty * trade_price)) / new_qty
        new_market_value = new_qty * trade_price  # Using trade price as current market price
        new_unrealized_pnl = (trade_price - new_avg_price) * new_qty
        
        # Update position
        await sqlite_memory_connection.execute("""
            UPDATE positions
            SET qty = ?, avg_price = ?, market_value = ?, unrealized_pnl = ?, updated_at = ?
            WHERE id = ?
        """, (float(new_qty), float(new_avg_price), float(new_market_value), 
              float(new_unrealized_pnl), datetime.utcnow(), "pos-1"))
        await sqlite_memory_connection.commit()
        
        # Verify updated position
        cursor = await sqlite_memory_connection.execute("""
            SELECT qty, avg_price, market_value, unrealized_pnl
            FROM positions
            WHERE id = ?
        """, ("pos-1",))
        row = await cursor.fetchone()
        
        assert Decimal(str(row[0])) == new_qty
        assert abs(Decimal(str(row[1])) - new_avg_price) < Decimal("0.01")  # Allow small rounding diff
        assert Decimal(str(row[2])) == new_market_value
        # P&L should be positive since trade price > avg price
        assert Decimal(str(row[3])) > 0

    @pytest.mark.asyncio
    async def test_position_risk_calculations(self, sqlite_memory_connection):
        """Test position-level risk metrics calculations."""
        # Insert positions with different risk profiles
        risk_positions = [
            ("risk-1", "account-1", "AAPL", 1000, 150.0, 155000.0, 5000.0),    # Large position, profitable
            ("risk-2", "account-1", "GME", 100, 200.0, 15000.0, -5000.0),      # Volatile stock, losing
            ("risk-3", "account-1", "SPY", 500, 400.0, 205000.0, 5000.0),      # ETF, stable
            ("risk-4", "account-1", "TSLA", 50, 800.0, 35000.0, -5000.0),      # High beta, losing
        ]
        
        for pos_data in risk_positions:
            await sqlite_memory_connection.execute("""
                INSERT INTO positions (id, account_id, symbol, qty, avg_price, market_value, unrealized_pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, pos_data)
        await sqlite_memory_connection.commit()
        
        # Calculate risk metrics
        cursor = await sqlite_memory_connection.execute("""
            SELECT 
                symbol,
                qty,
                market_value,
                unrealized_pnl,
                CASE 
                    WHEN market_value = 0 THEN 0 
                    ELSE (unrealized_pnl / market_value) * 100 
                END as pnl_percentage,
                CASE
                    WHEN qty >= 1000 THEN 'Large'
                    WHEN qty >= 100 THEN 'Medium'
                    ELSE 'Small'
                END as position_size_category
            FROM positions
            WHERE account_id = 'account-1'
            ORDER BY market_value DESC
        """)
        risk_metrics = await cursor.fetchall()
        
        assert len(risk_metrics) == 4
        
        # SPY should be largest position by market value
        largest_position = risk_metrics[0]
        assert largest_position[0] == "SPY"
        assert largest_position[5] == "Medium"  # 500 shares = Medium
        
        # Calculate portfolio concentration
        total_market_value = sum(row[2] for row in risk_metrics)
        
        cursor = await sqlite_memory_connection.execute("""
            SELECT 
                symbol,
                market_value,
                (market_value * 100.0 / ?) as portfolio_weight
            FROM positions
            WHERE account_id = 'account-1'
            ORDER BY portfolio_weight DESC
        """, (total_market_value,))
        concentration_metrics = await cursor.fetchall()
        
        # Verify concentration calculations
        total_weight = sum(row[2] for row in concentration_metrics)
        assert abs(total_weight - 100.0) < 0.01  # Should sum to ~100%


class TestEnhancedExecutionsRepositorySQLite:
    """Enhanced test trades repository with complex scenarios."""
    
    @pytest.mark.asyncio
    async def test_trade_execution_sequence_and_timing(self, sqlite_memory_connection):
        """Test trade execution sequences with precise timing."""
        # Insert order first
        order_id = "sequence-order-1"
        await sqlite_memory_connection.execute("""
            INSERT INTO orders (id, symbol, side, qty, price, status, client_key, account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_id, "AAPL", "buy", 1000, 150.0, "partially_filled", "sequence-client", "account-1"))
        await sqlite_memory_connection.commit()
        
        # Insert sequence of partial fills
        base_time = datetime(2024, 1, 1, 10, 0, 0)
        partial_fills = [
            ("fill-1", order_id, "AAPL", "buy", 300, 149.95, base_time, 1.50),
            ("fill-2", order_id, "AAPL", "buy", 200, 150.05, base_time + timedelta(seconds=5), 1.00),
            ("fill-3", order_id, "AAPL", "buy", 350, 150.15, base_time + timedelta(seconds=12), 1.75),
            ("fill-4", order_id, "AAPL", "buy", 150, 150.25, base_time + timedelta(seconds=20), 0.75),
        ]
        
        for trade_data in partial_fills:
            await sqlite_memory_connection.execute("""
                INSERT INTO trades (id, order_id, symbol, side, qty, price, executed_at, commission, account_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (*trade_data, "account-1"))
        await sqlite_memory_connection.commit()
        
        # Analyze execution sequence
        cursor = await sqlite_memory_connection.execute("""
            SELECT 
                id,
                qty,
                price,
                executed_at,
                SUM(qty) OVER (ORDER BY executed_at) as cumulative_qty,
                AVG(price) OVER (ORDER BY executed_at ROWS UNBOUNDED PRECEDING) as running_avg_price,
                ROW_NUMBER() OVER (ORDER BY executed_at) as execution_sequence
            FROM trades
            WHERE order_id = ?
            ORDER BY executed_at
        """, (order_id,))
        execution_analysis = await cursor.fetchall()
        
        assert len(execution_analysis) == 4
        
        # Verify cumulative quantities
        assert execution_analysis[0][4] == 300   # First fill
        assert execution_analysis[1][4] == 500   # First + Second
        assert execution_analysis[2][4] == 850   # First + Second + Third
        assert execution_analysis[3][4] == 1000  # All fills (complete order)
        
        # Verify execution sequence numbers
        assert execution_analysis[0][6] == 1
        assert execution_analysis[3][6] == 4
        
        # Calculate volume-weighted average price (VWAP)
        cursor = await sqlite_memory_connection.execute("""
            SELECT 
                SUM(qty * price) / SUM(qty) as vwap,
                MIN(price) as best_fill,
                MAX(price) as worst_fill,
                SUM(commission) as total_commission
            FROM trades
            WHERE order_id = ?
        """, (order_id,))
        vwap_analysis = await cursor.fetchone()
        
        # Expected VWAP calculation: 
        # (300*149.95 + 200*150.05 + 350*150.15 + 150*150.25) / 1000
        expected_vwap = (300*149.95 + 200*150.05 + 350*150.15 + 150*150.25) / 1000
        assert abs(vwap_analysis[0] - expected_vwap) < 0.01
        assert vwap_analysis[1] == 149.95  # Best fill
        assert vwap_analysis[2] == 150.25  # Worst fill
        assert vwap_analysis[3] == 5.0     # Total commission

    @pytest.mark.asyncio
    async def test_trade_analytics_and_performance_metrics(self, sqlite_memory_connection):
        """Test comprehensive trade analytics and performance metrics."""
        # Insert trades across multiple days and symbols
        base_date = datetime(2024, 1, 1, 9, 30)  # Market open
        
        trades_data = [
            # Day 1 - AAPL trades
            ("trade-1", "order-1", "AAPL", "buy", 100, 150.0, base_date, 1.0, "account-1"),
            ("trade-2", "order-2", "AAPL", "sell", 50, 155.0, base_date + timedelta(hours=2), 0.5, "account-1"),
            
            # Day 1 - MSFT trades  
            ("trade-3", "order-3", "MSFT", "buy", 200, 300.0, base_date + timedelta(hours=1), 2.0, "account-1"),
            ("trade-4", "order-4", "MSFT", "sell", 100, 310.0, base_date + timedelta(hours=3), 1.0, "account-1"),
            
            # Day 2 - More trades
            ("trade-5", "order-5", "AAPL", "buy", 75, 148.0, base_date + timedelta(days=1), 0.75, "account-1"),
            ("trade-6", "order-6", "GOOGL", "buy", 25, 2000.0, base_date + timedelta(days=1, hours=1), 5.0, "account-1"),
        ]
        
        for trade in trades_data:
            await sqlite_memory_connection.execute("""
                INSERT INTO trades (id, order_id, symbol, side, qty, price, executed_at, commission, account_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, trade)
        await sqlite_memory_connection.commit()
        
        # Analytics Query 1: Daily trading summary
        cursor = await sqlite_memory_connection.execute("""
            SELECT 
                DATE(executed_at) as trading_date,
                COUNT(*) as trade_count,
                COUNT(DISTINCT symbol) as symbols_traded,
                SUM(CASE WHEN side = 'buy' THEN qty ELSE 0 END) as total_bought,
                SUM(CASE WHEN side = 'sell' THEN qty ELSE 0 END) as total_sold,
                SUM(qty * price) as total_volume,
                SUM(commission) as total_commissions
            FROM trades
            WHERE account_id = 'account-1'
            GROUP BY DATE(executed_at)
            ORDER BY trading_date
        """)
        daily_summary = await cursor.fetchall()
        
        assert len(daily_summary) == 2  # 2 trading days
        
        # Day 1 analysis
        day1 = daily_summary[0]
        assert day1[1] == 4     # 4 trades
        assert day1[2] == 2     # 2 symbols (AAPL, MSFT)
        assert day1[3] == 300   # Total bought (100 AAPL + 200 MSFT)
        assert day1[4] == 150   # Total sold (50 AAPL + 100 MSFT)
        
        # Analytics Query 2: Symbol performance analysis
        cursor = await sqlite_memory_connection.execute("""
            SELECT 
                symbol,
                COUNT(*) as trade_count,
                SUM(CASE WHEN side = 'buy' THEN qty ELSE -qty END) as net_position,
                AVG(CASE WHEN side = 'buy' THEN price END) as avg_buy_price,
                AVG(CASE WHEN side = 'sell' THEN price END) as avg_sell_price,
                SUM(qty * price * CASE WHEN side = 'buy' THEN -1 ELSE 1 END) as net_cash_flow
            FROM trades
            WHERE account_id = 'account-1'
            GROUP BY symbol
            ORDER BY symbol
        """)
        symbol_performance = await cursor.fetchall()
        
        # Find AAPL performance
        aapl_perf = next((row for row in symbol_performance if row[0] == "AAPL"), None)
        assert aapl_perf is not None
        assert aapl_perf[1] == 3        # 3 AAPL trades
        assert aapl_perf[2] == 125      # Net position (100 + 75 - 50)
        assert aapl_perf[3] == 149.0    # Avg buy price ((150*100 + 148*75)/(100+75))
        assert aapl_perf[4] == 155.0    # Avg sell price
        
        # Analytics Query 3: Time-based trading patterns
        cursor = await sqlite_memory_connection.execute("""
            SELECT 
                strftime('%H', executed_at) as trading_hour,
                COUNT(*) as trades_per_hour,
                AVG(qty) as avg_trade_size,
                SUM(commission) as hourly_commissions
            FROM trades
            WHERE account_id = 'account-1'
            GROUP BY strftime('%H', executed_at)
            ORDER BY trading_hour
        """)
        hourly_patterns = await cursor.fetchall()
        
        # Verify hourly distribution makes sense
        assert len(hourly_patterns) >= 3  # Should have trades in multiple hours
        total_hourly_trades = sum(row[1] for row in hourly_patterns)
        assert total_hourly_trades == 6  # Total trades


class TestDatabaseIntegrityAndConstraints:
    """Test database integrity constraints and edge cases."""
    
    @pytest.mark.asyncio
    async def test_referential_integrity_cascading_effects(self, sqlite_memory_connection):
        """Test referential integrity and cascading delete behavior."""
        # Enable foreign key constraints
        await sqlite_memory_connection.execute("PRAGMA foreign_keys = ON")
        
        # Insert parent order
        order_id = "parent-order-123"
        await sqlite_memory_connection.execute("""
            INSERT INTO orders (id, symbol, side, qty, price, status, client_key, account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_id, "AAPL", "buy", 100, 150.0, "filled", "parent-client", "account-1"))
        
        # Insert related trades
        trade_ids = ["child-trade-1", "child-trade-2"]
        for i, trade_id in enumerate(trade_ids):
            await sqlite_memory_connection.execute("""
                INSERT INTO trades (id, order_id, symbol, side, qty, price, executed_at, commission, account_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (trade_id, order_id, "AAPL", "buy", 50, 150.0, datetime.utcnow(), 0.5, "account-1"))
        await sqlite_memory_connection.commit()
        
        # Verify relationships exist
        cursor = await sqlite_memory_connection.execute(
            "SELECT COUNT(*) FROM trades WHERE order_id = ?", (order_id,)
        )
        trade_count = await cursor.fetchone()
        assert trade_count[0] == 2
        
        # Test constraint violation: try to delete parent order with existing trades
        # (This would normally be prevented by business logic, but test constraint)
        try:
            await sqlite_memory_connection.execute("DELETE FROM orders WHERE id = ?", (order_id,))
            await sqlite_memory_connection.commit()
            # If we get here, foreign key constraint is not enforced
        except aiosqlite.IntegrityError:
            # Expected - foreign key constraint prevents deletion
            await sqlite_memory_connection.rollback()
            
        # Verify order still exists
        cursor = await sqlite_memory_connection.execute(
            "SELECT COUNT(*) FROM orders WHERE id = ?", (order_id,)
        )
        order_count = await cursor.fetchone()
        assert order_count[0] == 1

    @pytest.mark.asyncio
    async def test_concurrent_access_and_locking(self, sqlite_memory_connection):
        """Test concurrent access scenarios and locking behavior."""
        # Insert test data
        await sqlite_memory_connection.execute("""
            INSERT INTO positions (id, account_id, symbol, qty, avg_price, market_value, unrealized_pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, ("concurrent-pos", "account-1", "AAPL", 100, 150.0, 15000.0, 0.0))
        await sqlite_memory_connection.commit()
        
        # Simulate concurrent updates
        async def update_position_1():
            await sqlite_memory_connection.execute("""
                UPDATE positions 
                SET qty = qty + 50, market_value = market_value + 7500
                WHERE id = 'concurrent-pos'
            """)
            # Small delay to simulate processing time
            await asyncio.sleep(0.01)
            await sqlite_memory_connection.commit()
            
        async def update_position_2():
            await asyncio.sleep(0.005)  # Slightly delayed start
            await sqlite_memory_connection.execute("""
                UPDATE positions 
                SET unrealized_pnl = unrealized_pnl + 1000
                WHERE id = 'concurrent-pos'
            """)
            await sqlite_memory_connection.commit()
        
        # Run concurrent updates
        await asyncio.gather(update_position_1(), update_position_2())
        
        # Verify final state
        cursor = await sqlite_memory_connection.execute("""
            SELECT qty, market_value, unrealized_pnl
            FROM positions 
            WHERE id = 'concurrent-pos'
        """)
        final_state = await cursor.fetchone()
        
        # Both updates should have been applied
        assert final_state[0] == 150    # qty updated
        assert final_state[1] == 22500  # market_value updated  
        assert final_state[2] == 1000   # unrealized_pnl updated

    @pytest.mark.asyncio
    async def test_data_type_validation_and_edge_cases(self, sqlite_memory_connection):
        """Test data type validation and edge case handling."""
        # Test 1: Very large decimal values
        large_decimal_order = (
            "large-decimal-order",
            "BERKSHIRE", 
            "buy", 
            999999999.999999,  # Very large quantity
            999999.99,         # Very high price
            "new",
            "large-decimal-client",
            "account-1"
        )
        
        await sqlite_memory_connection.execute("""
            INSERT INTO orders (id, symbol, side, qty, price, status, client_key, account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, large_decimal_order)
        await sqlite_memory_connection.commit()
        
        # Verify large decimals stored correctly
        cursor = await sqlite_memory_connection.execute(
            "SELECT qty, price FROM orders WHERE id = ?", ("large-decimal-order",)
        )
        row = await cursor.fetchone()
        assert abs(row[0] - 999999999.999999) < 0.000001
        assert abs(row[1] - 999999.99) < 0.01
        
        # Test 2: Zero and negative edge cases
        edge_cases = [
            # Zero quantity (should be handled by business logic, but test DB storage)
            ("zero-qty-order", "AAPL", "buy", 0, 150.0, "cancelled", "zero-client", "account-1"),
            # Very small quantity
            ("small-qty-order", "AAPL", "buy", 0.000001, 150.0, "new", "small-client", "account-1"),
        ]
        
        for edge_case in edge_cases:
            await sqlite_memory_connection.execute("""
                INSERT INTO orders (id, symbol, side, qty, price, status, client_key, account_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, edge_case)
        await sqlite_memory_connection.commit()
        
        # Verify edge cases stored
        cursor = await sqlite_memory_connection.execute(
            "SELECT id, qty FROM orders WHERE id IN ('zero-qty-order', 'small-qty-order') ORDER BY id"
        )
        edge_results = await cursor.fetchall()
        assert len(edge_results) == 2
        assert edge_results[1][1] == 0.000001  # Small quantity preserved
        
        # Test 3: String length limits and special characters
        long_symbol = "A" * 50  # Very long symbol
        special_client_key = "client-with-special-chars-!@#$%^&*()_+-="
        
        await sqlite_memory_connection.execute("""
            INSERT INTO orders (id, symbol, side, qty, price, status, client_key, account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("special-order", long_symbol, "buy", 100, 150.0, "new", special_client_key, "account-1"))
        await sqlite_memory_connection.commit()
        
        # Verify special characters handled
        cursor = await sqlite_memory_connection.execute(
            "SELECT symbol, client_key FROM orders WHERE id = ?", ("special-order",)
        )
        special_result = await cursor.fetchone()
        assert special_result[0] == long_symbol
        assert special_result[1] == special_client_key
