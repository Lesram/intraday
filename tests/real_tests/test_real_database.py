"""
REAL Database Integration Tests.

These tests validate ACTUAL database operations:
- Real CRUD operations with real database
- Real transaction handling and rollbacks
- Real concurrent access scenarios
- Real constraint validation
- Real query performance

NO MOCKING - All operations hit the actual database.
"""

import asyncio
import uuid
from datetime import datetime, UTC, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import text, select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError


def make_order_id():
    """Generate a unique order ID."""
    return uuid.uuid4()


def make_idempotency_key():
    """Generate a unique idempotency key for orders."""
    return f"test_{uuid.uuid4().hex}"


# =============================================================================
# ORDER TABLE REAL TESTS
# =============================================================================

class TestRealOrderDatabase:
    """
    Real database tests for Order model.
    Tests actual CRUD operations on the orders table.
    """
    
    def test_create_order_real_insert(self, db_session: Session):
        """Test that we can actually insert an order into the database."""
        from backend.infra.schemas import Order
        
        order_id = make_order_id()
        order = Order(
            id=order_id,
            client_idempotency_key=make_idempotency_key(),
            symbol="AAPL",
            side="buy",
            qty=100,
            order_type="market",
            tif="gtc",
            status="pending",
            submitted_at=datetime.now(UTC)
        )
        
        db_session.add(order)
        db_session.flush()  # Force insert without commit
        
        # Verify the order exists in database
        result = db_session.execute(
            text("SELECT id, symbol, qty FROM orders WHERE id = :id"),
            {"id": str(order_id)}
        ).fetchone()
        
        assert result is not None, "Order was not inserted into database"
        assert result[1] == "AAPL"
        assert result[2] == 100
    
    def test_order_query_performance(self, db_session: Session, timing):
        """Test that order queries complete in acceptable time."""
        from backend.infra.schemas import Order
        
        # Insert multiple orders
        for i in range(100):
            order = Order(
                id=make_order_id(),
                client_idempotency_key=make_idempotency_key(),
                symbol="AAPL" if i % 2 == 0 else "MSFT",
                side="buy" if i % 3 == 0 else "sell",
                qty=i + 1,
                order_type="market",
                tif="gtc",
                status="filled",
                submitted_at=datetime.now(UTC)
            )
            db_session.add(order)
        
        db_session.flush()
        
        # Time a complex query
        timing.start()
        result = db_session.execute(
            text("""
                SELECT symbol, COUNT(*) as count, SUM(qty) as total_qty
                FROM orders 
                WHERE status = 'filled'
                GROUP BY symbol
                ORDER BY total_qty DESC
            """)
        ).fetchall()
        timing.stop()
        
        # Query should complete in under 100ms even with 100 records
        timing.assert_under(0.1, "Order aggregation query")
        assert len(result) >= 1
    
    def test_order_update_real_modification(self, db_session: Session):
        """Test that order updates are persisted correctly."""
        from backend.infra.schemas import Order
        
        order_id = make_order_id()
        order = Order(
            id=order_id,
            client_idempotency_key=make_idempotency_key(),
            symbol="GOOGL",
            side="buy",
            qty=50,
            order_type="limit",
            tif="gtc",
            limit_price=Decimal("175.00"),
            status="pending",
            submitted_at=datetime.now(UTC)
        )
        
        db_session.add(order)
        db_session.flush()
        
        # Update the order
        order.status = "filled"
        order.filled_qty = Decimal("50")
        order.avg_fill_price = Decimal("175.50")
        
        db_session.flush()
        
        # Verify update persisted
        result = db_session.execute(
            text("SELECT status, filled_qty, avg_fill_price FROM orders WHERE id = :id"),
            {"id": str(order_id)}
        ).fetchone()
        
        assert result[0] == "filled"
        assert Decimal(str(result[1])) == Decimal("50")
        assert Decimal(str(result[2])) == Decimal("175.50")
    
    def test_order_delete_real_removal(self, db_session: Session):
        """Test that order deletion actually removes from database."""
        from backend.infra.schemas import Order
        
        order_id = make_order_id()
        order = Order(
            id=order_id,
            client_idempotency_key=make_idempotency_key(),
            symbol="TSLA",
            side="sell",
            qty=25,
            order_type="market",
            tif="ioc",
            status="cancelled",
            submitted_at=datetime.now(UTC)
        )
        
        db_session.add(order)
        db_session.flush()
        
        # Verify exists
        count_before = db_session.execute(
            text("SELECT COUNT(*) FROM orders WHERE id = :id"),
            {"id": str(order_id)}
        ).scalar()
        assert count_before == 1
        
        # Delete
        db_session.delete(order)
        db_session.flush()
        
        # Verify removed
        count_after = db_session.execute(
            text("SELECT COUNT(*) FROM orders WHERE id = :id"),
            {"id": str(order_id)}
        ).scalar()
        assert count_after == 0


