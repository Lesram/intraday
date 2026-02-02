"""
AUTOMATED TEST SUITE - Strategies Feature
==========================================
Comprehensive automated tests covering Phases 1-3 before manual testing.

Run with: pytest test_strategies_automated_suite.py -v

This test suite covers:
- Phase 1: Database layer (schema, constraints, data)
- Phase 2: Service layer (CRUD operations, business logic)  
- Phase 3: API layer (REST endpoints - if auth works)

NOTE: These tests require PostgreSQL database with strategies table.
The test SQLite database does not have the required tables or support
the PostgreSQL-specific information_schema queries used here.
"""

import asyncio
import os
import uuid
from datetime import datetime
from typing import Any, Dict

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Load environment variables from .env if python-dotenv is installed.
try:
    from dotenv import load_dotenv  # type: ignore[import-not-found]

    load_dotenv()
except Exception:
    pass

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")

# Skip all tests if DATABASE_URL is not a PostgreSQL connection
# (these tests use PostgreSQL-specific information_schema queries)
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or "postgresql" not in DATABASE_URL.lower(),
    reason="Strategies automated tests require PostgreSQL database with strategies table. "
           "Set DATABASE_URL to a PostgreSQL connection string to run these tests."
)

# Only create engine if we have a valid DATABASE_URL
if DATABASE_URL:
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
else:
    engine = None
    AsyncSessionLocal = None


# ============================================================================
# PHASE 1: DATABASE LAYER TESTS
# ============================================================================

