"""
Tests for the persistence layer repositories.
Tests all CRUD operations, idempotency, and error handling.
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.infra.schemas import Base, Order, Execution, Position, Signal, ModelRegistry, AuditLog
from backend.infra.repositories import (
    OrdersRepo, ExecutionsRepo, PositionsRepo, SignalsRepo, 
    ModelsRepo, AuditsRepo,
    OrderNotFoundError, DuplicateOrderError,
    ExecutionNotFoundError, DuplicateExecutionError,
    PositionNotFoundError, DuplicatePositionError,
    ModelNotFoundError, DuplicateModelError,
    SignalNotFoundError, DuplicateSignalError,
    AuditNotFoundError
)


# Test database URL (in-memory SQLite for fast testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def async_engine():
    """Create test async engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()


@pytest.fixture
async def async_session(async_engine):
    """Create test async session."""
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session


@pytest.fixture
def orders_repo(async_session):
    """Create OrdersRepo instance."""
    return OrdersRepo(async_session)


@pytest.fixture 
def executions_repo(async_session):
    """Create ExecutionsRepo instance."""
    return ExecutionsRepo(async_session)


@pytest.fixture
def positions_repo(async_session):
    """Create PositionsRepo instance.""" 
    return PositionsRepo(async_session)


@pytest.fixture
def signals_repo(async_session):
    """Create SignalsRepo instance."""
    return SignalsRepo(async_session)


@pytest.fixture
def models_repo(async_session):
    """Create ModelsRepo instance."""
    return ModelsRepo(async_session)


@pytest.fixture
def audits_repo(async_session):
    """Create AuditsRepo instance."""
    return AuditsRepo(async_session)