# =============================================================================
# POSITION TABLE REAL TESTS
# =============================================================================

class TestRealPositionDatabase:
    """Real database tests for Position model."""
    
    def test_position_create_with_calculations(self, db_session: Session):
        """Test position creation with P&L calculations."""
        from backend.infra.schemas import Position
        
        symbol = f"NVDA_{uuid.uuid4().hex[:8]}"  # Unique symbol for test
        
        position = Position(
            symbol=symbol,
            qty=Decimal("100"),
            avg_price=Decimal("450.00"),
            realized_pnl=Decimal("2500.00")
        )
        
        db_session.add(position)
        db_session.flush()
        
        # Verify position stored correctly
        result = db_session.execute(
            text("""
                SELECT qty, avg_price, realized_pnl
                FROM positions WHERE symbol = :symbol
            """),
            {"symbol": symbol}
        ).fetchone()
        
        assert result is not None
        assert Decimal(str(result[0])) == Decimal("100")
        assert Decimal(str(result[1])) == Decimal("450.00")
        assert Decimal(str(result[2])) == Decimal("2500.00")
    
    def test_position_aggregate_queries(self, db_session: Session):
        """Test real aggregate queries across positions."""
        from backend.infra.schemas import Position
        
        # Create diversified portfolio with unique symbols
        test_id = uuid.uuid4().hex[:6]
        positions = [
            Position(
                symbol=f"AAPL_{test_id}",
                qty=Decimal("50"),
                avg_price=Decimal("175.00"),
                realized_pnl=Decimal("250.00")
            ),
            Position(
                symbol=f"MSFT_{test_id}",
                qty=Decimal("30"),
                avg_price=Decimal("400.00"),
                realized_pnl=Decimal("-300.00")
            ),
            Position(
                symbol=f"GOOGL_{test_id}",
                qty=Decimal("20"),
                avg_price=Decimal("140.00"),
                realized_pnl=Decimal("100.00")
            )
        ]
        
        for pos in positions:
            db_session.add(pos)
        db_session.flush()
        
        # Calculate total portfolio metrics for our test positions
        result = db_session.execute(
            text("""
                SELECT 
                    COUNT(*) as position_count,
                    SUM(qty * avg_price) as total_market_value,
                    SUM(realized_pnl) as total_realized_pnl
                FROM positions
                WHERE symbol LIKE :pattern
            """),
            {"pattern": f"%_{test_id}"}
        ).fetchone()
        
        assert result[0] == 3, "Should have 3 positions"
        # 50*175 + 30*400 + 20*140 = 8750 + 12000 + 2800 = 23550
        assert Decimal(str(result[1])) == Decimal("23550.00"), "Total market value mismatch"
        # 250 - 300 + 100 = 50
        assert Decimal(str(result[2])) == Decimal("50.00"), "Total P&L should be $50"


# =============================================================================
# STRATEGY TABLE REAL TESTS
# =============================================================================

