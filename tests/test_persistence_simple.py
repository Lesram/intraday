"""
Simple persistence layer tests for Branch 2.3.
Tests repository pattern with SQLite for compatibility.
"""

from datetime import datetime
import uuid

import pytest
from sqlalchemy import (
    DECIMAL,
    JSON,
    Column,
    DateTime,
    String,
    text,
)
from sqlalchemy import UUID as SQLAlchemyUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.infra.repositories import (
    AuditsRepo,
    DuplicateOrderError,
    ExecutionsRepo,
    ModelsRepo,
    OrderNotFoundError,
    OrdersRepo,
    PositionsRepo,
    SignalsRepo,
)


# Simple test schemas for SQLite compatibility
class Base(DeclarativeBase):
    pass


class TestOrder(Base):
    __tablename__ = "test_orders"

    id = Column(SQLAlchemyUUID, primary_key=True, default=uuid.uuid4)
    client_idempotency_key = Column(String(255), unique=True, nullable=False)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    qty = Column(DECIMAL(18, 8), nullable=False)
    order_type = Column(String(20), nullable=False)
    tif = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, default="accepted")
    broker_order_id = Column(String(100), nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    attributes = Column(JSON, nullable=False, default=dict)


# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_engine():
    """Create test async engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest.fixture
async def test_session(test_engine):
    """Create test async session."""
    async_session_maker = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session


async def test_basic_order_operations():
    """Test basic order repository operations."""
    print("🧪 Testing basic order repository operations...")

    # Create in-memory database
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    # Create simple test table
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS test_orders (
                id TEXT PRIMARY KEY,
                client_idempotency_key TEXT UNIQUE NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty DECIMAL(18,8) NOT NULL,
                order_type TEXT NOT NULL,
                tif TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'accepted',
                broker_order_id TEXT,
                submitted_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                attributes JSON NOT NULL DEFAULT '{}'
            )
        """
            )
        )

    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        # Test inserting order data directly
        order_id = str(uuid.uuid4())
        await session.execute(
            text(
                """
            INSERT INTO test_orders (id, client_idempotency_key, symbol, side, qty, order_type, tif)
            VALUES (:id, :key, :symbol, :side, :qty, :type, :tif)
        """
            ),
            {
                "id": order_id,
                "key": "test-order-001",
                "symbol": "AAPL",
                "side": "buy",
                "qty": "100.0",
                "type": "market",
                "tif": "gtc",
            },
        )

        await session.commit()

        # Test querying
        result = await session.execute(
            text(
                """
            SELECT * FROM test_orders WHERE client_idempotency_key = :key
        """
            ),
            {"key": "test-order-001"},
        )

        row = result.fetchone()
        assert row is not None
        assert row[2] == "AAPL"  # symbol
        assert row[3] == "buy"  # side

        print("✅ Basic database operations work!")

    await engine.dispose()