class TestOrdersRepo:
    """Test OrdersRepo functionality."""
    
    async def test_upsert_by_idempotency_creates_new_order(self, orders_repo, async_session):
        """Test creating a new order with idempotency key."""
        client_key = "test-order-001"
        
        order = await orders_repo.upsert_by_idempotency(
            client_key=client_key,
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="market",
            tif="gtc"
        )
        
        assert order.client_idempotency_key == client_key
        assert order.symbol == "AAPL"
        assert order.side == "buy"
        assert order.qty == Decimal("100")
        assert order.status == "accepted"
        assert order.id is not None
    
    async def test_upsert_by_idempotency_returns_existing_order(self, orders_repo, async_session):
        """Test idempotency - returns existing order for same key."""
        client_key = "test-order-002"
        
        # Create first order
        order1 = await orders_repo.upsert_by_idempotency(
            client_key=client_key,
            symbol="AAPL", 
            side="buy",
            qty=Decimal("100"),
            order_type="market",
            tif="gtc"
        )
        
        await async_session.commit()
        
        # Try to create second order with same key
        order2 = await orders_repo.upsert_by_idempotency(
            client_key=client_key,
            symbol="TSLA",  # Different symbol
            side="sell",    # Different side
            qty=Decimal("50"), # Different qty
            order_type="limit",
            tif="ioc"
        )
        
        # Should return the original order, not create new one
        assert order1.id == order2.id
        assert order2.symbol == "AAPL"  # Original values
        assert order2.side == "buy"
        assert order2.qty == Decimal("100")
    
    async def test_set_status(self, orders_repo, async_session):
        """Test updating order status."""
        # Create order
        order = await orders_repo.upsert_by_idempotency(
            client_key="test-order-003",
            symbol="MSFT",
            side="buy",
            qty=Decimal("200"),
            order_type="limit",
            tif="gtc"
        )
        await async_session.commit()
        
        # Update status
        await orders_repo.set_status(order.id, "filled")
        await async_session.commit()
        
        # Verify update
        updated_order = await orders_repo.get_by_id(order.id)
        assert updated_order.status == "filled"
        assert updated_order.updated_at is not None
    
    async def test_set_status_not_found(self, orders_repo):
        """Test setting status for non-existent order."""
        fake_id = uuid.uuid4()
        
        with pytest.raises(OrderNotFoundError):
            await orders_repo.set_status(fake_id, "cancelled")
    
    async def test_attach_broker_result(self, orders_repo, async_session):
        """Test attaching broker response to order."""
        # Create order
        order = await orders_repo.upsert_by_idempotency(
            client_key="test-order-004",
            symbol="GOOGL",
            side="sell",
            qty=Decimal("50"),
            order_type="market",
            tif="gtc"
        )
        await async_session.commit()
        
        # Attach broker result
        await orders_repo.attach_broker_result(
            order.id,
            broker_order_id="BROKER-123456",
            status="submitted",
            attributes={"exchange": "NASDAQ", "commission": "1.00"}
        )
        await async_session.commit()
        
        # Verify update
        updated_order = await orders_repo.get_by_id(order.id)
        assert updated_order.broker_order_id == "BROKER-123456"
        assert updated_order.status == "submitted"
        assert updated_order.attributes["exchange"] == "NASDAQ"
        assert updated_order.attributes["commission"] == "1.00"
    
    async def test_get_active_orders(self, orders_repo, async_session):
        """Test getting active orders."""
        # Create orders with different statuses
        await orders_repo.upsert_by_idempotency(
            client_key="active-1", symbol="AAPL", side="buy", 
            qty=Decimal("100"), order_type="market", tif="gtc"
        )
        
        order2 = await orders_repo.upsert_by_idempotency(
            client_key="active-2", symbol="MSFT", side="sell",
            qty=Decimal("200"), order_type="limit", tif="gtc"
        )
        
        order3 = await orders_repo.upsert_by_idempotency(
            client_key="filled-1", symbol="TSLA", side="buy",
            qty=Decimal("50"), order_type="market", tif="ioc"
        )
        
        # Update one to filled status
        await orders_repo.set_status(order3.id, "filled")
        await async_session.commit()
        
        # Get active orders
        active_orders = await orders_repo.get_active_orders()
        
        # Should return 2 active orders (status='accepted')
        assert len(active_orders) == 2
        active_symbols = [o.symbol for o in active_orders]
        assert "AAPL" in active_symbols
        assert "MSFT" in active_symbols
        assert "TSLA" not in active_symbols  # This one is filled