class TestRealStrategyDatabase:
    """Real database tests for Strategy model."""
    
    def test_strategy_json_parameters(self, db_session: Session):
        """Test that JSON parameters are stored and retrieved correctly."""
        from backend.infra.schemas import Strategy
        
        strategy_name = f"test_momentum_strategy_{uuid.uuid4().hex[:8]}"
        
        params = {
            "lookback_period": 20,
            "momentum_threshold": 0.02,
            "risk_multiplier": 1.5,
            "nested": {
                "level1": {
                    "level2": "deep_value"
                }
            }
        }
        
        strategy = Strategy(
            id=uuid.uuid4(),
            name=strategy_name,
            strategy_type="momentum",
            parameters=params,
            symbols=["AAPL", "MSFT", "GOOGL"],
            status="active"
        )
        
        db_session.add(strategy)
        db_session.flush()
        
        # Re-query to ensure JSON round-trip works
        db_session.expire(strategy)
        
        result = db_session.execute(
            text("SELECT parameters, symbols FROM strategies WHERE name = :name"),
            {"name": strategy_name}
        ).fetchone()
        
        assert result is not None
        
        # Verify the strategy can be loaded with correct params
        loaded_strategy = db_session.query(Strategy).filter_by(
            name=strategy_name
        ).first()
        
        assert loaded_strategy.parameters["lookback_period"] == 20
        assert loaded_strategy.symbols == ["AAPL", "MSFT", "GOOGL"]
        assert loaded_strategy.parameters["nested"]["level1"]["level2"] == "deep_value"


# =============================================================================
# TRANSACTION & CONCURRENCY TESTS
# =============================================================================

class TestRealTransactions:
    """Real transaction handling tests."""
    
    def test_transaction_rollback_on_error(self, db_session: Session):
        """Test that transactions properly rollback on error."""
        from backend.infra.schemas import Order
        
        order_id = make_order_id()
        
        # Insert first order
        order = Order(
            id=order_id,
            client_idempotency_key=make_idempotency_key(),
            symbol="AAPL",
            side="buy",
            qty=10,
            order_type="market",
            tif="gtc",
            status="pending",
            submitted_at=datetime.now(UTC)
        )
        db_session.add(order)
        db_session.flush()
        
        # Verify first order exists
        assert db_session.execute(
            text("SELECT COUNT(*) FROM orders WHERE id = :id"),
            {"id": str(order_id)}
        ).scalar() == 1
        
        # Now rollback
        db_session.rollback()
        
        # Order should no longer exist
        assert db_session.execute(
            text("SELECT COUNT(*) FROM orders WHERE id = :id"),
            {"id": str(order_id)}
        ).scalar() == 0
    
    def test_unique_constraint_enforcement(self, db_session: Session):
        """Test that unique constraints are enforced (idempotency key)."""
        from backend.infra.schemas import Order
        
        idempotency_key = make_idempotency_key()
        
        order1 = Order(
            id=make_order_id(),
            client_idempotency_key=idempotency_key,
            symbol="AAPL",
            side="buy",
            qty=10,
            order_type="market",
            tif="gtc",
            status="pending",
            submitted_at=datetime.now(UTC)
        )
        db_session.add(order1)
        db_session.flush()
        
        # Try to insert duplicate idempotency key - should fail
        order2 = Order(
            id=make_order_id(),
            client_idempotency_key=idempotency_key,  # Same key - should fail
            symbol="MSFT",
            side="sell",
            qty=20,
            order_type="market",
            tif="gtc",
            status="pending",
            submitted_at=datetime.now(UTC)
        )
        db_session.add(order2)
        
        with pytest.raises(IntegrityError):
            db_session.flush()


# =============================================================================
# EXECUTION/TRADE HISTORY REAL TESTS
# =============================================================================