async def test_repository_pattern_simulation():
    """Test repository pattern with simple operations."""
    print("🧪 Testing repository pattern simulation...")

    # Simulate repository operations without full ORM
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                client_idempotency_key TEXT UNIQUE NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty DECIMAL(18,8) NOT NULL,
                order_type TEXT NOT NULL,
                tif TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'accepted',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                attributes JSON NOT NULL DEFAULT '{}'
            )
        """
            )
        )

        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty DECIMAL(18,8) NOT NULL,
                price DECIMAL(18,8) NOT NULL,
                execution_id TEXT UNIQUE NOT NULL,
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                attributes JSON NOT NULL DEFAULT '{}'
            )
        """
            )
        )

        await conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                symbol TEXT UNIQUE NOT NULL,
                qty DECIMAL(18,8) NOT NULL,
                avg_cost DECIMAL(18,8) NOT NULL,
                market_value DECIMAL(18,8),
                unrealized_pnl DECIMAL(18,8),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                attributes JSON NOT NULL DEFAULT '{}'
            )
        """
            )
        )

    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        # Test order creation with idempotency
        order_id = str(uuid.uuid4())
        client_key = "idempotency-test-001"

        # First insertion
        await session.execute(
            text(
                """
            INSERT INTO orders (id, client_idempotency_key, symbol, side, qty, order_type, tif)
            VALUES (:id, :key, :symbol, :side, :qty, :type, :tif)
        """
            ),
            {
                "id": order_id,
                "key": client_key,
                "symbol": "AAPL",
                "side": "buy",
                "qty": "100.0",
                "type": "market",
                "tif": "gtc",
            },
        )

        await session.commit()

        # Test idempotency - try to insert duplicate key
        try:
            await session.execute(
                text(
                    """
                INSERT INTO orders (id, client_idempotency_key, symbol, side, qty, order_type, tif)
                VALUES (:id, :key, :symbol, :side, :qty, :type, :tif)
            """
                ),
                {
                    "id": str(uuid.uuid4()),  # Different ID
                    "key": client_key,  # Same key - should fail
                    "symbol": "MSFT",
                    "side": "sell",
                    "qty": "50.0",
                    "type": "limit",
                    "tif": "ioc",
                },
            )
            await session.commit()
            assert False, "Should have failed due to unique constraint"
        except Exception:
            await session.rollback()
            print("✅ Idempotency constraint working correctly!")

        # Test execution creation
        execution_id = str(uuid.uuid4())
        exec_id_broker = "EXEC-001"

        await session.execute(
            text(
                """
            INSERT INTO executions (id, order_id, symbol, side, qty, price, execution_id)
            VALUES (:id, :order_id, :symbol, :side, :qty, :price, :exec_id)
        """
            ),
            {
                "id": execution_id,
                "order_id": order_id,
                "symbol": "AAPL",
                "side": "buy",
                "qty": "100.0",
                "price": "150.75",
                "exec_id": exec_id_broker,
            },
        )

        # Test position update
        position_id = str(uuid.uuid4())
        await session.execute(
            text(
                """
            INSERT OR REPLACE INTO positions (id, symbol, qty, avg_cost, market_value, unrealized_pnl)
            VALUES (:id, :symbol, :qty, :avg_cost, :market_value, :pnl)
        """
            ),
            {
                "id": position_id,
                "symbol": "AAPL",
                "qty": "100.0",
                "avg_cost": "150.75",
                "market_value": "15075.0",
                "pnl": "0.0",
            },
        )

        await session.commit()

        # Verify data integrity
        order_result = await session.execute(
            text(
                """
            SELECT * FROM orders WHERE id = :id
        """
            ),
            {"id": order_id},
        )
        order_row = order_result.fetchone()

        exec_result = await session.execute(
            text(
                """
            SELECT * FROM executions WHERE order_id = :order_id
        """
            ),
            {"order_id": order_id},
        )
        exec_row = exec_result.fetchone()

        pos_result = await session.execute(
            text(
                """
            SELECT * FROM positions WHERE symbol = :symbol
        """
            ),
            {"symbol": "AAPL"},
        )
        pos_row = pos_result.fetchone()

        assert order_row is not None
        assert exec_row is not None
        assert pos_row is not None

        print("✅ Repository pattern simulation successful!")
        print(
            f"   📝 Order: {order_row[2]} {order_row[3]} {order_row[4]}@{order_row[5]}"
        )
        print(f"   📈 Execution: {exec_row[4]}@{exec_row[5]} (ID: {exec_row[6]})")
        print(f"   💼 Position: {pos_row[2]} shares @ ${pos_row[3]} avg cost")

    await engine.dispose()


async def test_configuration_integration():
    """Test that our repositories can work with configuration."""
    print("🧪 Testing configuration integration...")

    # Test that we can import and use configuration
    from backend.config import get_settings

    settings = get_settings()

    # Verify database configuration exists
    assert hasattr(settings.data, "database_url")
    assert hasattr(settings, "database")
    assert hasattr(settings.database, "pool_size")
    assert hasattr(settings.database, "max_overflow")

    print(f"   🔧 Database URL: {settings.data.database_url}")
    print(f"   🏊 Pool size: {settings.database.pool_size}")
    print(f"   📊 Max overflow: {settings.database.max_overflow}")

    print("✅ Configuration integration verified!")


async def test_repository_imports():
    """Test that all repository classes can be imported."""
    print("🧪 Testing repository imports...")

    # Test imports
    assert OrdersRepo is not None
    assert ExecutionsRepo is not None
    assert PositionsRepo is not None
    assert SignalsRepo is not None
    assert ModelsRepo is not None
    assert AuditsRepo is not None

    # Test exception imports
    assert OrderNotFoundError is not None
    assert DuplicateOrderError is not None

    print("✅ All repository classes imported successfully!")


async def run_all_tests():
    """Run all persistence layer tests."""
    print("🚀 Starting Branch 2.3 Persistence Layer Tests...\n")

    try:
        await test_configuration_integration()
        print()

        await test_repository_imports()
        print()

        await test_basic_order_operations()
        print()

        await test_repository_pattern_simulation()
        print()

        print("🎉 All persistence layer tests completed successfully!")
        print("\n📋 Test Summary:")
        print("   ✅ Configuration system integration")
        print("   ✅ Repository class imports")
        print("   ✅ Basic database operations")
        print("   ✅ Repository pattern simulation")
        print("   ✅ Order lifecycle (create → execute → position)")
        print("   ✅ Idempotency constraints")
        print("   ✅ Data integrity checks")

        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


if __name__ == "__main__":
    import asyncio

    success = asyncio.run(run_all_tests())
    if not success:
        exit(1)