class TestExecutionsRepo:
    """Test ExecutionsRepo functionality."""
    
    async def test_create_execution(self, executions_repo, async_session):
        """Test creating a new execution."""
        order_id = uuid.uuid4()
        
        execution = await executions_repo.create_execution(
            order_id=order_id,
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            price=Decimal("150.50"),
            execution_id="EXEC-001"
        )
        
        assert execution.order_id == order_id
        assert execution.symbol == "AAPL"
        assert execution.side == "buy"
        assert execution.qty == Decimal("100")
        assert execution.price == Decimal("150.50")
        assert execution.execution_id == "EXEC-001"
        assert execution.id is not None
    
    async def test_upsert_by_execution_id_creates_new(self, executions_repo, async_session):
        """Test creating execution with upsert."""
        order_id = uuid.uuid4()
        
        execution = await executions_repo.upsert_by_execution_id(
            order_id=order_id,
            symbol="MSFT",
            side="sell", 
            qty=Decimal("50"),
            price=Decimal("300.25"),
            execution_id="EXEC-002"
        )
        
        assert execution.symbol == "MSFT"
        assert execution.execution_id == "EXEC-002"
    
    async def test_upsert_by_execution_id_returns_existing(self, executions_repo, async_session):
        """Test upsert returns existing execution."""
        order_id = uuid.uuid4()
        
        # Create first execution
        exec1 = await executions_repo.upsert_by_execution_id(
            order_id=order_id,
            symbol="GOOGL",
            side="buy",
            qty=Decimal("25"),
            price=Decimal("2500.00"),
            execution_id="EXEC-003"
        )
        await async_session.commit()
        
        # Try to create with same execution_id
        exec2 = await executions_repo.upsert_by_execution_id(
            order_id=uuid.uuid4(),  # Different order ID
            symbol="TSLA",          # Different symbol
            side="sell",            # Different side
            qty=Decimal("100"),     # Different qty
            price=Decimal("250.00"), # Different price
            execution_id="EXEC-003" # Same execution ID
        )
        
        # Should return original execution
        assert exec1.id == exec2.id
        assert exec2.symbol == "GOOGL"  # Original values
        assert exec2.side == "buy"
        assert exec2.qty == Decimal("25")
        assert exec2.price == Decimal("2500.00")
    
    async def test_get_total_filled_qty(self, executions_repo, async_session):
        """Test calculating total filled quantity."""
        order_id = uuid.uuid4()
        
        # Create multiple executions for same order
        await executions_repo.create_execution(
            order_id=order_id, symbol="AAPL", side="buy",
            qty=Decimal("50"), price=Decimal("150.00"), execution_id="EXEC-A1"
        )
        await executions_repo.create_execution(
            order_id=order_id, symbol="AAPL", side="buy", 
            qty=Decimal("25"), price=Decimal("151.00"), execution_id="EXEC-A2"
        )
        await executions_repo.create_execution(
            order_id=order_id, symbol="AAPL", side="buy",
            qty=Decimal("25"), price=Decimal("150.50"), execution_id="EXEC-A3"
        )
        await async_session.commit()
        
        total_qty = await executions_repo.get_total_filled_qty(order_id)
        assert total_qty == Decimal("100")  # 50 + 25 + 25
    
    async def test_get_volume_weighted_avg_price(self, executions_repo, async_session):
        """Test calculating VWAP."""
        order_id = uuid.uuid4()
        
        # Create executions: 50@150 + 50@151 should give VWAP of 150.50
        await executions_repo.create_execution(
            order_id=order_id, symbol="AAPL", side="buy",
            qty=Decimal("50"), price=Decimal("150.00"), execution_id="VWAP-1"
        )
        await executions_repo.create_execution(
            order_id=order_id, symbol="AAPL", side="buy",
            qty=Decimal("50"), price=Decimal("151.00"), execution_id="VWAP-2"
        )
        await async_session.commit()
        
        vwap = await executions_repo.get_volume_weighted_avg_price(order_id)
        expected_vwap = (Decimal("50") * Decimal("150.00") + Decimal("50") * Decimal("151.00")) / Decimal("100")
        assert vwap == expected_vwap  # Should be 150.50


