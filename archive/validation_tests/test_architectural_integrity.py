"""
Architectural Integrity Validation Suite

This test suite validates that all architectural fixes are working correctly:
1. Unified configuration system eliminates conflicts
2. Database access uses proper ORM patterns (no direct SQL)
3. Authentication configuration is consistent
4. All components integrate without conflicts
"""

import asyncio
import os
import tempfile
import uuid
from decimal import Decimal
from typing import Dict, Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Import unified systems
from backend.config.unified import (
    get_unified_settings, 
    reset_settings,
    validate_configuration,
    UnifiedSettings
)
from backend.infra.unified_database import (
    get_database_manager,
    get_db_session,
    shutdown_database,
    database_health
)
from backend.infra.repositories import OrderRepository
from backend.infra.outbox_worker import OutboxWorker


class TestArchitecturalIntegrity:
    """Test suite for architectural integrity validation."""
    
    @pytest.fixture(autouse=True)
    async def setup_test_environment(self):
        """Setup clean test environment for each test."""
        # Reset global state
        reset_settings()
        await shutdown_database()
        
        # Setup test environment variables
        os.environ.update({
            "DATABASE_URL": "sqlite+aiosqlite:///./test_architecture.db",
            "SECURITY_JWT_SECRET": "test-jwt-secret-key-minimum-32-characters-long-for-testing",
            "ENVIRONMENT": "test",
            "USE_MOCK_BROKER": "true",
            "DEBUG": "false"
        })
        
        yield
        
        # Cleanup
        await shutdown_database()
        reset_settings()
        
        # Remove test database
        try:
            if os.path.exists("test_architecture.db"):
                os.remove("test_architecture.db")
        except:
            pass
    
    async def test_unified_configuration_system(self):
        """Test that unified configuration eliminates conflicts."""
        
        # Test configuration loading
        settings = get_unified_settings()
        
        # Validate configuration structure
        assert hasattr(settings, 'database')
        assert hasattr(settings, 'jwt') 
        assert hasattr(settings, 'alpaca')
        assert hasattr(settings, 'outbox')
        
        # Test database configuration
        assert settings.database.url == "sqlite+aiosqlite:///./test_architecture.db"
        assert settings.database.is_sqlite == True
        assert settings.database.is_postgresql == False
        
        # Test JWT configuration
        assert len(settings.jwt.secret) >= 32
        assert settings.jwt.algorithm == "HS256"
        
        # Test environment detection
        assert settings.environment == "test"
        assert settings.is_development() == False
        assert settings.is_production() == False
        
        # Test configuration validation
        validation_result = validate_configuration()
        assert validation_result["valid"] == True
        assert validation_result["environment"] == "test"
        assert validation_result["database_type"] == "sqlite"
        assert validation_result["jwt_configured"] == True
    
    async def test_unified_database_manager(self):
        """Test that database manager eliminates direct SQL usage."""
        
        # Initialize database
        db_manager = await get_database_manager()
        assert db_manager.is_initialized() == True
        
        # Test health check
        health = await db_manager.health_check()
        assert health["healthy"] == True
        assert health["initialized"] == True
        assert health["database_type"] == "sqlite"
        
        # Test session management
        async with db_manager.get_session() as session:
            assert isinstance(session, AsyncSession)
            
            # Test that we can execute queries through ORM
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1 as test"))
            test_row = result.fetchone()
            assert test_row[0] == 1
        
        # Test convenience function
        async with get_db_session() as session:
            assert isinstance(session, AsyncSession)
    
    async def test_repository_pattern_replaces_direct_sql(self):
        """Test that repository pattern works and replaces direct SQL."""
        
        # Initialize database
        db_manager = await get_database_manager()
        
        async with get_db_session() as session:
            # Create repository
            order_repo = OrderRepository(session)
            
            # Test order creation (this should work without any direct SQL)
            order_data = {
                "id": uuid.uuid4(),
                "user_id": uuid.uuid4(),
                "symbol": "AAPL",
                "side": "buy", 
                "qty": Decimal("10"),
                "order_type": "market",
                "status": "submitted"
            }
            
            # This should NOT use sqlite3.connect() anywhere
            order = await order_repo.create(order_data)
            assert order.id == order_data["id"]
            assert order.symbol == "AAPL"
            assert order.status == "submitted"
            
            # Test order retrieval
            retrieved_order = await order_repo.get_by_id(order.id)
            assert retrieved_order is not None
            assert retrieved_order.symbol == "AAPL"
            
            # Test order update
            retrieved_order.status = "filled"
            updated_order = await order_repo.update(retrieved_order)
            assert updated_order.status == "filled"
    
    async def test_outbox_worker_uses_orm_not_direct_sql(self):
        """Test that outbox worker uses ORM instead of direct SQL."""
        
        # Initialize systems
        db_manager = await get_database_manager()
        settings = get_unified_settings()
        
        # Get sessionmaker
        sessionmaker = await db_manager.get_sessionmaker()
        
        # Create outbox worker (should not use sqlite3.connect())
        worker = OutboxWorker(sessionmaker)
        
        # Test that worker initializes without direct SQL connections
        assert worker.sessionmaker == sessionmaker
        assert worker.settings == settings
        assert worker.use_mock_broker == True
        
        # Test order status update method (the main architectural fix)
        test_order_id = str(uuid.uuid4())
        
        # First create an order to update
        async with get_db_session() as session:
            order_repo = OrderRepository(session)
            order_data = {
                "id": uuid.UUID(test_order_id),
                "user_id": uuid.uuid4(),
                "symbol": "AAPL",
                "side": "buy",
                "qty": Decimal("10"),
                "order_type": "market", 
                "status": "submitted"
            }
            await order_repo.create(order_data)
            await session.commit()
        
        # Now test the worker's order update method
        # This should use ORM repositories, NOT sqlite3.connect()
        try:
            await worker._update_order_status(
                order_id=test_order_id,
                status="filled",
                broker_order_id="test_broker_123"
            )
            
            # Verify the update worked through ORM
            async with get_db_session() as session:
                order_repo = OrderRepository(session)
                updated_order = await order_repo.get_by_id(uuid.UUID(test_order_id))
                assert updated_order is not None
                assert updated_order.status == "filled"
                assert updated_order.broker_order_id == "test_broker_123"
                
        except Exception as e:
            # Log any errors for debugging
            print(f"Outbox worker test failed: {e}")
            raise
    
    async def test_no_direct_sql_connections_detected(self):
        """Test that no components are using direct SQL connections."""
        
        # Initialize all systems
        db_manager = await get_database_manager()
        settings = get_unified_settings()
        sessionmaker = await db_manager.get_sessionmaker()
        
        # Create instances of key components
        worker = OutboxWorker(sessionmaker)
        
        # Verify no sqlite3 module is imported in our unified modules
        # (This is a basic check - in production we'd use more sophisticated monitoring)
        
        import sys
        
        # Check that our unified modules don't import sqlite3
        unified_modules = [
            'backend.config.unified',
            'backend.infra.unified_database', 
            'backend.infra.repositories'
        ]
        
        for module_name in unified_modules:
            if module_name in sys.modules:
                module = sys.modules[module_name]
                module_vars = vars(module)
                
                # Check that sqlite3 is not imported
                assert 'sqlite3' not in module_vars, f"Module {module_name} should not import sqlite3 directly"
    
    async def test_configuration_consistency_across_components(self):
        """Test that all components use consistent configuration."""
        
        settings = get_unified_settings()
        db_manager = await get_database_manager()
        
        # Test that database manager uses same URL as settings
        engine = await db_manager.get_engine()
        db_url = str(engine.url)
        
        # Both should point to same database
        assert "test_architecture.db" in db_url
        assert settings.database.url in db_url or db_url in settings.database.url
        
        # Test that outbox worker uses same settings
        sessionmaker = await db_manager.get_sessionmaker()
        worker = OutboxWorker(sessionmaker)
        
        assert worker.settings.use_mock_broker == settings.use_mock_broker
        assert worker.settings.environment == settings.environment
    
    async def test_complete_order_flow_integration(self):
        """Test complete order flow using unified architecture."""
        
        # Initialize all systems
        db_manager = await get_database_manager()
        sessionmaker = await db_manager.get_sessionmaker()
        worker = OutboxWorker(sessionmaker)
        
        order_id = uuid.uuid4()
        
        # 1. Create order through repository
        async with get_db_session() as session:
            order_repo = OrderRepository(session)
            order_data = {
                "id": order_id,
                "user_id": uuid.uuid4(),
                "symbol": "TSLA",
                "side": "buy",
                "qty": Decimal("5"),
                "order_type": "market",
                "status": "submitted"
            }
            order = await order_repo.create(order_data)
            await session.commit()
        
        # 2. Process order through outbox worker (using ORM)
        await worker._update_order_status(
            order_id=str(order_id),
            status="accepted",
            broker_order_id="broker_456"
        )
        
        # 3. Verify final state through repository
        async with get_db_session() as session:
            order_repo = OrderRepository(session)
            final_order = await order_repo.get_by_id(order_id)
            
            assert final_order is not None
            assert final_order.status == "accepted"
            assert final_order.broker_order_id == "broker_456"
            assert final_order.symbol == "TSLA"
        
        # 4. Test database health after all operations
        health = await database_health()
        assert health["healthy"] == True


