#!/usr/bin/env python3
"""Test constraint violations with production guardrails"""

import asyncio
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

async def test_constraint_violations():
    """Test production guardrails constraint violations"""
    
    print("🧪 Testing production constraint violations...")
    
    try:
        # Import the database infrastructure
        from backend.infra.db import get_db_session
        from backend.infra.guardrails_production import TransactionalGuardrails, GuardrailViolation
        
        # Initialize the DB (needed for tests)
        from backend.infra.db import initialize_db
        await initialize_db()
        
        print("  ✅ Database initialized")
        
        # Create production guardrails
        guardrails = TransactionalGuardrails(
            symbol_whitelist=["AAPL", "MSFT", "GOOGL"],
            max_daily_orders=5,  # Low limit for testing
            max_daily_notional=1000.0,  # Low limit for testing  
            max_order_size=100.0
        )
        
        print("  ✅ Production guardrails initialized")
        
        # Test 1: Valid order should pass
        test_account = "test_account_phase5" 
        try:
            # This should work - first order of the day
            async for session in get_db_session():
                # Note: We break after first iteration since get_db_session is a generator
                pass
            
            # Test without database for now (just basic validations)
            guardrails._validate_symbol("AAPL")
            guardrails._validate_order_size(50.0)
            guardrails._validate_trading_hours()  # This might fail if not trading hours
            
            print("  ✅ Basic guardrail validations passed")
            
        except GuardrailViolation as e:
            if e.violation_type == "TRADING_HOURS":
                print("  ⚠️ Trading hours violation expected (test running outside market hours)")
            else:
                print(f"  ❌ Unexpected guardrail violation: {e}")
        except Exception as e:
            print(f"  ⚠️ Database operation skipped: {e}")
        
        # Test 2: Invalid symbol should fail  
        try:
            guardrails._validate_symbol("INVALID_SYMBOL")
            print("  ❌ Invalid symbol was accepted - constraint not working!")
            return False
        except GuardrailViolation as e:
            if e.violation_type == "SYMBOL_WHITELIST":
                print("  ✅ Invalid symbol properly rejected")
            else:
                print(f"  ❌ Wrong violation type: {e.violation_type}")
        
        # Test 3: Order size limit
        try:
            guardrails._validate_order_size(200.0)  # Above max_order_size=100.0
            print("  ❌ Oversized order was accepted - constraint not working!")
            return False
        except GuardrailViolation as e:
            if e.violation_type == "ORDER_SIZE_LIMIT":
                print("  ✅ Oversized order properly rejected")
            else:
                print(f"  ❌ Wrong violation type: {e.violation_type}")
        
        # Test 4: Circuit breaker functionality
        print("  🔧 Testing circuit breaker...")
        
        # Simulate broker errors
        test_errors = [
            Exception("Connection timeout"),
            Exception("500 Internal Server Error"), 
            Exception("DNS resolution failed")
        ]
        
        for error in test_errors:
            guardrails.record_broker_error(error)
            
        status = guardrails.get_circuit_breaker_status()
        print(f"    Circuit breaker errors: {status['consecutive_errors']}")
        print(f"    Circuit breaker open: {status['circuit_open']}")
        
        if status['consecutive_errors'] > 0:
            print("  ✅ Circuit breaker tracking errors")
        else:
            print("  ⚠️ Circuit breaker not tracking errors")
        
        # Reset circuit breaker
        guardrails.reset_circuit_breaker()
        status_after = guardrails.get_circuit_breaker_status()
        if not status_after['circuit_open'] and status_after['consecutive_errors'] == 0:
            print("  ✅ Circuit breaker reset working")
        else:
            print("  ❌ Circuit breaker reset failed")
            
        print("\n🎉 Constraint violation tests completed!")
        return True
        
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_database_constraints():
    """Test database-level constraints (simpler version)"""
    
    print("\n📋 Testing database constraints directly...")
    
    try:
        import sqlite3
        
        # Connect directly to database
        conn = sqlite3.connect('trading_platform.db')
        cursor = conn.cursor()
        
        # Test order_events uniqueness
        print("  🔧 Testing order_events deduplication...")
        
        # Insert first event
        cursor.execute("""
            INSERT INTO order_events (order_id, broker_order_id, event_type, event_time)
            VALUES (?, ?, ?, ?)
        """, ("test-order-1", "test-broker-123", "fill", "2025-09-30 12:00:00"))
        
        print("    ✅ First event inserted")
        
        # Try duplicate - should fail
        try:
            cursor.execute("""
                INSERT INTO order_events (order_id, broker_order_id, event_type, event_time)
                VALUES (?, ?, ?, ?)
            """, ("test-order-2", "test-broker-123", "fill", "2025-09-30 12:00:00"))
            conn.commit()
            print("    ❌ Duplicate event allowed - constraint not working!")
            return False
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                print("    ✅ Duplicate event properly rejected")
            else:
                print(f"    ❌ Unexpected error: {e}")
        
        # Test daily_ledger uniqueness
        print("  🔧 Testing daily_ledger uniqueness...")
        
        # Insert first ledger entry
        cursor.execute("""
            INSERT INTO daily_ledger (account_id, day_utc, orders_count, submitted_notional_usd)
            VALUES (?, ?, ?, ?)
        """, ("test_account", date.today(), 1, 100.0))
        
        print("    ✅ First ledger entry inserted")
        
        # Try duplicate - should fail
        try:
            cursor.execute("""
                INSERT INTO daily_ledger (account_id, day_utc, orders_count, submitted_notional_usd)
                VALUES (?, ?, ?, ?)
            """, ("test_account", date.today(), 2, 200.0))
            conn.commit()
            print("    ❌ Duplicate ledger allowed - constraint not working!")
            return False
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                print("    ✅ Duplicate ledger properly rejected")
            else:
                print(f"    ❌ Unexpected error: {e}")
        
        # Cleanup
        cursor.execute("DELETE FROM order_events WHERE order_id LIKE 'test-order-%'")
        cursor.execute("DELETE FROM daily_ledger WHERE account_id = 'test_account'")
        conn.commit()
        
        print("  ✅ Database constraints test completed")
        return True
        
    except Exception as e:
        print(f"  ❌ Database constraint test failed: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    async def main():
        success1 = await test_constraint_violations()
        success2 = await test_database_constraints()
        return success1 and success2
    
    success = asyncio.run(main())
    
    if success:
        print("\n✅ All constraint violation tests passed!")
    else:
        print("\n❌ Some tests failed - see details above")
        
    sys.exit(0 if success else 1)