class TestPositionsRepo:
    """Test PositionsRepo functionality."""
    
    async def test_upsert_position_creates_new(self, positions_repo, async_session):
        """Test creating new position."""
        position = await positions_repo.upsert_position(
            symbol="AAPL",
            qty=Decimal("100"), 
            avg_cost=Decimal("150.00"),
            market_value=Decimal("15100.00"),
            unrealized_pnl=Decimal("100.00")
        )
        
        assert position.symbol == "AAPL"
        assert position.qty == Decimal("100")
        assert position.avg_cost == Decimal("150.00")
        assert position.market_value == Decimal("15100.00")
        assert position.unrealized_pnl == Decimal("100.00")
    
    async def test_upsert_position_updates_existing(self, positions_repo, async_session):
        """Test updating existing position."""
        # Create initial position
        await positions_repo.upsert_position(
            symbol="MSFT", qty=Decimal("50"), avg_cost=Decimal("300.00")
        )
        await async_session.commit()
        
        # Update position
        updated_position = await positions_repo.upsert_position(
            symbol="MSFT", qty=Decimal("75"), avg_cost=Decimal("305.00"),
            market_value=Decimal("23000.00"), unrealized_pnl=Decimal("375.00")
        )
        
        assert updated_position.qty == Decimal("75")
        assert updated_position.avg_cost == Decimal("305.00")
        assert updated_position.market_value == Decimal("23000.00")
    
    async def test_get_portfolio_summary(self, positions_repo, async_session):
        """Test portfolio summary calculation."""
        # Create multiple positions
        await positions_repo.upsert_position(
            symbol="AAPL", qty=Decimal("100"), avg_cost=Decimal("150.00"),
            market_value=Decimal("15100.00"), unrealized_pnl=Decimal("100.00")
        )
        await positions_repo.upsert_position(
            symbol="MSFT", qty=Decimal("-50"), avg_cost=Decimal("300.00"),
            market_value=Decimal("-15200.00"), unrealized_pnl=Decimal("200.00")
        )
        await positions_repo.upsert_position(
            symbol="GOOGL", qty=Decimal("10"), avg_cost=Decimal("2500.00"),
            market_value=Decimal("25100.00"), unrealized_pnl=Decimal("100.00")
        )
        await async_session.commit()
        
        summary = await positions_repo.get_portfolio_summary()
        
        assert summary["total_positions"] == 3
        assert summary["long_positions"] == 2  # AAPL, GOOGL
        assert summary["short_positions"] == 1  # MSFT
        assert summary["total_market_value"] == Decimal("25000.00")  # 15100 + (-15200) + 25100
        assert summary["total_unrealized_pnl"] == Decimal("400.00")  # 100 + 200 + 100
        assert "AAPL" in summary["symbols"]
        assert "MSFT" in summary["symbols"]
        assert "GOOGL" in summary["symbols"]


class TestSignalsRepo:
    """Test SignalsRepo functionality."""
    
    async def test_create_signal(self, signals_repo, async_session):
        """Test creating a trading signal."""
        signal = await signals_repo.create_signal(
            symbol="AAPL",
            model_name="momentum_v1",
            signal_type="buy",
            direction="long",
            strength=Decimal("0.85"),
            confidence=Decimal("0.92"),
            target_price=Decimal("155.00"),
            stop_loss=Decimal("145.00")
        )
        
        assert signal.symbol == "AAPL"
        assert signal.model_name == "momentum_v1"
        assert signal.signal_type == "buy"
        assert signal.direction == "long"
        assert signal.strength == Decimal("0.85")
        assert signal.confidence == Decimal("0.92")
        assert signal.target_price == Decimal("155.00")
        assert signal.stop_loss == Decimal("145.00")
    
    async def test_get_active_signals(self, signals_repo, async_session):
        """Test getting active signals."""
        # Create signals with different expiry
        await signals_repo.create_signal(
            symbol="AAPL", model_name="model1", signal_type="buy",
            direction="long", strength=Decimal("0.8"), confidence=Decimal("0.9")
        )
        
        # Create expired signal
        expired_time = datetime.utcnow() - timedelta(hours=1)
        await signals_repo.create_signal(
            symbol="MSFT", model_name="model1", signal_type="sell",
            direction="short", strength=Decimal("0.7"), confidence=Decimal("0.8"),
            expiry=expired_time
        )
        
        # Create active signal with future expiry
        future_time = datetime.utcnow() + timedelta(hours=2)
        await signals_repo.create_signal(
            symbol="GOOGL", model_name="model2", signal_type="buy",
            direction="long", strength=Decimal("0.9"), confidence=Decimal("0.95"),
            expiry=future_time
        )
        await async_session.commit()
        
        active_signals = await signals_repo.get_active_signals()
        
        # Should return 2 active signals (AAPL with no expiry, GOOGL with future expiry)
        assert len(active_signals) == 2
        symbols = [s.symbol for s in active_signals]
        assert "AAPL" in symbols
        assert "GOOGL" in symbols
        assert "MSFT" not in symbols  # This one is expired
    
    async def test_get_high_confidence_signals(self, signals_repo, async_session):
        """Test getting high-confidence signals."""
        # Create signals with different confidence/strength
        await signals_repo.create_signal(
            symbol="HIGH1", model_name="model1", signal_type="buy", 
            direction="long", strength=Decimal("0.9"), confidence=Decimal("0.95")  # High
        )
        await signals_repo.create_signal(
            symbol="LOW1", model_name="model1", signal_type="sell",
            direction="short", strength=Decimal("0.5"), confidence=Decimal("0.6")  # Low
        )
        await signals_repo.create_signal(
            symbol="HIGH2", model_name="model2", signal_type="buy",
            direction="long", strength=Decimal("0.85"), confidence=Decimal("0.9")  # High
        )
        await async_session.commit()
        
        high_signals = await signals_repo.get_high_confidence_signals(
            min_confidence=Decimal("0.8"), min_strength=Decimal("0.7")
        )
        
        # Should return 2 high-confidence signals
        assert len(high_signals) == 2
        symbols = [s.symbol for s in high_signals]
        assert "HIGH1" in symbols
        assert "HIGH2" in symbols
        assert "LOW1" not in symbols