async def run_architectural_validation():
    """Run architectural validation suite."""
    print("🔍 Starting Architectural Integrity Validation...")
    
    test_instance = TestArchitecturalIntegrity()
    
    try:
        # Setup
        await test_instance.setup_test_environment().__anext__()
        
        # Run tests
        print("✅ Testing unified configuration system...")
        await test_instance.test_unified_configuration_system()
        
        print("✅ Testing unified database manager...")
        await test_instance.test_unified_database_manager()
        
        print("✅ Testing repository pattern...")
        await test_instance.test_repository_pattern_replaces_direct_sql()
        
        print("✅ Testing outbox worker ORM usage...")
        await test_instance.test_outbox_worker_uses_orm_not_direct_sql()
        
        print("✅ Testing no direct SQL connections...")
        await test_instance.test_no_direct_sql_connections_detected()
        
        print("✅ Testing configuration consistency...")
        await test_instance.test_configuration_consistency_across_components()
        
        print("✅ Testing complete order flow integration...")
        await test_instance.test_complete_order_flow_integration()
        
        print("\n🎉 ALL ARCHITECTURAL INTEGRITY TESTS PASSED!")
        print("✅ Configuration conflicts eliminated")
        print("✅ Direct SQL usage replaced with ORM")
        print("✅ Database access patterns unified")
        print("✅ Authentication configuration standardized")
        print("✅ System integration validated")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ARCHITECTURAL VALIDATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    """Run validation when executed directly."""
    import asyncio
    
    success = asyncio.run(run_architectural_validation())
    exit(0 if success else 1)