class TestPhase1Database:
    """Test database schema, constraints, and structure."""

    @pytest.mark.asyncio
    async def test_01_strategies_table_exists(self):
        """Test 1.1: Verify strategies table exists."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'strategies'
                    );
                """)
            )
            exists = result.scalar()
            assert exists, "strategies table does not exist"
            print("✅ strategies table exists")

    @pytest.mark.asyncio
    async def test_02_table_structure(self):
        """Test 1.2: Verify strategies table has correct columns."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'strategies'
                    ORDER BY ordinal_position;
                """)
            )
            columns = result.fetchall()
            
            # Expected columns
            expected_columns = {
                'id', 'name', 'description', 'strategy_type', 'status',
                'symbols', 'parameters', 'model_id', 'total_trades',
                'winning_trades', 'losing_trades', 'total_pnl', 'sharpe_ratio',
                'max_drawdown', 'win_rate', 'avg_trade_pnl', 'execution_count',
                'last_executed_at', 'last_error', 'error_count',
                'created_at', 'updated_at', 'created_by', 'updated_by'
            }
            
            actual_columns = {col[0] for col in columns}
            missing = expected_columns - actual_columns
            extra = actual_columns - expected_columns
            
            assert len(missing) == 0, f"Missing columns: {missing}"
            print(f"✅ Found {len(columns)} columns")
            print(f"   Column count: {len(actual_columns)}")
            
            # Verify JSON columns
            json_columns = [col for col in columns if col[1] in ('jsonb', 'json')]
            assert len(json_columns) >= 2, "Missing JSONB columns (symbols, parameters)"
            print(f"✅ JSONB columns present: {len(json_columns)}")

    @pytest.mark.asyncio
    async def test_03_indexes(self):
        """Test 1.3: Verify indexes exist."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = 'strategies'
                    AND schemaname = 'public';
                """)
            )
            indexes = result.fetchall()
            
            assert len(indexes) > 0, "No indexes found on strategies table"
            
            # Check for important indexes
            index_names = [idx[0] for idx in indexes]
            print(f"✅ Found {len(indexes)} indexes:")
            for idx_name in index_names:
                print(f"   - {idx_name}")
            
            # Should have at least primary key + status index
            assert any('pkey' in idx or 'pk' in idx.lower() for idx in index_names), \
                "Primary key index missing"

    @pytest.mark.asyncio
    async def test_04_foreign_keys(self):
        """Test 1.4: Verify foreign key constraints."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT
                        tc.constraint_name,
                        tc.table_name,
                        kcu.column_name,
                        ccu.table_name AS foreign_table_name,
                        ccu.column_name AS foreign_column_name
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                        AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                        AND tc.table_name = 'strategies';
                """)
            )
            fks = result.fetchall()
            
            print(f"✅ Found {len(fks)} foreign key(s)")
            for fk in fks:
                print(f"   - {fk[2]} → {fk[3]}.{fk[4]}")

    @pytest.mark.asyncio
    async def test_05_test_data_exists(self):
        """Test 1.5: Verify test data exists in database."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM strategies;")
            )
            count = result.scalar()
            
            assert count > 0, "No strategies found in database"
            print(f"✅ Found {count} strategies in database")


# ============================================================================
# PHASE 2: SERVICE LAYER TESTS
# ============================================================================

class TestPhase2ServiceLayer:
    """Test service and repository layer operations."""

    @pytest.mark.asyncio
    async def test_01_repository_get_all(self):
        """Test 2.1: StrategyRepo.get_all() returns strategies."""
        from backend.services.strategy_service import StrategyRepo
        
        async with AsyncSessionLocal() as session:
            repo = StrategyRepo(session)
            strategies = await repo.get_all()
            
            assert len(strategies) > 0, "get_all() returned no strategies"
            assert hasattr(strategies[0], 'id'), "Strategy missing 'id' field"
            assert hasattr(strategies[0], 'name'), "Strategy missing 'name' field"
            assert hasattr(strategies[0], 'status'), "Strategy missing 'status' field"
            
            print(f"✅ get_all() returned {len(strategies)} strategies")
            print(f"   First strategy: {strategies[0].name}")

    @pytest.mark.asyncio
    async def test_02_repository_get_by_id(self):
        """Test 2.2: StrategyRepo.get_by_id() retrieves specific strategy."""
        from backend.services.strategy_service import StrategyRepo
        
        async with AsyncSessionLocal() as session:
            repo = StrategyRepo(session)
            
            # Get first strategy
            all_strategies = await repo.get_all()
            assert len(all_strategies) > 0, "No strategies to test with"
            
            strategy_id = all_strategies[0].id
            strategy = await repo.get_by_id(strategy_id)
            
            assert strategy is not None, f"get_by_id({strategy_id}) returned None"
            assert strategy.id == strategy_id, "Returned wrong strategy"
            assert strategy.name, "Strategy name is empty"
            
            print(f"✅ get_by_id() retrieved: {strategy.name}")
            print(f"   Status: {strategy.status}")
            print(f"   Type: {strategy.strategy_type}")

    @pytest.mark.asyncio
    async def test_03_service_create(self):
        """Test 2.3: StrategyService.create_strategy() creates new strategy."""
        from backend.services.strategy_service import StrategyService
        
        async with AsyncSessionLocal() as session:
            service = StrategyService(session)
            
            # Create unique test strategy
            unique_id = uuid.uuid4().hex[:8]
            test_data = {
                "name": f"Automated Test Strategy {unique_id}",
                "description": "Created by automated test suite",
                "strategy_type": "technical",
                "symbols": ["TEST", "AUTO"],
                "parameters": {"test": True, "automated": True}
            }
            
            created = await service.create_strategy(test_data)
            await session.commit()
            
            assert created is not None, "create_strategy() returned None"
            assert created.id is not None, "Created strategy has no ID"
            assert created.name == test_data["name"], "Name mismatch"
            assert created.status == "inactive", "Default status should be 'inactive'"
            
            print(f"✅ Created strategy: {created.id}")
            print(f"   Name: {created.name}")
            print(f"   Status: {created.status}")
            
            # Store ID for later tests
            self.test_strategy_id = created.id

    @pytest.mark.asyncio
    async def test_04_service_update(self):
        """Test 2.4: StrategyService.update_strategy() updates fields."""
        from backend.services.strategy_service import StrategyService
        
        async with AsyncSessionLocal() as session:
            service = StrategyService(session)
            
            # Get a strategy to update
            all_strategies = await service.repo.get_all()
            strategy = all_strategies[0]
            
            # Update description and parameters
            updates = {
                "description": f"Updated by automated test at {datetime.now()}",
                "parameters": {"updated": True, "timestamp": str(datetime.now())}
            }
            
            updated = await service.update_strategy(strategy.id, updates)
            await session.commit()
            
            assert updated is not None, "update_strategy() returned None"
            assert updated.description == updates["description"], "Description not updated"
            assert updated.parameters["updated"] == True, "Parameters not updated"
            
            print(f"✅ Updated strategy: {strategy.id}")
            print(f"   New description: {updated.description[:50]}...")

    @pytest.mark.asyncio
    async def test_05_service_start(self):
        """Test 2.5a: StrategyService.start_strategy() changes status."""
        from backend.services.strategy_service import StrategyService
        
        async with AsyncSessionLocal() as session:
            service = StrategyService(session)
            
            # Get an inactive strategy
            all_strategies = await service.repo.get_all()
            strategy = next((s for s in all_strategies if s.status == 'inactive'), all_strategies[0])
            
            # Ensure it's stopped first
            if strategy.status != 'inactive':
                await service.stop_strategy(strategy.id)
                await session.commit()
            
            # Start it
            started = await service.start_strategy(strategy.id)
            await session.commit()
            
            assert started is not None, "start_strategy() returned None"
            assert started.status == "active", f"Status is '{started.status}', expected 'active'"
            
            print(f"✅ Started strategy: {strategy.id}")
            print(f"   Status: {started.status}")
            
            # Store for next test
            self.test_active_strategy_id = strategy.id

    @pytest.mark.asyncio
    async def test_06_service_pause(self):
        """Test 2.5b: StrategyService.pause_strategy() changes status."""
        from backend.services.strategy_service import StrategyService
        
        async with AsyncSessionLocal() as session:
            service = StrategyService(session)
            
            # Use strategy from previous test or get an active one
            strategy_id = getattr(self, 'test_active_strategy_id', None)
            if not strategy_id:
                all_strategies = await service.repo.get_all()
                strategy = next((s for s in all_strategies if s.status == 'active'), all_strategies[0])
                strategy_id = strategy.id
            
            # Pause it
            paused = await service.pause_strategy(strategy_id)
            await session.commit()
            
            assert paused is not None, "pause_strategy() returned None"
            assert paused.status == "paused", f"Status is '{paused.status}', expected 'paused'"
            
            print(f"✅ Paused strategy: {strategy_id}")
            print(f"   Status: {paused.status}")
            
            self.test_paused_strategy_id = strategy_id

    @pytest.mark.asyncio
    async def test_07_service_stop(self):
        """Test 2.5c: StrategyService.stop_strategy() changes status."""
        from backend.services.strategy_service import StrategyService
        
        async with AsyncSessionLocal() as session:
            service = StrategyService(session)
            
            # Use strategy from previous test
            strategy_id = getattr(self, 'test_paused_strategy_id', None)
            if not strategy_id:
                all_strategies = await service.repo.get_all()
                strategy = next((s for s in all_strategies if s.status != 'inactive'), all_strategies[0])
                strategy_id = strategy.id
            
            # Stop it
            stopped = await service.stop_strategy(strategy_id)
            await session.commit()
            
            assert stopped is not None, "stop_strategy() returned None"
            assert stopped.status == "inactive", f"Status is '{stopped.status}', expected 'inactive'"
            
            print(f"✅ Stopped strategy: {strategy_id}")
            print(f"   Status: {stopped.status}")


# ============================================================================
# PHASE 3: API LAYER TESTS (Optional - requires running server)
# ============================================================================

class TestPhase3API:
    """Test REST API endpoints (requires backend server running)."""

    @pytest.mark.skip(reason="Requires authentication - run manually with test_phase3_api.ps1")
    @pytest.mark.asyncio
    async def test_01_api_list_strategies(self):
        """Test 3.1: GET /api/v1/strategies returns list."""
        # This test is skipped in automated suite
        # Run test_phase3_api.ps1 for API testing
        pass


# ============================================================================
# TEST EXECUTION SUMMARY
# ============================================================================

def pytest_sessionfinish(session, exitstatus):
    """Print summary after all tests complete."""
    print("\n" + "="*80)
    print("AUTOMATED TEST SUITE COMPLETE")
    print("="*80)
    
    if exitstatus == 0:
        print("✅ All automated tests PASSED")
        print("\n📋 Next Steps:")
        print("   1. Review test output above")
        print("   2. Proceed with Phase 4-6 manual testing (browser required)")
        print("   3. Open COMPREHENSIVE_MANUAL_TEST_PLAN.md for manual test steps")
        print("   4. Optional: Debug API authentication for Phase 3 API tests")
    else:
        print("❌ Some tests FAILED")
        print("\n📋 Troubleshooting:")
        print("   1. Check error messages above")
        print("   2. Verify database connection (DATABASE_URL)")
        print("   3. Ensure test data exists (run seed_strategies.py)")
        print("   4. Check backend service imports")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    # Run with pytest
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