class TestModelsRepo:
    """Test ModelsRepo functionality."""
    
    async def test_register_model(self, models_repo, async_session):
        """Test registering a new model."""
        model = await models_repo.register_model(
            name="sentiment_analyzer",
            version="1.0.0",
            model_type="classification",
            status="training",
            metadata={"author": "data_team", "framework": "sklearn"},
            performance_metrics={"accuracy": 0.89, "precision": 0.91}
        )
        
        assert model.name == "sentiment_analyzer"
        assert model.version == "1.0.0"
        assert model.model_type == "classification"
        assert model.status == "training"
        assert model.metadata["author"] == "data_team"
        assert model.performance_metrics["accuracy"] == 0.89
    
    async def test_register_duplicate_model(self, models_repo, async_session):
        """Test registering duplicate model raises error."""
        # Register first model
        await models_repo.register_model(
            name="test_model", version="1.0.0", model_type="regression"
        )
        await async_session.commit()
        
        # Try to register duplicate
        with pytest.raises(DuplicateModelError):
            await models_repo.register_model(
                name="test_model", version="1.0.0", model_type="classification"
            )
    
    async def test_promote_model_to_production(self, models_repo, async_session):
        """Test promoting model to production."""
        # Register multiple versions
        await models_repo.register_model(
            name="trading_model", version="1.0.0", model_type="ensemble", status="production"
        )
        await models_repo.register_model(
            name="trading_model", version="2.0.0", model_type="ensemble", status="testing"
        )
        await async_session.commit()
        
        # Promote v2.0.0 to production
        await models_repo.promote_model_to_production("trading_model", "2.0.0")
        await async_session.commit()
        
        # Check statuses
        v1_model = await models_repo.get_model_by_name_version("trading_model", "1.0.0")
        v2_model = await models_repo.get_model_by_name_version("trading_model", "2.0.0")
        
        assert v1_model.status == "archived"  # Demoted
        assert v2_model.status == "production"  # Promoted