class TestRealTradeHistory:
    """Real tests for trade history and audit trail."""
    
    def test_trade_execution_audit_trail(self, db_session: Session):
        """Test that trade executions create proper audit trail."""
        from backend.infra.schemas import Execution, Order
        
        # Create order first
        order_id = make_order_id()
        order = Order(
            id=order_id,
            client_idempotency_key=make_idempotency_key(),
            symbol="AAPL",
            side="buy",
            qty=100,
            order_type="market",
            tif="gtc",
            status="filled",
            filled_qty=Decimal("100"),
            avg_fill_price=Decimal("175.50"),
            submitted_at=datetime.now(UTC)
        )
        db_session.add(order)
        db_session.flush()
        
        # Create execution record
        execution = Execution(
            id=uuid.uuid4(),
            order_id=order_id,
            fill_qty=Decimal("100"),
            fill_price=Decimal("175.50"),
            ts=datetime.now(UTC),
            venue="NASDAQ"
        )
        db_session.add(execution)
        db_session.flush()
        
        # Query execution history
        result = db_session.execute(
            text("""
                SELECT e.fill_qty, e.fill_price, o.order_type, o.symbol
                FROM executions e
                JOIN orders o ON e.order_id = o.id
                WHERE o.id = :order_id
            """),
            {"order_id": str(order_id)}
        ).fetchone()
        
        assert result is not None
        assert Decimal(str(result[0])) == Decimal("100")
        assert Decimal(str(result[1])) == Decimal("175.50")
        assert result[2] == "market"
        assert result[3] == "AAPL"


# =============================================================================
# PERFORMANCE BENCHMARKS
# =============================================================================

class TestDatabasePerformance:
    """Real performance benchmarks for database operations."""
    
    def test_bulk_order_insert_performance(self, db_session: Session, timing):
        """Test bulk order insert completes in acceptable time."""
        from backend.infra.schemas import Order
        
        orders = []
        for i in range(1000):
            orders.append(Order(
                id=make_order_id(),
                client_idempotency_key=make_idempotency_key(),
                symbol=["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"][i % 5],
                side="buy" if i % 2 == 0 else "sell",
                qty=i + 1,
                order_type="market",
                tif="gtc",
                status="pending",
                submitted_at=datetime.now(UTC)
            ))
        
        timing.start()
        db_session.add_all(orders)
        db_session.flush()
        elapsed = timing.stop()
        
        # 1000 inserts should complete in under 5 seconds
        timing.assert_under(5.0, "Bulk insert of 1000 orders")
        
        # Verify all inserted
        count = db_session.execute(
            text("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
        ).scalar()
        assert count >= 1000
    
    def test_complex_analytics_query_performance(self, db_session: Session, timing):
        """Test complex analytics queries perform acceptably."""
        from backend.infra.schemas import Order
        
        # Insert test data
        now = datetime.now(UTC)
        for i in range(500):
            order = Order(
                id=make_order_id(),
                client_idempotency_key=make_idempotency_key(),
                symbol=["AAPL", "MSFT", "GOOGL"][i % 3],
                side="buy" if i % 2 == 0 else "sell",
                qty=(i % 100) + 1,
                order_type="market",
                tif="gtc",
                status="filled",
                filled_qty=Decimal((i % 100) + 1),
                avg_fill_price=Decimal(str(150 + (i % 50))),
                submitted_at=now - timedelta(days=i % 30)
            )
            db_session.add(order)
        
        db_session.flush()
        
        # Run complex analytics query
        timing.start()
        result = db_session.execute(
            text("""
                SELECT 
                    symbol,
                    DATE(submitted_at) as trade_date,
                    COUNT(*) as trade_count,
                    SUM(CASE WHEN side = 'buy' THEN qty ELSE 0 END) as buy_volume,
                    SUM(CASE WHEN side = 'sell' THEN qty ELSE 0 END) as sell_volume,
                    AVG(avg_fill_price) as avg_price
                FROM orders
                WHERE status = 'filled'
                GROUP BY symbol, DATE(submitted_at)
                ORDER BY trade_date DESC, symbol
                LIMIT 100
            """)
        ).fetchall()
        timing.stop()
        
        timing.assert_under(1.0, "Complex analytics query")
        assert len(result) > 0