class TestAuditsRepo:
    """Test AuditsRepo functionality."""
    
    async def test_create_audit_log(self, audits_repo, async_session):
        """Test creating audit log entry."""
        audit = await audits_repo.create_audit_log(
            action="CREATE_ORDER",
            entity_type="order",
            entity_id="123e4567-e89b-12d3-a456-426614174000",
            user_id="user123",
            ip_address="192.168.1.100",
            details={"symbol": "AAPL", "qty": 100}
        )
        
        assert audit.action == "CREATE_ORDER"
        assert audit.entity_type == "order"
        assert audit.user_id == "user123"
        assert audit.ip_address == "192.168.1.100"
        assert audit.details["symbol"] == "AAPL"
        assert audit.details["qty"] == 100
    
    async def test_log_order_action(self, audits_repo, async_session):
        """Test logging order-specific action."""
        order_id = uuid.uuid4()
        
        audit = await audits_repo.log_order_action(
            action="ORDER_FILLED",
            order_id=order_id,
            user_id="trader1",
            details={"fill_price": "150.25", "fill_qty": 50}
        )
        
        assert audit.action == "ORDER_FILLED"
        assert audit.entity_type == "order"
        assert audit.entity_id == str(order_id)
        assert audit.user_id == "trader1"
    
    async def test_get_audit_summary(self, audits_repo, async_session):
        """Test getting audit summary statistics."""
        # Create multiple audit logs
        await audits_repo.create_audit_log(
            action="LOGIN", entity_type="user", entity_id="user1", user_id="user1"
        )
        await audits_repo.create_audit_log(
            action="CREATE_ORDER", entity_type="order", entity_id="order1", user_id="user1"
        )
        await audits_repo.create_audit_log(
            action="LOGIN", entity_type="user", entity_id="user2", user_id="user2"
        )
        await async_session.commit()
        
        summary = await audits_repo.get_audit_summary()
        
        assert summary["total_logs"] == 3
        assert summary["action_counts"]["LOGIN"] == 2
        assert summary["action_counts"]["CREATE_ORDER"] == 1
        assert summary["entity_type_counts"]["user"] == 2
        assert summary["entity_type_counts"]["order"] == 1
        assert summary["user_counts"]["user1"] == 2
        assert summary["user_counts"]["user2"] == 1


@pytest.mark.asyncio
async def test_end_to_end_order_flow():
    """Test complete order flow: order -> execution -> position -> audit."""
    # Create test database
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        # Initialize repositories
        orders_repo = OrdersRepo(session)
        executions_repo = ExecutionsRepo(session)
        positions_repo = PositionsRepo(session)
        audits_repo = AuditsRepo(session)
        
        try:
            # 1. Create order
            order = await orders_repo.upsert_by_idempotency(
                client_key="e2e-test-001",
                symbol="AAPL",
                side="buy",
                qty=Decimal("100"),
                order_type="market",
                tif="gtc"
            )
            
            # 2. Log order creation
            await audits_repo.log_order_action(
                action="ORDER_CREATED",
                order_id=order.id,
                user_id="test_user",
                details={"symbol": "AAPL", "side": "buy", "qty": "100"}
            )
            
            # 3. Create execution
            execution = await executions_repo.upsert_by_execution_id(
                order_id=order.id,
                symbol="AAPL", 
                side="buy",
                qty=Decimal("100"),
                price=Decimal("150.75"),
                execution_id="E2E-EXEC-001"
            )
            
            # 4. Update order status
            await orders_repo.set_status(order.id, "filled")
            
            # 5. Update position
            position = await positions_repo.upsert_position(
                symbol="AAPL",
                qty=Decimal("100"),
                avg_cost=Decimal("150.75"),
                market_value=Decimal("15075.00")
            )
            
            # 6. Log position update
            await audits_repo.log_position_action(
                action="POSITION_UPDATED",
                position_id=position.id,
                user_id="test_user",
                details={"new_qty": "100", "avg_cost": "150.75"}
            )
            
            await session.commit()
            
            # Verify the complete flow
            final_order = await orders_repo.get_by_id(order.id)
            final_execution = await executions_repo.get_by_execution_id("E2E-EXEC-001")
            final_position = await positions_repo.get_by_symbol("AAPL")
            audit_logs = await audits_repo.get_logs_by_entity("order", str(order.id))
            
            assert final_order.status == "filled"
            assert final_execution.qty == Decimal("100")
            assert final_position.qty == Decimal("100")
            assert len(audit_logs) >= 1
            
            print("✅ End-to-end order flow test completed successfully!")
            
        except Exception as e:
            await session.rollback()
            raise
    
    await engine.dispose()


if __name__ == "__main__":
    import asyncio
    
    print("🧪 Running Branch 2.3 Persistence Layer Tests...")
    asyncio.run(test_end_to_end_order_flow())
    print("🎉 All tests completed!")
